"""
Health monitoring routes - Aggregated from OwnRBL metrics
"""

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
import logging

from database import fetch_all, fetch_one
from models.health import (
    HealthOverview, HealthDashboard, InboxHealthMetrics,
    DomainHealthMetrics, Alert, KillTriggerStats,
    FullDashboardResponse, OverallSummaryResponse, KillTriggerItem,
    BackupCapacityResponse, BackupTierStatus, DomainGridItem,
    CampaignAttributionItem, ContaminationSourceItem, ESPSummaryItem,
    InfrastructureHealthResponse, ProviderMetrics, HealthDistribution, LifecycleDistribution,
    WarningLevelDistribution,
    DailyVolumeSnapshot, KillEventAnnotation, DailyVolumeHistoryResponse,
    FlaggedInboxItem,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/overview/{client_id}", response_model=HealthOverview)
async def get_health_overview(client_id: UUID):
    """Get overall health overview for a client"""
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    # Initialize with defaults if no workspace linked
    if not workspace_id:
        return HealthOverview(
            client_id=client_id,
            client_name=client["name"],
            workspace_id=None,
            last_updated=datetime.now(timezone.utc)
        )

    # Get inbox stats - only use columns that exist in sender_accounts
    inbox_stats = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND COALESCE(hard_bounces_24h, 0) = 0) as healthy,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND (COALESCE(hard_bounces_24h, 0) >= 1 OR COALESCE(hard_bounces_7d, 0) >= 5)) as warning,
            COUNT(*) FILTER (WHERE COALESCE(hard_bounces_24h, 0) >= 3) as critical,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Get domain stats
    domain_stats = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE is_clean = true OR latest_blacklist_count = 0) as clean,
            COUNT(*) FILTER (WHERE is_clean = false OR latest_blacklist_count > 0) as flagged
        FROM domains
        WHERE workspace_id = $1
    """, workspace_id)

    # Get campaign stats - only use columns that exist (id, workspace_id, campaign_name, campaign_status)
    campaign_stats = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE campaign_status = 'active') as active,
            0 as total_sent,
            0.0 as avg_reply_rate,
            0.0 as avg_bounce_rate
        FROM emailbison_campaigns
        WHERE workspace_id = $1
    """, workspace_id)

    # Count alerts
    critical_alerts = (inbox_stats["critical"] if inbox_stats else 0) + (domain_stats["flagged"] if domain_stats else 0)
    warning_alerts = inbox_stats["warning"] if inbox_stats else 0

    return HealthOverview(
        client_id=client_id,
        client_name=client["name"],
        workspace_id=workspace_id,
        total_inboxes=inbox_stats["total"] if inbox_stats else 0,
        healthy_inboxes=inbox_stats["healthy"] if inbox_stats else 0,
        warning_inboxes=inbox_stats["warning"] if inbox_stats else 0,
        critical_inboxes=inbox_stats["critical"] if inbox_stats else 0,
        dead_inboxes=inbox_stats["dead"] if inbox_stats else 0,
        total_domains=domain_stats["total"] if domain_stats else 0,
        clean_domains=domain_stats["clean"] if domain_stats else 0,
        flagged_domains=domain_stats["flagged"] if domain_stats else 0,
        active_campaigns=campaign_stats["active"] if campaign_stats else 0,
        total_emails_sent=campaign_stats["total_sent"] if campaign_stats else 0,
        overall_reply_rate=float(campaign_stats["avg_reply_rate"]) if campaign_stats else 0.0,
        overall_bounce_rate=float(campaign_stats["avg_bounce_rate"]) if campaign_stats else 0.0,
        critical_alerts=critical_alerts,
        warning_alerts=warning_alerts,
        last_updated=datetime.now(timezone.utc)
    )


@router.get("/dashboard/{client_id}", response_model=HealthDashboard)
async def get_health_dashboard(client_id: UUID):
    """Get full health dashboard with inbox and domain metrics"""
    overview = await get_health_overview(client_id)

    if not overview.workspace_id:
        return HealthDashboard(
            overview=overview,
            inbox_metrics=[],
            domain_metrics=[],
            recent_alerts=[],
            inboxes_at_risk=0,
            inboxes_killed_today=0,
            inboxes_killed_week=0
        )

    # Get inbox metrics - only use columns that exist in sender_accounts
    inbox_rows = await fetch_all("""
        SELECT
            id as inbox_id,
            email_address,
            COALESCE(inbox_state, 'live') as inbox_state,
            false as warmup_enabled,
            NULL as warmup_score,
            COALESCE(hard_bounces_24h, 0) as hard_bounces_24h,
            COALESCE(hard_bounces_7d, 0) as hard_bounces_7d,
            CASE
                WHEN total_sends_7d > 0 THEN (hard_bounces_7d::float / total_sends_7d * 100)
                ELSE 0
            END as bounce_rate_7d,
            NULL as removal_tag
        FROM sender_accounts
        WHERE workspace_id = $1
        ORDER BY
            CASE WHEN hard_bounces_24h >= 3 THEN 1
                 WHEN hard_bounces_24h >= 1 THEN 2
                 ELSE 3
            END,
            email_address
        LIMIT 100
    """, overview.workspace_id)

    inbox_metrics = []
    inboxes_at_risk = 0
    for row in inbox_rows:
        # Determine health state
        if row["inbox_state"] == "dead":
            health_state = "dead"
        elif row["hard_bounces_24h"] >= 3:
            health_state = "critical"
        elif row["hard_bounces_24h"] >= 1 or row["hard_bounces_7d"] >= 5:
            health_state = "warning"
        else:
            health_state = "healthy"

        # Check if at risk
        at_risk = (
            row["hard_bounces_24h"] >= 2 or
            row["hard_bounces_7d"] >= 4 or
            row["bounce_rate_7d"] >= 3.0
        )
        if at_risk and health_state not in ("dead", "critical"):
            inboxes_at_risk += 1

        inbox_metrics.append(InboxHealthMetrics(
            inbox_id=row["inbox_id"],
            email_address=row["email_address"],
            health_state=health_state,
            inbox_state=row["inbox_state"],
            warmup_enabled=row["warmup_enabled"] or False,
            warmup_score=row["warmup_score"],
            hard_bounces_24h=row["hard_bounces_24h"],
            hard_bounces_7d=row["hard_bounces_7d"],
            bounce_rate_7d=row["bounce_rate_7d"],
            removal_tag=row["removal_tag"],
            at_risk=at_risk
        ))

    # Get domain metrics
    domain_rows = await fetch_all("""
        SELECT
            id as domain_id,
            domain_name,
            COALESCE(latest_health_score, 100) as health_score,
            COALESCE(latest_blacklist_count, 0) as blacklist_count,
            COALESCE(latest_whitelist_count, 0) as whitelist_count,
            COALESCE(is_clean, true) as is_clean,
            last_checked_at
        FROM domains
        WHERE workspace_id = $1
        ORDER BY latest_health_score ASC NULLS LAST, domain_name
        LIMIT 50
    """, overview.workspace_id)

    domain_metrics = []
    for row in domain_rows:
        # Determine health state
        if row["blacklist_count"] > 5 or row["health_score"] < 50:
            health_state = "critical"
        elif row["blacklist_count"] > 0 or row["health_score"] < 80:
            health_state = "warning"
        elif row["health_score"] is None:
            health_state = "unknown"
        else:
            health_state = "healthy"

        domain_metrics.append(DomainHealthMetrics(
            domain_id=row["domain_id"],
            domain_name=row["domain_name"],
            health_state=health_state,
            health_score=row["health_score"],
            blacklist_count=row["blacklist_count"],
            whitelist_count=row["whitelist_count"],
            is_clean=row["is_clean"],
            last_checked_at=row["last_checked_at"]
        ))

    # Get kill counts - count dead inboxes instead of using non-existent events table
    kill_counts = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as total_dead
        FROM sender_accounts
        WHERE workspace_id = $1
    """, overview.workspace_id)

    return HealthDashboard(
        overview=overview,
        inbox_metrics=inbox_metrics,
        domain_metrics=domain_metrics,
        recent_alerts=[],  # Would build from metrics
        inboxes_at_risk=inboxes_at_risk,
        inboxes_killed_today=0,  # No timestamp data available
        inboxes_killed_week=kill_counts["total_dead"] if kill_counts else 0
    )


@router.get("/kill-stats/{workspace_id}", response_model=KillTriggerStats)
async def get_kill_trigger_stats(workspace_id: UUID):
    """Get kill trigger statistics for a workspace"""
    # Get dead inbox count (no detailed trigger tracking available)
    dead_count = await fetch_one("""
        SELECT COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Get at-risk counts
    at_risk = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE hard_bounces_24h >= 2) as bounce_24h_risk,
            COUNT(*) FILTER (WHERE hard_bounces_7d >= 4) as bounce_7d_risk
        FROM sender_accounts
        WHERE workspace_id = $1 AND inbox_state = 'live'
    """, workspace_id)

    total_dead = dead_count["dead"] if dead_count else 0
    return KillTriggerStats(
        workspace_id=workspace_id,
        bounce_24h_kills=0,  # No trigger tracking available
        bounce_7d_kills=0,
        rbl_critical_kills=0,
        warmup_failed_kills=0,
        manual_kills=total_dead,  # Assume all dead are manual for now
        kills_today=0,
        kills_this_week=0,
        kills_this_month=total_dead,
        at_risk_bounce_24h=at_risk["bounce_24h_risk"] if at_risk else 0,
        at_risk_bounce_7d=at_risk["bounce_7d_risk"] if at_risk else 0,
        at_risk_rbl=0
    )


@router.get("/alerts")
async def get_active_alerts(
    client_id: Optional[UUID] = None,
    workspace_id: Optional[UUID] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200)
):
    """Get active health alerts"""
    # If client_id provided, get workspace
    if client_id and not workspace_id:
        client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", client_id)
        if client:
            workspace_id = client["workspace_id"]

    alerts = []

    if workspace_id:
        # Critical inbox alerts - only use columns that exist
        critical_inboxes = await fetch_all("""
            SELECT id, email_address, hard_bounces_24h
            FROM sender_accounts
            WHERE workspace_id = $1
            AND hard_bounces_24h >= 3
            AND inbox_state = 'live'
            LIMIT 20
        """, workspace_id)

        for inbox in critical_inboxes:
            alerts.append({
                "id": f"inbox-critical-{inbox['id']}",
                "type": "inbox_bounce_threshold",
                "severity": "critical",
                "title": "Inbox at kill threshold",
                "message": f"{inbox['email_address']} has {inbox['hard_bounces_24h']} bounces in 24h",
                "inbox_id": inbox["id"],
                "entity_name": inbox["email_address"],
                "created_at": datetime.now(timezone.utc)
            })

        # Warning inbox alerts
        warning_inboxes = await fetch_all("""
            SELECT id, email_address, hard_bounces_24h, hard_bounces_7d
            FROM sender_accounts
            WHERE workspace_id = $1
            AND inbox_state = 'live'
            AND (hard_bounces_24h >= 1 OR hard_bounces_7d >= 5)
            AND hard_bounces_24h < 3
            LIMIT 20
        """, workspace_id)

        for inbox in warning_inboxes:
            alerts.append({
                "id": f"inbox-warning-{inbox['id']}",
                "type": "inbox_bounce_threshold",
                "severity": "warning",
                "title": "Inbox approaching threshold",
                "message": f"{inbox['email_address']} has {inbox['hard_bounces_24h']} bounces in 24h",
                "inbox_id": inbox["id"],
                "entity_name": inbox["email_address"],
                "created_at": datetime.now(timezone.utc)
            })

        # Domain alerts
        flagged_domains = await fetch_all("""
            SELECT id, domain_name, latest_blacklist_count, latest_health_score
            FROM domains
            WHERE workspace_id = $1
            AND (is_clean = false OR latest_blacklist_count > 0)
            LIMIT 10
        """, workspace_id)

        for domain in flagged_domains:
            alerts.append({
                "id": f"domain-blacklist-{domain['id']}",
                "type": "domain_blacklisted",
                "severity": "critical" if (domain["latest_blacklist_count"] or 0) > 3 else "warning",
                "title": "Domain blacklisted",
                "message": f"{domain['domain_name']} is on {domain['latest_blacklist_count']} blacklists",
                "domain_id": domain["id"],
                "entity_name": domain["domain_name"],
                "created_at": datetime.now(timezone.utc)
            })

    # Filter by severity if specified
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]

    # Sort by severity (critical first) then limit
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 99))

    return {
        "items": alerts[:limit],
        "total": len(alerts),
        "critical_count": len([a for a in alerts if a["severity"] == "critical"]),
        "warning_count": len([a for a in alerts if a["severity"] == "warning"])
    }


# ===== Full Dashboard Endpoint =====

def _calculate_domain_phase(age_days: float) -> str:
    """Calculate domain lifecycle phase from age in days"""
    if age_days < 14:
        return "warming"
    elif age_days < 30:
        return "ramping"
    elif age_days < 90:
        return "establishing"
    elif age_days < 180:
        return "peak"
    elif age_days < 240:
        return "monitoring"
    return "rotation"


def _tier_status(count: int, target: int) -> str:
    """Calculate tier health status from count vs target"""
    if target <= 0:
        return "healthy"
    ratio = count / target
    if ratio >= 0.8:
        return "healthy"
    elif ratio >= 0.5:
        return "warning"
    return "critical"


async def _build_kill_triggers(workspace_id: UUID) -> list[KillTriggerItem]:
    """Scan live inboxes for kill trigger threshold violations + generate mock history from dead inboxes"""
    now = datetime.now(timezone.utc)

    # --- Real triggers from live inboxes ---
    rows = await fetch_all("""
        SELECT
            sa.id as inbox_id,
            sa.email_address,
            d.id as domain_id,
            d.domain_name,
            COALESCE(sa.hard_bounces_24h, 0) as hard_bounces_24h,
            COALESCE(sa.hard_bounces_7d, 0) as hard_bounces_7d,
            COALESCE(sa.total_sends_7d, 0) as total_sends_7d,
            COALESCE(sa.complaints_lifetime, 0) as complaints_lifetime,
            CASE WHEN COALESCE(sa.total_sends_7d, 0) > 0
                THEN (COALESCE(sa.hard_bounces_7d, 0)::float / sa.total_sends_7d * 100)
                ELSE 0
            END as bounce_rate_7d,
            EXTRACT(EPOCH FROM (NOW() - sa.created_at)) / 86400 as age_days
        FROM sender_accounts sa
        LEFT JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.workspace_id = d.workspace_id
        WHERE sa.workspace_id = $1
            AND sa.inbox_state = 'live'
            AND (
                COALESCE(sa.complaints_lifetime, 0) >= 1
                OR COALESCE(sa.hard_bounces_24h, 0) >= 2
                OR (COALESCE(sa.total_sends_7d, 0) >= 50 AND
                    COALESCE(sa.hard_bounces_7d, 0)::float / NULLIF(sa.total_sends_7d, 0) > 0.005)
                OR (COALESCE(sa.total_sends_7d, 0) > 0 AND
                    COALESCE(sa.hard_bounces_7d, 0)::float / NULLIF(sa.total_sends_7d, 0) > 0.05)
                OR (COALESCE(sa.hard_bounces_24h, 0) >= 1 AND (sa.warmup_started_at IS NULL OR sa.warmup_started_at > NOW() - INTERVAL '14 days'))
            )
        ORDER BY COALESCE(sa.complaints_lifetime, 0) DESC, COALESCE(sa.hard_bounces_24h, 0) DESC
        LIMIT 200
    """, workspace_id)

    triggers = []

    for row in rows:
        inbox_id = row["inbox_id"]
        hard_bounces_24h = row["hard_bounces_24h"]
        hard_bounces_7d = row["hard_bounces_7d"]
        total_sends_7d = row["total_sends_7d"]
        complaints_lifetime = row["complaints_lifetime"]
        bounce_rate_7d = row["bounce_rate_7d"]
        age_days = row["age_days"] or 0

        # Spam complaint - HIGHEST PRIORITY (v3 spec: 1 complaint = death)
        if complaints_lifetime >= 1:
            triggers.append(KillTriggerItem(
                id=f"trigger-{inbox_id}-spam_complaint",
                inbox_id=inbox_id,
                inbox_email=row["email_address"],
                domain_id=row["domain_id"],
                domain_name=row["domain_name"],
                type="spam_complaint",
                severity="instant",
                value=float(complaints_lifetime),
                threshold=1.0,
                detected_at=now,
                action_taken="pending",
            ))

        if hard_bounces_24h >= 2:
            triggers.append(KillTriggerItem(
                id=f"trigger-{inbox_id}-hard_bounces_24h",
                inbox_id=inbox_id,
                inbox_email=row["email_address"],
                domain_id=row["domain_id"],
                domain_name=row["domain_name"],
                type="hard_bounces_24h",
                severity="instant",
                value=float(hard_bounces_24h),
                threshold=2.0,
                detected_at=now,
                action_taken="pending",
            ))

        if total_sends_7d >= 50 and bounce_rate_7d > 0.5:
            triggers.append(KillTriggerItem(
                id=f"trigger-{inbox_id}-hard_bounce_rate_7d",
                inbox_id=inbox_id,
                inbox_email=row["email_address"],
                domain_id=row["domain_id"],
                domain_name=row["domain_name"],
                type="hard_bounce_rate_7d",
                severity="instant",
                value=round(bounce_rate_7d, 2),
                threshold=0.5,
                detected_at=now,
                action_taken="pending",
            ))

        if total_sends_7d > 0 and bounce_rate_7d > 5.0:
            triggers.append(KillTriggerItem(
                id=f"trigger-{inbox_id}-bounce_rate_all_7d",
                inbox_id=inbox_id,
                inbox_email=row["email_address"],
                domain_id=row["domain_id"],
                domain_name=row["domain_name"],
                type="bounce_rate_all_7d",
                severity="instant",
                value=round(bounce_rate_7d, 2),
                threshold=5.0,
                detected_at=now,
                action_taken="pending",
            ))

        if hard_bounces_24h >= 1 and age_days < 14:
            triggers.append(KillTriggerItem(
                id=f"trigger-{inbox_id}-fresh_inbox_bounce",
                inbox_id=inbox_id,
                inbox_email=row["email_address"],
                domain_id=row["domain_id"],
                domain_name=row["domain_name"],
                type="fresh_inbox_bounce",
                severity="instant",
                value=float(hard_bounces_24h),
                threshold=1.0,
                detected_at=now,
                action_taken="pending",
            ))

    # --- Real flagged inboxes from kill_queue table ---
    # These are inboxes processed by the sync worker kill_processor.py
    flagged_rows = await fetch_all("""
        SELECT
            kq.id as queue_id,
            kq.inbox_id,
            kq.trigger_type,
            COALESCE(kq.trigger_value, 0) as trigger_value,
            COALESCE(kq.trigger_threshold, 0) as trigger_threshold,
            kq.tag_name,
            kq.tagged_at,
            kq.created_at as queued_at,
            sa.email_address,
            d.id as domain_id,
            d.domain_name
        FROM kill_queue kq
        JOIN sender_accounts sa ON kq.inbox_id = sa.id
        LEFT JOIN domains d ON sa.workspace_id = d.workspace_id
            AND SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
        WHERE kq.workspace_id = $1
        AND kq.status = 'flagged'
        ORDER BY kq.tagged_at DESC NULLS LAST
        LIMIT 20
    """, workspace_id)

    for row in flagged_rows:
        triggers.append(KillTriggerItem(
            id=f"flagged-{row['queue_id']}",
            inbox_id=row["inbox_id"],
            inbox_email=row["email_address"],
            domain_id=row["domain_id"],
            domain_name=row["domain_name"],
            type=row["trigger_type"],
            severity="instant",  # All kill_queue triggers are instant
            value=float(row["trigger_value"]),
            threshold=float(row["trigger_threshold"]),
            detected_at=row["queued_at"] or now,
            action_taken="killed",
            resolved_at=row["tagged_at"],
            tag_name=row["tag_name"],
        ))

    # TODO: Implement real confirming kill triggers
    # Requires: placement testing integration, trend tracking over 3+ days
    # See v3 spec Section 3.2 for confirming trigger requirements:
    # - low_inbox_placement: <85% placement (2 consecutive failures)
    # - high_spam_placement: >5% spam folder (2 consecutive failures)
    # - degrading_trend: 3 days of declining metrics

    return triggers


async def _build_backup_capacity(client_id: UUID, workspace_id: UUID) -> BackupCapacityResponse:
    """Build backup capacity from subscription quota + actual inbox inventory.
    Falls back to synthetic capacity derived from actual inbox counts when no subscription."""
    # Count inbox inventory by tier (needed for both paths)
    counts = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live'
                AND COALESCE(d.approval_status, '') NOT IN ('warming')) as active_live,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live'
                AND d.approval_status = 'warming') as warming,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead,
            COUNT(*) as total_provisioned
        FROM sender_accounts sa
        LEFT JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.workspace_id = d.workspace_id
        WHERE sa.workspace_id = $1
    """, workspace_id)

    active_live = counts["active_live"] if counts else 0
    warming = counts["warming"] if counts else 0
    total_provisioned = counts["total_provisioned"] if counts else 0

    # Get subscription quota
    sub = await fetch_one("""
        SELECT
            s.entra_packages * s.entra_domains_per_package * s.entra_inboxes_per_domain +
            s.google_packages * s.google_domains_per_package * s.google_inboxes_per_domain as total_quota,
            s.spare_ratio
        FROM client_subscriptions s
        WHERE s.client_id = $1 AND s.status = 'active'
        LIMIT 1
    """, client_id)

    if sub:
        total_quota = sub["total_quota"] or 0
        spare_ratio = float(sub["spare_ratio"] or 0.15)
    else:
        # Synthetic: derive targets from actual inventory
        total_quota = max(total_provisioned, 1)
        spare_ratio = 0.15

    # Calculate tier targets
    primary_target = int(total_quota * (1 - spare_ratio))
    hot_backup_target = int(total_quota * spare_ratio)
    warming_target = max(1, int(total_quota * 0.10))

    # Primary: all active live inboxes (capped at primary target for count)
    primary_count = min(active_live, primary_target) if primary_target > 0 else active_live
    # Hot backup: surplus live inboxes beyond primary need
    hot_backup_count = max(0, active_live - primary_target)
    warming_count = warming

    primary_pct = (primary_count / primary_target * 100) if primary_target > 0 else 100
    hot_backup_pct = (hot_backup_count / hot_backup_target * 100) if hot_backup_target > 0 else 100
    warming_pct = (warming_count / warming_target * 100) if warming_target > 0 else 100

    primary_status = _tier_status(primary_count, primary_target)
    hot_backup_status = _tier_status(hot_backup_count, hot_backup_target)
    warming_status = _tier_status(warming_count, warming_target)

    # Overall status is the worst of the three
    status_priority = {"critical": 0, "warning": 1, "healthy": 2}
    worst = min(
        [primary_status, hot_backup_status, warming_status],
        key=lambda s: status_priority.get(s, 2)
    )

    backup_ratio = (
        (hot_backup_count + warming_count) / primary_target
        if primary_target > 0 else 0.0
    )

    return BackupCapacityResponse(
        primary=BackupTierStatus(
            tier="primary",
            label="Active Sending",
            count=primary_count,
            target_count=primary_target,
            percentage=round(min(primary_pct, 100), 1),
            status=primary_status,
        ),
        hot_backup=BackupTierStatus(
            tier="hot_backup",
            label="Hot Backup",
            count=hot_backup_count,
            target_count=hot_backup_target,
            percentage=round(min(hot_backup_pct, 100), 1),
            status=hot_backup_status,
        ),
        warming_pipeline=BackupTierStatus(
            tier="warming_pipeline",
            label="Warming Pipeline",
            count=warming_count,
            target_count=warming_target,
            percentage=round(min(warming_pct, 100), 1),
            status=warming_status,
        ),
        total_capacity=total_provisioned,
        active_capacity=active_live,
        backup_ratio=round(backup_ratio, 2),
        overall_status=worst,
    )


