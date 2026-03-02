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
    tag_name: Optional[str] = None  # Trigger-specific tag applied in EmailBison (e.g., flagged_fresh_inbox_bounce)


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


# ===== Infrastructure Health Models (Database-Only) =====

class ProviderMetrics(BaseModel):
    """Provider breakdown metrics"""
    name: str  # gmail, microsoft, other
    count: int
    live_count: int
    dead_count: int
    avg_health_score: float
    # Connection status (OAuth state from EmailBison)
    connected_count: int = 0  # Live + Connected (operational)
    disconnected_count: int = 0  # Live + Not connected (needs reconnection)


class HealthDistribution(BaseModel):
    """Health score distribution for pie chart"""
    healthy: int  # 80-100
    good: int  # 60-80
    warning: int  # 40-60
    critical: int  # 0-40
    total: int


class LifecycleDistribution(BaseModel):
    """Lifecycle distribution for inventory visibility - shows inbox maturity and pool status"""
    # Lifecycle states (mutually exclusive)
    incubating: int  # < 14 days old or on warming domain
    active: int  # Mature, ready for deployment
    dead: int  # Killed/deactivated

    # Pool status (for live inboxes only)
    deployed: int  # Currently assigned to active campaigns
    reserve: int  # Ready pool, not in campaigns
    warning: int  # Has recent bounces, needs cooldown

    # Total for display (excludes dead by default in pie chart)
    total_live: int  # incubating + active (or deployed + reserve + warning for live only)


class WarningLevelDistribution(BaseModel):
    """
    Warning level distribution for predictive death forecasting.
    Tracks inboxes by proximity to kill thresholds.
    """
    # Warning levels (progressive severity)
    healthy: int = 0     # No bounces, stable
    watching: int = 0    # 1-2 hard bounces in 7d (pattern forming)
    warning: int = 0     # 1 hard bounce in 24h (next bounce = kill)
    critical: int = 0    # At or above kill threshold (pending kill)

    # Summary
    total_at_risk: int = 0  # watching + warning + critical


class InfrastructureHealthResponse(BaseModel):
    """
    Infrastructure health from LOCAL DATABASE only.
    No live EmailBison API calls - data refreshed by sync worker.
    """
    client_id: UUID

    # Summary metrics
    total_inboxes: int
    live_inboxes: int  # inbox_state = 'live' (includes disconnected)
    dead_inboxes: int  # inbox_state = 'dead' (killed by triggers)
    avg_health_score: float

    # Connection status breakdown (CRITICAL for accuracy)
    # Operational = Live + Connected (can actually send email)
    # Disconnected = Live + Not connected (OAuth expired, needs reconnection)
    connected_inboxes: int = 0  # Operational - can send NOW
    disconnected_inboxes: int = 0  # Live but OAuth expired - CANNOT send

    # Capacity metrics
    operational_capacity: int = 0  # SUM(daily_limit) for connected inboxes only
    potential_capacity: int = 0  # SUM(daily_limit) for all live inboxes (if reconnected)

    # Provider breakdown (from sender_accounts.esp)
    providers: list[ProviderMetrics]

    # Health distribution (for pie chart - health score based)
    health_distribution: HealthDistribution

    # Lifecycle distribution (for inventory visibility - shows all inboxes except dead)
    lifecycle_distribution: Optional["LifecycleDistribution"] = None

    # Warning level distribution (for predictive death forecasting)
    warning_distribution: Optional["WarningLevelDistribution"] = None

    # Domain metrics (from domains table)
    total_domains: int
    live_domains: int  # Domains with at least 1 live inbox
    dead_domains: int  # Domains with 0 live inboxes (legacy HyperTide domains)
    clean_domains: int
    flagged_domains: int

    # Domain source breakdown (how domains were acquired)
    domain_source_breakdown: Optional[dict] = None  # {generated: X, purchased: Y, legacy: Z}

    # Data freshness
    last_sync: Optional[datetime] = None
    sync_source: str = "database"


# ===== Daily Volume Snapshot Models (for Capacity Chart) =====

class DailyVolumeSnapshot(BaseModel):
    """Single day's volume and capacity snapshot for time-series chart."""

    date: datetime  # Snapshot date
    emails_sent: int = 0  # Total emails sent this day
    emails_delivered: int = 0  # Emails successfully delivered
    emails_bounced: int = 0  # Emails bounced
    daily_capacity_available: int = 0  # Total daily capacity (sum of inbox limits)
    live_inboxes: int = 0  # Count of live inboxes as of end of day
    incubating_inboxes: int = 0  # Count of incubating inboxes
    dead_inboxes: int = 0  # Count of dead inboxes
    capacity_utilization_pct: Optional[float] = None  # Percentage of capacity used (0-100)
    kills_that_day: int = 0  # Inboxes killed on this day


class KillEventAnnotation(BaseModel):
    """Kill event for chart annotation (vertical marker)."""

    date: datetime  # Date of kill event
    inboxes_killed: int = 0  # Number of inboxes killed this day
    kill_reasons: str = ""  # Comma-separated list of kill trigger types


class DailyVolumeHistoryResponse(BaseModel):
    """Response containing daily volume history for dashboard chart."""

    client_id: UUID
    workspace_id: Optional[UUID] = None
    start_date: datetime
    end_date: datetime
    days_requested: int = 90
    days_returned: int = 0

    # Time-series data
    snapshots: list[DailyVolumeSnapshot] = []

    # Kill events for chart annotations
    kill_events: list[KillEventAnnotation] = []

    # Summary metrics
    total_emails_sent: int = 0
    avg_daily_capacity: int = 0
    avg_utilization_pct: float = 0.0
    total_kills: int = 0


class CapacityInsight(BaseModel):
    """Auto-generated insight message for capacity chart."""

    icon: str = ""  # Emoji icon
    message: str = ""  # Insight text
    severity: str = "info"  # info, warning, critical


class FlaggedInboxItem(BaseModel):
    """Single flagged/killed inbox for export."""

    workspace_name: str
    domain_name: Optional[str] = None
    email_address: str
    kill_trigger: Optional[str] = None
    killed_at: Optional[datetime] = None
    days_before_kill: Optional[int] = None
    inbox_state: str
    connection_status: Optional[str] = None
    warmup_started_at: Optional[datetime] = None
    hard_bounces_24h: int = 0
    hard_blocked_24h: int = 0
    hard_unknown_24h: int = 0
    complaints_lifetime: int = 0
    trigger_value: Optional[float] = None
    trigger_threshold: Optional[float] = None
