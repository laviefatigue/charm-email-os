"""
Health Check Module

Evaluates inbox and domain health, detects kill triggers.
Replaces Prefect-based health checks with polling-based evaluation.
"""
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID
import asyncpg

from .audit_logger import AuditLogger, SyncResult
from .slack_alerter import SlackAlerter


# Configurable kill trigger thresholds (env vars with v3 spec defaults).
#
# Microsoft thresholds — pre-overhaul defaults retained. Microsoft Entra is
# legacy ride-to-death (CEO Rule C2): existing fleet only, no new orders. We
# don't tighten kill thresholds on the legacy population.
KILL_THRESHOLD_SPAM = int(os.getenv('KILL_THRESHOLD_SPAM', 1))
KILL_THRESHOLD_HARD_BLOCKED_24H = int(os.getenv('KILL_THRESHOLD_HARD_BLOCKED_24H', 2))
KILL_THRESHOLD_HARD_UNKNOWN_24H = int(os.getenv('KILL_THRESHOLD_HARD_UNKNOWN_24H', 3))
KILL_THRESHOLD_HARD_BOUNCES_24H = int(os.getenv('KILL_THRESHOLD_HARD_BOUNCES_24H', 2))

# Google thresholds — tighter post-2026-04-29 (ADR-007). 100% Google going
# forward + 3 inboxes/domain means a single hard bounce is meaningful signal:
# - 1 dead inbox = 33% capacity loss on the domain (already at v3's "replace
#   domain" threshold)
# - The pre-overhaul `warning` soft-pause buffer was a charm-specific addition
#   not in the v3 spec; v3 says "kill fast, swap fast, diagnose after"
# - With the 20-send floor still in effect, this won't kill on warmup-network
#   bounce noise — only on inboxes that have actually started sending volume
GOOGLE_KILL_THRESHOLD_HARD_BLOCKED_24H = int(os.getenv('GOOGLE_KILL_THRESHOLD_HARD_BLOCKED_24H', 1))
GOOGLE_KILL_THRESHOLD_HARD_UNKNOWN_24H = int(os.getenv('GOOGLE_KILL_THRESHOLD_HARD_UNKNOWN_24H', 1))
GOOGLE_KILL_THRESHOLD_HARD_BOUNCES_24H = int(os.getenv('GOOGLE_KILL_THRESHOLD_HARD_BOUNCES_24H', 1))


def evaluate_lifetime_rule(
    complaints: int,
    sends: int,
    hard_bounces: int,
    *,
    spam_threshold: int = 1,
    min_sends: int = 20,
    rate_threshold: float = 0.05,
) -> Optional[Tuple[str, float, float]]:
    """Pure function form of the post-2026-05-04 lifetime kill rule.

    Returns (trigger_type, value, threshold) when the inbox should be killed,
    or None when it should be left alive.

    Branches (top to bottom):
      1. complaints >= spam_threshold        → ('spam_complaint', complaints, spam_threshold)
      2. sends < min_sends                   → None (skip — insufficient data)
      3. hard_bounces / sends > rate_threshold → ('hard_bounce_rate_lifetime', rate, rate_threshold)
      4. otherwise                           → None

    Extracted for unit-testability — see tests/test_kill_rule_lifetime.py.
    """
    if complaints >= spam_threshold:
        return ('spam_complaint', float(complaints), float(spam_threshold))
    if sends < min_sends:
        return None
    rate = hard_bounces / sends if sends > 0 else 0.0
    if rate > rate_threshold:
        return ('hard_bounce_rate_lifetime', rate, rate_threshold)
    return None


def get_count_threshold(esp: Optional[str], trigger: str) -> int:
    """Return the count threshold for a trigger, ESP-aware.

    Google uses tightened thresholds (1/1/1) per ADR-007. Microsoft and
    unknown-ESP retain the pre-overhaul defaults (2/3/2).
    """
    if esp == 'gmail':
        return {
            'hard_blocked_24h': GOOGLE_KILL_THRESHOLD_HARD_BLOCKED_24H,
            'hard_unknown_24h': GOOGLE_KILL_THRESHOLD_HARD_UNKNOWN_24H,
            'hard_bounces_24h': GOOGLE_KILL_THRESHOLD_HARD_BOUNCES_24H,
        }[trigger]
    return {
        'hard_blocked_24h': KILL_THRESHOLD_HARD_BLOCKED_24H,
        'hard_unknown_24h': KILL_THRESHOLD_HARD_UNKNOWN_24H,
        'hard_bounces_24h': KILL_THRESHOLD_HARD_BOUNCES_24H,
    }[trigger]
KILL_THRESHOLD_HARD_BOUNCE_RATE = float(os.getenv('KILL_THRESHOLD_HARD_BOUNCE_RATE', 0.02))
KILL_THRESHOLD_TOTAL_BOUNCE_RATE = float(os.getenv('KILL_THRESHOLD_TOTAL_BOUNCE_RATE', 0.05))
KILL_THRESHOLD_MIN_SENDS = int(os.getenv('KILL_THRESHOLD_MIN_SENDS', 100))  # Industry standard: min 100 sends before rate triggers