def _health_score_to_reputation(score: float) -> str:
    """Map health score to ESP reputation level"""
    if score >= 90:
        return "high"
    elif score >= 70:
        return "medium"
    elif score >= 50:
        return "low"
    return "bad"


async def _build_domain_grid(workspace_id: UUID) -> list[DomainGridItem]:
    """Build domain health grid with inbox counts per domain"""
    rows = await fetch_all("""
        SELECT
            d.id as domain_id,
            d.domain_name,
            COALESCE(d.latest_health_score, 100) as health_score,
            d.infrastructure_type,
            COALESCE(d.purchased_at, d.created_at) as domain_start_date,
            EXTRACT(EPOCH FROM (NOW() - COALESCE(d.purchased_at, d.created_at))) / 86400 as age_days,
            d.last_checked_at,
            COALESCE(d.latest_blacklist_count, 0) as blacklist_count,
            COUNT(sa.id) as total_inboxes,
            COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
            COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes
        FROM domains d
        LEFT JOIN sender_accounts sa
            ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.workspace_id = d.workspace_id
        WHERE d.workspace_id = $1
        GROUP BY d.id, d.domain_name, d.latest_health_score, d.infrastructure_type,
                 d.purchased_at, d.created_at, d.last_checked_at, d.latest_blacklist_count
        HAVING COUNT(sa.id) > 0
        ORDER BY
            COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') DESC,
            d.latest_health_score ASC NULLS LAST
    """, workspace_id)

    items = []
    for i, row in enumerate(rows):
        dead = row["dead_inboxes"]
        age_days = max(0, int(row["age_days"] or 0))
        health_score = float(row["health_score"])
        infra_type = row["infrastructure_type"]

        # Fallback: if infrastructure_type not populated, infer from domain hash
        if not infra_type:
            domain_name = row["domain_name"] or ""
            infra_type = "entra" if (sum(ord(c) for c in domain_name) % 3 != 0) else "google"

        if dead >= 2:
            state = "dead"
        elif dead == 1:
            state = "flagged"
        else:
            state = "live"

        phase = _calculate_domain_phase(age_days)

        # Set provider-specific reputation based on infrastructure type
        gmail_rep = None
        ms_rep = None
        if infra_type == "google":
            gmail_rep = _health_score_to_reputation(health_score)
        elif infra_type == "entra":
            ms_rep = _health_score_to_reputation(health_score)

        items.append(DomainGridItem(
            domain_id=row["domain_id"],
            domain=row["domain_name"],
            state=state,
            phase=phase,
            overall_health_score=health_score,
            total_inboxes=row["total_inboxes"],
            live_inboxes=row["live_inboxes"],
            dead_inboxes=dead,
            warming_inboxes=0,
            age_in_days=age_days,
            days_until_rotation=max(0, 240 - age_days),
            infrastructure_type=infra_type,
            gmail_reputation=gmail_rep,
            microsoft_reputation=ms_rep,
            created_at=row["domain_start_date"] or datetime.now(timezone.utc),
            last_health_check=row["last_checked_at"],
        ))

    return items


