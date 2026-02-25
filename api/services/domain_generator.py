"""
Pattern-based domain suggestion generator.

Generates domain suggestions without requiring AI or Hypertide.
Uses deterministic patterns based on brand keywords.
"""

import random
from typing import Optional
from pydantic import BaseModel


class DomainSuggestion(BaseModel):
    """A generated domain suggestion."""
    domain: str
    pattern: str  # "prefix", "suffix", or "pure"
    rationale: str
    legitimacy_score: float = 0.8  # Default score for pattern-based


# Common prefixes that work well for business domains
PREFIXES = [
    "try",      # tryselery.com - "Try our product"
    "get",      # getselery.com - "Get started"
    "use",      # useselery.com - "Use our service"
    "go",       # goselery.com - "Go with us"
    "hire",     # hireselery.com - Good for B2B
    "meet",     # meetselery.com - Professional
    "join",     # joinselery.com - Community feel
    "with",     # withselery.com - Partnership feel
    "hey",      # heyselery.com - Friendly
    "run",      # runselery.com - Action-oriented
]

# Common suffixes that create professional domains
SUFFIXES = [
    "hq",       # seleryhq.com - Headquarters
    "app",      # seleryapp.com - Application/SaaS
    "hub",      # seleryhub.com - Central hub
    "team",     # seleryteam.com - Team focused
    "mail",     # selerymail.com - Email specific
    "inbox",    # seleryinbox.com - Email specific
    "send",     # selerysend.com - Email specific
    "reach",    # seleryreach.com - Outreach
    "now",      # selerynow.com - Urgency
    "pro",      # selerypro.com - Professional
]

# TLDs ordered by preference (balance of cost and legitimacy)
DEFAULT_TLDS = [".com", ".io", ".co", ".ai", ".email"]


def generate_domain_suggestions(
    brand_keyword: str,
    count: int = 10,
    tlds: Optional[list[str]] = None,
    include_pure: bool = True,
    shuffle: bool = True,
) -> list[DomainSuggestion]:
    """
    Generate domain suggestions for a brand.

    Args:
        brand_keyword: The brand name (e.g., "selery")
        count: Number of suggestions to return (default 10)
        tlds: List of TLDs to use (default: [".com", ".io", ".co"])
        include_pure: Include pure brand domains (e.g., "selery.com")
        shuffle: Randomize order before returning

    Returns:
        List of DomainSuggestion objects

    Examples for brand="selery":
        - tryselery.com (prefix)
        - getselery.io (prefix)
        - seleryhq.com (suffix)
        - selerymail.io (suffix)
        - selery.com (pure)
    """
    # Clean and normalize brand keyword
    brand = brand_keyword.lower().strip()
    brand = "".join(c for c in brand if c.isalnum())

    if not brand:
        return []

    # Use provided TLDs or defaults
    selected_tlds = tlds or DEFAULT_TLDS[:3]

    suggestions = []

    # Pattern 1: prefix + brand
    for prefix in PREFIXES:
        for tld in selected_tlds:
            domain = f"{prefix}{brand}{tld}"
            suggestions.append(DomainSuggestion(
                domain=domain,
                pattern="prefix",
                rationale=f"Action-oriented: '{prefix}' invites engagement",
                legitimacy_score=0.85,
            ))

    # Pattern 2: brand + suffix
    for suffix in SUFFIXES:
        for tld in selected_tlds:
            domain = f"{brand}{suffix}{tld}"
            suggestions.append(DomainSuggestion(
                domain=domain,
                pattern="suffix",
                rationale=f"Professional: '{suffix}' adds business context",
                legitimacy_score=0.80,
            ))

    # Pattern 3: pure brand (highest legitimacy)
    if include_pure:
        for tld in (tlds or DEFAULT_TLDS):
            domain = f"{brand}{tld}"
            suggestions.append(DomainSuggestion(
                domain=domain,
                pattern="pure",
                rationale="Direct brand match - most memorable",
                legitimacy_score=0.95,
            ))

    # Deduplicate
    seen = set()
    unique = []
    for s in suggestions:
        if s.domain not in seen:
            seen.add(s.domain)
            unique.append(s)

    # Shuffle for variety (if requested)
    if shuffle:
        random.shuffle(unique)

    # Return top N suggestions
    return unique[:count]


def generate_from_keywords(
    keywords: list[str],
    count: int = 10,
    tlds: Optional[list[str]] = None,
) -> list[DomainSuggestion]:
    """
    Generate domain suggestions from multiple keywords.

    Useful when you have brand name plus industry keywords.

    Args:
        keywords: List of keywords (first is primary brand)
        count: Number of suggestions to return
        tlds: List of TLDs to use

    Returns:
        List of DomainSuggestion objects

    Example:
        keywords=["selery", "fulfillment", "shipping"]
        -> tryselery.com, seleryfulfillment.io, ...
    """
    if not keywords:
        return []

    suggestions = []

    # Use first keyword as primary brand
    brand = keywords[0].lower().strip()
    brand = "".join(c for c in brand if c.isalnum())

    # Generate standard suggestions for primary brand
    suggestions.extend(generate_domain_suggestions(brand, count=count * 2, tlds=tlds))

    # Add combinations with secondary keywords
    for keyword in keywords[1:4]:  # Up to 3 additional keywords
        kw = keyword.lower().strip()
        kw = "".join(c for c in kw if c.isalnum())
        if not kw or len(kw) < 3:
            continue

        selected_tlds = tlds or DEFAULT_TLDS[:2]
        for tld in selected_tlds:
            # brand + keyword
            domain = f"{brand}{kw}{tld}"
            suggestions.append(DomainSuggestion(
                domain=domain,
                pattern="compound",
                rationale=f"Brand + keyword: combines identity with '{kw}'",
                legitimacy_score=0.75,
            ))

    # Deduplicate and return
    seen = set()
    unique = []
    for s in suggestions:
        if s.domain not in seen:
            seen.add(s.domain)
            unique.append(s)

    random.shuffle(unique)
    return unique[:count]
