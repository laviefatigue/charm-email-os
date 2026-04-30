"""DB access — workspace context lookup + ready-to-graduate query.

The new app does not own any tables. It reads existing charm-email-os
tables (workspaces, workspace_api_keys, sender_accounts) and writes
sender_accounts state changes during graduation (which mirror the
existing lifecycle_tag_sync._graduate_mature_inboxes path).

Mirroring discipline: the SQL here MUST match the eligibility filter in
sync_modules/lifecycle_tag_sync.py:_graduate_mature_inboxes exactly. Any
divergence creates a shadow-mode false positive or false negative. When
upstream changes the filter, this query updates in lockstep.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import asyncpg

# Hard-coded business-day window per ADR-006 / migration 094.
# Mirrors INCUBATION_BUSINESS_DAYS in sync_modules/lifecycle_tag_sync.py.
INCUBATION_BUSINESS_DAYS = 14


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: UUID
    workspace_name: str
    emailbison_workspace_id: str | None
    api_key: str


@dataclass(frozen=True)
class GraduationCandidate:
    sender_id: UUID
    email_address: str
    emailbison_account_id: int
    esp: str | None  # 'gmail' | 'microsoft' | None
    warmup_enabled_since_iso: str  # ISO date — for logging/audit
    business_days_elapsed: int


async def fetch_workspace_context(
    conn: asyncpg.Connection,
    workspace_name: str,
) -> WorkspaceContext | None:
    """Look up an active workspace by name + return its scoped API key.

    Returns None if the workspace doesn't exist, isn't active, or has
    no active API key. Caller decides whether to fail-loud or skip.
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


async def fetch_graduation_candidates(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    business_days: int = INCUBATION_BUSINESS_DAYS,
) -> list[GraduationCandidate]:
    """Return inboxes eligible for graduation in the given workspace.

    Eligibility (mirrors sync_modules/lifecycle_tag_sync.py:256-281):
      - workspace_id matches
      - inbox_state = 'live'  (alive — does not mean pool=live)
      - is_active = TRUE
      - warmup_enabled = TRUE
      - warmup_enabled_since IS NOT NULL
      - inventory_lifecycle_status = 'incubating'
      - emailbison_account_id IS NOT NULL
      - business days elapsed since warmup_enabled_since >= `business_days`

    The business-day count uses generate_series excluding Sat (DOW=6) and
    Sun (DOW=0). Holidays are intentionally not excluded for v1 — same
    rule as the existing module.
    """
    rows = await conn.fetch(
        """
        SELECT
            id,
            email_address,
            emailbison_account_id::int AS emailbison_account_id,
            esp,
            warmup_enabled_since,
            (
                SELECT COUNT(*)
                FROM generate_series(
                    warmup_enabled_since::date,
                    CURRENT_DATE - INTERVAL '1 day',
                    INTERVAL '1 day'
                ) AS d
                WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)
            )::int AS business_days_elapsed
        FROM sender_accounts
        WHERE workspace_id = $1
          AND inbox_state = 'live'
          AND is_active = TRUE
          AND warmup_enabled = TRUE
          AND warmup_enabled_since IS NOT NULL
          AND inventory_lifecycle_status = 'incubating'
          AND emailbison_account_id IS NOT NULL
          AND (
              SELECT COUNT(*)
              FROM generate_series(
                  warmup_enabled_since::date,
                  CURRENT_DATE - INTERVAL '1 day',
                  INTERVAL '1 day'
              ) AS d
              WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)
          ) >= $2
        ORDER BY warmup_enabled_since ASC, id ASC
        """,
        workspace_id,
        business_days,
    )
    return [
        GraduationCandidate(
            sender_id=r["id"],
            email_address=r["email_address"],
            emailbison_account_id=r["emailbison_account_id"],
            esp=r["esp"],
            warmup_enabled_since_iso=r["warmup_enabled_since"].date().isoformat(),
            business_days_elapsed=r["business_days_elapsed"],
        )
        for r in rows
    ]


async def update_graduation(
    conn: asyncpg.Connection,
    sender_id: UUID,
    target_pool: str,  # 'live' or 'reserve'
) -> None:
    """Apply the graduation transition in DB, atomically with the rotation log.

    Caller must wrap in a transaction with the EB tag operations so that we
    never have a DB transition without a matching EB tag, or vice versa.
    """
    await conn.execute(
        """
        UPDATE sender_accounts
        SET
            inventory_lifecycle_status = 'active',
            inventory_pool_status = $2,
            updated_at = NOW()
        WHERE id = $1
        """,
        sender_id,
        target_pool,
    )


async def record_rotation_history(
    conn: asyncpg.Connection,
    workspace_id: UUID,
    sender_id: UUID,
    sender_email: str,
    target_pool: str,
    reason: str,
) -> None:
    """Log the graduation event for audit. Mirrors the INSERT in lifecycle_tag_sync."""
    await conn.execute(
        """
        INSERT INTO inbox_rotation_history (
            workspace_id, rotation_type,
            target_inbox_id, target_inbox_email,
            source_pool, target_pool,
            reason, triggered_by,
            success, executed_at
        ) VALUES (
            $1, 'graduate',
            $2, $3,
            NULL, $4,
            $5, 'incubation-watcher',
            TRUE, NOW()
        )
        """,
        workspace_id,
        sender_id,
        sender_email,
        target_pool,
        reason,
    )