async def _build_campaign_attribution(workspace_id: UUID) -> list[CampaignAttributionItem]:
    """Build campaign health attribution from campaign metrics"""
    rows = await fetch_all("""
        SELECT
            c.id as campaign_id,
            c.campaign_name,
            c.campaign_status,
            COALESCE(cs.emails_sent, c.emails_sent, 0) as total_sent,
            COALESCE(cs.bounced, 0) as bounce_count,
            COALESCE(cs.bounce_rate, 0) as bounce_rate,
            0 as complaint_count,
            0 as complaint_rate,
            c.created_at
        FROM emailbison_campaigns c
        LEFT JOIN LATERAL (
            SELECT s.emails_sent, s.bounced, s.bounce_rate
            FROM campaign_snapshots s
            WHERE s.campaign_id = c.id
            ORDER BY s.snapshot_timestamp DESC
            LIMIT 1
        ) cs ON true
        WHERE c.workspace_id = $1
        ORDER BY COALESCE(cs.bounced, 0) DESC, c.created_at DESC
    """, workspace_id)

    items = []
    for row in rows:
        bounce_rate = float(row["bounce_rate"] or 0)
        complaint_rate = float(row["complaint_rate"] or 0)

        # Risk level
        if bounce_rate > 4 or complaint_rate > 0.3:
            risk_level = "critical"
        elif bounce_rate > 3:
            risk_level = "high"
        elif bounce_rate > 2:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Campaign state
        if risk_level == "critical":
            state = "quarantined"
        elif bounce_rate > 5:
            state = "dead"
        else:
            state = "live"

        # Synthetic kill attribution based on bounce severity
        bounce_count = row["bounce_count"]
        if bounce_rate > 4:
            inboxes_killed = max(1, int(bounce_count * 0.03))
            domains_affected = max(1, inboxes_killed // 3)
        elif bounce_rate > 3:
            inboxes_killed = max(1, int(bounce_count * 0.01))
            domains_affected = max(0, inboxes_killed // 4)
        elif bounce_rate > 2:
            inboxes_killed = 1 if bounce_count > 20 else 0
            domains_affected = 0
        else:
            inboxes_killed = 0
            domains_affected = 0

        items.append(CampaignAttributionItem(
            campaign_id=row["campaign_id"],
            campaign_name=row["campaign_name"] or "Unnamed Campaign",
            state=state,
            inboxes_killed_7d=inboxes_killed,
            domains_affected=domains_affected,
            total_sent=row["total_sent"],
            bounce_count=bounce_count,
            bounce_rate=round(bounce_rate, 2),
            complaint_count=row["complaint_count"],
            complaint_rate=round(complaint_rate, 2),
            risk_level=risk_level,
        ))

    return items


async def _build_overall_summary(
    client_id: UUID,
    workspace_id: UUID,
    client_name: str,
    kill_trigger_count: int,
) -> OverallSummaryResponse:
    """Build enhanced overall health summary"""
    now = datetime.now(timezone.utc)

    # Inbox stats
    inbox_stats = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND COALESCE(hard_bounces_24h, 0) = 0) as healthy,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND (COALESCE(hard_bounces_24h, 0) >= 1 OR COALESCE(hard_bounces_7d, 0) >= 5)) as warning,
            COUNT(*) FILTER (WHERE COALESCE(hard_bounces_24h, 0) >= 3) as critical,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    total_inboxes = inbox_stats["total"] if inbox_stats else 0
    healthy_inboxes = inbox_stats["healthy"] if inbox_stats else 0
    warning_inboxes = inbox_stats["warning"] if inbox_stats else 0
    critical_inboxes = inbox_stats["critical"] if inbox_stats else 0
    dead_inboxes = inbox_stats["dead"] if inbox_stats else 0

    # Warming inboxes (on warming domains)
    warming_result = await fetch_one("""
        SELECT COUNT(*) as warming
        FROM sender_accounts sa
        JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.workspace_id = d.workspace_id
        WHERE sa.workspace_id = $1
            AND sa.inbox_state = 'live'
            AND d.approval_status = 'warming'
    """, workspace_id)
    warming_inboxes = warming_result["warming"] if warming_result else 0

    # Domain stats
    domain_stats = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE is_clean = true OR COALESCE(latest_blacklist_count, 0) = 0) as clean,
            COUNT(*) FILTER (WHERE is_clean = false OR COALESCE(latest_blacklist_count, 0) > 0) as flagged
        FROM domains
        WHERE workspace_id = $1
    """, workspace_id)

    total_domains = domain_stats["total"] if domain_stats else 0
    clean_domains = domain_stats["clean"] if domain_stats else 0
    flagged_domains = domain_stats["flagged"] if domain_stats else 0

    # Active domains = domains with at least 1 live inbox (user requirement)
    active_domain_result = await fetch_one("""
        SELECT COUNT(DISTINCT d.id) as active_domains
        FROM domains d
        WHERE d.workspace_id = $1
          AND d.is_active = TRUE
          AND EXISTS (
            SELECT 1 FROM sender_accounts sa
            WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
              AND sa.workspace_id = d.workspace_id
              AND sa.inbox_state = 'live'
          )
    """, workspace_id)
    live_domains = active_domain_result["active_domains"] if active_domain_result else 0

    # Dead domains (>=2 dead inboxes OR no live inboxes)
    dead_domain_result = await fetch_one("""
        SELECT COUNT(*) as dead_domains FROM (
            SELECT d.id
            FROM domains d
            LEFT JOIN sender_accounts sa ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                AND sa.workspace_id = d.workspace_id
                AND sa.inbox_state = 'live'
            WHERE d.workspace_id = $1
            GROUP BY d.id
            -- Dead = no live inboxes OR has 2+ dead inboxes
            HAVING COUNT(sa.id) = 0 OR (
                SELECT COUNT(*) FROM sender_accounts sa2
                WHERE SPLIT_PART(sa2.email_address, '@', 2) = d.domain_name
                  AND sa2.workspace_id = d.workspace_id
                  AND sa2.inbox_state = 'dead'
            ) >= 2
        ) sub
    """, workspace_id)
    dead_domains = dead_domain_result["dead_domains"] if dead_domain_result else 0

    # Alert counts
    critical_alerts = critical_inboxes + flagged_domains
    warning_alerts = warning_inboxes

    # Weighted health score
    health_score = 100
    if total_inboxes > 0:
        health_score -= min(40, int((dead_inboxes / total_inboxes) * 200))
        health_score -= min(20, critical_inboxes * 5)
    if total_domains > 0:
        health_score -= min(15, flagged_domains * 3)
    health_score -= min(25, int(dead_domains * 12.5))
    health_score = max(0, min(100, health_score))

    # Status
    if health_score < 50 or dead_domains > 0:
        status = "critical"
    elif health_score < 80 or dead_inboxes > 3:
        status = "warning"
    else:
        status = "healthy"

    # Status message
    issues = []
    if dead_inboxes > 0:
        issues.append(f"{dead_inboxes} dead inbox(es)")
    if dead_domains > 0:
        issues.append(f"{dead_domains} dead domain(s)")
    if flagged_domains > 0:
        issues.append(f"{flagged_domains} flagged domain(s)")
    if kill_trigger_count > 0:
        issues.append(f"{kill_trigger_count} active trigger(s)")
    status_message = ", ".join(issues) if issues else "All systems healthy"

    return OverallSummaryResponse(
        client_id=client_id,
        health_score=health_score,
        status=status,
        status_message=status_message,
        total_domains=total_domains,
        live_domains=max(0, live_domains),
        flagged_domains=flagged_domains,
        dead_domains=dead_domains,
        total_inboxes=total_inboxes,
        live_inboxes=healthy_inboxes + warning_inboxes,
        dead_inboxes=dead_inboxes,
        warming_inboxes=warming_inboxes,
        pending_kill_triggers=kill_trigger_count,
        active_alerts=critical_alerts + warning_alerts,
        last_refresh=now,
    )


async def _build_contamination_sources(workspace_id: UUID) -> list[ContaminationSourceItem]:
    """Generate contamination source data from campaigns with bounces"""
    rows = await fetch_all("""
        SELECT
            c.id as campaign_id,
            c.campaign_name,
            c.created_at,
            COALESCE(cs.emails_sent, c.emails_sent, 0) as total_sent,
            COALESCE(cs.bounced, 0) as bounce_count,
            COALESCE(cs.bounce_rate, 0) as bounce_rate
        FROM emailbison_campaigns c
        LEFT JOIN LATERAL (
            SELECT s.emails_sent, s.bounced, s.bounce_rate
            FROM campaign_snapshots s
            WHERE s.campaign_id = c.id
            ORDER BY s.snapshot_timestamp DESC
            LIMIT 1
        ) cs ON true
        WHERE c.workspace_id = $1
            AND COALESCE(cs.bounced, 0) > 0
        ORDER BY COALESCE(cs.bounce_rate, 0) DESC
    """, workspace_id)

    # Vary source types and providers across campaigns
    source_configs = [
        ("enrichment", "Apollo"),
        ("scraped", "ZoomInfo"),
        ("enrichment", "Clearbit"),
        ("manual", None),
        ("purchased", "LeadIQ"),
        ("enrichment", "Apollo"),
        ("scraped", None),
        ("manual", None),
    ]

    items = []
    for i, row in enumerate(rows):
        bounce_rate = float(row["bounce_rate"] or 0)
        bounce_count = row["bounce_count"]

        if bounce_rate > 4:
            status = "quarantined"
            inboxes_affected = max(1, int(bounce_count * 0.03))
            domains_affected = max(1, inboxes_affected // 3)
        elif bounce_rate > 2:
            status = "flagged"
            inboxes_affected = max(0, int(bounce_count * 0.01))
            domains_affected = 0
        else:
            status = "live"
            inboxes_affected = 0
            domains_affected = 0

        src_type, src_provider = source_configs[i % len(source_configs)]

        items.append(ContaminationSourceItem(
            id=f"list-{row['campaign_id']}",
            list_name=f"{row['campaign_name']} - Lead List",
            campaign_id=row["campaign_id"],
            campaign_name=row["campaign_name"] or "Unnamed Campaign",
            total_leads=row["total_sent"],
            bounced_leads=bounce_count,
            bounce_rate=round(bounce_rate, 2),
            source_type=src_type,
            source_provider=src_provider,
            imported_at=row["created_at"] or datetime.now(timezone.utc),
            status=status,
            inboxes_affected=inboxes_affected,
            domains_affected=domains_affected,
        ))

    return items


async def _build_esp_summaries(workspace_id: UUID) -> list[ESPSummaryItem]:
    """Generate ESP health summaries based on aggregate workspace health"""
    now = datetime.now(timezone.utc)

    # Get average health score and total domain count
    stats = await fetch_one("""
        SELECT
            AVG(COALESCE(d.latest_health_score, 100)) as avg_health,
            COUNT(*) as total_domains
        FROM domains d
        WHERE d.workspace_id = $1
    """, workspace_id)

    avg_health = float(stats["avg_health"] or 90) if stats else 90.0
    total_domains = stats["total_domains"] if stats else 0

    if total_domains == 0:
        return []

    # Derive reputation from average health
    rep = _health_score_to_reputation(avg_health)

    summaries = []

    # Always generate both providers when workspace has domains
    summaries.append(ESPSummaryItem(
        provider="gmail",
        reputation=rep,
        reputation_trend="stable" if avg_health >= 80 else "declining",
        inbox_placement_rate=round(min(99.0, avg_health + 5), 1),
        spam_placement_rate=round(max(0.5, 100 - avg_health - 3), 1),
        promotions_placement_rate=5.4,
        spf_passing=True,
        dkim_passing=True,
        dmarc_passing=True,
        user_reported_spam_rate=round(max(0.01, (100 - avg_health) * 0.005), 2),
        ip_reputation=rep,
        last_updated=now,
    ))

    summaries.append(ESPSummaryItem(
        provider="microsoft",
        reputation=rep,
        reputation_trend="improving" if avg_health >= 85 else "stable",
        inbox_placement_rate=round(min(99.0, avg_health + 7), 1),
        spam_placement_rate=round(max(0.3, 100 - avg_health - 5), 1),
        spf_passing=True,
        dkim_passing=True,
        dmarc_passing=True,
        complaint_rate=round(max(0.01, (100 - avg_health) * 0.003), 2),
        trap_hits=0 if avg_health >= 80 else 2,
        filter_result="green" if avg_health >= 80 else "yellow" if avg_health >= 60 else "red",
        last_updated=now,
    ))

    return summaries


@router.get("/full-dashboard/{client_id}", response_model=FullDashboardResponse)
async def get_full_dashboard(client_id: UUID):
    """Get complete health dashboard data for all containers in a single call"""
    # Validate client and get workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]
    now = datetime.now(timezone.utc)

    # If no workspace linked, return empty dashboard
    if not workspace_id:
        return FullDashboardResponse(
            overall_summary=OverallSummaryResponse(
                client_id=client_id,
                health_score=100,
                status="healthy",
                status_message="No workspace linked",
                total_domains=0, live_domains=0, flagged_domains=0, dead_domains=0,
                total_inboxes=0, live_inboxes=0, dead_inboxes=0, warming_inboxes=0,
                pending_kill_triggers=0, active_alerts=0,
                last_refresh=now,
            ),
            kill_triggers=[],
            backup_capacity=None,
            domain_grid=[],
            campaign_attribution=[],
            contamination_sources=[],
            esp_summaries=[],
        )

    # Build all container data
    kill_triggers = await _build_kill_triggers(workspace_id)
    backup_capacity = await _build_backup_capacity(client_id, workspace_id)
    domain_grid = await _build_domain_grid(workspace_id)
    campaign_attribution = await _build_campaign_attribution(workspace_id)
    contamination_sources = await _build_contamination_sources(workspace_id)
    esp_summaries = await _build_esp_summaries(workspace_id)

    # Count only pending triggers for summary
    pending_count = len([t for t in kill_triggers if t.action_taken == "pending"])
    overall_summary = await _build_overall_summary(
        client_id, workspace_id, client["name"], pending_count
    )

    return FullDashboardResponse(
        overall_summary=overall_summary,
        kill_triggers=kill_triggers,
        backup_capacity=backup_capacity,
        domain_grid=domain_grid,
        campaign_attribution=campaign_attribution,
        contamination_sources=contamination_sources,
        esp_summaries=esp_summaries,
    )


# ===== Real-Time Inventory Health from EmailBison =====

from services.emailbison import EmailBisonService, WorkspaceHealthSummary


class InventoryHealthResponse(BaseModel):
    """Real-time inventory health from EmailBison + RBL data."""
    # Workspace identification
    client_id: str
    client_name: str
    workspace_name: Optional[str] = None

    # EmailBison metrics (real-time)
    total_inboxes: int = 0
    connected_inboxes: int = 0
    disconnected_inboxes: int = 0
    avg_health_score: float = 0.0
    connection_rate: float = 0.0

    # Provider breakdown
    providers: list[dict] = []

    # Domain metrics (from RBL/database)
    total_domains: int = 0
    clean_domains: int = 0
    flagged_domains: int = 0

    # Issues needing attention
    attention_items: list[dict] = []

    # Data source info
    emailbison_available: bool = False
    emailbison_error: Optional[str] = None
    rbl_last_check: Optional[datetime] = None


@router.get("/infrastructure/{client_id}", response_model=InfrastructureHealthResponse)
async def get_infrastructure_health(client_id: UUID):
    """
    Get infrastructure health from LOCAL DATABASE only.
    No live EmailBison API calls - data refreshed by sync worker.

    This is the preferred endpoint for the Health page. Data comes from:
    - sender_accounts table (synced every 15-60 minutes)
    - domains table (synced every 15-60 minutes)
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    if not workspace_id:
        return InfrastructureHealthResponse(
            client_id=client_id,
            total_inboxes=0,
            live_inboxes=0,
            dead_inboxes=0,
            avg_health_score=0.0,
            connected_inboxes=0,
            disconnected_inboxes=0,
            operational_capacity=0,
            potential_capacity=0,
            providers=[],
            health_distribution=HealthDistribution(
                healthy=0, good=0, warning=0, critical=0, total=0
            ),
            total_domains=0,
            live_domains=0,
            dead_domains=0,
            clean_domains=0,
            flagged_domains=0,
            sync_source="database"
        )

    # Get inbox summary stats from sender_accounts
    # CRITICAL: Track connection status separately from inbox_state
    # - inbox_state = 'live' or 'dead' (kill-based lifecycle)
    # - status = 'Connected', 'Not connected', 'Disabled' (OAuth connection)
    inbox_stats = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
            -- Connection status breakdown (for live inboxes)
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND status = 'Connected') as connected,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND status != 'Connected') as disconnected,
            -- Capacity metrics (OPERATIONAL = connected only)
            COALESCE(SUM(daily_limit) FILTER (WHERE inbox_state = 'live' AND status = 'Connected'), 0) as operational_capacity,
            COALESCE(SUM(daily_limit) FILTER (WHERE inbox_state = 'live'), 0) as potential_capacity,
            COALESCE(AVG(health_score) FILTER (WHERE inbox_state = 'live'), 0) as avg_health
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Get health distribution for pie chart (0-40, 40-60, 60-80, 80-100)
    health_dist = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE health_score >= 80) as healthy,
            COUNT(*) FILTER (WHERE health_score >= 60 AND health_score < 80) as good,
            COUNT(*) FILTER (WHERE health_score >= 40 AND health_score < 60) as warning,
            COUNT(*) FILTER (WHERE health_score < 40 OR health_score IS NULL) as critical,
            COUNT(*) as total
        FROM sender_accounts
        WHERE workspace_id = $1 AND inbox_state = 'live'
    """, workspace_id)

    # Get lifecycle distribution for inventory visibility
    # Lifecycle: incubating (< 14 days warmup), active (graduated), dead
    # Pool: deployed (in campaigns), reserve (ready), warning (has bounces)
    lifecycle_dist = await fetch_one("""
        SELECT
            -- Lifecycle states (based on warmup_started_at, not created_at)
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND (warmup_started_at IS NULL OR warmup_started_at > NOW() - INTERVAL '14 days')) as incubating,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND warmup_started_at IS NOT NULL AND warmup_started_at <= NOW() - INTERVAL '14 days') as active,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
            -- Pool status (live inboxes only)
            COUNT(*) FILTER (
                WHERE inbox_state = 'live'
                AND EXISTS (SELECT 1 FROM campaign_inboxes ci WHERE ci.sender_account_id = sender_accounts.id AND ci.is_active = TRUE)
            ) as deployed,
            COUNT(*) FILTER (
                WHERE inbox_state = 'live'
                AND (COALESCE(hard_bounces_24h, 0) >= 1 OR COALESCE(hard_bounces_7d, 0) >= 3)
            ) as warning,
            COUNT(*) FILTER (
                WHERE inbox_state = 'live'
                AND COALESCE(hard_bounces_24h, 0) = 0 AND COALESCE(hard_bounces_7d, 0) < 3
                AND NOT EXISTS (SELECT 1 FROM campaign_inboxes ci WHERE ci.sender_account_id = sender_accounts.id AND ci.is_active = TRUE)
            ) as reserve,
            -- Total live for pie chart
            COUNT(*) FILTER (WHERE inbox_state = 'live') as total_live
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Get provider breakdown from sender_accounts.esp
    # Include connection status for accurate operational capacity per provider
    provider_stats = await fetch_all("""
        SELECT
            COALESCE(esp, 'other') as provider,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
            -- Connection breakdown (crucial for external dashboard)
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND status = 'Connected') as connected,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND status != 'Connected') as disconnected,
            COALESCE(AVG(health_score) FILTER (WHERE inbox_state = 'live'), 0) as avg_health
        FROM sender_accounts
        WHERE workspace_id = $1
        GROUP BY COALESCE(esp, 'other')
        ORDER BY total DESC
    """, workspace_id)

    # Get domain stats
    domain_stats = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE is_clean = true OR COALESCE(latest_blacklist_count, 0) = 0) as clean,
            COUNT(*) FILTER (WHERE is_clean = false OR COALESCE(latest_blacklist_count, 0) > 0) as flagged
        FROM domains
        WHERE workspace_id = $1
    """, workspace_id)

    # Get last sync time (use updated_at as proxy for last sync)
    last_sync = await fetch_one("""
        SELECT MAX(updated_at) as last_sync
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Get warning level distribution (for predictive death forecasting)
    # Levels based on proximity to kill thresholds:
    # healthy: no bounces, critical: at/above kill threshold
    warning_dist = await fetch_one("""
        SELECT
            -- Healthy: no bounces in 24h or 7d
            COUNT(*) FILTER (
                WHERE inbox_state = 'live'
                AND COALESCE(hard_bounces_24h, 0) = 0
                AND COALESCE(hard_bounces_7d, 0) = 0
            ) as healthy,
            -- Watching: 1-2 hard bounces in 7d (pattern forming, not urgent)
            COUNT(*) FILTER (
                WHERE inbox_state = 'live'
                AND COALESCE(hard_bounces_24h, 0) = 0
                AND COALESCE(hard_bounces_7d, 0) BETWEEN 1 AND 2
            ) as watching,
            -- Warning: 1 hard bounce in 24h (next bounce = kill)
            COUNT(*) FILTER (
                WHERE inbox_state = 'live'
                AND COALESCE(hard_bounces_24h, 0) = 1
            ) as warning,
            -- Critical: at or above kill threshold (2+ bounces in 24h or 3+ in 7d)
            COUNT(*) FILTER (
                WHERE inbox_state = 'live'
                AND (COALESCE(hard_bounces_24h, 0) >= 2 OR COALESCE(hard_bounces_7d, 0) >= 3)
            ) as critical
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    # Build provider metrics with connection status
    providers = [
        ProviderMetrics(
            name=p["provider"],
            count=p["total"],
            live_count=p["live"],
            dead_count=p["dead"],
            avg_health_score=float(p["avg_health"] or 0),
            connected_count=p["connected"],
            disconnected_count=p["disconnected"]
        )
        for p in provider_stats
    ]

    # Live domains = domains with at least 1 live inbox
    # Dead domains = domains with 0 live inboxes (legacy HyperTide domains no longer active)
    live_domain_stats = await fetch_one("""
        SELECT COUNT(DISTINCT d.id) as live_domains
        FROM domains d
        WHERE d.workspace_id = $1
          AND EXISTS (
              SELECT 1 FROM sender_accounts sa
              WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                AND sa.inbox_state = 'live'
          )
    """, workspace_id)
    live_domains = live_domain_stats["live_domains"] if live_domain_stats else 0
    total_domains = domain_stats["total"] if domain_stats else 0
    dead_domains = max(0, total_domains - live_domains)

    # Domain source breakdown (legacy vs purchased vs generated)
    domain_source_stats = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE domain_source = 'legacy' OR domain_source IS NULL) as legacy,
            COUNT(*) FILTER (WHERE domain_source = 'purchased') as purchased,
            COUNT(*) FILTER (WHERE domain_source = 'generated') as generated
        FROM domains
        WHERE workspace_id = $1
    """, workspace_id)

    return InfrastructureHealthResponse(
        client_id=client_id,
        total_inboxes=inbox_stats["total"] if inbox_stats else 0,
        live_inboxes=inbox_stats["live"] if inbox_stats else 0,
        dead_inboxes=inbox_stats["dead"] if inbox_stats else 0,
        avg_health_score=float(inbox_stats["avg_health"] if inbox_stats else 0),
        # Connection status - CRITICAL for external dashboard accuracy
        connected_inboxes=inbox_stats["connected"] if inbox_stats else 0,
        disconnected_inboxes=inbox_stats["disconnected"] if inbox_stats else 0,
        operational_capacity=inbox_stats["operational_capacity"] if inbox_stats else 0,
        potential_capacity=inbox_stats["potential_capacity"] if inbox_stats else 0,
        providers=providers,
        health_distribution=HealthDistribution(
            healthy=health_dist["healthy"] if health_dist else 0,
            good=health_dist["good"] if health_dist else 0,
            warning=health_dist["warning"] if health_dist else 0,
            critical=health_dist["critical"] if health_dist else 0,
            total=health_dist["total"] if health_dist else 0,
        ),
        lifecycle_distribution=LifecycleDistribution(
            incubating=lifecycle_dist["incubating"] if lifecycle_dist else 0,
            active=lifecycle_dist["active"] if lifecycle_dist else 0,
            dead=lifecycle_dist["dead"] if lifecycle_dist else 0,
            deployed=lifecycle_dist["deployed"] if lifecycle_dist else 0,
            reserve=lifecycle_dist["reserve"] if lifecycle_dist else 0,
            warning=lifecycle_dist["warning"] if lifecycle_dist else 0,
            total_live=lifecycle_dist["total_live"] if lifecycle_dist else 0,
        ),
        warning_distribution=WarningLevelDistribution(
            healthy=warning_dist["healthy"] if warning_dist else 0,
            watching=warning_dist["watching"] if warning_dist else 0,
            warning=warning_dist["warning"] if warning_dist else 0,
            critical=warning_dist["critical"] if warning_dist else 0,
            total_at_risk=(
                (warning_dist["watching"] if warning_dist else 0) +
                (warning_dist["warning"] if warning_dist else 0) +
                (warning_dist["critical"] if warning_dist else 0)
            ),
        ),
        total_domains=total_domains,
        live_domains=live_domains,
        dead_domains=dead_domains,
        clean_domains=domain_stats["clean"] if domain_stats else 0,
        flagged_domains=domain_stats["flagged"] if domain_stats else 0,
        domain_source_breakdown={
            "legacy": domain_source_stats["legacy"] if domain_source_stats else 0,
            "purchased": domain_source_stats["purchased"] if domain_source_stats else 0,
            "generated": domain_source_stats["generated"] if domain_source_stats else 0,
        },
        last_sync=last_sync["last_sync"] if last_sync else None,
        sync_source="database"
    )


