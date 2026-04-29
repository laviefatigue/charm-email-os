"""
Reapply orchestrator — the unit of work.

Reapplies a campaign's sender attachment to match the current `live`-tagged set.
Designed as a library function so v2 (a scheduler) can call it per (campaign,
local_date) without changes.

Invariants enforced:
  1. Pause is always followed by a resume attempt (try/finally).
  2. Mutations only when apply=True. Dry-run never makes mutating calls.
  3. SUCCEEDED is reachable only via set-equality verification post-mutation.
  4. Empty target set or oversized removal → SKIPPED with no mutation.
  5. Attach happens before remove (fail-closed ordering: if attach fails after
     remove succeeded, working senders would be gone for nothing).

Operator action required iff status == FAILED_LEFT_PAUSED. This is the only
state where the campaign is left in a non-running condition without intent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from enum import StrEnum
from typing import Any, Protocol

from .window import CampaignSchedule, evaluate_window

# Active EB statuses on which we operate. EB has been observed to mix case;
# we lowercase for comparison. "Sending" appears when a campaign is mid-send.
_ACTIVE_STATUSES = {"active", "queued", "sending"}


class ReapplyStatus(StrEnum):
    SUCCEEDED = "succeeded"
    SKIPPED_NO_DIFF = "skipped_no_diff"
    SKIPPED_EMPTY_LIVE = "skipped_empty_live"
    SKIPPED_NOT_ACTIVE = "skipped_not_active"
    SKIPPED_TIME_GATE = "skipped_time_gate"
    SKIPPED_OVERSIZED_REMOVAL = "skipped_oversized_removal"
    SKIPPED_DRY_RUN = "skipped_dry_run"
    FAILED_PRE_PAUSE = "failed_pre_pause"
    FAILED_POST_RESUME = "failed_post_resume"
    FAILED_LEFT_PAUSED = "failed_left_paused"


@dataclass
class ReapplyResult:
    status: ReapplyStatus
    campaign_id: int
    workspace_name: str
    is_dry_run: bool = False

    target_set: list[int] = field(default_factory=list)
    prior_set: list[int] = field(default_factory=list)
    attached_ids: list[int] = field(default_factory=list)
    removed_ids: list[int] = field(default_factory=list)
    final_set: list[int] = field(default_factory=list)

    verify_passed: bool | None = None
    error_message: str | None = None
    error_step: str | None = None

    @property
    def operator_action_required(self) -> bool:
        """True iff the campaign may be left paused without intent."""
        return self.status == ReapplyStatus.FAILED_LEFT_PAUSED


class _EBProtocol(Protocol):
    """Subset of EBClient methods the orchestrator needs.

    Defined as a Protocol so tests can substitute a fake without inheriting.
    """
    async def get_campaign(self, campaign_id: int) -> dict[str, Any]: ...
    async def get_campaign_schedule(self, campaign_id: int) -> dict[str, Any]: ...
    async def pause_campaign(self, campaign_id: int) -> dict[str, Any]: ...
    async def resume_campaign(self, campaign_id: int) -> dict[str, Any]: ...
    async def get_campaign_senders(self, campaign_id: int) -> list[dict[str, Any]]: ...
    async def attach_senders(self, campaign_id: int, sender_email_ids: list[int]) -> dict[str, Any]: ...
    async def remove_senders(self, campaign_id: int, sender_email_ids: list[int]) -> dict[str, Any]: ...
    async def list_senders_with_tag(self, tag_id: int, *, per_page: int = 100) -> list[dict[str, Any]]: ...
    async def resolve_tag_id(self, tag_name: str) -> int | None: ...


def _parse_eb_time(s: str) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS' from EB schedule response."""
    parts = s.strip().split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    if len(parts) == 3:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"unrecognized time format: {s!r}")


def _build_schedule_from_eb(data: dict[str, Any]) -> CampaignSchedule:
    """Construct a CampaignSchedule from the EB /schedule response payload."""
    required = (
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "start_time", "end_time", "timezone",
    )
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"schedule response missing fields: {missing}")
    return CampaignSchedule(
        monday=bool(data["monday"]),
        tuesday=bool(data["tuesday"]),
        wednesday=bool(data["wednesday"]),
        thursday=bool(data["thursday"]),
        friday=bool(data["friday"]),
        saturday=bool(data["saturday"]),
        sunday=bool(data["sunday"]),
        start_time=_parse_eb_time(data["start_time"]),
        end_time=_parse_eb_time(data["end_time"]),
        timezone=data["timezone"],
    )


