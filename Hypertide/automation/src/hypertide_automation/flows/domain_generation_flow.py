"""
Prefect Flow: Domain Generation

Reads domain requests from Google Sheet, generates variations,
checks availability and pricing, populates Domains tab with quotes.

Flow Structure:
    1. Read "pending" requests from Requests tab
    2. Generate domain variations (AI or pattern-based)
    3. Check availability with configured registrars
    4. Get pricing for available domains
    5. Populate Domains tab with "quoted" status
    6. Update Request status to "completed"

Usage:
    # Run manually
    python -m hypertide_automation.flows.domain_generation_flow

    # Or via Prefect
    prefect deployment run domain-generation-flow/domain-generation-manual
"""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from prefect import flow, task, get_run_logger
from pydantic import BaseModel

from .sheets import SheetsClient
from ..domain_sourcing.generator import (
    generate_domain_candidates,
    generate_fallback_candidates,
    DomainGeneratorConfig,
)
from ..domain_sourcing.models import DomainRequest, TLDPreference
from ..domain_sourcing.registrars import (
    RegistrarFactory,
    Registrar,
    RegistrarError,
)


# ============================================================================
# Models
# ============================================================================

class DomainGenerationResult(BaseModel):
    """Result of domain generation flow."""
    requests_processed: int
    domains_generated: int
    domains_quoted: int
    errors: List[str]


# ============================================================================
# Tasks
# ============================================================================

@task(
    name="read-pending-requests",
    description="Read domain requests with status 'pending'",
    retries=2,
    retry_delay_seconds=5,
)
def read_pending_requests(sheet_id: str) -> List[Dict[str, Any]]:
    """Read pending domain requests from sheet using SheetsClient."""
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)
    requests = client.get_pending_requests()

    logger.info(f"Found {len(requests)} pending requests")
    return requests


@task(
    name="update-request-status",
    description="Update request status in sheet",
)
def update_request_status(
    sheet_id: str,
    row: int,
    status: str,
    processed_at: Optional[str] = None,
    notes: Optional[str] = None,
) -> bool:
    """Update a request's status using SheetsClient."""
    client = SheetsClient(sheet_id=sheet_id)
    return client.update_request_status(row=row, status=status, notes=notes)


@task(
    name="generate-domain-variations",
    description="Generate domain name variations from keyword",
)
async def generate_domain_variations(
    keyword: str,
    tld_preferences: str,
    use_ai: bool = False,
    count: int = 20,
) -> List[Dict[str, str]]:
    """
    Generate domain variations for a keyword.

    Args:
        keyword: Base keyword or brand name
        tld_preferences: Comma-separated TLDs (e.g., "com,io,co")
        use_ai: Use AI generation (requires API key)
        count: Number of variations to generate

    Returns:
        List of {name, tld, rationale} dicts
    """
    logger = get_run_logger()

    # Parse TLD preferences
    tlds = [t.strip().lstrip(".") for t in tld_preferences.split(",")]
    tld_prefs = [TLDPreference(tld=t, priority=i+1) for i, t in enumerate(tlds[:5])]

    # Build request
    request = DomainRequest(
        client_name=keyword,
        industry="general",
        brand_keywords=[keyword],
        preferred_tlds=tld_prefs,
        required_entra_domains=count // 2,
        required_google_domains=count // 4,
    )

    try:
        if use_ai:
            # Try AI generation
            config = DomainGeneratorConfig(
                model="gpt-4",
                provider="openai",
                temperature=0.8,
            )
            candidates = await generate_domain_candidates(request, config)
        else:
            # Use fallback pattern-based generation
            candidates = generate_fallback_candidates(request)

        # Convert to simple dicts
        variations = []
        for c in candidates:
            variations.append({
                "name": c.base_name,
                "tld": c.tld,
                "domain": c.domain_name,
                "rationale": c.generation_rationale or "",
            })

        logger.info(f"Generated {len(variations)} variations for '{keyword}'")
        return variations

    except Exception as e:
        logger.warning(f"AI generation failed, using fallback: {e}")
        candidates = generate_fallback_candidates(request)
        return [
            {
                "name": c.base_name,
                "tld": c.tld,
                "domain": c.domain_name,
                "rationale": c.generation_rationale or "",
            }
            for c in candidates
        ]


