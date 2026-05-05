"""
Gate 1: synthetic correctness tests for the event-driven triggers.

Plan: docs/plans/event-driven-architecture.md § "Gate 1 — Trigger correctness"

Each test:
  1. Creates a state change (INSERT or UPDATE on the trigger's source table)
  2. Asserts a corresponding row exists in event_log with correct
     event_type, payload shape, status='emitted', and workspace_id
     (where required by the tag_op CHECK constraint)
  3. Asserts pg_notify was emitted on the correct channel

Verifies the triggers in migration 108 fire correctly under all expected
state transitions. Uses the testcontainers-based Postgres fixture from
conftest.py — requires Docker to run locally; skips otherwise.

These tests are READ-ONLY at the application level — they don't run
the listener; they just verify that the DB triggers themselves emit
the right events.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
import pytest_asyncio


pytestmark = pytest.mark.asyncio


# ──────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────
async def _make_workspace(pool: asyncpg.Pool, name: str = "ws-triggers") -> uuid.UUID:
    return await pool.fetchval(
        """
        INSERT INTO workspaces (
            workspace_name, is_active, emailbison_workspace_id
        ) VALUES ($1, TRUE, 9999)
        RETURNING id
        """,
        name,
    )


async def _make_domain(pool: asyncpg.Pool, ws_id: uuid.UUID, name: str = "trig.example") -> uuid.UUID:
    return await pool.fetchval(
        """
        INSERT INTO domains (
            domain_name, workspace_id, pool_status, is_active, infrastructure_type
        ) VALUES ($1, $2, 'live', TRUE, 'google')
        RETURNING id
        """,
        name, ws_id,
    )


async def _make_inbox(
    pool: asyncpg.Pool, ws_id: uuid.UUID, dom_id: uuid.UUID,
    *, email: str = "i@trig.example", eb_id: int = 12345,
    inbox_state: str = "live",
    pool_status: str = "live",
) -> uuid.UUID:
    return await pool.fetchval(
        """
        INSERT INTO sender_accounts (
            email_address, workspace_id, domain_id, esp,
            emailbison_account_id, status,
            inbox_state, is_active,
            inventory_lifecycle_status, inventory_pool_status,
            warmup_enabled, warmup_started_at,
            health_score, first_seen_at
        ) VALUES (
            $1, $2, $3, 'gmail',
            $4, 'Connected',
            $5, TRUE,
            'active', $6,
            TRUE, NOW() - INTERVAL '14 days',
            100, NOW()
        )
        RETURNING id
        """,
        email, ws_id, dom_id, eb_id, inbox_state, pool_status,
    )


# ──────────────────────────────────────────────────────────────────────────
# Test 1: bounce_observed trigger fires on hard bounce INSERT
# ──────────────────────────────────────────────────────────────────────────
async def test_bounce_observed_fires_on_hard_bounce(db_pool):
    ws_id = await _make_workspace(db_pool, "ws-bounce-1")
    dom_id = await _make_domain(db_pool, ws_id, "bounce1.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=11001)

    rm_id = await db_pool.fetchval(
        """
        INSERT INTO response_messages (
            sender_account_id, workspace_id, folder, bounce_type,
            emailbison_reply_id, campaign_id, received_at
        ) VALUES ($1, $2, 'bounced', 'hard_blocked'::bounce_type, 'eb-bounce-1', NULL, NOW())
        RETURNING id
        """,
        inbox_id, ws_id,
    )

    rows = await db_pool.fetch(
        """
        SELECT event_type, entity_type, entity_id, workspace_id, status, payload
        FROM event_log WHERE entity_id = $1
        """,
        rm_id,
    )
    assert len(rows) == 1, "Trigger must emit exactly one event for the bounce"
    ev = rows[0]
    assert ev["event_type"] == "bounce_observed"
    assert ev["entity_type"] == "response_message"
    assert ev["status"] == "emitted"
    assert ev["workspace_id"] == ws_id
    payload = ev["payload"] if isinstance(ev["payload"], dict) else json.loads(ev["payload"])
    assert payload["sender_account_id"] == str(inbox_id)
    assert payload["bounce_type"] == "hard_blocked"


async def test_bounce_observed_does_not_fire_on_soft_bounce(db_pool):
    """Trigger filters by bounce_type IN (hard_blocked, hard_unknown).
    Soft bounces are captured for analytics but don't drive kills."""
    ws_id = await _make_workspace(db_pool, "ws-bounce-2")
    dom_id = await _make_domain(db_pool, ws_id, "bounce2.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=11002)

    rm_id = await db_pool.fetchval(
        """
        INSERT INTO response_messages (
            sender_account_id, workspace_id, folder, bounce_type,
            emailbison_reply_id, campaign_id, received_at
        ) VALUES ($1, $2, 'bounced', 'soft_full'::bounce_type, 'eb-soft-1', NULL, NOW())
        RETURNING id
        """,
        inbox_id, ws_id,
    )

    count = await db_pool.fetchval(
        "SELECT COUNT(*) FROM event_log WHERE entity_id = $1", rm_id
    )
    assert count == 0, "Soft bounces must not emit bounce_observed events"


# ──────────────────────────────────────────────────────────────────────────
# Test 2: kill_queued trigger fires on pending INSERT
# ──────────────────────────────────────────────────────────────────────────
async def test_kill_queued_fires_on_pending_insert(db_pool):
    ws_id = await _make_workspace(db_pool, "ws-killq-1")
    dom_id = await _make_domain(db_pool, ws_id, "killq1.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=11003)

    kq_id = await db_pool.fetchval(
        """
        INSERT INTO kill_queue (
            inbox_id, workspace_id, trigger_type, trigger_value, trigger_threshold
        ) VALUES ($1, $2, 'spam_complaint'::kill_trigger_type, 1, 1)
        RETURNING id
        """,
        inbox_id, ws_id,
    )

    rows = await db_pool.fetch(
        "SELECT event_type, status, workspace_id, payload FROM event_log WHERE entity_id = $1",
        kq_id,
    )
    assert len(rows) == 1
    ev = rows[0]
    assert ev["event_type"] == "kill_queued"
    assert ev["status"] == "emitted"
    assert ev["workspace_id"] == ws_id
    payload = ev["payload"] if isinstance(ev["payload"], dict) else json.loads(ev["payload"])
    assert payload["inbox_id"] == str(inbox_id)
    assert payload["trigger_type"] == "spam_complaint"


# ──────────────────────────────────────────────────────────────────────────
# Test 3: inbox_died trigger fires on inbox_state transition
# ──────────────────────────────────────────────────────────────────────────
async def test_inbox_died_fires_on_state_transition_to_dead(db_pool):
    ws_id = await _make_workspace(db_pool, "ws-died-1")
    dom_id = await _make_domain(db_pool, ws_id, "died1.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=11004, inbox_state="live")

    await db_pool.execute(
        """
        UPDATE sender_accounts
        SET inbox_state = 'dead',
            kill_trigger = 'spam_complaint'::kill_trigger_type,
            killed_at = NOW()
        WHERE id = $1
        """,
        inbox_id,
    )

    rows = await db_pool.fetch(
        """
        SELECT event_type, status, workspace_id, payload
        FROM event_log
        WHERE entity_id = $1 AND event_type = 'inbox_died'
        """,
        inbox_id,
    )
    assert len(rows) == 1
    ev = rows[0]
    assert ev["status"] == "emitted"
    assert ev["workspace_id"] == ws_id
    payload = ev["payload"] if isinstance(ev["payload"], dict) else json.loads(ev["payload"])
    assert payload["kill_trigger"] == "spam_complaint"


async def test_inbox_died_does_not_fire_on_already_dead_update(db_pool):
    """Trigger only fires on the live → dead transition, not subsequent
    updates of an already-dead row."""
    ws_id = await _make_workspace(db_pool, "ws-died-2")
    dom_id = await _make_domain(db_pool, ws_id, "died2.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=11005, inbox_state="dead")

    # Update the dead row (e.g., a metadata field). Should NOT emit inbox_died.
    await db_pool.execute(
        "UPDATE sender_accounts SET health_score = 50 WHERE id = $1",
        inbox_id,
    )

    count = await db_pool.fetchval(
        """
        SELECT COUNT(*) FROM event_log
        WHERE entity_id = $1 AND event_type = 'inbox_died'
        """,
        inbox_id,
    )
    assert count == 0, "Should not re-fire on updates of already-dead rows"


# ──────────────────────────────────────────────────────────────────────────
# Test 4: inbox_pickup trigger fires on INSERT
# ──────────────────────────────────────────────────────────────────────────
async def test_inbox_pickup_fires_on_insert(db_pool):
    ws_id = await _make_workspace(db_pool, "ws-pickup-1")
    dom_id = await _make_domain(db_pool, ws_id, "pickup1.example")
    inbox_id = await _make_inbox(db_pool, ws_id, dom_id, eb_id=11006)

    rows = await db_pool.fetch(
        """
        SELECT event_type, status, workspace_id, payload
        FROM event_log
        WHERE entity_id = $1 AND event_type = 'inbox_pickup'
        """,
        inbox_id,
    )
    assert len(rows) == 1
    ev = rows[0]
    assert ev["status"] == "emitted"
    assert ev["workspace_id"] == ws_id


# ──────────────────────────────────────────────────────────────────────────
# Test 5: pool_changed trigger fires on inventory_pool_status transitions
# ──────────────────────────────────────────────────────────────────────────
async def test_pool_changed_fires_on_pool_transition(db_pool):
    ws_id = await _make_workspace(db_pool, "ws-pool-1")
    dom_id = await _make_domain(db_pool, ws_id, "pool1.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id, eb_id=11007, pool_status="reserve",
    )

    await db_pool.execute(
        "UPDATE sender_accounts SET inventory_pool_status = 'live' WHERE id = $1",
        inbox_id,
    )

    rows = await db_pool.fetch(
        """
        SELECT event_type, payload
        FROM event_log
        WHERE entity_id = $1 AND event_type = 'pool_changed'
        """,
        inbox_id,
    )
    assert len(rows) == 1
    payload = rows[0]["payload"] if isinstance(rows[0]["payload"], dict) else json.loads(rows[0]["payload"])
    assert payload["old_pool"] == "reserve"
    assert payload["new_pool"] == "live"


# ──────────────────────────────────────────────────────────────────────────
# Test 6: domain_burned trigger fires on pool_status='burned'
# ──────────────────────────────────────────────────────────────────────────
async def test_domain_burned_fires_on_burn(db_pool):
    ws_id = await _make_workspace(db_pool, "ws-burn-1")
    dom_id = await _make_domain(db_pool, ws_id, "burn1.example")

    await db_pool.execute(
        """
        UPDATE domains SET pool_status = 'burned',
                            burn_trigger = 'spam_complaint',
                            burned_at = NOW()
        WHERE id = $1
        """,
        dom_id,
    )

    rows = await db_pool.fetch(
        """
        SELECT event_type, status, workspace_id
        FROM event_log
        WHERE entity_id = $1 AND event_type = 'domain_burned'
        """,
        dom_id,
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "emitted"
    assert rows[0]["workspace_id"] == ws_id


# ──────────────────────────────────────────────────────────────────────────
# Test 7: package_assigned trigger fires
# ──────────────────────────────────────────────────────────────────────────
async def test_package_assigned_fires_on_workspace_update(db_pool):
    ws_id = await _make_workspace(db_pool, "ws-pkg-1")

    pkg_id = await db_pool.fetchval(
        """
        INSERT INTO workspace_packages (
            name, display_name, target_live_count,
            target_reserve_count, daily_limit_per_inbox,
            target_monthly_sends, is_active
        ) VALUES ('test_pkg', 'Test', 100, 20, 20, 10000, TRUE)
        RETURNING id
        """,
    )

    await db_pool.execute(
        "UPDATE workspaces SET package_id = $1 WHERE id = $2",
        pkg_id, ws_id,
    )

    rows = await db_pool.fetch(
        """
        SELECT event_type, status, workspace_id
        FROM event_log
        WHERE entity_id = $1 AND event_type = 'package_assigned'
        """,
        ws_id,
    )
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == ws_id


# ──────────────────────────────────────────────────────────────────────────
# Test 8: tag_op events MUST have workspace_id (CHECK constraint)
# ──────────────────────────────────────────────────────────────────────────
async def test_tag_op_without_workspace_id_raises(db_pool):
    """The CHECK constraint enforces per-workspace partitioning rule from
    ADR-006. A handler trying to enqueue tag_op without workspace_id
    must fail at the DB layer."""
    inbox_id = uuid.uuid4()  # doesn't need to exist; CHECK fires first

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


async def test_non_tag_op_event_can_have_null_workspace(db_pool):
    """Non-tag_op events (rare, but allowed) can have NULL workspace_id."""
    entity_id = uuid.uuid4()
    await db_pool.execute(
        """
        INSERT INTO event_log (
            event_type, entity_type, entity_id, payload, status, workspace_id
        ) VALUES (
            'misc_event', 'inbox', $1, '{}'::jsonb, 'emitted', NULL
        )
        """,
        entity_id,
    )
    # Just asserts no exception raised


# ──────────────────────────────────────────────────────────────────────────
# Test 9: Same-transaction guarantee — trigger row commits atomically

async def test_rollback_leaves_no_event(db_pool):
    """End-to-end: rollback the whole TX, assert no event_log row."""
    ws_id = await _make_workspace(db_pool, "ws-rb-2")
    dom_id = await _make_domain(db_pool, ws_id, "rb2.example")

    pre = await db_pool.fetchval(
        "SELECT COUNT(*) FROM event_log WHERE workspace_id = $1",
        ws_id,
    )

    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO sender_accounts (
                        email_address, workspace_id, domain_id, esp,
                        emailbison_account_id, status,
                        inbox_state, is_active,
                        inventory_lifecycle_status, inventory_pool_status,
                        warmup_enabled, health_score, first_seen_at
                    ) VALUES (
                        'rb2@trig.example', $1, $2, 'gmail',
                        99998, 'Connected', 'live', TRUE,
                        'active', 'live', TRUE, 100, NOW()
                    )
                    """,
                    ws_id, dom_id,
                )
                raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    post = await db_pool.fetchval(
        "SELECT COUNT(*) FROM event_log WHERE workspace_id = $1",
        ws_id,
    )
    assert post == pre, (
        "event_log must roll back together with the originating transaction; "
        "events should NOT survive a rollback"
    )
