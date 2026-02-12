"""
Kill Queue Processor

Processes inboxes queued for deletion:
1. Tag inbox in EmailBison (24hr queue)
2. Wait 24 hours (don't disrupt active campaigns)
3. Delete from EmailBison and mark dead locally
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from uuid import UUID
import asyncpg

from .emailbison_client import EmailBisonClient, EmailBisonAPIError
from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


class KillProcessor:
    """Processes the kill queue with 24hr tagging before deletion."""

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

    async def process_queue(self) -> SyncResult:
        """
        Process the kill queue:
        1. Tag pending items (24hr wait starts)
        2. Delete items past 24hr wait
        """
        audit = await self.audit_logger.start_audit(
            sync_type='kill_queue',
            metadata={'scope': 'process_all'}
        )

        try:
            # Step 1: Tag pending items
            tagged_count = await self.tag_pending_items(audit)

            # Step 2: Delete items past 24hr
            deleted_count = await self.delete_ready_items(audit)

            print(f"[KillProcessor] Tagged: {tagged_count}, Deleted: {deleted_count}")

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def tag_pending_items(self, audit) -> int:
        """Tag pending kill queue items in EmailBison."""
        pending = await self.db.fetch("""
            SELECT
                kq.id,
                kq.inbox_id,
                kq.workspace_id,
                kq.trigger_type,
                sa.email_address,
                sa.emailbison_account_id,
                w.emailbison_workspace_id,
                w.workspace_name
            FROM kill_queue kq
            JOIN sender_accounts sa ON kq.inbox_id = sa.id
            JOIN workspaces w ON kq.workspace_id = w.id
            WHERE kq.status = 'pending'
            AND sa.emailbison_account_id IS NOT NULL
            AND w.emailbison_workspace_id IS NOT NULL
        """)

        if not pending:
            return 0

        tagged_count = 0
        today = datetime.now().strftime('%Y%m%d')
        tag_name = f"delete_queue_{today}"

        # Group by workspace for efficiency
        by_workspace = {}
        for item in pending:
            ws_id = item['emailbison_workspace_id']
            if ws_id not in by_workspace:
                by_workspace[ws_id] = []
            by_workspace[ws_id].append(item)

        for ws_id, items in by_workspace.items():
            try:
                # Switch to workspace
                await self.client.switch_workspace(int(ws_id))

                # Get or create the delete queue tag
                tag = await self.client.get_or_create_tag(tag_name)
                tag_id = tag.get('id')

                if not tag_id:
                    audit.add_error(
                        record_id=f"workspace_{ws_id}",
                        error="Failed to create/find delete queue tag"
                    )
                    continue

                # Tag each inbox
                for item in items:
                    audit.increment_processed()

                    try:
                        # Tag in EmailBison
                        await self.client.tag_inbox(
                            account_id=int(item['emailbison_account_id']),
                            tag_id=tag_id
                        )

                        # Update queue status
                        scheduled_delete = datetime.now(timezone.utc) + timedelta(hours=24)
                        await self.db.execute("""
                            UPDATE kill_queue
                            SET
                                status = 'tagged',
                                tagged_at = NOW(),
                                tag_name = $2,
                                scheduled_delete_at = $3,
                                updated_at = NOW()
                            WHERE id = $1
                        """, item['id'], tag_name, scheduled_delete)

                        tagged_count += 1
                        audit.increment_updated()

                        print(f"    [TAGGED] {item['email_address']} - scheduled for {scheduled_delete}")

                    except EmailBisonAPIError as e:
                        audit.add_error(
                            record_id=item['email_address'],
                            error=f"Failed to tag: {e}",
                            details={'inbox_id': str(item['inbox_id'])}
                        )

                        # Mark as failed
                        await self.db.execute("""
                            UPDATE kill_queue
                            SET status = 'failed', error_message = $2, updated_at = NOW()
                            WHERE id = $1
                        """, item['id'], str(e))

            except Exception as e:
                audit.add_error(
                    record_id=f"workspace_{ws_id}",
                    error=f"Workspace error: {e}"
                )

        return tagged_count

    async def delete_ready_items(self, audit) -> int:
        """Delete items that have passed 24hr waiting period."""
        ready = await self.db.fetch("""
            SELECT
                kq.id,
                kq.inbox_id,
                kq.workspace_id,
                kq.trigger_type,
                kq.tag_name,
                sa.email_address,
                sa.emailbison_account_id,
                w.emailbison_workspace_id,
                w.workspace_name
            FROM kill_queue kq
            JOIN sender_accounts sa ON kq.inbox_id = sa.id
            JOIN workspaces w ON kq.workspace_id = w.id
            WHERE kq.status = 'tagged'
            AND kq.scheduled_delete_at <= NOW()
            AND sa.emailbison_account_id IS NOT NULL
            AND w.emailbison_workspace_id IS NOT NULL
        """)

        if not ready:
            return 0

        deleted_count = 0

        for item in ready:
            audit.increment_processed()

            try:
                # Switch to workspace
                await self.client.switch_workspace(int(item['emailbison_workspace_id']))

                # Delete from EmailBison
                await self.client.delete_sender_account(int(item['emailbison_account_id']))

                # Mark inbox as dead locally
                await self.db.execute("""
                    UPDATE sender_accounts
                    SET
                        inbox_state = 'dead',
                        killed_at = NOW(),
                        kill_trigger = $2,
                        is_active = FALSE,
                        updated_at = NOW()
                    WHERE id = $1
                """, item['inbox_id'], item['trigger_type'])

                # Update queue status
                await self.db.execute("""
                    UPDATE kill_queue
                    SET
                        status = 'deleted',
                        deleted_at = NOW(),
                        updated_at = NOW()
                    WHERE id = $1
                """, item['id'])

                deleted_count += 1
                audit.increment_updated()

                print(f"    [DELETED] {item['email_address']} - trigger: {item['trigger_type']}")

                # Alert
                if self.alerter:
                    await self.alerter.alert_inbox_deleted(
                        inbox_email=item['email_address'],
                        workspace=item['workspace_name'],
                        trigger=item['trigger_type']
                    )

            except EmailBisonAPIError as e:
                audit.add_error(
                    record_id=item['email_address'],
                    error=f"Failed to delete: {e}",
                    details={'inbox_id': str(item['inbox_id'])}
                )

                # If 404, inbox already deleted in EmailBison
                if e.status_code == 404:
                    # Still mark as dead locally
                    await self.db.execute("""
                        UPDATE sender_accounts
                        SET inbox_state = 'dead', is_active = FALSE, updated_at = NOW()
                        WHERE id = $1
                    """, item['inbox_id'])

                    await self.db.execute("""
                        UPDATE kill_queue
                        SET status = 'deleted', deleted_at = NOW(), updated_at = NOW()
                        WHERE id = $1
                    """, item['id'])

                    deleted_count += 1
                else:
                    # Other error - leave in queue for retry
                    await self.db.execute("""
                        UPDATE kill_queue
                        SET error_message = $2, updated_at = NOW()
                        WHERE id = $1
                    """, item['id'], str(e))

            except Exception as e:
                audit.add_error(
                    record_id=item['email_address'],
                    error=str(e)
                )

        return deleted_count

    async def cancel_kill(self, inbox_id: UUID, reason: str = None) -> bool:
        """
        Cancel a pending/tagged kill (manual override).

        Returns:
            True if cancelled, False if not found or already processed
        """
        result = await self.db.fetchrow("""
            UPDATE kill_queue
            SET
                status = 'cancelled',
                error_message = $2,
                updated_at = NOW()
            WHERE inbox_id = $1
            AND status IN ('pending', 'tagged')
            RETURNING id, tag_name, inbox_id
        """, inbox_id, reason or 'Manual cancellation')

        if result and result['tag_name']:
            # Try to remove the tag from EmailBison
            try:
                inbox = await self.db.fetchrow("""
                    SELECT
                        sa.emailbison_account_id,
                        w.emailbison_workspace_id
                    FROM sender_accounts sa
                    JOIN workspaces w ON sa.workspace_id = w.id
                    WHERE sa.id = $1
                """, inbox_id)

                if inbox and inbox['emailbison_account_id']:
                    await self.client.switch_workspace(int(inbox['emailbison_workspace_id']))

                    # Find tag ID
                    tags = await self.client.list_tags()
                    tag = next((t for t in tags if t.get('name') == result['tag_name']), None)

                    if tag:
                        await self.client.untag_inbox(
                            account_id=int(inbox['emailbison_account_id']),
                            tag_id=tag['id']
                        )

            except Exception as e:
                print(f"[KillProcessor] Warning: Failed to remove tag: {e}")

        return result is not None

    async def get_queue_summary(self) -> Dict:
        """Get summary of kill queue status."""
        stats = await self.db.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'tagged') as tagged,
                COUNT(*) FILTER (WHERE status = 'deleted') as deleted,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
            FROM kill_queue
        """)

        return {
            'pending': stats['pending'] or 0,
            'tagged': stats['tagged'] or 0,
            'deleted': stats['deleted'] or 0,
            'failed': stats['failed'] or 0,
            'cancelled': stats['cancelled'] or 0
        }
