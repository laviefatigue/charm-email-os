"""
Domain search and variation engine.

Handles:
- Multi-registrar parallel search
- Domain name variation generation (fuzzy matching)
- Price comparison and deal detection
- Result ranking and scoring

Example:
    candidates = await generate_domain_candidates(request)
    results = await search_registrars(candidates, target_price=8.00)

    # Get best deals
    deals = [r for r in results if r.is_deal and r.best_price < 10]
"""

from typing import Optional
from datetime import datetime
from decimal import Decimal
import asyncio
import logging

from pydantic import BaseModel, Field

from .models import (
    DomainCandidate,
    DomainSearchResult,
    RegistrarResult,
    RegistrarType,
    DomainStatus,
)
from .registrars import Registrar, RegistrarFactory

logger = logging.getLogger(__name__)


class SearchConfig(BaseModel):
    """Configuration for domain search."""
    target_price: Decimal = Field(
        default=Decimal("8.00"),
        description="Target price threshold for 'deal' classification"
    )
    max_price: Decimal = Field(
        default=Decimal("15.00"),
        description="Maximum acceptable price"
    )
    include_variations: bool = Field(
        default=True,
        description="Generate and search domain variations"
    )
    max_variations_per_domain: int = Field(
        default=5,
        description="Max variations to generate per base domain"
    )
    concurrency: int = Field(
        default=10,
        description="Max concurrent registrar API calls"
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="Timeout for each registrar check"
    )


def generate_variations(base_name: str, tld: str, max_count: int = 5) -> list[tuple[str, str]]:
    """
    Generate variations of a domain name for fuzzy matching.

    Variations help find available alternatives when exact match
    is taken or expensive.

    Args:
        base_name: Domain name without TLD (e.g., "outreach-acme")
        tld: Original TLD (e.g., "com")
        max_count: Maximum variations to generate

    Returns:
        List of (name, tld) tuples

    Example:
        >>> variations = generate_variations("outreach-acme", "com", 5)
        >>> for name, ext in variations:
        ...     print(f"{name}.{ext}")
        outreach-acme.io
        outreach-acme.co
        getoutreach-acme.com
        outreachacme.com
        outreach-acmehq.com
    """
    variations = []

    # Alternative TLDs
    alt_tlds = ["io", "co", "ai", "app", "dev", "net"] if tld == "com" else ["com"]
    for alt in alt_tlds[:2]:
        if alt != tld:
            variations.append((base_name, alt))

    # Remove hyphen if present
    if "-" in base_name:
        no_hyphen = base_name.replace("-", "")
        variations.append((no_hyphen, tld))

    # Add hyphen if not present (between apparent words)
    if "-" not in base_name and len(base_name) > 6:
        # Try common split points
        for i in [4, 5, 6]:
            if i < len(base_name) - 2:
                hyphenated = f"{base_name[:i]}-{base_name[i:]}"
                variations.append((hyphenated, tld))
                break

    # Common prefixes
    prefixes = ["get", "try", "use", "go", "my"]
    for prefix in prefixes[:1]:  # Just one prefix variation
        if not base_name.startswith(prefix):
            variations.append((f"{prefix}{base_name}", tld))

    # Common suffixes
    suffixes = ["hq", "app", "io"]
    for suffix in suffixes[:1]:  # Just one suffix variation
        if not base_name.endswith(suffix):
            variations.append((f"{base_name}{suffix}", tld))

    # Dedupe and limit
    seen = set()
    unique = []
    for name, ext in variations:
        key = f"{name}.{ext}"
        if key not in seen:
            seen.add(key)
            unique.append((name, ext))

    return unique[:max_count]


