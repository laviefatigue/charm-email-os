"""Read-only pre-flight checks for the EOD reapply tool.

Diagnostic helper that exercises every read path the orchestrator depends on,
without making any mutating EB call. Safe to run any time, against any
workspace, against any campaign — including paused ones.

Use cases:
  - Operator pre-flight before running `reapply --apply`.
  - Daily ops health check ("is workspace X still wired up?").
  - L5 staging gate: collapses runbook sections 1–3 into one command.

Design notes:
  - Each check returns a CheckResult with status (ok/warn/fail/skip) and detail.
  - The sequence early-exits on FAIL of a load-bearing check (e.g. DB unreachable
    means we can't do anything else).
  - Soft-failures (live tag missing, campaign archived, etc.) WARN but continue
    so the operator gets a complete picture.
  - Never mutates state. Read-only by construction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import asyncpg

from .db import fetch_workspace_context
from .eb_client import EBClient, EmailBisonAPIError
from .reapply import _ACTIVE_STATUSES, _build_schedule_from_eb


class CheckStatus(StrEnum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    detail: str = ""


@dataclass
class CheckReport:
    workspace_name: str
    campaign_id: int | None
    results: list[CheckResult] = field(default_factory=list)

    @property
    def overall_status(self) -> CheckStatus:
        """Worst status across all results. SKIP doesn't count toward 'worst'."""
        statuses = {r.status for r in self.results if r.status != CheckStatus.SKIP}
        if CheckStatus.FAIL in statuses:
            return CheckStatus.FAIL
        if CheckStatus.WARN in statuses:
            return CheckStatus.WARN
        return CheckStatus.OK

    def add(self, name: str, status: CheckStatus, detail: str = "") -> None:
        self.results.append(CheckResult(name, status, detail))


