"""
Health monitoring models - Aggregated from OwnRBL metrics
"""

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


AlertSeverity = Literal["info", "warning", "critical"]
AlertType = Literal[
    "inbox_bounce_threshold",
    "inbox_warmup_failed",
    "domain_blacklisted",
    "domain_health_low",
    "campaign_bounce_high",
    "campaign_reply_low"
]


class InboxHealthMetrics(BaseModel):
    """Health metrics for a single inbox"""
    inbox_id: UUID
    email_address: str
    health_state: str  # healthy, warning, critical, dead
    inbox_state: str  # live, dead

    # Warmup
    warmup_enabled: bool = False
    warmup_score: Optional[float] = None

    # Bounce metrics
    hard_bounces_24h: int = 0
    hard_bounces_7d: int = 0
    bounce_rate_7d: float = 0.0

    # Kill trigger status
    removal_tag: Optional[str] = None
    at_risk: bool = False


class DomainHealthMetrics(BaseModel):
    """Health metrics for a single domain"""
    domain_id: UUID
    domain_name: str
    health_state: str  # healthy, warning, critical, unknown

    # RBL status
    health_score: float = 100.0
    blacklist_count: int = 0
    whitelist_count: int = 0
    is_clean: bool = True

    # Critical listings
    critical_blacklists: Optional[list[str]] = None

    # Last check
    last_checked_at: Optional[datetime] = None


class Alert(BaseModel):
    """Health alert"""
    id: str
    type: AlertType
    severity: AlertSeverity
    title: str
    message: str

    # Related entities
    client_id: Optional[UUID] = None
    workspace_id: Optional[UUID] = None
    inbox_id: Optional[UUID] = None
    domain_id: Optional[UUID] = None
    campaign_id: Optional[UUID] = None

    # Context
    entity_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None

    # Timestamps
    created_at: datetime
    acknowledged_at: Optional[datetime] = None


class HealthOverview(BaseModel):
    """Overall health overview for a client"""
    client_id: UUID
    client_name: str
    workspace_id: Optional[UUID] = None

    # Inbox summary
    total_inboxes: int = 0
    healthy_inboxes: int = 0
    warning_inboxes: int = 0
    critical_inboxes: int = 0
    dead_inboxes: int = 0

    # Domain summary
    total_domains: int = 0
    clean_domains: int = 0
    flagged_domains: int = 0

    # Campaign summary
    active_campaigns: int = 0
    total_emails_sent: int = 0
    overall_reply_rate: float = 0.0
    overall_bounce_rate: float = 0.0

    # Active alerts
    critical_alerts: int = 0
    warning_alerts: int = 0
    alerts: Optional[list[Alert]] = None

    # Last updated
    last_updated: datetime


class HealthDashboard(BaseModel):
    """Full health dashboard data"""
    overview: HealthOverview
    inbox_metrics: list[InboxHealthMetrics]
    domain_metrics: list[DomainHealthMetrics]
    recent_alerts: list[Alert]

    # Kill trigger summary
    inboxes_at_risk: int = 0
    inboxes_killed_today: int = 0
    inboxes_killed_week: int = 0


class KillTriggerStats(BaseModel):
    """Kill trigger statistics"""
    workspace_id: UUID

    # Counts by trigger type
    bounce_24h_kills: int = 0
    bounce_7d_kills: int = 0
    rbl_critical_kills: int = 0
    warmup_failed_kills: int = 0
    manual_kills: int = 0

    # Time-based
    kills_today: int = 0
    kills_this_week: int = 0
    kills_this_month: int = 0

    # At-risk inboxes
    at_risk_bounce_24h: int = 0
    at_risk_bounce_7d: int = 0
    at_risk_rbl: int = 0
