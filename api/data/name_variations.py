"""
Name variation generation for sender email prefixes.

Generates up to 52 unique email prefix variations from a single base name.
Used for Hypertide inbox provisioning where clients provide 1-2 real identities
but need many unique email prefixes.

Provider-specific usage:
- Entra (Microsoft): Up to 52 inboxes per domain
- Google: Up to 10 inboxes per domain

Usage:
    from data.name_variations import generate_variations, get_patterns_for_provider

Example:
    Base name: Chris Booth
    Entra (52): chris, chris.booth, cbooth, chrisbooth, ... (all 52 patterns)
    Google (10): chris.booth, chris, c.booth, chrisbooth, chris.b, ...
"""

from typing import Optional


# =============================================================================
# 52 Pattern Templates
# =============================================================================
# Extracted from production domain usehirecharm.com
# Template variables:
#   {first} = full first name (lowercase)
#   {last}  = full last name (lowercase)
#   {f}     = first letter of first name
#   {l}     = first letter of last name

PATTERN_TEMPLATES_52 = {
    # GROUP 1: Basic Formats (13 patterns)
    "firstname": "{first}",                          # chris
    "firstname.lastname": "{first}.{last}",          # chris.booth
    "firstname_lastname": "{first}_{last}",          # chris_booth
    "firstname-lastname": "{first}-{last}",          # chris-booth
    "firstnamelastname": "{first}{last}",            # chrisbooth
    "f.lastname": "{f}.{last}",                      # c.booth
    "f_lastname": "{f}_{last}",                      # c_booth
    "f-lastname": "{f}-{last}",                      # c-booth
    "flastname": "{f}{last}",                        # cbooth
    "firstname.l": "{first}.{l}",                    # chris.b
    "firstname_l": "{first}_{l}",                    # chris_b
    "firstname-l": "{first}-{l}",                    # chris-b
    "firstnamel": "{first}{l}",                      # chrisb

    # GROUP 2: Lastname-First Formats (5 patterns)
    "lastname": "{last}",                            # booth
    "lastname.f": "{last}.{f}",                      # booth.c
    "lastname_f": "{last}_{f}",                      # booth_c
    "lastname-f": "{last}-{f}",                      # booth-c
    "lastnamef": "{last}{f}",                        # boothc

    # GROUP 3: First + First Initial Variations (8 patterns)
    "firstnamef": "{first}{f}",                      # chrisc
    "firstname.f": "{first}.{f}",                    # chris.c
    "firstname_f": "{first}_{f}",                    # chris_c
    "firstname-f": "{first}-{f}",                    # chris-c
    "firstnamefl": "{first}{f}{l}",                  # chriscb
    "firstname.fl": "{first}.{f}{l}",                # chris.cb
    "firstname_fl": "{first}_{f}{l}",                # chris_cb
    "firstname-fl": "{first}-{f}{l}",                # chris-cb

    # GROUP 4: First + Double Last Initial (4 patterns)
    "firstnamell": "{first}{l}{l}",                  # chrisbb
    "firstname.ll": "{first}.{l}{l}",                # chris.bb
    "firstname_ll": "{first}_{l}{l}",                # chris_bb
    "firstname-ll": "{first}-{l}{l}",                # chris-bb

    # GROUP 5: Full Combo + Last Initial (8 patterns)
    "firstnamelastname.l": "{first}{last}.{l}",      # chrisbooth.b
    "firstnamelastname_l": "{first}{last}_{l}",      # chrisbooth_b
    "firstnamelastname-l": "{first}{last}-{l}",      # chrisbooth-b
    "firstnamelastnamel": "{first}{last}{l}",        # chrisboothb
    "firstnamelastname.f": "{first}{last}.{f}",      # chrisbooth.c
    "firstnamelastname_f": "{first}{last}_{f}",      # chrisbooth_c
    "firstnamelastname-f": "{first}{last}-{f}",      # chrisbooth-c
    "firstnamelastnamef": "{first}{last}{f}",        # chrisboothc

    # GROUP 6: Full Combo + Both Initials (6 patterns)
    "firstnamelastname.fl": "{first}{last}.{f}{l}",  # chrisbooth.cb
    "firstnamelastname_fl": "{first}{last}_{f}{l}",  # chrisbooth_cb
    "firstnamelastname-fl": "{first}{last}-{f}{l}",  # chrisbooth-cb
    "firstnamelastnamefl": "{first}{last}{f}{l}",    # chrisboothcb
    "firstnamelastname.ll": "{first}{last}.{l}{l}",  # chrisbooth.bb
    "firstnamelastnamell": "{first}{last}{l}{l}",    # chrisboothbb

    # GROUP 7: FirstL + Lastname Combinations (8 patterns)
    "firstnamel.lastname": "{first}{l}.{last}",      # chrisb.booth
    "firstnamel_lastname": "{first}{l}_{last}",      # chrisb_booth
    "firstnamel-lastname": "{first}{l}-{last}",      # chrisb-booth
    "firstnamellastname": "{first}{l}{last}",        # chrisbbooth
    "firstnamef.lastname": "{first}{f}.{last}",      # chrisc.booth
    "firstnamef_lastname": "{first}{f}_{last}",      # chrisc_booth
    "firstnamef-lastname": "{first}{f}-{last}",      # chrisc-booth
    "firstnameflastname": "{first}{f}{last}",        # chriscbooth
}


