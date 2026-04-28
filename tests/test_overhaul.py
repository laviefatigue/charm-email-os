"""
Integration tests for the 2026-04-27 tagging-kill overhaul.

These tests run against a REAL Postgres (testcontainers or TEST_DATABASE_URL,
see conftest.py) and exercise the production modules end-to-end. Each test
asserts on BOTH database state AND the fake EmailBison client's recorded
calls / current tag state, so the assertions describe the externally-visible
outcome, not implementation details.

Test catalog (mapped to the plan in docs/work-logs/2026-04-27-...md)
─────────────────────────────────────────────────────────────────────
T1   Google graduates to reserve, never to live
T2   Microsoft graduates to live (legacy ride-to-death)
T3   set_tag_sync reconciles a pre-existing dual-tagged inbox
T5   set_tag_sync active circuit breaker — warning inboxes lose both pool tags
T7   Cross-domain promotion: source domain stays reserve, promoted inbox is deployed
T8   2-kill capacity safety net: small domain with 2 dead → state=dead
T11  Continuous warmup: warmup_enabled=FALSE blocks graduation even past 14 BD
T12  Min-sends floor: low total_sends_24h prevents hard_bounces_24h kill

Package-tier additions (migration 097)
──────────────────────────────────────
T13  Threshold maintenance promotes deficit count of reserves
T14  Override caps live target — orchestrator does not exceed it
T15  Workspace with no package assigned skips threshold maintenance
T16  pause_pool_transitions=TRUE skips threshold maintenance
T17  Domain-aware ordering: partially-tapped domain consumed before opening new one
T18  DB trigger rejects override greater than package target_live_count
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import asyncpg
import pytest
import pytest_asyncio

from sync_modules.audit_logger import AuditLogger
from sync_modules.health_checks import HealthCheckModule
from sync_modules.kill_processor import KillProcessor
from sync_modules.lifecycle_tag_sync import LifecycleTagSyncModule
from sync_modules.set_tag_sync import SetTagSyncModule
from sync_modules.slack_alerter import SlackAlerter

from tests.fakes import FakeEmailBisonClient


pytestmark = pytest.mark.asyncio


# ──────────────────────────────────────────────────────────────────────────
# Helpers — small, explicit, no factory abstractions to chase later.
# ──────────────────────────────────────────────────────────────────────────
async def _make_domain(
    pool: asyncpg.Pool, workspace_id, name: str, pool_status: str = "live"
):
    return await pool.fetchval("""
        INSERT INTO domains (domain_name, workspace_id, pool_status, is_active, infrastructure_type)
        VALUES ($1, $2, $3, TRUE, 'google')
        RETURNING id
    """, name, workspace_id, pool_status)


async def _make_inbox(
    pool: asyncpg.Pool,
    workspace_id,
    domain_id,
    *,
    email: str,
    eb_account_id: int,
    esp: str = "gmail",
    inbox_state: str = "live",
    inventory_lifecycle_status: str = "incubating",
    inventory_pool_status=None,
    warmup_enabled: bool = True,
    warmup_started_at_days_ago: int = 14,
    total_sends_24h: int = 50,
    hard_bounces_24h: int = 0,
    status: str = "Connected",
    health_score: int = 100,
):
    """Insert a sender_accounts row with the most-overrideable defaults."""
    started = datetime.now(timezone.utc) - timedelta(days=warmup_started_at_days_ago)
    return await pool.fetchval("""
        INSERT INTO sender_accounts (
            email_address, workspace_id, domain_id, esp,
            emailbison_account_id, status,
            inbox_state, is_active,
            inventory_lifecycle_status, inventory_pool_status,
            warmup_enabled, warmup_started_at,
            total_sends_24h, hard_bounces_24h,
            health_score, first_seen_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6,
            $7, TRUE,
            $8, $9,
            $10, $11,
            $12, $13,
            $14, NOW()
        )
        RETURNING id
    """,
        email, workspace_id, domain_id, esp,
        eb_account_id, status,
        inbox_state,
        inventory_lifecycle_status, inventory_pool_status,
        warmup_enabled, started,
        total_sends_24h, hard_bounces_24h,
        health_score,
    )


def _audit_logger(db_pool):
    return AuditLogger(db_pool)


def _alerter():
    # SlackAlerter without a webhook is a no-op; safe in tests.
    return SlackAlerter(webhook_url="")


# ──────────────────────────────────────────────────────────────────────────
# T1: Google graduates to reserve, never to live
# ──────────────────────────────────────────────────────────────────────────
async def test_t1_google_graduates_to_reserve(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t1", eb_id=101)
    domain_id = await _make_domain(db_pool, ws_id, "t1-google.example", "reserve")
    inbox_id = await _make_inbox(
        db_pool, ws_id, domain_id,
        email="g@t1-google.example",
        eb_account_id=10001,
        esp="gmail",
        inventory_lifecycle_status="incubating",
        warmup_started_at_days_ago=30,  # well past 14 BD
    )

    lifecycle = LifecycleTagSyncModule(
        db=db_pool, client=fake_client,
        audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    await lifecycle.sync_workspace_tags(
        workspace_id=ws_id,
        workspace_name="ws-t1",
        emailbison_workspace_id=101,
    )

    # DB: graduated to reserve, lifecycle active.
    row = await db_pool.fetchrow(
        "SELECT inventory_lifecycle_status, inventory_pool_status FROM sender_accounts WHERE id = $1",
        inbox_id,
    )
    assert row["inventory_lifecycle_status"] == "active"
    assert row["inventory_pool_status"] == "reserve"

    # EB: 'reserve' tag added, 'live' tag NEVER touched.
    assert "reserve" in fake_client.tags_on(10001)
    assert "live" not in fake_client.tags_on(10001)
    # And no historical tag_inbox call put 'live' on this inbox.
    live_tag_id = fake_client.tags.get("live")
    if live_tag_id is not None:
        live_calls = [
            c for c in fake_client.calls_named("tag_inbox")
            if c.kwargs.get("tag_id") == live_tag_id
            and c.kwargs.get("account_id") == 10001
        ]
        assert live_calls == [], "Google inbox must never receive the 'live' tag at graduation"


# ──────────────────────────────────────────────────────────────────────────
# T2: Microsoft graduates directly to live
# ──────────────────────────────────────────────────────────────────────────
async def test_t2_microsoft_graduates_to_live(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t2", eb_id=102)
    domain_id = await _make_domain(db_pool, ws_id, "t2-ms.example", "live")
    inbox_id = await _make_inbox(
        db_pool, ws_id, domain_id,
        email="m@t2-ms.example",
        eb_account_id=10002,
        esp="microsoft",
        inventory_lifecycle_status="incubating",
        warmup_started_at_days_ago=30,
    )

    lifecycle = LifecycleTagSyncModule(
        db=db_pool, client=fake_client,
        audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    await lifecycle.sync_workspace_tags(
        workspace_id=ws_id, workspace_name="ws-t2", emailbison_workspace_id=102,
    )

    row = await db_pool.fetchrow(
        "SELECT inventory_lifecycle_status, inventory_pool_status FROM sender_accounts WHERE id = $1",
        inbox_id,
    )
    assert row["inventory_lifecycle_status"] == "active"
    assert row["inventory_pool_status"] == "deployed"
    assert fake_client.tags_on(10002) == {"live"}


# ──────────────────────────────────────────────────────────────────────────
# T3: set_tag_sync reconciles a pre-existing dual-tagged inbox
# ──────────────────────────────────────────────────────────────────────────
async def test_t3_set_tag_sync_strips_orphan_live_from_reserve_inbox(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t3", eb_id=103)
    domain_id = await _make_domain(db_pool, ws_id, "t3-dual.example", "reserve")
    inbox_id = await _make_inbox(
        db_pool, ws_id, domain_id,
        email="dual@t3-dual.example",
        eb_account_id=10003,
        esp="gmail",
        inventory_lifecycle_status="active",
        inventory_pool_status="reserve",
    )

    # Seed the dual-tag bug state directly in the fake EB.
    live_tag = (await fake_client.get_or_create_tag("live"))["id"]
    reserve_tag = (await fake_client.get_or_create_tag("reserve"))["id"]
    await fake_client.tag_inbox(10003, live_tag)
    await fake_client.tag_inbox(10003, reserve_tag)
    assert fake_client.tags_on(10003) == {"live", "reserve"}

    set_tags = SetTagSyncModule(
        db=db_pool, client=fake_client,
        audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    await set_tags.sync_workspace_sets(
        workspace_id=ws_id, workspace_name="ws-t3", emailbison_workspace_id=103,
    )

    # The reconciling untag should have removed 'live' but left 'reserve'.
    assert fake_client.tags_on(10003) == {"reserve"}


# ──────────────────────────────────────────────────────────────────────────
# T5: active circuit breaker — warning inboxes lose both pool tags
# ──────────────────────────────────────────────────────────────────────────
async def test_t5_warning_inbox_loses_both_pool_tags(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t5", eb_id=105)
    domain_id = await _make_domain(db_pool, ws_id, "t5-warn.example", "live")
    inbox_id = await _make_inbox(
        db_pool, ws_id, domain_id,
        email="w@t5-warn.example",
        eb_account_id=10005,
        esp="gmail",
        inventory_lifecycle_status="active",
        inventory_pool_status="warning",   # <- the test condition
    )

    # Pre-populate EB with an existing 'live' tag — the bug we're guarding
    # against is "warning state in DB, still tagged live in EB."
    live_tag = (await fake_client.get_or_create_tag("live"))["id"]
    await fake_client.tag_inbox(10005, live_tag)

    set_tags = SetTagSyncModule(
        db=db_pool, client=fake_client,
        audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    await set_tags.sync_workspace_sets(
        workspace_id=ws_id, workspace_name="ws-t5", emailbison_workspace_id=105,
    )

    assert "live" not in fake_client.tags_on(10005)
    assert "reserve" not in fake_client.tags_on(10005)


# ──────────────────────────────────────────────────────────────────────────
# T7: Cross-domain promotion preserves source domain pool_status
# ──────────────────────────────────────────────────────────────────────────
async def test_t7_cross_domain_promotion(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t7", eb_id=107)
    live_domain = await _make_domain(db_pool, ws_id, "t7-live.example", "live")
    reserve_domain = await _make_domain(db_pool, ws_id, "t7-reserve.example", "reserve")

    # Killed: deployed inbox on a live domain.
    killed_id = await _make_inbox(
        db_pool, ws_id, live_domain,
        email="killed@t7-live.example", eb_account_id=10070,
        esp="gmail",
        inventory_lifecycle_status="active",
        inventory_pool_status="deployed",
    )
    # Bench candidate: oldest reserve inbox, on a different (reserve) domain.
    candidate_id = await _make_inbox(
        db_pool, ws_id, reserve_domain,
        email="candidate@t7-reserve.example", eb_account_id=10071,
        esp="gmail",
        inventory_lifecycle_status="active",
        inventory_pool_status="reserve",
        warmup_started_at_days_ago=60,  # oldest
    )
    # Decoy reserve inbox — newer, should NOT win.
    decoy_id = await _make_inbox(
        db_pool, ws_id, reserve_domain,
        email="decoy@t7-reserve.example", eb_account_id=10072,
        esp="gmail",
        inventory_lifecycle_status="active",
        inventory_pool_status="reserve",
        warmup_started_at_days_ago=20,
    )

    # Pre-mark the killed inbox dead to satisfy _promote_backup_inbox's prereqs.
    await db_pool.execute("""
        UPDATE sender_accounts SET inbox_state='dead', killed_at=NOW(),
            kill_trigger='hard_bounces_24h'::kill_trigger_type
        WHERE id = $1
    """, killed_id)

    kp = KillProcessor(
        db=db_pool, client=fake_client,
        audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    await kp._promote_backup_inbox(
        killed_inbox_id=killed_id,
        workspace_id=ws_id,
        trigger_type="hard_bounces_24h",
    )

    # Candidate (oldest reserve) was promoted; decoy untouched.
    candidate = await db_pool.fetchrow(
        "SELECT inventory_pool_status FROM sender_accounts WHERE id = $1", candidate_id
    )
    decoy = await db_pool.fetchrow(
        "SELECT inventory_pool_status FROM sender_accounts WHERE id = $1", decoy_id
    )
    assert candidate["inventory_pool_status"] == "deployed"
    assert decoy["inventory_pool_status"] == "reserve"

    # CRITICAL: source domain (t7-reserve.example) STAYS pool_status='reserve'
    # despite having one of its inboxes promoted to deployed. This is the
    # post-overhaul invariant — domain mixing is allowed via per-inbox override.
    src_domain = await db_pool.fetchrow(
        "SELECT pool_status FROM domains WHERE id = $1", reserve_domain
    )
    assert src_domain["pool_status"] == "reserve"


# ──────────────────────────────────────────────────────────────────────────
# T11: Continuous warmup — graduation blocked when warmup_enabled flips off
# ──────────────────────────────────────────────────────────────────────────
async def test_t11_warmup_disabled_blocks_graduation(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t11", eb_id=111)
    domain_id = await _make_domain(db_pool, ws_id, "t11-pause.example", "reserve")
    inbox_id = await _make_inbox(
        db_pool, ws_id, domain_id,
        email="paused@t11-pause.example", eb_account_id=10110,
        esp="gmail",
        inventory_lifecycle_status="incubating",
        warmup_enabled=True,
        warmup_started_at_days_ago=30,
    )

    # Toggle warmup off — the migration 094 trigger clears warmup_enabled_since.
    await db_pool.execute(
        "UPDATE sender_accounts SET warmup_enabled = FALSE WHERE id = $1",
        inbox_id,
    )

    lifecycle = LifecycleTagSyncModule(
        db=db_pool, client=fake_client,
        audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    await lifecycle.sync_workspace_tags(
        workspace_id=ws_id, workspace_name="ws-t11", emailbison_workspace_id=111,
    )

    # DB still incubating; no graduation occurred.
    row = await db_pool.fetchrow(
        "SELECT inventory_lifecycle_status FROM sender_accounts WHERE id = $1",
        inbox_id,
    )
    assert row["inventory_lifecycle_status"] == "incubating"
    # And no pool tag was applied in EB.
    assert fake_client.tags_on(10110) == set()


# ──────────────────────────────────────────────────────────────────────────
# T12: Min-sends floor blocks low-volume bounce kill
# ──────────────────────────────────────────────────────────────────────────
async def test_t12_min_sends_floor_blocks_low_volume_kill(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t12", eb_id=112)
    domain_id = await _make_domain(db_pool, ws_id, "t12-quiet.example", "live")
    inbox_id = await _make_inbox(
        db_pool, ws_id, domain_id,
        email="quiet@t12-quiet.example", eb_account_id=10120,
        esp="gmail",
        inventory_lifecycle_status="active",
        inventory_pool_status="deployed",
        hard_bounces_24h=2,        # would normally trigger
        total_sends_24h=3,         # but volume is too low — floor is 20
        warmup_started_at_days_ago=60,
    )

    health = HealthCheckModule(
        db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    triggers_detected = await health.check_workspace_health(
        workspace_id=ws_id, workspace_name="ws-t12",
    )

    # No kill queue entry should exist for this inbox.
    queued = await db_pool.fetchval(
        "SELECT COUNT(*) FROM kill_queue WHERE inbox_id = $1", inbox_id,
    )
    assert queued == 0
    # And no kill triggers detected at all.
    assert triggers_detected == 0


# ──────────────────────────────────────────────────────────────────────────
# T8: Small-domain capacity safety net — 2 dead inboxes retire the domain
# ──────────────────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────────────────
# Package-tier helpers (migration 097)
# ──────────────────────────────────────────────────────────────────────────
async def _assign_package(db_pool, workspace_id, package_name: str = '50k_google',
                          override: int = None):
    """Assign a workspace_packages row to a workspace with optional override."""
    pkg_id = await db_pool.fetchval(
        "SELECT id FROM workspace_packages WHERE name = $1", package_name
    )
    assert pkg_id is not None, f"Package {package_name} not seeded — migration 097 required"
    await db_pool.execute("""
        UPDATE workspaces
        SET package_id = $2,
            target_live_count_override = $3,
            package_assigned_at = NOW()
        WHERE id = $1
    """, workspace_id, pkg_id, override)


async def _set_pause(db_pool, workspace_id, paused: bool):
    await db_pool.execute(
        "UPDATE workspaces SET pause_pool_transitions = $2 WHERE id = $1",
        workspace_id, paused,
    )


async def _make_reserve_inbox(db_pool, workspace_id, domain_id, *,
                              email: str, eb_account_id: int,
                              days_warmup: int = 30):
    """Reserve-pool, graduated, ready to be promoted."""
    return await _make_inbox(
        db_pool, workspace_id, domain_id,
        email=email, eb_account_id=eb_account_id, esp='gmail',
        inventory_lifecycle_status='active',
        inventory_pool_status='reserve',
        warmup_started_at_days_ago=days_warmup,
    )


async def _make_deployed_inbox(db_pool, workspace_id, domain_id, *,
                               email: str, eb_account_id: int):
    return await _make_inbox(
        db_pool, workspace_id, domain_id,
        email=email, eb_account_id=eb_account_id, esp='gmail',
        inventory_lifecycle_status='active',
        inventory_pool_status='deployed',
        warmup_started_at_days_ago=60,
    )


async def _run_threshold_phase(db_pool, fake_client, workspace_id):
    """Invoke just the orchestrator's threshold-maintenance phase."""
    from sync_modules.workspace_writes import WorkspaceWriteOrchestrator
    orch = WorkspaceWriteOrchestrator(
        db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    ws = await db_pool.fetchrow("""
        SELECT w.id, w.workspace_name, w.package_id, w.target_live_count_override,
               w.pause_pool_transitions,
               p.target_live_count AS package_live_target,
               p.target_reserve_count AS package_reserve_minimum
        FROM workspaces w
        LEFT JOIN workspace_packages p ON p.id = w.package_id
        WHERE w.id = $1
    """, workspace_id)
    await orch._maintain_pool_thresholds(ws)


# ──────────────────────────────────────────────────────────────────────────
# T13: Threshold maintenance promotes deficit count
# ──────────────────────────────────────────────────────────────────────────
async def test_t13_threshold_promotes_deficit(
    db_pool, fake_client, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t13", eb_id=113)
    # Use 50k package (target_live_count=150) with override=3 so we only need
    # 3 deployed. Start with 1 deployed and 5 reserves available.
    await _assign_package(db_pool, ws_id, '50k_google', override=3)

    live_d = await _make_domain(db_pool, ws_id, "t13-live.example", "live")
    res_d = await _make_domain(db_pool, ws_id, "t13-res.example", "reserve")

    await _make_deployed_inbox(db_pool, ws_id, live_d,
                               email="d1@t13-live.example", eb_account_id=11300)
    # 5 reserves on the reserve domain
    for i in range(5):
        await _make_reserve_inbox(
            db_pool, ws_id, res_d,
            email=f"r{i}@t13-res.example", eb_account_id=11310 + i,
            days_warmup=30 + i,
        )

    await _run_threshold_phase(db_pool, fake_client, ws_id)

    # Should have promoted exactly 2 (target=3, current=1, deficit=2)
    deployed_count = await db_pool.fetchval("""
        SELECT COUNT(*) FROM sender_accounts
        WHERE workspace_id = $1 AND inventory_pool_status = 'deployed'
    """, ws_id)
    assert deployed_count == 3, f"expected 3 deployed, got {deployed_count}"

    # And inbox_rotation_history rows should exist for the 2 promotions
    promotion_rows = await db_pool.fetch("""
        SELECT target_inbox_email FROM inbox_rotation_history
        WHERE workspace_id = $1 AND rotation_type = 'threshold_promotion'
        ORDER BY executed_at
    """, ws_id)
    assert len(promotion_rows) == 2


# ──────────────────────────────────────────────────────────────────────────
# T14: Override caps live target — orchestrator does not exceed
# ──────────────────────────────────────────────────────────────────────────
async def test_t14_override_caps_live_target(
    db_pool, fake_client, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t14", eb_id=114)
    await _assign_package(db_pool, ws_id, '50k_google', override=2)

    live_d = await _make_domain(db_pool, ws_id, "t14-live.example", "live")
    res_d = await _make_domain(db_pool, ws_id, "t14-res.example", "reserve")

    # Already at the override target.
    for i in range(2):
        await _make_deployed_inbox(db_pool, ws_id, live_d,
                                   email=f"d{i}@t14-live.example",
                                   eb_account_id=11400 + i)
    # Plenty of reserves available.
    for i in range(10):
        await _make_reserve_inbox(
            db_pool, ws_id, res_d,
            email=f"r{i}@t14-res.example", eb_account_id=11410 + i,
        )

    await _run_threshold_phase(db_pool, fake_client, ws_id)

    deployed_count = await db_pool.fetchval("""
        SELECT COUNT(*) FROM sender_accounts
        WHERE workspace_id = $1 AND inventory_pool_status = 'deployed'
    """, ws_id)
    assert deployed_count == 2, f"override=2 should hold; got {deployed_count}"


# ──────────────────────────────────────────────────────────────────────────
# T15: No package assigned → threshold phase is a no-op
# ──────────────────────────────────────────────────────────────────────────
async def test_t15_no_package_skips_threshold(
    db_pool, fake_client, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t15", eb_id=115)
    # Deliberately NOT assigning a package.

    live_d = await _make_domain(db_pool, ws_id, "t15-live.example", "live")
    res_d = await _make_domain(db_pool, ws_id, "t15-res.example", "reserve")
    await _make_reserve_inbox(db_pool, ws_id, res_d,
                              email="r0@t15-res.example", eb_account_id=11500)

    # Even calling _maintain_pool_thresholds directly should bail out.
    await _run_threshold_phase(db_pool, fake_client, ws_id)

    # No promotions should have happened.
    promotion_rows = await db_pool.fetchval("""
        SELECT COUNT(*) FROM inbox_rotation_history
        WHERE workspace_id = $1
    """, ws_id)
    assert promotion_rows == 0


# ──────────────────────────────────────────────────────────────────────────
# T16: pause_pool_transitions=TRUE skips threshold maintenance
# ──────────────────────────────────────────────────────────────────────────
async def test_t16_pause_skips_threshold(
    db_pool, fake_client, workspace_factory
):
    """The orchestrator's per-workspace driver must respect pause_pool_transitions.

    Note: this test calls _run_workspace (not _maintain_pool_thresholds) because
    the pause check is in the caller, not the method itself.
    """
    ws_id = await workspace_factory(name="ws-t16", eb_id=116)
    await _assign_package(db_pool, ws_id, '50k_google', override=5)
    await _set_pause(db_pool, ws_id, True)

    live_d = await _make_domain(db_pool, ws_id, "t16-live.example", "live")
    res_d = await _make_domain(db_pool, ws_id, "t16-res.example", "reserve")
    for i in range(3):
        await _make_reserve_inbox(
            db_pool, ws_id, res_d,
            email=f"r{i}@t16-res.example", eb_account_id=11600 + i,
        )

    # Build the orchestrator and invoke its workspace driver to exercise the
    # pause check. We don't bring up an EmailBison client since the threshold
    # phase is the only one being tested.
    from sync_modules.workspace_writes import WorkspaceWriteOrchestrator
    orch = WorkspaceWriteOrchestrator(
        db=db_pool, audit_logger=_audit_logger(db_pool), alerter=_alerter(),
        enable_lifecycle_tagging=True, enable_kill_processing=False,
    )
    workspaces = await orch._load_active_workspaces_with_keys()
    ws = next(w for w in workspaces if w['id'] == ws_id)
    import asyncio
    sem = asyncio.Semaphore(1)
    await orch._run_workspace(ws, sem)

    promotion_rows = await db_pool.fetchval("""
        SELECT COUNT(*) FROM inbox_rotation_history
        WHERE workspace_id = $1 AND rotation_type = 'threshold_promotion'
    """, ws_id)
    assert promotion_rows == 0, f"paused workspace should not promote; got {promotion_rows}"


# ──────────────────────────────────────────────────────────────────────────
# T17: Domain-aware ordering — partially-tapped domain finished first
# ──────────────────────────────────────────────────────────────────────────
async def test_t17_partially_tapped_domain_consumed_first(
    db_pool, fake_client, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t17", eb_id=117)
    await _assign_package(db_pool, ws_id, '50k_google', override=3)

    live_d = await _make_domain(db_pool, ws_id, "t17-live.example", "live")
    # Domain A: partially-tapped (1 deployed, 2 reserve = 3 total per domain).
    a = await _make_domain(db_pool, ws_id, "t17-tapped.example", "reserve")
    await _make_deployed_inbox(db_pool, ws_id, a,
                               email="t17a-deployed@t17-tapped.example",
                               eb_account_id=11700)
    a_r1 = await _make_reserve_inbox(db_pool, ws_id, a,
                                     email="t17a-r1@t17-tapped.example",
                                     eb_account_id=11701, days_warmup=20)
    a_r2 = await _make_reserve_inbox(db_pool, ws_id, a,
                                     email="t17a-r2@t17-tapped.example",
                                     eb_account_id=11702, days_warmup=21)

    # Domain B: untapped, OLDER (longer warmup) — would win on age alone.
    b = await _make_domain(db_pool, ws_id, "t17-untapped.example", "reserve")
    b_r1 = await _make_reserve_inbox(db_pool, ws_id, b,
                                     email="t17b-r1@t17-untapped.example",
                                     eb_account_id=11710, days_warmup=60)
    b_r2 = await _make_reserve_inbox(db_pool, ws_id, b,
                                     email="t17b-r2@t17-untapped.example",
                                     eb_account_id=11711, days_warmup=61)

    # Existing live-pool deployed inbox so deployed_count includes 2 already
    # (1 from tapped domain + this one). Override=3 → deficit=1.
    await _make_deployed_inbox(db_pool, ws_id, live_d,
                               email="t17-live@t17-live.example",
                               eb_account_id=11720)

    await _run_threshold_phase(db_pool, fake_client, ws_id)

    # Exactly 1 promotion. It MUST come from the partially-tapped domain (A)
    # despite domain B having older inboxes.
    promo = await db_pool.fetch("""
        SELECT target_inbox_email FROM inbox_rotation_history
        WHERE workspace_id = $1 AND rotation_type = 'threshold_promotion'
    """, ws_id)
    assert len(promo) == 1
    assert promo[0]['target_inbox_email'].endswith('@t17-tapped.example'), (
        f"expected promotion from tapped domain (A); got {promo[0]['target_inbox_email']}"
    )


# ──────────────────────────────────────────────────────────────────────────
# T18: DB trigger rejects override > package.target_live_count
# ──────────────────────────────────────────────────────────────────────────
async def test_t18_trigger_rejects_oversized_override(
    db_pool, fake_client, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t18", eb_id=118)
    pkg_id = await db_pool.fetchval(
        "SELECT id FROM workspace_packages WHERE name = '50k_google'"
    )
    await db_pool.execute(
        "UPDATE workspaces SET package_id = $2 WHERE id = $1",
        ws_id, pkg_id,
    )

    # 50k_google has target_live_count = 150. Setting override = 200 must fail.
    with pytest.raises(asyncpg.exceptions.RaiseError) as exc:
        await db_pool.execute(
            "UPDATE workspaces SET target_live_count_override = $2 WHERE id = $1",
            ws_id, 200,
        )
    assert 'cannot exceed package target_live_count' in str(exc.value)


# ──────────────────────────────────────────────────────────────────────────
# T8: Small-domain capacity safety net — 2 dead inboxes retire the domain
# ──────────────────────────────────────────────────────────────────────────
async def test_t8_two_kill_safety_net_retires_small_domain(
    db_pool, fake_client: FakeEmailBisonClient, workspace_factory
):
    ws_id = await workspace_factory(name="ws-t8", eb_id=108)
    domain_id = await _make_domain(db_pool, ws_id, "t8-google3.example", "live")

    # 3-inbox Google domain.
    a = await _make_inbox(
        db_pool, ws_id, domain_id, email="a@t8-google3.example", eb_account_id=10080,
        inventory_lifecycle_status="active", inventory_pool_status="deployed",
    )
    b = await _make_inbox(
        db_pool, ws_id, domain_id, email="b@t8-google3.example", eb_account_id=10081,
        inventory_lifecycle_status="active", inventory_pool_status="deployed",
    )
    await _make_inbox(
        db_pool, ws_id, domain_id, email="c@t8-google3.example", eb_account_id=10082,
        inventory_lifecycle_status="active", inventory_pool_status="deployed",
    )

    # Mark two inboxes dead.
    await db_pool.execute("""
        UPDATE sender_accounts SET inbox_state='dead', killed_at=NOW(),
            kill_trigger='hard_bounces_24h'::kill_trigger_type,
            inventory_lifecycle_status='dead', inventory_pool_status=NULL
        WHERE id = ANY($1::uuid[])
    """, [a, b])

    kp = KillProcessor(
        db=db_pool, client=fake_client,
        audit_logger=_audit_logger(db_pool), alerter=_alerter(),
    )
    # Trigger the post-kill domain state recompute.
    await kp._update_domain_on_inbox_death(b)

    domain_state = await db_pool.fetchval(
        "SELECT domain_state FROM domains WHERE id = $1", domain_id
    )
    assert domain_state == "dead"
