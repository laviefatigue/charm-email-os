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
import json
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
            #
            # IMPORTANT: daily_capacity = CONNECTED live inboxes only
            # A live but disconnected inbox has 0 operational capacity
            #
            # ESP-aware disconnection: Microsoft IMAP disconnects are transient (~10 min).
            # Only count as "disconnected" if past threshold (48h Microsoft, 24h Gmail/other).
            capacity = await conn.fetchrow("""
                SELECT
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected_inboxes,
                    COUNT(*) FILTER (
                        WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')
                        AND sa.disconnected_at IS NOT NULL
                        AND (
                            (sa.esp = 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '48 hours')
                            OR (sa.esp != 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '24 hours')
                        )
                    ) as disconnected_inboxes,
                    COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') as incubating_inboxes,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,
                    -- Only CONNECTED live inboxes contribute to operational capacity
                    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected'), 0) as daily_capacity
                FROM sender_accounts sa
                LEFT JOIN domains d ON sa.domain_id = d.id
                WHERE sa.workspace_id = $1
                AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
            """, workspace_id)

            # Get kills on that date
            kills = await conn.fetchval("""
                SELECT COUNT(*)
                FROM sender_accounts sa
                LEFT JOIN domains d ON sa.domain_id = d.id
                WHERE sa.workspace_id = $1
                  AND sa.killed_at::DATE = $2
                  AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
            """, workspace_id, snapshot_date)

            # Try to get sending volume from campaign data
            # Uses campaign_snapshots table - get LATEST snapshot per campaign for the day
            #
            # IMPORTANT: campaign_snapshots contains CUMULATIVE values (total to date).
            # Multiple snapshots per day means we must use MAX (latest) per campaign,
            # then SUM across campaigns. Using SUM directly would cause 24x inflation
            # if hourly snapshots exist.
            volume = await conn.fetchrow("""
                WITH latest_daily_snapshots AS (
                    -- Get the latest snapshot per campaign for the target date
                    SELECT DISTINCT ON (cs.campaign_id)
                        cs.campaign_id,
                        cs.emails_sent,
                        cs.bounced
                    FROM campaign_snapshots cs
                    JOIN emailbison_campaigns ec ON cs.campaign_id = ec.id
                    WHERE ec.workspace_id = $1
                      AND DATE(cs.snapshot_timestamp) = $2
                    ORDER BY cs.campaign_id, cs.snapshot_timestamp DESC
                )
                SELECT
                    COALESCE(SUM(emails_sent), 0) as emails_sent,
                    COALESCE(SUM(emails_sent) - SUM(bounced), 0) as emails_delivered,
                    COALESCE(SUM(bounced), 0) as emails_bounced,
                    0 as emails_complained  -- Not tracked in campaign_snapshots
                FROM latest_daily_snapshots
            """, workspace_id, snapshot_date)

            # Use zeros if no campaign data found
            emails_sent = volume['emails_sent'] if volume and volume['emails_sent'] else 0
            emails_delivered = volume['emails_delivered'] if volume and volume['emails_delivered'] else 0
            emails_bounced = volume['emails_bounced'] if volume and volume['emails_bounced'] else 0
            emails_complained = volume['emails_complained'] if volume and volume['emails_complained'] else 0

            # Calculate utilization. Cap at 999.99 to fit NUMERIC(5,2) — a
            # workspace with daily_capacity≈0 but active sends (e.g. inboxes
            # without daily_limit set) would otherwise produce values >1000%
            # and trigger numeric field overflow on insert.
            daily_capacity = capacity['daily_capacity'] or 1
            raw_utilization = (emails_sent / daily_capacity) * 100 if daily_capacity > 0 else 0
            utilization_pct = min(raw_utilization, 999.99)

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
            'connected_inboxes': capacity['connected_inboxes'],
            'disconnected_inboxes': capacity['disconnected_inboxes'],
            'incubating_inboxes': capacity['incubating_inboxes'],
            'dead_inboxes': capacity['dead_inboxes'],
            'utilization_pct': round(utilization_pct, 2),
            'kills': kills or 0
        }

        # Calculate operational percentage for visibility
        operational_pct = (
            (capacity['connected_inboxes'] / capacity['live_inboxes'] * 100)
            if capacity['live_inboxes'] > 0 else 0
        )

        logger.info(
            f"✅ Snapshot complete: {workspace_id} | "
            f"Date: {snapshot_date} | "
            f"Sent: {emails_sent} | "
            f"Capacity: {capacity['daily_capacity']} (connected only) | "
            f"Operational: {operational_pct:.0f}% ({capacity['connected_inboxes']}/{capacity['live_inboxes']} live) | "
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

        # Log to sync_audit_log table directly (AuditLogger doesn't have log_event)
        if self.db:
            try:
                await self.db.execute("""
                    INSERT INTO sync_audit_log (sync_type, workspace_id, status, records_processed, metadata, completed_at)
                    VALUES ('daily_snapshot', NULL, $1, $2, $3, NOW())
                """,
                'completed' if not errors else 'partial',
                len(results),
                json.dumps(summary, default=str)
                )
            except Exception as e:
                logger.warning(f"Failed to log audit event: {e}")

        # Capture warmup snapshots for incubating inboxes
        try:
            warmup_count = await self.snapshot_warmup_incubating(snapshot_date)
            summary['warmup_snapshots'] = warmup_count
        except Exception as e:
            logger.error(f"Failed to capture warmup snapshots: {e}")
            summary['warmup_snapshots_error'] = str(e)

        # Recalculate domain burn velocities (30-day window)
        try:
            velocity_count = await self.db.fetchval(
                "SELECT recalculate_all_domain_velocities()"
            )
            summary['velocity_recalculated'] = velocity_count
            logger.info(f"Recalculated burn velocity for {velocity_count} domains")
        except Exception as e:
            logger.error(f"Failed to recalculate domain velocities: {e}")
            summary['velocity_error'] = str(e)

        # Alert on failures
        if errors and self.alerter:
            await self.alerter.send_alert(
                level='warning',
                title='Daily Snapshot Failures',
                message=f"Daily snapshot had {len(errors)} failures:\n" +
                "\n".join(f"- {e['workspace_name']}: {e['error']}" for e in errors[:5])
            )

        return summary

    async def snapshot_warmup_incubating(
        self,
        snapshot_date: Optional[date] = None
    ) -> int:
        """
        Capture warmup metrics for all incubating inboxes across all workspaces.

        Only snapshots inboxes with inventory_lifecycle_status = 'incubating'.
        After graduation to 'active', tracking stops (kill triggers take over).

        Returns:
            Count of warmup snapshots created
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        async with self.db.acquire() as conn:
            # Snapshot all incubating inboxes in one bulk INSERT
            result = await conn.execute("""
                INSERT INTO warmup_snapshots (
                    sender_account_id,
                    workspace_id,
                    snapshot_date,
                    warmup_score,
                    warmup_emails_sent,
                    warmup_replies_received,
                    warmup_emails_saved_from_spam,
                    warmup_bounces_received,
                    warmup_bounces_caused,
                    warmup_daily_limit,
                    warmup_enabled,
                    inbox_connected,
                    days_since_warmup_start,
                    emails_sent_all_time
                )
                SELECT
                    sa.id,
                    sa.workspace_id,
                    $1,
                    sa.warmup_score,
                    0,  -- warmup_emails_sent: not tracked per-sync, EB only gives aggregated
                    0,  -- warmup_replies_received: same
                    0,  -- warmup_emails_saved_from_spam: same
                    COALESCE(sa.warmup_bounces_received, 0),
                    COALESCE(sa.warmup_bounces_caused, 0),
                    sa.daily_limit,
                    COALESCE(sa.warmup_enabled, FALSE),
                    (sa.status = 'Connected'),
                    CASE
                        WHEN sa.warmup_started_at IS NOT NULL
                        THEN EXTRACT(DAY FROM NOW() - sa.warmup_started_at)::INTEGER
                        ELSE 0
                    END,
                    COALESCE(sa.emails_sent_all_time, 0)
                FROM sender_accounts sa
                LEFT JOIN domains d ON sa.domain_id = d.id
                WHERE sa.inventory_lifecycle_status = 'incubating'
                AND sa.is_active = TRUE
                AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
                ON CONFLICT (sender_account_id, snapshot_date)
                DO UPDATE SET
                    warmup_score = EXCLUDED.warmup_score,
                    warmup_bounces_received = EXCLUDED.warmup_bounces_received,
                    warmup_bounces_caused = EXCLUDED.warmup_bounces_caused,
                    warmup_daily_limit = EXCLUDED.warmup_daily_limit,
                    warmup_enabled = EXCLUDED.warmup_enabled,
                    inbox_connected = EXCLUDED.inbox_connected,
                    days_since_warmup_start = EXCLUDED.days_since_warmup_start,
                    emails_sent_all_time = EXCLUDED.emails_sent_all_time
            """, snapshot_date)

            # Parse row count from "INSERT 0 N"
            count = int(result.split()[-1]) if result else 0

            # Purge snapshots older than 30 days
            purged = await conn.execute("""
                DELETE FROM warmup_snapshots
                WHERE snapshot_date < $1
            """, date.today() - timedelta(days=30))

            purged_count = int(purged.split()[-1]) if purged else 0

            logger.info(
                f"Warmup snapshots: {count} incubating inboxes captured for {snapshot_date}"
                + (f", purged {purged_count} old rows" if purged_count > 0 else "")
            )

            return count

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
