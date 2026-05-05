"""
Gate 2: TagOpWorker (Tier 2 batch worker) tests.

Plan: docs/plans/event-driven-architecture.md § "Tier 2 — EB tag synchronization"

Tests cover:
  - Single attach → bulk EB call → event marked completed
  - Multiple events same tag → single bulk EB call (not N individual)
  - Multiple workspaces → separate sessions (per-workspace partitioning)
  - EB API failure → events marked failed with retry_after
  - Inbox missing emailbison_account_id → just that event marked failed
  - Idempotency: re-running on completed events is a no-op
  - Workspace-level isolation: workspace A's failure doesn't break B

Uses testcontainers Postgres + FakeEmailBisonClient. Skips locally
without Docker; runs in CI.

Note on production wiring: TagOpWorker uses
EmailBisonClient(api_key=..., is_workspace_scoped=True). Tests inject
FakeEmailBisonClient via monkeypatch on the EmailBisonClient class.
"""
from __future__ import annotations

import json
import uuid
from typing import Dict, List
from unittest.mock import patch

import asyncpg
import pytest
import pytest_asyncio

from sync_modules.tag_op_worker import TagOpWorker
from sync_modules.audit_logger import AuditLogger
from sync_modules.slack_alerter import SlackAlerter

from tests.fakes import FakeEmailBisonClient, FakeEBError


pytestmark = pytest.mark.asyncio


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────
async def _make_workspace_with_key(pool, name: str, eb_id: int, key: str = "fake-key"):
    ws_id = await pool.fetchval(
        """
        INSERT INTO workspaces (workspace_name, is_active, emailbison_workspace_id)
        VALUES ($1, TRUE, $2) RETURNING id
        """,
        name, eb_id,
    )
    await pool.execute(
        """
        INSERT INTO workspace_api_keys (
            workspace_id, emailbison_workspace_id, key_name, key_token, is_active
        ) VALUES ($1, $2, 'test', $3, TRUE)
        """,
        ws_id, eb_id, key,
    )
    return ws_id


async def _make_inbox(
    pool, ws_id, *,
    eb_account_id: int,
    email: str = None,
):
    """Create a minimal active inbox with emailbison_account_id set."""
    if email is None:
        email = f'i{eb_account_id}@test.example'
    # Domains required for FK; create one inline
    dom_id = await pool.fetchval(
        """
        INSERT INTO domains (domain_name, workspace_id, pool_status, is_active, infrastructure_type)
        VALUES ($1, $2, 'live', TRUE, 'google') RETURNING id
        """,
        f'd{eb_account_id}.test.example', ws_id,
    )
    return await pool.fetchval(
        """
        INSERT INTO sender_accounts (
            email_address, workspace_id, domain_id, esp,
            emailbison_account_id, status,
            inbox_state, is_active,
            inventory_lifecycle_status, inventory_pool_status,
            warmup_enabled, health_score, first_seen_at
        ) VALUES (
            $1, $2, $3, 'gmail',
            $4, 'Connected', 'live', TRUE,
            'active', 'live', TRUE, 100, NOW()
        ) RETURNING id
        """,
        email, ws_id, dom_id, eb_account_id,
    )


async def _enqueue_tag_op(
    pool, *, op: str, inbox_id, workspace_id, tag_name: str,
):
    """Insert a pending tag_op event (skipping the trigger path) into event_log."""
    return await pool.fetchval(
        """
        INSERT INTO event_log (
            event_type, entity_type, entity_id,
            payload, status, workspace_id
        ) VALUES (
            $1, 'inbox', $2, $3::jsonb, 'pending', $4
        ) RETURNING id
        """,
        f'tag_op_{op}',
        inbox_id,
        json.dumps({'inbox_id': str(inbox_id), 'tag_name': tag_name}),
        workspace_id,
    )


def _audit_logger(pool):
    return AuditLogger(pool)


def _alerter():
    return SlackAlerter(webhook_url="")


def _patch_eb_client(fake_client):
    """Monkeypatch EmailBisonClient construction inside tag_op_worker
    to return our fake. The fake supports `async with`."""
    return patch(
        'sync_modules.tag_op_worker.EmailBisonClient',
        return_value=fake_client,
    )


