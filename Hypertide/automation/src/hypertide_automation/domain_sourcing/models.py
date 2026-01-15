"""
Data models for domain sourcing workflow.

These models track the entire lifecycle of domain sourcing:
- Request creation from client onboarding
- AI-generated domain candidates
- Registrar search results
- Approval tracking
- Purchase confirmation
"""

from enum import Enum
from typing import Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator
import uuid


class RegistrarType(str, Enum):
    """Supported domain registrars."""
    PORKBUN = "porkbun"
    DYNADOT = "dynadot"
    NAMECHEAP = "namecheap"  # Future support
    CLOUDFLARE = "cloudflare"  # Future support


class DomainStatus(str, Enum):
    """Domain lifecycle status in sourcing workflow."""
    GENERATED = "generated"  # AI-generated, not yet searched
    SEARCHING = "searching"  # Currently checking registrars
    AVAILABLE = "available"  # Available for purchase
    UNAVAILABLE = "unavailable"  # Already registered
    PENDING_APPROVAL = "pending_approval"  # Waiting for human approval
    APPROVED = "approved"  # Approved for purchase
    REJECTED = "rejected"  # Rejected by human
    PURCHASING = "purchasing"  # Purchase in progress
    PURCHASED = "purchased"  # Successfully purchased
    FAILED = "failed"  # Purchase failed


class TLDPreference(BaseModel):
    """TLD preference with priority weighting."""
    tld: str = Field(..., description="Top-level domain (e.g., 'com', 'io')")
    priority: int = Field(default=1, ge=1, le=10, description="Priority (1=highest)")
    max_price: Decimal = Field(default=Decimal("15.00"), description="Max acceptable price")


class DomainRequest(BaseModel):
    """
    Domain sourcing request - created when a client is onboarded.

    This is the primary input from the client onboarding form.
    Used to generate AI domain suggestions.

    Example:
        DomainRequest(
            client_name="Acme SaaS",
            industry="B2B Software",
            brand_keywords=["outreach", "connect", "growth"],
            target_audience="Enterprise Sales Teams",
            required_entra_domains=6,
            required_google_domains=5,
        )
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Client context for AI domain generation
    client_name: str = Field(..., description="Client/company name")
    industry: str = Field(..., description="Industry vertical (e.g., 'SaaS', 'Healthcare')")
    brand_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords reflecting brand identity"
    )
    target_audience: str = Field(
        default="",
        description="Who the client sells to (helps AI understand context)"
    )
    avoid_words: list[str] = Field(
        default_factory=list,
        description="Words to avoid in domain names"
    )

    # Domain requirements
    required_entra_domains: int = Field(
        default=0, ge=0,
        description="Number of domains needed for Microsoft Entra"
    )
    required_google_domains: int = Field(
        default=0, ge=0,
        description="Number of domains needed for Google Workspace"
    )

    # TLD preferences
    preferred_tlds: list[TLDPreference] = Field(
        default_factory=lambda: [
            TLDPreference(tld="com", priority=1, max_price=Decimal("12.00")),
            TLDPreference(tld="io", priority=2, max_price=Decimal("35.00")),
            TLDPreference(tld="co", priority=3, max_price=Decimal("25.00")),
            TLDPreference(tld="ai", priority=4, max_price=Decimal("50.00")),
        ]
    )

    # Budget constraints
    max_price_per_domain: Decimal = Field(
        default=Decimal("15.00"),
        description="Maximum price per domain (prefer <$8)"
    )
    target_price_per_domain: Decimal = Field(
        default=Decimal("8.00"),
        description="Target price - look for deals at or below this"
    )

    # Workflow tracking
    status: str = Field(default="pending_generation")

    @property
    def total_domains_needed(self) -> int:
        """Total domains required across both providers."""
        return self.required_entra_domains + self.required_google_domains

    @property
    def generation_count(self) -> int:
        """How many domain names to generate (3x buffer for availability)."""
        return self.total_domains_needed * 3

    @field_validator('brand_keywords', mode='before')
    @classmethod
    def lowercase_keywords(cls, v):
        if isinstance(v, list):
            return [kw.lower().strip() for kw in v if kw.strip()]
        return v


class DomainCandidate(BaseModel):
    """
    A generated domain name candidate.

    Created by the AI domain generator, then enriched with
    registrar search results.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str = Field(..., description="Parent DomainRequest ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Domain details
    domain_name: str = Field(..., description="Full domain name (e.g., 'outreach-acme.com')")
    base_name: str = Field(..., description="Domain without TLD (e.g., 'outreach-acme')")
    tld: str = Field(..., description="Top-level domain (e.g., 'com')")

    # AI generation metadata
    generation_rationale: str = Field(
        default="",
        description="Why the AI suggested this domain"
    )
    legitimacy_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="AI-assessed professionalism score (0-1)"
    )

    # Status tracking
    status: DomainStatus = Field(default=DomainStatus.GENERATED)

    # Registrar results (populated after search)
    registrar_results: list["RegistrarResult"] = Field(default_factory=list)

    @property
    def best_price(self) -> Optional[Decimal]:
        """Get the lowest available price across registrars."""
        available = [r for r in self.registrar_results if r.is_available]
        if not available:
            return None
        return min(r.registration_price for r in available)

    @property
    def best_registrar(self) -> Optional[RegistrarType]:
        """Get the registrar with the best price."""
        available = [r for r in self.registrar_results if r.is_available]
        if not available:
            return None
        best = min(available, key=lambda r: r.registration_price)
        return best.registrar

    @property
    def is_available(self) -> bool:
        """Check if domain is available on any registrar."""
        return any(r.is_available for r in self.registrar_results)

    @property
    def is_deal(self) -> bool:
        """Check if domain has a promotional/sale price."""
        return any(r.is_promotional for r in self.registrar_results if r.is_available)


