"""
Integration tests for the post-2026-05-04 lifetime-rate kill rule.

Plan reference: docs/plans/kill-rule-rate-based-rewrite.md

The rule (replaces all _24h count-based triggers):

    1. complaints_lifetime ≥ 1                      → kill (spam_complaint)
    2. emails_sent_all_time < KILL_MIN_SENDS_LIFETIME (20)
                                                    → skip
    3. (hard_bounces_lifetime / emails_sent_all_time) > KILL_MATURE_RATE (5%)
                                                    → kill (hard_bounce_rate_lifetime)

The numerator is computed on demand from response_messages.bounce_type IN
('hard_blocked','hard_unknown') — no rolling counter to drift.

Boundary cases under test (matches the table in the plan doc):

    1 bnc / 19 sends   ( 5.3%) → skip       (under 20-send floor)
    1 bnc / 20 sends   ( 5.0%) → safe       (5.0% not strictly > 5%)
    2 bnc / 20 sends   (10.0%) → kill
    1 bnc / 25 sends   ( 4.0%) → safe
    50 bnc / 1500 sends ( 3.3%) → safe
    80 bnc / 1500 sends ( 5.3%) → kill
    100 bnc / 1500 sends ( 6.7%) → kill
    1 spam complaint, any volume → kill
    20+ sends, 0 bounces → safe

Plus dry-run flag verification: rule fires but no kill_queue row when
KILL_RULE_DRY_RUN=true.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import asyncpg
import pytest
import pytest_asyncio

from sync_modules.audit_logger import AuditLogger
from sync_modules import health_checks as hc
from sync_modules.health_checks import HealthCheckModule
from sync_modules.slack_alerter import SlackAlerter

from tests.fakes import FakeEmailBisonClient


pytestmark = pytest.mark.asyncio


# ──────────────────────────────────────────────────────────────────────────
# Helpers (mirror tests/test_warning_drop.py — small inline fakes are cheap)
# ──────────────────────────────────────────────────────────────────────────
async def _make_domain(pool: asyncpg.Pool, workspace_id, name: str):
    return await pool.fetchval(
        """
        INSERT INTO domains (domain_name, workspace_id, pool_status, is_active, infrastructure_type)
        VALUES ($1, $2, 'live', TRUE, 'google')
        RETURNING id
        """,
        name, workspace_id,
    )


async def _make_inbox(
    pool: asyncpg.Pool,
    workspace_id,
    domain_id,
    *,
    email: str,
    eb_account_id: int,
    esp: str = "gmail",
    emails_sent_all_time: int = 0,
    complaints_lifetime: int = 0,
):
    """Seed a live inbox. Lifetime counters drive the new rule."""
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
            $1, $2, $3, $4,
            $5, 'Connected',
            'live', TRUE,
            'active', 'live',
            TRUE, NOW() - INTERVAL '14 days',
            $6, $7,
            100, NOW()
        )
        RETURNING id
        """,
        email, workspace_id, domain_id, esp,
        eb_account_id,
        emails_sent_all_time, complaints_lifetime,
    )


async def _seed_bounces(
    pool: asyncpg.Pool,
    workspace_id,
    inbox_id,
    *,
    hard_blocked: int = 0,
    hard_unknown: int = 0,
    soft_full: int = 0,
):
    """Insert N bounce rows into response_messages of each type."""
    rows = []
    for i in range(hard_blocked):
        rows.append(('hard_blocked', f'hard_blocked_{inbox_id}_{i}'))
    for i in range(hard_unknown):
        rows.append(('hard_unknown', f'hard_unknown_{inbox_id}_{i}'))
    for i in range(soft_full):
        rows.append(('soft_full', f'soft_full_{inbox_id}_{i}'))
    if not rows:
        return
    await pool.executemany(
        """
        INSERT INTO response_messages
            (sender_account_id, workspace_id, folder, bounce_type, emailbison_reply_id, campaign_id, received_at)
        VALUES ($1, $2, 'bounced', $3::bounce_type, $4, NULL, NOW() - INTERVAL '7 days')
        """,
        [(inbox_id, workspace_id, bt, eb_id) for bt, eb_id in rows],
    )


