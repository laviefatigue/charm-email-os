"""Tests for EngagementSyncModule and related client methods."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestEngagementClientMethods:
    """Tests for EmailBison client engagement endpoints."""

    @pytest.mark.asyncio
    async def test_get_campaign_event_stats_calls_correct_endpoint(self):
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"data": []})

        await client.get_campaign_event_stats(
            start_date="2026-03-01",
            end_date="2026-03-07"
        )

        client._request.assert_called_once_with(
            'GET', '/campaign-events/stats',
            params={'start_date': '2026-03-01', 'end_date': '2026-03-07'}
        )

    @pytest.mark.asyncio
    async def test_get_campaign_event_stats_passes_sender_email_ids(self):
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"data": []})

        await client.get_campaign_event_stats(
            start_date="2026-03-01",
            end_date="2026-03-07",
            sender_email_ids=[100, 200, 300]
        )

        call_args = client._request.call_args
        params = call_args[1]['params'] if 'params' in call_args[1] else call_args[0][2]
        assert params['sender_email_ids[0]'] == 100
        assert params['sender_email_ids[1]'] == 200
        assert params['sender_email_ids[2]'] == 300

    @pytest.mark.asyncio
    async def test_get_sender_email_replies_calls_correct_endpoint(self):
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"data": [], "meta": {"last_page": 1}})

        await client.get_sender_email_replies(
            sender_email_id=12345,
            folder='inbox',
            status='interested'
        )

        client._request.assert_called_once_with(
            'GET', '/sender-emails/12345/replies',
            params={'page': 1, 'folder': 'inbox', 'status': 'interested'}
        )

    @pytest.mark.asyncio
    async def test_get_all_sender_email_replies_handles_pagination(self):
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")

        # Simulate 2 pages of results
        page1 = {"data": [{"id": 1}, {"id": 2}], "meta": {"current_page": 1, "last_page": 2}}
        page2 = {"data": [{"id": 3}], "meta": {"current_page": 2, "last_page": 2}}
        client.get_sender_email_replies = AsyncMock(side_effect=[page1, page2])

        result = await client.get_all_sender_email_replies(sender_email_id=100)

        assert len(result) == 3
        assert result[0]['id'] == 1
        assert result[2]['id'] == 3

    @pytest.mark.asyncio
    async def test_get_all_sender_email_replies_handles_empty_response(self):
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client.get_sender_email_replies = AsyncMock(
            return_value={"data": [], "meta": {"current_page": 1, "last_page": 1}}
        )

        result = await client.get_all_sender_email_replies(sender_email_id=100)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_sender_email_replies_handles_list_response(self):
        """EB sometimes returns a plain list instead of paginated dict."""
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client.get_sender_email_replies = AsyncMock(
            return_value=[{"id": 1}, {"id": 2}]
        )

        result = await client.get_all_sender_email_replies(sender_email_id=100)
        assert len(result) == 2


class TestEngagementSyncModule:
    """Tests for the EngagementSyncModule."""

    def _make_module(self):
        from sync_modules.sync_engagement import EngagementSyncModule

        db = AsyncMock()
        client = AsyncMock()
        audit_logger = AsyncMock()
        alerter = AsyncMock()

        # Mock audit context
        audit_ctx = AsyncMock()
        audit_ctx.increment_processed = AsyncMock()
        audit_ctx.increment_created = AsyncMock()
        audit_ctx.increment_updated = AsyncMock()
        audit_ctx.add_error = AsyncMock()
        audit_ctx.complete = AsyncMock(return_value=MagicMock(success=True))
        audit_ctx.fail = AsyncMock(return_value=MagicMock(success=False))
        audit_logger.start_audit = AsyncMock(return_value=audit_ctx)

        module = EngagementSyncModule(
            db=db, client=client,
            audit_logger=audit_logger, alerter=alerter
        )
        return module, db, client, audit_ctx

    def test_parse_event_stats_extracts_daily_counts(self):
        from sync_modules.sync_engagement import EngagementSyncModule

        module = EngagementSyncModule.__new__(EngagementSyncModule)

        stats = {
            "data": [
                {"label": "Replied", "dates": [["2026-03-15", 3], ["2026-03-16", 1]]},
                {"label": "Sent", "dates": [["2026-03-15", 50], ["2026-03-16", 45]]},
                {"label": "Unique Opens", "dates": [["2026-03-15", 10], ["2026-03-16", 8]]},
                {"label": "Interested", "dates": [["2026-03-15", 2], ["2026-03-16", 0]]},
                {"label": "Bounced", "dates": [["2026-03-15", 1], ["2026-03-16", 0]]},
            ]
        }

        result = module._parse_event_stats(stats, "2026-03-15")
        assert result['replies'] == 3
        assert result['sent'] == 50
        assert result['unique_opens'] == 10
        assert result['interested'] == 2
        assert result['bounced'] == 1

    def test_parse_event_stats_returns_zeros_for_missing_date(self):
        from sync_modules.sync_engagement import EngagementSyncModule

        module = EngagementSyncModule.__new__(EngagementSyncModule)

        stats = {
            "data": [
                {"label": "Sent", "dates": [["2026-03-15", 50]]},
            ]
        }

        result = module._parse_event_stats(stats, "2026-03-20")  # Date not in response
        assert result['sent'] == 0
        assert result['replies'] == 0

    def test_parse_event_stats_handles_empty_response(self):
        from sync_modules.sync_engagement import EngagementSyncModule

        module = EngagementSyncModule.__new__(EngagementSyncModule)

        assert module._parse_event_stats({}, "2026-03-15")['sent'] == 0
        assert module._parse_event_stats(None, "2026-03-15")['sent'] == 0
        assert module._parse_event_stats({"data": []}, "2026-03-15")['sent'] == 0

    def test_parse_all_dates_extracts_multiple_days(self):
        from sync_modules.sync_engagement import EngagementSyncModule

        module = EngagementSyncModule.__new__(EngagementSyncModule)

        stats = {
            "data": [
                {"label": "Replied", "dates": [["2026-03-15", 3], ["2026-03-16", 1]]},
                {"label": "Sent", "dates": [["2026-03-15", 50], ["2026-03-16", 45]]},
            ]
        }

        result = module._parse_all_dates(stats)
        assert len(result) == 2
        assert result["2026-03-15"]["replies"] == 3
        assert result["2026-03-15"]["sent"] == 50
        assert result["2026-03-16"]["replies"] == 1
        assert result["2026-03-16"]["sent"] == 45

    @pytest.mark.asyncio
    async def test_sync_workspace_handles_empty_inbox_list(self):
        module, db, client, audit_ctx = self._make_module()

        db.fetch = AsyncMock(return_value=[])  # No inboxes

        # eb_workspace_id removed — client is pre-scoped to the workspace
        result = await module.sync_workspace(
            workspace_id=uuid4(),
            workspace_name="Test",
        )

        audit_ctx.complete.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_workspace_calls_event_stats_per_inbox(self):
        module, db, client, audit_ctx = self._make_module()

        inbox_id = uuid4()
        # switch_workspace removed — client is pre-scoped to the workspace
        db.fetch = AsyncMock(return_value=[
            {"id": inbox_id, "emailbison_account_id": "12345", "email_address": "test@example.com"}
        ])
        db.execute = AsyncMock()
        client.get_campaign_event_stats = AsyncMock(return_value={
            "data": [
                {"label": "Sent", "dates": [["2026-03-18", 10]]},
                {"label": "Replied", "dates": [["2026-03-18", 1]]},
            ]
        })

        ws_id = uuid4()
        # eb_workspace_id removed — client is pre-scoped to the workspace
        await module.sync_workspace(ws_id, "Test")

        # Should have called event stats for the inbox
        client.get_campaign_event_stats.assert_called_once()
        call_args = client.get_campaign_event_stats.call_args
        assert call_args[1]['sender_email_ids'] == [12345]
