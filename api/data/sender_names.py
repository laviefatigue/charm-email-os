"""
Expanded sender name pools for inbox provisioning.

Contains 50+ first names and 50+ last names for generating
professional-sounding email addresses.

Usage:
    from data.sender_names import FIRST_NAMES_POOL, LAST_NAMES_POOL
"""

# Gender-neutral and traditional professional first names (50+)
FIRST_NAMES_POOL = [
    # Gender-neutral professional names (preferred for cold email)
    'Alex', 'Jordan', 'Taylor', 'Morgan', 'Casey',
    'Riley', 'Cameron', 'Avery', 'Parker', 'Quinn',
    'Jamie', 'Drew', 'Blake', 'Reese', 'Skyler',
    'Sam', 'Chris', 'Pat', 'Robin', 'Dana',
    'Sage', 'Rowan', 'Emery', 'Finley', 'Phoenix',
    'Hayden', 'Peyton', 'Sydney', 'Kendall', 'Devon',

    # Traditional professional names (common in business)
    'Michael', 'Sarah', 'David', 'Jennifer', 'James',
    'Emily', 'Robert', 'Jessica', 'William', 'Amanda',
    'John', 'Ashley', 'Daniel', 'Stephanie', 'Matthew',
    'Nicole', 'Andrew', 'Megan', 'Joshua', 'Rachel',
    'Ryan', 'Lauren', 'Brian', 'Michelle', 'Kevin',
]  # 55 names total


# Common US surnames (50+)
LAST_NAMES_POOL = [
    # Most common US surnames
    'Smith', 'Johnson', 'Williams', 'Brown', 'Davis',
    'Miller', 'Wilson', 'Moore', 'Taylor', 'Anderson',
    'Thomas', 'Jackson', 'White', 'Harris', 'Martin',
    'Thompson', 'Garcia', 'Martinez', 'Robinson', 'Clark',
    'Lewis', 'Lee', 'Walker', 'Hall', 'Allen',
    'Young', 'King', 'Wright', 'Scott', 'Green',
    'Baker', 'Adams', 'Nelson', 'Carter', 'Mitchell',
    'Parker', 'Turner', 'Collins', 'Edwards', 'Stewart',
    'Morris', 'Murphy', 'Cook', 'Rogers', 'Morgan',
    'Peterson', 'Cooper', 'Reed', 'Bailey', 'Bell',
    'Howard', 'Ward', 'Torres', 'Gray', 'Watson',
]  # 55 names total


def generate_email_prefix(first_name: str, last_name: str) -> str:
    """Generate email prefix from name (e.g., 'John Smith' -> 'john.smith')"""
    return f"{first_name.lower()}.{last_name.lower()}"


def get_random_name(
    exclude_prefixes: set[str] | None = None,
    first_pool: list[str] | None = None,
    last_pool: list[str] | None = None,
) -> dict:
    """
    Get a random name combination that isn't in the exclude set.

    Args:
        exclude_prefixes: Set of email prefixes to avoid
        first_pool: Optional custom first name pool
        last_pool: Optional custom last name pool

    Returns:
        Dict with firstName, lastName, emailPrefix, source
    """
    import random

    first_pool = first_pool or FIRST_NAMES_POOL
    last_pool = last_pool or LAST_NAMES_POOL
    exclude_prefixes = exclude_prefixes or set()

    max_attempts = 100
    for _ in range(max_attempts):
        first = random.choice(first_pool)
        last = random.choice(last_pool)
        prefix = generate_email_prefix(first, last)

        if prefix not in exclude_prefixes:
            return {
                "firstName": first,
                "lastName": last,
                "emailPrefix": prefix,
                "source": "generated",
            }

    # Fallback: use numbered suffix if all combinations exhausted
    first = random.choice(first_pool)
    last = random.choice(last_pool)
    suffix = random.randint(1, 99)
    return {
        "firstName": first,
        "lastName": last,
        "emailPrefix": f"{first.lower()}.{last.lower()}{suffix}",
        "source": "generated",
    }


def generate_random_names(count: int = 10, exclude_prefixes: set[str] | None = None) -> list[dict]:
    """
    Generate a list of random sender names.

    Args:
        count: Number of names to generate (max 10 for Hypertide)
        exclude_prefixes: Set of email prefixes to avoid

    Returns:
        List of name dicts with firstName, lastName, emailPrefix, source
    """
    count = min(count, 10)  # Hypertide max
    exclude_prefixes = exclude_prefixes or set()
    names = []

    for _ in range(count):
        name = get_random_name(exclude_prefixes)
        names.append(name)
        exclude_prefixes.add(name["emailPrefix"])

    return names
