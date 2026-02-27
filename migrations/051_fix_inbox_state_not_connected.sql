-- Migration: 051_fix_inbox_state_not_connected.sql
-- Purpose: Fix inboxes incorrectly marked as 'dead' due to sync bug
--
-- Bug: Old sync code treated 'Not connected' and 'Disconnected' status as 'dead'
-- Reality: Only 'Disabled' (explicit user action) should be 'dead'
-- Impact: 1938 inboxes incorrectly marked dead when they are actually live/warming

BEGIN;

-- First, let's count affected rows
DO $$
DECLARE
    affected_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO affected_count
    FROM sender_accounts
    WHERE inbox_state = 'dead'
      AND killed_at IS NULL
      AND status != 'Disabled';

    RAISE NOTICE 'Found % inboxes to fix', affected_count;
END $$;

-- Fix inbox_state for inboxes that were incorrectly marked dead
-- Only fix those that:
--   1. Have inbox_state = 'dead'
--   2. Were NOT killed (killed_at IS NULL)
--   3. Status is NOT 'Disabled' (only Disabled should be dead)
UPDATE sender_accounts
SET
    inbox_state = 'live',
    -- Also fix inventory status
    inventory_lifecycle_status = CASE
        WHEN created_at > NOW() - INTERVAL '14 days' THEN 'incubating'
        ELSE 'active'
    END,
    inventory_pool_status = CASE
        WHEN COALESCE(hard_bounces_24h, 0) >= 1 OR COALESCE(hard_bounces_7d, 0) >= 3 THEN 'warning'
        WHEN created_at <= NOW() - INTERVAL '14 days' AND COALESCE(warmup_enabled, TRUE) = TRUE THEN 'reserve'
        ELSE 'incubating'
    END,
    updated_at = NOW()
WHERE inbox_state = 'dead'
  AND killed_at IS NULL
  AND status != 'Disabled';

-- Also update the domains table cached counts
-- This recalculates live_inbox_count and dead_inbox_count based on actual inbox_state
UPDATE domains d
SET
    live_inbox_count = counts.live,
    dead_inbox_count = counts.dead,
    domain_state = CASE
        WHEN counts.live = 0 AND counts.dead > 0 THEN 'dead'::domain_state
        WHEN counts.live = 0 AND counts.dead = 0 THEN 'live'::domain_state  -- No inboxes yet
        ELSE 'live'::domain_state
    END,
    updated_at = NOW()
FROM (
    SELECT
        domain_id,
        COUNT(*) FILTER (WHERE inbox_state = 'live') as live,
        COUNT(*) FILTER (WHERE inbox_state = 'dead') as dead
    FROM sender_accounts
    GROUP BY domain_id
) counts
WHERE d.id = counts.domain_id
  AND (d.live_inbox_count != counts.live OR d.dead_inbox_count != counts.dead);

COMMIT;

-- Verify the fix
DO $$
DECLARE
    remaining_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining_count
    FROM sender_accounts
    WHERE inbox_state = 'dead'
      AND killed_at IS NULL
      AND status != 'Disabled';

    IF remaining_count > 0 THEN
        RAISE WARNING 'Still have % unfixed inboxes', remaining_count;
    ELSE
        RAISE NOTICE 'All incorrectly marked inboxes have been fixed';
    END IF;
END $$;
