-- Migration 100: rename `inventory_pool_status` value 'deployed' → 'live'
--
-- Per ADR-008 (proposed): the inbox-level pool column will eventually be
-- collapsed into a single `inbox_status` with values incubating/reserve/live/dead.
-- This migration is the same-week stepping stone (Direction B from the
-- 2026-04-29 architecture review):
--
--   - EB tag is named 'live' (the canonical name)
--   - domains.pool_status uses 'live' (long-standing)
--   - inventory_pool_status used 'deployed' (historical drift from the
--     per-inbox authority added by ADR-006)
--
-- Bringing inventory_pool_status into alignment with the EB tag and the
-- domain column reduces translation overhead in queries, audits, and
-- mental models. After ADR-008 collapse, this is the value name we keep.
--
-- inventory_pool_status is varchar (not enum), so this is a simple UPDATE.
-- No ALTER TYPE needed.
--
-- Pre-state (2026-04-29):
--   deployed: 1,871 active inboxes
--   reserve:  133
--   NULL:     2,768
--
-- Post-state expected:
--   live:     1,871
--   reserve:  133
--   NULL:     2,768

-- IMPORTANT: there's a CHECK constraint `chk_inventory_pool_status` that
-- allows only 'deployed', 'reserve', 'warning', 'quarantined', NULL. We
-- must drop it before the rename, then recreate it with the new
-- vocabulary.
--
-- ADR-007 already removed 'warning' and 'quarantined' from runtime usage;
-- migration 098 drained the existing active+live rows but missed 39
-- inactive (`is_active=FALSE`) rows still at 'warning'. This migration
-- nulls those out as well, so the new tightened constraint
-- ('live'/'reserve'/NULL only) accepts every existing row.
--
-- Production execution at 2026-04-29 ~17:00 UTC was performed step-by-step
-- via the admin SQL endpoint (which rejects mixed DDL+DML in one call).
-- The same statements below run as a single transaction in any environment
-- that allows it (test containers, psql).

BEGIN;

-- 1. Drop the existing constraint (which forbids 'live').
ALTER TABLE sender_accounts
    DROP CONSTRAINT IF EXISTS chk_inventory_pool_status;

-- 2a. Rename the value: 'deployed' → 'live'.
UPDATE sender_accounts
SET inventory_pool_status = 'live',
    updated_at = NOW()
WHERE inventory_pool_status = 'deployed';

-- 2b. NULL out any remaining 'warning' rows that migration 098 missed
-- (inactive rows: is_active=FALSE). ADR-007 removed 'warning' from runtime
-- usage and these rows can't be reached by sync paths anyway.
UPDATE sender_accounts
SET inventory_pool_status = NULL,
    updated_at = NOW()
WHERE inventory_pool_status IN ('warning', 'quarantined');

-- 3. Recreate the constraint with the new vocabulary.
-- Tightened to just 'live', 'reserve', NULL — drops 'deployed', 'warning'
-- and 'quarantined' which are no longer valid post-ADR-007/ADR-008-step1.
ALTER TABLE sender_accounts
    ADD CONSTRAINT chk_inventory_pool_status
    CHECK (
        inventory_pool_status IS NULL
        OR inventory_pool_status::text = ANY (
            ARRAY['live'::varchar, 'reserve'::varchar]::text[]
        )
    );

-- Sanity check.
DO $$
DECLARE
    live_count INTEGER;
    deployed_remaining INTEGER;
    warning_remaining INTEGER;
BEGIN
    SELECT COUNT(*) INTO live_count
    FROM sender_accounts
    WHERE inventory_pool_status = 'live';

    SELECT COUNT(*) INTO deployed_remaining
    FROM sender_accounts
    WHERE inventory_pool_status = 'deployed';

    SELECT COUNT(*) INTO warning_remaining
    FROM sender_accounts
    WHERE inventory_pool_status IN ('warning', 'quarantined');

    RAISE NOTICE 'Migration 100 complete: % rows at live, % deployed (should be 0), % warning/quarantined (should be 0)',
        live_count, deployed_remaining, warning_remaining;

    IF deployed_remaining > 0 THEN
        RAISE EXCEPTION 'Migration 100 incomplete: % rows still have inventory_pool_status=deployed', deployed_remaining;
    END IF;
END $$;

COMMIT;
