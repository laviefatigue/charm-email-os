"""L4 tests for cli — argument parsing, exit code mapping, output formatting.

We mock the async pipeline entirely so the CLI layer is exercised in isolation.
The actual orchestrator + EB client + DB interactions are covered by L1-L3.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from eod_reapply.cli import (
    exit_code_for,
    main,
    render_json,
    render_summary,
)
from eod_reapply.reapply import ReapplyResult, ReapplyStatus

# =============================================================================
# Exit code mapping (single source of truth)
# =============================================================================

class TestExitCodes:
    def test_succeeded_is_zero(self):
        assert exit_code_for(ReapplyStatus.SUCCEEDED) == 0

    def test_no_diff_is_zero(self):
        assert exit_code_for(ReapplyStatus.SKIPPED_NO_DIFF) == 0

    def test_not_active_is_zero(self):
        # No-op, not an error
        assert exit_code_for(ReapplyStatus.SKIPPED_NOT_ACTIVE) == 0

    def test_time_gate_is_zero(self):
        # No-op, not an error
        assert exit_code_for(ReapplyStatus.SKIPPED_TIME_GATE) == 0

    def test_dry_run_with_changes_is_one(self):
        # 1 == "would have changed; operator review required before --apply"
        assert exit_code_for(ReapplyStatus.SKIPPED_DRY_RUN) == 1

    def test_empty_live_is_two(self):
        assert exit_code_for(ReapplyStatus.SKIPPED_EMPTY_LIVE) == 2

    def test_oversized_removal_is_two(self):
        assert exit_code_for(ReapplyStatus.SKIPPED_OVERSIZED_REMOVAL) == 2

    def test_failed_pre_pause_is_two(self):
        assert exit_code_for(ReapplyStatus.FAILED_PRE_PAUSE) == 2

    def test_failed_post_resume_is_two(self):
        # Resume succeeded; just verification mismatch
        assert exit_code_for(ReapplyStatus.FAILED_POST_RESUME) == 2

    def test_failed_left_paused_is_three(self):
        # CRITICAL — operator action required
        assert exit_code_for(ReapplyStatus.FAILED_LEFT_PAUSED) == 3

    def test_every_status_has_an_exit_code(self):
        # Forces us to update the mapping when adding statuses
        for status in ReapplyStatus:
            exit_code_for(status)  # raises KeyError if missing


# =============================================================================
# Output rendering
# =============================================================================

def _make_result(**overrides):
    base = dict(
        status=ReapplyStatus.SUCCEEDED,
        campaign_id=42,
        workspace_name="Charm",
        is_dry_run=False,
        target_set=[10, 11],
        prior_set=[11, 99],
        attached_ids=[10],
        removed_ids=[99],
        final_set=[10, 11],
        verify_passed=True,
    )
    base.update(overrides)
    return ReapplyResult(**base)


class TestRenderSummary:
    def test_summary_contains_workspace_and_campaign(self):
        r = _make_result()
        out = render_summary(r)
        assert "Charm" in out
        assert "42" in out

    def test_summary_shows_diffs(self):
        r = _make_result()
        out = render_summary(r)
        assert "to attach" in out
        assert "[10]" in out
        assert "to remove" in out
        assert "[99]" in out

    def test_operator_action_banner_when_left_paused(self):
        r = _make_result(
            status=ReapplyStatus.FAILED_LEFT_PAUSED,
            verify_passed=None,
            error_message="resume failed",
            error_step="resume",
        )
        out = render_summary(r)
        assert "OPERATOR ACTION REQUIRED" in out

    def test_no_operator_banner_on_success(self):
        r = _make_result()
        out = render_summary(r)
        assert "OPERATOR ACTION REQUIRED" not in out

    def test_long_set_truncated(self):
        # Sets with > 10 elements should print '[...]' rather than the full list
        r = _make_result(target_set=list(range(50)))
        out = render_summary(r)
        assert "[...]" in out


class TestRenderJson:
    def test_json_is_valid(self):
        r = _make_result()
        parsed = json.loads(render_json(r))
        assert parsed["status"] == "succeeded"
        assert parsed["campaign_id"] == 42
        assert parsed["target_set"] == [10, 11]
        assert parsed["operator_action_required"] is False

    def test_status_is_string_not_enum(self):
        r = _make_result(status=ReapplyStatus.FAILED_LEFT_PAUSED, verify_passed=None)
        parsed = json.loads(render_json(r))
        assert parsed["status"] == "failed_left_paused"
        assert parsed["operator_action_required"] is True


# =============================================================================
# CLI integration (with mocked async pipeline)
# =============================================================================

class TestCliInvocation:
    """Tests run the click command via CliRunner with the async pipeline mocked."""

    def _runner_with_mock(self, mock_result: ReapplyResult):
        runner = CliRunner()
        async_mock = AsyncMock(return_value=mock_result)
        return runner, async_mock

    def test_required_args_enforced(self):
        runner = CliRunner()
        result = runner.invoke(main, ["reapply"])
        # click exits 2 on usage errors
        assert result.exit_code == 2
        assert "workspace" in result.output.lower() or "missing" in result.output.lower()

    def test_database_url_required(self):
        runner = CliRunner()
        # No DATABASE_URL set, no --database-url flag
        result = runner.invoke(main, [
            "reapply",
            "--workspace", "Charm",
            "--campaign-id", "42",
        ], env={"DATABASE_URL": ""})
        assert result.exit_code == 2
        assert "DATABASE_URL" in result.output or "database" in result.output.lower()

    def test_default_is_dry_run(self):
        runner, mock_async = self._runner_with_mock(_make_result(
            status=ReapplyStatus.SKIPPED_DRY_RUN, is_dry_run=True
        ))
        with patch("eod_reapply.cli._async_run", mock_async):
            result = runner.invoke(main, [
                "reapply",
                "--workspace", "Charm",
                "--campaign-id", "42",
                "--database-url", "postgres://fake",
            ])
        assert result.exit_code == 1  # dry-run with changes
        # The async function should have been called with apply_changes=False
        call_kwargs = mock_async.call_args.kwargs
        assert call_kwargs["apply_changes"] is False
        assert "DRY-RUN" in result.output

    def test_apply_flag_passes_through(self):
        runner, mock_async = self._runner_with_mock(_make_result(status=ReapplyStatus.SUCCEEDED))
        with patch("eod_reapply.cli._async_run", mock_async):
            result = runner.invoke(main, [
                "reapply",
                "--workspace", "Charm",
                "--campaign-id", "42",
                "--apply",
                "--database-url", "postgres://fake",
            ])
        assert result.exit_code == 0
        call_kwargs = mock_async.call_args.kwargs
        assert call_kwargs["apply_changes"] is True
        assert "APPLY" in result.output

    def test_skip_time_check_warning_printed(self):
        runner, mock_async = self._runner_with_mock(_make_result(status=ReapplyStatus.SUCCEEDED))
        with patch("eod_reapply.cli._async_run", mock_async):
            result = runner.invoke(main, [
                "reapply",
                "--workspace", "Charm",
                "--campaign-id", "42",
                "--apply",
                "--skip-time-check",
                "--database-url", "postgres://fake",
            ])
        assert "WARNING" in result.output
        assert "skip-time-check" in result.output

    def test_exit_code_3_on_failed_left_paused(self):
        runner, mock_async = self._runner_with_mock(_make_result(
            status=ReapplyStatus.FAILED_LEFT_PAUSED,
            error_message="resume failed",
            error_step="resume",
            verify_passed=None,
        ))
        with patch("eod_reapply.cli._async_run", mock_async):
            result = runner.invoke(main, [
                "reapply",
                "--workspace", "Charm",
                "--campaign-id", "42",
                "--apply",
                "--database-url", "postgres://fake",
            ])
        assert result.exit_code == 3
        assert "OPERATOR ACTION REQUIRED" in result.output

    def test_exit_code_2_on_failed_pre_pause(self):
        runner, mock_async = self._runner_with_mock(_make_result(
            status=ReapplyStatus.FAILED_PRE_PAUSE,
            error_step="get_campaign",
            error_message="404 not found",
            attached_ids=[], removed_ids=[],
            verify_passed=None,
        ))
        with patch("eod_reapply.cli._async_run", mock_async):
            result = runner.invoke(main, [
                "reapply",
                "--workspace", "Charm",
                "--campaign-id", "42",
                "--apply",
                "--database-url", "postgres://fake",
            ])
        assert result.exit_code == 2

    def test_buffer_and_min_target_passthrough(self):
        runner, mock_async = self._runner_with_mock(_make_result(status=ReapplyStatus.SUCCEEDED))
        with patch("eod_reapply.cli._async_run", mock_async):
            runner.invoke(main, [
                "reapply",
                "--workspace", "Charm",
                "--campaign-id", "42",
                "--apply",
                "--buffer-minutes", "120",
                "--min-target-size", "5",
                "--max-removal-pct", "75",
                "--database-url", "postgres://fake",
            ])
        kwargs = mock_async.call_args.kwargs
        assert kwargs["buffer_minutes"] == 120
        assert kwargs["min_target_size"] == 5
        assert kwargs["max_removal_pct"] == 75.0

    def test_json_only_flag_omits_summary(self):
        runner, mock_async = self._runner_with_mock(_make_result(status=ReapplyStatus.SUCCEEDED))
        with patch("eod_reapply.cli._async_run", mock_async):
            result = runner.invoke(main, [
                "reapply",
                "--workspace", "Charm",
                "--campaign-id", "42",
                "--apply",
                "--json-only",
                "--database-url", "postgres://fake",
            ])
        # Output should be parseable as JSON (after stripping mode banner from stderr)
        # CliRunner combines stdout+stderr by default; check the stdout contains valid JSON
        # The JSON block should be the entire stdout when --json-only
        # Mode banners go to stderr (err=True in click.echo), but CliRunner captures them
        # mixed by default. Filter for the JSON block.
        json_block = result.output.strip().split("\n")
        # Find a line starting with '{'
        json_start = next((i for i, line in enumerate(json_block) if line.strip().startswith("{")), None)
        assert json_start is not None
        json_text = "\n".join(json_block[json_start:])
        # Trim trailing non-json lines if any
        # Find the last '}' line
        json_end = max((i for i, line in enumerate(json_block) if line.strip() == "}"), default=len(json_block) - 1)
        json_text = "\n".join(json_block[json_start:json_end + 1])
        parsed = json.loads(json_text)
        assert parsed["status"] == "succeeded"
        assert parsed["campaign_id"] == 42