# ──────────────────────────────────────────────────────────────────────────
# Test 1: single attach → bulk EB call → event completed
# ──────────────────────────────────────────────────────────────────────────
async def test_single_attach_completes_event(db_pool):
    ws_id = await _make_workspace_with_key(db_pool, "ws-tow-1", 7001)
    inbox_id = await _make_inbox(db_pool, ws_id, eb_account_id=70001)
    ev_id = await _enqueue_tag_op(
        db_pool, op='attach', inbox_id=inbox_id,
        workspace_id=ws_id, tag_name='flagged_hard_bounce_rate_lifetime',
    )

    fake = FakeEmailBisonClient()
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with _patch_eb_client(fake):
        await worker.run_once()

    # Event marked completed
    row = await db_pool.fetchrow(
        "SELECT status, handler_completed_at FROM event_log WHERE id = $1", ev_id,
    )
    assert row['status'] == 'completed'
    assert row['handler_completed_at'] is not None

    # EB received exactly one bulk attach with one inbox
    bulk_calls = fake.calls_named('tag_inboxes_bulk')
    assert len(bulk_calls) == 1
    assert bulk_calls[0].kwargs['account_ids'] == (70001,)
    # Tag name resolved + applied
    assert 'flagged_hard_bounce_rate_lifetime' in fake.tags
    assert fake.tags['flagged_hard_bounce_rate_lifetime'] in fake.inbox_tags[70001]


# ──────────────────────────────────────────────────────────────────────────
# Test 2: multiple events same tag → single bulk call
# ──────────────────────────────────────────────────────────────────────────
async def test_multiple_attaches_same_tag_bulk_into_one_call(db_pool):
    ws_id = await _make_workspace_with_key(db_pool, "ws-tow-2", 7002)
    inbox_a = await _make_inbox(db_pool, ws_id, eb_account_id=70011)
    inbox_b = await _make_inbox(db_pool, ws_id, eb_account_id=70012)
    inbox_c = await _make_inbox(db_pool, ws_id, eb_account_id=70013)

    for ib in (inbox_a, inbox_b, inbox_c):
        await _enqueue_tag_op(
            db_pool, op='attach', inbox_id=ib,
            workspace_id=ws_id, tag_name='live',
        )

    fake = FakeEmailBisonClient()
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with _patch_eb_client(fake):
        await worker.run_once()

    # ONE bulk call with three account_ids
    bulk_calls = fake.calls_named('tag_inboxes_bulk')
    assert len(bulk_calls) == 1
    account_ids = bulk_calls[0].kwargs['account_ids']
    assert set(account_ids) == {70011, 70012, 70013}

    # All three events completed
    completed = await db_pool.fetchval(
        """
        SELECT COUNT(*) FROM event_log
        WHERE workspace_id = $1 AND event_type = 'tag_op_attach'
          AND status = 'completed'
        """,
        ws_id,
    )
    assert completed == 3


# ──────────────────────────────────────────────────────────────────────────
# Test 3: separate workspaces use separate sessions
# ──────────────────────────────────────────────────────────────────────────
async def test_multiple_workspaces_get_separate_sessions(db_pool):
    """Each workspace must use its own EB client (per ADR-006).

    We can't easily distinguish two FakeEmailBisonClient instances at the
    constructor patch level, so we assert that EmailBisonClient was
    constructed once per workspace (not once globally).
    """
    ws_a = await _make_workspace_with_key(db_pool, "ws-tow-3a", 7031, key="key-a")
    ws_b = await _make_workspace_with_key(db_pool, "ws-tow-3b", 7032, key="key-b")
    inbox_a = await _make_inbox(db_pool, ws_a, eb_account_id=70031)
    inbox_b = await _make_inbox(db_pool, ws_b, eb_account_id=70032)

    await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_a, workspace_id=ws_a, tag_name='live')
    await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_b, workspace_id=ws_b, tag_name='live')

    fake = FakeEmailBisonClient()
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with patch('sync_modules.tag_op_worker.EmailBisonClient') as eb_cls:
        eb_cls.return_value = fake  # both workspaces get the same fake instance
        await worker.run_once()

    # EmailBisonClient constructor called once per workspace, with workspace-scoped keys.
    assert eb_cls.call_count == 2
    keys_used = {call.kwargs.get('api_key') for call in eb_cls.call_args_list}
    assert keys_used == {'key-a', 'key-b'}, \
        f"each workspace must use its own scoped key (per ADR-006), got {keys_used}"