# =============================================================================
# Pattern Tiers (Ranked by Natural/Professional Appearance)
# =============================================================================

# Tier 1: Most natural/professional - use for Google (top 10)
TIER_1_PATTERNS = [
    "firstname.lastname",    # chris.booth
    "firstname",             # chris
    "f.lastname",            # c.booth
    "firstnamelastname",     # chrisbooth
    "firstname.l",           # chris.b
    "flastname",             # cbooth
    "lastname.f",            # booth.c
    "firstname_lastname",    # chris_booth
    "lastname",              # booth
    "firstnamel",            # chrisb
]

# Tier 2: Common alternatives
TIER_2_PATTERNS = [
    "f_lastname",            # c_booth
    "f-lastname",            # c-booth
    "firstname_l",           # chris_b
    "firstname-l",           # chris-b
    "lastname_f",            # booth_c
    "lastname-f",            # booth-c
    "lastnamef",             # boothc
    "firstname-lastname",    # chris-booth
    "firstnamef",            # chrisc
    "firstname.f",           # chris.c
]

# Tier 3: Extended variations (remaining patterns)
TIER_3_PATTERNS = [
    "firstname_f",           # chris_c
    "firstname-f",           # chris-c
    "firstnamefl",           # chriscb
    "firstname.fl",          # chris.cb
    "firstname_fl",          # chris_cb
    "firstname-fl",          # chris-cb
    "firstnamell",           # chrisbb
    "firstname.ll",          # chris.bb
    "firstname_ll",          # chris_bb
    "firstname-ll",          # chris-bb
    "firstnamelastname.l",   # chrisbooth.b
    "firstnamelastname_l",   # chrisbooth_b
    "firstnamelastname-l",   # chrisbooth-b
    "firstnamelastnamel",    # chrisboothb
    "firstnamelastname.f",   # chrisbooth.c
    "firstnamelastname_f",   # chrisbooth_c
    "firstnamelastname-f",   # chrisbooth-c
    "firstnamelastnamef",    # chrisboothc
    "firstnamelastname.fl",  # chrisbooth.cb
    "firstnamelastname_fl",  # chrisbooth_cb
    "firstnamelastname-fl",  # chrisbooth-cb
    "firstnamelastnamefl",   # chrisboothcb
    "firstnamelastname.ll",  # chrisbooth.bb
    "firstnamelastnamell",   # chrisboothbb
    "firstnamel.lastname",   # chrisb.booth
    "firstnamel_lastname",   # chrisb_booth
    "firstnamel-lastname",   # chrisb-booth
    "firstnamellastname",    # chrisbbooth
    "firstnamef.lastname",   # chrisc.booth
    "firstnamef_lastname",   # chrisc_booth
    "firstnamef-lastname",   # chrisc-booth
    "firstnameflastname",    # chriscbooth
]

