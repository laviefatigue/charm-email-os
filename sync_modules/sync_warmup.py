"""
Warmup Sync Module

Synchronizes warmup status and statistics from EmailBison's dedicated warmup API.
Tracks warmup lifecycle: start times, progress, and completion.

Architecture (workspace-concurrent model):
    This module is designed for per-workspace parallel execution.
    It is called by WorkspaceSyncQueue._dispatch() with a workspace-scoped
    EmailBisonClient already initialised with the per-workspace API key.

    Contract:
        - Caller passes a client already scoped to the target workspace.
        - NO switch_workspace() calls anywhere in this module.
        - sync_workspace_warmup(workspace_id, workspace_name) handles one workspace.
        - auto_enable_warmup_for_connected() is called as an internal post-step
          at the end of sync_workspace_warmup() — the same scoped client is reused.

    Removed (old sequential model):
        - sync_all_workspaces()      — replaced by WorkspaceSyncQueue scheduler
        - emailbison_workspace_id param — no longer needed; client is pre-scoped
        - switch_workspace() calls   — eliminated by workspace-scoped API keys
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


class WarmupSyncModule:
    """Synchronizes warmup status and statistics from EmailBison."""

    def __init__(
        self,
        db: asyncpg.Pool,
        client: EmailBisonClient,
        audit_logger: AuditLogger,
        alerter: SlackAlerter = None
    ):
        self.db = db
        self.client = client
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    async def sync_workspace_warmup(
        self,
        workspace_id: UUID,
        workspace_name: str,
    ) -> SyncResult:
        """
        Sync warmup stats for a single workspace.

        The EmailBisonClient (self.client) must already be scoped to this
        workspace via its API key.  No switch_workspace() call is made here.
        Called by WorkspaceSyncQueue._dispatch() with a per-workspace client.

        Steps:
        1. Call GET /api/warmup/sender-emails with date range (last 7 days)
        2. For each inbox:
           - Update warmup_enabled status
           - Set warmup_started_at if first time seeing warmup_enabled=true
           - Create sender_warmup_snapshot record
           - Calculate warmup_progress (days/30 capped at 100%)
        3. auto_enable_warmup_for_connected() — enable warmup for inboxes that
           are connected but not yet in warmup (uses same scoped client).
        """
        audit = await self.audit_logger.start_audit(
            sync_type='warmup',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Get date range for warmup stats (last 7 days)
            end_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            start_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime('%Y-%m-%d')

            # Fetch warmup accounts
            warmup_accounts = await self.client.get_all_warmup_sender_accounts(
                start_date=start_date,
                end_date=end_date
            )
            print(f"  [{workspace_name}] Found {len(warmup_accounts)} accounts with warmup data")

            for account in warmup_accounts:
                audit.increment_processed()

                try:
                    await self.update_warmup_status(workspace_id, account, start_date, end_date)
                    audit.increment_updated()
                except Exception as e:
                    audit.add_error(
                        record_id=account.get('email'),
                        error=str(e),
                        details={'emailbison_id': account.get('id')}
                    )

            await self.audit_logger.update_sync_status(
                sync_type='warmup',
                workspace_id=workspace_id,
                record_count=len(warmup_accounts)
            )

            # Post-step: ensure all connected inboxes have warmup enabled
            # Reuses the same workspace-scoped client — no switch needed
            try:
                enabled = await self.auto_enable_warmup_for_connected(workspace_id, workspace_name)
                if enabled > 0:
                    print(f"  [{workspace_name}] Auto-enabled warmup for {enabled} inboxes")
            except Exception as e:
                print(f"  [{workspace_name}] [WARN] auto_enable_warmup failed: {e}")

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def update_warmup_status(
        self,
        workspace_id: UUID,
        account: Dict,
        period_start: str,
        period_end: str
    ):
        """
        Update warmup status for a single account.

        - Sets warmup_enabled based on API response
        - Sets warmup_started_at on first warmup detection
        - Sets warmup_stopped_at when warmup is disabled
        - Creates warmup snapshot
        """
        eb_id = str(account.get('id', ''))
        email = account.get('email', '').lower().strip()

        # Get warmup status from EmailBison
        eb_warmup_enabled = account.get('warmup_enabled', False)

        # Find existing local account
        existing = await self.db.fetchrow("""
            SELECT id, warmup_enabled, warmup_started_at
            FROM sender_accounts
            WHERE emailbison_account_id = $1
            AND workspace_id = $2
        """, eb_id, workspace_id)

        if not existing:
            # Account not found locally, skip (will be synced by account sync)
            return

        sender_account_id = existing['id']
        existing_warmup_enabled = existing['warmup_enabled'] or False
        existing_warmup_started_at = existing['warmup_started_at']

        now = datetime.now(timezone.utc)

        # Determine warmup lifecycle changes
        warmup_started_at = existing_warmup_started_at
        warmup_stopped_at = None

        # Detect warmup start
        if eb_warmup_enabled and not existing_warmup_started_at:
            # Use EB created_at as warmup start (accurate for pre-warmed workspaces)
            # Falls back to NOW() if created_at not available
            eb_created_str = account.get('created_at')
            if eb_created_str:
                try:
                    warmup_started_at = datetime.fromisoformat(eb_created_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    warmup_started_at = now
            else:
                warmup_started_at = now

        # Detect warmup stop
        if not eb_warmup_enabled and existing_warmup_enabled:
            warmup_stopped_at = now

        # Update sender_accounts with warmup status
        await self.db.execute("""
            UPDATE sender_accounts
            SET
                warmup_enabled = $2,
                warmup_started_at = COALESCE($3, warmup_started_at),
                warmup_stopped_at = CASE
                    WHEN $4::timestamptz IS NOT NULL THEN $4
                    ELSE warmup_stopped_at
                END,
                updated_at = NOW()
            WHERE id = $1
        """,
            sender_account_id,
            eb_warmup_enabled,
            warmup_started_at,
            warmup_stopped_at
        )

        # Create warmup snapshot
        await self.create_warmup_snapshot(
            sender_account_id=sender_account_id,
            account=account,
            period_start=period_start,
            period_end=period_end
        )

    async def create_warmup_snapshot(
        self,
        sender_account_id: UUID,
        account: Dict,
        period_start: str,
        period_end: str
    ):
        """Create a warmup statistics snapshot record."""
        now = datetime.now(timezone.utc)

        # Extract warmup metrics from EmailBison API response
        warmup_enabled = account.get('warmup_enabled', False)
        warmup_score = account.get('warmup_score', 0) or 0
        warmup_emails_sent = account.get('warmup_emails_sent', 0) or 0
        warmup_replies_received = account.get('warmup_replies_received', 0) or 0
        warmup_bounces_received = account.get('warmup_bounces_received_count', 0) or 0
        warmup_bounces_caused = account.get('warmup_bounces_caused_count', 0) or 0
        warmup_emails_saved_from_spam = account.get('warmup_emails_saved_from_spam', 0) or 0
        status = account.get('status', 'unknown')

        # Parse period dates
        try:
            period_start_dt = datetime.strptime(period_start, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            period_end_dt = datetime.strptime(period_end, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            period_start_dt = now - timedelta(days=7)
            period_end_dt = now

        await self.db.execute("""
            INSERT INTO sender_warmup_snapshots (
                sender_account_id,
                snapshot_timestamp,
                period_start,
                period_end,
                warmup_enabled,
                warmup_score,
                warmup_emails_sent,
                warmup_replies_received,
                warmup_bounces_received_count,
                warmup_bounces_caused_count,
                warmup_emails_saved_from_spam,
                sender_email_status
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """,
            sender_account_id,
            now,
            period_start_dt,
            period_end_dt,
            warmup_enabled,
            warmup_score,
            warmup_emails_sent,
            warmup_replies_received,
            warmup_bounces_received,
            warmup_bounces_caused,
            warmup_emails_saved_from_spam,
            status
        )

    async def auto_enable_warmup_for_connected(
        self,
        workspace_id: UUID,
        workspace_name: str = None
    ) -> int:
        """
        Find connected inboxes without warmup and enable it.

        Per user requirement: "We should always try to keep connected inboxes in warming."

        The EmailBisonClient (self.client) must already be scoped to this workspace.
        No switch_workspace() call is made — the caller is responsible for passing a
        correctly-scoped client.  Invoked as a post-step from sync_workspace_warmup().

        Args:
            workspace_id: Internal workspace UUID for DB queries.
            workspace_name: Display name for logging (optional, queried if not provided).

        Returns:
            Count of inboxes that had warmup enabled
        """
        # Resolve workspace name for logging if not passed in
        if not workspace_name:
            row = await self.db.fetchrow(
                "SELECT workspace_name FROM workspaces WHERE id = $1", workspace_id
            )
            workspace_name = row['workspace_name'] if row else str(workspace_id)

        # Find connected inboxes without warmup enabled.
        #
        # CRITICAL: `inbox_state = 'live'` filter is Plan F's missing piece
        # (discovered 2026-05-14). Without it this query re-enabled warmup
        # on dead-but-still-Connected inboxes — the kill_queued_handler
        # would set warmup_enabled=FALSE + enqueue a warmup_disable event
        # (which the Tier 2 worker drained against EB), and then the very
        # next sync_warmup cycle would re-enable EB-side warmup on the
        # dead inbox, undoing the kill's intent. Result: 672 dead inboxes
        # still warming on EB (some 90 days post-kill), bleeding
        # reputation onto domain neighbors — the original 2026-05-08 audit
        # finding that Plan F was supposed to fix.
        accounts = await self.db.fetch("""
            SELECT id, email_address, emailbison_account_id
            FROM sender_accounts
            WHERE workspace_id = $1
            AND status = 'Connected'
            AND inbox_state = 'live'
            AND (warmup_enabled = FALSE OR warmup_enabled IS NULL)
            AND emailbison_account_id IS NOT NULL
            AND is_active = TRUE
        """, workspace_id)

        if not accounts:
            return 0

        print(f"  [{workspace_name}] Found {len(accounts)} connected inboxes without warmup")

        # Enable warmup in batches
        batch_size = 50
        total_enabled = 0

        for i in range(0, len(accounts), batch_size):
            batch = accounts[i:i + batch_size]
            eb_ids = [int(a['emailbison_account_id']) for a in batch]

            try:
                await self.client.enable_warmup(eb_ids)
                total_enabled += len(batch)

                # Update local records
                for account in batch:
                    await self.db.execute("""
                        UPDATE sender_accounts
                        SET
                            warmup_enabled = TRUE,
                            warmup_started_at = COALESCE(warmup_started_at, NOW()),
                            updated_at = NOW()
                        WHERE id = $1
                    """, account['id'])

                print(f"    Enabled warmup for {len(batch)} inboxes")

            except EmailBisonAPIError as e:
                print(f"    [WARN] Failed to enable warmup for batch: {e}")

        return total_enabled

    async def get_warmup_progress(self, sender_account_id: UUID) -> Optional[int]:
        """
        Calculate warmup progress as a percentage (0-100).

        Standard warmup takes 30 days. Progress = min(100, days_warming / 30 * 100)
        """
        account = await self.db.fetchrow("""
            SELECT warmup_started_at, warmup_enabled
            FROM sender_accounts
            WHERE id = $1
        """, sender_account_id)

        if not account or not account['warmup_started_at']:
            return None

        if not account['warmup_enabled']:
            return None

        days_warming = (datetime.now(timezone.utc) - account['warmup_started_at']).days
        progress = min(100, int((days_warming / 30) * 100))

        return progress
