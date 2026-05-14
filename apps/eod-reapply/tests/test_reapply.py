"""L3 tests for reapply.reapply_campaign — orchestrator with failure injection.

Architecture: a FakeEBClient records every call and returns scripted responses.
Failure injection is by step name. Tests assert both per-case outcomes AND
cross-case invariants.

Critical invariants (must hold across ALL tests, especially failure cases):
  INV-1: If pause succeeds, resume is called exactly once.
  INV-2: dry-run never makes a mutating call.
  INV-3: SUCCEEDED is reachable only via verify-set-equality passing.
  INV-4: Empty/suspect target set never proceeds to mutation.
  INV-5: Attach precedes remove (fail-closed ordering).
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from eod_reapply.eb_client import EmailBisonAPIError
from eod_reapply.reapply import (
    ReapplyStatus,
    reapply_campaign,
)

# ---------- Schedule fixture (matches a Sammy-like Sydney schedule) ----------

SAMMY_SCHEDULE_RESPONSE = {
    "id": 1,
    "type": "Generated",
    "monday": True, "tuesday": True, "wednesday": True,
    "thursday": True, "friday": True, "saturday": False, "sunday": False,
    "start_time": "08:00", "end_time": "17:00",
    "timezone": "Australia/Sydney",
    "created_at": "2026-04-14T16:59:21.000000Z",
    "updated_at": "2026-04-14T16:59:21.000000Z",
}

# A UTC time inside the Sydney reapply window (Thu 18:00 AEDT = 07:00 UTC same day)
INSIDE_SYDNEY_WINDOW = datetime(2026, 1, 15, 7, 0, tzinfo=UTC)
# Outside window — Thursday 16:00 AEDT (before end) = 05:00 UTC
OUTSIDE_SYDNEY_WINDOW = datetime(2026, 1, 15, 5, 0, tzinfo=UTC)


# =============================================================================
# Fake EB client
# =============================================================================

class FakeEBClient:
    """Records every call. Returns scripted responses. Supports failure injection."""

    def __init__(self):
        # Call log: list of (method_name, args_tuple)
        self.calls: list[tuple[str, tuple]] = []

        # Scripted responses
        self.campaign_response: dict = {"id": 1, "name": "Test", "status": "Active"}
        self.schedule_response: dict = dict(SAMMY_SCHEDULE_RESPONSE)
        self.tags_response: list[dict] = [
            {"id": 5, "name": "live"},
            {"id": 6, "name": "reserve"},
        ]
        # By default, target = {10, 11, 12}; prior = {11, 99}
        # Diff: attach {10, 12}, remove {99}
        self.target_senders: list[dict] = [{"id": 10}, {"id": 11}, {"id": 12}]
        self.prior_senders_history: list[list[dict]] = [
            [{"id": 11}, {"id": 99}],   # 1st call (compute prior)
            [{"id": 10}, {"id": 11}, {"id": 12}],  # 2nd call (verify) — matches target
        ]
        self.pause_response: dict = {"id": 1, "status": "Paused"}
        self.resume_response: dict = {"id": 1, "status": "Queued"}
        self.attach_response: dict = {"success": True}
        self.remove_response: dict = {"success": True}

        # Failure injection: if set, the named method will raise on its next call
        self.fail_at: str | None = None
        self.fail_with_status: int = 500

        # Counter for prior_senders_history
        self._prior_call_idx = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    def _record(self, method: str, *args):
        self.calls.append((method, args))
        if self.fail_at == method:
            raise EmailBisonAPIError(self.fail_with_status, f"injected failure at {method}")

    # --- Methods ---

    async def get_campaign(self, campaign_id):
        self._record("get_campaign", campaign_id)
        return dict(self.campaign_response)

    async def get_campaign_schedule(self, campaign_id):
        self._record("get_campaign_schedule", campaign_id)
        return dict(self.schedule_response)

    async def pause_campaign(self, campaign_id):
        self._record("pause_campaign", campaign_id)
        return dict(self.pause_response)

    async def resume_campaign(self, campaign_id):
        self._record("resume_campaign", campaign_id)
        return dict(self.resume_response)

    async def get_campaign_senders(self, campaign_id):
        self._record("get_campaign_senders", campaign_id)
        idx = min(self._prior_call_idx, len(self.prior_senders_history) - 1)
        result = list(self.prior_senders_history[idx])
        self._prior_call_idx += 1
        return result

    async def attach_senders(self, campaign_id, sender_email_ids):
        self._record("attach_senders", campaign_id, tuple(sender_email_ids))
        return dict(self.attach_response)

    async def remove_senders(self, campaign_id, sender_email_ids):
        self._record("remove_senders", campaign_id, tuple(sender_email_ids))
        return dict(self.remove_response)

    async def list_senders_with_tag(self, tag_id, *, per_page=100):
        self._record("list_senders_with_tag", tag_id)
        return list(self.target_senders)

    async def resolve_tag_id(self, tag_name):
        self._record("resolve_tag_id", tag_name)
        for t in self.tags_response:
            if t.get("name") == tag_name:
                return int(t["id"])
        return None

    # --- Test introspection helpers ---

    def methods_called(self) -> list[str]:
        return [c[0] for c in self.calls]

    def call_count(self, method: str) -> int:
        return sum(1 for c in self.calls if c[0] == method)

    def last_call(self, method: str) -> tuple:
        for m, args in reversed(self.calls):
            if m == method:
                return args
        raise AssertionError(f"{method} was never called")

    def index_of(self, method: str) -> int:
        """Return the position of the first call to `method`. -1 if never called."""
        for i, (m, _) in enumerate(self.calls):
            if m == method:
                return i
        return -1


# =============================================================================
# Helpers
# =============================================================================

async def _no_sleep(_seconds: float) -> None:
    """No-op sleep so tests don't actually wait during verify settle-retry."""
    return None


