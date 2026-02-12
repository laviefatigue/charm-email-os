"""
Health Check Module

Evaluates inbox and domain health, detects kill triggers.
Replaces Prefect-based health checks with polling-based evaluation.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncpg

from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Kill trigger thresholds (from api/routes/health.py)
KILL_THRESHOLDS = {
    'hard_bounces_24h': {
        'value': 2,
        'severity': 'instant',
        'description': '2+ hard bounces in 24 hours'
    },
    'hard_bounce_rate_7d': {
        'value': 0.005,  # 0.5%
        'min_sends': 50,
        'severity': 'instant',
        'description': 'Hard bounce rate >0.5% (min 50 sends)'
    },
    'bounce_rate_all_7d': {
        'value': 0.05,  # 5%
        'min_sends': 50,
        'severity': 'instant',
        'description': 'Total bounce rate >5%'
    },
    'fresh_inbox_hard_bounce': {
        'value': 1,
        'max_age_days': 14,
        'severity': 'instant',
        'description': 'Any hard bounce on inbox <14 days old'
    }
}


class HealthCheckModule:
    """Evaluates health and detects kill triggers."""

    def __init__(
        self,
        db: asyncpg.Pool,
        audit_logger: AuditLogger,
        alerter: SlackAlerter = None
    ):
        self.db = db
        self.audit_logger = audit_logger
        self.alerter = alerter or SlackAlerter()

    async def run_all_checks(self) -> SyncResult:
        """Run health checks for all workspaces."""
        audit = await self.audit_logger.start_audit(
            sync_type='health',
            metadata={'scope': 'all_workspaces'}
        )

        try:
            workspaces = await self.db.fetch("""
                SELECT id, workspace_name
                FROM workspaces
                WHERE is_active = TRUE
            """)

            total_triggers = 0

            for ws in workspaces:
                audit.increment_processed()

                try:
                    triggers = await self.check_workspace_health(
                        workspace_id=ws['id'],
                        workspace_name=ws['workspace_name']
                    )
                    total_triggers += triggers

                    if triggers > 0:
                        audit.increment_updated()

                except Exception as e:
                    audit.add_error(
                        record_id=ws['workspace_name'],
                        error=str(e)
                    )

            if total_triggers > 0:
                print(f"[HealthCheck] Detected {total_triggers} kill triggers across all workspaces")

            return await audit.complete()

        except Exception as e:
            return await audit.fail(e)

    async def check_workspace_health(
        self,
        workspace_id: UUID,
        workspace_name: str
    ) -> int:
        """
        Check health for all inboxes in a workspace.

        Returns:
            Number of kill triggers detected
        """
        # Get all active inboxes with metrics
        inboxes = await self.db.fetch("""
            SELECT
                id,
                email_address,
                inbox_state,
                hard_bounces_24h,
                hard_bounces_7d,
                soft_bounces_7d,
                total_sends_7d,
                bounce_rate_7d,
                health_score,
                first_seen_at
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'live'
            AND is_active = TRUE
        """, workspace_id)

        triggers_detected = 0

        for inbox in inboxes:
            health_state, triggers = await self.evaluate_inbox_health(
                inbox=dict(inbox),
                workspace_id=workspace_id,
                workspace_name=workspace_name
            )

            # Update health state
            await self.db.execute("""
                UPDATE sender_accounts
                SET updated_at = NOW()
                WHERE id = $1
            """, inbox['id'])

            triggers_detected += len(triggers)

        # Update domain health scores
        await self.update_domain_health(workspace_id)

        # Check overall workspace health
        health_summary = await self.get_workspace_health_summary(workspace_id)
        if health_summary['status'] == 'critical' and self.alerter:
            await self.alerter.alert_health_critical(
                workspace=workspace_name,
                critical_inboxes=health_summary['critical_count'],
                dead_inboxes=health_summary['dead_count'],
                health_score=health_summary['health_score']
            )

        return triggers_detected

    async def evaluate_inbox_health(
        self,
        inbox: Dict,
        workspace_id: UUID,
        workspace_name: str
    ) -> Tuple[str, List[Dict]]:
        """
        Evaluate health state for a single inbox.

        Returns:
            Tuple of (health_state, list of triggered kill conditions)
        """
        triggers = []

        hard_bounces_24h = inbox.get('hard_bounces_24h') or 0
        hard_bounces_7d = inbox.get('hard_bounces_7d') or 0
        soft_bounces_7d = inbox.get('soft_bounces_7d') or 0
        total_sends_7d = inbox.get('total_sends_7d') or 0
        first_seen_at = inbox.get('first_seen_at')

        # Calculate age
        inbox_age_days = None
        if first_seen_at:
            inbox_age_days = (datetime.now(timezone.utc) - first_seen_at.replace(tzinfo=timezone.utc)).days

        # Check each kill threshold
        # 1. Hard bounces in 24h
        threshold = KILL_THRESHOLDS['hard_bounces_24h']
        if hard_bounces_24h >= threshold['value']:
            triggers.append({
                'trigger_type': 'hard_bounces_24h',
                'value': hard_bounces_24h,
                'threshold': threshold['value']
            })

        # 2. Hard bounce rate 7d
        threshold = KILL_THRESHOLDS['hard_bounce_rate_7d']
        if total_sends_7d >= threshold.get('min_sends', 0):
            hard_rate = hard_bounces_7d / total_sends_7d if total_sends_7d > 0 else 0
            if hard_rate > threshold['value']:
                triggers.append({
                    'trigger_type': 'hard_bounce_rate_7d',
                    'value': hard_rate,
                    'threshold': threshold['value']
                })

        # 3. Total bounce rate 7d
        threshold = KILL_THRESHOLDS['bounce_rate_all_7d']
        if total_sends_7d >= threshold.get('min_sends', 0):
            total_bounces = hard_bounces_7d + soft_bounces_7d
            total_rate = total_bounces / total_sends_7d if total_sends_7d > 0 else 0
            if total_rate > threshold['value']:
                triggers.append({
                    'trigger_type': 'bounce_rate_all_7d',
                    'value': total_rate,
                    'threshold': threshold['value']
                })

        # 4. Fresh inbox hard bounce
        threshold = KILL_THRESHOLDS['fresh_inbox_hard_bounce']
        if inbox_age_days is not None and inbox_age_days < threshold.get('max_age_days', 14):
            if hard_bounces_24h >= threshold['value'] or hard_bounces_7d >= threshold['value']:
                triggers.append({
                    'trigger_type': 'fresh_inbox_hard_bounce',
                    'value': max(hard_bounces_24h, hard_bounces_7d),
                    'threshold': threshold['value']
                })

        # Determine health state
        if triggers:
            health_state = 'critical'
        elif hard_bounces_24h >= 1 or hard_bounces_7d >= 3:
            health_state = 'warning'
        else:
            health_state = 'healthy'

        # Queue for kill if triggers found
        if triggers:
            for trigger in triggers:
                await self.queue_for_kill(
                    inbox_id=inbox['id'],
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    inbox_email=inbox['email_address'],
                    trigger_type=trigger['trigger_type'],
                    trigger_value=trigger['value'],
                    trigger_threshold=trigger['threshold']
                )

        return health_state, triggers

    async def queue_for_kill(
        self,
        inbox_id: UUID,
        workspace_id: UUID,
        workspace_name: str,
        inbox_email: str,
        trigger_type: str,
        trigger_value: float,
        trigger_threshold: float
    ):
        """Add inbox to kill queue if not already queued."""
        # Check if already queued (pending or tagged)
        existing = await self.db.fetchval("""
            SELECT id FROM kill_queue
            WHERE inbox_id = $1
            AND status IN ('pending', 'tagged')
        """, inbox_id)

        if existing:
            return  # Already in queue

        # Add to queue
        await self.db.execute("""
            INSERT INTO kill_queue (
                inbox_id,
                workspace_id,
                trigger_type,
                trigger_value,
                trigger_threshold
            ) VALUES ($1, $2, $3, $4, $5)
        """,
            inbox_id,
            workspace_id,
            trigger_type,
            Decimal(str(trigger_value)),
            Decimal(str(trigger_threshold))
        )

        print(f"    [KILL QUEUE] {inbox_email} - {trigger_type}: {trigger_value:.4f} > {trigger_threshold:.4f}")

        # Alert
        if self.alerter:
            await self.alerter.alert_kill_trigger(
                inbox_email=inbox_email,
                workspace=workspace_name,
                trigger=trigger_type,
                value=trigger_value,
                threshold=trigger_threshold
            )

    async def update_domain_health(self, workspace_id: UUID):
        """Update health scores for all domains in workspace."""
        await self.db.execute("""
            UPDATE domains d
            SET
                latest_health_score = COALESCE(sub.avg_score, 100),
                updated_at = NOW()
            FROM (
                SELECT
                    domain_id,
                    AVG(COALESCE(health_score, 100))::INTEGER as avg_score
                FROM sender_accounts
                WHERE workspace_id = $1
                AND domain_id IS NOT NULL
                AND inbox_state = 'live'
                GROUP BY domain_id
            ) sub
            WHERE d.id = sub.domain_id
            AND d.workspace_id = $1
        """, workspace_id)

    async def get_workspace_health_summary(self, workspace_id: UUID) -> Dict:
        """Get health summary for a workspace."""
        stats = await self.db.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE inbox_state = 'live') as live,
                COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
                COUNT(*) FILTER (WHERE hard_bounces_24h >= 2 OR hard_bounces_7d >= 5) as critical,
                COUNT(*) FILTER (WHERE hard_bounces_24h >= 1 OR hard_bounces_7d >= 3) as warning,
                AVG(health_score)::INTEGER as avg_health
            FROM sender_accounts
            WHERE workspace_id = $1
            AND is_active = TRUE
        """, workspace_id)

        total = stats['total'] or 0
        live = stats['live'] or 0
        dead = stats['dead'] or 0
        critical = stats['critical'] or 0
        warning = stats['warning'] or 0
        avg_health = stats['avg_health'] or 100

        # Calculate overall health score
        health_score = 100
        if total > 0:
            health_score -= (dead / total) * 30
            health_score -= (critical / total) * 20
            health_score -= (warning / total) * 10
        health_score = max(0, min(100, health_score))

        # Determine status
        if critical > 0 or health_score < 50:
            status = 'critical'
        elif warning > 0 or health_score < 80:
            status = 'warning'
        else:
            status = 'healthy'

        return {
            'total_inboxes': total,
            'live_count': live,
            'dead_count': dead,
            'critical_count': critical,
            'warning_count': warning,
            'health_score': health_score,
            'avg_inbox_health': avg_health,
            'status': status
        }

    async def reset_daily_counters(self):
        """Reset 24h bounce counters (run daily at midnight)."""
        result = await self.db.execute("""
            UPDATE sender_accounts
            SET
                hard_bounces_24h = 0,
                updated_at = NOW()
            WHERE hard_bounces_24h > 0
        """)
        print(f"[HealthCheck] Reset 24h counters: {result}")

    async def decay_weekly_counters(self):
        """Decay 7d bounce counters (run daily to approximate rolling window)."""
        # Simple approach: reduce by ~14% daily to approximate 7-day decay
        await self.db.execute("""
            UPDATE sender_accounts
            SET
                hard_bounces_7d = GREATEST(0, (hard_bounces_7d * 0.86)::INTEGER),
                soft_bounces_7d = GREATEST(0, (soft_bounces_7d * 0.86)::INTEGER),
                total_sends_7d = GREATEST(0, (total_sends_7d * 0.86)::INTEGER),
                updated_at = NOW()
            WHERE hard_bounces_7d > 0 OR soft_bounces_7d > 0 OR total_sends_7d > 0
        """)
