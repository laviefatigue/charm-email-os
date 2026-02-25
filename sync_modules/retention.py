"""
Data Retention Manager

Handles cleanup of old data based on retention policies:
- Response messages (non-bounce): Indefinite retention
- Bounce messages: 90 days
- Audit logs: 90 days
- Kill queue (completed): 90 days
"""
import os
from datetime import datetime, timedelta
from typing import Dict
import asyncpg

from .audit_logger import AuditLogger, SyncResult


# Default retention period in days
RETENTION_DAYS_AUDIT = int(os.getenv('RETENTION_DAYS_AUDIT', 90))
RETENTION_DAYS_BOUNCES = int(os.getenv('RETENTION_DAYS_BOUNCES', 90))


class RetentionManager:
    """Manages data retention and cleanup."""

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_logger: AuditLogger
    ):
        self.db = db
        self.audit_logger = audit_logger
        self.retention_days_audit = RETENTION_DAYS_AUDIT
        self.retention_days_bounces = RETENTION_DAYS_BOUNCES

    async def run_cleanup(self) -> SyncResult:
        """Run all retention cleanup jobs."""
        audit = await self.audit_logger.start_audit(
            sync_type='retention',
            metadata={
                'retention_days_audit': self.retention_days_audit,
                'retention_days_bounces': self.retention_days_bounces
            }
        )

        try:
            audit_cutoff = datetime.now() - timedelta(days=self.retention_days_audit)
            bounce_cutoff = datetime.now() - timedelta(days=self.retention_days_bounces)

            # 1. Cleanup audit logs
            audit_deleted = await self.cleanup_audit_logs(audit_cutoff)
            audit.records_processed += audit_deleted

            # 2. Cleanup bounce messages (keep non-bounce indefinitely)
            bounce_deleted = await self.cleanup_bounce_messages(bounce_cutoff)
            audit.records_processed += bounce_deleted

            # 3. Cleanup completed kill queue entries
            kill_queue_deleted = await self.cleanup_kill_queue(audit_cutoff)
            audit.records_processed += kill_queue_deleted

            # 4. Cleanup orphaned campaign events (optional)
            # events_deleted = await self.cleanup_orphaned_events()
            # audit.records_processed += events_deleted

            print(f"[Retention] Cleaned up: {audit_deleted} audit logs, {bounce_deleted} bounces, {kill_queue_deleted} kill queue")

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def cleanup_audit_logs(self, cutoff: datetime) -> int:
        """Delete audit logs older than cutoff."""
        result = await self.db.execute("""
            DELETE FROM sync_audit_log
            WHERE started_at < $1
        """, cutoff)

        # Parse "DELETE N" to get count
        return self._parse_delete_count(result)

    async def cleanup_bounce_messages(self, cutoff: datetime) -> int:
        """
        Delete bounce messages older than cutoff.
        NOTE: Non-bounce response messages are kept indefinitely for analysis.
        """
        result = await self.db.execute("""
            DELETE FROM response_messages
            WHERE folder = 'bounced'
            AND received_at < $1
        """, cutoff)

        return self._parse_delete_count(result)

    async def cleanup_kill_queue(self, cutoff: datetime) -> int:
        """Delete completed/cancelled kill queue entries older than cutoff."""
        result = await self.db.execute("""
            DELETE FROM kill_queue
            WHERE status IN ('deleted', 'cancelled')
            AND created_at < $1
        """, cutoff)

        return self._parse_delete_count(result)

    async def cleanup_orphaned_events(self) -> int:
        """Delete campaign events for campaigns that no longer exist."""
        result = await self.db.execute("""
            DELETE FROM campaign_events ce
            WHERE NOT EXISTS (
                SELECT 1 FROM emailbison_campaigns ec
                WHERE ec.id = ce.campaign_id
            )
        """)

        return self._parse_delete_count(result)

    async def get_retention_stats(self) -> Dict:
        """Get statistics about data eligible for cleanup."""
        audit_cutoff = datetime.now() - timedelta(days=self.retention_days_audit)
        bounce_cutoff = datetime.now() - timedelta(days=self.retention_days_bounces)

        stats = await self.db.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM sync_audit_log WHERE started_at < $1) as audit_eligible,
                (SELECT COUNT(*) FROM response_messages WHERE folder = 'bounced' AND received_at < $2) as bounce_eligible,
                (SELECT COUNT(*) FROM kill_queue WHERE status IN ('deleted', 'cancelled') AND created_at < $1) as kill_queue_eligible,
                (SELECT COUNT(*) FROM sync_audit_log) as total_audit_logs,
                (SELECT COUNT(*) FROM response_messages WHERE folder = 'bounced') as total_bounces,
                (SELECT COUNT(*) FROM response_messages WHERE folder != 'bounced') as total_responses,
                (SELECT COUNT(*) FROM kill_queue) as total_kill_queue
        """, audit_cutoff, bounce_cutoff)

        return {
            'eligible_for_cleanup': {
                'audit_logs': stats['audit_eligible'] or 0,
                'bounce_messages': stats['bounce_eligible'] or 0,
                'kill_queue': stats['kill_queue_eligible'] or 0
            },
            'totals': {
                'audit_logs': stats['total_audit_logs'] or 0,
                'bounce_messages': stats['total_bounces'] or 0,
                'response_messages_kept': stats['total_responses'] or 0,
                'kill_queue': stats['total_kill_queue'] or 0
            },
            'retention_policy': {
                'audit_logs_days': self.retention_days_audit,
                'bounce_messages_days': self.retention_days_bounces,
                'response_messages': 'indefinite'
            }
        }

    def _parse_delete_count(self, result: str) -> int:
        """Parse DELETE result to get count."""
        if not result:
            return 0
        try:
            # Result format: "DELETE N"
            parts = result.split()
            if len(parts) >= 2:
                return int(parts[1])
        except (ValueError, IndexError):
            pass
        return 0
