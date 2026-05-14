"""Lifecycle handlers (Phase 2).

  inbox_pickup_handler  — new inbox synced into workspace; soft validation + audit
  pool_changed_handler  — inventory_pool_status changed; enqueue tag_op events

The CROSS-WORKSPACE FIREWALL hard rule (Plan A) is enforced at the DB
CHECK constraint layer — that fires BEFORE these triggers. So by the
time inbox_pickup_handler runs, we already know the row passed
HR-1 + HR-2 validation. This handler does soft-validation extras
(e.g., "did the operator change a workspace assignment manually?").

Plan: docs/plans/event-driven-architecture.md
"""
from __future__ import annotations

import json
import logging
from typing import Dict
from uuid import UUID

import asyncpg

from ._common import enqueue_tag_op, fetch_inbox

logger = logging.getLogger(__name__)


async def inbox_pickup_handler(event: Dict, conn: asyncpg.Connection) -> None:
    """A new sender_accounts row was inserted.

    Plan A's CHECK constraint already validated workspace assignment.
    This handler:
      - Logs the pickup (audit)
      - Could in future fire workspace-onboarding side effects
        (mail-flow rule provisioning, etc.) — placeholder for that

    For Phase 2, just log. Polling-based discovery + sync continues.
    """
    payload = event['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)

    logger.info(
        "inbox_pickup: %s (esp=%s, workspace=%s)",
        payload.get('email_address'),
        payload.get('esp'),
        event.get('workspace_id'),
    )


async def pool_changed_handler(event: Dict, conn: asyncpg.Connection) -> None:
    """inventory_pool_status changed. Enqueue tag_op events for the new state.

    Old pool tag (if any) gets a tag_op_remove. New pool tag (if any)
    gets a tag_op_attach. NULL → no tag for that side.

    Special case: NULL → live (initial assignment from graduation) is
    handled by the lifecycle_tag_sync graduation path which writes EB
    BEFORE flipping pool_status. So if old_pool was NULL and new_pool
    is set, we still emit tag_op_attach as a reconciliation safety net
    (Tier 2 batch is idempotent — applying a tag that's already there
    is a 200 OK no-op).

    Per ADR-006: every tag_op carries workspace_id (CHECK constraint
    enforces this in the INSERT).
    """
    payload = event['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)

    inbox_id = UUID(event['entity_id']) if isinstance(event['entity_id'], str) else event['entity_id']
    old_pool = payload.get('old_pool')
    new_pool = payload.get('new_pool')
    workspace_id = event.get('workspace_id')
    if isinstance(workspace_id, str):
        workspace_id = UUID(workspace_id)

    if not workspace_id:
        # Defensive: pool_changed should always carry workspace_id from the
        # trigger payload. If somehow missing, fetch.
        inbox = await fetch_inbox(conn, inbox_id)
        workspace_id = inbox['workspace_id'] if inbox else None

    if not workspace_id:
        logger.error("pool_changed: missing workspace_id for inbox %s, skip", inbox_id)
        return

    triggered_by = event.get('id')
    if isinstance(triggered_by, str):
        triggered_by = UUID(triggered_by)

    if old_pool and old_pool != new_pool:
        await enqueue_tag_op(
            conn,
            op='remove',
            inbox_id=inbox_id,
            workspace_id=workspace_id,
            tag_name=old_pool,  # 'live' or 'reserve'
            triggered_by_event_id=triggered_by,
        )

    if new_pool and new_pool != old_pool:
        await enqueue_tag_op(
            conn,
            op='attach',
            inbox_id=inbox_id,
            workspace_id=workspace_id,
            tag_name=new_pool,
            triggered_by_event_id=triggered_by,
        )

    logger.debug(
        "pool_changed: inbox %s %s → %s, tag ops enqueued",
        inbox_id, old_pool, new_pool,
    )
