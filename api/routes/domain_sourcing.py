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
import asyncio
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
    PendingCandidatesResponse,
    DomainCandidateModel,
    ApprovalResponse,
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


@router.get("/registrar-status")
async def registrar_status():
    """
    Health check for registrar API connections.

    Returns status and balance for both Porkbun and Dynadot registrars.
    Use this to verify credentials are working before purchasing domains.
    """
    # Import here to avoid circular imports (services imported later in file)
    from services.porkbun import PorkbunService
    from services.dynadot import DynadotService

    porkbun = PorkbunService()
    dynadot = DynadotService()

    result = {
        "porkbun": {
            "configured": bool(porkbun.api_key and porkbun.api_secret),
            "connected": False,
            "balance": None,
            "error": None,
        },
        "dynadot": {
            "configured": bool(dynadot.api_key),
            "connected": False,
            "balance": None,
            "error": None,
        },
    }

    try:
        # Test Porkbun
        if result["porkbun"]["configured"]:
            try:
                pb_ok = await porkbun.ping()
                result["porkbun"]["connected"] = pb_ok
                if pb_ok:
                    pb_balance = await porkbun.get_balance()
                    result["porkbun"]["balance"] = str(pb_balance)
            except Exception as e:
                result["porkbun"]["error"] = str(e)
        else:
            result["porkbun"]["error"] = "API credentials not configured"

        # Test Dynadot
        if result["dynadot"]["configured"]:
            try:
                dd_balance = await dynadot.get_balance()
                result["dynadot"]["connected"] = dd_balance > 0
                result["dynadot"]["balance"] = str(dd_balance)
            except Exception as e:
                result["dynadot"]["error"] = str(e)
        else:
            result["dynadot"]["error"] = "API key not configured"

    finally:
        await porkbun.close()
        await dynadot.close()

    return result


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
                # Fetch actual WHOIS registration date from registrar
                registration_date = None
                try:
                    if registrar_name == "dynadot":
                        service = DynadotService()
                    else:
                        service = PorkbunService()
                    domain_info = await service.get_domain_info(domain_name)
                    await service.close()
                    if domain_info.success and domain_info.creation_date:
                        registration_date = domain_info.creation_date
                        logger.info(f"Got actual registration date for {domain_name}: {registration_date}")
                except Exception as info_error:
                    logger.warning(f"Error fetching domain info for {domain_name}: {info_error}")

                # Create domain record in database
                try:
                    existing = await fetch_one(
                        "SELECT id FROM domains WHERE workspace_id = $1 AND domain_name = $2",
                        workspace_id, domain_name
                    )
                    if existing:
                        domain_id = existing["id"]
                        logger.info(f"Domain {domain_name} already exists with id {domain_id}")
                        # Update with registration date if we have it
                        if registration_date:
                            await execute("""
                                UPDATE domains SET registration_date = $1, available_for_setup_at = $1 + INTERVAL '30 days', updated_at = NOW()
                                WHERE id = $2
                            """, registration_date, domain_id)
                    else:
                        if registration_date:
                            new_domain = await fetch_one("""
                                INSERT INTO domains (workspace_id, domain_name, registration_date, available_for_setup_at)
                                VALUES ($1, $2, $3, $3 + INTERVAL '30 days')
                                RETURNING id
                            """, workspace_id, domain_name, registration_date)
                        else:
                            new_domain = await fetch_one("""
                                INSERT INTO domains (workspace_id, domain_name, registration_date, available_for_setup_at)
                                VALUES ($1, $2, NOW(), NOW() + INTERVAL '30 days')
                                RETURNING id
                            """, workspace_id, domain_name)
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

    # Calculate domain count based on package if fill_package=True
    generation_count = request.count
    package_target = None
    existing_count = 0

    if request.fill_package:
        # Get subscription to determine package target
        subscription = await fetch_one("""
            SELECT
                s.id,
                COALESCE(pt.total_domains,
                         (s.entra_packages * s.entra_domains_per_package) +
                         (s.google_packages * s.google_domains_per_package)) as total_domains
            FROM client_subscriptions s
            LEFT JOIN package_templates pt ON s.package_template_id = pt.id
            WHERE s.client_id = $1 AND s.status = 'active'
        """, client_id)

        if subscription:
            package_target = subscription["total_domains"]

            # Count existing domains (available, purchased, active, legacy, warming)
            # These are domains that are already in the pipeline or active
            domain_counts = await fetch_one("""
                SELECT COUNT(*) as total
                FROM domains
                WHERE workspace_id = $1
                AND approval_status IN ('available', 'purchased', 'active', 'legacy', 'warming')
            """, workspace_id)

            existing_count = domain_counts["total"] if domain_counts else 0

            # Calculate gap - how many more domains needed
            gap = max(0, package_target - existing_count)

            if gap == 0:
                logger.info(f"Package capacity reached: {existing_count}/{package_target} domains")
                # Return empty response - no domains needed
                return GenerateForClientResponse(
                    client_id=client_id,
                    client_name=client_name,
                    industry="",
                    generated_domains=[],
                    filtered_count=0,
                    total_candidates=0,
                    message=f"Package capacity reached. {existing_count} domains exist, target is {package_target}.",
                    package_target=package_target,
                    existing_count=existing_count
                )

            # Use the gap as the count (cap at 100 for safety)
            generation_count = min(gap, 100)
            logger.info(f"Package-based generation: need {gap} domains ({existing_count}/{package_target} exist)")

    # Parse onboarding data - check both simplified and comprehensive sources
    onboarding = {}
    if client["onboarding_data"]:
        if isinstance(client["onboarding_data"], str):
            onboarding = json.loads(client["onboarding_data"])
        else:
            onboarding = client["onboarding_data"]

    # If no simplified onboarding, check for comprehensive submission
    if not onboarding:
        comprehensive = await fetch_one("""
            SELECT company_name, website, core_product, target_customer,
                   customer_voice, tone_style
            FROM client_onboarding_submissions
            WHERE client_id = $1 AND submission_status = 'submitted'
            ORDER BY created_at DESC LIMIT 1
        """, client_id)
        if comprehensive:
            onboarding = {
                "industry": "Technology",  # Default, could be enhanced
                "product": comprehensive.get("core_product") or "",
                "notes": comprehensive.get("target_customer") or "",
                "primaryDomain": comprehensive.get("website") or "",
            }

    industry = onboarding.get("industry", "Technology")
    product = onboarding.get("product", "")
    notes = onboarding.get("notes", "")
    primary_domain = onboarding.get("primaryDomain", "")

    # Extract client brand keyword from name (e.g., "Selery" -> "selery")
    # This ensures generated domains include the client's brand identity
    brand_keyword = client_name.lower().replace(" ", "").replace("-", "")

    # Extract additional keywords from product description
    brand_keywords = [brand_keyword]  # Always include client name as primary keyword
    if product:
        # Simple keyword extraction - split by common delimiters
        words = product.replace(",", " ").replace(".", " ").split()
        additional_keywords = [w.lower() for w in words if len(w) > 3 and w.lower() != brand_keyword][:5]
        brand_keywords.extend(additional_keywords)

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
            required_entra_domains=generation_count * 2,
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
        saved_domain_ids: list[UUID] = []
        for candidate in unique_candidates[:generation_count]:
            try:
                result = await fetch_one("""
                    INSERT INTO domains (workspace_id, domain_name, notes, approval_status)
                    VALUES ($1, $2, $3, 'available')
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
                    saved_domain_ids.append(result["id"])
            except Exception as db_error:
                logger.warning(f"Failed to save domain {candidate.domain_name}: {db_error}")
                continue

        logger.info(f"Generated {len(saved_domains)} unique domains for client {client_name} (filtered {filtered_count} duplicates)")

        # Automatically check prices for all saved domains
        # This eliminates the need for users to click "$ Check" buttons
        prices_checked = 0
        available_count = 0
        if saved_domain_ids:
            logger.info(f"Auto-checking prices for {len(saved_domain_ids)} newly generated domains...")
            prices_checked, available_count = await _auto_check_prices_for_domains(saved_domain_ids)
            logger.info(f"Price check complete: {prices_checked} checked, {available_count} available")

        return GenerateForClientResponse(
            client_id=client_id,
            client_name=client_name,
            industry=industry,
            generated_domains=saved_domains,
            filtered_count=filtered_count,
            total_candidates=total_candidates,
            provider_used=request.ai_provider,
            model_used=request.ai_model,
            package_target=package_target,
            existing_count=existing_count,
            message=f"Generated {len(saved_domains)} domains to fill package gap" if request.fill_package else None,
            prices_checked=prices_checked,
            available_count=available_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Domain generation for client failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending-candidates/{client_id}", response_model=PendingCandidatesResponse)
async def get_pending_domain_candidates(
    client_id: UUID,
    count: int = 10,
    request: Optional[GenerateForClientRequest] = None,
):
    """
    Get or generate fresh domain candidates that haven't been reviewed.

    Always returns exactly `count` domains for review. If not enough pending
    candidates exist in the database, generates more using AI.

    Args:
        client_id: The client UUID
        count: Number of candidates to return (default 10)
        request: Optional generation config (uses defaults if not provided)
    """
    import json

    # Get client + workspace
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

    # Get existing pending candidates
    pending = await fetch_all("""
        SELECT id, domain_name, notes, rationale, legitimacy_score, created_at
        FROM domains
        WHERE workspace_id = $1
          AND (approval_status = 'pending' OR approval_status IS NULL)
        ORDER BY created_at DESC
        LIMIT $2
    """, workspace_id, count)

    candidates = []
    for row in pending or []:
        # Extract base_name and tld from domain_name
        domain_name = row["domain_name"]
        parts = domain_name.rsplit(".", 1)
        base_name = parts[0] if len(parts) > 1 else domain_name
        tld = parts[1] if len(parts) > 1 else "com"

        candidates.append(DomainCandidateModel(
            id=row["id"],
            domain_name=domain_name,
            base_name=base_name,
            tld=tld,
            rationale=row.get("rationale") or row.get("notes") or "",
            legitimacy_score=row.get("legitimacy_score") or 0.75,
            approval_status="pending",
            created_at=row["created_at"].isoformat() if row.get("created_at") else None,
        ))

    # If not enough pending candidates, generate more
    if len(candidates) < count:
        needed = count - len(candidates)
        ht = _import_hypertide_modules()

        if ht:
            try:
                # Parse onboarding data for generation context
                onboarding = {}
                if client["onboarding_data"]:
                    if isinstance(client["onboarding_data"], str):
                        onboarding = json.loads(client["onboarding_data"])
                    else:
                        onboarding = client["onboarding_data"]

                # If no simplified onboarding, check for comprehensive submission
                if not onboarding:
                    comprehensive = await fetch_one("""
                        SELECT core_product, target_customer
                        FROM client_onboarding_submissions
                        WHERE client_id = $1 AND submission_status = 'submitted'
                        ORDER BY created_at DESC LIMIT 1
                    """, client_id)
                    if comprehensive:
                        onboarding = {
                            "industry": "Technology",
                            "product": comprehensive.get("core_product") or "",
                            "notes": comprehensive.get("target_customer") or "",
                        }

                industry = onboarding.get("industry", "Technology")
                product = onboarding.get("product", "")
                notes = onboarding.get("notes", "")

                # Extract client brand keyword from name (e.g., "Selery" -> "selery")
                brand_keyword = client["name"].lower().replace(" ", "").replace("-", "")

                # Extract additional keywords from product description
                brand_keywords = [brand_keyword]  # Always include client name
                if product:
                    words = product.replace(",", " ").replace(".", " ").split()
                    additional_keywords = [w.lower() for w in words if len(w) > 3 and w.lower() != brand_keyword][:5]
                    brand_keywords.extend(additional_keywords)

                # Default TLD preferences
                tld_prefs = [
                    ht["TLDPreference"](tld=".com", priority=1, max_price=Decimal("15")),
                    ht["TLDPreference"](tld=".io", priority=2, max_price=Decimal("40")),
                    ht["TLDPreference"](tld=".co", priority=3, max_price=Decimal("25")),
                ]

                domain_request = ht["DomainRequest"](
                    client_name=client["name"],
                    industry=industry,
                    brand_keywords=brand_keywords,
                    target_audience=notes,
                    avoid_words=[],
                    required_entra_domains=needed * 2,  # Generate extra to account for filtering
                    required_google_domains=0,
                    preferred_tlds=tld_prefs,
                )

                # Configure AI generator
                ai_provider = request.ai_provider if request else "anthropic"
                ai_model = request.ai_model if request else None

                config = ht["DomainGeneratorConfig"](
                    provider=ai_provider,
                    model=ai_model,
                )

                # Generate candidates
                try:
                    new_candidates = await ht["generate_domain_candidates"](domain_request, config)
                except Exception as e:
                    logger.warning(f"AI generation failed, using fallback: {e}")
                    new_candidates = ht["generate_fallback_candidates"](domain_request)

                # Save new candidates with pending status
                for candidate in new_candidates[:needed]:
                    # Check if domain already exists
                    existing = await fetch_one(
                        "SELECT id FROM domains WHERE workspace_id = $1 AND domain_name = $2",
                        workspace_id, candidate.domain_name
                    )
                    if existing:
                        continue

                    try:
                        result = await fetch_one("""
                            INSERT INTO domains (workspace_id, domain_name, notes, rationale, legitimacy_score, approval_status)
                            VALUES ($1, $2, $3, $4, $5, 'available')
                            RETURNING id, domain_name, created_at
                        """, workspace_id, candidate.domain_name,
                            f"AI generated: {candidate.generation_rationale}",
                            candidate.generation_rationale,
                            candidate.legitimacy_score
                        )

                        if result:
                            candidates.append(DomainCandidateModel(
                                id=result["id"],
                                domain_name=result["domain_name"],
                                base_name=candidate.base_name,
                                tld=candidate.tld,
                                rationale=candidate.generation_rationale,
                                legitimacy_score=candidate.legitimacy_score,
                                approval_status="available",
                                created_at=result["created_at"].isoformat() if result.get("created_at") else None,
                            ))
                    except Exception as db_error:
                        logger.warning(f"Failed to save candidate {candidate.domain_name}: {db_error}")
                        continue

            except Exception as e:
                logger.error(f"Failed to generate additional candidates: {e}")

    # Get total pending count
    total_pending = await fetch_one("""
        SELECT COUNT(*) as count FROM domains
        WHERE workspace_id = $1
          AND (approval_status = 'pending' OR approval_status IS NULL)
    """, workspace_id)

    return PendingCandidatesResponse(
        client_id=client_id,
        candidates=candidates[:count],
        total_pending=total_pending["count"] if total_pending else len(candidates),
    )


# =============================================================================
# DEPRECATED: Approve/Deny endpoints removed in simplified workflow
# Domains now go directly from 'available' (generated) to 'purchased'
# Users select domains they want to buy, no approval step needed
# =============================================================================

@router.delete("/remove/{domain_id}")
async def remove_domain_candidate(domain_id: UUID):
    """
    Remove a domain candidate from the list.

    Permanently deletes the domain - use this when you don't want to see
    a domain suggestion anymore. Cannot remove purchased/active domains.
    """
    # Verify domain exists
    domain = await fetch_one(
        "SELECT id, domain_name, approval_status FROM domains WHERE id = $1",
        domain_id
    )
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Don't allow removing purchased/active domains
    if domain["approval_status"] in ("purchased", "active"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot remove {domain['approval_status']} domains"
        )

    # Delete the domain
    await execute("DELETE FROM domains WHERE id = $1", domain_id)

    logger.info(f"Removed domain candidate: {domain['domain_name']} ({domain_id})")

    return {
        "domain_id": str(domain_id),
        "domain_name": domain["domain_name"],
        "status": "removed",
        "message": f"Domain {domain['domain_name']} removed from list",
    }


@router.delete("/clear-candidates/{client_id}")
async def clear_domain_candidates(client_id: UUID):
    """
    Clear all available domain candidates for a client.

    Used for starting fresh with domain generation.
    Does NOT delete purchased/active/legacy/warming domains.
    """
    # Verify client exists and get workspace_id
    client = await fetch_one("SELECT id, name, workspace_id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    workspace_id = client["workspace_id"]

    # Delete only available domain candidates (not purchased/active/legacy/warming)
    result = await execute("""
        DELETE FROM domains
        WHERE workspace_id = $1
          AND (approval_status = 'available' OR approval_status IS NULL)
    """, workspace_id)

    # Extract count from result like "DELETE 10"
    deleted_count = 0
    if result and result.startswith("DELETE"):
        try:
            deleted_count = int(result.split()[1])
        except (IndexError, ValueError):
            pass

    logger.info(f"Cleared {deleted_count} domain candidates for client {client['name']} ({client_id})")

    return {
        "client_id": str(client_id),
        "client_name": client["name"],
        "deleted_count": deleted_count,
        "message": f"Cleared {deleted_count} domain candidates for {client['name']}"
    }


@router.get("/available/{client_id}")
async def get_available_domains(client_id: UUID):
    """
    Get all available domain candidates for a client.

    These are generated domains ready for selection and purchase.
    Includes pricing data if available from price checker.
    """
    # Get client + workspace
    client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    workspace_id = client["workspace_id"]

    # Get available domains with pricing data
    # Only return domains that have been priced (at least one provider succeeded)
    available = await fetch_all("""
        SELECT d.id, d.domain_name, d.notes, d.rationale, d.legitimacy_score,
               d.created_at, d.cached_price, d.porkbun_price, d.porkbun_available,
               d.dynadot_price, d.dynadot_available, d.selected_provider,
               d.price_checked_at
        FROM domains d
        WHERE d.workspace_id = $1
          AND d.approval_status = 'available'
          AND d.cached_price IS NOT NULL
        ORDER BY d.cached_price ASC, d.created_at DESC
    """, workspace_id)

    candidates = []
    for row in available or []:
        domain_name = row["domain_name"]
        parts = domain_name.rsplit(".", 1)
        base_name = parts[0] if len(parts) > 1 else domain_name
        tld = parts[1] if len(parts) > 1 else "com"

        candidates.append({
            "id": str(row["id"]),
            "domain_name": domain_name,
            "base_name": base_name,
            "tld": tld,
            "rationale": row.get("rationale") or row.get("notes") or "",
            "legitimacy_score": row.get("legitimacy_score") or 0.75,
            "status": "available",
            # Pricing data
            "cached_price": float(row["cached_price"]) if row.get("cached_price") else None,
            "porkbun_price": float(row["porkbun_price"]) if row.get("porkbun_price") else None,
            "porkbun_available": row.get("porkbun_available"),
            "dynadot_price": float(row["dynadot_price"]) if row.get("dynadot_price") else None,
            "dynadot_available": row.get("dynadot_available"),
            "selected_provider": row.get("selected_provider"),
            "price_checked_at": row["price_checked_at"].isoformat() if row.get("price_checked_at") else None,
        })

    return {
        "client_id": str(client_id),
        "domains": candidates,
        "total": len(candidates),
    }


# Keep backwards compatibility alias
@router.get("/approved/{client_id}")
async def get_approved_domains(client_id: UUID):
    """DEPRECATED: Use /available/{client_id} instead. Kept for backwards compatibility."""
    return await get_available_domains(client_id)


# ============================================================================
# Domain Generation Jobs (Claude Code Worker Integration)
# ============================================================================

@router.post("/jobs/create/{client_id}")
async def create_domain_generation_job(client_id: UUID, count: int = 10, fill_package: bool = True):
    """
    Create a new domain generation job for the Claude Code worker.

    This queues a job that will be picked up by the domain_worker.py daemon,
    which spawns Claude Code to generate domain suggestions using the MCP tools.

    Args:
        client_id: The client UUID to generate domains for
        count: Number of domains to generate (default 10, ignored if fill_package=True)
        fill_package: If True, auto-calculate count to fill package capacity (default True)

    Returns:
        Job ID and status information
    """
    # Verify client exists
    client = await fetch_one("SELECT id, name, workspace_id FROM clients WHERE id = $1", client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    workspace_id = client["workspace_id"]
    generation_count = count
    package_target = None
    existing_count = 0

    # Calculate count based on package if fill_package=True
    if fill_package:
        subscription = await fetch_one("""
            SELECT
                s.id,
                COALESCE(pt.total_domains,
                         (s.entra_packages * s.entra_domains_per_package) +
                         (s.google_packages * s.google_domains_per_package)) as total_domains
            FROM client_subscriptions s
            LEFT JOIN package_templates pt ON s.package_template_id = pt.id
            WHERE s.client_id = $1 AND s.status = 'active'
        """, client_id)

        if subscription:
            package_target = subscription["total_domains"]

            # Count domains by status
            # - Confirmed: purchased, active, legacy, warming (committed)
            # - Available: generated, ready for purchase selection
            domain_counts = await fetch_one("""
                SELECT
                    COUNT(*) FILTER (WHERE approval_status IN ('purchased', 'active', 'legacy', 'warming')) as confirmed,
                    COUNT(*) FILTER (WHERE approval_status = 'available') as available
                FROM domains
                WHERE workspace_id = $1
            """, workspace_id)

            confirmed_count = domain_counts["confirmed"] if domain_counts else 0
            available_count = domain_counts["available"] if domain_counts else 0
            existing_count = confirmed_count  # Only confirmed count towards capacity
            gap = max(0, package_target - existing_count)

            # Always generate at least 20 domains per batch for good selection
            # Generate more if gap is larger, up to 50 per batch
            MIN_BATCH_SIZE = 20
            MAX_BATCH_SIZE = 50

            if gap == 0 and available_count >= MIN_BATCH_SIZE:
                # Have enough available domains to purchase from
                return {
                    "job_id": None,
                    "client_id": str(client_id),
                    "client_name": client["name"],
                    "count": 0,
                    "status": "skipped",
                    "created_at": None,
                    "message": f"Package capacity reached with {confirmed_count} confirmed domains. {available_count} available for purchase.",
                    "package_target": package_target,
                    "existing_count": confirmed_count,
                    "available_count": available_count
                }

            # Generate at least MIN_BATCH_SIZE, or gap + buffer for denials
            generation_count = max(MIN_BATCH_SIZE, min(gap + 10, MAX_BATCH_SIZE))
            logger.info(f"Package-based job: generating {generation_count} domains ({confirmed_count} confirmed, {available_count} available, target {package_target})")

    # Ensure jobs table exists
    await execute("""
        CREATE TABLE IF NOT EXISTS domain_generation_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            client_id UUID NOT NULL REFERENCES clients(id),
            count INTEGER DEFAULT 10,
            status VARCHAR(50) DEFAULT 'pending',
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)

    # Create job
    job = await fetch_one("""
        INSERT INTO domain_generation_jobs (client_id, count, status)
        VALUES ($1, $2, 'pending')
        RETURNING id, status, created_at
    """, client_id, generation_count)

    logger.info(f"Created domain generation job {job['id']} for client {client['name']} ({generation_count} domains)")

    return {
        "job_id": str(job["id"]),
        "client_id": str(client_id),
        "client_name": client["name"],
        "count": generation_count,
        "status": job["status"],
        "created_at": job["created_at"].isoformat(),
        "message": f"Job queued for processing by Claude Code worker. Generating {generation_count} domains.",
        "package_target": package_target,
        "existing_count": existing_count
    }


