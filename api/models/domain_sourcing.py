"""
Domain sourcing API models.

Pydantic models for domain generation and registrar search endpoints.
"""

from typing import Optional
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field
from uuid import UUID
import uuid


class TLDPreferenceRequest(BaseModel):
    """TLD preference input."""
    tld: str = Field(..., description="Top-level domain (e.g., 'com', 'io')")
    priority: int = Field(default=1, ge=1, le=10, description="Priority (1=highest)")
    max_price: float = Field(default=15.0, description="Max acceptable price")


class DomainGenerateRequest(BaseModel):
    """Request to generate AI domain suggestions."""
    client_id: UUID = Field(..., description="Client UUID")
    client_name: str = Field(..., description="Client/company name")
    industry: str = Field(..., description="Industry vertical")
    brand_keywords: list[str] = Field(default_factory=list, description="Brand keywords")
    target_audience: str = Field(default="", description="Target audience")
    avoid_words: list[str] = Field(default_factory=list, description="Words to avoid")

    # Domain requirements
    domains_needed: int = Field(default=6, ge=1, le=50, description="Number of domains needed")

    # TLD preferences
    preferred_tlds: list[TLDPreferenceRequest] = Field(
        default_factory=lambda: [
            TLDPreferenceRequest(tld="com", priority=1, max_price=12.0),
            TLDPreferenceRequest(tld="io", priority=2, max_price=35.0),
            TLDPreferenceRequest(tld="co", priority=3, max_price=25.0),
        ]
    )

    # AI provider
    ai_provider: str = Field(default="openai", description="AI provider (openai, anthropic, ollama)")
    ai_model: str = Field(default="gpt-4", description="AI model name")


class DomainCandidateResponse(BaseModel):
    """A generated domain candidate."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    domain_name: str = Field(..., description="Full domain (e.g., 'growth-acme.com')")
    base_name: str = Field(..., description="Domain without TLD")
    tld: str = Field(..., description="Top-level domain")
    rationale: str = Field(default="", description="Why this domain was suggested")
    legitimacy_score: float = Field(default=0.7, ge=0.0, le=1.0, description="Professionalism score")


class DomainGenerateResponse(BaseModel):
    """Response from domain generation."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: UUID
    candidates: list[DomainCandidateResponse]
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    provider_used: str
    model_used: str


class DomainSearchRequest(BaseModel):
    """Request to search registrars for domains."""
    candidates: list[DomainCandidateResponse] = Field(..., description="Domains to search")
    target_price: float = Field(default=8.0, description="Target price for 'deal' classification")
    max_price: float = Field(default=15.0, description="Maximum acceptable price")
    include_variations: bool = Field(default=True, description="Generate and search variations")


class RegistrarPriceResult(BaseModel):
    """Price result from a single registrar."""
    registrar: str = Field(..., description="Registrar name (porkbun, dynadot)")
    is_available: bool = Field(default=False)
    registration_price: float = Field(default=0.0)
    renewal_price: float = Field(default=0.0)
    is_promotional: bool = Field(default=False)
    regular_price: Optional[float] = None
    whois_privacy_included: bool = Field(default=False)
    error: Optional[str] = None


class DomainSearchResultResponse(BaseModel):
    """Search result for a single domain."""
    domain_name: str
    base_name: str
    tld: str
    legitimacy_score: float

    # Aggregated results
    is_available: bool = False
    best_price: Optional[float] = None
    best_registrar: Optional[str] = None
    is_deal: bool = False
    value_score: float = Field(default=0.0, description="Combined ranking score")

    # Per-registrar results
    registrar_results: list[RegistrarPriceResult] = Field(default_factory=list)


class DomainSearchResponse(BaseModel):
    """Response from domain search."""
    search_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    results: list[DomainSearchResultResponse]
    total_searched: int
    available_count: int
    deals_count: int
    under_target_count: int
    searched_at: datetime = Field(default_factory=datetime.utcnow)


class DomainApprovalRequest(BaseModel):
    """Request to approve domains for purchase."""
    client_id: UUID
    domains: list[dict] = Field(..., description="Domains to approve with registrar selection")
    # Each domain dict: {"domain_name": "...", "registrar": "porkbun", "price": 9.73}


class DomainPurchaseRequest(BaseModel):
    """Request to purchase approved domains."""
    client_id: UUID
    approved_domains: list[dict] = Field(..., description="Approved domains to purchase")
    nameservers: list[str] = Field(
        default_factory=lambda: [
            "ns1.hypertide.io",
            "ns2.hypertide.io",
        ],
        description="Nameservers to set after purchase"
    )


class DomainPurchaseResult(BaseModel):
    """Result of a single domain purchase."""
    domain_name: str
    registrar: str
    success: bool
    price: float
    order_id: Optional[str] = None
    error: Optional[str] = None


class DomainPurchaseResponse(BaseModel):
    """Response from domain purchase."""
    purchase_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_id: UUID
    results: list[DomainPurchaseResult]
    successful_count: int
    failed_count: int
    total_cost: float
    purchased_at: datetime = Field(default_factory=datetime.utcnow)


class ConfiguredRegistrarsResponse(BaseModel):
    """Response listing configured registrars."""
    registrars: list[str]
    message: str


class GenerateForClientRequest(BaseModel):
    """Request to generate domains for a client using their onboarding data."""
    count: int = Field(default=10, ge=1, le=50, description="Number of domains to generate")
    ai_provider: str = Field(default="openai", description="AI provider (openai, anthropic, ollama)")
    ai_model: str = Field(default="gpt-4", description="AI model name")
    preferred_tlds: list[TLDPreferenceRequest] = Field(
        default_factory=lambda: [
            TLDPreferenceRequest(tld="com", priority=1, max_price=12.0),
            TLDPreferenceRequest(tld="io", priority=2, max_price=35.0),
            TLDPreferenceRequest(tld="co", priority=3, max_price=25.0),
        ]
    )


class GeneratedDomainResult(BaseModel):
    """A domain that was generated and saved to DB."""
    id: UUID
    domain_name: str
    base_name: str
    tld: str
    rationale: str = ""
    legitimacy_score: float = 0.7


class GenerateForClientResponse(BaseModel):
    """Response from generating domains for a client."""
    client_id: UUID
    client_name: str
    industry: str
    generated_domains: list[GeneratedDomainResult]
    filtered_count: int = Field(description="Number of candidates filtered as duplicates")
    total_candidates: int = Field(description="Total candidates generated before filtering")
    provider_used: str
    model_used: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class DomainCandidateModel(BaseModel):
    """A domain candidate for approval workflow."""
    id: UUID
    domain_name: str
    base_name: str
    tld: str
    rationale: str = ""
    legitimacy_score: float = 0.75
    approval_status: str = "pending"
    created_at: Optional[str] = None
    reviewed_at: Optional[str] = None


class PendingCandidatesResponse(BaseModel):
    """Response from pending candidates endpoint."""
    client_id: UUID
    candidates: list[DomainCandidateModel]
    total_pending: int


class ApprovalResponse(BaseModel):
    """Response from approve/deny endpoints."""
    domain_id: UUID
    domain_name: str
    status: str = Field(..., description="New status: 'approved' or 'denied'")
    message: str
