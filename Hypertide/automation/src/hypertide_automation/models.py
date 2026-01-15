"""
Data models for Hypertide automation.

These models represent the input/output structures for automated purchasing.
Designed to integrate with your project record system.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class InboxType(str, Enum):
    """Inbox provider type."""
    ENTRA = "entra"      # Microsoft Enterprise (Azure AD)
    GOOGLE = "google"    # Google Workspace


class OrderType(str, Enum):
    """Hypertide order type."""
    HYPERTIDE_ENTRA = "hypertide_entra"
    HYPERTIDE_GOOGLE = "hypertide_google"


class SendingTool(str, Enum):
    """Email sequencer integration."""
    BISON = "Email Bison"          # Primary - EmailBison
    SMARTLEAD = "Smartlead.ai"     # Legacy
    INSTANTLY = "Instantly"         # Legacy


class DomainConfig(BaseModel):
    """
    Configuration for a single sending domain.

    Example:
        DomainConfig(
            name="outreach-acme",
            tld="com",
            use_hypertide_domain=True
        )
    """
    name: str = Field(..., description="Domain name without TLD (e.g., 'outreach-acme')")
    tld: str = Field(default="com", description="Top-level domain (com, io, co, etc.)")
    use_hypertide_domain: bool = Field(
        default=True,
        description="True = Hypertide provides domain, False = BYOD"
    )
    custom_domain: Optional[str] = Field(
        default=None,
        description="Full domain if BYOD (e.g., 'outreach.acme.com')"
    )

    @property
    def full_domain(self) -> str:
        """Get the full domain name."""
        if self.custom_domain:
            return self.custom_domain
        return f"{self.name}.{self.tld}"


class InboxConfig(BaseModel):
    """
    Configuration for inbox naming within a domain.

    Hypertide creates inboxes with pattern: {first}.{last}@{domain}

    Example:
        InboxConfig(first_name="alex", last_name="morgan")
        -> alex.morgan@outreach-acme.com
    """
    first_name: str = Field(..., description="First name for inbox")
    last_name: str = Field(..., description="Last name for inbox")

    @property
    def username(self) -> str:
        """Generate the username portion of the email."""
        return f"{self.first_name.lower()}.{self.last_name.lower()}"


class OrderRequest(BaseModel):
    """
    Complete order request for Hypertide purchase automation.

    This is the input structure your project record system would generate.

    Example:
        OrderRequest(
            client_name="Acme Corp",
            forwarding_domain="acme.com",
            order_type=OrderType.HYPERTIDE_ENTRA,
            quantity=2,  # 2 orders = 4 Entra domains, 10k emails/mo
            sending_tool=SendingTool.BISON,
            domains=[
                DomainConfig(name="outreach-acme", tld="com"),
                DomainConfig(name="connect-acme", tld="com"),
                DomainConfig(name="reach-acme", tld="io"),
                DomainConfig(name="hello-acme", tld="io"),
            ],
            inbox_names=[
                InboxConfig(first_name="alex", last_name="morgan"),
                InboxConfig(first_name="jordan", last_name="smith"),
                # ... more inbox configs
            ]
        )
    """
    # Client identification
    client_name: str = Field(..., description="Client/project name for reference")
    forwarding_domain: str = Field(..., description="Client's main domain (groups orders)")

    # Order specification
    order_type: OrderType = Field(default=OrderType.HYPERTIDE_ENTRA)
    quantity: int = Field(default=1, ge=1, le=20, description="Number of orders (1-20)")
    sending_tool: SendingTool = Field(default=SendingTool.BISON)

    # Domain configuration
    domains: list[DomainConfig] = Field(
        default_factory=list,
        description="Domain configurations (leave empty for Hypertide defaults)"
    )

    # Inbox naming (optional - Hypertide can auto-generate)
    inbox_names: list[InboxConfig] = Field(
        default_factory=list,
        description="Custom inbox names (leave empty for Hypertide defaults)"
    )

    # Payment
    use_saved_payment: bool = Field(
        default=True,
        description="Use saved payment method in Stripe"
    )

    @field_validator('quantity')
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v < 1 or v > 20:
            raise ValueError("Quantity must be between 1 and 20")
        return v

    @property
    def expected_domains(self) -> int:
        """Calculate expected number of domains based on order type and quantity."""
        if self.order_type == OrderType.HYPERTIDE_ENTRA:
            return self.quantity * 2  # 2 domains per Entra order
        else:
            return self.quantity * 5  # 5 domains per Google order

    @property
    def expected_inboxes(self) -> int:
        """Calculate expected total inboxes."""
        if self.order_type == OrderType.HYPERTIDE_ENTRA:
            return self.expected_domains * 50  # 50 inboxes per Entra domain
        else:
            return self.expected_domains * 3   # 3 inboxes per Google domain

    @property
    def expected_monthly_capacity(self) -> int:
        """Calculate expected monthly email capacity."""
        return self.quantity * 5000  # 5k emails per order


class OrderResult(BaseModel):
    """
    Result of a completed Hypertide purchase.

    This is returned after successful automation.
    """
    success: bool
    order_id: Optional[str] = None
    client_name: str
    forwarding_domain: str
    order_type: OrderType
    quantity: int
    domains_created: list[str] = Field(default_factory=list)
    total_inboxes: int = 0
    monthly_capacity: int = 0
    stripe_payment_id: Optional[str] = None
    error_message: Optional[str] = None
    screenshot_path: Optional[str] = None  # For debugging failed orders


class DomainStatus(str, Enum):
    """Domain health status in Hypertide."""
    ACTIVE = "active"
    TO_BE_CANCELLED = "to_be_cancelled"
    CANCELLED = "cancelled"


class ExistingDomain(BaseModel):
    """Represents an existing domain in Hypertide inventory."""
    domain: str
    inbox_type: InboxType
    status: DomainStatus
    inbox_count: int
    order_id: str
    forwarding_domain: str


# =============================================================================
# MIXED ORDER SUPPORT (Entra + Google in same client onboarding)
# =============================================================================

class InboxTarget(BaseModel):
    """
    Target inbox counts for a client (used to calculate optimal order quantities).

    Example:
        InboxTarget(entra_inboxes=500, google_inboxes=100)
        # System calculates: 5 Entra orders + 7 Google orders
    """
    entra_inboxes: int = Field(default=0, ge=0, description="Target Entra inbox count")
    google_inboxes: int = Field(default=0, ge=0, description="Target Google inbox count")

    @property
    def total_inboxes(self) -> int:
        """Total inboxes across both types."""
        return self.entra_inboxes + self.google_inboxes


class OrderBreakdown(BaseModel):
    """
    Calculated order quantities to meet inbox targets.

    Generated by calculate_optimal_orders() function.
    """
    # Entra calculations
    entra_orders: int = 0
    entra_domains: int = 0
    entra_inboxes_actual: int = 0

    # Google calculations
    google_orders: int = 0
    google_domains: int = 0
    google_inboxes_actual: int = 0

    # Totals
    total_inboxes: int = 0
    total_domains: int = 0
    total_monthly_capacity: int = 0

    # Cost estimates (orders × $50/mo base)
    estimated_monthly_cost: float = 0.0

    @property
    def has_entra(self) -> bool:
        return self.entra_orders > 0

    @property
    def has_google(self) -> bool:
        return self.google_orders > 0

    @property
    def is_mixed(self) -> bool:
        """True if order contains both Entra and Google."""
        return self.has_entra and self.has_google


class BisonCredentials(BaseModel):
    """
    EmailBison credentials for inbox connection.

    Shared across all orders in a bundle for the same client.
    """
    username: str = Field(..., description="Bison login email")
    password: str = Field(..., description="Bison password")
    workspace: str = Field(..., description="Bison workspace name")
    bison_url: str = Field(
        default="https://send.hirecharm.com",
        description="Bison instance URL"
    )


class MixedOrderRequest(BaseModel):
    """
    High-level order request for mixed Entra + Google inboxes.

    This is the primary input format from your project record system.
    The automation will calculate optimal order quantities and execute
    multiple purchase flows as needed.

    Example:
        MixedOrderRequest(
            client_name="Acme Corp",
            forwarding_domain="acme.com",
            inbox_target=InboxTarget(entra_inboxes=500, google_inboxes=100),
            bison_credentials=BisonCredentials(
                username="user@email.com",
                password="secret",
                workspace="Acme Workspace",
                bison_url="https://send.hirecharm.com"
            ),
            users=[
                InboxConfig(first_name="alex", last_name="morgan"),
                InboxConfig(first_name="jordan", last_name="smith"),
            ]
        )
    """
    # Client identification
    client_name: str = Field(..., description="Client/project name")
    forwarding_domain: str = Field(..., description="Client's main domain")

    # Target specification (system calculates orders)
    inbox_target: InboxTarget

    # Shared configuration
    bison_credentials: BisonCredentials
    users: list[InboxConfig] = Field(
        default_factory=list,
        description="User configs for inbox naming (max 10)"
    )

    # Domain configuration (optional - Hypertide can auto-generate)
    entra_domains: list[DomainConfig] = Field(
        default_factory=list,
        description="Custom Entra domain names"
    )
    google_domains: list[DomainConfig] = Field(
        default_factory=list,
        description="Custom Google domain names"
    )

    # Payment
    use_saved_payment: bool = Field(default=True)

    @field_validator('users')
    @classmethod
    def validate_users(cls, v: list[InboxConfig]) -> list[InboxConfig]:
        if len(v) > 10:
            raise ValueError("Maximum 10 users allowed per order")
        return v


class OrderBundle(BaseModel):
    """
    A bundle of OrderRequests generated from a MixedOrderRequest.

    Created by create_order_bundle() function.
    Contains separate OrderRequests for Entra and Google purchases.
    """
    client_name: str
    forwarding_domain: str

    # Calculated breakdown
    breakdown: OrderBreakdown

    # Individual orders to execute (1-2 orders)
    orders: list[OrderRequest] = Field(default_factory=list)

    # Shared config reference
    bison_credentials: BisonCredentials
    users: list[InboxConfig] = Field(default_factory=list)

    @property
    def order_count(self) -> int:
        return len(self.orders)

    @property
    def requires_multiple_purchases(self) -> bool:
        """True if bundle needs >1 purchase flow (mixed order)."""
        return self.order_count > 1


class BundleResult(BaseModel):
    """
    Result of executing an OrderBundle (multiple purchases).
    """
    success: bool
    client_name: str
    forwarding_domain: str

    # Individual order results
    order_results: list[OrderResult] = Field(default_factory=list)

    # Aggregated totals
    total_orders: int = 0
    successful_orders: int = 0
    failed_orders: int = 0
    total_inboxes: int = 0
    total_monthly_capacity: int = 0

    # Errors (if any)
    errors: list[str] = Field(default_factory=list)


# =============================================================================
# ORDER CALCULATION UTILITIES
# =============================================================================

def calculate_optimal_orders(target: InboxTarget) -> OrderBreakdown:
    """
    Calculate the optimal number of Hypertide orders to meet inbox targets.

    Hypertide order specifications:
    - Entra: 2 domains/order × 50 inboxes/domain = 100 inboxes/order
    - Google: 5 domains/order × 3 inboxes/domain = 15 inboxes/order

    Args:
        target: Target inbox counts for Entra and Google

    Returns:
        OrderBreakdown with calculated quantities

    Example:
        >>> target = InboxTarget(entra_inboxes=500, google_inboxes=100)
        >>> breakdown = calculate_optimal_orders(target)
        >>> print(f"Entra: {breakdown.entra_orders} orders = {breakdown.entra_inboxes_actual} inboxes")
        Entra: 5 orders = 500 inboxes
        >>> print(f"Google: {breakdown.google_orders} orders = {breakdown.google_inboxes_actual} inboxes")
        Google: 7 orders = 105 inboxes
    """
    import math

    # Entra: 100 inboxes per order (2 domains × 50 inboxes)
    ENTRA_INBOXES_PER_ORDER = 100
    ENTRA_DOMAINS_PER_ORDER = 2

    # Google: 15 inboxes per order (5 domains × 3 inboxes)
    GOOGLE_INBOXES_PER_ORDER = 15
    GOOGLE_DOMAINS_PER_ORDER = 5

    # Monthly capacity per order (both types)
    CAPACITY_PER_ORDER = 5000

    # Base cost per order
    COST_PER_ORDER = 50.0

    # Calculate Entra orders (round up to meet target)
    entra_orders = 0
    entra_domains = 0
    entra_inboxes = 0

    if target.entra_inboxes > 0:
        entra_orders = math.ceil(target.entra_inboxes / ENTRA_INBOXES_PER_ORDER)
        entra_orders = min(entra_orders, 20)  # Max 20 orders per purchase
        entra_domains = entra_orders * ENTRA_DOMAINS_PER_ORDER
        entra_inboxes = entra_orders * ENTRA_INBOXES_PER_ORDER

    # Calculate Google orders (round up to meet target)
    google_orders = 0
    google_domains = 0
    google_inboxes = 0

    if target.google_inboxes > 0:
        google_orders = math.ceil(target.google_inboxes / GOOGLE_INBOXES_PER_ORDER)
        google_orders = min(google_orders, 20)  # Max 20 orders per purchase
        google_domains = google_orders * GOOGLE_DOMAINS_PER_ORDER
        google_inboxes = google_orders * GOOGLE_INBOXES_PER_ORDER

    # Calculate totals
    total_orders = entra_orders + google_orders
    total_domains = entra_domains + google_domains
    total_inboxes = entra_inboxes + google_inboxes
    total_capacity = total_orders * CAPACITY_PER_ORDER
    estimated_cost = total_orders * COST_PER_ORDER

    return OrderBreakdown(
        entra_orders=entra_orders,
        entra_domains=entra_domains,
        entra_inboxes_actual=entra_inboxes,
        google_orders=google_orders,
        google_domains=google_domains,
        google_inboxes_actual=google_inboxes,
        total_inboxes=total_inboxes,
        total_domains=total_domains,
        total_monthly_capacity=total_capacity,
        estimated_monthly_cost=estimated_cost,
    )


def create_order_bundle(request: MixedOrderRequest) -> OrderBundle:
    """
    Convert a MixedOrderRequest into an executable OrderBundle.

    This function:
    1. Calculates optimal order quantities
    2. Creates separate OrderRequest objects for Entra and Google
    3. Assigns domains to each order type
    4. Returns a bundle ready for sequential execution

    Args:
        request: High-level mixed order request

    Returns:
        OrderBundle with individual OrderRequests

    Example:
        >>> mixed = MixedOrderRequest(
        ...     client_name="Acme Corp",
        ...     forwarding_domain="acme.com",
        ...     inbox_target=InboxTarget(entra_inboxes=200, google_inboxes=45),
        ...     bison_credentials=BisonCredentials(...)
        ... )
        >>> bundle = create_order_bundle(mixed)
        >>> print(f"Orders to execute: {bundle.order_count}")
        Orders to execute: 2
        >>> for order in bundle.orders:
        ...     print(f"  {order.order_type.value}: {order.quantity} orders")
        hypertide_entra: 2 orders
        hypertide_google: 3 orders
    """
    # Calculate optimal orders
    breakdown = calculate_optimal_orders(request.inbox_target)

    orders = []

    # Create Entra order if needed
    if breakdown.has_entra:
        entra_order = OrderRequest(
            client_name=request.client_name,
            forwarding_domain=request.forwarding_domain,
            order_type=OrderType.HYPERTIDE_ENTRA,
            quantity=breakdown.entra_orders,
            sending_tool=SendingTool.BISON,
            domains=request.entra_domains,
            inbox_names=request.users,
            use_saved_payment=request.use_saved_payment,
        )
        orders.append(entra_order)

    # Create Google order if needed
    if breakdown.has_google:
        google_order = OrderRequest(
            client_name=request.client_name,
            forwarding_domain=request.forwarding_domain,
            order_type=OrderType.HYPERTIDE_GOOGLE,
            quantity=breakdown.google_orders,
            sending_tool=SendingTool.BISON,
            domains=request.google_domains,
            inbox_names=request.users,
            use_saved_payment=request.use_saved_payment,
        )
        orders.append(google_order)

    return OrderBundle(
        client_name=request.client_name,
        forwarding_domain=request.forwarding_domain,
        breakdown=breakdown,
        orders=orders,
        bison_credentials=request.bison_credentials,
        users=request.users,
    )