async def _run(eb=None, **overrides):
    """Run reapply_campaign with sensible defaults. Returns (result, eb)."""
    if eb is None:
        eb = FakeEBClient()
    kwargs = dict(
        eb=eb,
        workspace_name="Charm",
        campaign_id=1,
        live_tag_name="live",
        apply=True,
        skip_time_check=False,
        buffer_minutes=60,
        now_utc=INSIDE_SYDNEY_WINDOW,
        last_run_local_date=None,
        sleep_func=_no_sleep,
    )
    kwargs.update(overrides)
    return await reapply_campaign(**kwargs), eb


def _assert_resume_called_after_pause(eb: FakeEBClient):
    """INV-1: if pause succeeded, resume must have been called."""
    if "pause_campaign" in eb.methods_called():
        # If pause was the *failure point*, resume may legitimately not be called —
        # but in our failure-injection model, pause failure raises before recording.
        # When pause is in the call log, pause succeeded (or returned non-Paused
        # status, in which case the orchestrator does still try resume defensively).
        assert "resume_campaign" in eb.methods_called(), (
            f"INVARIANT VIOLATED: pause was called but resume was not. "
            f"Methods called: {eb.methods_called()}"
        )


def _assert_no_mutation(eb: FakeEBClient):
    """INV-2: zero mutating calls."""
    mutating = {"pause_campaign", "resume_campaign", "attach_senders", "remove_senders"}
    called_mutating = set(eb.methods_called()) & mutating
    assert not called_mutating, f"dry-run made mutating calls: {called_mutating}"


# =============================================================================
# Happy paths
# =============================================================================

