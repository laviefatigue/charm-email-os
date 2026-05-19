"""
Shared application-level credentials access.

Single entry point for reading rows from the app_credentials table
(migration 112). Bumps last_used_at on each read for audit.

DO NOT bypass this module — direct SELECTs scatter access points and
make the next rotation / audit harder. The github_app module reads
the Charm Onboarder PEM through this helper; future services
consuming other shared credentials should do the same.

See docs/dayai/SPEC_app_credentials.md for the design.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


class CredentialNotFound(Exception):
    """Raised when no active row exists for the requested name."""


async def get_credential(name: str, pool: asyncpg.Pool) -> str:
    """
    Return the active credential value by name. Raises CredentialNotFound
    if no active row exists.

    Bumps app_credentials.last_used_at as a side effect.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE app_credentials
               SET last_used_at = NOW()
             WHERE name = $1
               AND is_active = TRUE
            RETURNING value
            """,
            name,
        )
    if row is None:
        raise CredentialNotFound(
            f"No active app_credentials row named {name!r}. "
            "Has the one-time seed INSERT been run on this environment?"
        )
    return row["value"]