@task(
    name="check-availability-and-price",
    description="Check domain availability and get pricing from registrars",
    timeout_seconds=300,
)
async def check_availability_and_price(
    domains: List[Dict[str, str]],
    preferred_registrars: List[str] = None,
) -> List[Dict[str, Any]]:
    """
    Check domain availability and pricing across registrars.

    Args:
        domains: List of {name, tld, domain} dicts
        preferred_registrars: List of registrar names to use

    Returns:
        List of availability results with pricing
    """
    logger = get_run_logger()

    results = []

    # Get configured registrars
    try:
        registrars = RegistrarFactory.create_all()
        if not registrars:
            logger.warning("No registrars configured, using placeholder prices")
            # Return placeholder results
            for domain in domains:
                results.append({
                    "domain": domain["domain"],
                    "tld": domain["tld"],
                    "registrar": "unknown",
                    "available": True,  # Assume available
                    "price": "12.00",
                    "renewal_price": "15.00",
                    "rationale": domain.get("rationale", ""),
                })
            return results

        logger.info(f"Using {len(registrars)} registrar(s) for availability check")

    except Exception as e:
        logger.warning(f"Could not initialize registrars: {e}")
        # Return placeholder results
        for domain in domains:
            results.append({
                "domain": domain["domain"],
                "tld": domain["tld"],
                "registrar": "unknown",
                "available": True,
                "price": "12.00",
                "renewal_price": "15.00",
                "rationale": domain.get("rationale", ""),
            })
        return results

    # Check each domain with first available registrar
    for domain in domains:
        domain_name = domain["domain"]
        best_result = None

        for registrar in registrars:
            try:
                async with registrar:
                    result = await registrar.check_availability(domain_name)

                    if result.is_available:
                        # Found available - record price
                        best_result = {
                            "domain": domain_name,
                            "tld": domain["tld"],
                            "registrar": result.registrar.value,
                            "available": True,
                            "price": str(result.registration_price or "0"),
                            "renewal_price": str(result.renewal_price or "0"),
                            "is_promo": result.is_promotional,
                            "rationale": domain.get("rationale", ""),
                        }
                        break  # Use first registrar with availability
                    else:
                        if best_result is None:
                            best_result = {
                                "domain": domain_name,
                                "tld": domain["tld"],
                                "registrar": result.registrar.value,
                                "available": False,
                                "price": "0",
                                "renewal_price": "0",
                                "rationale": domain.get("rationale", ""),
                                "error": result.error or "Not available",
                            }

            except Exception as e:
                logger.warning(f"Registrar check failed for {domain_name}: {e}")
                continue

        if best_result:
            results.append(best_result)
        else:
            # No registrar could check this domain
            results.append({
                "domain": domain_name,
                "tld": domain["tld"],
                "registrar": "error",
                "available": False,
                "price": "0",
                "renewal_price": "0",
                "rationale": domain.get("rationale", ""),
                "error": "Could not check availability",
            })

        # Small delay between checks to avoid rate limiting
        await asyncio.sleep(0.5)

    available_count = sum(1 for r in results if r["available"])
    logger.info(f"Checked {len(results)} domains, {available_count} available")

    return results


@task(
    name="add-domains-to-sheet",
    description="Add quoted domains to Domains tab",
)
def add_domains_to_sheet(
    sheet_id: str,
    domains: List[Dict[str, Any]],
    provider: str,
    max_price: float,
) -> int:
    """
    Add domains to the Domains tab with quoted status.

    Args:
        sheet_id: Google Sheet ID
        domains: List of domain availability results
        provider: Provider type (entra/google)
        max_price: Max price threshold for auto-suggestion

    Returns:
        Number of domains added
    """
    logger = get_run_logger()

    client = SheetsClient(sheet_id=sheet_id)

    # Parse max price
    try:
        max_price_value = float(max_price) if max_price else 15.00
    except (ValueError, TypeError):
        max_price_value = 15.00

    # Build domain list for SheetsClient.add_domains()
    domains_to_add = []
    for domain in domains:
        if not domain.get("available", False):
            continue  # Skip unavailable domains

        try:
            price = float(domain.get("price", 0) or 0)
            renewal_price = float(domain.get("renewal_price", 0) or 0)
        except (ValueError, TypeError):
            price = 0.0
            renewal_price = 0.0

        # Determine initial status based on price
        if price <= max_price_value:
            status = "suggested"  # Under budget, suggest for approval
        else:
            status = "quoted"  # Over budget, needs review

        domains_to_add.append({
            "domain": domain["domain"],
            "tld": domain["tld"],
            "registrar": domain.get("registrar", ""),
            "price": price,
            "renewal_price": renewal_price,
            "available": True,
            "provider": provider,
            "status": status,
        })

    added = client.add_domains(domains_to_add)
    logger.info(f"Added {added} domains to sheet")

    return added


