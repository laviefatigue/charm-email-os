"""L2 tests for eb_client.EBClient — mocked httpx via respx.

Limitations of this layer (called out in the L1 review):
  - These tests prove our client does what we think it should. They DO NOT
    prove EB's actual API behavior matches our mocks. The L5 staging gate is
    the only place that proves contract compatibility.
  - Mocked tests with frozen request/response shapes will pass even if EB
    silently changes a field name or pagination key. That's why mocks below
    are conservative — they mirror the documented OpenAPI shapes verbatim
    where possible.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx

from eod_reapply.eb_client import EBClient, EmailBisonAPIError

BASE_URL = "https://spellcast.example.com"
API_KEY = "test-token-deadbeef"


# ---------- Fixtures / helpers ----------

@pytest.fixture
def client_factory():
    """Returns a coroutine that yields an entered EBClient."""
    def _factory(base_url: str = BASE_URL, api_key: str = API_KEY, timeout_seconds: float = 5.0):
        return EBClient(base_url=base_url, api_key=api_key, timeout_seconds=timeout_seconds)
    return _factory


def _resp(status: int = 200, body: dict | list | None = None) -> httpx.Response:
    if body is None:
        return httpx.Response(status)
    return httpx.Response(status, json=body)


# =============================================================================
# Construction
# =============================================================================

class TestConstruction:
    def test_empty_base_url_raises(self):
        with pytest.raises(ValueError, match="base_url"):
            EBClient(base_url="", api_key=API_KEY)

    def test_empty_api_key_raises(self):
        with pytest.raises(ValueError, match="api_key"):
            EBClient(base_url=BASE_URL, api_key="")

    def test_trailing_slash_stripped(self):
        c = EBClient(base_url="https://x.example/", api_key="k")
        assert c.base_url == "https://x.example"

    def test_multiple_trailing_slashes_stripped(self):
        c = EBClient(base_url="https://x.example///", api_key="k")
        assert c.base_url == "https://x.example"

    async def test_must_be_used_as_context_manager(self, client_factory):
        c = client_factory()
        with pytest.raises(RuntimeError, match="async context manager"):
            await c.get_campaign(1)


# =============================================================================
# Auth header on every request
# =============================================================================

class TestAuthHeader:
    @respx.mock
    async def test_auth_header_on_get(self, client_factory):
        route = respx.get(f"{BASE_URL}/api/campaigns/1").mock(return_value=_resp(200, {"data": {"id": 1}}))
        async with client_factory() as c:
            await c.get_campaign(1)
        assert route.called
        assert route.calls[0].request.headers["authorization"] == f"Bearer {API_KEY}"

    @respx.mock
    async def test_auth_header_on_patch(self, client_factory):
        route = respx.patch(f"{BASE_URL}/api/campaigns/1/pause").mock(return_value=_resp(200, {"data": {}}))
        async with client_factory() as c:
            await c.pause_campaign(1)
        assert route.calls[0].request.headers["authorization"] == f"Bearer {API_KEY}"

    @respx.mock
    async def test_auth_header_on_post(self, client_factory):
        route = respx.post(f"{BASE_URL}/api/campaigns/1/attach-sender-emails").mock(return_value=_resp(200, {}))
        async with client_factory() as c:
            await c.attach_senders(1, [10])
        assert route.calls[0].request.headers["authorization"] == f"Bearer {API_KEY}"

    @respx.mock
    async def test_auth_header_on_delete(self, client_factory):
        route = respx.delete(f"{BASE_URL}/api/campaigns/1/remove-sender-emails").mock(return_value=_resp(200, {}))
        async with client_factory() as c:
            await c.remove_senders(1, [10])
        assert route.calls[0].request.headers["authorization"] == f"Bearer {API_KEY}"


# =============================================================================
# Campaigns
# =============================================================================

class TestGetCampaign:
    @respx.mock
    async def test_returns_unwrapped_data(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/123").mock(
            return_value=_resp(200, {"data": {"id": 123, "name": "Test", "status": "Active"}})
        )
        async with client_factory() as c:
            result = await c.get_campaign(123)
        assert result == {"id": 123, "name": "Test", "status": "Active"}

    @respx.mock
    async def test_404_raises(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/999").mock(return_value=_resp(404, {"error": "not found"}))
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.get_campaign(999)
        assert exc.value.status_code == 404

    @respx.mock
    async def test_401_raises_distinctly(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/1").mock(return_value=_resp(401, {"error": "unauthorized"}))
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.get_campaign(1)
        assert exc.value.status_code == 401

    @respx.mock
    async def test_500_raises(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/1").mock(return_value=_resp(500, {"error": "boom"}))
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.get_campaign(1)
        assert exc.value.status_code == 500
        assert exc.value.response_body == {"error": "boom"}

    @respx.mock
    async def test_text_body_on_error_captured(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/1").mock(
            return_value=httpx.Response(400, text="<html>bad gateway</html>")
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.get_campaign(1)
        assert exc.value.status_code == 400
        assert "<html>" in exc.value.response_body


class TestGetCampaignSchedule:
    @respx.mock
    async def test_returns_schedule_object(self, client_factory):
        # Mirrors the OpenAPI example for viewCampaignSchedule
        body = {
            "data": {
                "id": 1,
                "type": "Generated",
                "monday": True, "tuesday": True, "wednesday": True,
                "thursday": True, "friday": True, "saturday": False, "sunday": False,
                "start_time": "08:00", "end_time": "17:00",
                "timezone": "Australia/Sydney",
                "created_at": "2026-04-14T16:59:21.000000Z",
                "updated_at": "2026-04-14T16:59:21.000000Z",
            }
        }
        respx.get(f"{BASE_URL}/api/campaigns/42/schedule").mock(return_value=_resp(200, body))
        async with client_factory() as c:
            result = await c.get_campaign_schedule(42)
        assert result["timezone"] == "Australia/Sydney"
        assert result["start_time"] == "08:00"
        assert result["monday"] is True
        assert result["saturday"] is False


class TestPauseResume:
    @respx.mock
    async def test_pause_returns_data(self, client_factory):
        respx.patch(f"{BASE_URL}/api/campaigns/1/pause").mock(
            return_value=_resp(200, {"data": {"id": 1, "status": "Paused"}})
        )
        async with client_factory() as c:
            result = await c.pause_campaign(1)
        assert result["status"] == "Paused"

    @respx.mock
    async def test_pause_404_raises(self, client_factory):
        respx.patch(f"{BASE_URL}/api/campaigns/1/pause").mock(return_value=_resp(404, {"error": "not found"}))
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.pause_campaign(1)
        assert exc.value.status_code == 404

    @respx.mock
    async def test_resume_returns_data(self, client_factory):
        respx.patch(f"{BASE_URL}/api/campaigns/1/resume").mock(
            return_value=_resp(200, {"data": {"id": 1, "status": "Queued"}})
        )
        async with client_factory() as c:
            result = await c.resume_campaign(1)
        assert result["status"] == "Queued"


class TestGetCampaignSenders:
    @respx.mock
    async def test_returns_list_single_page_with_meta(self, client_factory):
        # Mirrors actual production response shape (Laravel paginated wrapper)
        body = {
            "data": [{"id": 1, "email": "a@example.com"}, {"id": 2, "email": "b@example.com"}],
            "meta": {"current_page": 1, "last_page": 1, "per_page": 15, "total": 2},
        }
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(return_value=_resp(200, body))
        async with client_factory() as c:
            result = await c.get_campaign_senders(9)
        assert len(result) == 2
        assert result[0]["id"] == 1

    @respx.mock
    async def test_paginates_through_multiple_pages(self, client_factory):
        # Real-world regression: Sammy campaign #63 has 634 senders across 43 pages.
        # Without pagination, we'd only see page 1 — leading to wildly wrong diffs.
        # Simulate 3 pages of 5 senders each.
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            side_effect=[
                _resp(200, {
                    "data": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}],
                    "meta": {"current_page": 1, "last_page": 3, "per_page": 5, "total": 13},
                }),
                _resp(200, {
                    "data": [{"id": 6}, {"id": 7}, {"id": 8}, {"id": 9}, {"id": 10}],
                    "meta": {"current_page": 2, "last_page": 3, "per_page": 5, "total": 13},
                }),
                _resp(200, {
                    "data": [{"id": 11}, {"id": 12}, {"id": 13}],
                    "meta": {"current_page": 3, "last_page": 3, "per_page": 5, "total": 13},
                }),
            ]
        )
        async with client_factory() as c:
            result = await c.get_campaign_senders(9)
        assert [s["id"] for s in result] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]

    @respx.mock
    async def test_bare_list_response_terminates(self, client_factory):
        # If EB ever returns a bare list (older endpoint shape), single-page semantics
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            return_value=_resp(200, [{"id": 1}, {"id": 2}])
        )
        async with client_factory() as c:
            result = await c.get_campaign_senders(9)
        assert len(result) == 2

    @respx.mock
    async def test_missing_meta_terminates_after_one_page(self, client_factory):
        # Defense: don't loop forever if meta is missing
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}]})
        )
        async with client_factory() as c:
            result = await c.get_campaign_senders(9)
        assert len(result) == 1

    @respx.mock
    async def test_empty_returns_empty_list(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            return_value=_resp(200, {"data": [], "meta": {"last_page": 1, "current_page": 1, "total": 0}})
        )
        async with client_factory() as c:
            result = await c.get_campaign_senders(9)
        assert result == []

    @respx.mock
    async def test_unexpected_data_shape_raises(self, client_factory):
        # Defensive: if EB ever returns an object instead of a list under data, fail loud
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            return_value=_resp(200, {"data": {"unexpected": "shape"}})
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="Expected list"):
                await c.get_campaign_senders(9)

    @respx.mock
    async def test_unexpected_top_level_shape_raises(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            return_value=httpx.Response(200, json="not-a-dict-or-list")
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="Unexpected campaign senders response shape"):
                await c.get_campaign_senders(9)

    @respx.mock
    async def test_pagination_safety_limit_breach_raises(self, client_factory, monkeypatch):
        from eod_reapply import eb_client as eb_client_mod
        monkeypatch.setattr(eb_client_mod, "_PAGINATION_SAFETY_LIMIT", 3)
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            return_value=_resp(200, {
                "data": [{"id": 1}],
                "meta": {"current_page": 1, "last_page": 99999, "per_page": 1, "total": 99999},
            })
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="safety limit"):
                await c.get_campaign_senders(9)

    @respx.mock
    async def test_total_mismatch_raises(self, client_factory):
        # Server says total=20 but we only collected 10 across the pages — fail loud
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            side_effect=[
                _resp(200, {
                    "data": [{"id": i} for i in range(1, 6)],
                    "meta": {"current_page": 1, "last_page": 2, "per_page": 5, "total": 20},
                }),
                _resp(200, {
                    "data": [{"id": i} for i in range(6, 11)],
                    "meta": {"current_page": 2, "last_page": 2, "per_page": 5, "total": 20},
                }),
            ]
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match=r"collected 10 senders but meta\.total=20"):
                await c.get_campaign_senders(9)

    @respx.mock
    async def test_shape_changes_mid_pagination_raises(self, client_factory):
        # Page 1 paginated; page 2 returns 204 (eventual consistency / server hiccup)
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            side_effect=[
                _resp(200, {
                    "data": [{"id": 1}, {"id": 2}],
                    "meta": {"current_page": 1, "last_page": 2, "per_page": 2, "total": 4},
                }),
                httpx.Response(204),  # empty body mid-pagination
            ]
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="silent truncation"):
                await c.get_campaign_senders(9)

    @respx.mock
    async def test_meta_lost_mid_pagination_raises(self, client_factory):
        # Page 1 has meta; page 2 mysteriously doesn't
        respx.get(f"{BASE_URL}/api/campaigns/9/sender-emails").mock(
            side_effect=[
                _resp(200, {
                    "data": [{"id": 1}, {"id": 2}],
                    "meta": {"current_page": 1, "last_page": 2, "per_page": 2, "total": 4},
                }),
                _resp(200, {"data": [{"id": 3}, {"id": 4}]}),  # no meta
            ]
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="missing meta.last_page but earlier pages had it"):
                await c.get_campaign_senders(9)


class TestAttachSenders:
    @respx.mock
    async def test_attach_sends_correct_body(self, client_factory):
        route = respx.post(f"{BASE_URL}/api/campaigns/5/attach-sender-emails").mock(
            return_value=_resp(200, {"success": True, "message": "ok"})
        )
        async with client_factory() as c:
            await c.attach_senders(5, [10, 11, 12])
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body == {"sender_email_ids": [10, 11, 12]}

    async def test_empty_list_raises_without_http_call(self, client_factory):
        async with client_factory() as c:
            with pytest.raises(ValueError, match="must not be empty"):
                await c.attach_senders(5, [])

    @respx.mock
    async def test_403_raises(self, client_factory):
        respx.post(f"{BASE_URL}/api/campaigns/5/attach-sender-emails").mock(
            return_value=_resp(403, {"error": "forbidden"})
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.attach_senders(5, [10])
        assert exc.value.status_code == 403


class TestRemoveSenders:
    @respx.mock
    async def test_remove_uses_delete_with_body(self, client_factory):
        route = respx.delete(f"{BASE_URL}/api/campaigns/5/remove-sender-emails").mock(
            return_value=_resp(200, {"success": True})
        )
        async with client_factory() as c:
            await c.remove_senders(5, [10, 11])
        assert route.called
        # DELETE with JSON body — the request must carry the body
        body = json.loads(route.calls[0].request.content)
        assert body == {"sender_email_ids": [10, 11]}
        assert route.calls[0].request.method == "DELETE"

    async def test_empty_list_raises_without_http_call(self, client_factory):
        async with client_factory() as c:
            with pytest.raises(ValueError, match="must not be empty"):
                await c.remove_senders(5, [])


# =============================================================================
# Sender emails (paginated, tag-filtered)
# =============================================================================

class TestListSendersWithTag:
    @respx.mock
    async def test_single_page_with_meta(self, client_factory):
        body = {
            "data": [{"id": 1}, {"id": 2}, {"id": 3}],
            "meta": {"last_page": 1, "current_page": 1},
        }
        route = respx.get(f"{BASE_URL}/api/sender-emails").mock(return_value=_resp(200, body))
        async with client_factory() as c:
            result = await c.list_senders_with_tag(7)
        assert len(result) == 3
        assert route.call_count == 1
        # tag_id query param check
        url = str(route.calls[0].request.url)
        # httpx URL-encodes the brackets
        assert "tag_ids%5B0%5D=7" in url or "tag_ids[0]=7" in url
        assert "page=1" in url

    @respx.mock
    async def test_three_pages(self, client_factory):
        # Three responses in sequence — respx side_effect supports a list
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            side_effect=[
                _resp(200, {"data": [{"id": 1}, {"id": 2}], "meta": {"last_page": 3, "current_page": 1}}),
                _resp(200, {"data": [{"id": 3}, {"id": 4}], "meta": {"last_page": 3, "current_page": 2}}),
                _resp(200, {"data": [{"id": 5}], "meta": {"last_page": 3, "current_page": 3}}),
            ]
        )
        async with client_factory() as c:
            result = await c.list_senders_with_tag(7)
        assert [s["id"] for s in result] == [1, 2, 3, 4, 5]

    @respx.mock
    async def test_bare_list_response_terminates(self, client_factory):
        # Some EB endpoints return a bare list with no meta — treat as single page
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            return_value=_resp(200, [{"id": 1}, {"id": 2}])
        )
        async with client_factory() as c:
            result = await c.list_senders_with_tag(7)
        assert [s["id"] for s in result] == [1, 2]

    @respx.mock
    async def test_missing_meta_terminates_after_one_page(self, client_factory):
        # Defense against infinite loop on malformed responses
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}]})
        )
        async with client_factory() as c:
            result = await c.list_senders_with_tag(7)
        assert len(result) == 1

    @respx.mock
    async def test_empty_data_on_page_1_with_last_page_1_terminates(self, client_factory):
        # Empty data is a natural terminator ONLY when last_page is reached
        # (or last_page is missing — single-page response).
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [], "meta": {"last_page": 1, "current_page": 1, "total": 0}})
        )
        async with client_factory() as c:
            result = await c.list_senders_with_tag(7)
        assert result == []

    @respx.mock
    async def test_empty_data_before_last_page_raises(self, client_factory):
        # Defensive: if last_page=5 but page 1 returns empty data, that's silent truncation
        # (the exact bug class that hid Sammy #63's 634 attached senders).
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [], "meta": {"last_page": 5, "current_page": 1, "total": 25}})
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="silent truncation"):
                await c.list_senders_with_tag(7)

    @respx.mock
    async def test_pagination_total_mismatch_raises(self, client_factory):
        # If meta.total disagrees with what we collected, fail loud rather than return wrong data
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            side_effect=[
                _resp(200, {
                    "data": [{"id": 1}, {"id": 2}],
                    "meta": {"current_page": 1, "last_page": 2, "per_page": 2, "total": 10},
                }),
                _resp(200, {
                    "data": [{"id": 3}],
                    "meta": {"current_page": 2, "last_page": 2, "per_page": 2, "total": 10},
                }),
            ]
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match=r"collected 3 senders but meta\.total=10"):
                await c.list_senders_with_tag(7)

    @respx.mock
    async def test_pagination_shape_changes_mid_stream_raises(self, client_factory):
        # Page 1 paginated, page 2 returns bare list — silent truncation territory
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            side_effect=[
                _resp(200, {
                    "data": [{"id": 1}],
                    "meta": {"current_page": 1, "last_page": 2, "per_page": 1, "total": 2},
                }),
                _resp(200, [{"id": 2}]),  # bare list — shape changed
            ]
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="shape changed"):
                await c.list_senders_with_tag(7)

    @respx.mock
    async def test_no_results_returns_empty_list(self, client_factory):
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [], "meta": {"last_page": 1}})
        )
        async with client_factory() as c:
            result = await c.list_senders_with_tag(7)
        assert result == []

    @respx.mock
    async def test_pagination_safety_limit_breach_raises(self, client_factory, monkeypatch):
        # Patch the safety limit DOWN so we can trigger it without 1000 real calls.
        # Each response says last_page=99999 so the loop never sees a natural exit.
        from eod_reapply import eb_client as eb_client_mod
        monkeypatch.setattr(eb_client_mod, "_PAGINATION_SAFETY_LIMIT", 3)

        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            return_value=_resp(200, {"data": [{"id": 1}], "meta": {"last_page": 99999, "current_page": 1}})
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="Pagination safety limit"):
                await c.list_senders_with_tag(7)


# =============================================================================
# Tags
# =============================================================================

class TestTags:
    @respx.mock
    async def test_get_workspace_tags_returns_list(self, client_factory):
        respx.get(f"{BASE_URL}/api/tags").mock(
            return_value=_resp(200, {"data": [
                {"id": 1, "name": "live"},
                {"id": 2, "name": "reserve"},
                {"id": 3, "name": "incubating"},
            ]})
        )
        async with client_factory() as c:
            tags = await c.get_workspace_tags()
        assert len(tags) == 3
        assert tags[0]["name"] == "live"

    @respx.mock
    async def test_resolve_tag_id_finds_match(self, client_factory):
        respx.get(f"{BASE_URL}/api/tags").mock(
            return_value=_resp(200, {"data": [
                {"id": 1, "name": "live"},
                {"id": 2, "name": "reserve"},
            ]})
        )
        async with client_factory() as c:
            tag_id = await c.resolve_tag_id("live")
        assert tag_id == 1

    @respx.mock
    async def test_resolve_tag_id_returns_none_when_missing(self, client_factory):
        respx.get(f"{BASE_URL}/api/tags").mock(
            return_value=_resp(200, {"data": [
                {"id": 2, "name": "reserve"},
            ]})
        )
        async with client_factory() as c:
            tag_id = await c.resolve_tag_id("live")
        assert tag_id is None

    @respx.mock
    async def test_resolve_tag_id_exact_match_only(self, client_factory):
        # Substring matches should NOT count — 'live' shouldn't match 'livewire'
        respx.get(f"{BASE_URL}/api/tags").mock(
            return_value=_resp(200, {"data": [
                {"id": 5, "name": "livewire"},
                {"id": 6, "name": "alive"},
            ]})
        )
        async with client_factory() as c:
            tag_id = await c.resolve_tag_id("live")
        assert tag_id is None


# =============================================================================
# Transport-level errors
# =============================================================================

class TestDefensiveResponseHandling:
    """Cover the defensive branches that handle unusual EB response shapes.

    These shouldn't fire in normal operation, but are no-silent-error guards
    if EB ever returns something unexpected.
    """

    @respx.mock
    async def test_get_campaign_with_204_no_content(self, client_factory):
        # 204 → resp.content is empty → _request returns None → _unwrap returns None
        # → get_campaign returns {} (no AttributeError on dict access downstream)
        respx.get(f"{BASE_URL}/api/campaigns/1").mock(return_value=httpx.Response(204))
        async with client_factory() as c:
            result = await c.get_campaign(1)
        assert result == {}

    @respx.mock
    async def test_get_campaign_senders_with_none_response(self, client_factory):
        # 204 → returns []
        respx.get(f"{BASE_URL}/api/campaigns/1/sender-emails").mock(
            return_value=httpx.Response(204)
        )
        async with client_factory() as c:
            result = await c.get_campaign_senders(1)
        assert result == []

    @respx.mock
    async def test_get_workspace_tags_with_none_response(self, client_factory):
        respx.get(f"{BASE_URL}/api/tags").mock(return_value=httpx.Response(204))
        async with client_factory() as c:
            result = await c.get_workspace_tags()
        assert result == []

    @respx.mock
    async def test_get_workspace_tags_unexpected_shape_raises(self, client_factory):
        # Defensive: if EB ever returns an object instead of a list, fail loud
        respx.get(f"{BASE_URL}/api/tags").mock(
            return_value=_resp(200, {"data": {"unexpected": "shape"}})
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="Expected list"):
                await c.get_workspace_tags()

    @respx.mock
    async def test_list_senders_unexpected_top_level_shape_raises(self, client_factory):
        # Defensive: if EB returns a string or number at top level (highly unusual)
        respx.get(f"{BASE_URL}/api/sender-emails").mock(
            return_value=httpx.Response(200, json="not-a-dict-or-list")
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError, match="Unexpected sender-emails response shape"):
                await c.list_senders_with_tag(1)


class TestTransportErrors:
    @respx.mock
    async def test_timeout_raises_with_status_zero(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/1").mock(
            side_effect=httpx.TimeoutException("read timeout")
        )
        async with client_factory(timeout_seconds=0.5) as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.get_campaign(1)
        assert exc.value.status_code == 0
        assert "Timeout" in exc.value.message

    @respx.mock
    async def test_connect_error_raises_with_status_zero(self, client_factory):
        respx.get(f"{BASE_URL}/api/campaigns/1").mock(
            side_effect=httpx.ConnectError("refused")
        )
        async with client_factory() as c:
            with pytest.raises(EmailBisonAPIError) as exc:
                await c.get_campaign(1)
        assert exc.value.status_code == 0
        assert "Network" in exc.value.message
