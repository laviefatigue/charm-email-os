"""
Lifecycle Tag Sync Module

Manages inbox lifecycle tags in EmailBison to control campaign assignment:
- 'incubating' - Inbox in warmup period (< 21 days from warmup_started_at)
- 'live' - Inbox graduated and available for campaigns (21+ days warmup)
- 'flagged_{trigger}' - Applied by kill_processor.py when inbox is killed

Tag Transitions:
1. When warmup_started_at is set -> add 'incubating' tag
2. When 21 days warmup complete -> remove 'incubating', add 'live'
3. When kill trigger fires -> remove 'live', add 'flagged_{trigger}' (handled by kill_processor)

The team uses these tags in EmailBison to filter which inboxes can be assigned to campaigns.
Only inboxes with the 'live' tag should be used for campaign sending.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Tag names used for lifecycle management
INCUBATING_TAG = 'incubating'
LIVE_TAG = 'live'
INCUBATION_DAYS = 21


class LifecycleTagSyncModule:
    """
    Manages inbox lifecycle tags in EmailBison.

    This module ensures EmailBison tags reflect the local database state:
    - Inboxes in incubation (< 21 days warmup) have 'incubating' tag
    - Graduated inboxes (21+ days warmup) have 'live' tag
    - Dead inboxes have neither (kill_processor handles flagged_* tags)

    The team uses these tags to control which inboxes can be assigned to campaigns.
    """

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
        """
        Sync lifecycle tags for all active workspaces.

        Returns:
            List of SyncResult for each workspace processed
        """
        results = []

        workspaces = await self.db.fetch("""
            SELECT id, workspace_name, emailbison_workspace_id
            FROM workspaces
            WHERE emailbison_workspace_id IS NOT NULL
            AND is_active = TRUE
        """)

        print(f"[LifecycleTagSync] Processing {len(workspaces)} workspaces")

        for ws in workspaces:
            try:
                result = await self.sync_workspace_tags(
                    workspace_id=ws['id'],
                    workspace_name=ws['workspace_name'],
                    emailbison_workspace_id=int(ws['emailbison_workspace_id'])
                )
                results.append(result)

                # Add delay between workspaces to avoid rate limiting
                await self.client.inter_batch_delay(1.0)

            except Exception as e:
                print(f"[LifecycleTagSync] Error syncing {ws['workspace_name']}: {e}")

        return results

    async def sync_workspace_tags(
        self,
        workspace_id: UUID,
        workspace_name: str,
        emailbison_workspace_id: int
    ) -> SyncResult:
        """
        Sync lifecycle tags for a single workspace.

        Handles:
        1. Graduate inboxes from 'incubating' to 'live' (21+ days warmup)
        2. Tag new warmup inboxes with 'incubating'
        3. Remove 'live' tag from dead inboxes (consistency check)

        Args:
            workspace_id: Our workspace UUID
            workspace_name: Workspace name for logging
            emailbison_workspace_id: EmailBison workspace ID

        Returns:
            SyncResult with counts of tags added/removed
        """
        audit = await self.audit_logger.start_audit(
            sync_type='lifecycle_tags',
            workspace_id=workspace_id,
            metadata={'workspace_name': workspace_name}
        )

        try:
            # Switch to workspace context
            if not await self.client.switch_workspace(emailbison_workspace_id):
                return await audit.fail(Exception(f"Failed to switch to workspace {workspace_name}"))

            # Get or create the lifecycle tags
            incubating_tag = await self.client.get_or_create_tag(INCUBATING_TAG)
            live_tag = await self.client.get_or_create_tag(LIVE_TAG)

            incubating_tag_id = incubating_tag.get('id')
            live_tag_id = live_tag.get('id')

            if not incubating_tag_id or not live_tag_id:
                return await audit.fail(Exception("Failed to get/create lifecycle tags"))

            # 1. Graduate inboxes: incubating -> live (21+ days warmup)
            graduated = await self._graduate_mature_inboxes(
                workspace_id=workspace_id,
                incubating_tag_id=incubating_tag_id,
                live_tag_id=live_tag_id,
                audit=audit
            )

            # 2. Tag new warmup inboxes with 'incubating'
            new_incubating = await self._tag_new_warmup_inboxes(
                workspace_id=workspace_id,
                incubating_tag_id=incubating_tag_id,
                audit=audit
            )

            # 3. Remove 'live' tag from dead inboxes (consistency)
            cleaned = await self._remove_live_from_dead(
                workspace_id=workspace_id,
                live_tag_id=live_tag_id,
                audit=audit
            )

            if graduated > 0 or new_incubating > 0 or cleaned > 0:
                print(f"  [{workspace_name}] Graduated: {graduated}, New incubating: {new_incubating}, Cleaned: {cleaned}")

            return await audit.complete(metadata={
                'graduated': graduated,
                'new_incubating': new_incubating,
                'live_removed_dead': cleaned
            })

        except Exception as e:
            return await audit.fail(e)

    async def _graduate_mature_inboxes(
        self,
        workspace_id: UUID,
        incubating_tag_id: int,
        live_tag_id: int,
        audit
    ) -> int:
        """
        Graduate inboxes from incubating to live after 21 days of warmup.

        Finds inboxes that:
        - Have warmup_started_at >= 21 days ago
        - Are live (inbox_state = 'live')
        - Are still marked as incubating locally

        Returns:
            Number of inboxes graduated
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=INCUBATION_DAYS)

        # Find inboxes ready to graduate
        ready_to_graduate = await self.db.fetch("""
            SELECT
                id,
                email_address,
                emailbison_account_id,
                warmup_started_at
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'live'
            AND warmup_started_at IS NOT NULL
            AND warmup_started_at <= $2
            AND inventory_lifecycle_status = 'incubating'
            AND emailbison_account_id IS NOT NULL
        """, workspace_id, cutoff)

        graduated_count = 0

        for inbox in ready_to_graduate:
            audit.increment_processed()
            eb_account_id = int(inbox['emailbison_account_id'])

            try:
                # Remove 'incubating' tag
                try:
                    await self.client.untag_inbox(eb_account_id, incubating_tag_id)
                except EmailBisonAPIError as e:
                    print(f"    [WARN] Failed to remove 'incubating' tag from inbox {eb_account_id} ({inbox['email_address']}): {e}")

                # Add 'live' tag
                await self.client.tag_inbox(eb_account_id, live_tag_id)

                # Update local status
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inventory_lifecycle_status = 'active',
                        updated_at = NOW()
                    WHERE id = $1
                """, inbox['id'])

                graduated_count += 1
                audit.increment_updated()

                print(f"    [GRADUATE] {inbox['email_address']} - incubating -> live")

            except EmailBisonAPIError as e:
                audit.add_error(
                    record_id=inbox['email_address'],
                    error=f"Failed to graduate: {e}"
                )

        return graduated_count

    async def _tag_new_warmup_inboxes(
        self,
        workspace_id: UUID,
        incubating_tag_id: int,
        audit
    ) -> int:
        """
        Tag new warmup inboxes with 'incubating'.

        Finds inboxes that:
        - Have warmup_started_at set (recently started warming)
        - Are live
        - Have warmup_started_at < 21 days ago
        - Don't have lifecycle_status set to 'incubating' yet

        Returns:
            Number of inboxes tagged
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=INCUBATION_DAYS)

        # Find newly warming inboxes that need 'incubating' tag
        new_warmup = await self.db.fetch("""
            SELECT
                id,
                email_address,
                emailbison_account_id,
                warmup_started_at
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'live'
            AND warmup_started_at IS NOT NULL
            AND warmup_started_at > $2
            AND emailbison_account_id IS NOT NULL
            AND (inventory_lifecycle_status IS NULL OR inventory_lifecycle_status != 'incubating')
        """, workspace_id, cutoff)

        tagged_count = 0

        for inbox in new_warmup:
            audit.increment_processed()
            eb_account_id = int(inbox['emailbison_account_id'])

            try:
                # Add 'incubating' tag
                await self.client.tag_inbox(eb_account_id, incubating_tag_id)

                # Update local status
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inventory_lifecycle_status = 'incubating',
                        updated_at = NOW()
                    WHERE id = $1
                """, inbox['id'])

                tagged_count += 1
                audit.increment_updated()

                print(f"    [TAG] {inbox['email_address']} - added 'incubating' tag")

            except EmailBisonAPIError as e:
                audit.add_error(
                    record_id=inbox['email_address'],
                    error=f"Failed to tag: {e}"
                )

        return tagged_count

    async def _remove_live_from_dead(
        self,
        workspace_id: UUID,
        live_tag_id: int,
        audit
    ) -> int:
        """
        Remove 'live' tag from dead inboxes (consistency check).

        This catches any edge cases where an inbox was killed but still has
        the 'live' tag. The kill_processor should handle this, but this
        provides a safety net.

        Returns:
            Number of tags removed
        """
        # Find dead inboxes that might still have 'live' tag
        dead_with_live = await self.db.fetch("""
            SELECT
                id,
                email_address,
                emailbison_account_id
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'dead'
            AND emailbison_account_id IS NOT NULL
            AND inventory_lifecycle_status = 'active'
        """, workspace_id)

        cleaned_count = 0

        for inbox in dead_with_live:
            audit.increment_processed()
            eb_account_id = int(inbox['emailbison_account_id'])

            try:
                # Try to remove 'live' tag
                await self.client.untag_inbox(eb_account_id, live_tag_id)

                # Update local status
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inventory_lifecycle_status = 'dead',
                        updated_at = NOW()
                    WHERE id = $1
                """, inbox['id'])

                cleaned_count += 1
                audit.increment_updated()

                print(f"    [CLEAN] {inbox['email_address']} - removed 'live' tag (dead inbox)")

            except EmailBisonAPIError:
                # Tag may not exist, that's fine
                pass

        return cleaned_count

    async def get_lifecycle_summary(self, workspace_id: UUID) -> Dict:
        """
        Get summary of lifecycle tag states for a workspace.

        Returns:
            Dict with counts of inboxes in each lifecycle state
        """
        stats = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE inbox_state = 'live' AND (warmup_started_at IS NULL OR warmup_started_at > NOW() - INTERVAL '21 days')) as incubating,
                COUNT(*) FILTER (WHERE inbox_state = 'live' AND warmup_started_at IS NOT NULL AND warmup_started_at <= NOW() - INTERVAL '21 days') as live,
                COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
                COUNT(*) as total
            FROM sender_accounts
            WHERE workspace_id = $1
            AND is_active = TRUE
        """, workspace_id)

        return {
            'incubating': stats['incubating'] or 0,
            'live': stats['live'] or 0,
            'dead': stats['dead'] or 0,
            'total': stats['total'] or 0
        }
