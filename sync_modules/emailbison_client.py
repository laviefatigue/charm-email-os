"""
EmailBison API Client

Shared async client with workspace switching, pagination, and retry logic.
Based on patterns from OwnRBL/clients/emailbison_client.py
"""
import asyncio
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import httpx

_raw_api_url = os.getenv('EMAILBISON_API_URL', 'https://spellcast.hirecharm.com/api')
# Ensure URL ends with /api (some configs miss this)
EMAILBISON_API_URL = _raw_api_url if _raw_api_url.endswith('/api') else f"{_raw_api_url.rstrip('/')}/api"
EMAILBISON_API_KEY = os.getenv('EMAILBISON_API_KEY', '')

# Debug: Log the actual URL being used (v2 - with /api fix)
print(f"[EmailBison Client v2] API URL: {EMAILBISON_API_URL}")

DEFAULT_TIMEOUT = 60.0
DEFAULT_RETRIES = 3
DEFAULT_RETRY_DELAY = 5.0


class EmailBisonClient:
    """Async EmailBison API client with workspace context management."""

    def __init__(
        self,
        api_url: str = None,
        api_key: str = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY
    ):
        self.api_url = api_url or EMAILBISON_API_URL
        self.api_key = api_key or EMAILBISON_API_KEY
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.client: Optional[httpx.AsyncClient] = None
        self.current_workspace_id: Optional[int] = None

    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict = None,
        json_data: Dict = None,
        retry_count: int = 0
    ) -> Dict:
        """Make HTTP request with retry logic."""
        url = f"{self.api_url}{endpoint}"

        try:
            response = await self.client.request(
                method=method,
                url=url,
                params=params,
                json=json_data
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            error_text = e.response.text[:500] if e.response else 'No response'
            if retry_count < self.max_retries and e.response.status_code >= 500:
                await asyncio.sleep(self.retry_delay * (retry_count + 1))
                return await self._request(method, endpoint, params, json_data, retry_count + 1)
            raise EmailBisonAPIError(
                f"HTTP {e.response.status_code}: {error_text}",
                status_code=e.response.status_code
            )

        except httpx.TimeoutException:
            if retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (retry_count + 1))
                return await self._request(method, endpoint, params, json_data, retry_count + 1)
            raise EmailBisonAPIError(f"Timeout connecting to {url}")

        except httpx.RequestError as e:
            if retry_count < self.max_retries:
                await asyncio.sleep(self.retry_delay * (retry_count + 1))
                return await self._request(method, endpoint, params, json_data, retry_count + 1)
            raise EmailBisonAPIError(f"Connection error: {str(e)}")

    # =========================================================================
    # WORKSPACE MANAGEMENT
    # =========================================================================

    async def switch_workspace(self, workspace_id: int) -> bool:
        """
        Switch to a workspace context.
        CRITICAL: Must be called before any workspace-scoped operation.
        """
        if self.current_workspace_id == workspace_id:
            return True

        try:
            await self._request(
                'POST',
                '/workspaces/switch-workspace',  # v1.1 endpoint deprecated
                json_data={'team_id': int(workspace_id)}
            )
            self.current_workspace_id = workspace_id
            return True
        except EmailBisonAPIError as e:
            print(f"[ERROR] Failed to switch workspace to {workspace_id}: {e}")
            return False

    async def list_workspaces(self) -> List[Dict]:
        """Get all workspaces (not workspace-scoped)."""
        data = await self._request('GET', '/workspaces/v1.1')
        return data if isinstance(data, list) else data.get('data', [])

    # =========================================================================
    # SENDER ACCOUNTS (Inboxes)
    # =========================================================================

    async def get_sender_accounts(
        self,
        page: int = 1,
        per_page: int = 100
    ) -> Dict:
        """Get sender accounts for current workspace (paginated)."""
        return await self._request(
            'GET',
            '/sender-emails',
            params={'page': page, 'per_page': per_page}
        )

    async def get_all_sender_accounts(self) -> List[Dict]:
        """Get all sender accounts for current workspace (handles pagination)."""
        all_accounts = []
        page = 1

        while True:
            response = await self.get_sender_accounts(page=page, per_page=100)

            # Handle both list and dict response formats
            if isinstance(response, list):
                accounts = response
                all_accounts.extend(accounts)
                break
            else:
                accounts = response.get('data', [])
                if not accounts:
                    break

                all_accounts.extend(accounts)

                meta = response.get('meta', {})
                current_page = meta.get('current_page', page)
                last_page = meta.get('last_page', current_page)

                if current_page >= last_page:
                    break

            page += 1

        return all_accounts

    async def get_sender_account(self, account_id: int) -> Dict:
        """Get single sender account details."""
        return await self._request('GET', f'/sender-emails/{account_id}')

    async def update_sender_account(self, account_id: int, data: Dict) -> Dict:
        """Update sender account."""
        return await self._request('PATCH', f'/sender-emails/{account_id}', json_data=data)

    # NOTE: delete_sender_account() method intentionally removed.
    # Inboxes are NEVER deleted from EmailBison - only tagged and flagged locally.
    # See kill_processor.py for the tagging-only workflow.

    async def get_sender_campaigns(self, account_id: int) -> List[Dict]:
        """Get campaigns that a sender account is assigned to."""
        response = await self._request('GET', f'/sender-emails/{account_id}/campaigns')
        if isinstance(response, list):
            return response
        return response.get('data', [])

    # =========================================================================
    # TAGS
    # =========================================================================

    async def list_tags(self) -> List[Dict]:
        """Get all tags for current workspace."""
        data = await self._request('GET', '/tags')
        return data if isinstance(data, list) else data.get('data', [])

    async def create_tag(self, name: str) -> Dict:
        """Create a new tag in current workspace."""
        return await self._request('POST', '/tags', json_data={'name': name})

    async def get_or_create_tag(self, name: str) -> Dict:
        """Get existing tag by name or create it."""
        tags = await self.list_tags()
        for tag in tags:
            if tag.get('name', '').lower() == name.lower():
                return tag

        return await self.create_tag(name)

    async def tag_inbox(self, account_id: int, tag_id: int) -> Dict:
        """Add tag to inbox.

        Uses the bulk tagging endpoint: POST /tags/attach-to-sender-emails
        Docs: https://docs.emailbison.com/tags/attaching-tags
        """
        return await self._request(
            'POST',
            '/tags/attach-to-sender-emails',
            json_data={
                'tag_ids': [tag_id],
                'sender_email_ids': [account_id]
            }
        )

    async def untag_inbox(self, account_id: int, tag_id: int) -> Dict:
        """Remove tag from inbox.

        Uses the bulk tagging endpoint: DELETE /tags/attach-to-sender-emails
        Docs: https://docs.emailbison.com/tags/removing-tags
        """
        return await self._request(
            'DELETE',
            '/tags/attach-to-sender-emails',
            json_data={
                'tag_ids': [tag_id],
                'sender_email_ids': [account_id]
            }
        )

    # =========================================================================
    # CAMPAIGNS
    # =========================================================================

    async def get_campaigns(self, page: int = 1, limit: int = 100) -> Dict:
        """Get campaigns for current workspace (paginated)."""
        return await self._request(
            'GET',
            '/campaigns',
            params={'page': page, 'limit': limit}
        )

    async def get_all_campaigns(self) -> List[Dict]:
        """Get all campaigns for current workspace (handles pagination)."""
        all_campaigns = []
        page = 1

        while True:
            response = await self.get_campaigns(page=page, limit=100)

            if isinstance(response, list):
                all_campaigns.extend(response)
                break
            else:
                campaigns = response.get('data', [])
                if not campaigns:
                    break

                all_campaigns.extend(campaigns)

                meta = response.get('meta', {})
                if page >= meta.get('last_page', page):
                    break

            page += 1

        return all_campaigns

    async def get_campaign_details(self, campaign_id: int) -> Dict:
        """Get detailed campaign info including metrics."""
        return await self._request('GET', f'/campaigns/{campaign_id}')

    async def get_campaign_replies(
        self,
        campaign_id: int,
        folder: str = 'inbox',
        page: int = 1,
        limit: int = 50
    ) -> Dict:
        """
        Get campaign replies/bounces.

        Args:
            campaign_id: Campaign ID
            folder: 'inbox', 'bounced', or 'spam'
            page: Page number
            limit: Results per page
        """
        return await self._request(
            'GET',
            f'/campaigns/{campaign_id}/replies',
            params={'folder': folder, 'page': page, 'limit': limit}
        )

    async def get_all_campaign_replies(
        self,
        campaign_id: int,
        folder: str = 'inbox'
    ) -> List[Dict]:
        """Get all replies for a campaign folder (handles pagination)."""
        all_replies = []
        page = 1

        while True:
            response = await self.get_campaign_replies(
                campaign_id=campaign_id,
                folder=folder,
                page=page,
                limit=100
            )

            if isinstance(response, list):
                all_replies.extend(response)
                break
            else:
                replies = response.get('data', [])
                if not replies:
                    break

                all_replies.extend(replies)

                meta = response.get('meta', {})
                if page >= meta.get('last_page', page):
                    break

            page += 1

        return all_replies

    async def get_campaign_leads(
        self,
        campaign_id: int,
        page: int = 1,
        limit: int = 100
    ) -> Dict:
        """Get campaign leads."""
        return await self._request(
            'GET',
            f'/campaigns/{campaign_id}/leads',
            params={'page': page, 'limit': limit}
        )

    # =========================================================================
    # WARMUP
    # =========================================================================

    async def get_warmup_sender_accounts(
        self,
        warmup_status: str = None,
        start_date: str = None,
        end_date: str = None,
        page: int = 1,
        per_page: int = 100
    ) -> Dict:
        """Get sender accounts with warmup statistics.

        Args:
            warmup_status: Filter by 'enabled' or 'disabled'
            start_date: Start date for stats (YYYY-MM-DD)
            end_date: End date for stats (YYYY-MM-DD)
            page: Page number
            per_page: Results per page
        """
        params = {'page': page, 'per_page': per_page}
        if warmup_status:
            params['warmup_status'] = warmup_status
        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        return await self._request('GET', '/warmup/sender-emails', params=params)

    async def get_all_warmup_sender_accounts(
        self,
        warmup_status: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> List[Dict]:
        """Get all sender accounts with warmup stats (handles pagination)."""
        all_accounts = []
        page = 1

        while True:
            response = await self.get_warmup_sender_accounts(
                warmup_status=warmup_status,
                start_date=start_date,
                end_date=end_date,
                page=page,
                per_page=100
            )

            if isinstance(response, list):
                all_accounts.extend(response)
                break
            else:
                accounts = response.get('data', [])
                if not accounts:
                    break

                all_accounts.extend(accounts)

                meta = response.get('meta', {})
                if page >= meta.get('last_page', page):
                    break

            page += 1

        return all_accounts

    async def enable_warmup(self, sender_email_ids: List[int]) -> Dict:
        """Enable warmup for specified inboxes.

        Args:
            sender_email_ids: List of EmailBison sender account IDs
        """
        return await self._request(
            'PATCH',
            '/warmup/sender-emails/enable',
            json_data={'sender_email_ids': sender_email_ids}
        )

    async def disable_warmup(self, sender_email_ids: List[int]) -> Dict:
        """Disable warmup for specified inboxes (24hr ramp-down).

        Args:
            sender_email_ids: List of EmailBison sender account IDs
        """
        return await self._request(
            'PATCH',
            '/warmup/sender-emails/disable',
            json_data={'sender_email_ids': sender_email_ids}
        )


class EmailBisonAPIError(Exception):
    """Custom exception for EmailBison API errors."""

    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        self.status_code = status_code