def calculate_value_score(
    result: DomainSearchResult,
    target_price: Decimal,
    max_price: Decimal,
) -> float:
    """
    Calculate a value score for ranking search results.

    Score components:
    - Availability (required)
    - Price score (lower is better)
    - Legitimacy score from AI
    - Deal bonus (promotional pricing)

    Returns:
        Float score from 0.0 to 1.0 (higher is better)
    """
    if not result.is_available or result.best_price is None:
        return 0.0

    score = 0.0

    # Price score (0-0.4): Closer to target_price is better
    if result.best_price <= target_price:
        # Below target: full price score + bonus
        score += 0.4 + 0.1  # 0.5 total for great price
    elif result.best_price <= max_price:
        # Between target and max: proportional score
        price_ratio = float((max_price - result.best_price) / (max_price - target_price))
        score += 0.4 * price_ratio
    else:
        # Above max price: minimal score
        score += 0.05

    # Legitimacy score (0-0.3): From AI assessment
    score += 0.3 * result.candidate.legitimacy_score

    # Deal bonus (0-0.1): Extra for promotional pricing
    if result.is_deal:
        score += 0.1

    # TLD preference (0-0.1): .com preferred
    tld_scores = {"com": 0.1, "io": 0.08, "co": 0.06, "ai": 0.05}
    score += tld_scores.get(result.candidate.tld, 0.03)

    return min(score, 1.0)


async def search_single_domain(
    candidate: DomainCandidate,
    registrars: list[Registrar],
    config: SearchConfig,
) -> DomainSearchResult:
    """
    Search all registrars for a single domain.

    Args:
        candidate: Domain candidate to search
        registrars: List of registrar instances
        config: Search configuration

    Returns:
        DomainSearchResult with all registrar results
    """
    candidate.status = DomainStatus.SEARCHING

    # Search all registrars in parallel
    async def check_registrar(registrar: Registrar) -> RegistrarResult:
        try:
            return await asyncio.wait_for(
                registrar.check_availability(candidate.domain_name),
                timeout=config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Timeout checking {candidate.domain_name} on {registrar.registrar_type}"
            )
            return RegistrarResult(
                registrar=registrar.registrar_type,
                is_available=False,
                error="Timeout",
            )
        except Exception as e:
            logger.error(
                f"Error checking {candidate.domain_name} on {registrar.registrar_type}: {e}"
            )
            return RegistrarResult(
                registrar=registrar.registrar_type,
                is_available=False,
                error=str(e),
            )

    results = await asyncio.gather(*[
        check_registrar(r) for r in registrars
    ])

    # Update candidate with results
    candidate.registrar_results = list(results)

    # Determine overall status
    if candidate.is_available:
        candidate.status = DomainStatus.AVAILABLE
    else:
        candidate.status = DomainStatus.UNAVAILABLE

    # Create search result
    search_result = DomainSearchResult.from_candidate(candidate)

    # Calculate value score
    search_result.value_score = calculate_value_score(
        search_result,
        config.target_price,
        config.max_price,
    )

    return search_result


async def search_registrars(
    candidates: list[DomainCandidate],
    config: Optional[SearchConfig] = None,
    registrars: Optional[list[Registrar]] = None,
) -> list[DomainSearchResult]:
    """
    Search all registrars for domain candidates.

    This is the main search function that:
    1. Optionally generates variations for each candidate
    2. Searches all configured registrars in parallel
    3. Ranks results by value score
    4. Returns sorted list (best deals first)

    Args:
        candidates: List of domain candidates to search
        config: Search configuration (uses defaults if None)
        registrars: Optional list of registrar instances (creates from env if None)

    Returns:
        List of DomainSearchResult objects, sorted by value_score descending

    Example:
        >>> candidates = await generate_domain_candidates(request)
        >>> results = await search_registrars(candidates)
        >>> for r in results[:10]:
        ...     if r.is_available:
        ...         print(f"{r.candidate.domain_name}: ${r.best_price} ({r.best_registrar})")
    """
    if config is None:
        config = SearchConfig()

    # Create registrars if not provided
    if registrars is None:
        registrars = RegistrarFactory.create_all()
        if not registrars:
            logger.warning("No registrars configured - check API credentials")
            return []

    # Expand candidates with variations if enabled
    all_candidates = list(candidates)
    if config.include_variations:
        for candidate in candidates:
            variations = generate_variations(
                candidate.base_name,
                candidate.tld,
                config.max_variations_per_domain,
            )
            for name, tld in variations:
                variation_candidate = DomainCandidate(
                    request_id=candidate.request_id,
                    domain_name=f"{name}.{tld}",
                    base_name=name,
                    tld=tld,
                    generation_rationale=f"Variation of {candidate.domain_name}",
                    legitimacy_score=candidate.legitimacy_score * 0.9,  # Slightly lower
                    status=DomainStatus.GENERATED,
                )
                all_candidates.append(variation_candidate)

    logger.info(
        f"Searching {len(all_candidates)} domains across {len(registrars)} registrars"
    )

    # Search with concurrency limit
    semaphore = asyncio.Semaphore(config.concurrency)

    async def search_with_semaphore(candidate: DomainCandidate) -> DomainSearchResult:
        async with semaphore:
            return await search_single_domain(candidate, registrars, config)

    # Run all searches
    results = await asyncio.gather(*[
        search_with_semaphore(c) for c in all_candidates
    ])

    # Sort by value score (best first)
    sorted_results = sorted(results, key=lambda r: r.value_score, reverse=True)

    # Log summary
    available = [r for r in sorted_results if r.is_available]
    deals = [r for r in available if r.is_deal]
    under_target = [r for r in available if r.best_price and r.best_price <= config.target_price]

    logger.info(
        f"Search complete: {len(available)} available, "
        f"{len(deals)} deals, {len(under_target)} under ${config.target_price}"
    )

    return sorted_results