async def reapply_campaign(
    *,
    eb: _EBProtocol,
    workspace_name: str,
    campaign_id: int,
    live_tag_name: str = "live",
    apply: bool = False,
    skip_time_check: bool = False,
    buffer_minutes: int = 60,
    now_utc: datetime | None = None,
    last_run_local_date: date | None = None,
    min_target_size: int = 1,
    max_removal_pct: float = 50.0,
) -> ReapplyResult:
    """Reapply the live-tagged sender set to a campaign's attachment list.

    Returns a ReapplyResult. Never raises (all failures are encoded in status).
    The caller is responsible for inspecting `operator_action_required`.
    """
    # Import here to avoid circulars; EmailBisonAPIError is what eb methods raise.
    from .eb_client import EmailBisonAPIError

    if now_utc is None:
        now_utc = datetime.now(UTC)

    result = ReapplyResult(
        status=ReapplyStatus.FAILED_PRE_PAUSE,
        campaign_id=campaign_id,
        workspace_name=workspace_name,
        is_dry_run=not apply,
    )

    # ----- Step 1: Verify campaign exists and is active -----
    try:
        campaign = await eb.get_campaign(campaign_id)
    except EmailBisonAPIError as e:
        result.error_message = f"get_campaign failed: {e}"
        result.error_step = "get_campaign"
        return result

    campaign_status_raw = campaign.get("status") or ""
    if campaign_status_raw.lower() not in _ACTIVE_STATUSES:
        result.status = ReapplyStatus.SKIPPED_NOT_ACTIVE
        result.error_message = (
            f"campaign status is {campaign_status_raw!r}; "
            f"expected one of {sorted(_ACTIVE_STATUSES)}"
        )
        return result

    # ----- Step 2: Time gate (optional) -----
    if not skip_time_check:
        try:
            sched_data = await eb.get_campaign_schedule(campaign_id)
        except EmailBisonAPIError as e:
            result.error_message = f"get_campaign_schedule failed: {e}"
            result.error_step = "get_schedule"
            return result

        try:
            schedule = _build_schedule_from_eb(sched_data)
        except (KeyError, ValueError) as e:
            result.error_message = f"schedule parse failed: {e}"
            result.error_step = "parse_schedule"
            return result

        decision = evaluate_window(
            schedule=schedule,
            now_utc=now_utc,
            last_run_local_date=last_run_local_date,
            buffer_minutes=buffer_minutes,
        )
        if not decision.should_run:
            result.status = ReapplyStatus.SKIPPED_TIME_GATE
            result.error_message = decision.reason
            return result

    # ----- Step 3: Resolve live tag id -----
    try:
        live_tag_id = await eb.resolve_tag_id(live_tag_name)
    except EmailBisonAPIError as e:
        result.error_message = f"resolve_tag_id failed: {e}"
        result.error_step = "resolve_tag"
        return result

    if live_tag_id is None:
        result.status = ReapplyStatus.SKIPPED_EMPTY_LIVE
        result.error_message = f"tag {live_tag_name!r} does not exist in workspace"
        result.error_step = "resolve_tag"
        return result

    # ----- Step 4: Compute target and prior sets -----
    try:
        target_senders = await eb.list_senders_with_tag(live_tag_id)
        prior_senders = await eb.get_campaign_senders(campaign_id)
    except EmailBisonAPIError as e:
        result.error_message = f"set fetch failed: {e}"
        result.error_step = "fetch_sets"
        return result

    target_ids = sorted({int(s["id"]) for s in target_senders if "id" in s})
    prior_ids = sorted({int(s["id"]) for s in prior_senders if "id" in s})
    result.target_set = target_ids
    result.prior_set = prior_ids

    # Guard: empty / suspiciously small target
    if len(target_ids) < min_target_size:
        result.status = ReapplyStatus.SKIPPED_EMPTY_LIVE
        result.error_message = (
            f"target set has {len(target_ids)} senders (min={min_target_size}); "
            f"refusing to wipe campaign senders"
        )
        return result

    # Compute diff
    target_set = set(target_ids)
    prior_set = set(prior_ids)
    to_attach = sorted(target_set - prior_set)
    to_remove = sorted(prior_set - target_set)
    result.attached_ids = to_attach
    result.removed_ids = to_remove

    # No-op fast path
    if not to_attach and not to_remove:
        result.status = ReapplyStatus.SKIPPED_NO_DIFF
        result.final_set = prior_ids
        result.verify_passed = True
        return result

    # Guard: oversized removal (suggests upstream tag corruption)
    if prior_ids and to_remove:
        removal_pct = (len(to_remove) / len(prior_ids)) * 100
        if removal_pct > max_removal_pct:
            result.status = ReapplyStatus.SKIPPED_OVERSIZED_REMOVAL
            result.error_message = (
                f"removal {removal_pct:.1f}% exceeds max {max_removal_pct}%; "
                f"would remove {len(to_remove)} of {len(prior_ids)} current senders"
            )
            return result

    # Dry run: stop here, no mutation
    if not apply:
        result.status = ReapplyStatus.SKIPPED_DRY_RUN
        result.final_set = prior_ids
        return result

    # ----- Step 5: Pause -----
    try:
        pause_resp = await eb.pause_campaign(campaign_id)
    except EmailBisonAPIError as e:
        # Campaign untouched; nothing to clean up
        result.error_message = f"pause failed: {e}"
        result.error_step = "pause"
        return result

    paused_status = (pause_resp.get("status") or "").lower()
    if paused_status != "paused":
        # EB returned 200 but did not transition to Paused. Try to resume defensively
        # (it might still be Active and acked the call as a no-op).
        # If the defensive resume ALSO fails, escalate to FAILED_LEFT_PAUSED — the
        # campaign may genuinely be paused and we have no signal otherwise.
        defensive_resume_error: str | None = None
        try:
            await eb.resume_campaign(campaign_id)
        except EmailBisonAPIError as resume_e:
            defensive_resume_error = str(resume_e)

        result.error_message = f"pause returned status={paused_status!r}, expected 'paused'"
        result.error_step = "pause_verify"
        if defensive_resume_error is not None:
            # Treat as left-paused — operator must verify
            result.status = ReapplyStatus.FAILED_LEFT_PAUSED
            result.error_message += f" | defensive resume also failed: {defensive_resume_error}"
        return result

    # ----- From here, resume MUST be attempted in finally -----
    try:
        # Step 6: Attach first (fail-closed ordering)
        if to_attach:
            try:
                await eb.attach_senders(campaign_id, to_attach)
            except EmailBisonAPIError as e:
                result.error_message = f"attach failed: {e}"
                result.error_step = "attach"
                return result

        # Step 7: Remove
        if to_remove:
            try:
                await eb.remove_senders(campaign_id, to_remove)
            except EmailBisonAPIError as e:
                result.error_message = f"remove failed: {e}"
                result.error_step = "remove"
                return result

        # Step 8: Verify by re-fetching
        try:
            final_senders = await eb.get_campaign_senders(campaign_id)
        except EmailBisonAPIError as e:
            result.error_message = f"verify fetch failed: {e}"
            result.error_step = "verify_fetch"
            return result

        final_ids = sorted({int(s["id"]) for s in final_senders if "id" in s})
        result.final_set = final_ids
        result.verify_passed = set(final_ids) == target_set

        if result.verify_passed:
            result.status = ReapplyStatus.SUCCEEDED
        else:
            result.status = ReapplyStatus.FAILED_POST_RESUME
            result.error_message = (
                f"verify mismatch: final={final_ids}, expected={sorted(target_set)}"
            )
            result.error_step = "verify"
    finally:
        # CRITICAL: always attempt resume.
        try:
            await eb.resume_campaign(campaign_id)
        except EmailBisonAPIError as e:
            # Resume failed — operator action required.
            result.status = ReapplyStatus.FAILED_LEFT_PAUSED
            prior_msg = result.error_message or ""
            sep = " | " if prior_msg else ""
            result.error_message = f"{prior_msg}{sep}resume failed: {e}"
            if not result.error_step:
                result.error_step = "resume"

    return result
