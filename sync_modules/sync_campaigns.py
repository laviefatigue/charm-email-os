"""
Campaign & Metrics Sync Module

Synchronizes campaigns and creates snapshots from EmailBison.
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

    async def sync_all_workspaces(self) -> List[SyncResult]:
        """Sync campaigns for all active workspaces."""
        results = []

        workspaces = await self.db.fetch("""
            SELECT id, workspace_name, emailbison_workspace_id
            FROM workspaces
            WHERE emailbison_workspace_id IS NOT NULL
            AND is_active = TRUE
        """)

        print(f"[CampaignSync] Syncing {len(workspaces)} workspaces")

        for ws in workspaces:
            try:
                result = await self.sync_workspace(
                    workspace_id=ws['id'],
                    workspace_name=ws['workspace_name'],
                    emailbison_workspace_id=int(ws['emailbison_workspace_id'])
                )
                results.append(result)

                if result.status == 'failed' and self.alerter:
                    await self.alerter.alert_sync_failure(
                        module='campaigns',
                        error=result.error_message or 'Unknown error',
                        workspace=ws['workspace_name'],
                        records_processed=result.records_processed
                    )

            except Exception as e:
                print(f"[CampaignSync] Error syncing {ws['workspace_name']}: {e}")

        # After syncing all campaigns, sync campaign-inbox assignments
        try:
            await self.sync_all_campaign_inbox_assignments()
        except Exception as e:
            print(f"[CampaignSync] Error syncing campaign-inbox assignments: {e}")

        return results

    async def sync_workspace(
        self,
        workspace_id: UUID,
        workspace_name: str,
        emailbison_workspace_id: int
    ) -> SyncResult:
        """Sync campaigns for a single workspace."""
        audit = await self.audit_logger.start_audit(
            sync_type='campaigns',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Switch to workspace context
            if not await self.client.switch_workspace(emailbison_workspace_id):
                return await audit.fail(Exception(f"Failed to switch to workspace {workspace_name}"))

            # Fetch all campaigns
            campaigns = await self.client.get_all_campaigns()
            print(f"  [{workspace_name}] Found {len(campaigns)} campaigns")

            for campaign in campaigns:
                audit.increment_processed()

                try:
                    # Upsert campaign record
                    local_campaign_id = await self.upsert_campaign(workspace_id, campaign)

                    # CRITICAL: Switch workspace before detail fetch
                    await self.client.switch_workspace(emailbison_workspace_id)

                    # Fetch detailed metrics
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
                status,
                first_seen_at,
                last_seen_at
            ) VALUES ($1, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (workspace_id, emailbison_campaign_id) DO UPDATE SET
                campaign_name = EXCLUDED.campaign_name,
                status = EXCLUDED.status,
                last_seen_at = NOW(),
                updated_at = NOW()
            RETURNING id
        """, workspace_id, eb_id, name, status)

        return result['id']

    async def create_snapshot(self, campaign_id: UUID, details: Dict):
        """Create a metrics snapshot for a campaign."""
        now = datetime.now(timezone.utc)

        # Extract metrics from campaign details
        emails_sent = int(details.get('emails_sent', 0) or 0)
        total_leads = int(details.get('total_leads', 0) or 0)
        contacted = int(details.get('total_leads_contacted', 0) or 0)
        opens = int(details.get('unique_opens', 0) or 0)
        replies = int(details.get('unique_replies', details.get('replied', 0)) or 0)
        bounced = int(details.get('bounced', 0) or 0)
        interested = int(details.get('interested', 0) or 0)

        # Calculate rates
        open_rate = (opens / contacted * 100) if contacted > 0 else 0
        reply_rate = (replies / contacted * 100) if contacted > 0 else 0
        bounce_rate = (bounced / emails_sent * 100) if emails_sent > 0 else 0

        # Period must have end > start (database constraint)
        period_start = now - timedelta(days=1)
        period_end = now

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
                open_rate,
                reply_rate,
                bounce_rate,
                active_senders
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, 0)
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
            round(open_rate, 2),
            round(reply_rate, 2),
            round(bounce_rate, 2)
        )

    async def sync_all_campaign_inbox_assignments(self) -> int:
        """
        Sync campaign-inbox associations by querying each inbox's campaigns.

        Uses the API: GET /api/sender-emails/{id}/campaigns
        This is the authoritative source for which inboxes are assigned to campaigns.

        Returns:
            Number of campaign-inbox associations synced
        """
        print("[CampaignSync] Syncing campaign-inbox assignments...")

        # Get all sender accounts with EmailBison IDs
        accounts = await self.db.fetch("""
            SELECT sa.id, sa.email_address, sa.emailbison_account_id,
                   w.emailbison_workspace_id, w.workspace_name
            FROM sender_accounts sa
            JOIN workspaces w ON sa.workspace_id = w.id
            WHERE sa.emailbison_account_id IS NOT NULL
            AND sa.is_active = TRUE
            AND w.emailbison_workspace_id IS NOT NULL
            AND w.is_active = TRUE
            ORDER BY w.emailbison_workspace_id
        """)

        print(f"  Found {len(accounts)} active sender accounts")

        total_synced = 0
        current_workspace_id = None

        for account in accounts:
            eb_account_id = int(account['emailbison_account_id'])
            eb_workspace_id = int(account['emailbison_workspace_id'])
            sender_account_id = account['id']

            # Switch workspace if needed
            if current_workspace_id != eb_workspace_id:
                if not await self.client.switch_workspace(eb_workspace_id):
                    print(f"    [WARN] Failed to switch to workspace {account['workspace_name']}")
                    continue
                current_workspace_id = eb_workspace_id

            # Get campaigns for this inbox
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
            WHERE ec.status IN ('active', 'running', 'sending')
            AND w.emailbison_workspace_id IS NOT NULL
            AND w.is_active = TRUE
        """

        if workspace_id:
            query += " AND ec.workspace_id = $1"
            return await self.db.fetch(query, workspace_id)
        else:
            return await self.db.fetch(query)
