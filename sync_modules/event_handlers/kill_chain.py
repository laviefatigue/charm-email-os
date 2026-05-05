"""Kill chain handlers (Phase 2).

Three handlers for the bounce → kill → mark-dead chain:
  bounce_observed_handler  — recompute rate, queue kill if > 5%
  kill_queued_handler      — process pending kill row, mark inbox dead, enqueue tag ops
  inbox_died_handler       — fire promotion (delegates to Phase 3 promote_one)

All handlers are idempotent. The listener manages event_log lifecycle
(emitted → processing → completed/failed); these functions just do the
DB work.

Per the load-bearing rule: handlers do DB-only work. They never touch
EB. Tag changes happen via enqueue_tag_op() into event_log; Tier 2
batch worker (Phase 4) processes per-workspace with scoped EB clients.

Plan: docs/plans/event-driven-architecture.md
"""
from __future__ import annotations

import logging
import os
from typing import Dict
from uuid import UUID

import asyncpg

from ._common import enqueue_tag_op, fetch_inbox, hard_bounces_lifetime

logger = logging.getLogger(__name__)


# Mirror evaluate_lifetime_rule constants. Kept independent so handler
# can be reasoned about without importing health_checks (avoids cycles).
KILL_THRESHOLD_SPAM = int(os.getenv('KILL_THRESHOLD_SPAM', 1))
KILL_MIN_SENDS_LIFETIME = int(os.getenv('KILL_MIN_SENDS_LIFETIME', 20))
KILL_MATURE_RATE = float(os.getenv('KILL_MATURE_RATE', 0.05))


async def bounce_observed_handler(event: Dict, conn: asyncpg.Connection) -> None:
    """A new hard bounce landed in response_messages.

    Recompute the inbox's lifetime rate. If now > 5%, INSERT into
    kill_queue. The kill_queue trigger will then fire kill_queued_handler.

    Idempotency:
      - The check `COALESCE(complaints_lifetime, 0) >= 1` already routes
        to spam_complaint kill_queue rows on a different code path.
      - INSERT into kill_queue uses ON CONFLICT (inbox_id) WHERE status='pending'
        DO NOTHING — re-running for the same inbox doesn't double-queue.
    """
    payload = event['payload']
    if isinstance(payload, str):
        import json as _json
        payload = _json.loads(payload)

    inbox_id = UUID(payload['sender_account_id'])

    inbox = await fetch_inbox(conn, inbox_id)
    if not inbox:
        logger.debug("bounce_observed: inbox %s not active, skip", inbox_id)
        return

    if inbox['inbox_state'] != 'live':
        # Already dead. Nothing to do; bounce is just data.
        return

    sends = int(inbox['emails_sent_all_time'])
    if sends < KILL_MIN_SENDS_LIFETIME:
        return  # below volume floor

    complaints = int(inbox['complaints_lifetime'] or 0)
    if complaints >= KILL_THRESHOLD_SPAM:
        # Spam-complaint path is handled by complaint_observed_handler
        # (Phase 5 fold-in). This handler only queues rate-based kills.
        return

    hard = await hard_bounces_lifetime(conn, inbox_id)
    if hard <= 0:
        return
    rate = hard / sends
    if rate <= KILL_MATURE_RATE:
        return  # under threshold

    # Rate breach. Queue a kill. Idempotent via the partial unique index
    # (idx_kill_queue_inbox_pending, migration 099) — re-running for the
    # same inbox while a pending row exists is a silent no-op.
    queued_id = await conn.fetchval(
        """
        INSERT INTO kill_queue (
            inbox_id, workspace_id,
            trigger_type, trigger_value, trigger_threshold
        ) VALUES (
            $1, $2,
            'hard_bounce_rate_lifetime'::kill_trigger_type, $3, $4
        )
        ON CONFLICT (inbox_id) WHERE status = 'pending' DO NOTHING
        RETURNING id
        """,
        inbox_id, inbox['workspace_id'],
        round(rate, 6), KILL_MATURE_RATE,
    )

    if queued_id:
        logger.info(
            "bounce_observed: queued kill for %s (rate=%.4f > %.4f)",
            inbox['email_address'], rate, KILL_MATURE_RATE,
        )