class RegistrarResult(BaseModel):
    """
    Search result from a single registrar.

    Contains availability, pricing, and promotional info.
    """
    registrar: RegistrarType
    checked_at: datetime = Field(default_factory=datetime.utcnow)

    # Availability
    is_available: bool = False

    # Pricing (when available)
    registration_price: Decimal = Field(default=Decimal("0.00"))
    renewal_price: Decimal = Field(default=Decimal("0.00"))

    # Promotional pricing
    is_promotional: bool = Field(
        default=False,
        description="True if current price is a sale/promo"
    )
    regular_price: Optional[Decimal] = Field(
        default=None,
        description="Regular price (if promotional)"
    )
    promo_expires: Optional[datetime] = Field(
        default=None,
        description="When the promotional price expires"
    )

    # Additional info
    whois_privacy_included: bool = False
    transfer_lock_days: int = 60

    # Error handling
    error: Optional[str] = None

    @property
    def savings(self) -> Decimal:
        """Calculate savings if promotional."""
        if self.is_promotional and self.regular_price:
            return self.regular_price - self.registration_price
        return Decimal("0.00")


class DomainSearchResult(BaseModel):
    """
    Aggregated search results for a domain across all registrars.

    This is the primary result structure returned by search_registrars().
    """
    candidate: DomainCandidate
    search_completed_at: datetime = Field(default_factory=datetime.utcnow)

    # Aggregated status
    is_available: bool = False
    best_price: Optional[Decimal] = None
    best_registrar: Optional[RegistrarType] = None
    is_deal: bool = False

    # All registrar results
    results: list[RegistrarResult] = Field(default_factory=list)

    # Scoring for prioritization
    value_score: float = Field(
        default=0.0,
        description="Combined score based on price, legitimacy, and availability"
    )

    @classmethod
    def from_candidate(cls, candidate: DomainCandidate) -> "DomainSearchResult":
        """Create search result from a populated candidate."""
        return cls(
            candidate=candidate,
            is_available=candidate.is_available,
            best_price=candidate.best_price,
            best_registrar=candidate.best_registrar,
            is_deal=candidate.is_deal,
            results=candidate.registrar_results,
        )


class ApprovedDomain(BaseModel):
    """
    A domain that has been approved for purchase by a human.

    This is the handoff structure between approval and purchase.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    approved_at: datetime = Field(default_factory=datetime.utcnow)
    approved_by: str = Field(default="", description="Approver identifier")

    # Domain info
    domain_name: str
    tld: str

    # Purchase details
    registrar: RegistrarType
    price: Decimal

    # Source tracking
    candidate_id: str
    request_id: str

    # Assignment (which provider pool)
    assigned_to: str = Field(
        default="entra",
        description="'entra' or 'google' - which inbox type this domain is for"
    )


class PurchaseResult(BaseModel):
    """
    Result of a domain purchase attempt.
    """
    approved_domain: ApprovedDomain
    purchased_at: datetime = Field(default_factory=datetime.utcnow)

    # Purchase status
    success: bool = False

    # Registrar response
    registrar_order_id: Optional[str] = None
    actual_price: Decimal = Field(default=Decimal("0.00"))

    # DNS configuration
    nameservers_set: bool = False
    nameservers: list[str] = Field(default_factory=list)

    # Errors
    error: Optional[str] = None

    @property
    def domain_name(self) -> str:
        return self.approved_domain.domain_name


class DomainSourcingSession(BaseModel):
    """
    Complete session tracking for a domain sourcing workflow.

    Aggregates all stages from request to purchase.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Request
    request: DomainRequest

    # Generated candidates
    candidates: list[DomainCandidate] = Field(default_factory=list)

    # Search results (sorted by value score)
    search_results: list[DomainSearchResult] = Field(default_factory=list)

    # Approved for purchase
    approved: list[ApprovedDomain] = Field(default_factory=list)

    # Purchase results
    purchases: list[PurchaseResult] = Field(default_factory=list)

    # Session status
    status: str = Field(default="created")
    completed_at: Optional[datetime] = None

    @property
    def successful_purchases(self) -> list[PurchaseResult]:
        """Get successfully purchased domains."""
        return [p for p in self.purchases if p.success]

    @property
    def domains_still_needed(self) -> int:
        """How many more domains need to be purchased."""
        purchased = len(self.successful_purchases)
        return max(0, self.request.total_domains_needed - purchased)

    @property
    def is_complete(self) -> bool:
        """Check if enough domains have been purchased."""
        return self.domains_still_needed == 0
