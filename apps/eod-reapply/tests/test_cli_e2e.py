"""End-to-end CLI smoke tests.

Unlike test_cli.py (which mocks `_async_run` entirely), these tests:
  - mock asyncpg.connect to return a fake connection with a scripted row
  - mock the EB API via respx
  - run the actual `_async_run` body
  - assert exit codes, output, and that the request flow was correct

Catches wiring errors that the per-layer mocks couldn't see (e.g. wrong table
column name in db.py, EB client constructed with wrong base URL, etc.).
"""
from __future__ import annotations

import json
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import respx
from click.testing import CliRunner

from eod_reapply.cli import main

EB_BASE = "https://eb.example.com"
DB_URL = "postgresql://fake/test"
WORKSPACE_NAME = "Charm"
CAMPAIGN_ID = 42
API_KEY = "test-token"


def _resp(status: int = 200, body: dict | list | None = None) -> httpx.Response:
    return httpx.Response(status, json=body) if body is not None else httpx.Response(status)


def _schedule_response_inside_window():
    """Schedule for a campaign that's definitely past EOD when we run.
    Sammy-like: M-F 8am-5pm Sydney, but using --skip-time-check we don't care.
    """
    return {
        "data": {
            "id": 1, "type": "Generated",
            "monday": True, "tuesday": True, "wednesday": True,
            "thursday": True, "friday": True, "saturday": False, "sunday": False,
            "start_time": "08:00", "end_time": "17:00",
            "timezone": "Australia/Sydney",
        }
    }


class FakeAsyncpgConn:
    """Mimics asyncpg.Connection."""

    def __init__(self, row=None):
        self._row = row
        self.fetchrow_calls: list[tuple] = []
        self.closed = False

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self._row

    async def close(self):
        self.closed = True


def _patch_asyncpg(row_data=None):
    """Returns a context manager that patches asyncpg.connect to return our fake."""
    fake_conn = FakeAsyncpgConn(row=row_data)

    async def fake_connect(*args, **kwargs):
        return fake_conn

    return patch("eod_reapply.cli.asyncpg.connect", side_effect=fake_connect), fake_conn


@pytest.fixture
def workspace_row():
    return {
        "workspace_id": uuid4(),
        "workspace_name": WORKSPACE_NAME,
        "emailbison_workspace_id": "8",
        "api_key": API_KEY,
    }


# =============================================================================
# Workspace lookup failures (DB layer)
# =============================================================================

class TestWorkspaceLookup:
    def test_workspace_not_found_exits_2(self):
        """When fetch_workspace_context returns None, exit cleanly with 2."""
        runner = CliRunner()
        patcher, _ = _patch_asyncpg(row_data=None)
        with patcher:
            result = runner.invoke(main, [
                "reapply",
                "--workspace", "DOES_NOT_EXIST",
                "--campaign-id", "1",
                "--apply",
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])
        assert result.exit_code == 2
        assert "not found" in result.output

    def test_db_connection_failure_exits_via_handler(self, workspace_row):
        """If asyncpg.connect raises, the catch-all handler must kick in.

        This is the load-bearing 'no silent error' test — without the handler,
        Click would exit 1 with a traceback, masking our exit-code semantics.
        """
        runner = CliRunner()

        async def boom(*args, **kwargs):
            raise ConnectionError("could not connect to database")

        with patch("eod_reapply.cli.asyncpg.connect", side_effect=boom):
            result = runner.invoke(main, [
                "reapply",
                "--workspace", WORKSPACE_NAME,
                "--campaign-id", "1",
                "--apply",
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])
        # Exit code must come from our mapping (FAILED_PRE_PAUSE → 2)
        assert result.exit_code == 2
        # Output must surface the cause (no silent failure)
        assert "ConnectionError" in result.output
        assert "could not connect to database" in result.output


# =============================================================================
# Full happy-path e2e (DB → EB pipeline)
# =============================================================================