class TestHappyPath:
    async def test_succeeded_with_diff(self):
        result, eb = await _run()
        assert result.status == ReapplyStatus.SUCCEEDED, result.error_message
        assert result.target_set == [10, 11, 12]
        assert result.prior_set == [11, 99]
        assert result.attached_ids == [10, 12]
        assert result.removed_ids == [99]
        assert result.final_set == [10, 11, 12]
        assert result.verify_passed is True
        assert result.is_dry_run is False
        assert result.operator_action_required is False
        _assert_resume_called_after_pause(eb)

    async def test_succeeded_no_diff_no_mutation(self):
        eb = FakeEBClient()
        # Make prior == target so diff is empty
        eb.prior_senders_history = [
            [{"id": 10}, {"id": 11}, {"id": 12}],
            [{"id": 10}, {"id": 11}, {"id": 12}],
        ]
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SKIPPED_NO_DIFF
        assert result.attached_ids == []
        assert result.removed_ids == []
        assert result.verify_passed is True
        # No-diff fast path: no pause, no mutation
        assert "pause_campaign" not in eb.methods_called()
        assert "attach_senders" not in eb.methods_called()
        assert "remove_senders" not in eb.methods_called()

    async def test_attach_before_remove(self):
        # INV-5: attach must precede remove in call order
        result, eb = await _run()
        assert result.status == ReapplyStatus.SUCCEEDED
        attach_idx = eb.index_of("attach_senders")
        remove_idx = eb.index_of("remove_senders")
        assert attach_idx >= 0 and remove_idx >= 0
        assert attach_idx < remove_idx, (
            f"INV-5 violated: attach at {attach_idx}, remove at {remove_idx}"
        )

    async def test_succeeded_attach_only_no_remove(self):
        eb = FakeEBClient()
        # target is superset of prior — only attaches
        eb.prior_senders_history = [
            [{"id": 11}],
            [{"id": 10}, {"id": 11}, {"id": 12}],
        ]
        result, _ = await _run(eb=eb)
        assert result.status == ReapplyStatus.SUCCEEDED
        assert result.attached_ids == [10, 12]
        assert result.removed_ids == []

    async def test_succeeded_remove_only_no_attach(self):
        eb = FakeEBClient()
        # prior is superset of target — but oversized removal would trip the guard
        # so we make target=2 and prior=3 (33% removal, under 50% default)
        eb.target_senders = [{"id": 10}, {"id": 11}]
        eb.prior_senders_history = [
            [{"id": 10}, {"id": 11}, {"id": 99}],
            [{"id": 10}, {"id": 11}],  # final, matches target
        ]
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SUCCEEDED
        assert result.attached_ids == []
        assert result.removed_ids == [99]
        # attach_senders should not have been called
        assert "attach_senders" not in eb.methods_called()


# =============================================================================
# Dry run (INV-2)
# =============================================================================

class TestDryRun:
    async def test_dry_run_no_mutation(self):
        result, eb = await _run(apply=False)
        assert result.status == ReapplyStatus.SKIPPED_DRY_RUN
        assert result.is_dry_run is True
        assert result.attached_ids == [10, 12]  # what would be attached
        assert result.removed_ids == [99]
        _assert_no_mutation(eb)

    async def test_dry_run_no_diff_still_no_mutation(self):
        eb = FakeEBClient()
        eb.prior_senders_history = [
            [{"id": 10}, {"id": 11}, {"id": 12}],
            [{"id": 10}, {"id": 11}, {"id": 12}],
        ]
        result, eb = await _run(eb=eb, apply=False)
        assert result.status == ReapplyStatus.SKIPPED_NO_DIFF
        _assert_no_mutation(eb)

    async def test_dry_run_with_failure_injection_no_mutation(self):
        # Even if a non-mutating step "fails", dry-run must not mutate
        eb = FakeEBClient()
        # Inject failure at attach (which dry-run shouldn't reach anyway)
        eb.fail_at = "attach_senders"
        result, eb = await _run(eb=eb, apply=False)
        # Should reach SKIPPED_DRY_RUN without ever calling attach
        assert result.status == ReapplyStatus.SKIPPED_DRY_RUN
        _assert_no_mutation(eb)


# =============================================================================
# Skip cases (no mutation)
# =============================================================================

