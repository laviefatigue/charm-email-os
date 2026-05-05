"""Shared helpers for event handlers.

These helpers consolidate the patterns every handler needs:
  - Reading the originating row by entity_id
  - Enqueueing tag_op events into event_log for Tier 2 batch processing
  - Idempotency-guarded UPDATEs

Plan: docs/plans/event-driven-architecture.md
"""
from __future__ import annotations

import json
import logging
from typing import Iterable, Optional
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


async def enqueue_tag_op(
    conn: asyncpg.Connection,
    *,
    op: str,                        # 'attach' or 'remove'
    inbox_id: UUID,
    workspace_id: UUID,
    tag_name: str,
    triggered_by_event_id: Optional[UUID] = None,
) -> UUID:
    """Insert a tag_op event into event_log for the Tier 2 batch worker.

    Per ADR-006 + the migration 107 CHECK constraint, every tag_op MUST
    carry workspace_id. The DB will reject the INSERT if it's missing —
    that's a load-bearing guarantee.

    The Tier 2 batch worker (Phase 4 of the plan) will:
      SELECT FROM event_log WHERE event_type = 'tag_op_*' AND status = 'pending'
        AND workspace_id = X
      → group by tag_name → bulk EB API call with workspace's scoped key
      → mark events 'completed' (or 'failed' with error_message)

    Returns the new event_log row id (handler can store this for traceability).
    """
    if op not in ('attach', 'remove'):
        raise ValueError(f"op must be 'attach' or 'remove', got {op!r}")

    event_type = f'tag_op_{op}'

    payload = {
        'inbox_id': str(inbox_id),
        'tag_name': tag_name,
        'triggered_by_event_id': str(triggered_by_event_id) if triggered_by_event_id else None,
    }

    row_id = await conn.fetchval(
        """
        INSERT INTO event_log (
            event_type, entity_type, entity_id,
            payload, status, workspace_id
        ) VALUES (
            $1, 'inbox', $2,
            $3::jsonb, 'pending', $4
        )
        RETURNING id
        """,
        event_type, inbox_id, json.dumps(payload), workspace_id,
    )
    return row_id


async def fetch_inbox(conn: asyncpg.Connection, inbox_id: UUID) -> Optional[dict]:
    """Read a sender_accounts row by id. Returns None if not found / inactive."""
    row = await conn.fetchrow(
        """
        SELECT id, email_address, workspace_id, domain_id, esp,
               inbox_state, status,
               inventory_lifecycle_status, inventory_pool_status,
               complaints_lifetime,
               COALESCE(emails_sent_all_time, 0) AS emails_sent_all_time,
               kill_trigger::text AS kill_trigger
        FROM sender_accounts
        WHERE id = $1 AND is_active = TRUE
        """,
        inbox_id,
    )
    return dict(row) if row else None


async def hard_bounces_lifetime(conn: asyncpg.Connection, inbox_id: UUID) -> int:
    """Compute lifetime hard bounces from response_messages (the rule's numerator)."""
    return await conn.fetchval(
        """
        SELECT COUNT(*) FROM response_messages
        WHERE sender_account_id = $1
          AND folder = 'bounced'
          AND bounce_type IN ('hard_blocked', 'hard_unknown')
        """,
        inbox_id,
    )
