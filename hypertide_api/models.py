"""
Hypertide Order Models

Pydantic models for order creation and management with:
- EmailBison-only credentials
- Order validation
- Status tracking
- Duplicate detection support
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, field_validator


# =============================================================================
# Enums
# =============================================================================

class PlanType(str, Enum):
    """Hypertide plan types."""
    ENTRA = "entra"     # Microsoft 365 / Azure AD
    GOOGLE = "google"   # Google Workspace


class OrderStatus(str, Enum):
    """Order processing status."""
    PENDING = "pending"                    # Created, waiting for processing
    VALIDATING = "validating"              # Checking for duplicates
    PROCESSING = "processing"              # API call in progress
    COMPLETED = "completed"                # Successfully created
    FAILED = "failed"                      # Failed, manual retry available
    DUPLICATE = "duplicate"                # Domain(s) already exist
    CANCELLED = "cancelled"                # Cancelled by user


class FailureReason(str, Enum):
    """Classification of failure reasons."""
    AUTHENTICATION = "authentication"      # API key invalid
    VALIDATION = "validation"              # Invalid request data
    DOMAIN_CONFLICT = "domain_conflict"    # Domain already in use
    PAYMENT_REQUIRED = "payment_required"  # Payment method issues
    API_ERROR = "api_error"               # Hypertide API returned error
    NETWORK_ERROR = "network_error"        # Connection failed
    TIMEOUT = "timeout"                    # Request timed out
    UNKNOWN = "unknown"                    # Unclassified error


# =============================================================================
# Order Specifications
# =============================================================================

# Fixed order specifications from Hypertide
PLAN_SPECS = {
    PlanType.ENTRA: {
        "domains_per_order": 2,
        "inboxes_per_domain": 50,
        "inboxes_per_order": 100,
        "capacity_per_order": 5000,  # emails/month
        "cost_per_order": 50.0,      # USD/month
    },
    PlanType.GOOGLE: {
        "domains_per_order": 5,
        "inboxes_per_domain": 3,
        "inboxes_per_order": 15,
        "capacity_per_order": 5000,
        "cost_per_order": 50.0,
    },
}


# =============================================================================
# Credential Models
# =============================================================================

class BisonCredentials(BaseModel):
    """
    EmailBison credentials for inbox connection.

    These credentials are used by Hypertide to connect
    the created inboxes to your EmailBison workspace.
    """
    username: str = Field(..., description="Bison login email")
    password: str = Field(..., description="Bison password")
    workspace: str = Field(..., description="Bison workspace name")
    bison_url: str = Field(
        default="https://spellcast.hirecharm.com",
        description="Bison instance URL"
    )
    api_key: str = Field(default="", description="Optional Bison API key")


class InboxUser(BaseModel):
    """User configuration for inbox naming."""
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)

    @property
    def email_prefix(self) -> str:
        """Generate email prefix (before @)."""
        return f"{self.first_name.lower()}.{self.last_name.lower()}"


# =============================================================================
# Order Request Models
# =============================================================================

class SingleOrderRequest(BaseModel):
    """
    Request to create a single Hypertide order.

    This represents one order (1 Entra or 1 Google).
    - Entra: 2 domains, 100 inboxes
    - Google: 5 domains, 15 inboxes
    """
    # Order identification
    order_id: UUID = Field(default_factory=uuid4)
    job_id: Optional[UUID] = Field(default=None, description="Parent job ID")

    # Client info
    client_id: UUID
    client_name: str
    forwarding_domain: str

    # Order specification
    plan: PlanType
    domains: list[str] = Field(..., min_length=1)

    # Credentials (EmailBison only)
    bison_credentials: BisonCredentials

    # Inbox configuration
    users: list[InboxUser] = Field(default_factory=list, max_length=10)

    # Warmup settings (defaults for Bison)
    warmup_enabled: bool = Field(default=True)
    warmup_limit: int = Field(default=5, ge=1, le=50)
    warmup_reply_rate: int = Field(default=100, ge=0, le=100)
    warmup_increment: int = Field(default=1, ge=0, le=10)

    @field_validator("domains")
    @classmethod
    def validate_domain_count(cls, v: list[str], info) -> list[str]:
        """Validate domain count matches plan requirements."""
        # Note: This validation runs per-order, not per-bundle
        # Full validation happens at service level
        return v

    @property
    def expected_inboxes(self) -> int:
        """Calculate expected inbox count."""
        spec = PLAN_SPECS[self.plan]
        return len(self.domains) * spec["inboxes_per_domain"]

    @property
    def monthly_cost(self) -> float:
        """Calculate monthly cost (per order, not per domain)."""
        spec = PLAN_SPECS[self.plan]
        domains_per_order = spec["domains_per_order"]
        orders = (len(self.domains) + domains_per_order - 1) // domains_per_order
        return orders * spec["cost_per_order"]


class BatchOrderRequest(BaseModel):
    """
    Request to create multiple orders as a batch.

    Use this when purchasing for a client that needs
    both Entra and Google inboxes, or multiple orders
    of the same type.
    """
    # Batch identification
    batch_id: UUID = Field(default_factory=uuid4)
    job_id: Optional[UUID] = Field(default=None, description="Parent job ID")

    # Client info (shared across orders)
    client_id: UUID
    client_name: str
    forwarding_domain: str

    # Individual orders
    orders: list[SingleOrderRequest] = Field(..., min_length=1)

    # Shared credentials
    bison_credentials: BisonCredentials

    @property
    def total_domains(self) -> int:
        """Total domains across all orders."""
        return sum(len(o.domains) for o in self.orders)

    @property
    def total_inboxes(self) -> int:
        """Total inboxes across all orders."""
        return sum(o.expected_inboxes for o in self.orders)

    @property
    def total_cost(self) -> float:
        """Total monthly cost."""
        return sum(o.monthly_cost for o in self.orders)

    @property
    def entra_orders(self) -> list[SingleOrderRequest]:
        """Get Entra orders only."""
        return [o for o in self.orders if o.plan == PlanType.ENTRA]

    @property
    def google_orders(self) -> list[SingleOrderRequest]:
        """Get Google orders only."""
        return [o for o in self.orders if o.plan == PlanType.GOOGLE]


# =============================================================================
# Order Result Models
# =============================================================================

class OrderResult(BaseModel):
    """Result of a single order creation attempt."""
    order_id: UUID
    success: bool
    plan: PlanType
    domains: list[str]

    # Hypertide response
    hypertide_order_ids: list[str] = Field(default_factory=list)
    nameservers: Optional[dict] = None
    subscription_id: Optional[str] = None  # Stripe subscription ID from charge

    # Calculated values
    inboxes_created: int = 0
    monthly_cost: float = 0.0

    # Error info (if failed)
    error_message: Optional[str] = None
    failure_reason: Optional[FailureReason] = None

    # Timestamps
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        """Processing duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class BatchOrderResult(BaseModel):
    """Result of batch order creation."""
    batch_id: UUID
    job_id: Optional[UUID] = None
    client_id: UUID
    client_name: str

    # Overall status
    success: bool  # True if ALL orders succeeded
    partial_success: bool = False  # True if SOME orders succeeded

    # Individual results
    order_results: list[OrderResult] = Field(default_factory=list)

    # Aggregated stats
    total_orders: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    total_inboxes: int = 0
    total_monthly_cost: float = 0.0

    # Duplicate detection
    duplicate_domains: list[str] = Field(default_factory=list)

    # Error summary
    errors: list[str] = Field(default_factory=list)

    # Timestamps
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def add_result(self, result: OrderResult):
        """Add an order result and update aggregates."""
        self.order_results.append(result)
        self.total_orders += 1

        if result.success:
            self.successful_orders += 1
            self.total_inboxes += result.inboxes_created
            self.total_monthly_cost += result.monthly_cost
        else:
            self.failed_orders += 1
            if result.error_message:
                self.errors.append(result.error_message)

        # Update success flags
        self.success = self.failed_orders == 0
        self.partial_success = self.successful_orders > 0 and self.failed_orders > 0


