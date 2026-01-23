"""
Domain models - Read from OwnRBL domains table
"""

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


DomainStatus = Literal[
    "pending",           # Generated, waiting for approval
    "pending_approval",  # Alias for pending
    "approved",          # Approved, ready to purchase
    "rejected",          # Denied, won't purchase
    "purchasing",        # Purchase in progress
    "purchased",         # Domain bought, no inboxes yet
    "provisioning",      # Inboxes being created in Hypertide
    "active",            # Domain with active inboxes (proper workflow)
    "legacy",            # Pre-existing domains before 1/22/26 (needs audit)
    "warming",           # In warmup period
    "flagged",           # Health issues detected
    "dead"               # Retired/disabled
]
DomainHealthState = Literal["healthy", "warning", "critical", "unknown"]
NameserverStatus = Literal["pending", "verified", "failed", "mismatch", "propagating"]


class DomainBase(BaseModel):
    """Base domain fields"""
    domain_name: str
    workspace_id: UUID


class DomainCreate(DomainBase):
    """Create a new domain"""
    status: DomainStatus = "pending"


RegistrarProvider = Literal["porkbun", "dynadot"]


class Domain(BaseModel):
    """Full domain model from OwnRBL"""
    id: UUID
    workspace_id: UUID
    client_id: Optional[UUID] = None  # Reverse-lookup from clients table
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

    # Purchase & DNS tracking for Hypertide readiness
    purchased_at: Optional[datetime] = None  # When domain was purchased
    nameservers_updated_at: Optional[datetime] = None  # When NS set to DNSimple (24hr propagation)
    selected_provider: Optional[RegistrarProvider] = None  # Which registrar owns this domain

    # Nameserver verification status
    nameserver_status: Optional[NameserverStatus] = "pending"  # pending, verified, failed, mismatch
    nameserver_verified_at: Optional[datetime] = None  # When verification was last run
    current_nameservers: Optional[list[str]] = None  # Actual NS returned from registrar

    # Timestamps
    flagged_at: Optional[datetime] = None
    dead_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Inbox counts from this domain
    inbox_count: int = 0
    live_inbox_count: int = 0
    dead_inbox_count: int = 0

    # Blacklist details (names of RBLs domain is listed on)
    blacklist_names: Optional[list[str]] = None

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
