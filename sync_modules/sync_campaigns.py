"""
Campaign & Metrics Sync Module

Synchronizes campaigns and creates snapshots from EmailBison.

Architecture (workspace-concurrent model):
    This module is designed for per-workspace parallel execution.
    It is called by WorkspaceSyncQueue._dispatch() with a workspace-scoped
    EmailBisonClient already initialised with the per-workspace API key.

    Contract:
        - Caller passes a client already scoped to the target workspace.
        - NO switch_workspace() calls anywhere in this module.
        - sync_workspace(workspace_id, workspace_name) — one workspace, one client.
        - sync_campaign_inbox_assignments(workspace_id) — filters accounts to one
          workspace and makes API calls using the scoped client.  Called as a
          post-hook by WorkspaceSyncQueue._dispatch() after campaigns completes.

    Removed (old sequential model):
        - sync_all_workspaces()              — replaced by WorkspaceSyncQueue scheduler
        - emailbison_workspace_id param      — no longer needed; client is pre-scoped
        - switch_workspace() calls           — eliminated by workspace-scoped API keys
        - sync_all_campaign_inbox_assignments() — replaced by sync_campaign_inbox_assignments(workspace_id)

IMPORTANT: sending_started_at Lifecycle Tracking
----------------------------------------------
This module sets `sender_accounts.sending_started_at` when an inbox is
first assigned to a campaign. This timestamp is critical for:

1. Kill trigger lifecycle analysis - distinguishes kills during warmup
   vs kills during active campaign sending
2. Data integrity - spam complaints only count if from campaign activity
3. Reporting - accurate lifecycle stage categorization

sending_started_at is set on first campaign_inboxes insert, NOT on warmup
graduation (which only sets inventory_lifecycle_status='active').

See: Migration 079_backfill_sending_started_at.sql for backfill logic
See: /api/health/analysis/kill-trigger-lifecycle for analysis endpoint
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, AuditContext, SyncResult
from .slack_alerter import SlackAlerter


class CampaignSyncModule:
    """Synchronizes campaigns and metrics from EmailBison."""

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

    async def sync_workspace(
        self,
        workspace_id: UUID,
        workspace_name: str,
    ) -> SyncResult:
        """
        Sync campaigns for a single workspace.

        The EmailBisonClient (self.client) must already be scoped to this
        workspace via its API key.  No switch_workspace() call is made here.
        Called by WorkspaceSyncQueue._dispatch() with a per-workspace client.

        Post-hook: WorkspaceSyncQueue calls sync_campaign_inbox_assignments()
        after this method completes successfully.
        """
        audit = await self.audit_logger.start_audit(
            sync_type='campaigns',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Fetch all campaigns
            campaigns = await self.client.get_all_campaigns()
            print(f"  [{workspace_name}] Found {len(campaigns)} campaigns")

            for campaign in campaigns:
                audit.increment_processed()

                try:
                    # Upsert campaign record
                    local_campaign_id = await self.upsert_campaign(workspace_id, campaign)

                    # Fetch detailed metrics — no workspace switch needed, client is already scoped
                    try:
                        details = await self.client.get_campaign_details(campaign['id'])
                        # Unwrap data if nested
                        if 'data' in details:
                            details = details['data']
                        await self.create_snapshot(local_campaign_id, details)
                        audit.increment_updated()
                    except EmailBisonAPIError as e:
                        if e.status_code == 403:
                            # Permission error, skip details but keep campaign
                            audit.add_error(
                                record_id=campaign.get('name'),
                                error=f"Access denied for campaign details",
                                details={'campaign_id': campaign['id']}
                            )
                        else:
                            raise

                except Exception as e:
                    audit.add_error(
                        record_id=campaign.get('name'),
                        error=str(e),
                        details={'emailbison_id': campaign.get('id')}
                    )

            await self.audit_logger.update_sync_status(
                sync_type='campaigns',
                workspace_id=workspace_id,
                record_count=len(campaigns)
            )

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def upsert_campaign(self, workspace_id: UUID, campaign: Dict) -> UUID:
        """
        Upsert a campaign from EmailBison data.

        Returns:
            Local campaign UUID
        """
        eb_id = str(campaign.get('id', ''))
        name = campaign.get('name', 'Unnamed Campaign')
        status = campaign.get('status', 'unknown')

        result = await self.db.fetchrow("""
            INSERT INTO emailbison_campaigns (
                workspace_id,
                emailbison_campaign_id,
                campaign_name,
                campaign_status,
                first_seen_at,
                last_seen_at
            ) VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (workspace_id, emailbison_campaign_id) DO UPDATE SET
                campaign_name = EXCLUDED.campaign_name,
                campaign_status = EXCLUDED.campaign_status,
                last_seen_at = NOW(),
                updated_at = NOW()
            RETURNING id
        """, workspace_id, eb_id, name, status)

        return result['id']

    async def create_snapshot(self, campaign_id: UUID, details: Dict):
        """Create a metrics snapshot for a campaign and update main record."""
        from decimal import Decimal
        now = datetime.now(timezone.utc)

        # Extract metrics from campaign details
        # EB API returns some fields as strings (e.g. unique_opens = "0")
        # Force int() on all count fields to ensure consistent types for asyncpg
        emails_sent = int(details.get('emails_sent', 0) or 0)
        total_leads = int(details.get('total_leads', 0) or 0)
        contacted = int(details.get('total_leads_contacted', 0) or 0)
        opens = int(details.get('unique_opens', 0) or 0)
        replies = int(details.get('unique_replies', details.get('replied', 0)) or 0)
        bounced = int(details.get('bounced', 0) or 0)
        interested = int(details.get('interested', 0) or 0)
        unsubscribed = int(details.get('unsubscribed', 0) or 0)

        # Calculate rates using Decimal for consistent asyncpg numeric type inference.
        # Python's round() returns int when input is 0, causing asyncpg "inconsistent types"
        # error between float and int for numeric columns.
        open_rate = Decimal(str(opens / contacted * 100)) if contacted > 0 else Decimal('0')
        reply_rate = Decimal(str(replies / contacted * 100)) if contacted > 0 else Decimal('0')
        bounce_rate = Decimal(str(bounced / emails_sent)) if emails_sent > 0 else Decimal('0')
        completion_pct = Decimal(str(contacted / total_leads * 100)) if total_leads > 0 else Decimal('0')

        # Period must have end > start (database constraint)
        period_start = now - timedelta(days=1)
        period_end = now

        # Update main campaign record with latest metrics
        await self.db.execute("""
            UPDATE emailbison_campaigns
            SET
                total_leads = $2,
                total_leads_contacted = $3,
                emails_sent = $4,
                bounces = $5,
                bounce_rate = $6,
                completion_percentage = $7,
                last_snapshot_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
        """,
            campaign_id,
            total_leads,
            contacted,
            emails_sent,
            bounced,
            Decimal(str(round(float(bounce_rate), 4))),
            Decimal(str(round(float(completion_pct), 2)))
        )

        # Create snapshot for historical tracking
        interested_rate = Decimal(str(interested / contacted * 100)) if contacted > 0 else Decimal('0')
        unsubscribe_rate = Decimal(str(unsubscribed / contacted * 100)) if contacted > 0 else Decimal('0')

        await self.db.execute("""
            INSERT INTO campaign_snapshots (
                campaign_id,
                snapshot_timestamp,
                period_start,
                period_end,
                emails_sent,
                total_leads,
                total_leads_contacted,
                unique_opens,
                unique_replies,
                interested_replies,
                bounced,
                unsubscribed,
                open_rate,
                reply_rate,
                bounce_rate,
                interested_rate,
                unsubscribe_rate,
                active_senders
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, 0)
        """,
            campaign_id,
            now,
            period_start,
            period_end,
            emails_sent,
            total_leads,
            contacted,
            opens,
            replies,
            interested,
            bounced,
            unsubscribed,
            Decimal(str(round(float(open_rate), 2))),
            Decimal(str(round(float(reply_rate), 2))),
            Decimal(str(round(float(bounce_rate * 100), 2))),
            Decimal(str(round(float(interested_rate), 2))),
            Decimal(str(round(float(unsubscribe_rate), 2)))
        )

    async def sync_campaign_inbox_assignments(self, workspace_id: UUID) -> int:
        """
        Sync campaign-inbox associations for a single workspace.

        Uses the API: GET /api/sender-emails/{id}/campaigns
        This is the authoritative source for which inboxes are assigned to campaigns.

        The EmailBisonClient (self.client) must already be scoped to this workspace.
        No switch_workspace() calls are made.  Called as a post-hook by
        WorkspaceSyncQueue._dispatch() immediately after sync_workspace() completes.

        Args:
            workspace_id: Our internal workspace UUID.  Used to filter accounts
                          so only this workspace's inboxes are queried.

        Returns:
            Number of campaign-inbox associations synced
        """
        print(f"[CampaignSync] Syncing campaign-inbox assignments for workspace {workspace_id}...")

        # Get sender accounts for THIS workspace only
        accounts = await self.db.fetch("""
            SELECT sa.id, sa.email_address, sa.emailbison_account_id,
                   w.workspace_name
            FROM sender_accounts sa
            JOIN workspaces w ON sa.workspace_id = w.id
            WHERE sa.workspace_id = $1
            AND sa.emailbison_account_id IS NOT NULL
            AND sa.is_active = TRUE
            AND w.is_active = TRUE
        """, workspace_id)

        print(f"  Found {len(accounts)} active sender accounts in workspace")

        total_synced = 0

        for account in accounts:
            eb_account_id = int(account['emailbison_account_id'])
            sender_account_id = account['id']

            # Get campaigns for this inbox — client is already scoped to workspace
            try:
                campaigns = await self.client.get_sender_campaigns(eb_account_id)
            except EmailBisonAPIError as e:
                if e.status_code in (404, 403):
                    # Account may not exist or no access
                    continue
                raise

            if not campaigns:
                continue

            # Track which campaign IDs this inbox is assigned to
            current_campaign_ids = set()

            for campaign in campaigns:
                eb_campaign_id = str(campaign.get('id', ''))
                if not eb_campaign_id:
                    continue

                current_campaign_ids.add(eb_campaign_id)

                # Look up local campaign
                local_campaign = await self.db.fetchrow("""
                    SELECT id FROM emailbison_campaigns
                    WHERE emailbison_campaign_id = $1
                """, eb_campaign_id)

                campaign_id = local_campaign['id'] if local_campaign else None

                # Upsert campaign-inbox association
                await self.db.execute("""
                    INSERT INTO campaign_inboxes (
                        campaign_id,
                        sender_account_id,
                        emailbison_campaign_id,
                        emailbison_sender_id,
                        assigned_at,
                        is_active,
                        created_at,
                        updated_at
                    ) VALUES ($1, $2, $3, $4, NOW(), TRUE, NOW(), NOW())
                    ON CONFLICT (emailbison_campaign_id, emailbison_sender_id) DO UPDATE SET
                        campaign_id = COALESCE(EXCLUDED.campaign_id, campaign_inboxes.campaign_id),
                        sender_account_id = EXCLUDED.sender_account_id,
                        is_active = TRUE,
                        removed_at = NULL,
                        updated_at = NOW()
                """,
                    campaign_id,
                    sender_account_id,
                    eb_campaign_id,
                    eb_account_id  # Pass as integer
                )

                # Set sending_started_at on first campaign assignment
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET sending_started_at = NOW()
                    WHERE id = $1
                    AND sending_started_at IS NULL
                """, sender_account_id)

                total_synced += 1

            # Mark campaigns this inbox is no longer assigned to as inactive
            if current_campaign_ids:
                await self.db.execute("""
                    UPDATE campaign_inboxes
                    SET
                        is_active = FALSE,
                        removed_at = NOW(),
                        updated_at = NOW()
                    WHERE emailbison_sender_id = $1
                    AND emailbison_campaign_id != ALL($2::text[])
                    AND is_active = TRUE
                """, eb_account_id, list(current_campaign_ids))  # Pass as integer

        print(f"  Synced {total_synced} campaign-inbox assignments")
        return total_synced

    async def get_active_campaigns(self, workspace_id: UUID = None) -> List[Dict]:
        """Get campaigns that should be checked for events."""
        query = """
            SELECT
                ec.id,
                ec.emailbison_campaign_id,
                ec.campaign_name,
                ec.workspace_id,
                w.emailbison_workspace_id,
                w.workspace_name
            FROM emailbison_campaigns ec
            JOIN workspaces w ON ec.workspace_id = w.id
            WHERE ec.campaign_status IN ('active', 'running', 'sending')
            AND w.emailbison_workspace_id IS NOT NULL
            AND w.is_active = TRUE
        """

        if workspace_id:
            query += " AND ec.workspace_id = $1"
            return await self.db.fetch(query, workspace_id)
        else:
            return await self.db.fetch(query)
