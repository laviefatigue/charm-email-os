"""
Domain models - Read from OwnRBL domains table
"""

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


DomainStatus = Literal[
    "available",         # Generated, ready for purchase (replaces pending/approved)
    "pending",           # Legacy: alias for available
    "pending_approval",  # Legacy: alias for available
    "approved",          # Legacy: alias for available
    "rejected",          # Legacy: deprecated
    "denied",            # Legacy: deprecated
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
InfrastructureType = Literal["entra", "google"]


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

    # Domain age tracking (for 30-day setup requirement)
    registration_date: Optional[datetime] = None  # When domain was first registered (from WHOIS/registrar)
    available_for_setup_at: Optional[datetime] = None  # registration_date + 30 days

    # Pricing from registrar checks (saved for fast loading)
    porkbun_price: Optional[float] = None
    porkbun_available: Optional[bool] = None
    dynadot_price: Optional[float] = None
    dynadot_available: Optional[bool] = None
    cached_price: Optional[float] = None  # Best price between providers

    # Computed domain age fields (populated by API)
    domain_age_days: Optional[int] = None  # Days since registration
    days_until_available: Optional[int] = None  # Days until 30-day threshold (0 if ready/exempt)
    is_setup_eligible: bool = False  # True if (30+ days old OR exempt) AND NS verified
    is_age_exempt: bool = False  # True if status is 'legacy' or 'active' (bypasses 30-day check)

    # Timestamps
    flagged_at: Optional[datetime] = None
    dead_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Purchase job locking (domain reserved by active purchase job)
    purchase_job_id: Optional[UUID] = None  # Job locking this domain
    purchase_job_status: Optional[str] = None  # Cached job status (pending/executing/failed/completed)

    # Infrastructure type (Entra or Google) - set when inboxes are provisioned
    infrastructure_type: Optional[InfrastructureType] = None  # entra or google
    infrastructure_set_at: Optional[datetime] = None  # When infrastructure was assigned

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