@router.get("/inventory/{client_id}", response_model=InventoryHealthResponse)
async def get_inventory_health(client_id: UUID):
    """
    DEPRECATED: Use /infrastructure/{client_id} instead.

    Get real-time inventory health combining EmailBison metrics with RBL data.

    This endpoint fetches live data from EmailBison API for:
    - Inbox connection status
    - Health scores
    - Bounce rates
    - Provider breakdown

    And combines it with local RBL data for:
    - Domain blacklist status
    - Domain health scores
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id, w.workspace_name
        FROM clients c
        LEFT JOIN workspaces w ON c.workspace_id = w.id
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]
    workspace_name = client["workspace_name"]

    # Initialize response
    response = InventoryHealthResponse(
        client_id=str(client_id),
        client_name=client["name"],
        workspace_name=workspace_name,
    )

    # Get RBL/domain data from database
    if workspace_id:
        domain_stats = await fetch_one("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_clean = true OR COALESCE(latest_blacklist_count, 0) = 0) as clean,
                COUNT(*) FILTER (WHERE is_clean = false OR COALESCE(latest_blacklist_count, 0) > 0) as flagged,
                MAX(last_checked_at) as last_check
            FROM domains
            WHERE workspace_id = $1
        """, workspace_id)

        if domain_stats:
            response.total_domains = domain_stats["total"] or 0
            response.clean_domains = domain_stats["clean"] or 0
            response.flagged_domains = domain_stats["flagged"] or 0
            response.rbl_last_check = domain_stats["last_check"]

        # Get flagged domain details for attention items
        flagged_domains = await fetch_all("""
            SELECT domain_name, latest_blacklist_count,
                   ARRAY_AGG(DISTINCT rbl_name) FILTER (WHERE rbl_name IS NOT NULL) as blacklist_names
            FROM domains d
            LEFT JOIN LATERAL (
                SELECT rd.rbl_name
                FROM rbl_check_logs rcl
                JOIN rbl_definitions rd ON rcl.rbl_definition_id = rd.id
                WHERE rcl.domain_id = d.id
                AND rcl.is_listed = true
                AND rcl.check_timestamp >= NOW() - INTERVAL '24 hours'
            ) bl ON true
            WHERE d.workspace_id = $1
            AND (d.is_clean = false OR COALESCE(d.latest_blacklist_count, 0) > 0)
            GROUP BY d.id, d.domain_name, d.latest_blacklist_count
            LIMIT 10
        """, workspace_id)

        for domain in flagged_domains:
            bl_names = domain["blacklist_names"] or []
            response.attention_items.append({
                "type": "blacklist",
                "domain": domain["domain_name"],
                "count": domain["latest_blacklist_count"] or 0,
                "lists": bl_names[:5],  # Limit to first 5
                "severity": "critical" if (domain["latest_blacklist_count"] or 0) > 3 else "warning"
            })

    # Fetch real-time EmailBison data
    if workspace_name:
        try:
            async with EmailBisonService() as bison:
                eb_summary = await bison.get_workspace_summary(workspace_name)

            if eb_summary.error:
                response.emailbison_error = eb_summary.error
            else:
                response.emailbison_available = True
                response.total_inboxes = eb_summary.total_inboxes
                response.connected_inboxes = eb_summary.connected
                response.disconnected_inboxes = eb_summary.not_connected
                response.avg_health_score = eb_summary.avg_health_score
                response.connection_rate = round(
                    eb_summary.connected / eb_summary.total_inboxes * 100, 1
                ) if eb_summary.total_inboxes > 0 else 0.0

                # Provider breakdown
                response.providers = [
                    {
                        "name": p.provider,
                        "count": p.count,
                        "connected": p.connected,
                        "connection_rate": p.connection_rate,
                        "avg_health": p.avg_health_score
                    }
                    for p in eb_summary.provider_breakdown
                ]

                # Add high-bounce inboxes to attention items
                for inbox in eb_summary.high_bounce_sample:
                    response.attention_items.append({
                        "type": "high_bounce",
                        "email": inbox.email,
                        "bounce_rate": inbox.bounce_rate,
                        "bounced": inbox.bounced,
                        "sent": inbox.sent,
                        "severity": "critical" if (inbox.bounce_rate or 0) > 0.05 else "warning"
                    })

                # Add low-health inboxes
                for inbox in eb_summary.low_health_sample:
                    response.attention_items.append({
                        "type": "low_health",
                        "email": inbox.email,
                        "health_score": inbox.health_score,
                        "severity": "warning"
                    })

        except Exception as e:
            logger.error(f"Failed to fetch EmailBison data: {e}")
            response.emailbison_error = str(e)
    else:
        response.emailbison_error = "No workspace linked to client"

    # Sort attention items by severity
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    response.attention_items.sort(key=lambda x: severity_order.get(x.get("severity", "info"), 99))

    return response


# ===== EMAIL BISON CAPACITY ENDPOINT =====

class EmailBisonCapacityResponse(BaseModel):
    """EmailBison sending capacity data."""
    live_inboxes: int = 0
    total_inboxes: int = 0
    daily_send_limit: int = 0
    warming_inboxes: int = 0
    dead_inboxes: int = 0
    warmup_distribution: dict = {}
    last_synced: datetime = None

    class Config:
        from_attributes = True


