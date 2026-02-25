-- Migration: Simplified Domain Workflow
-- Removes approve/deny step, domains go straight from generation to purchase selection
--
-- Status flow changes:
-- OLD: pending -> approved -> purchased -> active
-- NEW: available -> purchased -> active
--
-- Run: psql -h localhost -p 5433 -U postgres -d postgres -f migrations/024_simplified_domain_workflow.sql

BEGIN;

-- 1. Convert 'pending' domains to 'available' (generated, ready to buy)
UPDATE domains
SET approval_status = 'available'
WHERE approval_status = 'pending';

-- 2. Convert 'approved' domains to 'available' (they were approved but not purchased yet)
UPDATE domains
SET approval_status = 'available'
WHERE approval_status = 'approved';

-- 3. Delete 'denied' domains (no longer needed - user can just ignore domains they don't want)
-- Keep a count for logging
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO deleted_count FROM domains WHERE approval_status = 'denied';
    RAISE NOTICE 'Deleting % denied domains', deleted_count;
END $$;

DELETE FROM domains WHERE approval_status = 'denied';

-- 4. Add a comment to clarify the new status values
COMMENT ON COLUMN domains.approval_status IS 'Domain lifecycle status: available (generated, can purchase), purchased (bought, NS pending), active (NS verified), legacy (pre-existing), warming (in warmup)';

-- 5. Log migration results
DO $$
DECLARE
    available_count INTEGER;
    purchased_count INTEGER;
    active_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO available_count FROM domains WHERE approval_status = 'available';
    SELECT COUNT(*) INTO purchased_count FROM domains WHERE approval_status = 'purchased';
    SELECT COUNT(*) INTO active_count FROM domains WHERE approval_status = 'active';
    RAISE NOTICE 'Migration complete. Domains: % available, % purchased, % active',
        available_count, purchased_count, active_count;
END $$;

COMMIT;
