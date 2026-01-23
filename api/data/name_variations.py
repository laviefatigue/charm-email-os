"""
Name variation generation for sender email prefixes.

Generates multiple email prefix variations from a single base name.
Used for Hypertide inbox provisioning where clients provide 1-2 real identities
but need many unique email prefixes.

Usage:
    from data.name_variations import generate_variations, VARIATION_PATTERNS

Example:
    Base name: Chris Booth
    Variations: chris.booth, c.booth, chrisbooth, chris.b, cbooth, booth.chris
"""

from typing import Optional


# Variation pattern definitions
# Each pattern generates a different email prefix format from first/last name
VARIATION_PATTERNS = {
    "firstname.lastname": {
        "fn": lambda f, l: f"{f.lower()}.{l.lower()}",
        "display": lambda f, l: (f, l),
        "description": "Full name with dot (chris.booth)",
    },
    "f.lastname": {
        "fn": lambda f, l: f"{f[0].lower()}.{l.lower()}",
        "display": lambda f, l: (f[0], l),
        "description": "Initial.lastname (c.booth)",
    },
    "firstnamelastname": {
        "fn": lambda f, l: f"{f.lower()}{l.lower()}",
        "display": lambda f, l: (f, l),
        "description": "No separator (chrisbooth)",
    },
    "firstname.l": {
        "fn": lambda f, l: f"{f.lower()}.{l[0].lower()}",
        "display": lambda f, l: (f, l[0]),
        "description": "First.initial (chris.b)",
    },
    "flastname": {
        "fn": lambda f, l: f"{f[0].lower()}{l.lower()}",
        "display": lambda f, l: (f[0], l),
        "description": "Initial + lastname (cbooth)",
    },
    "lastname.firstname": {
        "fn": lambda f, l: f"{l.lower()}.{f.lower()}",
        "display": lambda f, l: (f, l),
        "description": "Reversed order (booth.chris)",
    },
    "lastname.f": {
        "fn": lambda f, l: f"{l.lower()}.{f[0].lower()}",
        "display": lambda f, l: (f[0], l),
        "description": "Lastname.initial (booth.c)",
    },
    "firstname_lastname": {
        "fn": lambda f, l: f"{f.lower()}_{l.lower()}",
        "display": lambda f, l: (f, l),
        "description": "Underscore separator (chris_booth)",
    },
}

# Default patterns to use when none specified
DEFAULT_PATTERNS = [
    "firstname.lastname",
    "f.lastname",
    "firstnamelastname",
    "firstname.l",
    "flastname",
]


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
        pattern: Pattern name from VARIATION_PATTERNS

    Returns:
        Tuple of (display_first, display_last, email_prefix)
    """
    if pattern not in VARIATION_PATTERNS:
        raise ValueError(f"Unknown pattern: {pattern}")

    pattern_def = VARIATION_PATTERNS[pattern]
    prefix = pattern_def["fn"](first_name, last_name)
    display_first, display_last = pattern_def["display"](first_name, last_name)

    return display_first, display_last, prefix


def generate_variations(
    base_names: list[dict],
    patterns: Optional[list[str]] = None,
    count: int = 10,
) -> list[dict]:
    """
    Generate email prefix variations from base names.

    Args:
        base_names: List of base name dicts with firstName, lastName, isFounder
        patterns: List of pattern names to use (default: DEFAULT_PATTERNS)
        count: Target number of variations to generate (max 10 for Hypertide)

    Returns:
        List of variation dicts with firstName, lastName, emailPrefix, baseName, pattern

    Example:
        >>> generate_variations(
        ...     [{"firstName": "Chris", "lastName": "Booth", "isFounder": True}],
        ...     patterns=["firstname.lastname", "f.lastname"],
        ...     count=5
        ... )
        [
            {"firstName": "Chris", "lastName": "Booth", "emailPrefix": "chris.booth", ...},
            {"firstName": "C", "lastName": "Booth", "emailPrefix": "c.booth", ...},
            ...
        ]
    """
    count = min(count, 10)  # Hypertide max is 10
    patterns = patterns or DEFAULT_PATTERNS
    variations = []
    used_prefixes = set()

    # Sort base names: founders first
    sorted_bases = sorted(
        base_names,
        key=lambda x: (not x.get("isFounder", False), x.get("firstName", "")),
    )

    # First pass: generate variations using selected patterns
    for base in sorted_bases:
        first = base.get("firstName", "")
        last = base.get("lastName", "")
        is_founder = base.get("isFounder", False)
        base_name_str = f"{first} {last}"

        for pattern in patterns:
            if len(variations) >= count:
                break

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

        if len(variations) >= count:
            break

    # Second pass: add numbered suffixes if more variations needed
    suffix = 1
    while len(variations) < count and suffix <= 99:
        for base in sorted_bases:
            if len(variations) >= count:
                break

            first = base.get("firstName", "")
            last = base.get("lastName", "")
            base_name_str = f"{first} {last}"

            # Add numbered suffix to firstname.lastname pattern
            prefix = f"{first.lower()}.{last.lower()}{suffix}"
            if prefix not in used_prefixes:
                variations.append({
                    "firstName": first,
                    "lastName": last,
                    "emailPrefix": prefix,
                    "baseName": base_name_str,
                    "pattern": "numbered",
                    "isFounder": False,
                })
                used_prefixes.add(prefix)

        suffix += 1

    return variations


def get_available_patterns() -> list[dict]:
    """
    Get list of available variation patterns with descriptions.

    Returns:
        List of pattern info dicts with name, description, example
    """
    return [
        {
            "name": name,
            "description": info["description"],
            "example": info["fn"]("Chris", "Booth"),
        }
        for name, info in VARIATION_PATTERNS.items()
    ]