# ──────────────────────────────────────────────────────────────────────────
# Test 4: EB API failure → events marked failed with retry_after
# ──────────────────────────────────────────────────────────────────────────
async def test_eb_failure_marks_events_failed_with_retry_after(db_pool):
    ws_id = await _make_workspace_with_key(db_pool, "ws-tow-4", 7004)
    inbox_id = await _make_inbox(db_pool, ws_id, eb_account_id=70041)
    ev_id = await _enqueue_tag_op(
        db_pool, op='attach', inbox_id=inbox_id,
        workspace_id=ws_id, tag_name='flagged_spam_complaint',
    )

    fake = FakeEmailBisonClient()
    fake.fail_on('tag_inboxes_bulk', message='simulated 500 error')
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with _patch_eb_client(fake):
        await worker.run_once()

    row = await db_pool.fetchrow(
        """
        SELECT status, error_message, retry_count, retry_after
        FROM event_log WHERE id = $1
        """,
        ev_id,
    )
    assert row['status'] == 'failed'
    assert 'simulated 500 error' in row['error_message']
    assert row['retry_count'] == 1
    assert row['retry_after'] is not None  # exponential backoff scheduled


# ──────────────────────────────────────────────────────────────────────────
# Test 5: inbox missing emailbison_account_id → just that event fails
# ──────────────────────────────────────────────────────────────────────────
async def test_inbox_missing_eb_account_id_fails_only_that_event(db_pool):
    ws_id = await _make_workspace_with_key(db_pool, "ws-tow-5", 7005)
    # inbox_a has eb_account_id; inbox_b does not
    inbox_a = await _make_inbox(db_pool, ws_id, eb_account_id=70051)
    inbox_b = await db_pool.fetchval(
        """
        INSERT INTO sender_accounts (
            email_address, workspace_id, domain_id, esp,
            emailbison_account_id, status,
            inbox_state, is_active,
            inventory_lifecycle_status, inventory_pool_status,
            warmup_enabled, health_score, first_seen_at
        )
        SELECT 'noeb@test.example', $1, d.id, 'gmail',
               NULL, 'Connected', 'live', TRUE,
               'active', 'live', TRUE, 100, NOW()
        FROM domains d WHERE d.workspace_id = $1 LIMIT 1
        RETURNING id
        """,
        ws_id,
    )

    ev_a = await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_a, workspace_id=ws_id, tag_name='live')
    ev_b = await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_b, workspace_id=ws_id, tag_name='live')

    fake = FakeEmailBisonClient()
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with _patch_eb_client(fake):
        await worker.run_once()

    # ev_a (good inbox) completed; ev_b (no eb_account_id) failed
    statuses = {
        r['id']: r['status']
        for r in await db_pool.fetch(
            "SELECT id, status FROM event_log WHERE id = ANY($1::uuid[])",
            [ev_a, ev_b],
        )
    }
    assert statuses[ev_a] == 'completed'
    assert statuses[ev_b] == 'failed'

    # The bulk call only included the good inbox
    bulk_calls = fake.calls_named('tag_inboxes_bulk')
    assert len(bulk_calls) == 1
    assert bulk_calls[0].kwargs['account_ids'] == (70051,)


# ──────────────────────────────────────────────────────────────────────────
# Test 6: idempotency — re-running on completed events is a no-op
# ──────────────────────────────────────────────────────────────────────────
async def test_idempotent_completed_events_not_reprocessed(db_pool):
    ws_id = await _make_workspace_with_key(db_pool, "ws-tow-6", 7006)
    inbox_id = await _make_inbox(db_pool, ws_id, eb_account_id=70061)
    await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_id, workspace_id=ws_id, tag_name='live')

    fake = FakeEmailBisonClient()
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with _patch_eb_client(fake):
        await worker.run_once()
        # Second cycle — should find no pending events and make no EB calls
        await worker.run_once()

    bulk_calls = fake.calls_named('tag_inboxes_bulk')
    assert len(bulk_calls) == 1, "Second cycle must not re-issue EB calls"