# Lifetime-rate rule (post-2026-05-04 rewrite — see docs/plans/kill-rule-rate-based-rewrite.md).
# Replaces the windowed-count rules (hard_blocked_24h ≥ N, etc.) that produced
# the 2026-04-14 Barrena mass-kill via stored-counter inflation. Numerator
# computed on demand from response_messages bounce events; denominator is
# sender_accounts.emails_sent_all_time (synced from EB). No rolling counter,
# no decay, no reset — therefore no inflation bug class.
KILL_MIN_SENDS_LIFETIME = int(os.getenv('KILL_MIN_SENDS_LIFETIME', 20))
KILL_MATURE_RATE = float(os.getenv('KILL_MATURE_RATE', 0.05))
# When true, evaluate the new rule but log decisions instead of queueing kills.
# Default true on first deploy so we can read one cycle of would-kill output
# before flipping. Set KILL_RULE_DRY_RUN=false in env to make rule load-bearing.
KILL_RULE_DRY_RUN = os.getenv('KILL_RULE_DRY_RUN', 'true').lower() in ('true', '1', 'yes')
# Min campaign send volume required before count-based bounce triggers
# (hard_bounces_24h, hard_blocked_24h, hard_unknown_24h, combined
# hard_bounces_24h) fire. CEO target of 15-20 sends/day per inbox is the
# floor — below that, a few hard bounces are noise, not signal.
#
# We accept EITHER total_sends_24h ≥ floor OR total_sends_7d ≥ floor.
# Reasoning: post-2026-04-27 overhaul we want to read the 24h column
# (migration 095) as the canonical signal because it answers "did this
# inbox send today?" directly. But sync_warmup is not yet writing the
# new column on every cycle — until it does, the 24h column will be
# zero for everyone and the floor would silently pause all count-based
# kills fleet-wide. The 7d fallback keeps the existing protection
# active during the rollout window. Once sync_warmup populates 24h
# reliably, the 7d fallback can be removed.
KILL_THRESHOLD_MIN_SENDS_24H_FOR_COUNT_TRIGGER = int(
    os.getenv('KILL_THRESHOLD_MIN_SENDS_24H_FOR_COUNT_TRIGGER', 20)
)
KILL_THRESHOLD_MIN_SENDS_7D_FALLBACK = int(
    os.getenv('KILL_THRESHOLD_MIN_SENDS_7D_FALLBACK', 20)
)
KILL_THRESHOLD_FRESH_INBOX_DAYS = int(os.getenv('KILL_THRESHOLD_FRESH_INBOX_DAYS', 21))
KILL_THRESHOLD_FRESH_BLOCKED = int(os.getenv('KILL_THRESHOLD_FRESH_BLOCKED', 1))
KILL_THRESHOLD_FRESH_UNKNOWN = int(os.getenv('KILL_THRESHOLD_FRESH_UNKNOWN', 3))
KILL_THRESHOLD_DISCONNECTED_DAYS = int(os.getenv('KILL_THRESHOLD_DISCONNECTED_DAYS', 21))

# Kill trigger thresholds (configurable via env vars)
# Priority order: spam > hard_blocked > hard_unknown > combined > rate-based > disconnected
# NOTE: provider_block_* auto-detection removed (2026-03-18). Hard_blocked bounces indicate
# RECIPIENT server rejection (550 5.7.x), not sending-provider domain blocks. A single strict
# corporate recipient rejecting email was being misclassified as a domain-level provider block,
# causing instant domain burns. Provider blocks should be detected via account disconnection/
# suspension signals. See _flag_all_disconnected_domains() for connection-based detection.
#
# NOTE: fresh_inbox_blocked and fresh_inbox_unknown removed (2026-03-18). These had identical
# thresholds to hard_blocked_24h (>=2) and hard_unknown_24h (>=3), making them redundant.
KILL_THRESHOLDS = {
    'spam_complaint': {
        'value': KILL_THRESHOLD_SPAM,
        'severity': 'instant',
        'description': f'{KILL_THRESHOLD_SPAM}+ spam complaints = immediate death (v3 spec)'
    },
    'hard_blocked_24h': {
        'value': KILL_THRESHOLD_HARD_BLOCKED_24H,
        'severity': 'instant',
        'description': f'{KILL_THRESHOLD_HARD_BLOCKED_24H}+ spam/policy rejections in 24h (reputation damage)'
    },
    'hard_unknown_24h': {
        'value': KILL_THRESHOLD_HARD_UNKNOWN_24H,
        'severity': 'instant',
        'description': f'{KILL_THRESHOLD_HARD_UNKNOWN_24H}+ bad addresses in 24h (list quality issue)'
    },
    'hard_bounces_24h': {
        'value': KILL_THRESHOLD_HARD_BOUNCES_24H,
        'severity': 'instant',
        'description': f'{KILL_THRESHOLD_HARD_BOUNCES_24H}+ combined hard bounces in 24h (fallback)'
    },
    'hard_bounce_rate_7d': {
        'value': KILL_THRESHOLD_HARD_BOUNCE_RATE,
        'min_sends': KILL_THRESHOLD_MIN_SENDS,
        'severity': 'instant',
        'description': f'Hard bounce rate >{KILL_THRESHOLD_HARD_BOUNCE_RATE*100}% (min {KILL_THRESHOLD_MIN_SENDS} sends)'
    },
    'bounce_rate_all_7d': {
        'value': KILL_THRESHOLD_TOTAL_BOUNCE_RATE,
        'min_sends': KILL_THRESHOLD_MIN_SENDS,
        'severity': 'instant',
        'description': f'Total bounce rate >{KILL_THRESHOLD_TOTAL_BOUNCE_RATE*100}%'
    },
    # New post-2026-05-04 rule — see comment block on KILL_MIN_SENDS_LIFETIME above.
    'hard_bounce_rate_lifetime': {
        'value': KILL_MATURE_RATE,
        'min_sends': KILL_MIN_SENDS_LIFETIME,
        'severity': 'instant',
        'description': f'Lifetime hard bounce rate >{KILL_MATURE_RATE*100:.0f}% (min {KILL_MIN_SENDS_LIFETIME} sends)'
    },
    # 'disconnected_timeout' was removed 2026-04-30 per docs/plans/connection-state-machine.md.
    # The 21-day-disconnect-equals-dead rule produced ~1,200 fleet-wide zombies (rows
    # marked dead in DB while currently Connected and sending in EB). Connection state
    # is now monitoring-only; quality state (live/dead) is driven only by the 5
    # reputation triggers above. The disconnected_timeout enum value is preserved for
    # historical kill_trigger entries but no new code path writes it.
}

