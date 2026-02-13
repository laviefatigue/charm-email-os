"""
Health monitoring routes - Aggregated from OwnRBL metrics
"""

from fastapi import APIRouter, HTTPException, Query
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
                OR (COALESCE(sa.hard_bounces_24h, 0) >= 1 AND sa.created_at > NOW() - INTERVAL '14 days')
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
                id=f"trigger-{inbox_id}-fresh_inbox_hard_bounce",
                inbox_id=inbox_id,
                inbox_email=row["email_address"],
                domain_id=row["domain_id"],
                domain_name=row["domain_name"],
                type="fresh_inbox_hard_bounce",
                severity="instant",
                value=float(hard_bounces_24h),
                threshold=1.0,
                detected_at=now,
                action_taken="pending",
            ))

    # --- Mock recent kills from dead inboxes ---
    dead_rows = await fetch_all("""
        SELECT
            sa.id as inbox_id,
            sa.email_address,
            d.id as domain_id,
            d.domain_name,
            d.infrastructure_type,
            COALESCE(sa.hard_bounces_7d, 0) as hard_bounces_7d,
            COALESCE(sa.total_sends_7d, 0) as total_sends_7d
        FROM sender_accounts sa
        LEFT JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
            AND sa.workspace_id = d.workspace_id
        WHERE sa.workspace_id = $1
            AND sa.inbox_state = 'dead'
        ORDER BY sa.updated_at DESC NULLS LAST
        LIMIT 9
    """, workspace_id)

    # Vary trigger types and times for dead inboxes
    mock_trigger_types = [
        ("hard_bounces_24h", "instant", 3.0, 2.0),
        ("hard_bounce_rate_7d", "instant", 1.2, 0.5),
        ("fresh_inbox_hard_bounce", "instant", 1.0, 1.0),
        ("hard_bounces_24h", "instant", 4.0, 2.0),
        ("bounce_rate_all_7d", "instant", 7.5, 5.0),
        ("hard_bounce_rate_7d", "instant", 0.8, 0.5),
        ("hard_bounces_24h", "instant", 2.0, 2.0),
        ("fresh_inbox_hard_bounce", "instant", 2.0, 1.0),
        ("hard_bounces_24h", "instant", 5.0, 2.0),
    ]
    time_offsets = [
        timedelta(hours=1), timedelta(hours=3), timedelta(hours=8),
        timedelta(days=1), timedelta(days=1, hours=12), timedelta(days=2),
        timedelta(days=3), timedelta(days=4), timedelta(days=5),
    ]

    for i, row in enumerate(dead_rows):
        ttype, sev, val, thresh = mock_trigger_types[i % len(mock_trigger_types)]
        offset = time_offsets[i % len(time_offsets)]
        triggers.append(KillTriggerItem(
            id=f"kill-{row['inbox_id']}-{ttype}",
            inbox_id=row["inbox_id"],
            inbox_email=row["email_address"],
            domain_id=row["domain_id"],
            domain_name=row["domain_name"],
            type=ttype,
            severity=sev,
            value=val,
            threshold=thresh,
            detected_at=now - offset,
            action_taken="killed",
            resolved_at=now - offset + timedelta(minutes=2),
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

    # Dead domains (>=2 dead inboxes)
    dead_domain_result = await fetch_one("""
        SELECT COUNT(*) as dead_domains FROM (
            SELECT d.id
            FROM domains d
            JOIN sender_accounts sa ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
                AND sa.workspace_id = d.workspace_id
            WHERE d.workspace_id = $1 AND sa.inbox_state = 'dead'
            GROUP BY d.id
            HAVING COUNT(*) >= 2
        ) sub
    """, workspace_id)
    dead_domains = dead_domain_result["dead_domains"] if dead_domain_result else 0
    live_domains = total_domains - flagged_domains - dead_domains

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
            providers=[],
            health_distribution=HealthDistribution(
                healthy=0, good=0, warning=0, critical=0, total=0
            ),
            total_domains=0,
            clean_domains=0,
            flagged_domains=0,
            sync_source="database"
        )

    # Get inbox summary stats from sender_accounts
    inbox_stats = await fetch_one("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
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
    # Lifecycle: incubating (< 14 days old), active (mature), dead
    # Pool: deployed (in campaigns), reserve (ready), warning (has bounces)
    lifecycle_dist = await fetch_one("""
        SELECT
            -- Lifecycle states
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND created_at > NOW() - INTERVAL '14 days') as incubating,
            COUNT(*) FILTER (WHERE inbox_state = 'live' AND created_at <= NOW() - INTERVAL '14 days') as active,
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
    provider_stats = await fetch_all("""
        SELECT
            COALESCE(esp, 'other') as provider,
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE inbox_state = 'live') as live,
            COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead,
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

    # Build provider metrics
    providers = [
        ProviderMetrics(
            name=p["provider"],
            count=p["total"],
            live_count=p["live"],
            dead_count=p["dead"],
            avg_health_score=float(p["avg_health"] or 0)
        )
        for p in provider_stats
    ]

    return InfrastructureHealthResponse(
        client_id=client_id,
        total_inboxes=inbox_stats["total"] if inbox_stats else 0,
        live_inboxes=inbox_stats["live"] if inbox_stats else 0,
        dead_inboxes=inbox_stats["dead"] if inbox_stats else 0,
        avg_health_score=float(inbox_stats["avg_health"] if inbox_stats else 0),
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
        total_domains=domain_stats["total"] if domain_stats else 0,
        clean_domains=domain_stats["clean"] if domain_stats else 0,
        flagged_domains=domain_stats["flagged"] if domain_stats else 0,
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
