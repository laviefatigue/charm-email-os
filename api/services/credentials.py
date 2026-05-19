"""
Shared application-level secrets access.

Single entry point for reading rows from the `secrets` table
(migration 136). Bumps last_used_at on each read for audit.

DO NOT bypass this module — direct SELECTs scatter access points and
make the next rotation / audit harder. The github_app module reads
the Charm Onboarder PEM through this helper; future services
consuming other shared secrets (webhook signing keys, Day.AI OAuth
refresh tokens, etc.) should do the same.

Canonical reference: docs/architecture/client-context-sync.md
§Security Model. See docs/dayai/SPEC_secrets.md for design notes.
"""

from __future__ import annotations

import logging

import asyncpg

logger = logging.getLogger(__name__)


class CredentialNotFound(Exception):
    """Raised when no active row exists for the requested name."""


async def get_credential(name: str, pool: asyncpg.Pool) -> str:
    """
    Return the active secret value by name. Raises CredentialNotFound
    if no active row exists.

    Bumps secrets.last_used_at as a side effect.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE secrets
               SET last_used_at = NOW()
             WHERE name = $1
               AND is_active = TRUE
            RETURNING value
            """,
            name,
        )
    if row is None:
        raise CredentialNotFound(
            f"No active secrets row named {name!r}. "
            "Has the one-time seed INSERT been run on this environment?"
        )
    return row["value"]