async def kill_queued_handler(event: Dict, conn: asyncpg.Connection) -> None:
    """A new kill_queue row was inserted with status='pending'. Process it.

    Steps (all in same transaction since the listener wraps the handler call):
      1. Claim the kill_queue row (UPDATE status='flagged') — idempotent
      2. UPDATE sender_accounts: inbox_state='dead', kill_trigger=...,
         killed_at=NOW(), inventory_pool_status=NULL
      3. Enqueue tag_op_attach for flagged_{trigger_type}
      4. Enqueue tag_op_remove for 'live' tag

    No EB API calls. Tier 2 batch worker drains the tag_ops later.

    The inbox_state UPDATE will fire the inbox_died trigger, which
    will fire inbox_died_handler (which handles pool_promotion).
    Clean separation.
    """
    payload = event['payload']
    if isinstance(payload, str):
        import json as _json
        payload = _json.loads(payload)

    kill_queue_id = UUID(event['entity_id']) if isinstance(event['entity_id'], str) else event['entity_id']
    inbox_id = UUID(payload['inbox_id'])
    trigger_type = payload['trigger_type']
    workspace_id = UUID(payload['workspace_id']) if isinstance(payload.get('workspace_id'), str) else payload.get('workspace_id')

    # 1. Claim the kill_queue row. If another consumer already claimed it,
    #    `flagged` returned 0 rows — bail out (idempotent).
    claimed = await conn.fetchval(
        """
        UPDATE kill_queue
        SET status = 'flagged', tagged_at = NOW()
        WHERE id = $1 AND status = 'pending'
        RETURNING id
        """,
        kill_queue_id,
    )
    if not claimed:
        logger.debug("kill_queued: %s already claimed, skip", kill_queue_id)
        return

    # 2. Mark the inbox dead. Guarded by inbox_state='live' so re-runs
    #    don't reset the state of an already-dead inbox.
    updated = await conn.fetchval(
        """
        UPDATE sender_accounts
        SET inbox_state = 'dead',
            kill_trigger = $2::kill_trigger_type,
            killed_at = NOW(),
            inventory_pool_status = NULL,
            inventory_lifecycle_status = 'dead',
            updated_at = NOW()
        WHERE id = $1 AND inbox_state = 'live'
        RETURNING email_address
        """,
        inbox_id, trigger_type,
    )
    if not updated:
        logger.warning(
            "kill_queued: inbox %s already not-live; kill_queue marked flagged but no DB transition",
            inbox_id,
        )
        return

    # 3 + 4. Enqueue tag ops for the Tier 2 batch worker. Per ADR-006,
    #        workspace_id is required (CHECK constraint enforces).
    flagged_tag = f'flagged_{trigger_type}'

    if not workspace_id:
        # Fall back to fetching from inbox if payload didn't carry it
        inbox = await fetch_inbox(conn, inbox_id)
        workspace_id = inbox['workspace_id'] if inbox else None

    if not workspace_id:
        logger.error(
            "kill_queued: cannot enqueue tag ops for %s — workspace_id missing",
            inbox_id,
        )
        return

    triggered_by = event.get('id')
    if triggered_by and isinstance(triggered_by, str):
        triggered_by = UUID(triggered_by)

    await enqueue_tag_op(
        conn,
        op='attach',
        inbox_id=inbox_id,
        workspace_id=workspace_id,
        tag_name=flagged_tag,
        triggered_by_event_id=triggered_by,
    )
    await enqueue_tag_op(
        conn,
        op='remove',
        inbox_id=inbox_id,
        workspace_id=workspace_id,
        tag_name='live',
        triggered_by_event_id=triggered_by,
    )

    logger.info(
        "kill_queued: %s killed (trigger=%s); tag ops enqueued",
        updated, trigger_type,
    )


async def inbox_died_handler(event: Dict, conn: asyncpg.Connection) -> None:
    """An inbox transitioned to 'dead'. Fill the resulting deficit by
    promoting a reserve (if the workspace has a package configured).

    The event_listener passes a fresh pool connection. We use it both
    for resolving workspace target and for the promote_to_target call.

    promote_to_target is shared between:
      - This handler (event-driven, fires immediately)
      - WorkspaceWriteOrchestrator._maintain_pool_thresholds (poll, every 60s)

    Both paths produce identical outcomes; this one's just faster.

    Workspaces with package_id=NULL or pause_pool_transitions=TRUE
    silently skip. Polling backstop continues to handle those (which
    is the right thing — operator hasn't opted into proactive promotion).
    """
    from sync_modules.pool_promotion import (
        get_workspace_promotion_target,
        promote_to_target,
    )

    workspace_id = event.get('workspace_id')
    if isinstance(workspace_id, str):
        workspace_id = UUID(workspace_id)

    if not workspace_id:
        logger.warning("inbox_died: missing workspace_id, skip")
        return

    target = await get_workspace_promotion_target(conn, workspace_id)
    if target is None:
        # No package set or paused. Polling backstop handles latent-capacity
        # warnings; nothing for events to do here.
        return

    # Use the connection's pool for promote_to_target — it expects a Pool,
    # not a Connection, because promote_inbox_to_deployed acquires its own
    # connection for the transactional UPDATE+INSERT pattern.
    pool = conn._holder._pool if hasattr(conn, '_holder') else None
    if pool is None:
        # Fallback for tests / direct conn use: just log (poll handles it)
        logger.warning(
            "inbox_died: handler couldn't access pool from conn (test context?), "
            "polling will handle promotion"
        )
        return

    result = await promote_to_target(
        pool, workspace_id, target,
        triggered_by='event_driven_inbox_died',
        rotation_type='promote',
        reason='kill_replacement',
    )

    if result['promoted']:
        logger.info(
            "inbox_died: promoted %d reserve(s) for workspace %s (target=%d, was deficit=%d)",
            result['promoted'], workspace_id, target, result['deficit_at_decision'],
        )
    elif result['no_candidates'] and result['deficit_at_decision'] > 0:
        logger.warning(
            "inbox_died: workspace %s has deficit=%d but no promotable reserves",
            workspace_id, result['deficit_at_decision'],
        )