async def run_checks(
    *,
    database_url: str,
    eb_base_url: str,
    workspace_name: str,
    campaign_id: int | None = None,
    live_tag_name: str = "live",
    min_target_size: int = 1,
) -> CheckReport:
    """Run all pre-flight checks. Returns a CheckReport — never raises.

    If campaign_id is None, only workspace-level checks (DB + EB auth + live tag)
    are run. With campaign_id, also probes campaign + schedule + sender list +
    expected diff.
    """
    report = CheckReport(workspace_name=workspace_name, campaign_id=campaign_id)

    # ----- 1. DB connection -----
    try:
        conn = await asyncpg.connect(database_url)
    except Exception as e:
        report.add("db_connection", CheckStatus.FAIL, f"{type(e).__name__}: {e}")
        return report
    report.add("db_connection", CheckStatus.OK, "asyncpg.connect succeeded")

    # ----- 2. Workspace lookup -----
    # `finally` is the single close site so we can't accidentally double-close
    # and mask one error with another from a second close call.
    workspace_lookup_failed = False
    try:
        try:
            ctx = await fetch_workspace_context(conn, workspace_name)
        except Exception as e:
            report.add("workspace_lookup", CheckStatus.FAIL, f"{type(e).__name__}: {e}")
            workspace_lookup_failed = True
    finally:
        await conn.close()
    if workspace_lookup_failed:
        return report

    if ctx is None:
        report.add(
            "workspace_lookup", CheckStatus.FAIL,
            f"no active workspace + active key for {workspace_name!r}",
        )
        return report
    report.add(
        "workspace_lookup", CheckStatus.OK,
        f"workspace_id={ctx.workspace_id}, eb_workspace_id={ctx.emailbison_workspace_id}",
    )

    # ----- 3. EB auth (via /api/tags — cheapest auth probe) -----
    async with EBClient(base_url=eb_base_url, api_key=ctx.api_key) as eb:
        try:
            tags = await eb.get_workspace_tags()
        except EmailBisonAPIError as e:
            report.add("eb_auth", CheckStatus.FAIL, f"GET /api/tags failed: {e}")
            return report
        report.add(
            "eb_auth", CheckStatus.OK,
            f"GET /api/tags returned {len(tags)} tag(s) — auth verified",
        )

        # ----- 4. Live tag resolves -----
        live_tag_id: int | None = next(
            (int(t["id"]) for t in tags if t.get("name") == live_tag_name and "id" in t),
            None,
        )
        if live_tag_id is None:
            report.add(
                "live_tag_resolves", CheckStatus.FAIL,
                f"tag {live_tag_name!r} does not exist in workspace; "
                f"available: {sorted(t.get('name', '?') for t in tags)[:10]}",
            )
            return report
        report.add(
            "live_tag_resolves", CheckStatus.OK,
            f"tag {live_tag_name!r} → id={live_tag_id}",
        )

        # ----- 5. Live tag set size -----
        try:
            target_senders = await eb.list_senders_with_tag(live_tag_id)
        except EmailBisonAPIError as e:
            report.add("live_tag_set_size", CheckStatus.FAIL, f"GET /api/sender-emails failed: {e}")
            return report
        size = len(target_senders)
        if size == 0:
            report.add(
                "live_tag_set_size", CheckStatus.FAIL,
                "live tag set is empty; reapply would refuse to wipe campaigns",
            )
        elif size < min_target_size:
            report.add(
                "live_tag_set_size", CheckStatus.WARN,
                f"only {size} sender(s) tagged {live_tag_name!r} (below min_target_size={min_target_size})",
            )
        else:
            report.add(
                "live_tag_set_size", CheckStatus.OK,
                f"{size} sender(s) have the {live_tag_name!r} tag",
            )

        # If no campaign id, we're done — workspace-level checks complete
        if campaign_id is None:
            for name in ("campaign_exists", "campaign_active", "schedule_fetches",
                        "schedule_parses", "campaign_senders_fetches", "expected_diff"):
                report.add(name, CheckStatus.SKIP, "no --campaign-id given")
            return report

        # ----- 6. Campaign exists -----
        try:
            campaign = await eb.get_campaign(campaign_id)
        except EmailBisonAPIError as e:
            report.add("campaign_exists", CheckStatus.FAIL,
                       f"GET /api/campaigns/{campaign_id} failed: {e}")
            return report
        camp_name = campaign.get("name", "?")
        camp_status = campaign.get("status", "?")
        report.add(
            "campaign_exists", CheckStatus.OK,
            f"campaign #{campaign_id} = {camp_name!r} status={camp_status!r}",
        )

        # ----- 7. Campaign is in an active state -----
        status_lower = str(camp_status).lower()
        if status_lower in _ACTIVE_STATUSES:
            report.add("campaign_active", CheckStatus.OK, f"status={camp_status!r}")
        else:
            report.add(
                "campaign_active", CheckStatus.WARN,
                f"status={camp_status!r} not in active set {sorted(_ACTIVE_STATUSES)}; "
                f"reapply would skip with SKIPPED_NOT_ACTIVE",
            )

        # ----- 8. Schedule fetches -----
        try:
            sched_data = await eb.get_campaign_schedule(campaign_id)
        except EmailBisonAPIError as e:
            report.add("schedule_fetches", CheckStatus.FAIL,
                       f"GET /api/campaigns/{campaign_id}/schedule failed: {e}")
            return report
        report.add(
            "schedule_fetches", CheckStatus.OK,
            f"tz={sched_data.get('timezone', '?')!r}, "
            f"hours={sched_data.get('start_time', '?')}–{sched_data.get('end_time', '?')}",
        )

        # ----- 9. Schedule parses to a valid CampaignSchedule -----
        try:
            schedule = _build_schedule_from_eb(sched_data)
        except (KeyError, ValueError) as e:
            report.add("schedule_parses", CheckStatus.FAIL, str(e))
            return report
        sending_days = ",".join(
            label for label, on in [
                ("Mon", schedule.monday), ("Tue", schedule.tuesday), ("Wed", schedule.wednesday),
                ("Thu", schedule.thursday), ("Fri", schedule.friday),
                ("Sat", schedule.saturday), ("Sun", schedule.sunday),
            ] if on
        )
        report.add(
            "schedule_parses", CheckStatus.OK,
            f"days=[{sending_days}] {schedule.start_time}–{schedule.end_time} {schedule.timezone}",
        )

        # ----- 10. Currently-attached senders fetch -----
        try:
            prior_senders = await eb.get_campaign_senders(campaign_id)
        except EmailBisonAPIError as e:
            report.add("campaign_senders_fetches", CheckStatus.FAIL,
                       f"GET /api/campaigns/{campaign_id}/sender-emails failed: {e}")
            return report
        report.add(
            "campaign_senders_fetches", CheckStatus.OK,
            f"{len(prior_senders)} sender(s) currently attached to campaign",
        )

        # ----- 11. Expected diff (informational) -----
        target_ids = {int(s["id"]) for s in target_senders if "id" in s}
        prior_ids = {int(s["id"]) for s in prior_senders if "id" in s}
        to_attach = sorted(target_ids - prior_ids)
        to_remove = sorted(prior_ids - target_ids)

        if not to_attach and not to_remove:
            report.add(
                "expected_diff", CheckStatus.OK,
                "no diff — reapply would short-circuit as SKIPPED_NO_DIFF",
            )
        else:
            removal_pct = (len(to_remove) / len(prior_ids) * 100) if prior_ids else 0.0
            tail_attach = "..." if len(to_attach) > 5 else ""
            tail_remove = "..." if len(to_remove) > 5 else ""
            report.add(
                "expected_diff", CheckStatus.OK,
                f"would attach {len(to_attach)} {to_attach[:5]}{tail_attach}, "
                f"remove {len(to_remove)} {to_remove[:5]}{tail_remove} "
                f"({removal_pct:.0f}% of currently-attached)",
            )

    return report


# ---------- Rendering helpers ----------

_STATUS_GLYPH = {
    CheckStatus.OK:   "[ OK  ]",
    CheckStatus.WARN: "[WARN ]",
    CheckStatus.FAIL: "[FAIL ]",
    CheckStatus.SKIP: "[SKIP ]",
}


def render_report_text(report: CheckReport) -> str:
    """Human-readable check report."""
    lines = []
    lines.append("=" * 78)
    header = f"PRE-FLIGHT CHECK — workspace={report.workspace_name!r}"
    if report.campaign_id is not None:
        header += f" campaign=#{report.campaign_id}"
    lines.append(header)
    lines.append("=" * 78)
    for r in report.results:
        glyph = _STATUS_GLYPH[r.status]
        lines.append(f"  {glyph}  {r.name:30s}  {r.detail}")
    lines.append("-" * 78)
    lines.append(f"  OVERALL: {report.overall_status.value.upper()}")
    lines.append("=" * 78)
    return "\n".join(lines)


def report_to_dict(report: CheckReport) -> dict[str, Any]:
    return {
        "workspace_name": report.workspace_name,
        "campaign_id": report.campaign_id,
        "overall_status": report.overall_status.value,
        "checks": [
            {"name": r.name, "status": r.status.value, "detail": r.detail}
            for r in report.results
        ],
    }


# Exit code mapping for the CLI
_CHECK_EXIT_CODE = {
    CheckStatus.OK:   0,
    CheckStatus.WARN: 1,
    CheckStatus.FAIL: 2,
    CheckStatus.SKIP: 0,  # only reached when ALL are skip — degenerate
}


def exit_code_for_check(report: CheckReport) -> int:
    return _CHECK_EXIT_CODE[report.overall_status]