class TestSkipCases:
    async def test_campaign_not_active(self):
        eb = FakeEBClient()
        eb.campaign_response = {"id": 1, "name": "Test", "status": "Archived"}
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SKIPPED_NOT_ACTIVE
        assert "Archived" in result.error_message
        _assert_no_mutation(eb)

    async def test_campaign_paused_status_skipped(self):
        # Already paused — we don't operate on paused campaigns
        eb = FakeEBClient()
        eb.campaign_response = {"id": 1, "name": "Test", "status": "Paused"}
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SKIPPED_NOT_ACTIVE
        _assert_no_mutation(eb)

    async def test_status_case_insensitive(self):
        # EB has been observed to return both "Active" and "active"
        eb = FakeEBClient()
        eb.campaign_response = {"id": 1, "status": "active"}
        result, _ = await _run(eb=eb)
        assert result.status == ReapplyStatus.SUCCEEDED

    async def test_time_gate_too_early(self):
        # 16:00 AEDT — before end_time — should skip
        result, eb = await _run(now_utc=OUTSIDE_SYDNEY_WINDOW)
        assert result.status == ReapplyStatus.SKIPPED_TIME_GATE
        assert "too early" in result.error_message.lower()
        _assert_no_mutation(eb)

    async def test_time_gate_already_ran_today(self):
        # Already ran today (Sydney local) — skip
        result, eb = await _run(
            now_utc=INSIDE_SYDNEY_WINDOW,
            last_run_local_date=date(2026, 1, 15),
        )
        assert result.status == ReapplyStatus.SKIPPED_TIME_GATE
        assert "already ran" in result.error_message
        _assert_no_mutation(eb)

    async def test_skip_time_check_overrides_gate(self):
        # Use --skip-time-check to bypass the time gate even when too early
        result, _ = await _run(
            now_utc=OUTSIDE_SYDNEY_WINDOW,
            skip_time_check=True,
        )
        assert result.status == ReapplyStatus.SUCCEEDED

    async def test_live_tag_missing_skipped(self):
        eb = FakeEBClient()
        eb.tags_response = [{"id": 6, "name": "reserve"}]  # no 'live'
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SKIPPED_EMPTY_LIVE
        assert "live" in result.error_message
        _assert_no_mutation(eb)

    async def test_empty_target_set_refused(self):
        eb = FakeEBClient()
        eb.target_senders = []  # no senders have the live tag
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SKIPPED_EMPTY_LIVE
        _assert_no_mutation(eb)

    async def test_target_below_min_size_refused(self):
        eb = FakeEBClient()
        eb.target_senders = [{"id": 10}]  # only 1
        result, eb = await _run(eb=eb, min_target_size=5)
        assert result.status == ReapplyStatus.SKIPPED_EMPTY_LIVE
        _assert_no_mutation(eb)

    async def test_oversized_removal_refused(self):
        # prior has 4, target has 1 — would remove 75% > 50% default
        eb = FakeEBClient()
        eb.target_senders = [{"id": 10}]
        eb.prior_senders_history = [
            [{"id": 10}, {"id": 91}, {"id": 92}, {"id": 93}],
            [{"id": 10}, {"id": 91}, {"id": 92}, {"id": 93}],  # would not change
        ]
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SKIPPED_OVERSIZED_REMOVAL
        assert "75.0%" in result.error_message
        _assert_no_mutation(eb)

    async def test_sammy_production_shape_trips_oversized_removal_guard(self):
        """Regression test for the L5 staging discovery on Sammy campaign #63.

        Real production state observed 2026-04-29:
          - 634 senders attached (across 43 paginated pages)
          - 22 senders tagged 'live' (zero overlap with currently-attached)
          - All 634 attached are 'Not connected'; all 22 live are 'Connected'

        With our oversized-removal guard at default 50%, this MUST be refused —
        we'd be removing 100% of attached senders, which is suspicious enough to
        require operator override.

        This test pins that behavior so future refactors can't regress it.
        """
        eb = FakeEBClient()
        # Simulate 634 prior senders (real Sammy #63 count)
        prior_senders = [{"id": 10000 + i} for i in range(634)]
        # 22 target (live-tagged) senders, completely disjoint from prior
        target_senders = [{"id": 20000 + i} for i in range(22)]

        eb.target_senders = target_senders
        eb.prior_senders_history = [prior_senders, prior_senders]  # verify call returns same

        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.SKIPPED_OVERSIZED_REMOVAL
        assert "100.0%" in result.error_message
        # The diff details must be captured in the result for operator review
        assert len(result.target_set) == 22
        assert len(result.prior_set) == 634
        assert len(result.attached_ids) == 22  # all 22 would be added
        assert len(result.removed_ids) == 634  # all 634 would be removed
        # Guard prevents mutation
        _assert_no_mutation(eb)

    async def test_sammy_production_shape_with_override_proceeds(self):
        """Operator override path: --max-removal-pct 100 lets the 634→22 swap proceed."""
        eb = FakeEBClient()
        prior_senders = [{"id": 10000 + i} for i in range(634)]
        target_senders = [{"id": 20000 + i} for i in range(22)]

        eb.target_senders = target_senders
        eb.prior_senders_history = [
            prior_senders,
            target_senders,  # verify: post-mutation set matches target
        ]

        result, _ = await _run(eb=eb, max_removal_pct=100.0)
        assert result.status == ReapplyStatus.SUCCEEDED
        assert len(result.attached_ids) == 22
        assert len(result.removed_ids) == 634
        assert result.verify_passed is True

    async def test_oversized_removal_override(self):
        eb = FakeEBClient()
        eb.target_senders = [{"id": 10}]
        eb.prior_senders_history = [
            [{"id": 10}, {"id": 91}, {"id": 92}, {"id": 93}],
            [{"id": 10}],  # final — matches target after removal
        ]
        result, _ = await _run(eb=eb, max_removal_pct=99.0)
        assert result.status == ReapplyStatus.SUCCEEDED