# Domain health thresholds — rate-based + capacity safety net
# Use Decimal for all numeric values to prevent asyncpg type inference errors
# (Python float vs int inconsistency on prepared statement reuse)
#
# CRITICAL RULE — DOMAIN-LEVEL TAGGING:
# A domain's inboxes must NEVER have mixed pool tags (some live, some reserve).
# When a kill trigger fires, the domain-level decision determines ALL inboxes:
# - spam_complaint on ANY inbox → entire domain burns, ALL inboxes lose pool tags
# - Other kills (hard_blocked, hard_bounces) → inbox dies, domain flagged for monitoring
# - Domain burn = ALL inboxes retired regardless of individual health
# Warning/degraded inboxes keep their domain's pool tag in EB; warning state
# is tracked only in DB (inventory_pool_status='warning').
DOMAIN_THRESHOLDS = {
    'complaint_rate_healthy': Decimal('0.001'),    # < 0.1% = domain is fine
    'complaint_rate_flagged': Decimal('0.003'),    # 0.1-0.3% = flagged, monitor closely
    'complaint_rate_burn': Decimal('0.01'),        # > 1.0% sustained = dead/burn
    'monitoring_window_days': 7,                   # Observation window before burn decision
    'unhealthy_pause': Decimal('0.30'),            # 30% unhealthy = capacity safety net
    'unhealthy_min_count': 2,                      # Min unhealthy inboxes before % threshold applies
}