async def fuzzy_search(
    base_domain: str,
    target_price: Decimal = Decimal("8.00"),
    max_results: int = 20,
    registrars: Optional[list[Registrar]] = None,
) -> list[DomainSearchResult]:
    """
    Perform a fuzzy search for a single domain name.

    Generates variations and searches for best available options.
    Useful for quick searches when you have a specific name in mind.

    Args:
        base_domain: Full domain name (e.g., "outreach-acme.com")
        target_price: Target price for deals
        max_results: Maximum results to return
        registrars: Optional registrar instances

    Returns:
        Sorted list of available domain options

    Example:
        >>> results = await fuzzy_search("acme-growth.com", target_price=Decimal("10.00"))
        >>> for r in results[:5]:
        ...     print(f"{r.candidate.domain_name}: ${r.best_price}")
    """
    # Parse domain
    parts = base_domain.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid domain format: {base_domain}")

    base_name, tld = parts

    # Create a candidate for the original domain
    original = DomainCandidate(
        request_id="fuzzy-search",
        domain_name=base_domain,
        base_name=base_name,
        tld=tld,
        generation_rationale="Original search target",
        legitimacy_score=0.8,
        status=DomainStatus.GENERATED,
    )

    # Search with variations
    config = SearchConfig(
        target_price=target_price,
        include_variations=True,
        max_variations_per_domain=10,
    )

    results = await search_registrars([original], config, registrars)

    # Return only available results
    available = [r for r in results if r.is_available]
    return available[:max_results]


def filter_by_price(
    results: list[DomainSearchResult],
    max_price: Decimal,
    min_price: Optional[Decimal] = None,
) -> list[DomainSearchResult]:
    """
    Filter search results by price range.

    Args:
        results: List of search results
        max_price: Maximum price (inclusive)
        min_price: Optional minimum price

    Returns:
        Filtered list of results
    """
    filtered = []
    for r in results:
        if not r.is_available or r.best_price is None:
            continue
        if r.best_price > max_price:
            continue
        if min_price and r.best_price < min_price:
            continue
        filtered.append(r)
    return filtered


def group_by_registrar(
    results: list[DomainSearchResult],
) -> dict[RegistrarType, list[DomainSearchResult]]:
    """
    Group results by the registrar offering the best price.

    Useful for batch purchasing from a single registrar.

    Args:
        results: List of search results

    Returns:
        Dict mapping registrar type to results
    """
    groups: dict[RegistrarType, list[DomainSearchResult]] = {}

    for r in results:
        if r.is_available and r.best_registrar:
            if r.best_registrar not in groups:
                groups[r.best_registrar] = []
            groups[r.best_registrar].append(r)

    return groups
