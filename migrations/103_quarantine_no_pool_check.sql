-- Migration 103: chk_quarantined_no_pool — structural HR-1 enforcement
--
-- Plan A Phase 4 of docs/plans/cross-workspace-integrity-firewall.md.
--
-- ENFORCES the cross-workspace integrity firewall's hard rule HR-1
-- (a quarantined row can NEVER carry a pool tag) at the database layer.
--
-- Pre-Phase-4: HR-1 was enforced procedurally — the CASE expression in
-- sync_accounts.upsert (Plan A Phase 5a, commit f43b7b4) sets
-- inventory_pool_status=NULL whenever EXCLUDED.is_quarantined=TRUE. But
-- that's defense-by-discipline: any new code path that bypasses
-- upsert_account and writes to sender_accounts directly (e.g. an audit
-- script doing a bulk UPDATE) could re-introduce the invariant violation.
--
-- Post-Phase-4: the database itself REFUSES the write. CHECK constraint
-- failure raises an error at INSERT/UPDATE time. HR-1 enforced
-- structurally, not procedurally.
--
-- WHY THIS WAS DEFERRED FROM PHASE 1
-- ──────────────────────────────────
-- Migration 101 added the columns but NOT the CHECK constraint. If the
-- constraint had been added at Phase 1 time, it would have failed on any
-- existing live+foreign rows (HR-1 violations would have become
-- migration-blocking errors). Phase 5a + Phase 0d cleanup ensured we
-- have 0 violations across the fleet; this migration can now apply
-- cleanly.
--
-- VERIFIED PRE-CONDITION (2026-05-01 ~21:00 UTC):
--   SELECT COUNT(*) FROM sender_accounts
--   WHERE is_quarantined = TRUE AND inventory_pool_status IS NOT NULL;
--   -> 0
--
-- ROLLBACK
-- ────────
-- DROP CONSTRAINT chk_quarantined_no_pool. Reversible.

-- Idempotent guard — drop if exists, then add. Allows re-running on test
-- environments without conflict.
ALTER TABLE sender_accounts
    DROP CONSTRAINT IF EXISTS chk_quarantined_no_pool;

ALTER TABLE sender_accounts
    ADD CONSTRAINT chk_quarantined_no_pool
    CHECK (
        NOT is_quarantined
        OR inventory_pool_status IS NULL
    );

COMMENT ON CONSTRAINT chk_quarantined_no_pool ON sender_accounts IS
    'HR-1 of the cross-workspace integrity firewall: a quarantined inbox '
    'can never carry an inventory_pool_status. Enforced structurally — '
    'the database rejects any write that would violate the invariant. '
    'Migration 103 (Plan A Phase 4) added this constraint after migration '
    '101 (Phase 1) provided the column and Phase 5a wired the procedural '
    'CASE branch in sync_accounts.upsert. The CASE branch remains as '
    'belt-and-suspenders, but this constraint is the load-bearing rule.';
