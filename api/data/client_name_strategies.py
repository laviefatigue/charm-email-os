"""
Client-specific name generation strategies.

Defines founder names and generation preferences for specific clients.
Used by the generate_sender_names endpoint to customize inbox names.

Usage:
    from data.client_name_strategies import CLIENT_NAME_STRATEGIES, get_strategy
"""

from typing import Optional

# Client name strategies keyed by client identifier (name or ID)
CLIENT_NAME_STRATEGIES = {
    # Charm - Chris Booth as founder, professional team style
    "charm": {
        "founder_name": {"first": "Chris", "last": "Booth"},
        "variations": [
            {"first": "Chris", "last": "Booth", "email_prefix": "chris.booth"},
            {"first": "C", "last": "Booth", "email_prefix": "c.booth"},
            {"first": "Christopher", "last": "Booth", "email_prefix": "christopher.booth"},
        ],
        "team_style": "professional",  # Use professional-sounding names
        "include_founder": True,  # Always include founder in first position
        "preferred_first_names": [
            "Alex", "Jordan", "Taylor", "Morgan", "Casey",
            "Riley", "Cameron", "Avery", "Parker", "Quinn",
        ],
    },

    # HireCharm - Same as Charm (alias)
    "hirecharm": {
        "founder_name": {"first": "Chris", "last": "Booth"},
        "include_founder": True,
        "team_style": "professional",
    },

    # Default strategy for clients without specific config
    "default": {
        "founder_name": None,
        "include_founder": False,
        "team_style": "gender_neutral",
        "preferred_first_names": None,  # Use full pool
    },
}


def get_strategy(client_name: Optional[str] = None, client_id: Optional[str] = None) -> dict:
    """
    Get the name strategy for a client.

    Args:
        client_name: Client name to look up (case-insensitive)
        client_id: Client ID to look up (not yet implemented)

    Returns:
        Strategy dict with founder_name, include_founder, team_style, etc.
    """
    if client_name:
        # Normalize client name for lookup
        normalized = client_name.lower().replace(" ", "").replace("-", "")

        # Check for exact or partial matches
        for key in CLIENT_NAME_STRATEGIES:
            if key in normalized or normalized in key:
                return CLIENT_NAME_STRATEGIES[key]

    return CLIENT_NAME_STRATEGIES["default"]


def get_founder_name(strategy: dict) -> Optional[dict]:
    """
    Extract founder name from strategy if configured.

    Args:
        strategy: Strategy dict from get_strategy()

    Returns:
        Dict with firstName, lastName, emailPrefix, source='founder' or None
    """
    if not strategy.get("include_founder"):
        return None

    founder = strategy.get("founder_name")
    if not founder:
        return None

    return {
        "firstName": founder["first"],
        "lastName": founder["last"],
        "emailPrefix": f"{founder['first'].lower()}.{founder['last'].lower()}",
        "source": "founder",
    }


def apply_strategy(
    names: list[dict],
    strategy: dict,
    target_count: int = 10,
) -> list[dict]:
    """
    Apply a client strategy to a list of names.

    Ensures founder is first if include_founder is True.

    Args:
        names: List of name dicts to potentially modify
        strategy: Strategy dict from get_strategy()
        target_count: Target number of names (max 10 for Hypertide)

    Returns:
        Modified list with founder first (if applicable)
    """
    from data.sender_names import get_random_name

    target_count = min(target_count, 10)
    used_prefixes = {n["emailPrefix"] for n in names}
    result = []

    # Add founder first if configured
    founder = get_founder_name(strategy)
    if founder and founder["emailPrefix"] not in used_prefixes:
        result.append(founder)
        used_prefixes.add(founder["emailPrefix"])

    # Add existing names (skip founder if already added)
    for name in names:
        if name["emailPrefix"] not in used_prefixes or name["emailPrefix"] == founder.get("emailPrefix") if founder else False:
            continue
        if len(result) >= target_count:
            break
        result.append(name)
        used_prefixes.add(name["emailPrefix"])

    # Fill remaining slots with random names
    preferred_firsts = strategy.get("preferred_first_names")
    while len(result) < target_count:
        name = get_random_name(
            exclude_prefixes=used_prefixes,
            first_pool=preferred_firsts if preferred_firsts else None,
        )
        result.append(name)
        used_prefixes.add(name["emailPrefix"])

    return result
