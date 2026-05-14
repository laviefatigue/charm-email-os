"""
Gate 2: handler idempotency tests for the event-driven architecture.

Plan: docs/plans/event-driven-architecture.md § "Gate 2 — Handler idempotency"

For each handler, test:
  1. Happy-path: handler produces the expected DB state given an event
  2. Idempotency: running the handler twice on the same event produces
     the same final state, no double side effects
  3. Pre-condition guard: handler bails when the row is no longer
     in the expected state (e.g., inbox already dead)

Uses testcontainers Postgres fixture from conftest.py — requires Docker
to run locally; skips otherwise.

Phase 2 handlers covered:
  - bounce_observed_handler  (full impl)
  - kill_queued_handler      (full impl)
  - pool_changed_handler     (full impl)
  - domain_burned_handler    (full impl)

Phase 3 handlers (currently stubs in Phase 2) get tests when the
real implementations land:
  - inbox_died_handler       (Phase 3: wires pool_promotion.promote_one)
  - package_assigned_handler (Phase 3: wires maintain_pool_thresholds_one)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest
import pytest_asyncio

from sync_modules.event_handlers.kill_chain import (
    bounce_observed_handler,
    kill_queued_handler,
)
from sync_modules.event_handlers.lifecycle import (
    pool_changed_handler,
)
from sync_modules.event_handlers.domain import (
    domain_burned_handler,
)


pytestmark = pytest.mark.asyncio


# ──────────────────────────────────────────────────────────────────────────
# Fixture helpers (same patterns as test_event_triggers.py)
# ──────────────────────────────────────────────────────────────────────────
async def _make_workspace(pool, name="ws-handlers", eb_id=8888):
    return await pool.fetchval(
        """
        INSERT INTO workspaces (workspace_name, is_active, emailbison_workspace_id)
        VALUES ($1, TRUE, $2) RETURNING id
        """,
        name, eb_id,
    )


async def _make_domain(pool, ws_id, name="hndlr.example"):
    return await pool.fetchval(
        """
        INSERT INTO domains (domain_name, workspace_id, pool_status, is_active, infrastructure_type)
        VALUES ($1, $2, 'live', TRUE, 'google') RETURNING id
        """,
        name, ws_id,
    )


async def _make_inbox(
    pool, ws_id, dom_id,
    *, email="i@hndlr.example", eb_id=22000,
    inbox_state="live", pool_status="live",
    emails_sent=200, complaints=0,
):
    return await pool.fetchval(
        """
        INSERT INTO sender_accounts (
            email_address, workspace_id, domain_id, esp,
            emailbison_account_id, status,
            inbox_state, is_active,
            inventory_lifecycle_status, inventory_pool_status,
            warmup_enabled, warmup_started_at,
            emails_sent_all_time, complaints_lifetime,
            health_score, first_seen_at
        ) VALUES (
            $1, $2, $3, 'gmail',
            $4, 'Connected',
            $5, TRUE,
            'active', $6,
            TRUE, NOW() - INTERVAL '14 days',
            $7, $8,
            100, NOW()
        ) RETURNING id
        """,
        email, ws_id, dom_id, eb_id, inbox_state, pool_status, emails_sent, complaints,
    )


async def _seed_bounces(pool, ws_id, inbox_id, *, hard_blocked=0, hard_unknown=0):
    """Insert N hard bounces into response_messages."""
    for i in range(hard_blocked):
        await pool.execute(
            """
            INSERT INTO response_messages (
                sender_account_id, workspace_id, folder, bounce_type,
                emailbison_reply_id, campaign_id, received_at
            ) VALUES ($1, $2, 'bounced', 'hard_blocked', $3, NULL, NOW() - INTERVAL '1 hour')
            """,
            inbox_id, ws_id, f'eb-blk-{inbox_id}-{i}',
        )
    for i in range(hard_unknown):
        await pool.execute(
            """
            INSERT INTO response_messages (
                sender_account_id, workspace_id, folder, bounce_type,
                emailbison_reply_id, campaign_id, received_at
            ) VALUES ($1, $2, 'bounced', 'hard_unknown', $3, NULL, NOW() - INTERVAL '1 hour')
            """,
            inbox_id, ws_id, f'eb-unk-{inbox_id}-{i}',
        )


def _make_event(event_type, entity_id, payload, workspace_id=None):
    """Build an event dict the same shape the listener would pass."""
    return {
        'id': uuid.uuid4(),
        'event_type': event_type,
        'entity_type': 'inbox',  # not validated by handlers
        'entity_id': entity_id,
        'payload': payload,
        'workspace_id': workspace_id,
        'status': 'processing',
    }


# ──────────────────────────────────────────────────────────────────────────
# bounce_observed_handler
# ──────────────────────────────────────────────────────────────────────────
async def test_bounce_observed_queues_kill_when_rate_exceeds_threshold(db_pool):
    """11 hard bounces / 100 sends = 11% > 5% → should queue kill."""
    ws_id = await _make_workspace(db_pool, "ws-boh-1", eb_id=8801)
    dom_id = await _make_domain(db_pool, ws_id, "boh1.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id, eb_id=22001, emails_sent=100,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=11)

    event = _make_event(
        'bounce_observed', uuid.uuid4(),
        {'sender_account_id': str(inbox_id), 'bounce_type': 'hard_blocked'},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await bounce_observed_handler(event, conn)

    # Assert kill_queue row was created
    rows = await db_pool.fetch(
        """
        SELECT trigger_type::text AS trigger_type, status
        FROM kill_queue WHERE inbox_id = $1
        """,
        inbox_id,
    )
    assert len(rows) == 1
    assert rows[0]['trigger_type'] == 'hard_bounce_rate_lifetime'
    assert rows[0]['status'] == 'pending'


async def test_bounce_observed_does_not_queue_below_floor(db_pool):
    """19 sends < 20 floor → handler bails, no kill_queue row."""
    ws_id = await _make_workspace(db_pool, "ws-boh-2", eb_id=8802)
    dom_id = await _make_domain(db_pool, ws_id, "boh2.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id, eb_id=22002, emails_sent=19,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=5)

    event = _make_event(
        'bounce_observed', uuid.uuid4(),
        {'sender_account_id': str(inbox_id), 'bounce_type': 'hard_blocked'},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await bounce_observed_handler(event, conn)

    count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM kill_queue WHERE inbox_id = $1", inbox_id,
    )
    assert count == 0


async def test_bounce_observed_idempotent(db_pool):
    """Running the handler twice for the same inbox produces ONE kill_queue row."""
    ws_id = await _make_workspace(db_pool, "ws-boh-3", eb_id=8803)
    dom_id = await _make_domain(db_pool, ws_id, "boh3.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id, eb_id=22003, emails_sent=100,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=11)

    event = _make_event(
        'bounce_observed', uuid.uuid4(),
        {'sender_account_id': str(inbox_id), 'bounce_type': 'hard_blocked'},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await bounce_observed_handler(event, conn)
        await bounce_observed_handler(event, conn)  # second run

    count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM kill_queue WHERE inbox_id = $1", inbox_id,
    )
    assert count == 1, "Idempotent — re-running must not double-queue"


# ──────────────────────────────────────────────────────────────────────────
# kill_queued_handler
# ──────────────────────────────────────────────────────────────────────────
async def test_kill_queued_marks_inbox_dead_and_enqueues_tag_ops(db_pool):
    """Happy path: kill_queue row → inbox dead + tag ops queued."""
    ws_id = await _make_workspace(db_pool, "ws-kqh-1", eb_id=8811)
    dom_id = await _make_domain(db_pool, ws_id, "kqh1.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=22011)

    kq_id = await db_pool.fetchval(
        """
        INSERT INTO kill_queue (
            inbox_id, workspace_id,
            trigger_type, trigger_value, trigger_threshold
        ) VALUES (
            $1, $2,
            'hard_bounce_rate_lifetime'::kill_trigger_type, 0.10, 0.05
        ) RETURNING id
        """,
        inbox_id, ws_id,
    )

    event = _make_event(
        'kill_queued', kq_id,
        {
            'inbox_id': str(inbox_id),
            'trigger_type': 'hard_bounce_rate_lifetime',
            'workspace_id': str(ws_id),
        },
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await kill_queued_handler(event, conn)

    # Inbox is dead with the right trigger.
    # Plan F (2026-05-08): warmup_enabled also flips to FALSE in the same
    # transaction, atomic with the kill mark.
    inbox = await db_pool.fetchrow(
        """
        SELECT inbox_state, kill_trigger::text AS kill_trigger,
               inventory_pool_status, inventory_lifecycle_status::text AS lifecycle,
               warmup_enabled
        FROM sender_accounts WHERE id = $1
        """,
        inbox_id,
    )
    assert inbox['inbox_state'] == 'dead'
    assert inbox['kill_trigger'] == 'hard_bounce_rate_lifetime'
    assert inbox['inventory_pool_status'] is None
    assert inbox['lifecycle'] == 'dead'
    assert inbox['warmup_enabled'] is False  # Plan F: warmup off on kill

    # kill_queue marked flagged
    kq = await db_pool.fetchrow(
        "SELECT status, tagged_at FROM kill_queue WHERE id = $1", kq_id,
    )
    assert kq['status'] == 'flagged'
    assert kq['tagged_at'] is not None

    # Tag ops enqueued (one attach for flagged_*, one remove for live)
    # plus one warmup_disable event (Plan F).
    workspace_events = await db_pool.fetch(
        """
        SELECT event_type, status, workspace_id
        FROM event_log
        WHERE entity_id = $1
          AND event_type IN ('tag_op_attach', 'tag_op_remove', 'warmup_disable')
        ORDER BY emitted_at
        """,
        inbox_id,
    )
    assert len(workspace_events) == 3
    op_types = {r['event_type'] for r in workspace_events}
    assert 'tag_op_attach' in op_types
    assert 'tag_op_remove' in op_types
    assert 'warmup_disable' in op_types
    for op in workspace_events:
        assert op['status'] == 'pending'
        assert op['workspace_id'] == ws_id  # Per ADR-006: workspace-scoped


async def test_kill_queued_idempotent(db_pool):
    """Re-running on same kill_queue row is a no-op (status guard)."""
    ws_id = await _make_workspace(db_pool, "ws-kqh-2", eb_id=8812)
    dom_id = await _make_domain(db_pool, ws_id, "kqh2.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=22012)

    kq_id = await db_pool.fetchval(
        """
        INSERT INTO kill_queue (
            inbox_id, workspace_id, trigger_type, trigger_value, trigger_threshold
        ) VALUES ($1, $2, 'spam_complaint'::kill_trigger_type, 1, 1)
        RETURNING id
        """,
        inbox_id, ws_id,
    )

    event = _make_event(
        'kill_queued', kq_id,
        {
            'inbox_id': str(inbox_id),
            'trigger_type': 'spam_complaint',
            'workspace_id': str(ws_id),
        },
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await kill_queued_handler(event, conn)
        await kill_queued_handler(event, conn)  # second run

    # Should still have exactly 2 tag_op events (not 4)
    tag_op_count = await db_pool.fetchval(
        """
        SELECT COUNT(*) FROM event_log
        WHERE entity_id = $1 AND event_type LIKE 'tag_op_%'
        """,
        inbox_id,
    )
    assert tag_op_count == 2, "Idempotent: second run must not duplicate tag ops"


# ──────────────────────────────────────────────────────────────────────────
# pool_changed_handler
# ──────────────────────────────────────────────────────────────────────────
async def test_pool_changed_enqueues_attach_and_remove(db_pool):
    """reserve → live: enqueue tag_op_remove(reserve) + tag_op_attach(live)."""
    ws_id = await _make_workspace(db_pool, "ws-pch-1", eb_id=8821)
    dom_id = await _make_domain(db_pool, ws_id, "pch1.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id, eb_id=22021, pool_status='live',
    )

    event = _make_event(
        'pool_changed', inbox_id,
        {'old_pool': 'reserve', 'new_pool': 'live'},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await pool_changed_handler(event, conn)

    ops = await db_pool.fetch(
        """
        SELECT event_type, payload
        FROM event_log
        WHERE entity_id = $1 AND event_type LIKE 'tag_op_%'
        ORDER BY emitted_at
        """,
        inbox_id,
    )
    assert len(ops) == 2

    payloads = []
    for op in ops:
        p = op['payload'] if isinstance(op['payload'], dict) else json.loads(op['payload'])
        payloads.append((op['event_type'], p['tag_name']))

    assert ('tag_op_remove', 'reserve') in payloads
    assert ('tag_op_attach', 'live') in payloads


async def test_pool_changed_null_old_only_attaches(db_pool):
    """NULL → reserve: enqueue tag_op_attach only (nothing to remove)."""
    ws_id = await _make_workspace(db_pool, "ws-pch-2", eb_id=8822)
    dom_id = await _make_domain(db_pool, ws_id, "pch2.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id, eb_id=22022,
    )

    event = _make_event(
        'pool_changed', inbox_id,
        {'old_pool': None, 'new_pool': 'reserve'},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await pool_changed_handler(event, conn)

    ops = await db_pool.fetch(
        """
        SELECT event_type FROM event_log
        WHERE entity_id = $1 AND event_type LIKE 'tag_op_%'
        """,
        inbox_id,
    )
    assert len(ops) == 1
    assert ops[0]['event_type'] == 'tag_op_attach'


async def test_pool_changed_to_null_only_removes(db_pool):
    """live → NULL (e.g., on burned-domain cascade): only tag_op_remove."""
    ws_id = await _make_workspace(db_pool, "ws-pch-3", eb_id=8823)
    dom_id = await _make_domain(db_pool, ws_id, "pch3.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id, eb_id=22023,
    )

    event = _make_event(
        'pool_changed', inbox_id,
        {'old_pool': 'live', 'new_pool': None},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await pool_changed_handler(event, conn)

    ops = await db_pool.fetch(
        """
        SELECT event_type FROM event_log
        WHERE entity_id = $1 AND event_type LIKE 'tag_op_%'
        """,
        inbox_id,
    )
    assert len(ops) == 1
    assert ops[0]['event_type'] == 'tag_op_remove'


# ──────────────────────────────────────────────────────────────────────────
# domain_burned_handler
# ──────────────────────────────────────────────────────────────────────────
async def test_domain_burned_nulls_pool_status_for_all_inboxes(db_pool):
    """Burning a domain NULL-outs pool_status for every inbox on it.
    Each row UPDATE fires pool_changed, which enqueues tag_op_remove."""
    ws_id = await _make_workspace(db_pool, "ws-dbh-1", eb_id=8831)
    dom_id = await _make_domain(db_pool, ws_id, "dbh1.example")
    inbox_a = await _make_inbox(db_pool, ws_id, dom_id, eb_id=22031, email='a@dbh1.example', pool_status='live')
    inbox_b = await _make_inbox(db_pool, ws_id, dom_id, eb_id=22032, email='b@dbh1.example', pool_status='reserve')

    event = _make_event(
        'domain_burned', dom_id,
        {'domain_name': 'dbh1.example', 'burn_trigger': 'spam_complaint'},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await domain_burned_handler(event, conn)

    # Both inboxes pool_status NULL
    pools = await db_pool.fetch(
        "SELECT id, inventory_pool_status FROM sender_accounts WHERE domain_id = $1",
        dom_id,
    )
    assert all(p['inventory_pool_status'] is None for p in pools)


async def test_domain_burned_idempotent(db_pool):
    """Re-running on already-NULL inboxes is a no-op (the WHERE filter on
    UPDATE catches it)."""
    ws_id = await _make_workspace(db_pool, "ws-dbh-2", eb_id=8832)
    dom_id = await _make_domain(db_pool, ws_id, "dbh2.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=22033, pool_status='live')

    event = _make_event(
        'domain_burned', dom_id,
        {'domain_name': 'dbh2.example', 'burn_trigger': 'spam_complaint'},
        workspace_id=ws_id,
    )

    async with db_pool.acquire() as conn:
        await domain_burned_handler(event, conn)
        await domain_burned_handler(event, conn)  # second run

    # Should still be NULL (not crashed)
    pool = await db_pool.fetchval(
        "SELECT inventory_pool_status FROM sender_accounts WHERE id = $1", inbox_id,
    )
    assert pool is None