# All patterns in ranked order
ALL_PATTERNS_RANKED = TIER_1_PATTERNS + TIER_2_PATTERNS + TIER_3_PATTERNS

# Legacy: Default patterns (backward compatibility)
DEFAULT_PATTERNS = TIER_1_PATTERNS[:5]


# =============================================================================
# Core Functions
# =============================================================================

def render_prefix(template: str, first: str, last: str) -> str:
    """
    Render a pattern template with name components.

    Args:
        template: Pattern template string with {first}, {last}, {f}, {l} placeholders
        first: First name (e.g., "Chris")
        last: Last name (e.g., "Booth")

    Returns:
        Rendered email prefix (lowercase)

    Example:
        >>> render_prefix("{first}.{last}", "Chris", "Booth")
        'chris.booth'
    """
    if not first or not last:
        raise ValueError("First and last name are required")

    return template.format(
        first=first.lower(),
        last=last.lower(),
        f=first[0].lower(),
        l=last[0].lower(),
    )


# Legacy: Old VARIATION_PATTERNS format (backward compatibility)
# Must be defined after render_prefix
VARIATION_PATTERNS = {
    name: {
        "fn": lambda f, l, t=template: render_prefix(t, f, l),
        "display": lambda f, l: (f, l),
        "description": f"{name} ({render_prefix(template, 'chris', 'booth')})",
    }
    for name, template in list(PATTERN_TEMPLATES_52.items())[:8]
}


def get_patterns_for_provider(provider: str, count: Optional[int] = None) -> list[str]:
    """
    Get ranked pattern list based on provider requirements.

    Args:
        provider: "entra" (Microsoft) or "google"
        count: Optional limit on number of patterns (default: provider max)

    Returns:
        List of pattern names in ranked order

    Example:
        >>> get_patterns_for_provider("google")
        ['firstname.lastname', 'firstname', 'f.lastname', ...]  # 10 patterns
        >>> get_patterns_for_provider("entra")
        ['firstname.lastname', 'firstname', ...]  # 52 patterns
    """
    provider_lower = provider.lower()

    if provider_lower == "entra":
        max_count = 52
        patterns = ALL_PATTERNS_RANKED
    elif provider_lower == "google":
        max_count = 10
        patterns = TIER_1_PATTERNS
    else:
        max_count = 10
        patterns = TIER_1_PATTERNS

    if count is not None:
        max_count = min(count, max_count)

    return patterns[:max_count]


def generate_prefix(
    first_name: str,
    last_name: str,
    pattern: str,
) -> tuple[str, str, str]:
    """
    Generate email prefix from a name using a specific pattern.

    Args:
        first_name: First name (e.g., "Chris")
        last_name: Last name (e.g., "Booth")
        pattern: Pattern name from PATTERN_TEMPLATES_52

    Returns:
        Tuple of (display_first, display_last, email_prefix)
    """
    if pattern not in PATTERN_TEMPLATES_52:
        raise ValueError(f"Unknown pattern: {pattern}")

    template = PATTERN_TEMPLATES_52[pattern]
    prefix = render_prefix(template, first_name, last_name)

    # Determine display names based on pattern
    display_first = first_name
    display_last = last_name

    # Adjust display for initial-based patterns
    if pattern.startswith("f.") or pattern.startswith("f_") or pattern.startswith("f-") or pattern == "flastname":
        display_first = first_name[0]
    if ".l" in pattern or "_l" in pattern or "-l" in pattern or pattern.endswith("l") and "lastname" not in pattern:
        if not pattern.endswith("fl") and not pattern.endswith("ll"):
            display_last = last_name[0]

    return display_first, display_last, prefix


