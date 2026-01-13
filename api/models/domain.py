"""
Domain models - Read from OwnRBL domains table
"""

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


DomainStatus = Literal["pending", "active", "flagged", "dead"]
DomainHealthState = Literal["healthy", "warning", "critical", "unknown"]


class DomainBase(BaseModel):
    """Base domain fields"""
    domain_name: str
    workspace_id: UUID


class DomainCreate(DomainBase):
    """Create a new domain"""
    status: DomainStatus = "pending"


class Domain(BaseModel):
    """Full domain model from OwnRBL"""
    id: UUID
    workspace_id: UUID
    domain_name: str
    status: DomainStatus = "active"

    # Health metrics from domain_check_summary
    latest_health_score: Optional[float] = None
    latest_blacklist_count: Optional[int] = None
    latest_whitelist_count: Optional[int] = None
    is_clean: Optional[bool] = None
    last_checked_at: Optional[datetime] = None

    # Computed health state
    health_state: DomainHealthState = "unknown"

    # Timestamps
    flagged_at: Optional[datetime] = None
    dead_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Inbox count from this domain
    inbox_count: int = 0

    class Config:
        from_attributes = True


class DomainList(BaseModel):
    """List of domains with pagination"""
    items: list[Domain]
    total: int
    page: int = 1
    page_size: int = 50


class DomainHealth(BaseModel):
    """Domain health details including RBL status"""
    domain_id: UUID
    domain_name: str
    health_score: float
    blacklist_count: int = 0
    whitelist_count: int = 0
    is_clean: bool = True
    health_state: DomainHealthState = "unknown"
    last_checked_at: Optional[datetime] = None

    # RBL check details
    rbl_results: Optional[list[dict]] = None  # Individual RBL check results
    critical_listings: Optional[list[str]] = None  # Major blacklists


class DomainGenerateRequest(BaseModel):
    """Request to generate domains from onboarding"""
    client_id: UUID
    primary_domain: str
    count: int = 1