# =============================================================================
# Failure injection — every mutating step + invariant checks
# =============================================================================

class TestFailureInjection:
    async def test_get_campaign_failure(self):
        eb = FakeEBClient()
        eb.fail_at = "get_campaign"
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "get_campaign"
        _assert_no_mutation(eb)

    async def test_get_schedule_failure(self):
        eb = FakeEBClient()
        eb.fail_at = "get_campaign_schedule"
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "get_schedule"
        _assert_no_mutation(eb)

    async def test_resolve_tag_failure(self):
        eb = FakeEBClient()
        eb.fail_at = "resolve_tag_id"
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "resolve_tag"
        _assert_no_mutation(eb)

    async def test_set_fetch_failure(self):
        eb = FakeEBClient()
        eb.fail_at = "list_senders_with_tag"
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "fetch_sets"
        _assert_no_mutation(eb)

    async def test_pause_failure_no_resume_attempted(self):
        eb = FakeEBClient()
        eb.fail_at = "pause_campaign"
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "pause"
        # Pause failed → no campaign mutation occurred → no resume needed
        # Verify no further mutating calls happened after the failed pause
        assert "attach_senders" not in eb.methods_called()
        assert "remove_senders" not in eb.methods_called()

    async def test_pause_returns_non_paused_status(self):
        # EB returns 200 but status is still "Active" — defensive resume + bail
        eb = FakeEBClient()
        eb.pause_response = {"id": 1, "status": "Active"}
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "pause_verify"
        # Defensive resume should have been attempted
        assert "resume_campaign" in eb.methods_called()

    async def test_pause_verify_with_defensive_resume_also_failing(self):
        # EB returns 200 but status != Paused, AND the defensive resume call also fails.
        # This is a real silent-error case: campaign may genuinely be paused.
        # We must escalate to FAILED_LEFT_PAUSED so the operator sees it.
        eb = FakeEBClient()
        eb.pause_response = {"id": 1, "status": "Active"}  # triggers defensive path

        # Make resume_campaign fail (we don't need to keep the original)
        async def failing_resume(*args):
            eb.calls.append(("resume_campaign", args))
            raise EmailBisonAPIError(500, "resume failed in defensive path")
        eb.resume_campaign = failing_resume

        result, eb = await _run(eb=eb)

        # Critical: must NOT be FAILED_PRE_PAUSE (which implied "campaign untouched")
        assert result.status == ReapplyStatus.FAILED_LEFT_PAUSED, (
            f"silent-error escalation: defensive resume failure must surface as "
            f"FAILED_LEFT_PAUSED, got {result.status.value}"
        )
        assert result.operator_action_required is True
        # Error message must capture both the pause-verify problem AND the resume failure
        assert "expected 'paused'" in result.error_message
        assert "defensive resume also failed" in result.error_message
        assert "resume failed in defensive path" in result.error_message
        # No mutation should have happened
        assert "attach_senders" not in eb.methods_called()
        assert "remove_senders" not in eb.methods_called()

    async def test_attach_failure_resume_still_called(self):
        # CRITICAL INVARIANT: pause succeeded → resume MUST be called even on attach fail
        eb = FakeEBClient()
        eb.fail_at = "attach_senders"
        result, eb = await _run(eb=eb)
        # Status should reflect the attach failure
        assert result.error_step == "attach"
        # But resume MUST have been called (INV-1)
        _assert_resume_called_after_pause(eb)
        # remove should NOT have been attempted (attach failed first, fail-closed)
        assert "remove_senders" not in eb.methods_called()

    async def test_remove_failure_resume_still_called(self):
        eb = FakeEBClient()
        eb.fail_at = "remove_senders"
        result, eb = await _run(eb=eb)
        assert result.error_step == "remove"
        _assert_resume_called_after_pause(eb)
        # attach should have been called (it precedes remove)
        assert "attach_senders" in eb.methods_called()

    async def test_verify_fetch_failure_all_attempts_resume_still_called(self):
        # get_campaign_senders fails on EVERY verify call (call 2 onward).
        # The verify loop retries each, and only after all attempts throw
        # does it bail with verify_fetch. Resume must still happen.
        eb = FakeEBClient()
        original = eb.get_campaign_senders
        call_count = {"n": 0}

        async def flaky(campaign_id):
            call_count["n"] += 1
            if call_count["n"] >= 2:  # every verify attempt fails
                eb.calls.append(("get_campaign_senders", (campaign_id,)))
                raise EmailBisonAPIError(500, "verify fetch failed")
            return await original(campaign_id)

        eb.get_campaign_senders = flaky
        result, eb = await _run(eb=eb)
        assert result.error_step == "verify_fetch"
        assert result.status == ReapplyStatus.FAILED_POST_RESUME
        assert "after 4 attempts" in (result.error_message or "")
        _assert_resume_called_after_pause(eb)

    async def test_verify_fetch_transient_error_retries_and_recovers(self):
        # The 2026-05-14 SPUI bug: the async DELETE leaves EB's pagination
        # metadata transiently inconsistent, so the first verify fetch
        # raises (eb_client's consistency guard). The verify loop must
        # treat that like a mismatch — settle and retry — not bail.
        eb = FakeEBClient()
        original = eb.get_campaign_senders
        call_count = {"n": 0}

        async def flaky(campaign_id):
            call_count["n"] += 1
            # call 1 = compute prior; call 2 = verify attempt 1 (raises);
            # call 3 = verify attempt 2 (succeeds, matches target).
            if call_count["n"] == 2:
                eb.calls.append(("get_campaign_senders", (campaign_id,)))
                raise EmailBisonAPIError(
                    0, "pagination collected 87 senders but meta.total=95"
                )
            return await original(campaign_id)

        eb.get_campaign_senders = flaky
        result, eb = await _run(eb=eb)
        # Recovered: the retry after the transient error succeeded.
        assert result.status == ReapplyStatus.SUCCEEDED
        assert result.verify_passed is True
        _assert_resume_called_after_pause(eb)

    async def test_verify_mismatch_marks_failed_post_resume(self):
        # All mutations succeed but the final set doesn't match target
        eb = FakeEBClient()
        eb.prior_senders_history = [
            [{"id": 11}, {"id": 99}],
            [{"id": 11}, {"id": 12}],  # missing id=10 and id=99 didn't get removed
        ]
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_POST_RESUME
        assert result.verify_passed is False
        assert result.error_step == "verify"
        # Resume should have been attempted (INV-1)
        _assert_resume_called_after_pause(eb)
        # operator_action_required is False here — campaign is resumed, just diverged
        assert result.operator_action_required is False

    async def test_verify_settle_converges_on_retry(self):
        # EB's /remove-sender-emails is async ("Sender emails sent for deletion.
        # This may take a moment."). First verify fetch can show the pre-remove
        # state, second fetch shows post-remove. Reapply must retry, not fail.
        eb = FakeEBClient()
        eb.prior_senders_history = [
            # 1st call: compute prior (pre-mutation). prior={11,99}, target={10,11,12}.
            [{"id": 11}, {"id": 99}],
            # 2nd call: verify attempt 1 — still pre-remove (id=99 not yet purged).
            [{"id": 10}, {"id": 11}, {"id": 12}, {"id": 99}],
            # 3rd call: verify attempt 2 — converged.
            [{"id": 10}, {"id": 11}, {"id": 12}],
        ]
        sleeps: list[float] = []

        async def record_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        result, eb = await _run(eb=eb, sleep_func=record_sleep, verify_settle_seconds=0.5)
        assert result.status == ReapplyStatus.SUCCEEDED
        assert result.verify_passed is True
        # get_campaign_senders called: 1 prior + 2 verify = 3 total.
        assert eb.call_count("get_campaign_senders") == 3
        # Exactly one sleep between verify attempts.
        assert sleeps == [0.5]

    async def test_verify_settle_succeeds_first_try_no_sleep(self):
        # When mutations settle immediately, no sleep should be incurred.
        eb = FakeEBClient()
        # Default fake: prior={11,99}, target={10,11,12}; verify attempt 1 matches.
        sleeps: list[float] = []

        async def record_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        result, eb = await _run(eb=eb, sleep_func=record_sleep)
        assert result.status == ReapplyStatus.SUCCEEDED
        # Only 2 calls: 1 prior + 1 verify. No retry.
        assert eb.call_count("get_campaign_senders") == 2
        assert sleeps == []

    async def test_resume_failure_marks_failed_left_paused(self):
        # Mutations succeed, verify passes, but resume itself fails
        eb = FakeEBClient()
        eb.fail_at = "resume_campaign"
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_LEFT_PAUSED
        assert result.error_message and "resume failed" in result.error_message
        # operator_action_required must be True
        assert result.operator_action_required is True

    async def test_attach_fail_then_resume_fail_marks_left_paused(self):
        # Both attach AND resume fail — final state is FAILED_LEFT_PAUSED
        # because resume failure overrides attach failure (more critical)
        eb = FakeEBClient()
        # Make attach fail, then resume also fail
        attach_called = {"v": False}
        resume_called = {"v": False}

        async def fail_attach(*a, **kw):
            attach_called["v"] = True
            eb.calls.append(("attach_senders", a))
            raise EmailBisonAPIError(500, "attach failure")

        async def fail_resume(*a, **kw):
            resume_called["v"] = True
            eb.calls.append(("resume_campaign", a))
            raise EmailBisonAPIError(500, "resume failure")

        eb.attach_senders = fail_attach
        eb.resume_campaign = fail_resume
        result, eb = await _run(eb=eb)
        assert attach_called["v"]
        assert resume_called["v"]
        assert result.status == ReapplyStatus.FAILED_LEFT_PAUSED
        # error_message should mention both
        assert "attach failed" in result.error_message
        assert "resume failed" in result.error_message
        assert result.operator_action_required is True