# ============================================================================
# Main Flow
# ============================================================================

@flow(
    name="domain-generation-flow",
    description="Generate domain variations and get pricing quotes",
    version="1.0.0",
)
async def domain_generation_flow(
    sheet_id: str,
    use_ai: bool = False,
    variations_per_request: int = 20,
) -> DomainGenerationResult:
    """
    Main flow: Generate domains and get quotes from requests.

    Process:
        1. Read pending requests from Requests tab
        2. For each request:
           - Generate domain variations
           - Check availability with registrars
           - Get pricing quotes
           - Add to Domains tab with "quoted" status
        3. Update request status to "completed"

    Args:
        sheet_id: Google Sheet ID
        use_ai: Use AI for domain generation (requires OpenAI key)
        variations_per_request: Number of variations to generate per keyword

    Returns:
        DomainGenerationResult with summary
    """
    logger = get_run_logger()
    logger.info(f"Starting domain generation flow (sheet: {sheet_id})")

    errors = []
    total_generated = 0
    total_quoted = 0

    # Read pending requests
    requests = read_pending_requests(sheet_id)

    if not requests:
        logger.info("No pending requests to process")
        return DomainGenerationResult(
            requests_processed=0,
            domains_generated=0,
            domains_quoted=0,
            errors=[],
        )

    # Process each request
    for request in requests:
        keyword = request["keyword"]
        logger.info(f"Processing request: {keyword}")

        # Mark as processing
        update_request_status(sheet_id, request["row"], "processing")

        try:
            # Generate variations
            variations = await generate_domain_variations(
                keyword=keyword,
                tld_preferences=request["tld_preferences"],
                use_ai=use_ai,
                count=variations_per_request,
            )
            total_generated += len(variations)

            # Check availability and pricing
            results = await check_availability_and_price(variations)

            # Add to Domains tab (max_price is float or None from SheetsClient)
            added = add_domains_to_sheet(
                sheet_id=sheet_id,
                domains=results,
                provider=request["provider"],
                max_price=request["max_price"] or 15.00,
            )
            total_quoted += added

            # Mark request as completed with notes about results
            notes = f"Generated {len(variations)} variations, {added} available"
            update_request_status(
                sheet_id,
                request["row"],
                "completed",
                notes=notes,
            )

        except Exception as e:
            error = f"Failed to process '{keyword}': {e}"
            logger.error(error)
            errors.append(error)

            # Mark as failed with error message
            update_request_status(sheet_id, request["row"], "failed", notes=str(e))

    logger.info(
        f"Flow complete: {len(requests)} requests, "
        f"{total_generated} generated, {total_quoted} quoted"
    )

    return DomainGenerationResult(
        requests_processed=len(requests),
        domains_generated=total_generated,
        domains_quoted=total_quoted,
        errors=errors,
    )


# ============================================================================
# Entry Point
# ============================================================================

def main():
    """Run the flow manually."""
    import os

    sheet_id = os.getenv("HYPERTIDE_SHEET_ID")
    if not sheet_id:
        print("Error: HYPERTIDE_SHEET_ID environment variable required")
        return 1

    result = asyncio.run(domain_generation_flow(
        sheet_id=sheet_id,
        use_ai=False,  # Default to pattern-based
        variations_per_request=15,
    ))

    print(f"\nResults:")
    print(f"  Requests processed: {result.requests_processed}")
    print(f"  Domains generated: {result.domains_generated}")
    print(f"  Domains quoted: {result.domains_quoted}")

    if result.errors:
        print(f"\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    return 0 if not result.errors else 1


if __name__ == "__main__":
    exit(main())