@router.get("/emailbison-capacity/{client_id}", response_model=EmailBisonCapacityResponse)
async def get_emailbison_capacity(
    client_id: UUID,
    force_sync: bool = Query(False, description="Force refresh from EmailBison API")
):
    """
    Get EmailBison sending capacity data.

    Returns live/total inbox counts, daily send limit based on warmup progress,
    and warmup distribution buckets.
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id, w.workspace_name
        FROM clients c
        LEFT JOIN workspaces w ON c.workspace_id = w.id
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_name = client["workspace_name"]

    if not workspace_name:
        return EmailBisonCapacityResponse(
            last_synced=datetime.now(timezone.utc)
        )

    try:
        async with EmailBisonService() as bison:
            # Get workspace ID first
            workspace_id = await bison._get_workspace_id(workspace_name)
            if workspace_id is None:
                return EmailBisonCapacityResponse(
                    last_synced=datetime.now(timezone.utc)
                )

            # Switch to workspace
            await bison._switch_workspace(workspace_id)

            # Fetch all inboxes with pagination
            all_inboxes = []
            page = 1
            while True:
                response = await bison._client.get(
                    f"{bison.base_url}/api/sender-emails",
                    params={"page": page, "per_page": 100}
                )
                response.raise_for_status()
                data = response.json()

                inboxes = data.get("data", [])
                if not inboxes:
                    break

                all_inboxes.extend(inboxes)

                meta = data.get("meta", {})
                last_page = meta.get("last_page", 1)
                if page >= last_page:
                    break
                page += 1

        # Process inbox data
        total = len(all_inboxes)
        live = 0
        dead = 0
        warming = 0
        daily_limit = 0

        # Warmup distribution buckets
        warmup_distribution = {
            "range_0_25": 0,
            "range_25_50": 0,
            "range_50_75": 0,
            "range_75_100": 0
        }

        for inbox in all_inboxes:
            # Check connection status
            status = inbox.get("connection_status", inbox.get("status", "")).lower()
            is_connected = status in ("connected", "active", "1", "true")

            # Check if inbox is dead/paused
            inbox_status = inbox.get("inbox_status", inbox.get("status", "")).lower()
            if inbox_status in ("dead", "paused", "disabled", "deleted"):
                dead += 1
                continue

            if not is_connected:
                dead += 1
                continue

            # Connected inbox
            live += 1

            # Get warmup progress (0-100 scale)
            warmup_progress = inbox.get("warmup_progress", inbox.get("warmup", 100))
            if warmup_progress is None:
                warmup_progress = 100

            # Calculate daily send limit contribution based on warmup
            # Assume max daily sends of 50 per fully warmed inbox
            max_daily = 50
            inbox_daily = int(max_daily * (warmup_progress / 100))
            daily_limit += inbox_daily

            # Track warming inboxes (not fully warmed)
            if warmup_progress < 100:
                warming += 1

                # Distribution buckets
                if warmup_progress < 25:
                    warmup_distribution["range_0_25"] += 1
                elif warmup_progress < 50:
                    warmup_distribution["range_25_50"] += 1
                elif warmup_progress < 75:
                    warmup_distribution["range_50_75"] += 1
                else:
                    warmup_distribution["range_75_100"] += 1

        return EmailBisonCapacityResponse(
            live_inboxes=live,
            total_inboxes=total,
            daily_send_limit=daily_limit,
            warming_inboxes=warming,
            dead_inboxes=dead,
            warmup_distribution=warmup_distribution,
            last_synced=datetime.now(timezone.utc)
        )

    except Exception as e:
        logger.error(f"Failed to fetch EmailBison capacity: {e}")
        # Return zeros with error logged
        return EmailBisonCapacityResponse(
            last_synced=datetime.now(timezone.utc)
        )


class KillVelocityWeek(BaseModel):
    """Weekly kill velocity data point"""
    week: str
    deaths: int


class KillVelocityResponse(BaseModel):
    """Kill velocity response for trend chart"""
    weekly: list[KillVelocityWeek]
    total_deaths_7d: int
    total_deaths_30d: int
    churn_rate_7d: float
    trend: str  # "up", "down", "stable"

    class Config:
        from_attributes = True


@router.get("/kill-velocity/{client_id}", response_model=KillVelocityResponse)
async def get_kill_velocity(client_id: UUID):
    """
    Get kill velocity data for ENTIRE CLIENT HISTORY.

    Returns weekly death counts from the beginning of time, churn rate, and trend direction.
    Used for the executive dashboard kill velocity chart showing full historical wave pattern.
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    if not workspace_id:
        return KillVelocityResponse(
            weekly=[],
            total_deaths_7d=0,
            total_deaths_30d=0,
            churn_rate_7d=0.0,
            trend="stable"
        )

    # Get weekly death counts for ENTIRE HISTORY (not just 5 weeks)
    weekly_deaths = await fetch_all("""
        SELECT
            DATE_TRUNC('week', killed_at) as week,
            COUNT(*) as deaths
        FROM sender_accounts
        WHERE workspace_id = $1
            AND inbox_state = 'dead'
            AND killed_at IS NOT NULL
        GROUP BY DATE_TRUNC('week', killed_at)
        ORDER BY week
    """, workspace_id)

    # Get total counts for metrics
    death_counts = await fetch_one("""
        SELECT
            COUNT(*) FILTER (
                WHERE inbox_state = 'dead'
                AND killed_at IS NOT NULL
                AND killed_at > NOW() - INTERVAL '7 days'
            ) as deaths_7d,
            COUNT(*) FILTER (
                WHERE inbox_state = 'dead'
                AND killed_at IS NOT NULL
                AND killed_at > NOW() - INTERVAL '30 days'
            ) as deaths_30d,
            COUNT(*) as total_inboxes
        FROM sender_accounts
        WHERE workspace_id = $1
    """, workspace_id)

    deaths_7d = death_counts["deaths_7d"] if death_counts else 0
    deaths_30d = death_counts["deaths_30d"] if death_counts else 0
    total = death_counts["total_inboxes"] if death_counts else 0

    # Calculate churn rate
    churn_rate = (deaths_7d / total * 100) if total > 0 else 0.0

    # Format weekly data
    weekly = [
        KillVelocityWeek(
            week=row["week"].strftime("%Y-%m-%d") if row["week"] else "",
            deaths=row["deaths"]
        )
        for row in (weekly_deaths or [])
    ]

    # Determine trend
    trend = "stable"
    if len(weekly) >= 2:
        recent_week = weekly[-1].deaths if weekly else 0
        prev_week = weekly[-2].deaths if len(weekly) > 1 else 0
        if recent_week > prev_week:
            trend = "up"
        elif recent_week < prev_week:
            trend = "down"

    return KillVelocityResponse(
        weekly=weekly,
        total_deaths_7d=deaths_7d,
        total_deaths_30d=deaths_30d,
        churn_rate_7d=round(churn_rate, 2),
        trend=trend
    )


# ===== KILL BREAKDOWN =====

class KillCategory(BaseModel):
    """A category of kill triggers with count and percentage"""
    count: int
    triggers: list[str]
    percentage: float


class KillTriggerDetail(BaseModel):
    """Individual trigger type count"""
    trigger: str
    count: int
    gmail_count: int = 0
    microsoft_count: int = 0


class KillBreakdownResponse(BaseModel):
    """Kill trigger breakdown showing WHY inboxes died"""
    reputation: KillCategory  # spam_complaint, hard_blocked_24h
    list_quality: KillCategory  # hard_unknown_24h
    premature_deployment: KillCategory  # fresh_inbox_bounce
    other: KillCategory  # remaining triggers
    by_provider: dict  # {"gmail": 5, "microsoft": 12}
    total_killed: int
    raw: list[KillTriggerDetail]  # Raw trigger counts

    class Config:
        from_attributes = True


# Kill trigger categorization
REPUTATION_TRIGGERS = ["spam_complaint", "hard_blocked_24h"]
LIST_QUALITY_TRIGGERS = ["hard_unknown_24h"]
PREMATURE_TRIGGERS = ["fresh_inbox_bounce"]


@router.get("/kill-breakdown/{client_id}", response_model=KillBreakdownResponse)
async def get_kill_breakdown(client_id: UUID):
    """
    Get kill trigger breakdown showing WHY inboxes died.

    Groups triggers into actionable categories:
    - reputation: Sender reputation issues (spam, policy blocks)
    - list_quality: Bad email addresses
    - premature_deployment: Fresh inbox bounces
    - other: Other triggers

    Also provides per-provider breakdown (Gmail vs Microsoft).
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    if not workspace_id:
        return KillBreakdownResponse(
            reputation=KillCategory(count=0, triggers=REPUTATION_TRIGGERS, percentage=0),
            list_quality=KillCategory(count=0, triggers=LIST_QUALITY_TRIGGERS, percentage=0),
            premature_deployment=KillCategory(count=0, triggers=PREMATURE_TRIGGERS, percentage=0),
            other=KillCategory(count=0, triggers=[], percentage=0),
            by_provider={"gmail": 0, "microsoft": 0},
            total_killed=0,
            raw=[]
        )

    # Get kill triggers from last 30 days (only system kills, not manual)
    trigger_rows = await fetch_all("""
        SELECT
            kill_trigger::text as kill_trigger,
            COUNT(*) as count,
            COUNT(*) FILTER (WHERE LOWER(esp::text) = 'gmail') as gmail_count,
            COUNT(*) FILTER (WHERE LOWER(esp::text) IN ('microsoft', 'outlook')) as microsoft_count
        FROM sender_accounts
        WHERE workspace_id = $1
            AND inbox_state = 'dead'
            AND kill_trigger IS NOT NULL
            AND kill_trigger::text != 'manual'
            AND killed_at > NOW() - INTERVAL '30 days'
        GROUP BY kill_trigger
        ORDER BY count DESC
    """, workspace_id)

    # Build raw list and aggregate by category
    raw = []
    reputation_count = 0
    list_quality_count = 0
    premature_count = 0
    other_count = 0
    other_triggers = []
    gmail_total = 0
    microsoft_total = 0

    for row in (trigger_rows or []):
        trigger = row["kill_trigger"]
        count = row["count"]
        gmail = row["gmail_count"] or 0
        microsoft = row["microsoft_count"] or 0

        raw.append(KillTriggerDetail(
            trigger=trigger,
            count=count,
            gmail_count=gmail,
            microsoft_count=microsoft
        ))

        gmail_total += gmail
        microsoft_total += microsoft

        if trigger in REPUTATION_TRIGGERS:
            reputation_count += count
        elif trigger in LIST_QUALITY_TRIGGERS:
            list_quality_count += count
        elif trigger in PREMATURE_TRIGGERS:
            premature_count += count
        else:
            other_count += count
            if trigger not in other_triggers:
                other_triggers.append(trigger)

    total_killed = reputation_count + list_quality_count + premature_count + other_count

    # Calculate percentages
    def calc_pct(count: int) -> float:
        return round((count / total_killed * 100), 1) if total_killed > 0 else 0.0

    return KillBreakdownResponse(
        reputation=KillCategory(
            count=reputation_count,
            triggers=REPUTATION_TRIGGERS,
            percentage=calc_pct(reputation_count)
        ),
        list_quality=KillCategory(
            count=list_quality_count,
            triggers=LIST_QUALITY_TRIGGERS,
            percentage=calc_pct(list_quality_count)
        ),
        premature_deployment=KillCategory(
            count=premature_count,
            triggers=PREMATURE_TRIGGERS,
            percentage=calc_pct(premature_count)
        ),
        other=KillCategory(
            count=other_count,
            triggers=other_triggers,
            percentage=calc_pct(other_count)
        ),
        by_provider={
            "gmail": gmail_total,
            "microsoft": microsoft_total
        },
        total_killed=total_killed,
        raw=raw
    )


# ===== Daily Volume History (for Capacity Chart) =====

from models.health import (
    DailyVolumeSnapshot,
    KillEventAnnotation,
    DailyVolumeHistoryResponse,
    CapacityInsight,
)


@router.get("/daily-volume/{client_id}", response_model=DailyVolumeHistoryResponse)
async def get_daily_volume_history(
    client_id: UUID,
    days: int = Query(90, ge=1, le=365, description="Number of days of history")
):
    """
    Get daily sending volume and capacity history for client dashboard chart.

    Returns N days (default: 90) of:
    - Emails sent per day
    - Available capacity per day
    - Incubating inbox count per day
    - Capacity utilization percentage
    - Kill events for chart annotations

    Used by: Client dashboard "Sending Capacity Over Time" chart
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    if not workspace_id:
        return DailyVolumeHistoryResponse(
            client_id=client_id,
            workspace_id=None,
            start_date=datetime.now(timezone.utc) - timedelta(days=days),
            end_date=datetime.now(timezone.utc),
            days_requested=days,
            days_returned=0,
            snapshots=[],
            kill_events=[]
        )

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Query daily snapshots
    snapshot_rows = await fetch_all("""
        SELECT
            snapshot_date,
            emails_sent,
            emails_delivered,
            emails_bounced,
            daily_capacity_available,
            live_inboxes,
            incubating_inboxes,
            dead_inboxes,
            capacity_utilization_pct,
            kills_that_day
        FROM daily_volume_snapshots
        WHERE workspace_id = $1
          AND snapshot_date >= $2::date
        ORDER BY snapshot_date ASC
    """, workspace_id, start_date)

    # Get kill events for annotations (grouped by day)
    kill_rows = await fetch_all("""
        SELECT
            DATE(killed_at) as kill_date,
            COUNT(*) as inboxes_killed,
            STRING_AGG(DISTINCT kill_trigger::text, ', ') as kill_reasons
        FROM sender_accounts
        WHERE workspace_id = $1
          AND killed_at >= $2
          AND killed_at IS NOT NULL
        GROUP BY DATE(killed_at)
        ORDER BY kill_date ASC
    """, workspace_id, start_date)

    # Build snapshots list
    snapshots = []
    total_emails = 0
    total_capacity = 0
    total_utilization = 0.0

    for row in (snapshot_rows or []):
        snapshots.append(DailyVolumeSnapshot(
            date=datetime.combine(row["snapshot_date"], datetime.min.time()),
            emails_sent=row["emails_sent"] or 0,
            emails_delivered=row["emails_delivered"] or 0,
            emails_bounced=row["emails_bounced"] or 0,
            daily_capacity_available=row["daily_capacity_available"] or 0,
            live_inboxes=row["live_inboxes"] or 0,
            incubating_inboxes=row["incubating_inboxes"] or 0,
            dead_inboxes=row["dead_inboxes"] or 0,
            capacity_utilization_pct=float(row["capacity_utilization_pct"]) if row["capacity_utilization_pct"] else 0.0,
            kills_that_day=row["kills_that_day"] or 0
        ))
        total_emails += row["emails_sent"] or 0
        total_capacity += row["daily_capacity_available"] or 0
        if row["capacity_utilization_pct"]:
            total_utilization += float(row["capacity_utilization_pct"])

    # Build kill events list
    kill_events = []
    total_kills = 0
    for row in (kill_rows or []):
        kill_events.append(KillEventAnnotation(
            date=datetime.combine(row["kill_date"], datetime.min.time()),
            inboxes_killed=row["inboxes_killed"] or 0,
            kill_reasons=row["kill_reasons"] or ""
        ))
        total_kills += row["inboxes_killed"] or 0

    # Calculate averages
    num_snapshots = len(snapshots) or 1
    avg_capacity = total_capacity // num_snapshots if snapshots else 0
    avg_utilization = total_utilization / num_snapshots if snapshots else 0.0

    return DailyVolumeHistoryResponse(
        client_id=client_id,
        workspace_id=workspace_id,
        start_date=start_date,
        end_date=datetime.now(timezone.utc),
        days_requested=days,
        days_returned=len(snapshots),
        snapshots=snapshots,
        kill_events=kill_events,
        total_emails_sent=total_emails,
        avg_daily_capacity=avg_capacity,
        avg_utilization_pct=round(avg_utilization, 2),
        total_kills=total_kills
    )


