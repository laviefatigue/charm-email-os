"""DB access — minimal. Reads workspace + workspace_api_keys only.

The new app does not own any tables in v1. It only consumes existing
charm-email-os tables to resolve a workspace name → API key.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: UUID
    workspace_name: str
    emailbison_workspace_id: str | None
    api_key: str


async def fetch_workspace_context(
    conn: asyncpg.Connection,
    workspace_name: str,
) -> WorkspaceContext | None:
    """Look up an active workspace by name and return its API key context.

    Returns None if the workspace doesn't exist, isn't active, or has no
    active API key.
    """
    row = await conn.fetchrow(
        """
        SELECT
            w.id AS workspace_id,
            w.workspace_name,
            w.emailbison_workspace_id,
            k.key_token AS api_key
        FROM workspaces w
        JOIN workspace_api_keys k
            ON k.workspace_id = w.id
            AND k.is_active = TRUE
        WHERE w.workspace_name = $1
            AND w.is_active = TRUE
        LIMIT 1
        """,
        workspace_name,
    )
    if row is None:
        return None
    return WorkspaceContext(
        workspace_id=row["workspace_id"],
        workspace_name=row["workspace_name"],
        emailbison_workspace_id=row["emailbison_workspace_id"],
        api_key=row["api_key"],
    )
