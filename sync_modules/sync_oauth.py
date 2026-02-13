"""
OAuth Config Sync Module

Scrapes Google OAuth Client IDs from EmailBison UI using browser automation.
The EmailBison API does not expose OAuth configuration, so we must scrape it.

Features:
- Queue-based async processing for new workspaces
- Monthly verification of existing configs
- Change detection with alerting
"""
import asyncio
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from uuid import UUID
import asyncpg

from playwright.async_api import async_playwright, Page, Browser

from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Configuration
EMAILBISON_URL = os.getenv("EMAILBISON_API_URL", "https://spellcast.hirecharm.com").rstrip("/api")
EMAILBISON_EMAIL = os.getenv("EMAILBISON_BROWSER_EMAIL", "")
EMAILBISON_PASSWORD = os.getenv("EMAILBISON_BROWSER_PASSWORD", "")
GOOGLE_OAUTH_PATH = "/sender-email-connect/google/oauth"

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 60


class OAuthSyncModule:
    """
    Sync Google OAuth Client IDs from EmailBison UI.

    Uses Playwright browser automation since the API doesn't expose this data.
    Supports:
    - Processing queued OAuth sync jobs (new workspaces)
    - Monthly verification of existing configs
    - Change detection with previous value tracking
    """

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_logger: AuditLogger,
        alerter: SlackAlerter = None
    ):
        self.db = db
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    async def process_queue(self) -> List[SyncResult]:
        """
        Process pending OAuth sync jobs from the queue.

        Called frequently by the sync worker to handle newly created workspaces.
        """
        results = []

        # Get pending queue items (oldest first, respecting retry limits)
        pending_items = await self.db.fetch("""
            SELECT q.id, q.workspace_id, q.emailbison_workspace_id, q.retry_count,
                   w.workspace_name
            FROM oauth_sync_queue q
            JOIN workspaces w ON w.id = q.workspace_id
            WHERE q.status IN ('pending', 'failed')
            AND q.retry_count < q.max_retries
            ORDER BY q.created_at ASC
            LIMIT 10
        """)

        if not pending_items:
            return results

        print(f"[OAuthSync] Processing {len(pending_items)} queued items")

        # Process each item with browser automation
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            try:
                page = await browser.new_page()

                # Login once for all items
                if not await self._login(page):
                    print("[OAuthSync] Browser login failed, aborting queue processing")
                    return results

                for item in pending_items:
                    queue_id = item['id']
                    workspace_id = item['workspace_id']
                    eb_workspace_id = item['emailbison_workspace_id']
                    workspace_name = item['workspace_name']

                    # Mark as processing
                    await self.db.execute("""
                        UPDATE oauth_sync_queue
                        SET status = 'processing', started_at = NOW()
                        WHERE id = $1
                    """, queue_id)

                    try:
                        result = await self._sync_workspace(
                            page=page,
                            workspace_id=workspace_id,
                            workspace_name=workspace_name,
                            emailbison_workspace_id=eb_workspace_id
                        )
                        results.append(result)

                        if result.status == 'completed':
                            # Mark queue item as completed
                            await self.db.execute("""
                                UPDATE oauth_sync_queue
                                SET status = 'completed', processed_at = NOW()
                                WHERE id = $1
                            """, queue_id)
                        else:
                            # Mark as failed, increment retry count
                            await self.db.execute("""
                                UPDATE oauth_sync_queue
                                SET status = 'failed',
                                    retry_count = retry_count + 1,
                                    error_message = $2
                                WHERE id = $1
                            """, queue_id, result.error_message)

                    except Exception as e:
                        print(f"[OAuthSync] Error processing {workspace_name}: {e}")
                        await self.db.execute("""
                            UPDATE oauth_sync_queue
                            SET status = 'failed',
                                retry_count = retry_count + 1,
                                error_message = $2
                            WHERE id = $1
                        """, queue_id, str(e))

            finally:
                await browser.close()

        return results

    async def verify_existing_configs(self) -> List[SyncResult]:
        """
        Monthly verification of existing OAuth configs.

        Checks if stored Client IDs are still valid and detects changes.
        """
        results = []

        # Get configs that haven't been verified in 30+ days
        stale_configs = await self.db.fetch("""
            SELECT oc.id, oc.workspace_id, oc.google_client_id,
                   w.workspace_name, w.emailbison_workspace_id
            FROM oauth_configs oc
            JOIN workspaces w ON w.id = oc.workspace_id
            WHERE w.is_active = TRUE
            AND w.emailbison_workspace_id IS NOT NULL
            AND (oc.last_verified_at IS NULL
                 OR oc.last_verified_at < NOW() - INTERVAL '30 days')
            ORDER BY oc.last_verified_at ASC NULLS FIRST
            LIMIT 20
        """)

        if not stale_configs:
            print("[OAuthSync] No configs need verification")
            return results

        print(f"[OAuthSync] Verifying {len(stale_configs)} OAuth configs")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            try:
                page = await browser.new_page()

                if not await self._login(page):
                    print("[OAuthSync] Browser login failed, aborting verification")
                    return results

                for config in stale_configs:
                    workspace_id = config['workspace_id']
                    workspace_name = config['workspace_name']
                    eb_workspace_id = config['emailbison_workspace_id']
                    previous_client_id = config['google_client_id']

                    try:
                        result = await self._sync_workspace(
                            page=page,
                            workspace_id=workspace_id,
                            workspace_name=workspace_name,
                            emailbison_workspace_id=eb_workspace_id,
                            verify_mode=True,
                            expected_client_id=previous_client_id
                        )
                        results.append(result)

                    except Exception as e:
                        print(f"[OAuthSync] Error verifying {workspace_name}: {e}")

            finally:
                await browser.close()

        return results

    async def sync_all_workspaces(self) -> List[SyncResult]:
        """
        Full sync of all workspaces (initial population).

        Use sparingly - prefer queue-based processing for new workspaces.
        """
        results = []

        workspaces = await self.db.fetch("""
            SELECT id, workspace_name, emailbison_workspace_id
            FROM workspaces
            WHERE emailbison_workspace_id IS NOT NULL
            AND is_active = TRUE
        """)

        print(f"[OAuthSync] Full sync of {len(workspaces)} workspaces")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)

            try:
                page = await browser.new_page()

                if not await self._login(page):
                    print("[OAuthSync] Browser login failed")
                    return results

                for ws in workspaces:
                    try:
                        result = await self._sync_workspace(
                            page=page,
                            workspace_id=ws['id'],
                            workspace_name=ws['workspace_name'],
                            emailbison_workspace_id=int(ws['emailbison_workspace_id'])
                        )
                        results.append(result)

                    except Exception as e:
                        print(f"[OAuthSync] Error syncing {ws['workspace_name']}: {e}")

            finally:
                await browser.close()

        return results

    async def _login(self, page: Page) -> bool:
        """Login to EmailBison via browser."""
        if not EMAILBISON_EMAIL or not EMAILBISON_PASSWORD:
            print("[OAuthSync] Browser credentials not configured")
            return False

        try:
            await page.goto(f"{EMAILBISON_URL}/login", wait_until="networkidle")

            # Check if already logged in
            if "dashboard" in page.url:
                print("[OAuthSync] Already logged in")
                return True

            # Fill login form
            await page.fill('input[type="email"], input[name="email"]', EMAILBISON_EMAIL)
            await page.fill('input[type="password"], input[name="password"]', EMAILBISON_PASSWORD)
            await page.click('button[type="submit"]')

            # Wait for redirect to dashboard
            await page.wait_for_url("**/dashboard**", timeout=15000)
            print("[OAuthSync] Login successful")
            return True

        except Exception as e:
            print(f"[OAuthSync] Login failed: {e}")
            return False

    async def _sync_workspace(
        self,
        page: Page,
        workspace_id: UUID,
        workspace_name: str,
        emailbison_workspace_id: int,
        verify_mode: bool = False,
        expected_client_id: Optional[str] = None
    ) -> SyncResult:
        """
        Sync OAuth config for a single workspace.

        Args:
            page: Playwright page (already logged in)
            workspace_id: Local workspace UUID
            workspace_name: Workspace name for logging
            emailbison_workspace_id: EmailBison workspace ID
            verify_mode: If True, checking existing config
            expected_client_id: Expected Client ID for verification
        """
        audit = await self.audit_logger.start_audit(
            'oauth',
            workspace_id,
            {'workspace_name': workspace_name, 'verify_mode': verify_mode}
        )

        try:
            # Navigate to Google OAuth page for this workspace
            oauth_config = await self._scrape_oauth_config(page, emailbison_workspace_id)

            if not oauth_config.get('google_client_id'):
                audit.add_error(
                    str(workspace_id),
                    "No Google Client ID found on page",
                    {'url': oauth_config.get('url')}
                )
                return await audit.fail(Exception("No Google Client ID found"))

            google_client_id = oauth_config['google_client_id']
            google_app_name = oauth_config.get('app_name')

            # Check for changes in verify mode
            verification_status = 'verified'
            previous_client_id = None

            if verify_mode and expected_client_id:
                if google_client_id != expected_client_id:
                    verification_status = 'changed'
                    previous_client_id = expected_client_id

                    # Alert on change
                    if self.alerter:
                        await self.alerter.send_alert(
                            f":warning: OAuth Client ID Changed for {workspace_name}",
                            f"Previous: {expected_client_id[:30]}...\n"
                            f"New: {google_client_id[:30]}..."
                        )

            # Upsert oauth_configs record
            await self.db.execute("""
                INSERT INTO oauth_configs (
                    workspace_id, google_client_id, google_app_name,
                    last_verified_at, verification_status, previous_google_client_id,
                    scraped_at
                ) VALUES ($1, $2, $3, NOW(), $4, $5, NOW())
                ON CONFLICT (workspace_id) DO UPDATE SET
                    google_client_id = EXCLUDED.google_client_id,
                    google_app_name = EXCLUDED.google_app_name,
                    last_verified_at = NOW(),
                    verification_status = EXCLUDED.verification_status,
                    previous_google_client_id = CASE
                        WHEN oauth_configs.google_client_id != EXCLUDED.google_client_id
                        THEN oauth_configs.google_client_id
                        ELSE oauth_configs.previous_google_client_id
                    END,
                    scraped_at = NOW(),
                    updated_at = NOW()
            """, workspace_id, google_client_id, google_app_name,
                verification_status, previous_client_id)

            audit.increment_processed()
            if verify_mode:
                audit.increment_updated()
            else:
                audit.increment_created()

            print(f"[OAuthSync] {workspace_name}: {google_client_id[:40]}... ({verification_status})")
            return await audit.complete()

        except Exception as e:
            print(f"[OAuthSync] Error for {workspace_name}: {e}")
            return await audit.fail(e)

    async def _scrape_oauth_config(self, page: Page, emailbison_workspace_id: int) -> dict:
        """
        Navigate to OAuth page and extract Client ID.

        Args:
            page: Playwright page (logged in)
            emailbison_workspace_id: Workspace to switch to

        Returns:
            dict with google_client_id, app_name, url
        """
        # Switch workspace by navigating to workspace-specific URL or using API
        # Note: We navigate directly - the page will be in the current session's workspace
        oauth_url = f"{EMAILBISON_URL}{GOOGLE_OAUTH_PATH}"
        await page.goto(oauth_url, wait_until="networkidle")
        await page.wait_for_timeout(1500)

        # Handle workspace-changed redirect
        if "workspace-changed" in page.url:
            try:
                await page.click('text="Back to dashboard"')
                await page.wait_for_timeout(500)
                await page.goto(oauth_url, wait_until="networkidle")
                await page.wait_for_timeout(1000)
            except Exception:
                pass

        # Extract Client ID from page
        result = await page.evaluate("""
            () => {
                // Get Google Client ID from input fields
                const inputs = Array.from(document.querySelectorAll('input'));
                let googleClientId = null;

                for (const input of inputs) {
                    const value = input.value || '';
                    if (value.includes('.apps.googleusercontent.com')) {
                        googleClientId = value;
                        break;
                    }
                }

                // Fallback: search in page text
                if (!googleClientId) {
                    const pageText = document.body.innerText;
                    const match = pageText.match(/\\d{12}-[a-z0-9]+\\.apps\\.googleusercontent\\.com/);
                    googleClientId = match ? match[0] : null;
                }

                // Get app name from instructions
                const pageText = document.body.innerText;
                const appNameMatch = pageText.match(/Select\\s+([A-Za-z0-9]+)\\./i);

                return {
                    google_client_id: googleClientId,
                    app_name: appNameMatch ? appNameMatch[1] : null,
                    url: window.location.href
                };
            }
        """)

        return result