# ──────────────────────────────────────────────────────────────────────────
# Test 7: workspace-level isolation — A's failure doesn't break B
# ──────────────────────────────────────────────────────────────────────────
async def test_workspace_failure_isolated(db_pool):
    """Workspace A's EB call fails; workspace B succeeds. They must not
    affect each other (per ADR-006 partitioning)."""
    ws_a = await _make_workspace_with_key(db_pool, "ws-tow-7a", 7071, key="key-a")
    ws_b = await _make_workspace_with_key(db_pool, "ws-tow-7b", 7072, key="key-b")
    inbox_a = await _make_inbox(db_pool, ws_a, eb_account_id=70071)
    inbox_b = await _make_inbox(db_pool, ws_b, eb_account_id=70072)
    ev_a = await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_a, workspace_id=ws_a, tag_name='live')
    ev_b = await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_b, workspace_id=ws_b, tag_name='live')

    # Fake fails the FIRST tag_inboxes_bulk call (workspace A processes first
    # because alphabetical ordering by workspace_name in the SELECT)
    fake = FakeEmailBisonClient()
    fake.fail_on('tag_inboxes_bulk', message='workspace A fault')

    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())
    with _patch_eb_client(fake):
        await worker.run_once()

    statuses = {
        r['id']: r['status']
        for r in await db_pool.fetch(
            "SELECT id, status FROM event_log WHERE id = ANY($1::uuid[])",
            [ev_a, ev_b],
        )
    }
    # Exactly one workspace's event failed; the other completed.
    failed = [k for k, v in statuses.items() if v == 'failed']
    completed = [k for k, v in statuses.items() if v == 'completed']
    assert len(failed) == 1 and len(completed) == 1, (
        f"Workspaces must be isolated: one failure, one success. Got {statuses}"
    )


# ──────────────────────────────────────────────────────────────────────────
# Test 8: retry_after backoff respected — events not picked up until window passes
# ──────────────────────────────────────────────────────────────────────────
async def test_retry_after_skipped_until_window_passes(db_pool):
    """An event with retry_after in the future must be skipped this cycle."""
    ws_id = await _make_workspace_with_key(db_pool, "ws-tow-8", 7008)
    inbox_id = await _make_inbox(db_pool, ws_id, eb_account_id=70081)
    ev_id = await _enqueue_tag_op(
        db_pool, op='attach', inbox_id=inbox_id,
        workspace_id=ws_id, tag_name='live',
    )
    # Set retry_after one hour in the future
    await db_pool.execute(
        "UPDATE event_log SET retry_after = NOW() + INTERVAL '1 hour' WHERE id = $1",
        ev_id,
    )

    fake = FakeEmailBisonClient()
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with _patch_eb_client(fake):
        await worker.run_once()

    # No EB call made
    assert fake.calls_named('tag_inboxes_bulk') == []

    # Event still pending
    status = await db_pool.fetchval(
        "SELECT status FROM event_log WHERE id = $1", ev_id,
    )
    assert status == 'pending'


# ──────────────────────────────────────────────────────────────────────────
# Test 9: tag-id cache reused within one workspace cycle
# ──────────────────────────────────────────────────────────────────────────
async def test_tag_id_cache_within_workspace_cycle(db_pool):
    """Same tag used twice in one cycle should result in only ONE
    get_or_create_tag call (cache)."""
    ws_id = await _make_workspace_with_key(db_pool, "ws-tow-9", 7009)
    inbox_a = await _make_inbox(db_pool, ws_id, eb_account_id=70091)
    inbox_b = await _make_inbox(db_pool, ws_id, eb_account_id=70092)

    # Two attaches with the SAME tag — should bulk into one call
    # (already covered by test 2). Adding two REMOVES with same tag too,
    # which produces a second group with same tag_name; cache should
    # prevent a second get_or_create.
    await _enqueue_tag_op(db_pool, op='attach', inbox_id=inbox_a, workspace_id=ws_id, tag_name='live')
    await _enqueue_tag_op(db_pool, op='remove', inbox_id=inbox_b, workspace_id=ws_id, tag_name='live')

    fake = FakeEmailBisonClient()
    worker = TagOpWorker(db_pool, _audit_logger(db_pool), _alerter())

    with _patch_eb_client(fake):
        await worker.run_once()

    # get_or_create_tag should have been called exactly once for 'live'
    # (cached for the second use)
    calls = [c for c in fake.calls_named('get_or_create_tag') if c.args == ('live',)]
    assert len(calls) == 1, f"Tag cache failed: {len(calls)} get_or_create calls for 'live'"


# ──────────────────────────────────────────────────────────────────────────
# Test 10: workspace_id NOT NULL constraint on tag_op events
# ──────────────────────────────────────────────────────────────────────────
async def test_tag_op_without_workspace_id_rejected_at_db_layer(db_pool):
    """Direct INSERT without workspace_id must fail (CHECK constraint).
    This is the load-bearing rule from ADR-006."""
    inbox_id = uuid.uuid4()
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await db_pool.execute(
            """
            INSERT INTO event_log (
                event_type, entity_type, entity_id, payload, status, workspace_id
            ) VALUES (
                'tag_op_attach', 'inbox', $1, '{}'::jsonb, 'pending', NULL
            )
            """,
            inbox_id,
        )