# ESP-aware domain burn thresholds (bounce-rate path)
# Entra domains (52 inboxes) burn on bounce pattern, not spam complaints.
# Google domains burn on spam complaints (handled by kill_processor ESP logic).
# Hard-bounce-only rate avoids false positives from transient Microsoft soft bounces.
ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE = Decimal('0.05')  # >5% hard bounce rate = domain compromised
ENTRA_DOMAIN_BURN_MIN_SENDS = 50       # Min sends before bounce rate is meaningful
ENTRA_DOMAIN_BURN_MIN_BLOCKED = 2      # 2+ blocked inboxes = cross-inbox pattern
ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER = 2  # Max auto-burns per workspace per health check cycle


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
            # First, aggregate bounce counts from response_messages
            # This ensures counters are up-to-date before checking triggers
            await self.aggregate_bounce_counts_from_events()

            workspaces = await self.db.fetch("""
                SELECT id, workspace_name
                FROM v_operational_workspaces
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

    async def aggregate_bounce_counts_from_events(self):
        """
        Aggregate bounce counts from response_messages table.

        This catches bounces that weren't properly linked during sync,
        and provides a reconciliation mechanism to ensure bounce counters
        are accurate before health checks run.

        Updates hard_bounces_24h, hard_bounces_7d, and hard_blocked_24h
        based on actual bounce events in the database.
        """
        try:
            # Count bounces per sender account from response_messages
            result = await self.db.execute("""
                WITH bounce_counts AS (
                    SELECT
                        sender_account_id,
                        COUNT(*) FILTER (
                            WHERE bounce_type IN ('hard_unknown', 'hard_blocked')
                            AND received_at > NOW() - INTERVAL '24 hours'
                        ) as hard_bounces_24h,
                        COUNT(*) FILTER (
                            WHERE bounce_type IN ('hard_unknown', 'hard_blocked')
                            AND received_at > NOW() - INTERVAL '7 days'
                        ) as hard_bounces_7d,
                        COUNT(*) FILTER (
                            WHERE bounce_type = 'hard_blocked'
                            AND received_at > NOW() - INTERVAL '24 hours'
                        ) as blocked_24h,
                        COUNT(*) FILTER (
                            WHERE bounce_type = 'hard_unknown'
                            AND received_at > NOW() - INTERVAL '24 hours'
                        ) as unknown_24h,
                        COUNT(*) FILTER (
                            WHERE bounce_type IN ('soft_full', 'soft_temp')
                            AND received_at > NOW() - INTERVAL '7 days'
                        ) as soft_7d
                    FROM response_messages
                    WHERE folder = 'bounced'
                      AND sender_account_id IS NOT NULL
                      AND received_at > NOW() - INTERVAL '7 days'
                    GROUP BY sender_account_id
                )
                UPDATE sender_accounts sa
                SET
                    hard_bounces_24h = GREATEST(COALESCE(sa.hard_bounces_24h, 0), COALESCE(bc.hard_bounces_24h, 0)),
                    hard_bounces_7d = GREATEST(COALESCE(sa.hard_bounces_7d, 0), COALESCE(bc.hard_bounces_7d, 0)),
                    hard_blocked_24h = GREATEST(COALESCE(sa.hard_blocked_24h, 0), COALESCE(bc.blocked_24h, 0)),
                    hard_unknown_24h = GREATEST(COALESCE(sa.hard_unknown_24h, 0), COALESCE(bc.unknown_24h, 0)),
                    soft_bounces_7d = GREATEST(COALESCE(sa.soft_bounces_7d, 0), COALESCE(bc.soft_7d, 0)),
                    updated_at = NOW()
                FROM bounce_counts bc
                WHERE sa.id = bc.sender_account_id
                AND (
                    COALESCE(sa.hard_bounces_24h, 0) < COALESCE(bc.hard_bounces_24h, 0)
                    OR COALESCE(sa.hard_bounces_7d, 0) < COALESCE(bc.hard_bounces_7d, 0)
                    OR COALESCE(sa.hard_blocked_24h, 0) < COALESCE(bc.blocked_24h, 0)
                    OR COALESCE(sa.hard_unknown_24h, 0) < COALESCE(bc.unknown_24h, 0)
                    OR COALESCE(sa.soft_bounces_7d, 0) < COALESCE(bc.soft_7d, 0)
                )
            """)
            print(f"[HealthCheck] Aggregated bounce counts from response_messages: {result}")
        except Exception as e:
            # Don't fail health checks if aggregation fails
            print(f"[HealthCheck] Warning: Failed to aggregate bounce counts: {e}")

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
        # Get all active inboxes with metrics.
        #
        # Lifetime metrics for the new rate rule:
        #   emails_sent_all_time      — synced from EB sender.emails_sent_count (denominator)
        #   complaints_lifetime       — instant-kill on ≥1
        #   hard_bounces_lifetime     — computed on demand from response_messages
        #                              (numerator; no stored counter to drift)
        #
        # Legacy _24h / _7d columns retained in the SELECT for now because UI
        # consumers may still read them. The kill-rule body no longer uses them.
        inboxes = await self.db.fetch("""
            SELECT
                sa.id,
                sa.email_address,
                sa.inbox_state,
                sa.status,
                sa.esp,
                sa.hard_bounces_24h,
                sa.hard_blocked_24h,
                sa.hard_unknown_24h,
                sa.hard_bounces_7d,
                sa.soft_bounces_7d,
                sa.total_sends_24h,
                sa.total_sends_7d,
                sa.bounce_rate_7d,
                sa.health_score,
                sa.warmup_started_at,
                sa.sending_started_at,
                sa.disconnected_at,
                sa.complaints_lifetime,
                COALESCE(sa.emails_sent_all_time, 0) AS emails_sent_all_time,
                (
                    SELECT COUNT(*) FROM response_messages rm
                    WHERE rm.sender_account_id = sa.id
                      AND rm.folder = 'bounced'
                      AND rm.bounce_type IN ('hard_blocked', 'hard_unknown')
                ) AS hard_bounces_lifetime
            FROM sender_accounts sa
            LEFT JOIN domains d ON sa.domain_id = d.id
            WHERE sa.workspace_id = $1
            AND sa.inbox_state = 'live'
            AND sa.is_active = TRUE
            AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
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
        Evaluate health for one live inbox using the post-2026-05-04 rule.

        Three branches, evaluated top to bottom:

          1. complaints_lifetime ≥ 1                    → spam_complaint kill
          2. emails_sent_all_time < KILL_MIN_SENDS_LIFETIME (default 20)
                                                        → skip (insufficient data)
          3. hard_bounces_lifetime / emails_sent_all_time > KILL_MATURE_RATE
             (default 5%)                               → hard_bounce_rate_lifetime kill

        The numerator (`hard_bounces_lifetime`) is computed in
        check_workspace_health from response_messages (no stored counter to
        drift). The denominator (`emails_sent_all_time`) is synced from EB.

        See docs/plans/kill-rule-rate-based-rewrite.md for the rationale and
        the 2026-04-14 Barrena mass-kill incident this rewrite addresses.

        When KILL_RULE_DRY_RUN is true, log the would-kill decision instead
        of queueing.
        """
        triggers: List[Dict] = []

        complaints = int(inbox.get('complaints_lifetime') or 0)
        sends = int(inbox.get('emails_sent_all_time') or 0)
        hard_bounces = int(inbox.get('hard_bounces_lifetime') or 0)

        verdict = evaluate_lifetime_rule(
            complaints=complaints,
            sends=sends,
            hard_bounces=hard_bounces,
            spam_threshold=KILL_THRESHOLDS['spam_complaint']['value'],
            min_sends=KILL_MIN_SENDS_LIFETIME,
            rate_threshold=KILL_MATURE_RATE,
        )
        if verdict is not None:
            trigger_type, value, threshold = verdict
            triggers.append({
                'trigger_type': trigger_type,
                'value': value,
                'threshold': threshold,
            })

        # Determine health state.
        health_state = 'critical' if triggers else 'healthy'

        # Queue or dry-run-log every fired trigger.
        for trigger in triggers:
            if KILL_RULE_DRY_RUN:
                print(
                    f"  [KILL_RULE_DRY_RUN] would-kill {inbox['email_address']} "
                    f"({workspace_name}): trigger={trigger['trigger_type']} "
                    f"value={trigger['value']:.4f} threshold={trigger['threshold']:.4f} "
                    f"(sends={sends}, hard_bounces={hard_bounces}, complaints={complaints})"
                )
            else:
                await self.queue_for_kill(
                    inbox_id=inbox['id'],
                    workspace_id=workspace_id,
                    workspace_name=workspace_name,
                    inbox_email=inbox['email_address'],
                    trigger_type=trigger['trigger_type'],
                    trigger_value=trigger['value'],
                    trigger_threshold=trigger['threshold'],
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
        """Add inbox to kill queue if not already pending.

        Uses ON CONFLICT with partial unique index (migration 099):
            idx_kill_queue_inbox_pending ON (inbox_id) WHERE status = 'pending'

        Pre-2026-04-29 the index also blocked on 'flagged' — but `flagged`
        rows in legacy code could correspond to inboxes still alive in DB
        (kill_processor partial-failure pattern). That silently blocked
        legitimate new kills from being queued. The narrower index lets
        health_checks re-queue after a flagged kill if the inbox is somehow
        still alive (the steady-state filter `WHERE inbox_state = 'live'`
        prevents re-queueing of properly-dead inboxes).
        """
        result = await self.db.fetchval("""
            INSERT INTO kill_queue (
                inbox_id,
                workspace_id,
                trigger_type,
                trigger_value,
                trigger_threshold
            ) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (inbox_id) WHERE status = 'pending'
            DO NOTHING
            RETURNING id
        """,
            inbox_id,
            workspace_id,
            trigger_type,
            Decimal(str(trigger_value)),
            Decimal(str(trigger_threshold))
        )

        if result is None:
            return  # Already in queue

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
        """
        Update health scores and V3 state for all domains in workspace.

        V3 Section 5 Domain Health Thresholds:
        - 1 dead inbox = 'flagged' (accelerate backup warming)
        - 2+ dead inboxes = 'dead' (tag for review)
        - >30% inboxes unhealthy = 'dead' (tag for review)
        - ALL live inboxes disconnected = 'flagged' (0 operational capacity)

        NOTE: Domain state changes are local flags only.
        Human operators decide actual action based on state.
        """
        # Update basic health metrics (including connection status counts)
        await self.db.execute("""
            UPDATE domains d
            SET
                latest_health_score = COALESCE(sub.avg_score, 100),
                live_inbox_count = COALESCE(sub.live_count, 0),
                dead_inbox_count = COALESCE(sub.dead_count, 0),
                health_percentage = CASE
                    WHEN COALESCE(sub.total_count, 0) > 0
                    THEN (COALESCE(sub.live_count, 0)::DECIMAL / sub.total_count * 100)
                    ELSE 100
                END,
                updated_at = NOW()
            FROM (
                SELECT
                    domain_id,
                    AVG(COALESCE(health_score, 100))::INTEGER as avg_score,
                    COUNT(*) as total_count,
                    COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,
                    COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,
                    COUNT(*) FILTER (WHERE health_score < 60) as unhealthy_count,
                    -- Connection status for operational capacity
                    COUNT(*) FILTER (WHERE inbox_state = 'live' AND status = 'Connected') as connected_count,
                    COUNT(*) FILTER (WHERE inbox_state = 'live' AND status IN ('Not connected', 'Disconnected')) as disconnected_count
                FROM sender_accounts
                WHERE workspace_id = $1
                AND domain_id IS NOT NULL
                GROUP BY domain_id
            ) sub
            WHERE d.id = sub.domain_id
            AND d.workspace_id = $1
        """, workspace_id)

        # Recalculate domain complaint rates for all domains in workspace
        try:
            await self.db.execute(
                "SELECT recalculate_all_domain_complaint_rates($1)", workspace_id
            )
        except Exception as e:
            print(f"    [WARNING] Could not recalculate complaint rates: {e}")

        # Rate-based + trigger-aware domain state update:
        # - Domains in 'monitoring' are NOT overridden (handled by evaluate_monitoring_domains)
        # - Complaint rate > 1.0% = dead
        # - >30% unhealthy (min 2 unhealthy) = dead (capacity safety net, size-aware)
        # - Complaint rate > 0.3% = flagged
        # - 1 reputation kill = flagged (for non-spam triggers like hard_blocked_24h)
        # - Otherwise = live
        await self.db.execute("""
            UPDATE domains d
            SET
                domain_state = CASE
                    -- Don't override monitoring state (handled by evaluate_monitoring_domains)
                    WHEN d.domain_state = 'monitoring' THEN 'monitoring'
                    -- Complaint rate > 1.0% = dead
                    WHEN COALESCE(d.domain_complaint_rate_7d, 0) >= $2 THEN 'dead'
                    -- Small-domain capacity safety net (Google 3-inbox/domain math):
                    -- total ≤ 5 AND dead ≥ 2 → retire entire domain. CEO commitment
                    -- for 50k sends/month requires cross-domain promotion to fill
                    -- the gap; keeping the lone surviving inbox 'live' would mean
                    -- the domain's reputation rests on a single account.
                    WHEN sub.total_count > 0
                        AND sub.total_count <= 5
                        AND sub.dead_count >= 2 THEN 'dead'
                    -- Legacy size-aware unhealthy% rule (Microsoft 52-inbox domains).
                    WHEN sub.total_count > 0
                        AND (sub.unhealthy_count::numeric / sub.total_count) > $3
                        AND (sub.total_count >= 10 OR sub.unhealthy_count >= $4) THEN 'dead'
                    -- Complaint rate > 0.3% = flagged
                    WHEN COALESCE(d.domain_complaint_rate_7d, 0) >= $5 THEN 'flagged'
                    -- 1+ reputation kills = flagged. INTENTIONAL: No time window on
                    -- reputation_dead. Domains with past reputation kills stay 'flagged'
                    -- permanently. domain_complaint_rate_7d provides time-windowed
                    -- escalation to 'dead'. This prevents compromised domains from
                    -- silently recovering. Monitoring evaluates escalation separately.
                    WHEN COALESCE(sub.reputation_dead, 0) >= 1 THEN 'flagged'
                    -- Otherwise live
                    ELSE 'live'
                END::domain_state,
                updated_at = NOW()
            FROM (
                SELECT domain_id,
                    COUNT(*) as total_count,
                    COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,
                    COUNT(*) FILTER (WHERE health_score < 60) as unhealthy_count,
                    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND (
                        kill_trigger IN ('spam_complaint', 'hard_blocked_24h')
                        OR kill_trigger::text LIKE 'provider_block_%'
                    )) as reputation_dead
                FROM sender_accounts
                WHERE workspace_id = $1 AND domain_id IS NOT NULL AND is_active = TRUE
                GROUP BY domain_id
            ) sub
            WHERE d.id = sub.domain_id
            AND d.workspace_id = $1
            AND d.pool_status != 'cancelled'
        """,
            workspace_id,
            DOMAIN_THRESHOLDS['complaint_rate_burn'],       # $2: 0.01 (1.0%)
            DOMAIN_THRESHOLDS['unhealthy_pause'],           # $3: 0.30 (30%)
            DOMAIN_THRESHOLDS['unhealthy_min_count'],       # $4: 2
            DOMAIN_THRESHOLDS['complaint_rate_flagged'],    # $5: 0.003 (0.3%)
        )

        # Evaluate domains in monitoring state (7-day observation window)
        await self._evaluate_monitoring_domains(workspace_id)

        # Flag domains where ALL live inboxes are disconnected
        await self._flag_all_disconnected_domains(workspace_id)

        # Recalculate domain aggregate metrics (bounce rate, cross-inbox patterns)
        await self._recalculate_workspace_domain_metrics(workspace_id)

        # V3: Check domain-wide bounce rate threshold (>5% = flag domain)
        await self._check_domain_bounce_rate_thresholds(workspace_id)

    async def _evaluate_monitoring_domains(self, workspace_id: UUID):
        """
        Evaluate domains in 'monitoring' state after their observation window.

        This module is ANALYSIS ONLY — it updates domain_state but NEVER burns
        domains (pool_status). Burns are handled exclusively by the kill processor's
        rate-based evaluation path.

        After 7-day window:
        - Rate >= 0.3%: set domain_state = 'dead' (kill processor handles burn decision)
        - Rate 0.1-0.3%: extend monitoring 7 more days
        - Rate < 0.1%: recover to 'live' (domain recovered after inbox kills)
        """
        monitoring_domains = await self.db.fetch("""
            SELECT id, domain_name, domain_complaint_rate_7d,
                   monitoring_started_at, monitoring_reason
            FROM domains
            WHERE workspace_id = $1
              AND domain_state = 'monitoring'
              AND monitoring_started_at IS NOT NULL
        """, workspace_id)

        window_days = DOMAIN_THRESHOLDS['monitoring_window_days']

        for domain in monitoring_domains:
            domain_id = domain['id']
            domain_name = domain['domain_name']
            rate = float(domain['domain_complaint_rate_7d'] or 0)
            started_at = domain['monitoring_started_at']

            # Check if observation window has expired
            now = datetime.now(timezone.utc)
            window_end = started_at + timedelta(days=window_days)

            if now < window_end:
                # Window still active — just log
                days_remaining = (window_end - now).days
                print(f"    [MONITORING] {domain_name}: {days_remaining}d remaining, "
                      f"rate={rate*100:.3f}%")
                continue

            # Window expired — make decision
            if rate >= DOMAIN_THRESHOLDS['complaint_rate_flagged']:
                # Rate >= 0.3% sustained — mark domain dead
                # Kill processor will handle the actual burn when it processes the next kill
                print(f"    [MONITORING → DEAD] {domain_name}: rate {rate*100:.3f}% "
                      f"sustained after {window_days}d — marking dead")

                await self.db.execute("""
                    UPDATE domains
                    SET domain_state = 'dead'::domain_state,
                        monitoring_started_at = NULL,
                        monitoring_reason = NULL,
                        updated_at = NOW()
                    WHERE id = $1
                """, domain_id)

                # Log event (informational — no burn action taken)
                try:
                    await self.db.execute("""
                        INSERT INTO domain_rotation_events (
                            domain_id, workspace_id, event_type,
                            trigger_type, old_status, new_status, notes
                        ) VALUES ($1, $2, 'monitoring_expired', 'spam_complaint',
                                  'monitoring', 'dead',
                                  $3)
                    """, domain_id, workspace_id,
                        f"Monitoring window expired: complaint rate {rate*100:.3f}% "
                        f"exceeded 0.3% threshold. Domain marked dead. "
                        f"Kill processor handles burn decision.")
                except Exception as e:
                    print(f"    [WARNING] Could not log monitoring event: {e}")

            elif rate >= DOMAIN_THRESHOLDS['complaint_rate_healthy']:
                # Rate 0.1-0.3% — borderline, extend monitoring
                print(f"    [MONITORING → EXTEND] {domain_name}: rate {rate*100:.3f}% "
                      f"in 0.1-0.3% range — extending {window_days}d")

                await self.db.execute("""
                    UPDATE domains
                    SET monitoring_started_at = NOW(),
                        monitoring_reason = $2,
                        updated_at = NOW()
                    WHERE id = $1
                """, domain_id,
                    f"Extended monitoring: rate {rate*100:.3f}% borderline "
                    f"(0.1-0.3% range)")

            else:
                # Rate < 0.1% — domain recovered
                print(f"    [MONITORING → LIVE] {domain_name}: rate {rate*100:.3f}% "
                      f"below 0.1% — domain recovered")

                await self.db.execute("""
                    UPDATE domains
                    SET domain_state = 'live'::domain_state,
                        monitoring_started_at = NULL,
                        monitoring_reason = NULL,
                        updated_at = NOW()
                    WHERE id = $1
                """, domain_id)

                # Log recovery event
                try:
                    await self.db.execute("""
                        INSERT INTO domain_rotation_events (
                            domain_id, workspace_id, event_type,
                            trigger_type, old_status, new_status, notes
                        ) VALUES ($1, $2, 'monitoring_recovered', 'spam_complaint',
                                  'monitoring', 'live',
                                  $3)
                    """, domain_id, workspace_id,
                        f"Monitoring window expired: complaint rate {rate*100:.3f}% "
                        f"below 0.1%. Domain recovered to live.")
                except Exception as e:
                    print(f"    [WARNING] Could not log recovery event: {e}")

    async def _recalculate_workspace_domain_metrics(self, workspace_id: UUID):
        """
        Recalculate aggregate metrics for all domains in workspace.

        Updates:
        - domain_bounce_rate_7d (aggregate of all inbox bounce rates)
        - inboxes_with_complaints / inboxes_with_blocks (cross-inbox detection)
        - burn_breakdown (JSONB with trigger type counts)
        """
        try:
            count = await self.db.fetchval(
                "SELECT recalculate_workspace_domain_metrics($1)",
                workspace_id
            )
            if count and count > 0:
                print(f"    [DOMAIN METRICS] Recalculated {count} domains")
        except Exception as e:
            # Don't fail health checks if metrics calc fails
            print(f"    [WARNING] Failed to recalculate workspace domain metrics: {e}")

    async def _check_domain_bounce_rate_thresholds(self, workspace_id: UUID):
        """
        V3 Section 5: Check domain-wide bounce rate thresholds.

        ESP-aware behavior:
        - Entra domains with >5% hard bounce rate OR 2+ blocked inboxes:
          AUTO-BURN via burn_domain_and_promote(). Microsoft gives no warning
          before blocking — recovery takes 2-4 weeks. Must be aggressive.
        - Google domains: FLAG only. Google gives graduated Postmaster warnings
          and burns are handled by kill_processor's spam complaint path.

        Circuit breaker: max ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER burns per
        workspace per cycle to prevent mass burns from transient Microsoft issues.
        """
        # Find domains that exceed thresholds.
        # Calculate hard-bounce-only rate inline (domain_bounce_rate_7d includes soft bounces).
        # Require minimum sends to avoid false positives on low-volume domains.
        flagged_domains = await self.db.fetch("""
            SELECT
                d.id,
                d.domain_name,
                d.domain_bounce_rate_7d,
                d.inboxes_with_complaints,
                d.inboxes_with_blocks,
                d.domain_state,
                d.pool_status,
                d.infrastructure_type,
                COALESCE((
                    SELECT CASE
                        WHEN SUM(sa.total_sends_7d) >= $2
                        THEN SUM(sa.hard_bounces_7d)::DECIMAL / SUM(sa.total_sends_7d)
                        ELSE 0
                    END
                    FROM sender_accounts sa
                    WHERE sa.domain_id = d.id AND sa.is_active = TRUE
                ), 0) as hard_bounce_rate_7d
            FROM domains d
            WHERE d.workspace_id = $1
            AND d.domain_state IN ('live', 'flagged')
            AND d.pool_status IN ('live', 'reserve')
            AND (
                d.domain_bounce_rate_7d > 0.05
                OR d.inboxes_with_complaints >= 2
                OR d.inboxes_with_blocks >= 2
            )
        """, workspace_id, ENTRA_DOMAIN_BURN_MIN_SENDS)

        burns_this_cycle = 0

        for domain in flagged_domains:
            reasons = []
            if domain['domain_bounce_rate_7d'] and domain['domain_bounce_rate_7d'] > 0.05:
                reasons.append(f"bounce_rate={domain['domain_bounce_rate_7d']*100:.1f}%")
            if domain['inboxes_with_complaints'] and domain['inboxes_with_complaints'] >= 2:
                reasons.append(f"complaints_across_{domain['inboxes_with_complaints']}_inboxes")
            if domain['inboxes_with_blocks'] and domain['inboxes_with_blocks'] >= 2:
                reasons.append(f"blocks_across_{domain['inboxes_with_blocks']}_inboxes")

            reason_str = ', '.join(reasons)

            # ESP-aware: Entra domains auto-burn on hard bounce rate or cross-inbox blocks
            if domain['infrastructure_type'] == 'entra':
                hard_bounce_rate = float(domain['hard_bounce_rate_7d'] or 0)
                blocked_count = domain['inboxes_with_blocks'] or 0

                should_burn = (
                    hard_bounce_rate >= float(ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE)
                    or blocked_count >= ENTRA_DOMAIN_BURN_MIN_BLOCKED
                )

                if should_burn and burns_this_cycle < ENTRA_DOMAIN_BURN_CIRCUIT_BREAKER:
                    # Determine burn trigger type
                    if hard_bounce_rate >= float(ENTRA_DOMAIN_BURN_HARD_BOUNCE_RATE):
                        trigger = 'bounce_rate_domain'
                    else:
                        trigger = 'cross_inbox_blocks'

                    try:
                        result = await self.db.fetchrow(
                            "SELECT * FROM burn_domain_and_promote($1, $2)",
                            domain['id'], trigger
                        )
                        burns_this_cycle += 1

                        action = result.get('action', '') if result else 'unknown'
                        promoted = result['promoted_domain_name'] if result and result['promoted_domain_name'] else None

                        # Log rotation event
                        try:
                            await self.db.execute("""
                                INSERT INTO domain_rotation_events (
                                    domain_id, workspace_id, event_type,
                                    trigger_type, old_status, new_status, notes
                                ) VALUES ($1, $2, 'domain_burn', $3,
                                          $4, 'burned', $5)
                            """, domain['id'], workspace_id, trigger,
                                domain['pool_status'], reason_str)
                        except Exception:
                            pass

                        promoted_msg = f", promoted {promoted}" if promoted else ""
                        print(f"    [ENTRA BURN] {domain['domain_name']}: "
                              f"hard_bounce={hard_bounce_rate*100:.1f}%, "
                              f"blocks={blocked_count} — {trigger}{promoted_msg}")

                        # Slack alert
                        if self.alerter:
                            if promoted:
                                action_text = f"Reserve domain `{promoted}` promoted to live."
                            else:
                                action_text = "No reserve domain available to promote."
                            await self.alerter.send_alert(
                                level="critical",
                                title=f"Entra Domain Burned: {domain['domain_name']}",
                                message=(
                                    f"*Trigger:* `{trigger}`\n"
                                    f"*Reasons:* {reason_str}\n"
                                    f"*Hard bounce rate:* {hard_bounce_rate*100:.1f}%\n"
                                    f"*Blocked inboxes:* {blocked_count}\n"
                                    f"*Action:* {action_text}"
                                ),
                                context={
                                    "domain": domain['domain_name'],
                                    "trigger": trigger,
                                    "hard_bounce_rate": hard_bounce_rate,
                                    "action": action
                                }
                            )
                        continue

                    except Exception as e:
                        print(f"    [ERROR] Failed to burn Entra domain {domain['domain_name']}: {e}")
                        # Fall through to flag instead

                elif should_burn:
                    reason_str += " (circuit breaker: burn deferred to next cycle)"

            # Default path: flag domain (Google, unknown ESP, or circuit breaker hit)
            await self.db.execute("""
                UPDATE domains
                SET domain_state = 'flagged', updated_at = NOW()
                WHERE id = $1
            """, domain['id'])

            print(f"    [DOMAIN FLAGGED] {domain['domain_name']}: {reason_str}")

            if self.alerter:
                await self.alerter.alert_domain_flagged(
                    domain=domain['domain_name'],
                    reason=reason_str
                )

    async def _flag_all_disconnected_domains(self, workspace_id: UUID):
        """
        Flag domains where ALL live inboxes are disconnected AND need attention.

        These domains have 0 operational capacity despite having live inboxes.
        This is separate from kill-based logic - it's about connection status.

        ESP-aware thresholds (per EmailBison support re: IMAP behavior):
        - Microsoft: IMAP disconnects are transient (~10 min auto-reconnect).
          Only flag if disconnected > 48 hours continuously.
        - Gmail/other: Disconnects almost always mean expired OAuth.
          Flag if disconnected > 24 hours.
        """
        # Find domains where all live inboxes are disconnected
        # AND at least one inbox has been disconnected past the ESP-aware threshold
        disconnected_domains = await self.db.fetch("""
            SELECT
                d.id,
                d.domain_name,
                d.domain_state,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_count,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected_count,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')) as disconnected_count,
                -- How many actually need attention (past ESP-aware threshold)?
                COUNT(*) FILTER (
                    WHERE sa.inbox_state = 'live'
                    AND sa.status IN ('Not connected', 'Disconnected')
                    AND sa.disconnected_at IS NOT NULL
                    AND (
                        (sa.esp = 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '48 hours')
                        OR (sa.esp != 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '24 hours')
                    )
                ) as needs_attention_count
            FROM domains d
            JOIN sender_accounts sa ON sa.domain_id = d.id
            WHERE d.workspace_id = $1
            AND d.domain_state = 'live'  -- Only check live domains
            AND d.pool_status != 'cancelled'
            GROUP BY d.id
            HAVING
                -- Has live inboxes
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live') > 0
                -- BUT none are connected (all disconnected)
                AND COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') = 0
                -- AND at least one inbox is past ESP-aware attention threshold
                -- (filters out transient Microsoft IMAP blips)
                AND COUNT(*) FILTER (
                    WHERE sa.inbox_state = 'live'
                    AND sa.status IN ('Not connected', 'Disconnected')
                    AND sa.disconnected_at IS NOT NULL
                    AND (
                        (sa.esp = 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '48 hours')
                        OR (sa.esp != 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '24 hours')
                    )
                ) > 0
        """, workspace_id)

        for domain in disconnected_domains:
            # Flag the domain
            await self.db.execute("""
                UPDATE domains
                SET
                    domain_state = 'flagged',
                    updated_at = NOW()
                WHERE id = $1
            """, domain['id'])

            print(
                f"    [DOMAIN FLAGGED] {domain['domain_name']}: "
                f"all_disconnected ({domain['disconnected_count']}/{domain['live_count']} live inboxes disconnected)"
            )

            # Alert
            if self.alerter:
                await self.alerter.alert_domain_flagged(
                    domain=domain['domain_name'],
                    reason=f"all_disconnected ({domain['disconnected_count']}/{domain['live_count']} live)"
                )

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
        """Reset 24h counters (run daily at midnight).

        Resets:
        - hard_bounces_24h (combined)
        - hard_blocked_24h (spam/policy rejections)
        - hard_unknown_24h (bad addresses)
        - total_sends_24h  (campaign send count, migration 095)

        sync_warmup re-populates total_sends_24h on its next pull from
        EmailBison; this reset just bounds the counter to today's window
        in case the worker restarts or sync is delayed.
        """
        result = await self.db.execute("""
            UPDATE sender_accounts
            SET
                hard_bounces_24h = 0,
                hard_blocked_24h = 0,
                hard_unknown_24h = 0,
                total_sends_24h = 0,
                updated_at = NOW()
            WHERE hard_bounces_24h > 0
               OR hard_blocked_24h > 0
               OR hard_unknown_24h > 0
               OR total_sends_24h > 0
        """)
        print(f"[HealthCheck] Reset 24h counters (bounces + sends): {result}")

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
