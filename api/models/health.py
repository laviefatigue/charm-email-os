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


# ===== Full Dashboard Models =====

class KillTriggerItem(BaseModel):
    """Individual kill trigger detected on an inbox"""
    id: str
    inbox_id: UUID
    inbox_email: str
    domain_id: Optional[UUID] = None
    domain_name: Optional[str] = None
    type: str  # hard_bounces_24h, hard_bounce_rate_7d, bounce_rate_all_7d, fresh_inbox_hard_bounce
    severity: str  # instant, confirming
    value: float
    threshold: float
    detected_at: datetime
    action_taken: Optional[str] = None  # killed, dismissed, pending
    resolved_at: Optional[datetime] = None
    retest_at: Optional[datetime] = None


class BackupTierStatus(BaseModel):
    """Status for a single backup capacity tier"""
    tier: str  # primary, hot_backup, warming_pipeline
    label: str
    count: int
    target_count: int
    percentage: float
    status: str  # healthy, warning, critical


class BackupCapacityResponse(BaseModel):
    """Overall backup capacity across all tiers"""
    primary: BackupTierStatus
    hot_backup: BackupTierStatus
    warming_pipeline: BackupTierStatus
    total_capacity: int
    active_capacity: int
    backup_ratio: float
    overall_status: str  # healthy, warning, critical


class DomainGridItem(BaseModel):
    """Domain health data for the domain grid"""
    domain_id: UUID
    domain: str
    state: str  # live, flagged, dead
    phase: str  # warming, ramping, establishing, peak, monitoring, rotation
    overall_health_score: float
    total_inboxes: int
    live_inboxes: int
    dead_inboxes: int
    warming_inboxes: int = 0
    age_in_days: int
    days_until_rotation: int
    infrastructure_type: Optional[str] = None  # entra, google
    gmail_reputation: Optional[str] = None
    microsoft_reputation: Optional[str] = None
    last_inbox_placement: Optional[float] = None
    last_spam_placement: Optional[float] = None
    created_at: datetime
    last_health_check: Optional[datetime] = None


class CampaignAttributionItem(BaseModel):
    """Campaign health attribution data"""
    campaign_id: UUID
    campaign_name: str
    state: str  # live, quarantined, dead
    inboxes_killed_7d: int = 0
    domains_affected: int = 0
    total_sent: int
    bounce_count: int
    bounce_rate: float
    complaint_count: int
    complaint_rate: float
    risk_level: str  # low, medium, high, critical


class OverallSummaryResponse(BaseModel):
    """Enhanced overall health summary for the dashboard"""
    client_id: UUID
    health_score: int
    status: str  # healthy, warning, critical
    status_message: str
    total_domains: int
    live_domains: int
    flagged_domains: int
    dead_domains: int
    total_inboxes: int
    live_inboxes: int
    dead_inboxes: int
    warming_inboxes: int
    pending_kill_triggers: int
    active_alerts: int
    last_refresh: datetime


class ContaminationSourceItem(BaseModel):
    """Lead list contamination source data"""
    id: str
    list_name: str
    campaign_id: UUID
    campaign_name: str
    total_leads: int
    bounced_leads: int
    bounce_rate: float
    source_type: str  # enrichment, scraped, manual, purchased, unknown
    source_provider: Optional[str] = None  # Apollo, ZoomInfo, etc.
    imported_at: datetime
    status: str  # live, quarantined, flagged
    inboxes_affected: int = 0
    domains_affected: int = 0


class ESPSummaryItem(BaseModel):
    """ESP health summary data"""
    provider: str  # gmail, microsoft
    reputation: str  # high, medium, low, bad
    reputation_trend: str  # improving, stable, declining
    inbox_placement_rate: float
    spam_placement_rate: float
    promotions_placement_rate: Optional[float] = None  # Gmail only
    spf_passing: bool = True
    dkim_passing: bool = True
    dmarc_passing: bool = True
    # Gmail-specific
    user_reported_spam_rate: Optional[float] = None
    ip_reputation: Optional[str] = None
    # Microsoft-specific
    complaint_rate: Optional[float] = None
    trap_hits: Optional[int] = None
    filter_result: Optional[str] = None  # green, yellow, red
    last_updated: datetime


class FullDashboardResponse(BaseModel):
    """Composite response for the full health dashboard"""
    overall_summary: OverallSummaryResponse
    kill_triggers: list[KillTriggerItem]
    backup_capacity: Optional[BackupCapacityResponse] = None
    domain_grid: list[DomainGridItem]
    campaign_attribution: list[CampaignAttributionItem]
    contamination_sources: list[ContaminationSourceItem] = []
    esp_summaries: list[ESPSummaryItem] = []