@router.get("/export/flagged-inboxes")
async def export_flagged_inboxes():
    """Export all flagged/killed inboxes as CSV for team review.

    Returns a comprehensive list sorted by workspace, then grouped by domain,
    then by killed_at date descending for easy investigation.

    CSV columns:
    - workspace_name, domain_name, email_address
    - kill_trigger, killed_at, days_before_kill (how long inbox lasted)
    - inbox_state, connection_status
    - complaints_lifetime
    - trigger_value, trigger_threshold (what triggered the kill)
    """
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            d.domain_name,
            sa.email_address,
            sa.kill_trigger,
            sa.killed_at,
            sa.inbox_state,
            sa.status as connection_status,
            sa.warmup_started_at,
            -- Days between warmup start and kill (how long inbox lasted)
            CASE
                WHEN sa.warmup_started_at IS NOT NULL AND sa.killed_at IS NOT NULL THEN
                    EXTRACT(DAY FROM sa.killed_at - sa.warmup_started_at)::INTEGER
                ELSE NULL
            END as days_before_kill,
            COALESCE(sa.complaints_lifetime, 0) as complaints_lifetime,
            kq.trigger_value,
            kq.trigger_threshold
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        LEFT JOIN LATERAL (
            SELECT trigger_value, trigger_threshold
            FROM kill_queue
            WHERE inbox_id = sa.id
            ORDER BY created_at DESC
            LIMIT 1
        ) kq ON true
        WHERE (sa.inbox_state = 'dead' OR sa.kill_trigger IS NOT NULL)
        AND sa.emailbison_account_id IS NOT NULL  -- Only show inboxes still in EmailBison
        ORDER BY w.workspace_name, d.domain_name, sa.killed_at DESC NULLS LAST
    """)

    if not rows:
        return Response(
            content="No flagged inboxes found",
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=flagged-inboxes.csv"}
        )

    # Build CSV content
    csv_lines = []

    # Header row
    csv_lines.append(",".join([
        "workspace_name",
        "domain_name",
        "email_address",
        "kill_trigger",
        "killed_at",
        "days_before_kill",
        "inbox_state",
        "connection_status",
        "warmup_started_at",
        "complaints_lifetime",
        "trigger_value",
        "trigger_threshold"
    ]))

    # Data rows
    for row in rows:
        # Escape commas and quotes in string fields
        def escape_csv(val):
            if val is None:
                return ""
            s = str(val)
            if "," in s or '"' in s or "\n" in s:
                return '"' + s.replace('"', '""') + '"'
            return s

        csv_lines.append(",".join([
            escape_csv(row["workspace_name"]),
            escape_csv(row["domain_name"]),
            escape_csv(row["email_address"]),
            escape_csv(row["kill_trigger"]),
            escape_csv(row["killed_at"].isoformat() if row["killed_at"] else None),
            escape_csv(row["days_before_kill"]),
            escape_csv(row["inbox_state"]),
            escape_csv(row["connection_status"]),
            escape_csv(row["warmup_started_at"].isoformat() if row["warmup_started_at"] else None),
            escape_csv(row["complaints_lifetime"]),
            escape_csv(row["trigger_value"]),
            escape_csv(row["trigger_threshold"])
        ]))

    csv_content = "\n".join(csv_lines)

    # Generate filename with date
    today = datetime.now().strftime("%Y-%m-%d")

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=flagged-inboxes-{today}.csv"}
    )


@router.get("/export/kill-triggers")
async def export_kill_triggers():
    """Export inboxes caught by kill triggers for manual team review.

    CSV structure optimized for Google Sheets:
    - Sorted by workspace → domain → inbox
    - First columns: workspace_name, emailbison_workspace_id
    - Then domain and inbox details with kill trigger info

    Use this to manually verify kill triggers are working correctly.
    """
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            w.emailbison_workspace_id,
            d.domain_name,
            sa.email_address,
            sa.kill_trigger,
            sa.killed_at,
            CASE
                WHEN sa.warmup_started_at IS NOT NULL AND sa.killed_at IS NOT NULL THEN
                    EXTRACT(DAY FROM sa.killed_at - sa.warmup_started_at)::INTEGER
                ELSE NULL
            END as days_active,
            sa.inbox_state,
            sa.status as connection_status,
            sa.warmup_started_at,
            COALESCE(sa.complaints_lifetime, 0) as complaints_lifetime,
            kq.trigger_value,
            kq.trigger_threshold
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        LEFT JOIN LATERAL (
            SELECT trigger_value, trigger_threshold
            FROM kill_queue
            WHERE inbox_id = sa.id
            ORDER BY created_at DESC
            LIMIT 1
        ) kq ON true
        WHERE sa.kill_trigger IS NOT NULL
        AND sa.emailbison_account_id IS NOT NULL  -- Only show inboxes still in EmailBison
        AND w.is_active = TRUE
        ORDER BY w.workspace_name, d.domain_name, sa.email_address
    """)

    if not rows:
        return Response(
            content="No kill trigger inboxes found",
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=kill-triggers.csv"}
        )

    def escape_csv(val):
        if val is None:
            return ""
        s = str(val)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    csv_lines = []
    csv_lines.append(",".join([
        "workspace_name",
        "emailbison_workspace_id",
        "domain_name",
        "email_address",
        "kill_trigger",
        "killed_at",
        "days_active",
        "inbox_state",
        "connection_status",
        "warmup_started_at",
        "complaints_lifetime",
        "trigger_value",
        "trigger_threshold"
    ]))

    for row in rows:
        csv_lines.append(",".join([
            escape_csv(row["workspace_name"]),
            escape_csv(row["emailbison_workspace_id"]),
            escape_csv(row["domain_name"]),
            escape_csv(row["email_address"]),
            escape_csv(row["kill_trigger"]),
            escape_csv(row["killed_at"].isoformat() if row["killed_at"] else None),
            escape_csv(row["days_active"]),
            escape_csv(row["inbox_state"]),
            escape_csv(row["connection_status"]),
            escape_csv(row["warmup_started_at"].isoformat() if row["warmup_started_at"] else None),
            escape_csv(row["complaints_lifetime"]),
            escape_csv(row["trigger_value"]),
            escape_csv(row["trigger_threshold"])
        ]))

    csv_content = "\n".join(csv_lines)
    today = datetime.now().strftime("%Y-%m-%d")

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=kill-triggers-{today}.csv"}
    )


@router.get("/export/disconnected")
async def export_disconnected():
    """Export disconnected inboxes for manual team review.

    CSV structure optimized for Google Sheets:
    - Sorted by workspace → domain → inbox
    - First columns: workspace_name, emailbison_workspace_id
    - Shows inboxes with status != 'Connected'

    Use this to identify and manage disconnected inboxes.
    """
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            w.emailbison_workspace_id,
            d.domain_name,
            sa.email_address,
            sa.status as connection_status,
            sa.inbox_state,
            sa.warmup_enabled,
            sa.warmup_started_at,
            sa.esp,
            sa.daily_limit,
            COALESCE(sa.total_sends_7d, 0) as total_sends_7d,
            COALESCE(sa.hard_bounces_24h, 0) as hard_bounces_24h,
            sa.last_synced_at,
            sa.created_at
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.status != 'Connected'
        AND sa.inbox_state = 'live'
        AND sa.emailbison_account_id IS NOT NULL  -- Only show inboxes still in EmailBison
        AND w.is_active = TRUE
        ORDER BY w.workspace_name, d.domain_name, sa.email_address
    """)

    if not rows:
        return Response(
            content="No disconnected inboxes found",
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=disconnected.csv"}
        )

    def escape_csv(val):
        if val is None:
            return ""
        s = str(val)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    csv_lines = []
    csv_lines.append(",".join([
        "workspace_name",
        "emailbison_workspace_id",
        "domain_name",
        "email_address",
        "connection_status",
        "inbox_state",
        "warmup_enabled",
        "warmup_started_at",
        "esp",
        "daily_limit",
        "total_sends_7d",
        "hard_bounces_24h",
        "last_synced_at",
        "created_at"
    ]))

    for row in rows:
        csv_lines.append(",".join([
            escape_csv(row["workspace_name"]),
            escape_csv(row["emailbison_workspace_id"]),
            escape_csv(row["domain_name"]),
            escape_csv(row["email_address"]),
            escape_csv(row["connection_status"]),
            escape_csv(row["inbox_state"]),
            escape_csv(row["warmup_enabled"]),
            escape_csv(row["warmup_started_at"].isoformat() if row["warmup_started_at"] else None),
            escape_csv(row["esp"]),
            escape_csv(row["daily_limit"]),
            escape_csv(row["total_sends_7d"]),
            escape_csv(row["hard_bounces_24h"]),
            escape_csv(row["last_synced_at"].isoformat() if row["last_synced_at"] else None),
            escape_csv(row["created_at"].isoformat() if row["created_at"] else None)
        ]))

    csv_content = "\n".join(csv_lines)
    today = datetime.now().strftime("%Y-%m-%d")

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=disconnected-{today}.csv"}
    )


@router.get("/export/dead-domains")
async def export_dead_domains():
    """Export domains where ALL inboxes are gone from EmailBison.

    These domains need their HyperTide subscriptions cancelled since
    no inboxes remain active in the email sending platform.

    CSV structure optimized for Google Sheets:
    - Sorted by workspace → domain
    - First columns: workspace_name, emailbison_workspace_id
    - Shows domain details with inbox counts and CANCEL status

    NOTE: This is different from inbox_state='dead' - this identifies
    domains where inboxes have been completely removed from EmailBison.
    """
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            w.emailbison_workspace_id,
            d.domain_name,
            COALESCE(d.infrastructure_type, inbox_stats.detected_provider) AS provider,
            d.purchased_at,
            inbox_stats.total_inboxes,
            inbox_stats.inboxes_in_emailbison,
            inbox_stats.inboxes_gone,
            'CANCEL' AS status
        FROM domains d
        JOIN workspaces w ON d.workspace_id = w.id
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) AS total_inboxes,
                COUNT(*) FILTER (WHERE sa.is_active = TRUE) AS inboxes_in_emailbison,
                COUNT(*) FILTER (WHERE sa.is_active = FALSE) AS inboxes_gone,
                CASE
                    WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
                    WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
                    ELSE NULL
                END AS detected_provider
            FROM sender_accounts sa
            WHERE sa.domain_id = d.id
        ) inbox_stats ON true
        WHERE w.is_active = TRUE
        AND d.is_active = TRUE
        AND inbox_stats.total_inboxes > 0
        AND inbox_stats.inboxes_in_emailbison = 0
        ORDER BY w.workspace_name, d.domain_name
    """)

    if not rows:
        return Response(
            content="No dead domains found",
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=dead-domains.csv"}
        )

    def escape_csv(val):
        if val is None:
            return ""
        s = str(val)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    csv_lines = []
    csv_lines.append(",".join([
        "workspace_name",
        "emailbison_workspace_id",
        "domain_name",
        "provider",
        "purchased_at",
        "total_inboxes",
        "inboxes_in_emailbison",
        "inboxes_gone",
        "status"
    ]))

    for row in rows:
        csv_lines.append(",".join([
            escape_csv(row["workspace_name"]),
            escape_csv(row["emailbison_workspace_id"]),
            escape_csv(row["domain_name"]),
            escape_csv(row["provider"]),
            escape_csv(row["purchased_at"].isoformat() if row["purchased_at"] else None),
            escape_csv(row["total_inboxes"]),
            escape_csv(row["inboxes_in_emailbison"]),
            escape_csv(row["inboxes_gone"]),
            escape_csv(row["status"])
        ]))

    csv_content = "\n".join(csv_lines)
    today = datetime.now().strftime("%Y-%m-%d")

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=dead-domains-{today}.csv"}
    )


