"""
Inventory management models - Pool status, lifecycle tracking, and auto-kill
"""

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


# ===== STATUS TYPES =====

InventoryPoolStatus = Literal["deployed", "warning", "reserve"]
InventoryLifecycleStatus = Literal["active", "incubating", "dead"]
CapacityStatus = Literal["healthy", "warning", "critical"]


# ===== OVERVIEW MODELS =====

class InventoryOverview(BaseModel):
    """Complete inventory overview with pool/lifecycle distribution"""
    workspace_id: UUID

    # Pool distribution
    deployed_count: int = 0
    deployed_target: int = 0
    warning_count: int = 0
    reserve_count: int = 0
    reserve_target: int = 0

    # Lifecycle distribution
    active_count: int = 0
    incubating_count: int = 0
    dead_count: int = 0

    # Death breakdown (separates health issues from business churn)
    killed_by_trigger: int = 0  # System-killed (spam, bounces) - health metric
    deactivated: int = 0  # Manual/business churn - not a health problem

    # Capacity metrics
    total_inboxes: int = 0
    spare_capacity: int = 0
    spare_percentage: float = 0.0
    capacity_status: CapacityStatus = "healthy"

    # Feature flag
    auto_kill_enabled: bool = False

    last_updated: datetime


class InventoryInboxItem(BaseModel):
    """Individual inbox in inventory view"""
    inbox_id: UUID
    email: str
    domain_name: str
    pool_status: Optional[str] = "reserve"
    lifecycle_status: Optional[str] = "incubating"
    age_days: int = 0
    health_score: Optional[int] = None
    hard_bounces_24h: int = 0
    hard_bounces_7d: int = 0
    associated_campaigns: list[str] = []
    warning_reason: Optional[str] = None
    cooldown_ends_at: Optional[datetime] = None


class InventoryInboxListResponse(BaseModel):
    """Response for inbox list endpoint"""
    items: list[InventoryInboxItem]
    total: int
    filtered_by: Optional[str] = None


# ===== AUTO-KILL CONFIGURATION =====

class AutoKillConfig(BaseModel):
    """Auto-kill feature configuration"""
    enabled: bool = False
    cooldown_hours: int = 48
    auto_replace: bool = True
    notify_on_kill: bool = True


class AutoKillConfigResponse(BaseModel):
    """Response after updating auto-kill config"""
    success: bool
    message: str
    config: AutoKillConfig


# ===== KILL AND REPLACE =====

class KillAndReplaceRequest(BaseModel):
    """Request to kill an inbox and optionally replace in campaigns"""
    inbox_id: UUID
    kill_reason: str
    auto_replace: bool = True


class KillAndReplaceResponse(BaseModel):
    """Response after kill and replace operation"""
    killed_inbox_id: UUID
    killed_inbox_email: str
    affected_campaigns: list[str] = []
    replacement_inbox_id: Optional[UUID] = None
    replacement_inbox_email: Optional[str] = None
    success: bool
    message: str


# ===== AUTO-KILL PROCESSING =====

class ProcessAutoKillsResponse(BaseModel):
    """Response after processing auto-kills"""
    processed: int
    message: str
    details: list[dict] = []


# ===== AUDIT LOG =====

class InventoryAuditEvent(BaseModel):
    """Inventory audit log entry"""
    id: UUID
    workspace_id: Optional[UUID]
    inbox_id: Optional[UUID]
    inbox_email: Optional[str]
    event_type: str
    previous_pool_status: Optional[str]
    new_pool_status: Optional[str]
    previous_lifecycle_status: Optional[str]
    new_lifecycle_status: Optional[str]
    reason: Optional[str]
    triggered_by: Optional[str]
    related_campaign_ids: Optional[list[UUID]]
    created_at: datetime


class InventoryAuditLogResponse(BaseModel):
    """Response for audit log endpoint"""
    items: list[InventoryAuditEvent]
    total: int