class TestEndToEndDryRun:
    @respx.mock
    def test_dry_run_full_pipeline_with_diff(self, workspace_row):
        """Full pipeline: DB lookup → EB calls → diff computed → no mutation → exit 1."""
        runner = CliRunner()
        patcher, fake_conn = _patch_asyncpg(row_data=workspace_row)

        # Mutating routes — register and assert NOT called at the end
        pause_route = respx.patch(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/pause").mock(
            return_value=_resp(200, {"data": {}})
        )
        attach_route = respx.post(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/attach-sender-emails").mock(
            return_value=_resp(200, {"success": True})
        )
        remove_route = respx.delete(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/remove-sender-emails").mock(
            return_value=_resp(200, {"success": True})
        )
        resume_route = respx.patch(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/resume").mock(
            return_value=_resp(200, {"data": {}})
        )

        # Read-only routes
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "status": "Active"}})
        )
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        # target = {10, 11}
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 10}, {"id": 11}], "meta": {"last_page": 1}})
        )
        # prior = {11, 99} → attach 10, remove 99 (50% removal — at the boundary, should pass)
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 11}, {"id": 99}]})
        )

        with patcher:
            result = runner.invoke(main, [
                "reapply",
                "--workspace", WORKSPACE_NAME,
                "--campaign-id", str(CAMPAIGN_ID),
                "--skip-time-check",
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])

        # Dry-run with changes → exit 1
        assert result.exit_code == 1, result.output

        # DB layer was hit
        assert len(fake_conn.fetchrow_calls) == 1
        assert fake_conn.closed

        # INV-2: dry-run made ZERO mutating calls
        assert not pause_route.called
        assert not attach_route.called
        assert not remove_route.called
        assert not resume_route.called

    @respx.mock
    def test_apply_full_pipeline_succeeded(self, workspace_row):
        """--apply: exercises pause → attach → remove → verify → resume against respx."""
        runner = CliRunner()
        patcher, fake_conn = _patch_asyncpg(row_data=workspace_row)

        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "status": "Active"}})
        )
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 10}, {"id": 11}], "meta": {"last_page": 1}})
        )

        # Two GETs to /campaigns/{id}/sender-emails — first is prior, second is verify
        prior_route = respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/sender-emails").mock(
            side_effect=[
                _resp(200, {"data": [{"id": 11}, {"id": 99}]}),  # prior
                _resp(200, {"data": [{"id": 10}, {"id": 11}]}),  # final (matches target)
            ]
        )
        pause_route = respx.patch(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/pause").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "status": "Paused"}})
        )
        attach_route = respx.post(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/attach-sender-emails").mock(
            return_value=_resp(200, {"success": True})
        )
        remove_route = respx.delete(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/remove-sender-emails").mock(
            return_value=_resp(200, {"success": True})
        )
        resume_route = respx.patch(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/resume").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "status": "Queued"}})
        )

        with patcher:
            result = runner.invoke(main, [
                "reapply",
                "--workspace", WORKSPACE_NAME,
                "--campaign-id", str(CAMPAIGN_ID),
                "--apply",
                "--skip-time-check",
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])

        assert result.exit_code == 0, result.output

        # Verify the expected calls happened
        assert pause_route.called
        assert attach_route.called
        assert remove_route.called
        assert resume_route.called
        assert prior_route.call_count == 2

        # Verify auth header on every EB request
        for route in [pause_route, attach_route, remove_route, resume_route]:
            assert route.calls[0].request.headers["authorization"] == f"Bearer {API_KEY}"

        # Verify attach body
        attach_body = json.loads(attach_route.calls[0].request.content)
        assert attach_body == {"sender_email_ids": [10]}

        # Verify remove body
        remove_body = json.loads(remove_route.calls[0].request.content)
        assert remove_body == {"sender_email_ids": [99]}

    @respx.mock
    def test_apply_with_resume_failure_exits_3(self, workspace_row):
        """Resume failure must propagate as exit 3 (operator action required)."""
        runner = CliRunner()
        patcher, _ = _patch_asyncpg(row_data=workspace_row)

        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "status": "Active"}})
        )
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        # target = {10, 11, 12}; prior = {11, 12, 99} — 1/3 = 33% removal, passes guard
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 10}, {"id": 11}, {"id": 12}], "meta": {"last_page": 1}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/sender-emails").mock(
            side_effect=[
                _resp(200, {"data": [{"id": 11}, {"id": 12}, {"id": 99}]}),     # prior
                _resp(200, {"data": [{"id": 10}, {"id": 11}, {"id": 12}]}),     # final — matches target
            ]
        )
        respx.patch(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/pause").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "status": "Paused"}})
        )
        respx.post(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/attach-sender-emails").mock(
            return_value=_resp(200, {"success": True})
        )
        respx.delete(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/remove-sender-emails").mock(
            return_value=_resp(200, {"success": True})
        )
        # Resume FAILS
        respx.patch(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/resume").mock(
            return_value=_resp(503, {"error": "service unavailable"})
        )

        with patcher:
            result = runner.invoke(main, [
                "reapply",
                "--workspace", WORKSPACE_NAME,
                "--campaign-id", str(CAMPAIGN_ID),
                "--apply",
                "--skip-time-check",
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])

        # Exit 3 == FAILED_LEFT_PAUSED → operator action required
        assert result.exit_code == 3, result.output
        assert "OPERATOR ACTION REQUIRED" in result.output

    @respx.mock
    def test_eb_unreachable_exits_2_via_handler(self, workspace_row):
        """If EB is unreachable, the orchestrator's get_campaign fails cleanly."""
        runner = CliRunner()
        patcher, _ = _patch_asyncpg(row_data=workspace_row)

        # Don't mock any EB calls — respx will raise on the first GET
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with patcher:
            result = runner.invoke(main, [
                "reapply",
                "--workspace", WORKSPACE_NAME,
                "--campaign-id", str(CAMPAIGN_ID),
                "--apply",
                "--skip-time-check",
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])
        # Should be a clean FAILED_PRE_PAUSE → exit 2 (NOT a traceback)
        assert result.exit_code == 2, result.output