def generate_variations(
    base_names: list[dict],
    patterns: Optional[list[str]] = None,
    count: int = 10,
    provider: str = "google",
) -> list[dict]:
    """
    Generate email prefix variations from base names.

    Args:
        base_names: List of base name dicts with firstName, lastName, isFounder
        patterns: List of pattern names to use (default: provider-specific)
        count: Target number of variations to generate
        provider: "entra" (up to 52) or "google" (up to 10)

    Returns:
        List of variation dicts with firstName, lastName, emailPrefix, baseName, pattern

    Example:
        >>> generate_variations(
        ...     [{"firstName": "Chris", "lastName": "Booth", "isFounder": True}],
        ...     count=52,
        ...     provider="entra"
        ... )
        [
            {"firstName": "Chris", "lastName": "Booth", "emailPrefix": "chris.booth", ...},
            {"firstName": "Chris", "lastName": "Booth", "emailPrefix": "chris", ...},
            ... # 52 total variations
        ]
    """
    # Provider-specific limits
    provider_lower = provider.lower()
    if provider_lower == "entra":
        count = min(count, 52)
    else:
        count = min(count, 10)

    # Use provider-specific patterns if none specified
    if patterns is None:
        patterns = get_patterns_for_provider(provider, count)

    variations = []
    used_prefixes = set()

    # Sort base names: founders first
    sorted_bases = sorted(
        base_names,
        key=lambda x: (not x.get("isFounder", False), x.get("firstName", "")),
    )

    # Generate variations using patterns
    for pattern in patterns:
        if len(variations) >= count:
            break

        for base in sorted_bases:
            if len(variations) >= count:
                break

            first = base.get("firstName", "")
            last = base.get("lastName", "")
            is_founder = base.get("isFounder", False)
            base_name_str = f"{first} {last}"

            try:
                display_first, display_last, prefix = generate_prefix(first, last, pattern)
            except (ValueError, IndexError):
                continue

            if prefix not in used_prefixes:
                variations.append({
                    "firstName": display_first,
                    "lastName": display_last,
                    "emailPrefix": prefix,
                    "baseName": base_name_str,
                    "pattern": pattern,
                    "isFounder": is_founder and pattern == "firstname.lastname",
                })
                used_prefixes.add(prefix)

    return variations


def generate_all_prefixes(first_name: str, last_name: str, provider: str = "entra") -> list[str]:
    """
    Generate all email prefixes for a name based on provider.

    This is a convenience function for quick prefix generation without
    the full variation dict structure.

    Args:
        first_name: First name (e.g., "Chris")
        last_name: Last name (e.g., "Booth")
        provider: "entra" (52 prefixes) or "google" (10 prefixes)

    Returns:
        List of email prefix strings

    Example:
        >>> generate_all_prefixes("Chris", "Booth", "entra")
        ['chris.booth', 'chris', 'c.booth', ...]  # 52 prefixes
    """
    patterns = get_patterns_for_provider(provider)
    prefixes = []

    for pattern in patterns:
        template = PATTERN_TEMPLATES_52[pattern]
        try:
            prefix = render_prefix(template, first_name, last_name)
            if prefix not in prefixes:
                prefixes.append(prefix)
        except (ValueError, IndexError):
            continue

    return prefixes


def get_available_patterns(provider: Optional[str] = None) -> list[dict]:
    """
    Get list of available variation patterns with descriptions.

    Args:
        provider: Optional filter by provider ("entra" or "google")

    Returns:
        List of pattern info dicts with name, template, example, tier
    """
    if provider:
        pattern_names = get_patterns_for_provider(provider)
    else:
        pattern_names = list(PATTERN_TEMPLATES_52.keys())

    result = []
    for name in pattern_names:
        template = PATTERN_TEMPLATES_52[name]
        example = render_prefix(template, "Chris", "Booth")

        # Determine tier
        if name in TIER_1_PATTERNS:
            tier = 1
        elif name in TIER_2_PATTERNS:
            tier = 2
        else:
            tier = 3

        result.append({
            "name": name,
            "template": template,
            "example": example,
            "tier": tier,
        })

    return result
