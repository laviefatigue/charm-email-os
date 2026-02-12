"""
Account & Domain Sync Module

Synchronizes sender accounts and domains from EmailBison.
"""
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, AuditContext, SyncResult
from .slack_alerter import SlackAlerter


# ESP mapping from EmailBison provider names to our enum
ESP_MAP = {
    'Google': 'gmail',
    'Microsoft': 'microsoft',
    'Yahoo': 'yahoo',
    'SMTP': 'other',
    'Other': 'other'
}


class AccountSyncModule:
    """Synchronizes sender accounts and domains from EmailBison."""

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
        """Sync accounts for all active workspaces."""
        results = []

        # Get all workspaces with EmailBison IDs
        workspaces = await self.db.fetch("""
            SELECT id, workspace_name, emailbison_workspace_id
            FROM workspaces
            WHERE emailbison_workspace_id IS NOT NULL
            AND is_active = TRUE
        """)

        print(f"[AccountSync] Syncing {len(workspaces)} workspaces")

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
                        module='accounts',
                        error=result.error_message or 'Unknown error',
                        workspace=ws['workspace_name'],
                        records_processed=result.records_processed
                    )

            except Exception as e:
                print(f"[AccountSync] Error syncing {ws['workspace_name']}: {e}")
                # Continue with other workspaces

        # Sync domains after accounts
        await self.sync_all_domains()

        return results

    async def sync_workspace(
        self,
        workspace_id: UUID,
        workspace_name: str,
        emailbison_workspace_id: int
    ) -> SyncResult:
        """Sync accounts for a single workspace."""
        audit = await self.audit_logger.start_audit(
            sync_type='accounts',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Switch to workspace context
            if not await self.client.switch_workspace(emailbison_workspace_id):
                return await audit.fail(Exception(f"Failed to switch to workspace {workspace_name}"))

            # Fetch all accounts from EmailBison
            accounts = await self.client.get_all_sender_accounts()
            print(f"  [{workspace_name}] Found {len(accounts)} accounts in EmailBison")

            # Track existing accounts for stale detection
            existing_eb_ids = set()

            # Upsert each account
            for account in accounts:
                audit.increment_processed()

                try:
                    created = await self.upsert_account(workspace_id, account)
                    if created:
                        audit.increment_created()
                    else:
                        audit.increment_updated()

                    eb_id = account.get('id')
                    if eb_id:
                        existing_eb_ids.add(str(eb_id))

                except Exception as e:
                    audit.add_error(
                        record_id=account.get('email'),
                        error=str(e),
                        details={'emailbison_id': account.get('id')}
                    )

            # Mark stale accounts (in our DB but not in EmailBison)
            await self.mark_stale_accounts(workspace_id, existing_eb_ids)

            # Update sync status for incremental syncing
            await self.audit_logger.update_sync_status(
                sync_type='accounts',
                workspace_id=workspace_id,
                record_count=len(accounts)
            )

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def upsert_account(self, workspace_id: UUID, account: Dict) -> bool:
        """
        Upsert a sender account from EmailBison data.

        Returns:
            True if created, False if updated
        """
        email = account.get('email', '').lower().strip()
        if not email:
            raise ValueError("Account missing email address")

        # Map EmailBison fields to our schema
        eb_id = str(account.get('id', ''))
        status = account.get('status') or account.get('connection_status') or 'Unknown'
        provider = account.get('provider') or ''

        # Determine inbox state
        inbox_state = 'dead' if status in ('Not connected', 'Disconnected', 'Disabled') else 'live'

        # Get ESP
        esp = ESP_MAP.get(provider, 'other')

        # Get tags for provider detection if no provider
        if not provider:
            tags = account.get('tags', [])
            for tag in tags:
                tag_name = tag.get('name', '').lower()
                if 'google' in tag_name or 'gmail' in tag_name:
                    esp = 'gmail'
                    break
                elif 'microsoft' in tag_name or 'outlook' in tag_name:
                    esp = 'microsoft'
                    break

        # Extract metrics
        health_score = account.get('health_score')
        bounce_rate = account.get('bounce_rate', 0) or 0

        result = await self.db.fetchrow("""
            INSERT INTO sender_accounts (
                workspace_id,
                email_address,
                emailbison_account_id,
                display_name,
                status,
                inbox_state,
                esp,
                health_score,
                bounce_rate_7d,
                is_active,
                first_seen_at,
                last_seen_at,
                last_synced_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW(), NOW())
            ON CONFLICT (workspace_id, email_address) DO UPDATE SET
                emailbison_account_id = EXCLUDED.emailbison_account_id,
                display_name = COALESCE(EXCLUDED.display_name, sender_accounts.display_name),
                status = EXCLUDED.status,
                inbox_state = CASE
                    WHEN sender_accounts.inbox_state = 'dead' THEN 'dead'
                    ELSE EXCLUDED.inbox_state
                END,
                esp = COALESCE(EXCLUDED.esp, sender_accounts.esp),
                health_score = EXCLUDED.health_score,
                bounce_rate_7d = EXCLUDED.bounce_rate_7d,
                is_active = EXCLUDED.is_active,
                last_seen_at = NOW(),
                last_synced_at = NOW(),
                updated_at = NOW()
            RETURNING (xmax = 0) as created
        """,
            workspace_id,
            email,
            eb_id,
            account.get('name'),
            status,
            inbox_state,
            esp,
            health_score,
            bounce_rate,
            inbox_state == 'live'
        )

        return result['created'] if result else False

    async def mark_stale_accounts(self, workspace_id: UUID, active_eb_ids: set):
        """Mark accounts that are no longer in EmailBison as inactive."""
        if not active_eb_ids:
            return

        # Find accounts in our DB but not in EmailBison
        stale = await self.db.fetch("""
            UPDATE sender_accounts
            SET
                is_active = FALSE,
                updated_at = NOW()
            WHERE workspace_id = $1
            AND emailbison_account_id IS NOT NULL
            AND emailbison_account_id != ALL($2::text[])
            AND is_active = TRUE
            RETURNING email_address
        """, workspace_id, list(active_eb_ids))

        if stale:
            print(f"    Marked {len(stale)} stale accounts as inactive")

    async def sync_all_domains(self):
        """
        Sync domains by creating missing ones from sender_accounts.
        Domains are derived from email addresses, not fetched from EmailBison.
        """
        print("[AccountSync] Syncing domains...")

        # Create missing domains
        created = await self.db.execute("""
            INSERT INTO domains (workspace_id, domain_name, approval_status, created_at, updated_at)
            SELECT DISTINCT
                sa.workspace_id,
                SPLIT_PART(sa.email_address, '@', 2),
                'legacy',
                NOW(),
                NOW()
            FROM sender_accounts sa
            WHERE SPLIT_PART(sa.email_address, '@', 2) != ''
            AND NOT EXISTS (
                SELECT 1 FROM domains d
                WHERE d.workspace_id = sa.workspace_id
                AND d.domain_name = SPLIT_PART(sa.email_address, '@', 2)
            )
        """)
        print(f"  Created domains: {created}")

        # Link sender_accounts to domains
        linked = await self.db.execute("""
            UPDATE sender_accounts sa
            SET domain_id = d.id, updated_at = NOW()
            FROM domains d
            WHERE sa.workspace_id = d.workspace_id
            AND SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.domain_id IS NULL
        """)
        print(f"  Linked accounts to domains: {linked}")

        # Update domain health scores (average of inbox health scores)
        await self.db.execute("""
            UPDATE domains d
            SET
                latest_health_score = sub.avg_score,
                updated_at = NOW()
            FROM (
                SELECT
                    domain_id,
                    AVG(health_score)::INTEGER as avg_score
                FROM sender_accounts
                WHERE domain_id IS NOT NULL
                AND health_score IS NOT NULL
                GROUP BY domain_id
            ) sub
            WHERE d.id = sub.domain_id
        """)
