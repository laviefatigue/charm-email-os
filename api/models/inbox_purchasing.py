"""
Pydantic models for inbox purchasing API.

Maps to HyperTide automation models for order calculation and purchase execution.
"""

from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from enum import Enum


class InboxProviderType(str, Enum):
    """Inbox provider type."""
    ENTRA = "entra"
    GOOGLE = "google"


class OrderStatus(str, Enum):
    """Purchase job status."""
    PENDING = "pending"
    CALCULATING = "calculating"
    READY = "ready"
    PROCESSING = "processing"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


# =============================================================================
# Request Models
# =============================================================================

class InboxTargetRequest(BaseModel):
    """Target inbox counts for calculation."""
    entra_inboxes: int = Field(default=0, ge=0, description="Target Entra inbox count")
    google_inboxes: int = Field(default=0, ge=0, description="Target Google inbox count")


class InboxNameConfig(BaseModel):
    """Configuration for a single inbox name."""
    first_name: str = Field(..., description="First name for inbox")
    last_name: str = Field(..., description="Last name for inbox")

    @property
    def email_prefix(self) -> str:
        """Generate the email prefix (before @)."""
        return f"{self.first_name.lower()}.{self.last_name.lower()}"


class DomainForInboxes(BaseModel):
    """Domain selection for inbox purchase."""
    domain_id: UUID
    domain_name: str
    provider_type: InboxProviderType = InboxProviderType.ENTRA


class CalculateOrdersRequest(BaseModel):
    """Request to calculate optimal order quantities."""
    client_id: UUID
    inbox_target: InboxTargetRequest


class GenerateNamesRequest(BaseModel):
    """Request to generate inbox names."""
    client_id: UUID
    count: int = Field(default=10, ge=1, le=50, description="Number of names to generate")
    first_names: Optional[list[str]] = Field(
        default=None,
        description="Custom first names to use (otherwise generates from common names)"
    )
    last_names: Optional[list[str]] = Field(
        default=None,
        description="Custom last names to use (otherwise generates from common names)"
    )


class ExecutePurchaseRequest(BaseModel):
    """Request to execute inbox purchase via HyperTide."""
    client_id: UUID
    client_name: str
    forwarding_domain: str = Field(..., description="Client's main domain for grouping")

    # Order specification
    inbox_target: InboxTargetRequest

    # Domain configuration (optional)
    entra_domains: list[DomainForInboxes] = Field(default_factory=list)
    google_domains: list[DomainForInboxes] = Field(default_factory=list)

    # Inbox naming
    inbox_names: list[InboxNameConfig] = Field(
        default_factory=list,
        max_length=10,
        description="Custom inbox names (max 10, leave empty for HyperTide defaults)"
    )

    # EmailBison credentials (for connecting inboxes after purchase)
    bison_username: Optional[str] = None
    bison_password: Optional[str] = None
    bison_workspace: Optional[str] = None
    bison_url: str = Field(default="https://spellcast.hirecharm.com")
    bison_api_key: Optional[str] = Field(default=None, description="EmailBison API key for workspace fetch")

    # Payment
    use_saved_payment: bool = Field(default=True, description="Use saved Stripe payment method")


# =============================================================================
# Response Models
# =============================================================================

class OrderBreakdownResponse(BaseModel):
    """Calculated order breakdown response."""
    # Entra calculations
    entra_orders: int = 0
    entra_domains: int = 0
    entra_inboxes_actual: int = 0

    # Google calculations
    google_orders: int = 0
    google_domains: int = 0
    google_inboxes_actual: int = 0

    # Totals
    total_orders: int = 0
    total_inboxes: int = 0
    total_domains: int = 0
    total_monthly_capacity: int = 0

    # Cost estimate
    estimated_monthly_cost: float = 0.0

    # Flags
    has_entra: bool = False
    has_google: bool = False
    is_mixed: bool = False


class CalculateOrdersResponse(BaseModel):
    """Response for order calculation."""
    client_id: UUID
    requested_target: InboxTargetRequest
    breakdown: OrderBreakdownResponse
    message: str


class GeneratedInboxName(BaseModel):
    """A generated inbox name."""
    first_name: str
    last_name: str
    email_prefix: str


class GenerateNamesResponse(BaseModel):
    """Response for name generation."""
    client_id: UUID
    names: list[GeneratedInboxName]
    count: int