def _audit_logger(db_pool):
    return AuditLogger(db_pool)


def _alerter():
    return SlackAlerter(webhook_url="")


async def _kill_queue_rows_for(db_pool, inbox_id):
    return await db_pool.fetch(
        """
        SELECT trigger_type::text AS trigger_type, trigger_value, status
        FROM kill_queue WHERE inbox_id = $1 ORDER BY created_at
        """,
        inbox_id,
    )


@pytest.fixture(autouse=True)
def _ensure_dry_run_off(monkeypatch):
    """All tests in this module evaluate the rule with dry-run OFF unless
    a specific test overrides it. We mutate the module-level constant rather
    than the env var because the constant is read at import time."""
    monkeypatch.setattr(hc, 'KILL_RULE_DRY_RUN', False)


# ──────────────────────────────────────────────────────────────────────────
# L1: 1 bounce / 19 sends → skip (under 20-send floor)
# ──────────────────────────────────────────────────────────────────────────
async def test_l1_under_floor_no_kill(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l1", eb_id=401)
    dom_id = await _make_domain(db_pool, ws_id, "l1.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l1.example", eb_account_id=40001,
        emails_sent_all_time=19,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=1)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l1")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], "Below 20-send floor: rule must skip"


# ──────────────────────────────────────────────────────────────────────────
# L2: 1 bounce / 20 sends (5.0%) → safe (strictly > 5% required)
# ──────────────────────────────────────────────────────────────────────────
async def test_l2_exactly_5pct_no_kill(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l2", eb_id=402)
    dom_id = await _make_domain(db_pool, ws_id, "l2.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l2.example", eb_account_id=40002,
        emails_sent_all_time=20,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=1)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l2")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], "Exactly 5.0% must not kill (rule is strictly > 5%)"


# ──────────────────────────────────────────────────────────────────────────
# L3: 2 bounces / 20 sends (10.0%) → kill
# ──────────────────────────────────────────────────────────────────────────
async def test_l3_low_volume_high_rate_kills(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l3", eb_id=403)
    dom_id = await _make_domain(db_pool, ws_id, "l3.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l3.example", eb_account_id=40003,
        emails_sent_all_time=20,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=2)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l3")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert len(rows) == 1
    assert rows[0]["trigger_type"] == "hard_bounce_rate_lifetime"


# ──────────────────────────────────────────────────────────────────────────
# L4: 1 bounce / 25 sends (4.0%) → safe
# ──────────────────────────────────────────────────────────────────────────
async def test_l4_low_rate_safe(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l4", eb_id=404)
    dom_id = await _make_domain(db_pool, ws_id, "l4.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l4.example", eb_account_id=40004,
        emails_sent_all_time=25,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=1)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l4")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], "4% rate must not kill"


# ──────────────────────────────────────────────────────────────────────────
# L5: mature inbox, 50/1500 (3.3%) → safe
# ──────────────────────────────────────────────────────────────────────────
async def test_l5_mature_low_rate_safe(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l5", eb_id=405)
    dom_id = await _make_domain(db_pool, ws_id, "l5.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l5.example", eb_account_id=40005,
        emails_sent_all_time=1500,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=30, hard_unknown=20)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l5")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], "Mature inbox at 3.3% (industry-healthy) must not kill"


# ──────────────────────────────────────────────────────────────────────────
# L6: mature inbox, 80/1500 (5.3%) → kill
# ──────────────────────────────────────────────────────────────────────────
async def test_l6_mature_just_over_threshold_kills(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l6", eb_id=406)
    dom_id = await _make_domain(db_pool, ws_id, "l6.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l6.example", eb_account_id=40006,
        emails_sent_all_time=1500,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=50, hard_unknown=30)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l6")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert len(rows) == 1
    assert rows[0]["trigger_type"] == "hard_bounce_rate_lifetime"


# ──────────────────────────────────────────────────────────────────────────
# L7: spam complaint trumps everything, even at 0 sends
# ──────────────────────────────────────────────────────────────────────────
async def test_l7_spam_complaint_no_floor(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l7", eb_id=407)
    dom_id = await _make_domain(db_pool, ws_id, "l7.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l7.example", eb_account_id=40007,
        emails_sent_all_time=0,
        complaints_lifetime=1,
    )

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l7")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert any(r["trigger_type"] == "spam_complaint" for r in rows), \
        "Spam complaint must fire regardless of send volume"


# ──────────────────────────────────────────────────────────────────────────
# L8: clean inbox at 20 sends with 0 bounces → safe
# ──────────────────────────────────────────────────────────────────────────
async def test_l8_clean_inbox_safe(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l8", eb_id=408)
    dom_id = await _make_domain(db_pool, ws_id, "l8.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l8.example", eb_account_id=40008,
        emails_sent_all_time=200,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=0)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l8")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], "Clean inbox must never queue a kill"


# ──────────────────────────────────────────────────────────────────────────
# L9: soft bounces are captured but never trigger kills
# ──────────────────────────────────────────────────────────────────────────
async def test_l9_soft_bounces_never_kill(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l9", eb_id=409)
    dom_id = await _make_domain(db_pool, ws_id, "l9.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l9.example", eb_account_id=40009,
        emails_sent_all_time=50,
    )
    # 50% soft bounce rate — should NOT trigger
    await _seed_bounces(db_pool, ws_id, inbox_id, soft_full=25)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l9")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], "Soft bounces (mailbox-full / temp errors) must never kill"


# ──────────────────────────────────────────────────────────────────────────
# L10: stale _24h column inflation alone must NOT cause a kill (the bug we
# fixed). Seed hard_blocked_24h=50 but lifetime hard bounces=0.
# ──────────────────────────────────────────────────────────────────────────
async def test_l10_stale_24h_counter_does_not_kill(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l10", eb_id=410)
    dom_id = await _make_domain(db_pool, ws_id, "l10.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l10.example", eb_account_id=40010,
        emails_sent_all_time=1500,
    )
    # No bounce rows in response_messages — lifetime hard bounces is 0.
    # But the legacy _24h column is set to a high value (the inflation pattern).
    await db_pool.execute(
        "UPDATE sender_accounts SET hard_blocked_24h = 50, total_sends_7d = 100 WHERE id = $1",
        inbox_id,
    )

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l10")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], (
        "Inflated _24h column with zero lifetime bounces must not produce a kill — "
        "this is the regression test for the 2026-04-14 Barrena mass-kill"
    )


# ──────────────────────────────────────────────────────────────────────────
# L11: dry-run flag — rule fires but no kill_queue row written
# ──────────────────────────────────────────────────────────────────────────
async def test_l11_dry_run_does_not_queue(db_pool, fake_client, workspace_factory, monkeypatch):
    monkeypatch.setattr(hc, 'KILL_RULE_DRY_RUN', True)

    ws_id = await workspace_factory(name="ws-l11", eb_id=411)
    dom_id = await _make_domain(db_pool, ws_id, "l11.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="g@l11.example", eb_account_id=40011,
        emails_sent_all_time=1500,
    )
    # Would-kill at 100/1500 = 6.7% lifetime rate.
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=60, hard_unknown=40)

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l11")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert rows == [], "KILL_RULE_DRY_RUN=true must not write kill_queue rows"


# ──────────────────────────────────────────────────────────────────────────
# L12: ESP-agnostic — Microsoft inbox at 6% kills the same way Gmail does
# ──────────────────────────────────────────────────────────────────────────
async def test_l12_esp_agnostic(db_pool, fake_client, workspace_factory):
    ws_id = await workspace_factory(name="ws-l12", eb_id=412)
    dom_id = await _make_domain(db_pool, ws_id, "l12.example")
    inbox_id = await _make_inbox(
        db_pool, ws_id, dom_id,
        email="m@l12.example", eb_account_id=40012,
        esp="microsoft",
        emails_sent_all_time=100,
    )
    await _seed_bounces(db_pool, ws_id, inbox_id, hard_blocked=6)  # 6.0%

    health = HealthCheckModule(db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter())
    await health.check_workspace_health(workspace_id=ws_id, workspace_name="ws-l12")

    rows = await _kill_queue_rows_for(db_pool, inbox_id)
    assert len(rows) == 1
    assert rows[0]["trigger_type"] == "hard_bounce_rate_lifetime"