@router.get("/jobs/status/{job_id}")
async def get_job_status(job_id: UUID):
    """
    Get the status of a domain generation job.

    Returns:
        Job details including status, timestamps, and any error message
    """
    job = await fetch_one("""
        SELECT j.*, c.name as client_name
        FROM domain_generation_jobs j
        JOIN clients c ON c.id = j.client_id
        WHERE j.id = $1
    """, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(job["id"]),
        "client_id": str(job["client_id"]),
        "client_name": job["client_name"],
        "count": job["count"],
        "status": job["status"],
        "error_message": job.get("error_message"),
        "created_at": job["created_at"].isoformat() if job.get("created_at") else None,
        "started_at": job["started_at"].isoformat() if job.get("started_at") else None,
        "completed_at": job["completed_at"].isoformat() if job.get("completed_at") else None,
    }


@router.get("/jobs/client/{client_id}")
async def get_client_jobs(client_id: UUID, limit: int = 10):
    """
    Get recent domain generation jobs for a client.

    Args:
        client_id: The client UUID
        limit: Maximum number of jobs to return (default 10)

    Returns:
        List of recent jobs for this client
    """
    jobs = await fetch_all("""
        SELECT id, count, status, error_message, created_at, started_at, completed_at
        FROM domain_generation_jobs
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT $2
    """, client_id, limit)

    return {
        "client_id": str(client_id),
        "jobs": [
            {
                "job_id": str(j["id"]),
                "count": j["count"],
                "status": j["status"],
                "error_message": j.get("error_message"),
                "created_at": j["created_at"].isoformat() if j.get("created_at") else None,
                "started_at": j["started_at"].isoformat() if j.get("started_at") else None,
                "completed_at": j["completed_at"].isoformat() if j.get("completed_at") else None,
            }
            for j in (jobs or [])
        ],
        "total": len(jobs or [])
    }


