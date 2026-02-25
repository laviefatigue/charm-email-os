"""
Daily Volume Snapshot Module

Captures daily sending volume and capacity metrics for client dashboard time-series charts.
Runs as part of the sync worker at 00:05 UTC daily.

Usage:
    # From sync worker:
    from sync_modules.daily_snapshot import DailySnapshotModule

    module = DailySnapshotModule(db, emailbison_client, alerter, audit_logger)
    await module.snapshot_all_workspaces()
"""
import asyncio
import logging
from datetime import date, timedelta
from typing import Optional, Dict, List, Any
from uuid import UUID

logger = logging.getLogger(__name__)


class DailySnapshotModule:
    """
    Module for capturing daily volume and capacity snapshots.

    Creates snapshots containing:
    - Emails sent that day (from EmailBison campaign data)
    - Live/incubating/dead inbox counts
    - Daily capacity available
    - Capacity utilization percentage
    - Kill events for chart annotations
    """

    def __init__(self, db, client, alerter, audit_logger):
        """
        Initialize the daily snapshot module.

        Args:
            db: asyncpg connection pool
            client: EmailBisonClient instance
            alerter: SlackAlerter instance
            audit_logger: AuditLogger instance
        """
        self.db = db
        self.client = client
        self.alerter = alerter
        self.audit_logger = audit_logger

    async def snapshot_workspace(
        self,
        workspace_id: UUID,
        snapshot_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Create daily snapshot for a single workspace.

        Args:
            workspace_id: UUID of workspace to snapshot
            snapshot_date: Date to snapshot (default: yesterday)

        Returns:
            Dict with snapshot metrics
        """
        if snapshot_date is None:
            snapshot_date = date.today() - timedelta(days=1)

        logger.info(f"Snapshotting workspace {workspace_id} for {snapshot_date}")

        async with self.db.acquire() as conn:
            # Get capacity metrics as of now (represents end of snapshot_date)
            capacity = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE inbox_state = 'live') as live_inboxes,
                    COUNT(*) FILTER (WHERE inventory_lifecycle_status = 'incubating') as incubating_inboxes,
                    COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_inboxes,
                    COALESCE(SUM(daily_limit) FILTER (WHERE inbox_state = 'live'), 0) as daily_capacity
                FROM sender_accounts
                WHERE workspace_id = $1
            """, workspace_id)

            # Get kills on that date
            kills = await conn.fetchval("""
                SELECT COUNT(*)
                FROM sender_accounts
                WHERE workspace_id = $1
                  AND killed_at::DATE = $2
            """, workspace_id, snapshot_date)

            # Try to get sending volume from campaign data
            # Option 1: If campaign_snapshots table exists with daily data
            volume = await conn.fetchrow("""
                SELECT
                    COALESCE(SUM(sent), 0) as emails_sent,
                    COALESCE(SUM(delivered), 0) as emails_delivered,
                    COALESCE(SUM(hard_bounces + soft_bounces), 0) as emails_bounced,
                    COALESCE(SUM(spam_complaints), 0) as emails_complained
                FROM campaign_snapshots cs
                JOIN emailbison_campaigns ec ON cs.campaign_id = ec.emailbison_id
                WHERE ec.workspace_id = $1
                  AND DATE(cs.snapshot_date) = $2
            """, workspace_id, snapshot_date)

            # Use zeros if no campaign data found
            emails_sent = volume['emails_sent'] if volume and volume['emails_sent'] else 0
            emails_delivered = volume['emails_delivered'] if volume and volume['emails_delivered'] else 0
            emails_bounced = volume['emails_bounced'] if volume and volume['emails_bounced'] else 0
            emails_complained = volume['emails_complained'] if volume and volume['emails_complained'] else 0

            # Calculate utilization
            daily_capacity = capacity['daily_capacity'] or 1
            utilization_pct = (emails_sent / daily_capacity) * 100 if daily_capacity > 0 else 0

            # Insert or update snapshot
            await conn.execute("""
                INSERT INTO daily_volume_snapshots (
                    workspace_id,
                    snapshot_date,
                    emails_sent,
                    emails_delivered,
                    emails_bounced,
                    emails_complained,
                    live_inboxes,
                    incubating_inboxes,
                    dead_inboxes,
                    daily_capacity_available,
                    capacity_utilization_pct,
                    kills_that_day,
                    updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
                ON CONFLICT (workspace_id, snapshot_date)
                DO UPDATE SET
                    emails_sent = EXCLUDED.emails_sent,
                    emails_delivered = EXCLUDED.emails_delivered,
                    emails_bounced = EXCLUDED.emails_bounced,
                    emails_complained = EXCLUDED.emails_complained,
                    live_inboxes = EXCLUDED.live_inboxes,
                    incubating_inboxes = EXCLUDED.incubating_inboxes,
                    dead_inboxes = EXCLUDED.dead_inboxes,
                    daily_capacity_available = EXCLUDED.daily_capacity_available,
                    capacity_utilization_pct = EXCLUDED.capacity_utilization_pct,
                    kills_that_day = EXCLUDED.kills_that_day,
                    updated_at = NOW()
            """,
                workspace_id,
                snapshot_date,
                emails_sent,
                emails_delivered,
                emails_bounced,
                emails_complained,
                capacity['live_inboxes'],
                capacity['incubating_inboxes'],
                capacity['dead_inboxes'],
                capacity['daily_capacity'],
                round(utilization_pct, 2),
                kills or 0
            )

        result = {
            'workspace_id': str(workspace_id),
            'snapshot_date': str(snapshot_date),
            'emails_sent': emails_sent,
            'daily_capacity': capacity['daily_capacity'],
            'live_inboxes': capacity['live_inboxes'],
            'incubating_inboxes': capacity['incubating_inboxes'],
            'dead_inboxes': capacity['dead_inboxes'],
            'utilization_pct': round(utilization_pct, 2),
            'kills': kills or 0
        }

        logger.info(
            f"✅ Snapshot complete: {workspace_id} | "
            f"Date: {snapshot_date} | "
            f"Sent: {emails_sent} | "
            f"Capacity: {capacity['daily_capacity']} | "
            f"Utilization: {utilization_pct:.1f}% | "
            f"Kills: {kills or 0}"
        )

        return result

    async def snapshot_all_workspaces(
        self,
        snapshot_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Run daily snapshot for all active workspaces.

        Args:
            snapshot_date: Date to snapshot (default: yesterday)

        Returns:
            Dict with results summary
        """
        if snapshot_date is None:
            snapshot_date = date.today() - timedelta(days=1)

        logger.info(f"Starting daily snapshot for all workspaces (date: {snapshot_date})")

        async with self.db.acquire() as conn:
            # Get all workspaces that have sender accounts
            workspaces = await conn.fetch("""
                SELECT DISTINCT w.id, w.workspace_name
                FROM workspaces w
                INNER JOIN sender_accounts sa ON sa.workspace_id = w.id
            """)

        results = []
        errors = []

        for workspace in workspaces:
            try:
                result = await self.snapshot_workspace(
                    workspace['id'],
                    snapshot_date
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to snapshot workspace {workspace['id']}: {e}")
                errors.append({
                    'workspace_id': str(workspace['id']),
                    'workspace_name': workspace['workspace_name'],
                    'error': str(e)
                })

        summary = {
            'snapshot_date': str(snapshot_date),
            'workspaces_processed': len(results),
            'workspaces_failed': len(errors),
            'total_emails_sent': sum(r['emails_sent'] for r in results),
            'total_capacity': sum(r['daily_capacity'] for r in results),
            'total_live_inboxes': sum(r['live_inboxes'] for r in results),
            'total_kills': sum(r['kills'] for r in results),
            'errors': errors if errors else None
        }

        logger.info(
            f"Daily snapshot complete: "
            f"{len(results)} succeeded, {len(errors)} failed | "
            f"Total capacity: {summary['total_capacity']:,} | "
            f"Total kills: {summary['total_kills']}"
        )

        # Log audit event
        if self.audit_logger:
            await self.audit_logger.log_event(
                event_type='daily_snapshot',
                module='daily_snapshot',
                data=summary,
                status='completed' if not errors else 'partial'
            )

        # Alert on failures
        if errors and self.alerter:
            await self.alerter.send_message(
                f"⚠️ Daily snapshot had {len(errors)} failures:\n" +
                "\n".join(f"- {e['workspace_name']}: {e['error']}" for e in errors[:5])
            )

        return summary

    async def backfill_snapshots(
        self,
        days: int = 90
    ) -> Dict[str, Any]:
        """
        Backfill daily snapshots for past N days.

        Note: This only captures current capacity state, not historical sending volume.
        Useful for initializing the chart with capacity data.

        Args:
            days: Number of days to backfill (default: 90)

        Returns:
            Dict with backfill summary
        """
        logger.info(f"Starting backfill for past {days} days")

        results = []
        for i in range(days, 0, -1):
            snapshot_date = date.today() - timedelta(days=i)
            try:
                summary = await self.snapshot_all_workspaces(snapshot_date)
                results.append(summary)
                # Small delay to avoid overwhelming the database
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Backfill failed for {snapshot_date}: {e}")

        return {
            'days_backfilled': len(results),
            'days_requested': days,
            'success_rate': f"{len(results) / days * 100:.1f}%"
        }