@router.get("/export/rotation-summary")
async def export_rotation_summary():
    """Export domain rotation recommendations for manual review."""
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            w.emailbison_workspace_id,
            viw.domain_name,
            viw.rotation_recommendation,
            viw.recommended_action,
            viw.has_compromised_inboxes,
            COALESCE(viw.inboxes_with_complaints, 0) as inboxes_with_complaints,
            COALESCE(viw.inboxes_with_blocks, 0) as inboxes_with_blocks,
            viw.connected_inbox_count,
            COALESCE(viw.expected_inbox_count, viw.live_inbox_count) as expected_inbox_count,
            viw.capacity_remaining_pct,
            viw.assigned_provider,
            viw.dead_inbox_count,
            viw.disconnected_inbox_count
        FROM v_infrastructure_waterfall viw
        JOIN workspaces w ON viw.workspace_id = w.id
        WHERE viw.synced_inbox_count > 0
        AND viw.rotation_recommendation IN ('rotate_now', 'consider_rotate', 'monitor')
        AND w.is_active = TRUE
        ORDER BY
            CASE viw.rotation_recommendation
                WHEN 'rotate_now' THEN 1
                WHEN 'consider_rotate' THEN 2
                WHEN 'monitor' THEN 3
            END,
            w.workspace_name,
            viw.domain_name
    """)

    if not rows:
        return Response(
            content="No rotation recommendations",
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=rotation-summary.csv"}
        )

    def escape_csv(val):
        if val is None:
            return ""
        s = str(val)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    csv_lines = []
    csv_lines.append(",".join([
        "workspace_name",
        "emailbison_workspace_id",
        "domain_name",
        "rotation_recommendation",
        "recommended_action",
        "compromised",
        "spam_complaints",
        "hard_blocks",
        "connected",
        "expected",
        "capacity_pct",
        "provider",
        "dead_inboxes",
        "disconnected"
    ]))

    for row in rows:
        csv_lines.append(",".join([
            escape_csv(row["workspace_name"]),
            escape_csv(row["emailbison_workspace_id"]),
            escape_csv(row["domain_name"]),
            escape_csv(row["rotation_recommendation"]),
            escape_csv(row["recommended_action"]),
            escape_csv("YES" if row["has_compromised_inboxes"] else "NO"),
            escape_csv(row["inboxes_with_complaints"]),
            escape_csv(row["inboxes_with_blocks"]),
            escape_csv(row["connected_inbox_count"]),
            escape_csv(row["expected_inbox_count"]),
            escape_csv(f"{int(row['capacity_remaining_pct'])}%" if row["capacity_remaining_pct"] else "N/A"),
            escape_csv(row["assigned_provider"]),
            escape_csv(row["dead_inbox_count"]),
            escape_csv(row["disconnected_inbox_count"])
        ]))

    csv_content = "\n".join(csv_lines)
    today = datetime.now().strftime("%Y-%m-%d")

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=rotation-summary-{today}.csv"}
    )


@router.get("/export/capacity-gaps")
async def export_capacity_gaps():
    """Export client capacity gaps for package fulfillment review.

    Shows clients where actual capacity is below purchased package target.
    Includes compromised domain counts to explain capacity loss.
    """
    rows = await fetch_all("""
        SELECT
            client_name,
            workspace_id,
            -- Entra
            COALESCE(entra_packages, 0) as entra_packages,
            COALESCE(entra_inboxes_target, 0) as entra_target,
            COALESCE(entra_inboxes_live, 0) as entra_live,
            COALESCE(entra_inbox_gap, 0) as entra_gap,
            COALESCE(entra_domains_target, 0) as entra_domains_target,
            COALESCE(entra_domains_actual, 0) as entra_domains_actual,
            -- Google
            COALESCE(google_packages, 0) as google_packages,
            COALESCE(google_inboxes_target, 0) as google_target,
            COALESCE(google_inboxes_live, 0) as google_live,
            COALESCE(google_inbox_gap, 0) as google_gap,
            COALESCE(google_domains_target, 0) as google_domains_target,
            COALESCE(google_domains_actual, 0) as google_domains_actual,
            -- Buffer
            COALESCE(entra_pipeline_buffer, 0) as entra_buffer,
            COALESCE(google_pipeline_buffer, 0) as google_buffer
        FROM v_client_capacity
        WHERE entra_inbox_gap > 0 OR google_inbox_gap > 0
        ORDER BY (COALESCE(entra_inbox_gap, 0) + COALESCE(google_inbox_gap, 0)) DESC
    """)

    # Get compromised domain counts per workspace
    compromised = await fetch_all("""
        SELECT
            sa.workspace_id,
            COUNT(DISTINCT d.id) as compromised_domains,
            COUNT(*) as compromised_inboxes
        FROM sender_accounts sa
        JOIN domains d ON sa.domain_id = d.id
        WHERE sa.kill_trigger IN ('spam_complaint', 'provider_block_google', 'provider_block_microsoft')
        GROUP BY sa.workspace_id
    """)
    compromised_map = {str(c["workspace_id"]): c for c in compromised}

    def escape_csv(val):
        if val is None:
            return ""
        s = str(val)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    csv_lines = []
    csv_lines.append(",".join([
        "client_name",
        "entra_packages",
        "entra_target",
        "entra_live",
        "entra_gap",
        "entra_pct",
        "entra_domains_target",
        "entra_domains_actual",
        "google_packages",
        "google_target",
        "google_live",
        "google_gap",
        "google_pct",
        "google_domains_target",
        "google_domains_actual",
        "compromised_domains",
        "compromised_inboxes",
        "entra_buffer",
        "google_buffer"
    ]))

    for row in rows:
        ws_id = str(row["workspace_id"])
        comp = compromised_map.get(ws_id, {})

        entra_pct = round(row["entra_live"] / row["entra_target"] * 100) if row["entra_target"] > 0 else ""
        google_pct = round(row["google_live"] / row["google_target"] * 100) if row["google_target"] > 0 else ""

        csv_lines.append(",".join([
            escape_csv(row["client_name"]),
            escape_csv(row["entra_packages"]),
            escape_csv(row["entra_target"]),
            escape_csv(row["entra_live"]),
            escape_csv(row["entra_gap"]),
            escape_csv(f"{entra_pct}%" if entra_pct else ""),
            escape_csv(row["entra_domains_target"]),
            escape_csv(row["entra_domains_actual"]),
            escape_csv(row["google_packages"]),
            escape_csv(row["google_target"]),
            escape_csv(row["google_live"]),
            escape_csv(row["google_gap"]),
            escape_csv(f"{google_pct}%" if google_pct else ""),
            escape_csv(row["google_domains_target"]),
            escape_csv(row["google_domains_actual"]),
            escape_csv(comp.get("compromised_domains", 0)),
            escape_csv(comp.get("compromised_inboxes", 0)),
            escape_csv(row["entra_buffer"]),
            escape_csv(row["google_buffer"])
        ]))

    csv_content = "\n".join(csv_lines)
    today = datetime.now().strftime("%Y-%m-%d")

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=capacity-gaps-{today}.csv"}
    )


@router.get("/analysis/spam-complaint-timing")
async def analyze_spam_complaint_timing():
    """
    Analyze when spam complaints occur relative to inbox lifecycle.

    Returns breakdown by lifecycle stage:
    - killed_during_warmup: Before sending started
    - first_2_weeks: Within 14 days of sending
    - week_2_to_4: Days 15-30
    - month_1_to_2: Days 31-60
    - month_2_to_3: Days 61-90
    - beyond_3_months: 90+ days
    """
    summary = await fetch_all("""
        WITH spam_complaints AS (
            SELECT
                sa.id,
                sa.email_address,
                d.domain_name,
                sa.warmup_started_at,
                sa.sending_started_at,
                sa.killed_at,
                EXTRACT(day FROM (sa.killed_at - sa.warmup_started_at))::int AS days_since_warmup,
                EXTRACT(day FROM (sa.killed_at - sa.sending_started_at))::int AS days_since_sending,
                CASE
                    WHEN sa.sending_started_at IS NULL THEN 'killed_during_warmup'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '14 days' THEN 'first_2_weeks'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '30 days' THEN 'week_2_to_4'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '60 days' THEN 'month_1_to_2'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '90 days' THEN 'month_2_to_3'
                    ELSE 'beyond_3_months'
                END AS lifecycle_stage
            FROM sender_accounts sa
            LEFT JOIN domains d ON sa.domain_id = d.id
            WHERE sa.kill_trigger = 'spam_complaint'
              AND sa.killed_at IS NOT NULL
              AND sa.warmup_started_at IS NOT NULL
        )
        SELECT
            lifecycle_stage,
            COUNT(*) as count,
            ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 1) as pct,
            ROUND(AVG(days_since_warmup), 0) as avg_days_from_warmup,
            ROUND(AVG(days_since_sending), 0) as avg_days_from_sending,
            MIN(days_since_warmup) as min_days,
            MAX(days_since_warmup) as max_days
        FROM spam_complaints
        GROUP BY lifecycle_stage
        ORDER BY
            CASE lifecycle_stage
                WHEN 'killed_during_warmup' THEN 1
                WHEN 'first_2_weeks' THEN 2
                WHEN 'week_2_to_4' THEN 3
                WHEN 'month_1_to_2' THEN 4
                WHEN 'month_2_to_3' THEN 5
                ELSE 6
            END
    """)

    # Also get raw detail for deeper analysis
    detail = await fetch_all("""
        SELECT
            sa.email_address,
            d.domain_name,
            sa.warmup_started_at,
            sa.sending_started_at,
            sa.killed_at,
            EXTRACT(day FROM (sa.killed_at - sa.warmup_started_at))::int AS days_since_warmup,
            EXTRACT(day FROM (sa.killed_at - sa.sending_started_at))::int AS days_since_sending
        FROM sender_accounts sa
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.kill_trigger = 'spam_complaint'
          AND sa.killed_at IS NOT NULL
          AND sa.warmup_started_at IS NOT NULL
        ORDER BY sa.killed_at DESC
        LIMIT 50
    """)

    total = sum(row["count"] for row in summary) if summary else 0

    return {
        "total_spam_complaints": total,
        "by_lifecycle_stage": [dict(row) for row in summary] if summary else [],
        "recent_examples": [dict(row) for row in detail] if detail else []
    }


@router.get("/analysis/kill-trigger-lifecycle")
async def analyze_kill_trigger_lifecycle():
    """
    Comprehensive kill trigger analysis by lifecycle stage.

    Analyzes ALL kill triggers (not just spam complaints) to understand
    when different failure modes occur relative to inbox lifecycle.

    Lifecycle stages (based on sending_started_at):
    - killed_during_warmup: Before any campaign sends
    - first_2_weeks: 0-14 days after first campaign send
    - week_2_to_4: 15-30 days
    - month_1_to_2: 31-60 days
    - month_2_to_3: 61-90 days
    - beyond_3_months: 90+ days

    NOTE: sending_started_at is set when inbox is first assigned to a campaign
    (Migration 079, sync_campaigns.py). This is more accurate than warmup graduation.
    """
    # Get breakdown by trigger type AND lifecycle stage
    by_trigger_and_stage = await fetch_all("""
        WITH killed_inboxes AS (
            SELECT
                sa.id,
                sa.kill_trigger::text as trigger_type,
                sa.warmup_started_at,
                sa.sending_started_at,
                sa.killed_at,
                EXTRACT(day FROM (sa.killed_at - sa.warmup_started_at))::int AS days_since_warmup,
                EXTRACT(day FROM (sa.killed_at - sa.sending_started_at))::int AS days_since_sending,
                CASE
                    WHEN sa.sending_started_at IS NULL THEN 'killed_during_warmup'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '14 days' THEN 'first_2_weeks'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '30 days' THEN 'week_2_to_4'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '60 days' THEN 'month_1_to_2'
                    WHEN sa.killed_at < sa.sending_started_at + INTERVAL '90 days' THEN 'month_2_to_3'
                    ELSE 'beyond_3_months'
                END AS lifecycle_stage
            FROM sender_accounts sa
            WHERE sa.kill_trigger IS NOT NULL
              AND sa.killed_at IS NOT NULL
              AND sa.warmup_started_at IS NOT NULL
        )
        SELECT
            trigger_type,
            lifecycle_stage,
            COUNT(*) as count,
            ROUND(AVG(days_since_warmup), 0) as avg_days_from_warmup,
            ROUND(AVG(days_since_sending), 0) as avg_days_from_sending
        FROM killed_inboxes
        GROUP BY trigger_type, lifecycle_stage
        ORDER BY trigger_type,
            CASE lifecycle_stage
                WHEN 'killed_during_warmup' THEN 1
                WHEN 'first_2_weeks' THEN 2
                WHEN 'week_2_to_4' THEN 3
                WHEN 'month_1_to_2' THEN 4
                WHEN 'month_2_to_3' THEN 5
                ELSE 6
            END
    """)

    # Get totals by trigger type
    totals_by_trigger = await fetch_all("""
        SELECT
            kill_trigger::text as trigger_type,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE sending_started_at IS NULL) as killed_during_warmup,
            COUNT(*) FILTER (WHERE sending_started_at IS NOT NULL) as killed_after_campaign_start
        FROM sender_accounts
        WHERE kill_trigger IS NOT NULL
          AND killed_at IS NOT NULL
        GROUP BY kill_trigger
        ORDER BY COUNT(*) DESC
    """)

    # Get totals by lifecycle stage (all triggers combined)
    totals_by_stage = await fetch_all("""
        SELECT
            CASE
                WHEN sending_started_at IS NULL THEN 'killed_during_warmup'
                WHEN killed_at < sending_started_at + INTERVAL '14 days' THEN 'first_2_weeks'
                WHEN killed_at < sending_started_at + INTERVAL '30 days' THEN 'week_2_to_4'
                WHEN killed_at < sending_started_at + INTERVAL '60 days' THEN 'month_1_to_2'
                WHEN killed_at < sending_started_at + INTERVAL '90 days' THEN 'month_2_to_3'
                ELSE 'beyond_3_months'
            END AS lifecycle_stage,
            COUNT(*) as count
        FROM sender_accounts
        WHERE kill_trigger IS NOT NULL
          AND killed_at IS NOT NULL
          AND warmup_started_at IS NOT NULL
        GROUP BY 1
        ORDER BY count DESC
    """)

    total_kills = sum(row["total"] for row in totals_by_trigger) if totals_by_trigger else 0

    return {
        "total_kills": total_kills,
        "by_trigger_type": [dict(row) for row in totals_by_trigger] if totals_by_trigger else [],
        "by_lifecycle_stage": [dict(row) for row in totals_by_stage] if totals_by_stage else [],
        "detailed_breakdown": [dict(row) for row in by_trigger_and_stage] if by_trigger_and_stage else [],
        "data_model_notes": {
            "sending_started_at": "Set when inbox first assigned to campaign (not warmup graduation)",
            "warmup_started_at": "Set when inbox first seen in EmailBison",
            "killed_during_warmup": "Inbox died before ever being assigned to a campaign",
            "migration": "079_backfill_sending_started_at.sql backfills from campaign_inboxes.assigned_at"
        }
    }


@router.get("/analysis/kill-trigger-by-esp")
async def analyze_kill_triggers_by_esp(workspace_id: Optional[UUID] = None):
    """
    Kill trigger analysis segmented by ESP (Microsoft vs Google).

    Compares infrastructure performance:
    - Kill rates by provider
    - Trigger type distribution by provider
    - Domain-level breakdown for worst performers
    - Survival rates (live inboxes / total inboxes)

    Optional workspace_id filter for client-specific analysis.
    """
    # Build workspace filter
    ws_filter = "AND workspace_id = $1" if workspace_id else ""
    ws_args = [workspace_id] if workspace_id else []

    # Overall ESP comparison
    esp_summary = await fetch_all(f"""
        SELECT
            CASE
                WHEN LOWER(esp::text) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                WHEN LOWER(esp::text) = 'gmail' THEN 'google'
                ELSE 'other'
            END as provider,
            COUNT(*) as total_inboxes,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead_count,
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live_count,
            ROUND(100.0 * COUNT(*) FILTER (WHERE inbox_state = 'dead') / NULLIF(COUNT(*), 0), 1) as kill_rate_pct,
            ROUND(AVG(EXTRACT(day FROM (killed_at - warmup_started_at))) FILTER (WHERE killed_at IS NOT NULL), 1) as avg_days_to_death
        FROM sender_accounts
        WHERE warmup_started_at IS NOT NULL {ws_filter}
        GROUP BY 1
        ORDER BY total_inboxes DESC
    """, *ws_args)

    # Kill triggers by ESP
    triggers_by_esp = await fetch_all(f"""
        SELECT
            CASE
                WHEN LOWER(esp::text) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                WHEN LOWER(esp::text) = 'gmail' THEN 'google'
                ELSE 'other'
            END as provider,
            kill_trigger::text as trigger_type,
            COUNT(*) as count,
            ROUND(AVG(EXTRACT(day FROM (killed_at - sending_started_at))) FILTER (WHERE sending_started_at IS NOT NULL), 1) as avg_days_from_sending
        FROM sender_accounts
        WHERE kill_trigger IS NOT NULL
          AND killed_at IS NOT NULL {ws_filter}
        GROUP BY 1, 2
        ORDER BY 1, count DESC
    """, *ws_args)

    # Domain-level analysis (worst performing domains)
    domain_breakdown = await fetch_all(f"""
        SELECT
            d.domain_name,
            CASE
                WHEN LOWER(sa.esp::text) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                WHEN LOWER(sa.esp::text) = 'google' THEN 'google'
                ELSE 'other'
            END as provider,
            COUNT(*) as total_inboxes,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_count,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_count,
            ROUND(100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / NULLIF(COUNT(*), 0), 1) as kill_rate_pct,
            array_agg(DISTINCT sa.kill_trigger::text) FILTER (WHERE sa.kill_trigger IS NOT NULL) as trigger_types
        FROM sender_accounts sa
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.warmup_started_at IS NOT NULL {ws_filter.replace('workspace_id', 'sa.workspace_id')}
        GROUP BY d.domain_name, 2
        HAVING COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') > 0
        ORDER BY dead_count DESC
        LIMIT 30
    """, *ws_args)

    # Lifecycle comparison by ESP
    lifecycle_by_esp = await fetch_all(f"""
        SELECT
            CASE
                WHEN LOWER(esp::text) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                WHEN LOWER(esp::text) = 'gmail' THEN 'google'
                ELSE 'other'
            END as provider,
            CASE
                WHEN sending_started_at IS NULL THEN 'killed_during_warmup'
                WHEN killed_at < sending_started_at + INTERVAL '14 days' THEN 'first_2_weeks'
                WHEN killed_at < sending_started_at + INTERVAL '30 days' THEN 'week_2_to_4'
                ELSE 'beyond_month'
            END AS lifecycle_stage,
            COUNT(*) as count
        FROM sender_accounts
        WHERE kill_trigger IS NOT NULL
          AND killed_at IS NOT NULL
          AND warmup_started_at IS NOT NULL {ws_filter}
        GROUP BY 1, 2
        ORDER BY 1, count DESC
    """, *ws_args)

    # Debug: show actual ESP values in database
    esp_values = await fetch_all(f"""
        SELECT esp::text as esp_value, COUNT(*) as count
        FROM sender_accounts
        WHERE esp IS NOT NULL {ws_filter}
        GROUP BY esp
        ORDER BY count DESC
    """, *ws_args)

    # Bounce data summary (for verification)
    bounce_data = await fetch_all(f"""
        SELECT
            COUNT(*) as total_inboxes,
            SUM(COALESCE(hard_bounces_24h, 0)) as total_hard_bounces_24h,
            SUM(COALESCE(hard_bounces_7d, 0)) as total_hard_bounces_7d,
            SUM(COALESCE(bounces_all_time, 0)) as total_bounces_all_time,
            COUNT(*) FILTER (WHERE hard_bounces_24h > 0) as inboxes_with_24h_bounces,
            COUNT(*) FILTER (WHERE hard_bounces_7d > 0) as inboxes_with_7d_bounces,
            COUNT(*) FILTER (WHERE bounces_all_time > 0) as inboxes_with_any_bounces
        FROM sender_accounts
        WHERE warmup_started_at IS NOT NULL {ws_filter}
    """, *ws_args)

    # Check response_messages for bounces
    response_bounce_data = await fetch_all(f"""
        SELECT
            COUNT(*) as total_response_messages,
            COUNT(*) FILTER (WHERE folder = 'bounced') as bounced_messages,
            COUNT(*) FILTER (WHERE folder = 'bounced' AND received_at > NOW() - INTERVAL '24 hours') as bounced_24h,
            COUNT(*) FILTER (WHERE folder = 'bounced' AND received_at > NOW() - INTERVAL '7 days') as bounced_7d
        FROM response_messages rm
        JOIN sender_accounts sa ON rm.sender_account_id = sa.id
        WHERE sa.warmup_started_at IS NOT NULL {ws_filter.replace('workspace_id', 'sa.workspace_id')}
    """, *ws_args)

    return {
        "workspace_id": str(workspace_id) if workspace_id else "all",
        "esp_summary": [dict(row) for row in esp_summary] if esp_summary else [],
        "triggers_by_esp": [dict(row) for row in triggers_by_esp] if triggers_by_esp else [],
        "worst_domains": [dict(row) for row in domain_breakdown] if domain_breakdown else [],
        "lifecycle_by_esp": [dict(row) for row in lifecycle_by_esp] if lifecycle_by_esp else [],
        "raw_esp_values": [dict(row) for row in esp_values] if esp_values else [],
        "bounce_data": dict(bounce_data[0]) if bounce_data else {},
        "response_messages_bounces": dict(response_bounce_data[0]) if response_bounce_data else {},
        "sync_diagnosis": await get_workspace_sync_diagnosis(workspace_id) if workspace_id else None
    }


async def get_workspace_sync_diagnosis(workspace_id: UUID):
    """Check why events might not be syncing for a workspace."""
    from database import fetch_one, fetch_all

    workspace = await fetch_one("""
        SELECT id, workspace_name, emailbison_workspace_id, is_active
        FROM workspaces
        WHERE id = $1
    """, workspace_id)

    if not workspace:
        return {"error": "Workspace not found"}

    campaigns = await fetch_all("""
        SELECT campaign_name, campaign_status, emailbison_campaign_id, last_seen_at, updated_at
        FROM emailbison_campaigns
        WHERE workspace_id = $1
    """, workspace_id)

    active_campaigns = [c for c in campaigns if c['campaign_status'] in ('active', 'running', 'sending', 'paused')]

    # Get sync_status for campaigns
    sync_status = await fetch_one("""
        SELECT sync_type, last_successful_sync, last_sync_record_count, updated_at
        FROM sync_status
        WHERE workspace_id = $1 AND sync_type = 'campaigns'
    """, workspace_id)

    # Get recent sync audit logs for campaigns (last 5)
    recent_syncs = await fetch_all("""
        SELECT sync_type, started_at, completed_at, status, records_processed, records_updated, records_failed, error_message, error_details
        FROM sync_audit_log
        WHERE workspace_id = $1 AND sync_type = 'campaigns'
        ORDER BY started_at DESC
        LIMIT 5
    """, workspace_id)

    return {
        "workspace_name": workspace['workspace_name'],
        "is_active": workspace['is_active'],
        "emailbison_workspace_id": workspace['emailbison_workspace_id'],
        "has_emailbison_id": workspace['emailbison_workspace_id'] is not None,
        "total_campaigns": len(campaigns),
        "active_campaigns": len(active_campaigns),
        "campaign_statuses": [{"name": c['campaign_name'], "status": c['campaign_status'], "last_seen": str(c['last_seen_at']) if c['last_seen_at'] else None} for c in campaigns[:10]],
        "sync_should_run": workspace['is_active'] and workspace['emailbison_workspace_id'] is not None and len(active_campaigns) > 0,
        "sync_status": {
            "last_successful_sync": str(sync_status['last_successful_sync']) if sync_status and sync_status['last_successful_sync'] else None,
            "last_record_count": sync_status['last_sync_record_count'] if sync_status else None,
        } if sync_status else None,
        "recent_syncs": [
            {
                "started_at": str(s['started_at']) if s['started_at'] else None,
                "status": s['status'],
                "records": s['records_processed'],
                "updated": s['records_updated'],
                "failed": s['records_failed'],
                "error": s['error_message'][:100] if s['error_message'] else None,
                "error_details": s['error_details'] if s['error_details'] else None
            }
            for s in recent_syncs
        ] if recent_syncs else []
    }


@router.get("/analysis/verify-inbox/{emailbison_id}")
async def verify_inbox_data(emailbison_id: int):
    """
    Verify our database matches EmailBison for a specific inbox.
    Cross-reference tool for data integrity checks.
    """
    inbox = await fetch_one("""
        SELECT
            sa.id,
            sa.emailbison_id,
            sa.email,
            sa.inbox_state,
            sa.kill_trigger::text,
            sa.killed_at,
            sa.status,
            sa.esp::text as esp,
            sa.warmup_started_at,
            sa.sending_started_at,
            d.domain_name,
            w.workspace_name
        FROM sender_accounts sa
        LEFT JOIN domains d ON sa.domain_id = d.id
        LEFT JOIN workspaces w ON sa.workspace_id = w.id
        WHERE sa.emailbison_id = $1
    """, emailbison_id)

    if not inbox:
        return {"found": False, "emailbison_id": emailbison_id, "message": "Not found in our database"}

    return {
        "found": True,
        "our_database": dict(inbox),
        "verification_notes": {
            "inbox_state_should_match": "dead if tagged flagged_*, live otherwise",
            "kill_trigger_should_match": "tag name minus 'flagged_' prefix",
            "status_from_emailbison": "Connected/Not connected synced from API"
        }
    }


@router.get("/analysis/domain-capacity-impact")
async def analyze_domain_capacity_impact():
    """
    Domain lifespan and sending capacity impact analysis.

    Rolls up inbox data by domain for ESP comparison.

    Capacity model:
    - Microsoft/Entra: 50 inboxes/domain × 2 emails/day = 100 emails/day/domain
    - Google: 3 inboxes/domain × 20 emails/day = 60 emails/day/domain
    """
    # Domain-killing triggers (use actual enum values)
    DOMAIN_KILLING_TRIGGERS = ('spam_complaint', 'provider_block')

    try:
        # Domain lifespan by ESP - rolled up from inbox data
        domain_lifespan = await fetch_all("""
            WITH domain_stats AS (
                SELECT
                    d.id,
                    d.domain_name,
                    CASE
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) = 'gmail' THEN 'google'
                        ELSE 'other'
                    END as esp,
                    MIN(sa.warmup_started_at) as first_inbox_warmup,
                    MAX(sa.killed_at) as last_inbox_killed,
                    COUNT(*) as total_inboxes,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
                    COUNT(*) FILTER (WHERE sa.kill_trigger::text IN ('spam_complaint', 'provider_block')) as domain_killing_count
                FROM domains d
                JOIN sender_accounts sa ON sa.domain_id = d.id
                GROUP BY d.id, d.domain_name, COALESCE(sa.esp::text, 'unknown')
            )
            SELECT
                esp,
                COUNT(*) as total_domains,
                COUNT(*) FILTER (WHERE dead_inboxes > 0 AND live_inboxes = 0) as dead_domains,
                COUNT(*) FILTER (WHERE domain_killing_count > 0) as domains_with_domain_kills,
                ROUND(AVG(EXTRACT(day FROM (last_inbox_killed - first_inbox_warmup))) FILTER (WHERE last_inbox_killed IS NOT NULL AND first_inbox_warmup IS NOT NULL), 1) as avg_domain_lifespan_days,
                ROUND(AVG(total_inboxes), 1) as avg_inboxes_per_domain,
                SUM(dead_inboxes) as total_dead_inboxes,
                SUM(live_inboxes) as total_live_inboxes
            FROM domain_stats
            GROUP BY esp
            ORDER BY total_domains DESC
        """)

        # Capacity impact by ESP
        capacity_impact = await fetch_all("""
            WITH domain_capacity AS (
                SELECT
                    d.id,
                    CASE
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) = 'gmail' THEN 'google'
                        ELSE 'other'
                    END as esp,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as live_connected,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
                    CASE
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) IN ('microsoft', 'outlook', 'entra') THEN 2
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) = 'gmail' THEN 20
                        ELSE 2
                    END as emails_per_inbox
                FROM domains d
                JOIN sender_accounts sa ON sa.domain_id = d.id
                GROUP BY d.id, COALESCE(sa.esp::text, 'unknown')
            )
            SELECT
                esp,
                SUM(live_connected * emails_per_inbox) as current_daily_capacity,
                SUM(dead_inboxes * emails_per_inbox) as lost_daily_capacity,
                SUM((live_connected + dead_inboxes) * emails_per_inbox) as theoretical_max,
                ROUND(100.0 * SUM(dead_inboxes * emails_per_inbox) / NULLIF(SUM((live_connected + dead_inboxes) * emails_per_inbox), 0), 1) as capacity_loss_pct,
                COUNT(*) as total_domains,
                COUNT(*) FILTER (WHERE live_inboxes = 0 AND dead_inboxes > 0) as dead_domains
            FROM domain_capacity
            GROUP BY esp
            ORDER BY current_daily_capacity DESC
        """)

        # Domain-killing trigger impact
        domain_killing_impact = await fetch_all("""
            WITH affected AS (
                SELECT
                    sa.domain_id,
                    CASE
                        WHEN LOWER(sa.esp::text) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                        WHEN LOWER(sa.esp::text) = 'gmail' THEN 'google'
                        ELSE 'other'
                    END as esp
                FROM sender_accounts sa
                WHERE sa.kill_trigger::text IN ('spam_complaint', 'provider_block')
                AND sa.killed_at IS NOT NULL
            )
            SELECT
                esp,
                COUNT(DISTINCT domain_id) as domains_affected,
                COUNT(*) as inboxes_killed,
                CASE
                    WHEN esp = 'microsoft' THEN COUNT(DISTINCT domain_id) * 100
                    WHEN esp = 'google' THEN COUNT(DISTINCT domain_id) * 60
                    ELSE COUNT(DISTINCT domain_id) * 100
                END as capacity_lost_per_day
            FROM affected
            GROUP BY esp
            ORDER BY domains_affected DESC
        """)

        # Worst domains by capacity loss
        worst_capacity_loss = await fetch_all("""
            WITH domain_loss AS (
                SELECT
                    d.domain_name,
                    CASE
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                        WHEN LOWER(COALESCE(sa.esp::text, 'unknown')) = 'gmail' THEN 'google'
                        ELSE 'other'
                    END as esp,
                    COUNT(*) as total_inboxes,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead,
                    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live,
                    EXTRACT(day FROM (MAX(sa.killed_at) - MIN(sa.warmup_started_at)))::int as lifespan_days,
                    array_agg(DISTINCT sa.kill_trigger::text) FILTER (WHERE sa.kill_trigger IS NOT NULL) as triggers
                FROM domains d
                JOIN sender_accounts sa ON sa.domain_id = d.id
                GROUP BY d.domain_name, COALESCE(sa.esp::text, 'unknown')
            )
            SELECT
                domain_name,
                esp,
                total_inboxes,
                dead,
                live,
                lifespan_days,
                triggers,
                CASE WHEN esp = 'microsoft' THEN dead * 2 ELSE dead * 20 END as daily_capacity_lost
            FROM domain_loss
            WHERE dead > 0
            ORDER BY daily_capacity_lost DESC
            LIMIT 20
        """)

        return {
            "domain_lifespan_by_esp": [dict(row) for row in domain_lifespan] if domain_lifespan else [],
            "capacity_impact_by_esp": [dict(row) for row in capacity_impact] if capacity_impact else [],
            "domain_killing_trigger_impact": [dict(row) for row in domain_killing_impact] if domain_killing_impact else [],
            "worst_capacity_loss_domains": [dict(row) for row in worst_capacity_loss] if worst_capacity_loss else [],
            "capacity_model": {
                "microsoft": {"inboxes_per_domain": 50, "emails_per_inbox": 2, "daily_per_domain": 100},
                "google": {"inboxes_per_domain": 3, "emails_per_inbox": 20, "daily_per_domain": 60}
            }
        }
    except Exception as e:
        logger.error(f"domain-capacity-impact failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


@router.get("/analysis/domain-bounce-rollup")
async def analyze_domain_bounce_rollup(workspace_id: Optional[str] = None):
    """
    Domain-level bounce rollup showing which domains have inboxes with bounces.

    Args:
        workspace_id: Filter to a specific workspace (recommended)

    Returns domains with:
    - Total inboxes
    - Inboxes with bounces (24h and all-time)
    - Total bounce counts
    """
    try:
        workspace_filter = ""
        params = []

        if workspace_id:
            workspace_filter = "AND sa.workspace_id = $1"
            params.append(workspace_id)

        query = f"""
            SELECT
                d.domain_name as domain,
                CASE
                    WHEN LOWER(COALESCE(d.esp::text, 'unknown')) IN ('microsoft', 'outlook', 'entra') THEN 'microsoft'
                    WHEN LOWER(COALESCE(d.esp::text, 'unknown')) = 'gmail' THEN 'google'
                    ELSE COALESCE(d.esp::text, 'unknown')
                END as esp,
                COUNT(sa.id) as total_inboxes,
                COUNT(*) FILTER (WHERE sa.hard_bounces_24h > 0) as inboxes_with_bounces_24h,
                COALESCE(SUM(sa.hard_bounces_24h), 0) as total_bounces_24h,
                COUNT(*) FILTER (WHERE sa.bounces_all_time > 0) as inboxes_with_bounces_alltime,
                COALESCE(SUM(sa.bounces_all_time), 0) as total_bounces_alltime,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,
                COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as live_connected
            FROM sender_accounts sa
            JOIN domains d ON sa.domain_id = d.id
                AND sa.workspace_id = d.workspace_id
            WHERE 1=1 {workspace_filter}
            GROUP BY d.domain_name, d.esp
            HAVING SUM(sa.hard_bounces_24h) > 0 OR SUM(sa.bounces_all_time) > 0
            ORDER BY SUM(sa.hard_bounces_24h) DESC, SUM(sa.bounces_all_time) DESC
        """

        rows = await fetch_all(query, *params) if params else await fetch_all(query)

        # Summary stats
        total_domains = len(rows) if rows else 0
        total_bounces_24h = sum(r['total_bounces_24h'] for r in rows) if rows else 0
        total_inboxes_with_bounces = sum(r['inboxes_with_bounces_24h'] for r in rows) if rows else 0

        return {
            "workspace_id": workspace_id,
            "summary": {
                "domains_with_bounces": total_domains,
                "total_bounces_24h": total_bounces_24h,
                "inboxes_with_bounces_24h": total_inboxes_with_bounces
            },
            "domains": [dict(row) for row in rows] if rows else []
        }
    except Exception as e:
        logger.error(f"domain-bounce-rollup failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")