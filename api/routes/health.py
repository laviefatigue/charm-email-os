"""
Health monitoring routes - Aggregated from OwnRBL metrics
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
import logging

from database import fetch_all, fetch_one
from models.health import (
    HealthOverview, HealthDashboard, InboxHealthMetrics,
    DomainHealthMetrics, Alert, KillTriggerStats
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

    # Get campaign stats
    campaign_stats = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE campaign_status = 'active') as active,
            COALESCE(SUM(emails_sent), 0) as total_sent,
            COALESCE(AVG(reply_rate), 0) as avg_reply_rate,
            COALESCE(AVG(bounce_rate), 0) as avg_bounce_rate
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
