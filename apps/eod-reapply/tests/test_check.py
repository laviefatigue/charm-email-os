"""Tests for check.run_checks — pre-flight diagnostic.

Mocks asyncpg + respx for the EB calls. Verifies the full check sequence,
early-exit on critical failure, soft-fail on warnings, and report shape.
"""
from __future__ import annotations

import json
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import respx
from click.testing import CliRunner

from eod_reapply.check import (
    CheckReport,
    CheckStatus,
    exit_code_for_check,
    render_report_text,
    report_to_dict,
    run_checks,
)
from eod_reapply.cli import main

EB_BASE = "https://eb.example.com"
DB_URL = "postgresql://fake/test"
WORKSPACE_NAME = "Charm"
CAMPAIGN_ID = 42
API_KEY = "test-token"


def _resp(status: int = 200, body=None) -> httpx.Response:
    return httpx.Response(status, json=body) if body is not None else httpx.Response(status)


class FakeAsyncpgConn:
    def __init__(self, row=None, raise_on_fetchrow=None):
        self._row = row
        self._raise = raise_on_fetchrow
        self.fetchrow_calls: list[tuple] = []
        self.closed = False

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        if self._raise is not None:
            raise self._raise
        return self._row

    async def close(self):
        self.closed = True


def _patch_asyncpg(row_data=None, connect_raises=None, fetchrow_raises=None):
    fake_conn = FakeAsyncpgConn(row=row_data, raise_on_fetchrow=fetchrow_raises)
    if connect_raises is not None:
        async def fake_connect(*args, **kwargs):
            raise connect_raises
    else:
        async def fake_connect(*args, **kwargs):
            return fake_conn
    return patch("eod_reapply.check.asyncpg.connect", side_effect=fake_connect), fake_conn


@pytest.fixture
def workspace_row():
    return {
        "workspace_id": uuid4(),
        "workspace_name": WORKSPACE_NAME,
        "emailbison_workspace_id": "8",
        "api_key": API_KEY,
    }


# =============================================================================
# CheckReport behaviour
# =============================================================================

class TestCheckReport:
    def test_overall_status_all_ok(self):
        r = CheckReport("Charm", None)
        r.add("a", CheckStatus.OK)
        r.add("b", CheckStatus.OK)
        assert r.overall_status == CheckStatus.OK

    def test_overall_status_warn_dominates_ok(self):
        r = CheckReport("Charm", None)
        r.add("a", CheckStatus.OK)
        r.add("b", CheckStatus.WARN)
        assert r.overall_status == CheckStatus.WARN

    def test_overall_status_fail_dominates_warn(self):
        r = CheckReport("Charm", None)
        r.add("a", CheckStatus.WARN)
        r.add("b", CheckStatus.FAIL)
        assert r.overall_status == CheckStatus.FAIL

    def test_skip_does_not_count(self):
        r = CheckReport("Charm", None)
        r.add("a", CheckStatus.OK)
        r.add("b", CheckStatus.SKIP)
        assert r.overall_status == CheckStatus.OK

    def test_exit_code_mapping(self):
        ok = CheckReport("Charm", None)
        ok.add("a", CheckStatus.OK)
        warn = CheckReport("Charm", None)
        warn.add("a", CheckStatus.WARN)
        fail = CheckReport("Charm", None)
        fail.add("a", CheckStatus.FAIL)
        assert exit_code_for_check(ok) == 0
        assert exit_code_for_check(warn) == 1
        assert exit_code_for_check(fail) == 2


# =============================================================================
# Critical-failure early exits
# =============================================================================

class TestEarlyExits:
    async def test_db_connect_failure_exits_immediately(self):
        patcher, _ = _patch_asyncpg(connect_raises=ConnectionError("boom"))
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME,
            )
        names = [r.name for r in report.results]
        assert names == ["db_connection"]
        assert report.results[0].status == CheckStatus.FAIL
        assert "ConnectionError" in report.results[0].detail

    async def test_workspace_lookup_missing_exits(self):
        patcher, _ = _patch_asyncpg(row_data=None)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name="DOES_NOT_EXIST",
            )
        names = [r.name for r in report.results]
        assert names == ["db_connection", "workspace_lookup"]
        assert report.results[1].status == CheckStatus.FAIL

    @respx.mock
    async def test_eb_auth_failure_exits(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(return_value=_resp(401, {"error": "unauthenticated"}))
        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME,
            )
        names = [r.name for r in report.results]
        assert names == ["db_connection", "workspace_lookup", "eb_auth"]
        assert report.results[-1].status == CheckStatus.FAIL


# =============================================================================
# Workspace-only checks (no campaign_id)
# =============================================================================

