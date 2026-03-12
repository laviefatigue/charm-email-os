#!/usr/bin/env python3
"""
Tests for EmailBison Client - Tag Operations

Verifies correct HTTP methods and endpoints for tag/untag operations.
The untag bug (DELETE /tags/attach-to-sender-emails instead of POST /tags/remove-from-sender-emails)
caused dual tags on inboxes. See: docs/decisions/EMAILBISON-UNTAG-ENDPOINT-FIX.md

Run:
    pytest tests/test_emailbison_client.py -v
    py -m pytest tests/test_emailbison_client.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ============================================================
# Extract the method/endpoint pairs for testing without
# needing to actually call the API
# ============================================================

class TestTagEndpoints:
    """Verify tag_inbox and untag_inbox use correct HTTP methods and endpoints."""

    @pytest.mark.asyncio
    async def test_tag_inbox_uses_post_attach(self):
        """tag_inbox() must use POST /tags/attach-to-sender-emails"""
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"success": True})

        await client.tag_inbox(account_id=123, tag_id=456)

        client._request.assert_called_once_with(
            'POST',
            '/tags/attach-to-sender-emails',
            json_data={
                'tag_ids': [456],
                'sender_email_ids': [123]
            }
        )

    @pytest.mark.asyncio
    async def test_untag_inbox_uses_post_remove(self):
        """untag_inbox() must use POST /tags/remove-from-sender-emails (NOT DELETE on attach)"""
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"success": True})

        await client.untag_inbox(account_id=123, tag_id=456)

        client._request.assert_called_once_with(
            'POST',
            '/tags/remove-from-sender-emails',
            json_data={
                'tag_ids': [456],
                'sender_email_ids': [123]
            }
        )

    @pytest.mark.asyncio
    async def test_untag_never_uses_delete(self):
        """Regression test: untag must NEVER use DELETE method"""
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"success": True})

        await client.untag_inbox(account_id=1, tag_id=2)

        method_used = client._request.call_args[0][0]
        assert method_used != 'DELETE', \
            "untag_inbox must use POST, not DELETE. See docs/decisions/EMAILBISON-UNTAG-ENDPOINT-FIX.md"

    @pytest.mark.asyncio
    async def test_untag_never_uses_attach_endpoint(self):
        """Regression test: untag must NEVER hit the attach endpoint"""
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"success": True})

        await client.untag_inbox(account_id=1, tag_id=2)

        endpoint_used = client._request.call_args[0][1]
        assert 'attach' not in endpoint_used, \
            "untag_inbox must use /tags/remove-from-sender-emails, not the attach endpoint"

    @pytest.mark.asyncio
    async def test_tag_and_untag_use_different_endpoints(self):
        """tag and untag must hit different endpoints"""
        from sync_modules.emailbison_client import EmailBisonClient

        client = EmailBisonClient(api_url="https://fake.api/api", api_key="fake-key")
        client._request = AsyncMock(return_value={"success": True})

        await client.tag_inbox(account_id=1, tag_id=2)
        tag_endpoint = client._request.call_args[0][1]

        client._request.reset_mock()

        await client.untag_inbox(account_id=1, tag_id=2)
        untag_endpoint = client._request.call_args[0][1]

        assert tag_endpoint != untag_endpoint, \
            f"tag and untag must use different endpoints, both used: {tag_endpoint}"
        assert tag_endpoint == '/tags/attach-to-sender-emails'
        assert untag_endpoint == '/tags/remove-from-sender-emails'
