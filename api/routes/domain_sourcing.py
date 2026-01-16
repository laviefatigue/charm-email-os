"""
Domain Sourcing Routes - AI domain generation and registrar search.

Integrates with the HyperTide automation module for:
- AI-powered domain name generation
- Multi-registrar availability and pricing search
- Domain purchase orchestration
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
from uuid import UUID
from database import fetch_one, fetch_all, execute
import logging
import sys
from pathlib import Path
from decimal import Decimal

# Add HyperTide automation to path
hypertide_path = Path(__file__).parent.parent.parent / "Hypertide" / "automation" / "src"
if str(hypertide_path) not in sys.path:
    sys.path.insert(0, str(hypertide_path))

from models.domain_sourcing import (
    DomainGenerateRequest,
    DomainGenerateResponse,
    DomainCandidateResponse,
    DomainSearchRequest,
    DomainSearchResponse,
    DomainSearchResultResponse,
    RegistrarPriceResult,
    DomainPurchaseRequest,
    DomainPurchaseResponse,
    DomainPurchaseResult,
    ConfiguredRegistrarsResponse,
    GenerateForClientRequest,
    GenerateForClientResponse,
    GeneratedDomainResult,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _import_hypertide_modules():
    """Import HyperTide modules with error handling."""
    try:
        from hypertide_automation.domain_sourcing.generator import (
            generate_domain_candidates,
            generate_fallback_candidates,
            DomainGeneratorConfig,
        )
        from hypertide_automation.domain_sourcing.search import (
            search_registrars,
            SearchConfig,
        )
        from hypertide_automation.domain_sourcing.registrars import (
            RegistrarFactory,
            PorkbunRegistrar,
            DynadotRegistrar,
        )
        from hypertide_automation.domain_sourcing.models import (
            DomainRequest,
            DomainCandidate,
            TLDPreference,
            DomainStatus,
        )
        return {
            "generate_domain_candidates": generate_domain_candidates,
            "generate_fallback_candidates": generate_fallback_candidates,
            "DomainGeneratorConfig": DomainGeneratorConfig,
            "search_registrars": search_registrars,
            "SearchConfig": SearchConfig,
            "RegistrarFactory": RegistrarFactory,
            "DomainRequest": DomainRequest,
            "DomainCandidate": DomainCandidate,
            "TLDPreference": TLDPreference,
            "DomainStatus": DomainStatus,
        }
    except ImportError as e:
        logger.warning(f"HyperTide modules not available: {e}")
        return None


@router.get("/registrars", response_model=ConfiguredRegistrarsResponse)
async def get_configured_registrars():
    """Get list of configured registrars."""
    ht = _import_hypertide_modules()
    if not ht:
        return ConfiguredRegistrarsResponse(
            registrars=[],
            message="HyperTide automation module not available"
        )

    try:
        configured = ht["RegistrarFactory"].get_configured_registrars()
        return ConfiguredRegistrarsResponse(
            registrars=[r.value for r in configured],
            message=f"{len(configured)} registrar(s) configured"
        )
    except Exception as e:
        logger.error(f"Error getting configured registrars: {e}")
        return ConfiguredRegistrarsResponse(
            registrars=[],
            message=f"Error: {str(e)}"
        )


@router.post("/generate", response_model=DomainGenerateResponse)
async def generate_domains(request: DomainGenerateRequest):
    """
    Generate AI-powered domain name suggestions.

    Uses OpenAI, Anthropic, or Ollama to generate professional domain names
    based on client context (industry, brand keywords, audience).
    """
    ht = _import_hypertide_modules()
    if not ht:
        raise HTTPException(
            status_code=503,
            detail="HyperTide automation module not available"
        )

    try:
        # Build domain request for HyperTide
        tld_prefs = [
            ht["TLDPreference"](tld=p.tld, priority=p.priority, max_price=Decimal(str(p.max_price)))
            for p in request.preferred_tlds
        ]

        domain_request = ht["DomainRequest"](
            client_name=request.client_name,
            industry=request.industry,
            brand_keywords=request.brand_keywords,
            target_audience=request.target_audience,
            avoid_words=request.avoid_words,
            required_entra_domains=request.domains_needed,
            required_google_domains=0,
            preferred_tlds=tld_prefs,
        )

        # Configure AI generator
        config = ht["DomainGeneratorConfig"](
            provider=request.ai_provider,
            model=request.ai_model,
        )

        # Generate candidates
        try:
            candidates = await ht["generate_domain_candidates"](domain_request, config)
        except Exception as e:
            logger.warning(f"AI generation failed, using fallback: {e}")
            candidates = ht["generate_fallback_candidates"](domain_request)

        # Convert to response format
        candidate_responses = [
            DomainCandidateResponse(
                id=c.id,
                domain_name=c.domain_name,
                base_name=c.base_name,
                tld=c.tld,
                rationale=c.generation_rationale,
                legitimacy_score=c.legitimacy_score,
            )
            for c in candidates
        ]

        return DomainGenerateResponse(
            client_id=request.client_id,
            candidates=candidate_responses,
            provider_used=request.ai_provider,
            model_used=request.ai_model,
        )

    except Exception as e:
        logger.error(f"Domain generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=DomainSearchResponse)
async def search_domains(request: DomainSearchRequest):
    """
    Search registrars for domain availability and pricing.

    Searches Porkbun and Dynadot (based on configured credentials)
    and returns ranked results by value score.
    """
    ht = _import_hypertide_modules()
    if not ht:
        raise HTTPException(
            status_code=503,
            detail="HyperTide automation module not available"
        )

    try:
        # Convert request candidates to HyperTide format
        candidates = [
            ht["DomainCandidate"](
                request_id="api-search",
                domain_name=c.domain_name,
                base_name=c.base_name,
                tld=c.tld,
                generation_rationale=c.rationale,
                legitimacy_score=c.legitimacy_score,
                status=ht["DomainStatus"].GENERATED,
            )
            for c in request.candidates
        ]

        # Configure search
        config = ht["SearchConfig"](
            target_price=Decimal(str(request.target_price)),
            max_price=Decimal(str(request.max_price)),
            include_variations=request.include_variations,
        )

        # Create registrars
        registrars = ht["RegistrarFactory"].create_all()
        if not registrars:
            raise HTTPException(
                status_code=503,
                detail="No registrars configured. Set PORKBUN_API_KEY/SECRET or DYNADOT_API_KEY"
            )

        # Run search
        results = await ht["search_registrars"](candidates, config, registrars)

        # Convert to response format
        response_results = []
        for r in results:
            registrar_results = [
                RegistrarPriceResult(
                    registrar=rr.registrar.value,
                    is_available=rr.is_available,
                    registration_price=float(rr.registration_price),
                    renewal_price=float(rr.renewal_price),
                    is_promotional=rr.is_promotional,
                    regular_price=float(rr.regular_price) if rr.regular_price else None,
                    whois_privacy_included=rr.whois_privacy_included,
                    error=rr.error,
                )
                for rr in r.results
            ]

            response_results.append(DomainSearchResultResponse(
                domain_name=r.candidate.domain_name,
                base_name=r.candidate.base_name,
                tld=r.candidate.tld,
                legitimacy_score=r.candidate.legitimacy_score,
                is_available=r.is_available,
                best_price=float(r.best_price) if r.best_price else None,
                best_registrar=r.best_registrar.value if r.best_registrar else None,
                is_deal=r.is_deal,
                value_score=r.value_score,
                registrar_results=registrar_results,
            ))

        # Calculate counts
        available = [r for r in response_results if r.is_available]
        deals = [r for r in available if r.is_deal]
        under_target = [r for r in available if r.best_price and r.best_price <= request.target_price]

        return DomainSearchResponse(
            results=response_results,
            total_searched=len(response_results),
            available_count=len(available),
            deals_count=len(deals),
            under_target_count=len(under_target),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Domain search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purchase", response_model=DomainPurchaseResponse)
async def purchase_domains(request: DomainPurchaseRequest):
    """
    Purchase approved domains from registrars.

    Executes purchases on Porkbun and/or Dynadot based on the
    registrar selection for each domain. Sets nameservers after purchase.
    Creates domain records in the database upon successful purchase.
    """
    ht = _import_hypertide_modules()
    if not ht:
        raise HTTPException(
            status_code=503,
            detail="HyperTide automation module not available"
        )

    # Get workspace_id from client
    client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", UUID(request.client_id))
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    workspace_id = client["workspace_id"]
    results = []
    total_cost = 0.0
    created_domain_ids = []

    for domain_data in request.approved_domains:
        domain_name = domain_data.get("domain_name")
        registrar_name = domain_data.get("registrar", "porkbun")
        expected_price = domain_data.get("price", 0.0)

        try:
            # Get registrar type
            from hypertide_automation.domain_sourcing.models import RegistrarType
            registrar_type = RegistrarType(registrar_name)

            # Create registrar instance
            registrar = ht["RegistrarFactory"].create(registrar_type)

            # Execute purchase
            async with registrar:
                purchase_result = await registrar.purchase(
                    domain_name,
                    years=1,
                    nameservers=request.nameservers,
                )

            if purchase_result.get("success"):
                # Create domain record in database
                try:
                    existing = await fetch_one(
                        "SELECT id FROM domains WHERE workspace_id = $1 AND domain_name = $2",
                        workspace_id, domain_name
                    )
                    if existing:
                        domain_id = existing["id"]
                        logger.info(f"Domain {domain_name} already exists with id {domain_id}")
                    else:
                        new_domain = await fetch_one(
                            "INSERT INTO domains (workspace_id, domain_name) VALUES ($1, $2) RETURNING id",
                            workspace_id, domain_name
                        )
                        domain_id = new_domain["id"]
                        logger.info(f"Created domain record for {domain_name} with id {domain_id}")
                    created_domain_ids.append(str(domain_id))
                except Exception as db_error:
                    logger.error(f"Failed to create domain record for {domain_name}: {db_error}")

                results.append(DomainPurchaseResult(
                    domain_name=domain_name,
                    registrar=registrar_name,
                    success=True,
                    price=expected_price,
                    order_id=purchase_result.get("order_id"),
                ))
                total_cost += expected_price
            else:
                results.append(DomainPurchaseResult(
                    domain_name=domain_name,
                    registrar=registrar_name,
                    success=False,
                    price=0.0,
                    error=purchase_result.get("error", "Unknown error"),
                ))

        except Exception as e:
            logger.error(f"Failed to purchase {domain_name}: {e}")
            results.append(DomainPurchaseResult(
                domain_name=domain_name,
                registrar=registrar_name,
                success=False,
                price=0.0,
                error=str(e),
            ))

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    logger.info(f"Domain purchase complete: {len(successful)} successful, {len(failed)} failed, {len(created_domain_ids)} DB records created")

    return DomainPurchaseResponse(
        client_id=request.client_id,
        results=results,
        successful_count=len(successful),
        failed_count=len(failed),
        total_cost=total_cost,
    )


@router.post("/generate-fallback", response_model=DomainGenerateResponse)
async def generate_domains_fallback(request: DomainGenerateRequest):
    """
    Generate domain suggestions without AI (pattern-based).

    Use this endpoint when AI providers are unavailable or
    for faster, deterministic results.
    """
    ht = _import_hypertide_modules()
    if not ht:
        raise HTTPException(
            status_code=503,
            detail="HyperTide automation module not available"
        )

    try:
        # Build domain request
        tld_prefs = [
            ht["TLDPreference"](tld=p.tld, priority=p.priority, max_price=Decimal(str(p.max_price)))
            for p in request.preferred_tlds
        ]

        domain_request = ht["DomainRequest"](
            client_name=request.client_name,
            industry=request.industry,
            brand_keywords=request.brand_keywords,
            target_audience=request.target_audience,
            avoid_words=request.avoid_words,
            required_entra_domains=request.domains_needed,
            required_google_domains=0,
            preferred_tlds=tld_prefs,
        )

        # Generate without AI
        candidates = ht["generate_fallback_candidates"](domain_request)

        # Convert to response format
        candidate_responses = [
            DomainCandidateResponse(
                id=c.id,
                domain_name=c.domain_name,
                base_name=c.base_name,
                tld=c.tld,
                rationale=c.generation_rationale,
                legitimacy_score=c.legitimacy_score,
            )
            for c in candidates
        ]

        return DomainGenerateResponse(
            client_id=request.client_id,
            candidates=candidate_responses,
            provider_used="fallback",
            model_used="pattern-based",
        )

    except Exception as e:
        logger.error(f"Fallback generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-for-client/{client_id}", response_model=GenerateForClientResponse)
async def generate_domains_for_client(client_id: UUID, request: GenerateForClientRequest):
    """
    Generate unique domain suggestions for a client using their onboarding data.

    This endpoint:
    1. Fetches client profile and onboarding data (industry, product, notes)
    2. Generates domain candidates using AI
    3. Filters out any domains that already exist for this workspace
    4. Saves unique candidates to the database
    5. Returns the newly saved domains

    Use this for the Purchase New workflow to generate client-specific domains.
    """
    import json

    ht = _import_hypertide_modules()
    if not ht:
        raise HTTPException(
            status_code=503,
            detail="HyperTide automation module not available"
        )

    # 1. Get client + onboarding data
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id, c.onboarding_data
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    workspace_id = client["workspace_id"]
    client_name = client["name"]

    # Parse onboarding data
    onboarding = {}
    if client["onboarding_data"]:
        if isinstance(client["onboarding_data"], str):
            onboarding = json.loads(client["onboarding_data"])
        else:
            onboarding = client["onboarding_data"]

    industry = onboarding.get("industry", "Technology")
    product = onboarding.get("product", "")
    notes = onboarding.get("notes", "")
    primary_domain = onboarding.get("primaryDomain", "")

    # Extract keywords from product description
    brand_keywords = []
    if product:
        # Simple keyword extraction - split by common delimiters
        words = product.replace(",", " ").replace(".", " ").split()
        brand_keywords = [w.lower() for w in words if len(w) > 3][:10]

    # Avoid words from primary domain (to avoid similar domains)
    avoid_words = []
    if primary_domain:
        avoid_words = [primary_domain.split(".")[0].lower()]

    try:
        # 2. Build domain request for HyperTide
        tld_prefs = [
            ht["TLDPreference"](tld=p.tld, priority=p.priority, max_price=Decimal(str(p.max_price)))
            for p in request.preferred_tlds
        ]

        # Generate 2x the requested count to account for filtering
        domain_request = ht["DomainRequest"](
            client_name=client_name,
            industry=industry,
            brand_keywords=brand_keywords,
            target_audience=notes,
            avoid_words=avoid_words,
            required_entra_domains=request.count * 2,
            required_google_domains=0,
            preferred_tlds=tld_prefs,
        )

        # Configure AI generator
        config = ht["DomainGeneratorConfig"](
            provider=request.ai_provider,
            model=request.ai_model,
        )

        # 3. Generate candidates
        try:
            candidates = await ht["generate_domain_candidates"](domain_request, config)
        except Exception as e:
            logger.warning(f"AI generation failed, using fallback: {e}")
            candidates = ht["generate_fallback_candidates"](domain_request)

        total_candidates = len(candidates)

        # 4. Check uniqueness - filter out existing domains
        unique_candidates = []
        for candidate in candidates:
            existing = await fetch_one(
                "SELECT id FROM domains WHERE workspace_id = $1 AND domain_name = $2",
                workspace_id, candidate.domain_name
            )
            if not existing:
                unique_candidates.append(candidate)

        filtered_count = total_candidates - len(unique_candidates)

        # 5. Save unique candidates to DB (up to requested count)
        saved_domains = []
        for candidate in unique_candidates[:request.count]:
            try:
                result = await fetch_one("""
                    INSERT INTO domains (workspace_id, domain_name, notes)
                    VALUES ($1, $2, $3)
                    RETURNING id, domain_name
                """, workspace_id, candidate.domain_name, f"AI generated: {candidate.generation_rationale}")

                if result:
                    saved_domains.append(GeneratedDomainResult(
                        id=result["id"],
                        domain_name=result["domain_name"],
                        base_name=candidate.base_name,
                        tld=candidate.tld,
                        rationale=candidate.generation_rationale,
                        legitimacy_score=candidate.legitimacy_score,
                    ))
            except Exception as db_error:
                logger.warning(f"Failed to save domain {candidate.domain_name}: {db_error}")
                continue

        logger.info(f"Generated {len(saved_domains)} unique domains for client {client_name} (filtered {filtered_count} duplicates)")

        return GenerateForClientResponse(
            client_id=client_id,
            client_name=client_name,
            industry=industry,
            generated_domains=saved_domains,
            filtered_count=filtered_count,
            total_candidates=total_candidates,
            provider_used=request.ai_provider,
            model_used=request.ai_model,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Domain generation for client failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