class OrderResultResponse(BaseModel):
    """Result of a single order purchase."""
    success: bool
    order_type: str  # "entra" or "google"
    quantity: int
    inboxes_created: int = 0
    domains_created: list[str] = Field(default_factory=list)
    order_id: Optional[str] = None
    error: Optional[str] = None


class PurchaseJobResponse(BaseModel):
    """Response when initiating a purchase job."""
    job_id: str
    client_id: UUID
    status: OrderStatus
    message: str
    estimated_duration_seconds: int = Field(
        default=180,
        description="Estimated time for completion (HyperTide automation takes 2-5 minutes)"
    )


class PurchaseStatusResponse(BaseModel):
    """Response for purchase job status check."""
    job_id: str
    client_id: UUID
    status: OrderStatus

    # Progress
    current_step: Optional[str] = None
    orders_completed: int = 0
    orders_total: int = 0

    # Results (populated when completed)
    results: Optional[list[OrderResultResponse]] = None
    total_inboxes: int = 0
    total_monthly_capacity: int = 0

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Errors
    errors: list[str] = Field(default_factory=list)
    error_type: Optional[str] = Field(
        default=None,
        description="Failure category: payment, config, auth, timeout, system, stale"
    )


class PurchaseCompleteResponse(BaseModel):
    """Response for completed purchase."""
    job_id: str
    client_id: UUID
    success: bool

    # Results
    order_results: list[OrderResultResponse]
    total_orders: int
    successful_orders: int
    failed_orders: int
    total_inboxes: int
    total_monthly_capacity: int

    # Errors
    errors: list[str] = Field(default_factory=list)

    # Next steps
    next_steps: list[str] = Field(default_factory=list)


# =============================================================================
# V2 Models - Enhanced Flow with Domain Grouping
# =============================================================================

class OrderGroup(BaseModel):
    """
    A group of domains to be provisioned together as one Hypertide order.

    Hypertide requires fixed domain counts per order:
    - Entra: Exactly 2 domains per order
    - Google: Exactly 5 domains per order
    """
    order_type: InboxProviderType = Field(..., description="'entra' or 'google'")
    domain_ids: list[UUID] = Field(..., description="Domain IDs in this order group")
    domain_names: list[str] = Field(default_factory=list, description="Domain names (populated by API)")
    sender_name_id: str = Field(..., description="ID of sender name to use for this group")

    def validate_domain_count(self) -> tuple[bool, str]:
        """Validate that domain count matches Hypertide requirements."""
        expected = 2 if self.order_type == InboxProviderType.ENTRA else 5
        actual = len(self.domain_ids)
        if actual != expected:
            return False, f"{self.order_type.value} requires exactly {expected} domains, got {actual}"
        return True, "OK"


class ExecutePurchaseV2Request(BaseModel):
    """
    V2 request for executing inbox purchase with domain grouping.

    This enforces Hypertide's fixed domain requirements:
    - Each Entra order must have exactly 2 domains
    - Each Google order must have exactly 5 domains

    Prefixes are automatically converted to InboxConfigs:
    - Entra: Top 50 prefixes become InboxConfigs
    - Google: Top 3 prefixes become InboxConfigs
    """
    client_id: UUID
    client_name: str
    forwarding_domain: str = Field(..., description="Client's main domain for grouping")

    # Order groups - each group becomes one Hypertide order
    order_groups: list[OrderGroup] = Field(..., description="Domain groups, each becoming one order")

    # Override for young domains (< 30 days)
    override_age_check: bool = Field(default=False, description="Allow domains younger than 30 days")

    # EmailBison credentials (for connecting inboxes after purchase)
    bison_username: Optional[str] = None
    bison_password: Optional[str] = None
    bison_workspace: Optional[str] = None
    bison_url: str = Field(default="https://spellcast.hirecharm.com")
    bison_api_key: Optional[str] = Field(default=None, description="EmailBison API key for workspace fetch")

    # Payment
    use_saved_payment: bool = Field(default=True, description="Use saved Stripe payment method")


class ExecutePurchaseV2Summary(BaseModel):
    """Summary of what will be purchased."""
    total_orders: int
    entra_orders: int
    google_orders: int
    total_domains: int
    total_inboxes: int
    entra_inboxes: int
    google_inboxes: int
    estimated_monthly_cost: float
    domain_breakdown: list[dict] = Field(default_factory=list)