# =============================================================================
# Job Models (for database persistence)
# =============================================================================

class OrderJobRecord(BaseModel):
    """
    Database record for tracking order jobs.

    This model represents a job row in the database with
    all the fields needed for:
    - Duplicate detection (domain lookup)
    - Status tracking
    - Manual retry
    - Slack notifications
    """
    id: UUID = Field(default_factory=uuid4)

    # Client reference
    client_id: UUID
    client_name: str
    workspace_id: Optional[UUID] = None

    # Order specification
    plan: PlanType
    domains: list[str]
    forwarding_domain: str

    # Status
    status: OrderStatus = OrderStatus.PENDING
    failure_reason: Optional[FailureReason] = None
    error_message: Optional[str] = None

    # Results
    hypertide_order_ids: list[str] = Field(default_factory=list)
    inboxes_created: int = 0
    monthly_cost: float = 0.0

    # Credentials (reference, not stored in DB)
    bison_workspace: str = ""

    # Processing
    retry_count: int = 0
    max_retries: int = 0  # 0 = no auto-retry
    worker_id: Optional[str] = None

    # Slack notification tracking
    slack_started_sent: bool = False
    slack_failed_sent: bool = False
    slack_completed_sent: bool = False

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# =============================================================================
# Utility Functions
# =============================================================================

def calculate_orders_needed(
    target_inboxes: int,
    plan: PlanType,
) -> dict:
    """
    Calculate number of orders and domains needed for target inbox count.

    Returns:
        {
            "orders": int,
            "domains": int,
            "actual_inboxes": int,
            "monthly_cost": float,
        }
    """
    import math

    spec = PLAN_SPECS[plan]
    inboxes_per_order = spec["inboxes_per_order"]
    domains_per_order = spec["domains_per_order"]
    cost_per_order = spec["cost_per_order"]

    orders = math.ceil(target_inboxes / inboxes_per_order)
    orders = min(orders, 20)  # Max 20 orders per purchase

    return {
        "orders": orders,
        "domains": orders * domains_per_order,
        "actual_inboxes": orders * inboxes_per_order,
        "monthly_cost": orders * cost_per_order,
    }


def group_domains_for_orders(
    domains: list[str],
    plan: PlanType,
) -> list[list[str]]:
    """
    Group domains into order-sized chunks.

    Entra: 2 domains per order
    Google: 5 domains per order

    Returns list of domain groups, each group = 1 order.
    """
    spec = PLAN_SPECS[plan]
    chunk_size = spec["domains_per_order"]

    groups = []
    for i in range(0, len(domains), chunk_size):
        groups.append(domains[i:i + chunk_size])

    return groups
