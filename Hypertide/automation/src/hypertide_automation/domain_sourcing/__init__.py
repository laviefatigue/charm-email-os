"""
Domain Sourcing Module for Hypertide Automation.

This module handles the pre-purchase domain sourcing workflow:
1. AI-powered domain name generation based on client context
2. Multi-registrar availability and pricing search
3. Fuzzy matching for promotional domain deals
4. Human approval workflow
5. Integration with Hypertide BYOD (Bring Your Own Domain) purchasing

Workflow:
    Client Form → DB Record → AI Domain Generation → Registrar Search →
    Human Approval → Domain Purchase → Hypertide BYOD Purchase

Example:
    from hypertide_automation.domain_sourcing import (
        DomainRequest,
        DomainCandidate,
        generate_domain_candidates,
        search_registrars,
        approve_and_purchase,
    )

    # Create request from client data
    request = DomainRequest(
        client_name="Acme Corp",
        industry="SaaS",
        brand_keywords=["outreach", "connect", "grow"],
        required_domains=11,  # 5 Google + 6 Entra domains
    )

    # Generate AI-powered domain suggestions
    candidates = await generate_domain_candidates(request)

    # Search for availability and pricing
    results = await search_registrars(candidates, target_price=8.00)

    # After human approval, purchase domains
    purchased = await purchase_approved_domains(approved_list)
"""

from .models import (
    DomainRequest,
    DomainCandidate,
    RegistrarResult,
    DomainSearchResult,
    ApprovedDomain,
    PurchaseResult,
    RegistrarType,
    DomainStatus,
)

from .registrars import (
    Registrar,
    PorkbunRegistrar,
    DynadotRegistrar,
    RegistrarFactory,
)

from .generator import (
    generate_domain_candidates,
    DomainGeneratorConfig,
)

from .search import (
    search_registrars,
    fuzzy_search,
    generate_variations,
    SearchConfig,
)

from .workflow import (
    DomainSourcingWorkflow,
    approve_domains,
    purchase_approved_domains,
)

__all__ = [
    # Models
    "DomainRequest",
    "DomainCandidate",
    "RegistrarResult",
    "DomainSearchResult",
    "ApprovedDomain",
    "PurchaseResult",
    "RegistrarType",
    "DomainStatus",
    # Registrars
    "Registrar",
    "PorkbunRegistrar",
    "DynadotRegistrar",
    "RegistrarFactory",
    # Generator
    "generate_domain_candidates",
    "DomainGeneratorConfig",
    # Search
    "search_registrars",
    "fuzzy_search",
    "generate_variations",
    "SearchConfig",
    # Workflow
    "DomainSourcingWorkflow",
    "approve_domains",
    "purchase_approved_domains",
]