# =============================================================================
# Schedule parsing edge cases
# =============================================================================

class TestSchedulePayloadParsing:
    async def test_missing_timezone_raises_parse_error(self):
        eb = FakeEBClient()
        bad = dict(SAMMY_SCHEDULE_RESPONSE)
        del bad["timezone"]
        eb.schedule_response = bad
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "parse_schedule"
        _assert_no_mutation(eb)

    async def test_invalid_timezone_raises_parse_error(self):
        eb = FakeEBClient()
        eb.schedule_response = {**SAMMY_SCHEDULE_RESPONSE, "timezone": "GMT+10"}  # not IANA
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "parse_schedule"
        _assert_no_mutation(eb)

    async def test_hh_mm_ss_time_format_accepted(self):
        eb = FakeEBClient()
        eb.schedule_response = {**SAMMY_SCHEDULE_RESPONSE, "start_time": "08:00:00", "end_time": "17:00:00"}
        result, _ = await _run(eb=eb)
        assert result.status == ReapplyStatus.SUCCEEDED

    async def test_unparseable_time_format_raises_parse_error(self):
        eb = FakeEBClient()
        eb.schedule_response = {**SAMMY_SCHEDULE_RESPONSE, "start_time": "8am"}
        result, eb = await _run(eb=eb)
        assert result.status == ReapplyStatus.FAILED_PRE_PAUSE
        assert result.error_step == "parse_schedule"
        assert "unrecognized time format" in result.error_message
        _assert_no_mutation(eb)

    async def test_default_now_utc_is_used_when_not_passed(self):
        # Cover the `now_utc = datetime.now(timezone.utc)` default branch.
        # We use --skip-time-check to avoid clock-dependent flakes.
        eb = FakeEBClient()
        result = await reapply_campaign(
            eb=eb,
            workspace_name="Charm",
            campaign_id=1,
            apply=True,
            skip_time_check=True,
            # Deliberately omit now_utc to exercise the default
        )
        assert result.status == ReapplyStatus.SUCCEEDED