@router.get("/can-generate/{client_id}")
async def can_generate_domains(client_id: UUID):
    """
    Check if domain generation is available for a client.

    Generation is possible if:
    - Client has onboarding data (for creative mode), OR
    - Client has existing domains (for pattern fallback mode)

    Returns:
        Whether generation is available and which mode would be used
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id, c.onboarding_data, c.onboarding_complete
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client["workspace_id"]

    # Check for comprehensive onboarding submission (external form)
    comprehensive_submission = await fetch_one("""
        SELECT id FROM client_onboarding_submissions
        WHERE client_id = $1 AND submission_status = 'submitted'
        ORDER BY created_at DESC LIMIT 1
    """, client_id)

    has_onboarding = (
        client["onboarding_complete"] or
        bool(client.get("onboarding_data")) or
        bool(comprehensive_submission)
    )

    # Check for existing domains
    domain_count = 0
    domain_pattern = None

    if workspace_id:
        count_result = await fetch_one("""
            SELECT COUNT(*) as count FROM domains WHERE workspace_id = $1
        """, workspace_id)
        domain_count = count_result["count"] if count_result else 0

        # Extract pattern from existing domains
        if domain_count > 0:
            domains = await fetch_all("""
                SELECT domain_name FROM domains WHERE workspace_id = $1 LIMIT 50
            """, workspace_id)
            domain_names = [d["domain_name"] for d in (domains or [])]

            # Find common suffix
            if domain_names:
                # Simple pattern extraction - find longest common suffix
                min_len = min(len(d) for d in domain_names)
                suffix = ""
                for i in range(1, min_len + 1):
                    suffixes = set(d[-i:] for d in domain_names)
                    if len(suffixes) == 1:
                        suffix = list(suffixes)[0]
                    else:
                        break
                if suffix and "." in suffix:
                    domain_pattern = suffix

    can_generate = has_onboarding or domain_count > 0

    return {
        "client_id": str(client_id),
        "client_name": client["name"],
        "can_generate": can_generate,
        "generation_mode": "onboarding" if has_onboarding else ("pattern_fallback" if domain_count > 0 else "none"),
        "has_onboarding": has_onboarding,
        "existing_domain_count": domain_count,
        "domain_pattern": domain_pattern,
        "message": (
            "Ready for AI-powered domain generation based on your profile" if has_onboarding
            else f"Ready to generate new domains matching pattern: {domain_pattern}" if domain_pattern
            else "No generation source available - complete onboarding or add existing domains"
        )
    }


# =============================================================================
# STANDALONE ENDPOINTS (No Hypertide Required)
# =============================================================================

from services.porkbun import PorkbunService, DomainCheckResult as PorkbunCheckResult
from services.dynadot import DynadotService, DomainCheckResult as DynadotCheckResult
from services.domain_generator import generate_domain_suggestions, DomainSuggestion
from pydantic import BaseModel, Field
import json


class SimpleGenerateResponse(BaseModel):
    """Response from simple domain generation."""
    client_id: str
    client_name: str
    suggestions: list[dict]
    count: int
    saved_count: int
    prices_checked: int = 0  # Number of domains with prices fetched
    available_count: int = 0  # Number of domains still available


async def _auto_check_prices_for_domains(domain_ids: list[UUID]) -> tuple[int, int]:
    """
    Automatically check prices for newly generated domains.

    Called after domain generation to immediately populate pricing data,
    eliminating the need for users to click "$ Check" buttons.

    Args:
        domain_ids: List of domain UUIDs to check

    Returns:
        Tuple of (checked_count, available_count)
    """
    if not domain_ids:
        return 0, 0

    porkbun = PorkbunService()
    dynadot = DynadotService()
    checked_count = 0
    available_count = 0

    try:
        # Fetch domain names
        domains = await fetch_all("""
            SELECT id, domain_name FROM domains WHERE id = ANY($1)
        """, domain_ids)

        for domain in domains:
            domain_id = domain["id"]
            domain_name = domain["domain_name"]

            try:
                # Check both providers concurrently
                porkbun_result, dynadot_result = await asyncio.gather(
                    porkbun.check_availability(domain_name),
                    dynadot.check_availability(domain_name),
                    return_exceptions=True
                )

                # Process Porkbun result
                porkbun_available = None
                porkbun_price = None
                if not isinstance(porkbun_result, Exception):
                    porkbun_available = porkbun_result.available
                    if porkbun_result.available and porkbun_result.price is not None:
                        porkbun_price = float(porkbun_result.price)

                # Process Dynadot result
                dynadot_available = None
                dynadot_price = None
                if not isinstance(dynadot_result, Exception):
                    dynadot_available = dynadot_result.available
                    if dynadot_result.available and dynadot_result.price is not None:
                        dynadot_price = float(dynadot_result.price)

                # Determine best price and provider
                best_price = None
                best_provider = None
                is_available = porkbun_available or dynadot_available

                if porkbun_price is not None and dynadot_price is not None:
                    if porkbun_price <= dynadot_price:
                        best_price = porkbun_price
                        best_provider = "porkbun"
                    else:
                        best_price = dynadot_price
                        best_provider = "dynadot"
                elif porkbun_price is not None:
                    best_price = porkbun_price
                    best_provider = "porkbun"
                elif dynadot_price is not None:
                    best_price = dynadot_price
                    best_provider = "dynadot"

                # Update domain with price data
                await execute("""
                    UPDATE domains
                    SET porkbun_price = $1,
                        porkbun_available = $2,
                        dynadot_price = $3,
                        dynadot_available = $4,
                        cached_price = $5,
                        selected_provider = $6,
                        last_price_check = NOW()
                    WHERE id = $7
                """, porkbun_price, porkbun_available, dynadot_price, dynadot_available,
                    best_price, best_provider, domain_id)

                checked_count += 1

                if is_available:
                    available_count += 1
                else:
                    # Auto-remove unavailable domains
                    await execute("""
                        DELETE FROM domains
                        WHERE id = $1 AND approval_status IN ('available', 'pending')
                    """, domain_id)
                    logger.info(f"Auto-removed unavailable domain: {domain_name}")

            except Exception as e:
                logger.warning(f"Failed to check price for {domain_name}: {e}")

            # Brief delay between checks to respect rate limits
            await asyncio.sleep(0.3)

    finally:
        await porkbun.close()
        await dynadot.close()

    return checked_count, available_count


class AvailabilityCheckRequest(BaseModel):
    """Request to check domain availability."""
    domains: list[str]


class AvailabilityCheckResponse(BaseModel):
    """Response from availability check."""
    results: list[dict]
    available_count: int
    total_checked: int


class PurchaseDomainsRequest(BaseModel):
    """Request to purchase domains."""
    domain_ids: list[UUID]


class PurchaseDomainsResponse(BaseModel):
    """Response from domain purchase."""
    purchases: list[dict]
    successful_count: int
    failed_count: int
    total_cost: str


class BalanceResponse(BaseModel):
    """Porkbun account balance response."""
    balance: str
    currency: str = "USD"


@router.post("/generate-simple/{client_id}", response_model=SimpleGenerateResponse)
async def generate_domains_simple(
    client_id: UUID,
    count: int = 10,
    tlds: Optional[str] = None,
):
    """
    Generate domain suggestions using pattern-based generation.

    No AI, no Hypertide - just deterministic patterns based on client name.

    Args:
        client_id: Client UUID
        count: Number of suggestions to generate (default 10)
        tlds: Comma-separated TLDs (default ".com,.io,.co")

    Returns:
        List of domain suggestions saved to database
    """
    # Get client with workspace
    client = await fetch_one("""
        SELECT c.id, c.name, c.workspace_id
        FROM clients c
        WHERE c.id = $1
    """, client_id)

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    if not client["workspace_id"]:
        raise HTTPException(status_code=400, detail="Client not linked to a workspace")

    workspace_id = client["workspace_id"]
    client_name = client["name"]

    # Extract brand keyword from client name
    brand = client_name.lower().replace(" ", "").replace("-", "")

    # Parse TLDs if provided
    tld_list = None
    if tlds:
        tld_list = [t.strip() for t in tlds.split(",") if t.strip()]
        # Ensure TLDs start with dot
        tld_list = [t if t.startswith(".") else f".{t}" for t in tld_list]

    # Generate suggestions
    suggestions = generate_domain_suggestions(
        brand_keyword=brand,
        count=count,
        tlds=tld_list,
    )

    # Save to database as available and collect IDs for price checking
    saved_count = 0
    saved_domain_ids: list[UUID] = []

    for s in suggestions:
        try:
            # Check if domain already exists for this workspace
            existing = await fetch_one("""
                SELECT id FROM domains WHERE workspace_id = $1 AND domain_name = $2
            """, workspace_id, s.domain)

            if not existing:
                # Use RETURNING to get the new domain ID
                result = await fetch_one("""
                    INSERT INTO domains (workspace_id, domain_name, rationale, legitimacy_score, approval_status)
                    VALUES ($1, $2, $3, $4, 'available')
                    RETURNING id
                """, workspace_id, s.domain, s.rationale, s.legitimacy_score)
                saved_count += 1
                if result:
                    saved_domain_ids.append(result["id"])
        except Exception as e:
            logger.warning(f"Failed to save domain {s.domain}: {e}")

    # Automatically check prices for all saved domains
    # This eliminates the need for users to click "$ Check" buttons
    prices_checked = 0
    available_count = 0
    if saved_domain_ids:
        logger.info(f"Auto-checking prices for {len(saved_domain_ids)} newly generated domains...")
        prices_checked, available_count = await _auto_check_prices_for_domains(saved_domain_ids)
        logger.info(f"Price check complete: {prices_checked} checked, {available_count} available")

    return SimpleGenerateResponse(
        client_id=str(client_id),
        client_name=client_name,
        suggestions=[s.model_dump() for s in suggestions],
        count=len(suggestions),
        saved_count=saved_count,
        prices_checked=prices_checked,
        available_count=available_count,
    )


@router.post("/check-availability", response_model=AvailabilityCheckResponse)
async def check_domain_availability(request: AvailabilityCheckRequest):
    """
    Check availability and pricing for domains via Porkbun API.

    No Hypertide required - direct API calls to Porkbun.

    Args:
        domains: List of domain names to check

    Returns:
        Availability and pricing for each domain
    """
    if not request.domains:
        raise HTTPException(status_code=400, detail="No domains provided")

    if len(request.domains) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 domains per request")

    porkbun = PorkbunService()

    try:
        results = await porkbun.check_bulk(request.domains)

        # Convert to response format
        response_results = []
        available_count = 0
        for r in results:
            result_dict = {
                "domain": r.domain,
                "available": r.available,
                "price": str(r.price) if r.price else None,
                "renewal_price": str(r.renewal_price) if r.renewal_price else None,
                "is_promotional": r.is_promotional,
                "regular_price": str(r.regular_price) if r.regular_price else None,
                "error": r.error,
            }
            response_results.append(result_dict)
            if r.available:
                available_count += 1

        return AvailabilityCheckResponse(
            results=response_results,
            available_count=available_count,
            total_checked=len(results),
        )

    finally:
        await porkbun.close()


@router.get("/porkbun/balance", response_model=BalanceResponse)
async def get_porkbun_balance():
    """
    Get current Porkbun account balance.

    Useful for checking if there are sufficient funds before purchasing.
    """
    porkbun = PorkbunService()

    try:
        balance = await porkbun.get_balance()
        return BalanceResponse(balance=str(balance))
    finally:
        await porkbun.close()


# =============================================================================
# SINGLE DOMAIN ACTIONS (Inline Table Operations)
# =============================================================================

class ProviderPriceInfo(BaseModel):
    """Price information from a single provider."""
    available: bool
    price: Optional[str] = None
    renewal_price: Optional[str] = None
    error: Optional[str] = None


class CheckPriceResponse(BaseModel):
    """Response from single domain price check with dual provider pricing."""
    domain_id: str
    domain_name: str
    available: bool  # True if available from at least one provider
    price: Optional[str] = None  # Best (lowest) price
    renewal_price: Optional[str] = None
    is_promotional: bool = False
    error: Optional[str] = None
    # Dual provider pricing
    porkbun: Optional[ProviderPriceInfo] = None
    dynadot: Optional[ProviderPriceInfo] = None
    best_provider: Optional[str] = None  # "porkbun" or "dynadot"


class PurchaseSingleResponse(BaseModel):
    """Response from single domain purchase."""
    domain_id: str
    domain_name: str
    success: bool
    order_id: Optional[str] = None
    price: Optional[str] = None
    error: Optional[str] = None


@router.post("/check-price/{domain_id}", response_model=CheckPriceResponse)
async def check_domain_price(domain_id: UUID):
    """
    Check price for a single domain from both Porkbun and Dynadot.

    Used for inline table actions - checks availability and pricing from
    both registrars, then stores the prices in the database for display.

    Args:
        domain_id: UUID of the domain to check

    Returns:
        Availability and pricing information from both providers
    """
    # Get domain from database
    domain = await fetch_one("""
        SELECT id, domain_name, workspace_id, approval_status
        FROM domains
        WHERE id = $1
    """, domain_id)

    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    porkbun = PorkbunService()
    dynadot = DynadotService()

    try:
        # Check both providers concurrently
        import asyncio
        porkbun_result, dynadot_result = await asyncio.gather(
            porkbun.check_availability(domain["domain_name"]),
            dynadot.check_availability(domain["domain_name"]),
            return_exceptions=True
        )

        # Process Porkbun result
        porkbun_info = None
        porkbun_price = None
        if isinstance(porkbun_result, Exception):
            logger.error(f"Porkbun API error for {domain['domain_name']}: {porkbun_result}")
            porkbun_info = ProviderPriceInfo(
                available=False,
                error=str(porkbun_result),
            )
        else:
            porkbun_info = ProviderPriceInfo(
                available=porkbun_result.available,
                price=str(porkbun_result.price) if porkbun_result.price is not None else None,
                renewal_price=str(porkbun_result.renewal_price) if porkbun_result.renewal_price is not None else None,
                error=porkbun_result.error,
            )
            if porkbun_result.available and porkbun_result.price is not None:
                porkbun_price = float(porkbun_result.price)

        # Process Dynadot result
        dynadot_info = None
        dynadot_price = None
        if isinstance(dynadot_result, Exception):
            logger.error(f"Dynadot API error for {domain['domain_name']}: {dynadot_result}")
            dynadot_info = ProviderPriceInfo(
                available=False,
                error=str(dynadot_result),
            )
        else:
            dynadot_info = ProviderPriceInfo(
                available=dynadot_result.available,
                price=str(dynadot_result.price) if dynadot_result.price is not None else None,
                renewal_price=str(dynadot_result.renewal_price) if dynadot_result.renewal_price is not None else None,
                error=dynadot_result.error,
            )
            if dynadot_result.available and dynadot_result.price is not None:
                dynadot_price = float(dynadot_result.price)

        # Determine best price and provider
        available = (porkbun_info and porkbun_info.available) or (dynadot_info and dynadot_info.available)
        best_price = None
        best_provider = None

        if porkbun_price is not None and dynadot_price is not None:
            if porkbun_price <= dynadot_price:
                best_price = porkbun_price
                best_provider = "porkbun"
            else:
                best_price = dynadot_price
                best_provider = "dynadot"
        elif porkbun_price is not None:
            best_price = porkbun_price
            best_provider = "porkbun"
        elif dynadot_price is not None:
            best_price = dynadot_price
            best_provider = "dynadot"

        # Cache the prices in database
        await execute("""
            UPDATE domains
            SET porkbun_price = $1,
                porkbun_available = $2,
                dynadot_price = $3,
                dynadot_available = $4,
                cached_price = $5,
                selected_provider = $6,
                price_checked_at = NOW()
            WHERE id = $7
        """, porkbun_price, porkbun_info.available if porkbun_info else False,
            dynadot_price, dynadot_info.available if dynadot_info else False,
            best_price, best_provider, domain_id)

        return CheckPriceResponse(
            domain_id=str(domain_id),
            domain_name=domain["domain_name"],
            available=available,
            price=str(best_price) if best_price else None,
            porkbun=porkbun_info,
            dynadot=dynadot_info,
            best_provider=best_provider,
        )

    finally:
        await porkbun.close()
        await dynadot.close()


# DNSimple nameservers required by Hypertide (must be set at purchase time)
DNSIMPLE_NAMESERVERS = [
    "ns1.dnsimple.com",
    "ns2.dnsimple-edge.net",
    "ns3.dnsimple.com",
    "ns4.dnsimple-edge.org",
]


@router.post("/purchase/{domain_id}", response_model=PurchaseSingleResponse)
async def purchase_single_domain(domain_id: UUID, provider: Optional[str] = None):
    """
    Purchase a single available domain from selected provider.

    Used for inline table actions - purchases the domain and updates status.
    Domain must be in 'available' status (generated, not yet purchased).

    IMPORTANT: Automatically sets DNSimple nameservers at purchase time.
    This is REQUIRED for Hypertide - nameservers must be configured before
    placing a Hypertide order. DNS propagation takes 24-48 hours.

    Args:
        domain_id: UUID of the domain to purchase
        provider: Optional provider override ("porkbun" or "dynadot")

    Returns:
        Purchase result with success status
    """
    PRICE_THRESHOLD = Decimal("15.00")

    # Get domain from database
    domain = await fetch_one("""
        SELECT id, domain_name, workspace_id, approval_status, cached_price,
               porkbun_price, porkbun_available, dynadot_price, dynadot_available,
               selected_provider
        FROM domains
        WHERE id = $1
    """, domain_id)

    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Domain must be available for purchase (not already purchased/active)
    # Accept 'pending', 'available', or 'approved' status
    if domain["approval_status"] not in ("available", "approved", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Domain is not available for purchase (current status: {domain['approval_status']})"
        )

    # Require price check before purchase - prevents defaulting to wrong registrar
    if domain.get("porkbun_price") is None and domain.get("dynadot_price") is None:
        return PurchaseSingleResponse(
            domain_id=str(domain_id),
            domain_name=domain["domain_name"],
            success=False,
            error="Price check required before purchase. Run 'Refresh Prices' first.",
        )

    # Determine which provider to use (selected_provider is set by price check to cheapest)
    use_provider = provider or domain.get("selected_provider")
    if not use_provider:
        return PurchaseSingleResponse(
            domain_id=str(domain_id),
            domain_name=domain["domain_name"],
            success=False,
            error="No provider selected. Run price check first.",
        )

    if use_provider == "dynadot":
        registrar = DynadotService()
        registrar_name = "dynadot"
    else:
        registrar = PorkbunService()
        registrar_name = "porkbun"

    try:
        # Check availability first (re-verify price hasn't changed)
        check_result = await registrar.check_availability(domain["domain_name"])

        if not check_result.available:
            # Primary provider unavailable - try fallback provider
            fallback_provider = "dynadot" if use_provider == "porkbun" else "porkbun"
            logger.info(f"Domain {domain['domain_name']} unavailable on {registrar_name}, trying {fallback_provider}")

            if fallback_provider == "dynadot":
                fallback_registrar = DynadotService()
            else:
                fallback_registrar = PorkbunService()

            fallback_check = await fallback_registrar.check_availability(domain["domain_name"])

            if fallback_check.available:
                # Switch to fallback provider
                registrar = fallback_registrar
                registrar_name = fallback_provider
                use_provider = fallback_provider
                check_result = fallback_check
                logger.info(f"Fallback successful: {domain['domain_name']} available on {fallback_provider}")

                # Update selected_provider in DB to reflect actual provider
                await execute("""
                    UPDATE domains SET selected_provider = $1 WHERE id = $2
                """, fallback_provider, domain_id)
            else:
                # Neither provider has it available
                return PurchaseSingleResponse(
                    domain_id=str(domain_id),
                    domain_name=domain["domain_name"],
                    success=False,
                    error="Domain is no longer available on any registrar",
                )

        # Verify price is under threshold
        price = check_result.price or Decimal("15")
        if price > PRICE_THRESHOLD:
            return PurchaseSingleResponse(
                domain_id=str(domain_id),
                domain_name=domain["domain_name"],
                success=False,
                error=f"Price ${price} exceeds threshold of ${PRICE_THRESHOLD}",
            )

        # Check balance
        balance = await registrar.get_balance()

        if balance < price:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient {registrar_name} balance. Need ${price}, have ${balance}."
            )

        # Purchase the domain (nameservers set separately after purchase)
        logger.info(f"Purchasing {domain['domain_name']} via {registrar_name}")
        result = await registrar.purchase(
            domain["domain_name"],
            nameservers=DNSIMPLE_NAMESERVERS,  # Some registrars may accept this
        )

        if result.success:
            # Explicitly set nameservers after purchase (required for Dynadot)
            # The register API often doesn't apply NS, so we must call set_nameservers
            ns_success = False
            ns_status = "pending"
            try:
                logger.info(f"Setting DNSimple nameservers for {domain['domain_name']} at {registrar_name}")
                ns_success = await registrar.set_nameservers(domain["domain_name"], DNSIMPLE_NAMESERVERS)
                if ns_success:
                    ns_status = "propagating"  # NS set, waiting for DNS propagation
                    logger.info(f"Nameservers set successfully for {domain['domain_name']}")
                else:
                    ns_status = "failed"
                    logger.warning(f"Failed to set nameservers for {domain['domain_name']} - will need manual fix")
            except Exception as ns_error:
                ns_status = "failed"
                logger.error(f"Error setting nameservers for {domain['domain_name']}: {ns_error}")

            # Get actual WHOIS registration date from registrar
            # This is the TRUE domain creation date, not when we purchased it
            registration_date = None
            try:
                logger.info(f"Fetching actual registration date for {domain['domain_name']} from {registrar_name}")
                domain_info = await registrar.get_domain_info(domain["domain_name"])
                if domain_info.success and domain_info.creation_date:
                    registration_date = domain_info.creation_date
                    logger.info(f"Got actual registration date for {domain['domain_name']}: {registration_date}")
                else:
                    logger.warning(f"Could not get registration date for {domain['domain_name']}, using NOW() as fallback")
            except Exception as info_error:
                logger.warning(f"Error fetching domain info for {domain['domain_name']}: {info_error}, using NOW() as fallback")

            # Update domain status to purchased with nameserver tracking
            # nameservers_updated_at is set only if NS were successfully configured
            # registration_date uses actual WHOIS creation date if available, else NOW()
            # available_for_setup_at is 30 days after registration_date
            if registration_date:
                # Use actual WHOIS creation date
                await execute("""
                    UPDATE domains
                    SET approval_status = 'purchased',
                        cached_price = $1,
                        selected_provider = $2,
                        purchased_at = NOW(),
                        registration_date = $3,
                        available_for_setup_at = $3 + INTERVAL '30 days',
                        nameservers_updated_at = CASE WHEN $4 THEN NOW() ELSE NULL END,
                        nameserver_status = $5,
                        updated_at = NOW()
                    WHERE id = $6
                """, float(price), registrar_name, registration_date, ns_success, ns_status, domain_id)
            else:
                # Fallback to NOW() if we couldn't fetch the actual date
                await execute("""
                    UPDATE domains
                    SET approval_status = 'purchased',
                        cached_price = $1,
                        selected_provider = $2,
                        purchased_at = NOW(),
                        registration_date = NOW(),
                        available_for_setup_at = NOW() + INTERVAL '30 days',
                        nameservers_updated_at = CASE WHEN $3 THEN NOW() ELSE NULL END,
                        nameserver_status = $4,
                        updated_at = NOW()
                    WHERE id = $5
                """, float(price), registrar_name, ns_success, ns_status, domain_id)

            logger.info(f"Successfully purchased {domain['domain_name']} - NS status: {ns_status}")

            return PurchaseSingleResponse(
                domain_id=str(domain_id),
                domain_name=domain["domain_name"],
                success=True,
                order_id=result.order_id,
                price=str(price),
            )
        else:
            return PurchaseSingleResponse(
                domain_id=str(domain_id),
                domain_name=domain["domain_name"],
                success=False,
                error=result.error,
            )

    finally:
        await registrar.close()


@router.post("/purchase-domains", response_model=PurchaseDomainsResponse)
async def purchase_selected_domains(request: PurchaseDomainsRequest):
    """
    Purchase selected domains via Porkbun API.

    Only purchases domains that are available (approval_status='available').
    Returns 402 Payment Required if insufficient balance.

    Args:
        domain_ids: List of domain UUIDs to purchase

    Returns:
        Purchase results for each domain
    """
    if not request.domain_ids:
        raise HTTPException(status_code=400, detail="No domain IDs provided")

    porkbun = PorkbunService()

    try:
        # Get available domains from database
        domains_to_purchase = []
        for domain_id in request.domain_ids:
            domain = await fetch_one("""
                SELECT id, domain_name, workspace_id, approval_status
                FROM domains
                WHERE id = $1
            """, domain_id)

            if not domain:
                raise HTTPException(status_code=404, detail=f"Domain {domain_id} not found")

            if domain["approval_status"] not in ("available", "approved", "pending"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Domain {domain['domain_name']} is not available for purchase (status: {domain['approval_status']})"
                )

            domains_to_purchase.append(domain)

        if not domains_to_purchase:
            raise HTTPException(status_code=400, detail="No valid domains to purchase")

        # Check availability and get total cost
        domain_names = [d["domain_name"] for d in domains_to_purchase]
        availability_results = await porkbun.check_bulk(domain_names)

        total_cost = Decimal("0")
        available_domains = []
        for result in availability_results:
            if result.available and result.price:
                total_cost += result.price
                available_domains.append(result)
            elif not result.available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Domain {result.domain} is no longer available"
                )

        # Check balance
        balance = await porkbun.get_balance()
        if balance < total_cost:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient balance. Need ${total_cost}, have ${balance}. Add funds at porkbun.com"
            )

        # Purchase each domain
        purchases = []
        successful_count = 0
        failed_count = 0
        actual_cost = Decimal("0")

        for domain in domains_to_purchase:
            result = await porkbun.purchase(domain["domain_name"])

            purchase_dict = {
                "domain_id": str(domain["id"]),
                "domain": domain["domain_name"],
                "success": result.success,
                "order_id": result.order_id,
                "error": result.error,
            }
            purchases.append(purchase_dict)

            if result.success:
                successful_count += 1
                # Find the price from availability check
                for avail in availability_results:
                    if avail.domain == domain["domain_name"] and avail.price:
                        actual_cost += avail.price
                        break

                # Update domain status in database
                await execute("""
                    UPDATE domains
                    SET approval_status = 'purchased', updated_at = NOW()
                    WHERE id = $1
                """, domain["id"])
            else:
                failed_count += 1

        return PurchaseDomainsResponse(
            purchases=purchases,
            successful_count=successful_count,
            failed_count=failed_count,
            total_cost=str(actual_cost),
        )

    finally:
        await porkbun.close()


class UpdateNameserversRequest(BaseModel):
    """Request to update nameservers for existing domains."""
    domain_names: list[str] = Field(..., description="Domain names to update")
    nameservers: list[str] = Field(
        default_factory=lambda: [
            "ns1.dnsimple.com",
            "ns2.dnsimple-edge.net",
            "ns3.dnsimple.com",
            "ns4.dnsimple-edge.org",
        ],
        description="DNSimple nameservers required by Hypertide"
    )


class UpdateNameserversResponse(BaseModel):
    """Response from nameserver update."""
    results: list[dict]
    successful_count: int
    failed_count: int


@router.post("/update-nameservers", response_model=UpdateNameserversResponse)
async def update_nameservers(request: UpdateNameserversRequest):
    """
    Update nameservers for existing domains.

    Use this to fix domains that were purchased with incorrect nameservers.
    Domains must be owned in either Porkbun or Dynadot.

    Hypertide requires these DNSimple nameservers:
    - ns1.dnsimple.com
    - ns2.dnsimple-edge.net
    - ns3.dnsimple.com
    - ns4.dnsimple-edge.org
    """
    porkbun = PorkbunService()
    dynadot = DynadotService()

    results = []
    successful_count = 0
    failed_count = 0

    try:
        for domain_name in request.domain_names:
            porkbun_error = None
            dynadot_error = None

            # Try Porkbun first
            try:
                logger.info(f"Trying Porkbun for {domain_name}")
                success = await porkbun.set_nameservers(domain_name, request.nameservers)
                if success:
                    # Update nameservers_updated_at in database for DNS readiness tracking
                    await execute("""
                        UPDATE domains
                        SET nameservers_updated_at = NOW(),
                            selected_provider = 'porkbun',
                            updated_at = NOW()
                        WHERE domain_name = $1
                    """, domain_name)
                    results.append({
                        "domain": domain_name,
                        "success": True,
                        "registrar": "porkbun",
                        "nameservers": request.nameservers,
                    })
                    successful_count += 1
                    logger.info(f"Updated nameservers for {domain_name} via Porkbun - DNS propagation started")
                    continue
                else:
                    porkbun_error = "API returned failure (domain may not be in this account)"
                    logger.info(f"Porkbun returned False for {domain_name}")
            except Exception as e:
                porkbun_error = str(e)
                logger.info(f"Porkbun exception for {domain_name}: {e}")

            # Try Dynadot
            try:
                logger.info(f"Trying Dynadot for {domain_name}")
                success = await dynadot.set_nameservers(domain_name, request.nameservers)
                if success:
                    # Update nameservers_updated_at in database for DNS readiness tracking
                    await execute("""
                        UPDATE domains
                        SET nameservers_updated_at = NOW(),
                            selected_provider = 'dynadot',
                            updated_at = NOW()
                        WHERE domain_name = $1
                    """, domain_name)
                    results.append({
                        "domain": domain_name,
                        "success": True,
                        "registrar": "dynadot",
                        "nameservers": request.nameservers,
                    })
                    successful_count += 1
                    logger.info(f"Updated nameservers for {domain_name} via Dynadot - DNS propagation started")
                    continue
                else:
                    dynadot_error = "API returned failure (domain may not be in this account)"
                    logger.info(f"Dynadot returned False for {domain_name}")
            except Exception as e:
                dynadot_error = str(e)
                logger.info(f"Dynadot exception for {domain_name}: {e}")

            # Both failed
            results.append({
                "domain": domain_name,
                "success": False,
                "error": f"Porkbun: {porkbun_error}, Dynadot: {dynadot_error}",
            })
            failed_count += 1

        return UpdateNameserversResponse(
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
        )

    finally:
        await porkbun.close()
        await dynadot.close()


class VerifyNameserversRequest(BaseModel):
    """Request to verify nameservers for domains."""
    domain_names: list[str]


class NameserverVerificationResult(BaseModel):
    """Result of verifying nameservers for a single domain."""
    domain: str
    status: str  # pending, verified, propagating, mismatch, failed
    current_nameservers: Optional[list[str]] = None
    expected_nameservers: list[str] = DNSIMPLE_NAMESERVERS
    registrar: Optional[str] = None
    error: Optional[str] = None


class VerifyNameserversResponse(BaseModel):
    """Response from nameserver verification."""
    results: list[NameserverVerificationResult]
    verified_count: int
    mismatch_count: int
    failed_count: int
    propagating_count: int = 0


@router.post("/verify-nameservers", response_model=VerifyNameserversResponse)
async def verify_nameservers(request: VerifyNameserversRequest):
    """
    Verify that nameservers are correctly set at the registrar.

    Checks both Porkbun and Dynadot to find which registrar owns each domain,
    then verifies the nameservers match the expected DNSimple nameservers.

    Status values:
    - verified: Nameservers match DNSimple requirements
    - propagating: NS were recently set, waiting for DNS propagation (up to 48h)
    - mismatch: Domain found but nameservers don't match (and >48h since last set)
    - failed: Could not retrieve nameserver info from any registrar
    """
    from datetime import datetime, timezone, timedelta

    porkbun = PorkbunService()
    dynadot = DynadotService()

    results = []
    verified_count = 0
    mismatch_count = 0
    failed_count = 0
    propagating_count = 0

    # Normalize expected nameservers for comparison (lowercase, sorted)
    expected_ns_set = set(ns.lower() for ns in DNSIMPLE_NAMESERVERS)

    # DNS propagation window (48 hours)
    PROPAGATION_HOURS = 48

    try:
        for domain_name in request.domain_names:
            current_ns = None
            registrar = None
            error = None

            # Get domain's nameservers_updated_at to check propagation window
            domain_record = await fetch_one("""
                SELECT nameservers_updated_at FROM domains WHERE domain_name = $1
            """, domain_name)
            ns_updated_at = domain_record.get("nameservers_updated_at") if domain_record else None

            # Check if we're within propagation window
            within_propagation_window = False
            if ns_updated_at:
                if isinstance(ns_updated_at, datetime):
                    # Make sure both are timezone-aware for comparison
                    now = datetime.now(timezone.utc)
                    if ns_updated_at.tzinfo is None:
                        ns_updated_at = ns_updated_at.replace(tzinfo=timezone.utc)
                    hours_since_update = (now - ns_updated_at).total_seconds() / 3600
                    within_propagation_window = hours_since_update < PROPAGATION_HOURS

            # Try Porkbun first
            try:
                ns_list = await porkbun.get_nameservers(domain_name)
                if ns_list:
                    current_ns = ns_list
                    registrar = "porkbun"
            except Exception as e:
                logger.debug(f"Porkbun NS lookup failed for {domain_name}: {e}")

            # Try Dynadot if Porkbun didn't work
            if current_ns is None:
                try:
                    ns_list = await dynadot.get_nameservers(domain_name)
                    if ns_list:
                        current_ns = ns_list
                        registrar = "dynadot"
                except Exception as e:
                    logger.debug(f"Dynadot NS lookup failed for {domain_name}: {e}")

            # Determine status
            if current_ns is None:
                # If we recently set NS but can't verify yet, it's propagating
                if within_propagation_window:
                    status = "propagating"
                    propagating_count += 1
                else:
                    status = "failed"
                    error = "Could not retrieve nameservers from any registrar"
                    failed_count += 1
            else:
                # Normalize current nameservers for comparison
                current_ns_set = set(ns.lower() for ns in current_ns)

                # Check if expected nameservers are a subset of current
                # (registrar may return additional NS entries)
                if expected_ns_set.issubset(current_ns_set) or current_ns_set == expected_ns_set:
                    status = "verified"
                    verified_count += 1
                else:
                    # If we recently set NS, consider it propagating not mismatch
                    if within_propagation_window:
                        status = "propagating"
                        propagating_count += 1
                    else:
                        status = "mismatch"
                        mismatch_count += 1

            # Update database with verification results
            await execute("""
                UPDATE domains
                SET nameserver_status = $1,
                    nameserver_verified_at = NOW(),
                    current_nameservers = $2,
                    selected_provider = COALESCE($3, selected_provider),
                    updated_at = NOW()
                WHERE domain_name = $4
            """, status, current_ns, registrar, domain_name)

            results.append(NameserverVerificationResult(
                domain=domain_name,
                status=status,
                current_nameservers=current_ns,
                expected_nameservers=DNSIMPLE_NAMESERVERS,
                registrar=registrar,
                error=error,
            ))

            logger.info(f"NS verification for {domain_name}: {status} "
                       f"(registrar={registrar}, ns={current_ns})")

        return VerifyNameserversResponse(
            results=results,
            verified_count=verified_count,
            mismatch_count=mismatch_count,
            failed_count=failed_count,
            propagating_count=propagating_count,
        )

    finally:
        await porkbun.close()
        await dynadot.close()


@router.get("/nameserver-status/{domain_name}")
async def get_nameserver_status(domain_name: str):
    """
    Get the current nameserver status for a domain.

    Returns verification status, current nameservers, and DNS readiness.
    """
    domain = await fetch_one("""
        SELECT
            domain_name,
            selected_provider,
            nameservers_updated_at,
            nameserver_status,
            nameserver_verified_at,
            current_nameservers
        FROM domains
        WHERE domain_name = $1
    """, domain_name)

    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Calculate DNS readiness
    dns_ready = False
    hours_until_ready = None

    if domain["nameservers_updated_at"]:
        from datetime import datetime, timezone
        ns_date = domain["nameservers_updated_at"]
        if ns_date.tzinfo is None:
            ns_date = ns_date.replace(tzinfo=timezone.utc)
        hours_since = (datetime.now(timezone.utc) - ns_date).total_seconds() / 3600
        dns_ready = hours_since >= 24
        hours_until_ready = max(0, 24 - hours_since) if not dns_ready else 0

    return {
        "domain": domain["domain_name"],
        "registrar": domain["selected_provider"],
        "nameserver_status": domain["nameserver_status"] or "pending",
        "current_nameservers": domain["current_nameservers"],
        "expected_nameservers": DNSIMPLE_NAMESERVERS,
        "nameservers_updated_at": domain["nameservers_updated_at"],
        "nameserver_verified_at": domain["nameserver_verified_at"],
        "dns_ready": dns_ready,
        "hours_until_ready": round(hours_until_ready, 1) if hours_until_ready is not None else 0,
    }


class SetNameserversRequest(BaseModel):
    """Request to set nameservers for domains."""
    domain_names: list[str]


class SetNameserverResult(BaseModel):
    """Result from setting nameservers for a single domain."""
    domain: str
    success: bool
    registrar: Optional[str] = None
    new_nameservers: Optional[list[str]] = None
    verified: bool = False
    error: Optional[str] = None


class SetNameserversResponse(BaseModel):
    """Response from setting nameservers."""
    results: list[SetNameserverResult]
    success_count: int
    failed_count: int
    verified_count: int


@router.post("/set-nameservers", response_model=SetNameserversResponse)
async def set_nameservers(request: SetNameserversRequest):
    """
    Set nameservers to DNSimple for the specified domains.

    This endpoint:
    1. Detects which registrar owns each domain (Porkbun or Dynadot)
    2. Sets the nameservers to DNSimple's nameservers
    3. Verifies the change was applied
    4. Updates the database with the new status

    Use this when:
    - Initial nameserver setup failed during purchase
    - Nameservers show as "mismatch" or "failed"
    - You need to manually fix DNS configuration
    """
    porkbun = PorkbunService()
    dynadot = DynadotService()

    results = []
    success_count = 0
    failed_count = 0
    verified_count = 0

    try:
        for domain_name in request.domain_names:
            registrar = None
            success = False
            verified = False
            error = None
            new_nameservers = None

            # Try to detect registrar via get_nameservers first
            # Note: get_nameservers returns [] for parked domains (exists but no NS)
            # and None for domains not in the account
            try:
                ns_list = await porkbun.get_nameservers(domain_name)
                if ns_list is not None:  # Domain exists in Porkbun (even if empty/parked)
                    registrar = "porkbun"
                    logger.info(f"{domain_name} found in Porkbun (NS: {ns_list})")
            except Exception as e:
                logger.debug(f"Porkbun lookup failed for {domain_name}: {e}")

            if registrar is None:
                try:
                    ns_list = await dynadot.get_nameservers(domain_name)
                    if ns_list is not None:  # Domain exists in Dynadot (even if empty/parked)
                        registrar = "dynadot"
                        logger.info(f"{domain_name} found in Dynadot (NS: {ns_list})")
                except Exception as e:
                    logger.debug(f"Dynadot lookup failed for {domain_name}: {e}")

            # If no registrar detected (parked domain with no NS), try setting directly
            # The registrar that owns the domain will accept the set command
            if registrar is None:
                logger.info(f"No NS found for {domain_name}, trying to set directly on each registrar")

                # Try Porkbun first
                try:
                    porkbun_success = await porkbun.set_nameservers(domain_name, DNSIMPLE_NAMESERVERS)
                    if porkbun_success:
                        registrar = "porkbun"
                        success = True
                        logger.info(f"Successfully set NS for {domain_name} via Porkbun")
                except Exception as e:
                    logger.debug(f"Porkbun set_ns failed for {domain_name}: {e}")

                # Try Dynadot if Porkbun didn't work
                if registrar is None:
                    try:
                        dynadot_success = await dynadot.set_nameservers(domain_name, DNSIMPLE_NAMESERVERS)
                        if dynadot_success:
                            registrar = "dynadot"
                            success = True
                            logger.info(f"Successfully set NS for {domain_name} via Dynadot")
                    except Exception as e:
                        logger.debug(f"Dynadot set_ns failed for {domain_name}: {e}")

            if registrar is None:
                error = "Domain not found in Porkbun or Dynadot"
                failed_count += 1
                results.append(SetNameserverResult(
                    domain=domain_name,
                    success=False,
                    error=error,
                ))
                continue

            # Set nameservers if not already set above (detected via get_nameservers)
            if not success:
                try:
                    if registrar == "porkbun":
                        success = await porkbun.set_nameservers(domain_name, DNSIMPLE_NAMESERVERS)
                    else:  # dynadot
                        success = await dynadot.set_nameservers(domain_name, DNSIMPLE_NAMESERVERS)

                    if not success:
                        error = f"Failed to set nameservers at {registrar}"
                except Exception as e:
                    error = str(e)
                    success = False

            if success:
                success_count += 1
                new_nameservers = DNSIMPLE_NAMESERVERS

                # Verify the change by re-reading nameservers
                await asyncio.sleep(1)  # Brief delay for registrar to process
                try:
                    if registrar == "porkbun":
                        current_ns = await porkbun.get_nameservers(domain_name)
                    else:
                        current_ns = await dynadot.get_nameservers(domain_name)

                    if current_ns:
                        current_ns_set = set(ns.lower() for ns in current_ns)
                        expected_ns_set = set(ns.lower() for ns in DNSIMPLE_NAMESERVERS)
                        if expected_ns_set.issubset(current_ns_set) or current_ns_set == expected_ns_set:
                            verified = True
                            verified_count += 1
                            new_nameservers = current_ns
                except Exception as e:
                    logger.debug(f"Verification read failed for {domain_name}: {e}")

                # Update database
                # Use "propagating" when NS set but not verified yet (DNS propagation takes 24-48h)
                status = "verified" if verified else "propagating"
                await execute("""
                    UPDATE domains
                    SET nameserver_status = $1,
                        nameservers_updated_at = NOW(),
                        current_nameservers = $2,
                        selected_provider = $3,
                        updated_at = NOW()
                    WHERE domain_name = $4
                """, status, new_nameservers, registrar, domain_name)

                logger.info(f"Set nameservers for {domain_name} at {registrar}: "
                           f"success={success}, verified={verified}")
            else:
                failed_count += 1
                # Update database with failed status
                await execute("""
                    UPDATE domains
                    SET nameserver_status = 'failed',
                        selected_provider = COALESCE($1, selected_provider),
                        updated_at = NOW()
                    WHERE domain_name = $2
                """, registrar, domain_name)

            results.append(SetNameserverResult(
                domain=domain_name,
                success=success,
                registrar=registrar,
                new_nameservers=new_nameservers,
                verified=verified,
                error=error,
            ))

    finally:
        await porkbun.close()
        await dynadot.close()

    return SetNameserversResponse(
        results=results,
        success_count=success_count,
        failed_count=failed_count,
        verified_count=verified_count,
    )


# =============================================================================
# BULK PRICE CHECKING
# =============================================================================

class BulkPriceCheckRequest(BaseModel):
    """Request to check prices for multiple domains."""
    client_id: Optional[UUID] = None  # If provided, check all pending/approved domains for this client
    domain_ids: Optional[list[UUID]] = None  # Or specify exact domain IDs
    job_id: Optional[UUID] = None  # If provided, check only domains from this generation job


class BulkPriceCheckResult(BaseModel):
    """Result for a single domain price check."""
    domain_id: str
    domain_name: str
    porkbun_available: Optional[bool] = None
    porkbun_price: Optional[str] = None
    dynadot_available: Optional[bool] = None
    dynadot_price: Optional[str] = None
    best_price: Optional[str] = None
    best_provider: Optional[str] = None
    error: Optional[str] = None


class BulkPriceCheckResponse(BaseModel):
    """Response from bulk price check."""
    results: list[BulkPriceCheckResult]
    checked_count: int
    available_count: int
    error_count: int


@router.post("/check-prices-bulk", response_model=BulkPriceCheckResponse)
async def check_prices_bulk(request: BulkPriceCheckRequest):
    """
    Check prices for multiple domains from both Porkbun and Dynadot.

    This endpoint:
    1. Checks availability and pricing from both registrars
    2. Stores results in domain_price_history table
    3. Updates cached_price in domains table

    Args:
        client_id: Check all pending/approved domains for this client
        domain_ids: Or specify exact domain IDs to check
        job_id: If provided, check only domains from this generation job

    Returns:
        Price information for each domain
    """
    # Get domains to check
    if request.domain_ids:
        domains = await fetch_all("""
            SELECT id, domain_name, workspace_id, approval_status
            FROM domains
            WHERE id = ANY($1)
        """, request.domain_ids)
    elif request.job_id:
        # Get domains generated by this specific job
        domains = await fetch_all("""
            SELECT id, domain_name, workspace_id, approval_status
            FROM domains
            WHERE job_id = $1
            AND approval_status = 'available'
        """, request.job_id)
    elif request.client_id:
        # Get workspace_id from client
        client = await fetch_one("SELECT workspace_id FROM clients WHERE id = $1", request.client_id)
        if not client or not client["workspace_id"]:
            raise HTTPException(status_code=404, detail="Client not found or has no workspace")

        # Get all available domains for this client
        domains = await fetch_all("""
            SELECT id, domain_name, workspace_id, approval_status
            FROM domains
            WHERE workspace_id = $1
            AND approval_status = 'available'
        """, client["workspace_id"])
    else:
        raise HTTPException(status_code=400, detail="Provide either client_id, domain_ids, or job_id")

    if not domains:
        return BulkPriceCheckResponse(
            results=[],
            checked_count=0,
            available_count=0,
            error_count=0,
        )

    porkbun = PorkbunService()
    dynadot = DynadotService()

    results = []
    checked_count = 0
    available_count = 0
    error_count = 0

    try:
        for domain in domains:
            domain_id = domain["id"]
            domain_name = domain["domain_name"]

            try:
                # Check both providers concurrently
                import asyncio
                porkbun_result, dynadot_result = await asyncio.gather(
                    porkbun.check_availability(domain_name),
                    dynadot.check_availability(domain_name),
                    return_exceptions=True
                )

                # Process Porkbun result
                porkbun_available = None
                porkbun_price = None
                if isinstance(porkbun_result, Exception):
                    logger.error(f"Porkbun API error for {domain_name}: {porkbun_result}")
                else:
                    porkbun_available = porkbun_result.available
                    if porkbun_result.available and porkbun_result.price is not None:
                        porkbun_price = float(porkbun_result.price)

                # Process Dynadot result
                dynadot_available = None
                dynadot_price = None
                if isinstance(dynadot_result, Exception):
                    logger.error(f"Dynadot API error for {domain_name}: {dynadot_result}")
                else:
                    dynadot_available = dynadot_result.available
                    if dynadot_result.available and dynadot_result.price is not None:
                        dynadot_price = float(dynadot_result.price)

                # Determine best price and provider
                best_price = None
                best_provider = None
                is_available = porkbun_available or dynadot_available

                if porkbun_price is not None and dynadot_price is not None:
                    if porkbun_price <= dynadot_price:
                        best_price = porkbun_price
                        best_provider = "porkbun"
                    else:
                        best_price = dynadot_price
                        best_provider = "dynadot"
                elif porkbun_price is not None:
                    best_price = porkbun_price
                    best_provider = "porkbun"
                elif dynadot_price is not None:
                    best_price = dynadot_price
                    best_provider = "dynadot"

                # Save to price history table
                await execute("""
                    INSERT INTO domain_price_history
                    (domain_id, porkbun_price, porkbun_available, dynadot_price, dynadot_available, best_price, best_provider)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, domain_id, porkbun_price, porkbun_available, dynadot_price, dynadot_available, best_price, best_provider)

                # Update cached price in domains table
                await execute("""
                    UPDATE domains
                    SET porkbun_price = $1,
                        porkbun_available = $2,
                        dynadot_price = $3,
                        dynadot_available = $4,
                        cached_price = $5,
                        selected_provider = $6,
                        price_checked_at = NOW()
                    WHERE id = $7
                """, porkbun_price, porkbun_available, dynadot_price, dynadot_available, best_price, best_provider, domain_id)

                checked_count += 1
                if is_available:
                    available_count += 1
                else:
                    # Auto-remove unavailable domains (already taken)
                    # Only remove 'available' status domains, keep purchased/active
                    await execute("""
                        DELETE FROM domains
                        WHERE id = $1 AND approval_status = 'available'
                    """, domain_id)
                    logger.info(f"Auto-removed unavailable domain: {domain_name}")

                results.append(BulkPriceCheckResult(
                    domain_id=str(domain_id),
                    domain_name=domain_name,
                    porkbun_available=porkbun_available,
                    porkbun_price=str(porkbun_price) if porkbun_price is not None else None,
                    dynadot_available=dynadot_available,
                    dynadot_price=str(dynadot_price) if dynadot_price is not None else None,
                    best_price=str(best_price) if best_price is not None else None,
                    best_provider=best_provider,
                ))

            except Exception as e:
                error_count += 1
                results.append(BulkPriceCheckResult(
                    domain_id=str(domain_id),
                    domain_name=domain_name,
                    error=str(e),
                ))

            # Rate limiting - brief delay between checks
            await asyncio.sleep(0.5)

    finally:
        await porkbun.close()
        await dynadot.close()

    return BulkPriceCheckResponse(
        results=results,
        checked_count=checked_count,
        available_count=available_count,
        error_count=error_count,
    )


