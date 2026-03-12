"""
Inbox models - Maps to OwnRBL sender_accounts table
"""

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


InboxStatus = Literal["pending", "warmup", "active", "paused", "dead"]
InboxHealthState = Literal["healthy", "warning", "critical", "dead"]
InboxState = Literal["live", "dead"]
ESPType = Literal["gmail", "microsoft", "other"]

# v3.0 Kill Trigger types from OwnRBL
KillTriggerType = Literal[
    "bounce_24h",
    "bounce_7d",
    "bounce_rate_7d",
    "total_bounce_rate",
    "fresh_inbox_bounce",
    "fresh_inbox_blocked",
    "fresh_inbox_unknown",
    "spam_complaint",
    "rbl_critical",
    "warmup_failed",
    "manual"
]


class InboxBase(BaseModel):
    """Base inbox fields"""
    email_address: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None


class InboxCreate(InboxBase):
    """Create a new inbox"""
    workspace_id: UUID
    domain_id: Optional[UUID] = None
    esp_type: ESPType = "other"


class Inbox(BaseModel):
    """Full inbox model from OwnRBL sender_accounts"""
    id: UUID
    workspace_id: UUID
    client_id: Optional[UUID] = None  # Reverse-lookup from clients table
    emailbison_account_id: Optional[int] = None  # External sync ID

    # Identity
    email_address: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None

    # Status
    status: InboxStatus = "pending"
    inbox_state: InboxState = "live"  # v3.0 health state
    esp_type: Optional[str] = None

    # Warmup metrics
    warmup_enabled: bool = False
    warmup_score: Optional[float] = None
    warmup_progress: Optional[int] = None
    daily_send_limit: Optional[int] = None

    # Bounce metrics (kill trigger data)
    hard_bounces_24h: Optional[int] = None
    hard_bounces_7d: Optional[int] = None
    soft_bounces_7d: Optional[int] = None
    total_sends_7d: Optional[int] = None
    bounce_rate_7d: Optional[float] = None

    # v3.0 Kill trigger
    removal_tag: Optional[str] = None
    removal_tagged_at: Optional[datetime] = None
    removed_at: Optional[datetime] = None
    kill_reason: Optional[str] = None

    # Computed health state
    health_state: InboxHealthState = "healthy"
    health_score: Optional[float] = None  # EmailBison health score (0-100)

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Domain info (joined)
    domain_name: Optional[str] = None

    class Config:
        from_attributes = True


class InboxList(BaseModel):
    """List of inboxes with pagination"""
    items: list[Inbox]
    total: int
    page: int = 1
    page_size: int = 50

    # Aggregates
    healthy_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    dead_count: int = 0


class InboxHealth(BaseModel):
    """Detailed inbox health metrics"""
    inbox_id: UUID
    email_address: str
    health_state: InboxHealthState
    inbox_state: InboxState

    # Warmup
    warmup_enabled: bool
    warmup_score: Optional[float] = None
    warmup_progress: Optional[int] = None

    # Bounce metrics
    hard_bounces_24h: int = 0
    hard_bounces_7d: int = 0
    soft_bounces_7d: int = 0
    total_sends_7d: int = 0
    bounce_rate_7d: float = 0.0

    # Kill trigger info
    removal_tag: Optional[str] = None
    removal_tagged_at: Optional[datetime] = None
    at_risk: bool = False  # True if approaching kill threshold


class InboxKillRequest(BaseModel):
    """Request to manually kill an inbox"""
    reason: str
    kill_trigger: KillTriggerType = "manual"


class InboxGenerateRequest(BaseModel):
    """Request to generate inboxes from onboarding"""
    client_id: UUID
    domain_id: UUID
    first_names: list[str]
    count: int = 1