# =============================================================================
# Cross-test invariant sweep
# =============================================================================

class TestInvariantSweep:
    """Run many failure permutations and assert global invariants hold."""

    @pytest.mark.parametrize("fail_at", [
        # Pre-pause failures: pause never happens, no resume expected. INV-1 holds vacuously.
        "get_campaign",
        "get_campaign_schedule",
        "resolve_tag_id",
        "list_senders_with_tag",
        # Post-pause failures: pause did happen, resume MUST follow.
        "attach_senders",
        "remove_senders",
        # NB: pause_campaign failure is a special case — covered by the dedicated
        # test_pause_failure_no_resume_attempted. Including it here would be wrong:
        # pause failure means no campaign state changed, so no resume is needed.
        # NB: get_campaign_senders failure (verify-fetch) handled separately above.
    ])
    async def test_inv1_resume_after_pause(self, fail_at):
        eb = FakeEBClient()
        eb.fail_at = fail_at
        await _run(eb=eb)
        _assert_resume_called_after_pause(eb)

    @pytest.mark.parametrize("fail_at", [
        "get_campaign", "get_campaign_schedule", "resolve_tag_id",
        "list_senders_with_tag", "pause_campaign",
        "attach_senders", "remove_senders", "resume_campaign",
    ])
    async def test_inv2_dry_run_no_mutation(self, fail_at):
        eb = FakeEBClient()
        eb.fail_at = fail_at
        await _run(eb=eb, apply=False)
        _assert_no_mutation(eb)

    async def test_inv3_succeeded_only_via_verify(self):
        # SUCCEEDED is set inside the try block only when verify_passed is True.
        # Sanity: across all failure injections, SUCCEEDED must imply verify_passed.
        for fail_at in [
            None, "attach_senders", "remove_senders", "resume_campaign",
        ]:
            eb = FakeEBClient()
            eb.fail_at = fail_at
            result, _ = await _run(eb=eb)
            if result.status == ReapplyStatus.SUCCEEDED:
                assert result.verify_passed is True