@router.get("/price-history/{domain_id}")
async def get_price_history(domain_id: UUID, limit: int = 30):
    """
    Get price history for a single domain.

    Returns the last N price checks for the domain, useful for
    charting price trends over time.
    """
    history = await fetch_all("""
        SELECT
            porkbun_price,
            porkbun_available,
            dynadot_price,
            dynadot_available,
            best_price,
            best_provider,
            checked_at
        FROM domain_price_history
        WHERE domain_id = $1
        ORDER BY checked_at DESC
        LIMIT $2
    """, domain_id, limit)

    return {
        "domain_id": str(domain_id),
        "history": [
            {
                "porkbun_price": str(h["porkbun_price"]) if h["porkbun_price"] else None,
                "porkbun_available": h["porkbun_available"],
                "dynadot_price": str(h["dynadot_price"]) if h["dynadot_price"] else None,
                "dynadot_available": h["dynadot_available"],
                "best_price": str(h["best_price"]) if h["best_price"] else None,
                "best_provider": h["best_provider"],
                "checked_at": h["checked_at"].isoformat() if h["checked_at"] else None,
            }
            for h in history
        ],
        "count": len(history),
    }


# =============================================================================
# Domain Purchase Jobs (Worker Mode)
# =============================================================================

class CreateDomainPurchaseJobRequest(BaseModel):
    """Request to create a domain purchase job."""
    domain_ids: list[UUID] = Field(..., description="Domain IDs to purchase")
    registrar: str = Field(default="dynadot", description="Registrar: 'dynadot' or 'porkbun'")