class TestWorkspaceOnlyChecks:
    @respx.mock
    async def test_all_ok_workspace_only(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 10}, {"id": 11}], "meta": {"last_page": 1}})
        )
        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME,
            )

        # The workspace-level checks ran and passed
        statuses = {r.name: r.status for r in report.results}
        assert statuses["db_connection"] == CheckStatus.OK
        assert statuses["workspace_lookup"] == CheckStatus.OK
        assert statuses["eb_auth"] == CheckStatus.OK
        assert statuses["live_tag_resolves"] == CheckStatus.OK
        assert statuses["live_tag_set_size"] == CheckStatus.OK

        # Campaign-level checks were SKIPped
        for name in ("campaign_exists", "campaign_active", "schedule_fetches",
                     "schedule_parses", "campaign_senders_fetches", "expected_diff"):
            assert statuses[name] == CheckStatus.SKIP

        assert report.overall_status == CheckStatus.OK

    @respx.mock
    async def test_live_tag_missing_fails(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 6, "name": "reserve"}]})
        )
        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME,
            )
        statuses = {r.name: r.status for r in report.results}
        assert statuses["live_tag_resolves"] == CheckStatus.FAIL
        assert report.overall_status == CheckStatus.FAIL

    @respx.mock
    async def test_live_tag_set_empty_fails(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [], "meta": {"last_page": 1}})
        )
        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME,
            )
        statuses = {r.name: r.status for r in report.results}
        assert statuses["live_tag_set_size"] == CheckStatus.FAIL

    @respx.mock
    async def test_live_tag_set_below_min_warns(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}], "meta": {"last_page": 1}})
        )
        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME,
                min_target_size=5,
            )
        statuses = {r.name: r.status for r in report.results}
        assert statuses["live_tag_set_size"] == CheckStatus.WARN
        assert report.overall_status == CheckStatus.WARN


# =============================================================================
# Campaign-level checks
# =============================================================================

class TestCampaignChecks:
    @respx.mock
    async def test_full_happy_path_with_diff(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 10}, {"id": 11}, {"id": 12}], "meta": {"last_page": 1}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "name": "TestCamp", "status": "Active"}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/schedule").mock(
            return_value=_resp(200, {"data": {
                "monday": True, "tuesday": True, "wednesday": True, "thursday": True,
                "friday": True, "saturday": False, "sunday": False,
                "start_time": "08:00", "end_time": "17:00", "timezone": "Australia/Sydney",
            }})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 11}, {"id": 99}]})
        )

        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME, campaign_id=CAMPAIGN_ID,
            )

        statuses = {r.name: r.status for r in report.results}
        assert statuses["campaign_exists"] == CheckStatus.OK
        assert statuses["campaign_active"] == CheckStatus.OK
        assert statuses["schedule_fetches"] == CheckStatus.OK
        assert statuses["schedule_parses"] == CheckStatus.OK
        assert statuses["campaign_senders_fetches"] == CheckStatus.OK
        assert statuses["expected_diff"] == CheckStatus.OK

        # Diff detail should mention attach + remove counts
        diff_detail = next(r.detail for r in report.results if r.name == "expected_diff")
        assert "attach 2" in diff_detail
        assert "remove 1" in diff_detail

    @respx.mock
    async def test_campaign_paused_warns(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}], "meta": {"last_page": 1}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "name": "Paused", "status": "Paused"}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/schedule").mock(
            return_value=_resp(200, {"data": {
                "monday": True, "tuesday": True, "wednesday": True, "thursday": True,
                "friday": True, "saturday": False, "sunday": False,
                "start_time": "08:00", "end_time": "17:00", "timezone": "Australia/Sydney",
            }})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/sender-emails").mock(
            return_value=_resp(200, {"data": []})
        )

        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME, campaign_id=CAMPAIGN_ID,
            )
        statuses = {r.name: r.status for r in report.results}
        assert statuses["campaign_active"] == CheckStatus.WARN
        # All other campaign checks ran (campaign_active is WARN, not FAIL — non-blocking)
        assert statuses["schedule_fetches"] == CheckStatus.OK

    @respx.mock
    async def test_campaign_not_found_fails(self, workspace_row):
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}], "meta": {"last_page": 1}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            return_value=_resp(404, {"error": "not found"})
        )

        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME, campaign_id=CAMPAIGN_ID,
            )
        statuses = {r.name: r.status for r in report.results}
        assert statuses["campaign_exists"] == CheckStatus.FAIL
        # Subsequent checks weren't run (early exit)
        assert "schedule_fetches" not in statuses

    @respx.mock
    async def test_no_diff_path(self, workspace_row):
        # target == prior → no_diff
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}, {"id": 2}], "meta": {"last_page": 1}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}").mock(
            return_value=_resp(200, {"data": {"id": CAMPAIGN_ID, "status": "Active"}})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/schedule").mock(
            return_value=_resp(200, {"data": {
                "monday": True, "tuesday": True, "wednesday": True, "thursday": True,
                "friday": True, "saturday": False, "sunday": False,
                "start_time": "08:00", "end_time": "17:00", "timezone": "America/New_York",
            }})
        )
        respx.get(f"{EB_BASE}/api/campaigns/{CAMPAIGN_ID}/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}, {"id": 2}]})
        )

        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            report = await run_checks(
                database_url=DB_URL, eb_base_url=EB_BASE,
                workspace_name=WORKSPACE_NAME, campaign_id=CAMPAIGN_ID,
            )
        diff = next(r for r in report.results if r.name == "expected_diff")
        assert diff.status == CheckStatus.OK
        assert "no diff" in diff.detail.lower()


