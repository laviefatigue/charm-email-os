"""Domain handlers (Phase 2).

  domain_burned_handler — domain.pool_status flipped to 'burned';
                          NULL out pool_status on every inbox of that
                          domain + enqueue tag_op_remove for live + reserve.

Plan: docs/plans/event-driven-architecture.md
"""
from __future__ import annotations

import json
import logging
from typing import Dict
from uuid import UUID

import asyncpg

from ._common import enqueue_tag_op

logger = logging.getLogger(__name__)


async def domain_burned_handler(event: Dict, conn: asyncpg.Connection) -> None:
    """A domain was burned. For every inbox on that domain:
      - inventory_pool_status → NULL (per the burned-domain rule from kill-triggers.md)
      - enqueue tag_op_remove for whatever pool tag they had

    The pool_status NULL transition will fire pool_changed_handler for each
    inbox, which would normally enqueue its own tag_ops. But since we're
    setting them all to NULL, pool_changed sees old=live/reserve, new=NULL,
    and only enqueues remove. So we don't strictly need to enqueue removes
    here — pool_changed handles it.

    But we do need to ensure the pool_status NULL UPDATE fires the trigger.
    Single bulk UPDATE; the trigger fires per row.
    """
    payload = event['payload']
    if isinstance(payload, str):
        payload = json.loads(payload)

    domain_id = UUID(event['entity_id']) if isinstance(event['entity_id'], str) else event['entity_id']
    workspace_id = event.get('workspace_id')

    # Bulk NULL-out pool_status. Each row UPDATE fires pool_changed_handler
    # which enqueues the appropriate tag_op_remove. Idempotent: if pool_status
    # is already NULL, no UPDATE happens.
    affected = await conn.fetch(
        """
        UPDATE sender_accounts
        SET inventory_pool_status = NULL,
            updated_at = NOW()
        WHERE domain_id = $1
          AND is_active = TRUE
          AND inventory_pool_status IS NOT NULL
        RETURNING id, email_address
        """,
        domain_id,
    )

    logger.info(
        "domain_burned: %s (workspace=%s) — cleared pool_status on %d inboxes",
        payload.get('domain_name'), workspace_id, len(affected),
    )
