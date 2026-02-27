-- Migration: 056_fix_domain_state_consistency.sql
-- Purpose: Fix domain_state inconsistencies with inbox reality
--
-- FINDINGS FROM AUDIT (2026-02-26):
-- 1. 153 domains marked 'live' but have 0 live inboxes → should be 'dead'
-- 2. 48 domains marked 'dead' but have 919 live inboxes → should be 'live' or 'flagged'
--
-- DEFINITION: What is a "dead" domain?
-- A domain is DEAD when it has NO operational capacity:
--   - live_inbox_count = 0 (all inboxes killed)
--   - OR all live inboxes are permanently disconnected (Disabled status)
--
-- A domain is FLAGGED when:
--   - It has live inboxes BUT some are dead (dead_inbox_count > 0)
--   - OR it has poor health metrics (high bounce rate, complaints)
--
-- A domain is LIVE when:
--   - It has live inboxes (live_inbox_count > 0)
--   - AND no dead inboxes (dead_inbox_count = 0)

BEGIN;

-- =============================================================================
-- PART 1: Backup current state
-- =============================================================================

CREATE TABLE IF NOT EXISTS _migration_056_domain_state_backup AS
SELECT
    id,
    domain_name,
    domain_state,
    live_inbox_count,
    dead_inbox_count
FROM domains;

-- =============================================================================
-- PART 2: Fix domains marked 'live' but with 0 live inboxes → 'dead'
-- =============================================================================

-- These domains have no operational capacity
UPDATE domains
SET
    domain_state = 'dead',
    updated_at = NOW()
WHERE domain_state = 'live'
  AND live_inbox_count = 0;

DO $$
DECLARE
    affected INTEGER;
BEGIN
    GET DIAGNOSTICS affected = ROW_COUNT;
    RAISE NOTICE 'Fixed % domains: live → dead (0 live inboxes)', affected;
END $$;

-- =============================================================================
-- PART 3: Fix domains marked 'dead' but with live inboxes → 'flagged' or 'live'
-- =============================================================================

-- If has live inboxes AND dead inboxes → flagged (partial capacity)
UPDATE domains
SET
    domain_state = 'flagged',
    updated_at = NOW()
WHERE domain_state = 'dead'
  AND live_inbox_count > 0
  AND dead_inbox_count > 0;

DO $$
DECLARE
    affected INTEGER;
BEGIN
    GET DIAGNOSTICS affected = ROW_COUNT;
    RAISE NOTICE 'Fixed % domains: dead → flagged (has live + dead inboxes)', affected;
END $$;

-- If has ONLY live inboxes (no dead) → live
UPDATE domains
SET
    domain_state = 'live',
    updated_at = NOW()
WHERE domain_state = 'dead'
  AND live_inbox_count > 0
  AND (dead_inbox_count = 0 OR dead_inbox_count IS NULL);

DO $$
DECLARE
    affected INTEGER;
BEGIN
    GET DIAGNOSTICS affected = ROW_COUNT;
    RAISE NOTICE 'Fixed % domains: dead → live (only live inboxes)', affected;
END $$;

-- =============================================================================
-- PART 4: Ensure flagged domains with no issues get updated
-- =============================================================================

-- If flagged but has all live inboxes (no dead) → live
UPDATE domains
SET
    domain_state = 'live',
    updated_at = NOW()
WHERE domain_state = 'flagged'
  AND live_inbox_count > 0
  AND (dead_inbox_count = 0 OR dead_inbox_count IS NULL);

DO $$
DECLARE
    affected INTEGER;
BEGIN
    GET DIAGNOSTICS affected = ROW_COUNT;
    RAISE NOTICE 'Fixed % domains: flagged → live (no dead inboxes)', affected;
END $$;

-- =============================================================================
-- PART 5: Summary report
-- =============================================================================

DO $$
DECLARE
    live_count INTEGER;
    flagged_count INTEGER;
    dead_count INTEGER;
    inconsistent INTEGER;
BEGIN
    SELECT COUNT(*) INTO live_count FROM domains WHERE domain_state = 'live';
    SELECT COUNT(*) INTO flagged_count FROM domains WHERE domain_state = 'flagged';
    SELECT COUNT(*) INTO dead_count FROM domains WHERE domain_state = 'dead';

    -- Check for remaining inconsistencies
    SELECT COUNT(*) INTO inconsistent FROM domains
    WHERE (domain_state = 'live' AND live_inbox_count = 0)
       OR (domain_state = 'dead' AND live_inbox_count > 0);

    RAISE NOTICE '=== Migration 056 Complete ===';
    RAISE NOTICE 'Domain state distribution:';
    RAISE NOTICE '  Live: %', live_count;
    RAISE NOTICE '  Flagged: %', flagged_count;
    RAISE NOTICE '  Dead: %', dead_count;
    RAISE NOTICE '  Remaining inconsistencies: %', inconsistent;
END $$;

COMMIT;

-- =============================================================================
-- DEFINITION DOCUMENTATION
-- =============================================================================
--
-- DOMAIN STATE DEFINITIONS:
--
-- LIVE:
--   - live_inbox_count > 0
--   - dead_inbox_count = 0 (no killed inboxes)
--   - Domain is healthy and fully operational
--
-- FLAGGED:
--   - live_inbox_count > 0 (has some operational capacity)
--   - dead_inbox_count > 0 (some inboxes killed)
--   - Domain needs attention but still has capacity
--   - Could also be flagged for: high bounce rate, all disconnected, etc.
--
-- DEAD:
--   - live_inbox_count = 0 (no operational capacity)
--   - All inboxes have been killed
--   - Domain should be rotated/replaced
--
-- IMPORTANT: inbox_state vs status
--   - inbox_state (live/dead): Whether inbox was KILLED by our system
--   - status (Connected/Not connected/Disabled): Whether inbox CAN SEND
--   - A live inbox can be disconnected and unable to send
--   - A dead inbox can still be "Connected" (we tag, don't delete)
--
-- OPERATIONAL CAPACITY:
--   - True operational capacity = live inboxes that are ALSO connected
--   - Disconnected live inboxes have 0 operational capacity
--   - This should be reflected in capacity calculations
--