class DomainPurchaseJobResponse(BaseModel):
    """Response from domain purchase job creation."""
    job_id: str
    client_id: str
    status: str
    domain_count: int
    registrar: str
    message: str


class DomainPurchaseJobStatusResponse(BaseModel):
    """Status of a domain purchase job."""
    job_id: str
    status: str  # pending, processing, completed, failed
    registrar: str
    domain_names: list[str]
    current_domain: Optional[str] = None
    successful_count: int
    failed_count: int
    total_cost: Optional[str] = None
    results: Optional[list] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@router.post("/purchase-jobs/create/{client_id}", response_model=DomainPurchaseJobResponse)
async def create_domain_purchase_job(client_id: UUID, request: CreateDomainPurchaseJobRequest):
    """
    Create a domain purchase job for the Hypertide worker.

    Instead of executing the purchase inline, this creates a job in the
    domain_purchase_jobs table that will be picked up by the hypertide_worker.

    This allows:
    - Non-blocking API response
    - Resilient job processing (survives API restarts)
    - Independent worker deployment

    Use GET /purchase-jobs/{job_id}/status to poll for completion.
    """
    if not request.domain_ids:
        raise HTTPException(status_code=400, detail="No domain IDs provided")

    if request.registrar not in ('dynadot', 'porkbun'):
        raise HTTPException(status_code=400, detail="Registrar must be 'dynadot' or 'porkbun'")

    # Get client workspace
    client = await fetch_one(
        "SELECT workspace_id FROM clients WHERE id = $1",
        client_id
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    workspace_id = client.get("workspace_id")

    # Verify domains exist and are available for purchase
    domain_names = []
    for domain_id in request.domain_ids:
        domain = await fetch_one("""
            SELECT domain_name, approval_status
            FROM domains
            WHERE id = $1
        """, domain_id)

        if not domain:
            raise HTTPException(status_code=404, detail=f"Domain {domain_id} not found")

        if domain["approval_status"] not in ("available", "approved", "pending"):
            raise HTTPException(
                status_code=400,
                detail=f"Domain {domain['domain_name']} is not available for purchase (status: {domain['approval_status']})"
            )

        domain_names.append(domain["domain_name"])

    # Create job
    job_id = await fetch_one("""
        INSERT INTO domain_purchase_jobs (
            client_id, workspace_id, domain_ids, domain_names, registrar, status
        ) VALUES ($1, $2, $3, $4, $5, 'pending')
        RETURNING id
    """, client_id, workspace_id, request.domain_ids, domain_names, request.registrar)

    logger.info(f"Created domain purchase job {job_id['id']} for {len(domain_names)} domains via {request.registrar}")

    return DomainPurchaseJobResponse(
        job_id=str(job_id['id']),
        client_id=str(client_id),
        status="pending",
        domain_count=len(domain_names),
        registrar=request.registrar,
        message=f"Job created. {len(domain_names)} domain(s) queued for purchase via {request.registrar}. Poll /purchase-jobs/{job_id['id']}/status for updates."
    )


@router.get("/purchase-jobs/{job_id}/status", response_model=DomainPurchaseJobStatusResponse)
async def get_domain_purchase_job_status(job_id: UUID):
    """
    Get the status of a domain purchase job.

    Poll this endpoint to track purchase progress and get results.
    """
    job = await fetch_one("""
        SELECT
            id, status, registrar, domain_names, current_domain,
            successful_count, failed_count, total_cost, results,
            error_message, created_at, started_at, completed_at
        FROM domain_purchase_jobs
        WHERE id = $1
    """, job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return DomainPurchaseJobStatusResponse(
        job_id=str(job["id"]),
        status=job["status"],
        registrar=job["registrar"],
        domain_names=job["domain_names"] or [],
        current_domain=job["current_domain"],
        successful_count=job["successful_count"] or 0,
        failed_count=job["failed_count"] or 0,
        total_cost=str(job["total_cost"]) if job["total_cost"] else None,
        results=job["results"],
        error_message=job["error_message"],
        created_at=job["created_at"].isoformat() if job["created_at"] else None,
        started_at=job["started_at"].isoformat() if job["started_at"] else None,
        completed_at=job["completed_at"].isoformat() if job["completed_at"] else None,
    )


@router.get("/purchase-jobs/client/{client_id}")
async def get_client_domain_purchase_jobs(client_id: UUID, limit: int = 10):
    """
    Get recent domain purchase jobs for a client.

    Returns the most recent jobs ordered by creation time.
    """
    jobs = await fetch_all("""
        SELECT
            id, status, registrar, domain_names, successful_count,
            failed_count, total_cost, error_message, created_at, completed_at
        FROM domain_purchase_jobs
        WHERE client_id = $1
        ORDER BY created_at DESC
        LIMIT $2
    """, client_id, limit)

    return {
        "jobs": [
            {
                "job_id": str(j["id"]),
                "status": j["status"],
                "registrar": j["registrar"],
                "domain_count": len(j["domain_names"]) if j["domain_names"] else 0,
                "successful_count": j["successful_count"] or 0,
                "failed_count": j["failed_count"] or 0,
                "total_cost": str(j["total_cost"]) if j["total_cost"] else None,
                "error_message": j["error_message"],
                "created_at": j["created_at"].isoformat() if j["created_at"] else None,
                "completed_at": j["completed_at"].isoformat() if j["completed_at"] else None,
            }
            for j in jobs
        ],
        "count": len(jobs),
    }