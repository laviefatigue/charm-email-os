"""Async Postgres connection helper. One connection per CLI invocation; pool not needed at this scale."""
from __future__ import annotations

import asyncpg


async def connect(database_url: str) -> asyncpg.Connection:
    """Open a single asyncpg connection. Caller closes via .close()."""
    return await asyncpg.connect(database_url)