# =============================================================================
# Render helpers
# =============================================================================

class TestRender:
    def test_render_text_contains_workspace_name(self):
        r = CheckReport("Sammy", 42)
        r.add("test", CheckStatus.OK, "all good")
        out = render_report_text(r)
        assert "Sammy" in out
        assert "42" in out
        assert "[ OK  ]" in out

    def test_render_text_shows_failures(self):
        r = CheckReport("Sammy", None)
        r.add("test", CheckStatus.FAIL, "broken")
        out = render_report_text(r)
        assert "[FAIL ]" in out
        assert "broken" in out
        assert "OVERALL: FAIL" in out

    def test_report_to_dict_round_trips(self):
        r = CheckReport("Sammy", 42)
        r.add("a", CheckStatus.OK, "x")
        r.add("b", CheckStatus.WARN, "y")
        d = report_to_dict(r)
        assert d["workspace_name"] == "Sammy"
        assert d["campaign_id"] == 42
        assert d["overall_status"] == "warn"
        assert len(d["checks"]) == 2
        assert d["checks"][0] == {"name": "a", "status": "ok", "detail": "x"}
        # Must be JSON-serializable
        json.dumps(d)


# =============================================================================
# CLI integration
# =============================================================================

class TestCheckCli:
    @respx.mock
    def test_check_cli_invocation_exit_0(self, workspace_row):
        runner = CliRunner()
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}], "meta": {"last_page": 1}})
        )

        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            result = runner.invoke(main, [
                "check",
                "--workspace", WORKSPACE_NAME,
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])
        assert result.exit_code == 0, result.output
        assert "PRE-FLIGHT CHECK" in result.output
        assert "OVERALL: OK" in result.output

    def test_check_cli_db_failure_exits_2(self):
        runner = CliRunner()
        patcher, _ = _patch_asyncpg(connect_raises=ConnectionError("boom"))
        with patcher:
            result = runner.invoke(main, [
                "check",
                "--workspace", WORKSPACE_NAME,
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
            ])
        assert result.exit_code == 2
        assert "FAIL" in result.output

    def test_check_cli_requires_workspace(self):
        runner = CliRunner()
        result = runner.invoke(main, ["check"])
        assert result.exit_code == 2
        assert "workspace" in result.output.lower() or "missing" in result.output.lower()

    def test_check_cli_requires_database_url(self):
        runner = CliRunner()
        result = runner.invoke(main, [
            "check",
            "--workspace", WORKSPACE_NAME,
        ], env={"DATABASE_URL": ""})
        assert result.exit_code == 2

    @respx.mock
    def test_check_cli_json_only_output(self, workspace_row):
        runner = CliRunner()
        respx.get(f"{EB_BASE}/api/tags").mock(
            return_value=_resp(200, {"data": [{"id": 5, "name": "live"}]})
        )
        respx.get(f"{EB_BASE}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}], "meta": {"last_page": 1}})
        )

        patcher, _ = _patch_asyncpg(row_data=workspace_row)
        with patcher:
            result = runner.invoke(main, [
                "check",
                "--workspace", WORKSPACE_NAME,
                "--database-url", DB_URL,
                "--eb-base-url", EB_BASE,
                "--json-only",
            ])
        assert result.exit_code == 0
        # Must contain valid JSON. Find the first '{' line and parse from there.
        lines = result.output.strip().split("\n")
        json_start = next(i for i, line in enumerate(lines) if line.strip().startswith("{"))
        parsed = json.loads("\n".join(lines[json_start:]))
        assert parsed["overall_status"] == "ok"
        assert parsed["workspace_name"] == WORKSPACE_NAME
