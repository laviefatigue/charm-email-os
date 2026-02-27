-- Migration: 053_fix_warmup_bounce_pollution.sql
-- Purpose: Reset bounce counters that were polluted by warmup bounces
--          through the now-removed bounce_delta tracking in sync_accounts.py
--
-- Background:
--   The bounce_delta calculation in sync_accounts.py used bounces_all_time
--   from EmailBison, which includes BOTH warmup AND campaign bounces.
--   This polluted hard_bounces_24h/7d counters, causing false positive kills.
--
--   After removing the delta calculation, bounce counters are now exclusively
--   managed by sync_events.py which tracks campaign-specific bounces via
--   the response_messages table (folder='bounced').
--
-- Run AFTER deploying the sync_accounts.py fix.

BEGIN;

-- Backup current values for rollback capability
CREATE TABLE IF NOT EXISTS _migration_053_bounce_backup AS
SELECT
    id,
    email_address,
    hard_bounces_24h,
    hard_bounces_7d,
    hard_blocked_24h,
    hard_unknown_24h,
    updated_at
FROM sender_accounts
WHERE hard_bounces_24h > 0
   OR hard_bounces_7d > 0
   OR hard_blocked_24h > 0
   OR hard_unknown_24h > 0;

-- Log backup count
DO $$
DECLARE
    backup_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO backup_count FROM _migration_053_bounce_backup;
    RAISE NOTICE 'Backed up % inboxes with non-zero bounce counters', backup_count;
END $$;

-- Recalculate bounce counters from response_messages (campaign bounces only)
-- This is the source of truth for campaign-specific bounces
WITH actual_bounces AS (
    SELECT
        sender_account_id,
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '24 hours'
            AND bounce_type LIKE 'hard%'
        ) as actual_24h,
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '7 days'
            AND bounce_type LIKE 'hard%'
        ) as actual_7d,
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '24 hours'
            AND bounce_type = 'hard_blocked'
        ) as actual_blocked_24h,
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '24 hours'
            AND bounce_type = 'hard_unknown'
        ) as actual_unknown_24h
    FROM response_messages
    WHERE folder = 'bounced'
      AND sender_account_id IS NOT NULL
    GROUP BY sender_account_id
)
UPDATE sender_accounts sa
SET
    hard_bounces_24h = COALESCE(ab.actual_24h, 0),
    hard_bounces_7d = COALESCE(ab.actual_7d, 0),
    hard_blocked_24h = COALESCE(ab.actual_blocked_24h, 0),
    hard_unknown_24h = COALESCE(ab.actual_unknown_24h, 0),
    updated_at = NOW()
FROM actual_bounces ab
WHERE sa.id = ab.sender_account_id;

-- Log update count
DO $$
DECLARE
    updated_count INTEGER;
BEGIN
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RAISE NOTICE 'Updated % inboxes with recalculated bounce counters from response_messages', updated_count;
END $$;

-- Reset counters for inboxes with no campaign bounces in response_messages
-- These may have had inflated counters from warmup bounce pollution
UPDATE sender_accounts
SET
    hard_bounces_24h = 0,
    hard_bounces_7d = 0,
    hard_blocked_24h = 0,
    hard_unknown_24h = 0,
    updated_at = NOW()
WHERE (hard_bounces_24h > 0 OR hard_bounces_7d > 0 OR hard_blocked_24h > 0 OR hard_unknown_24h > 0)
AND id NOT IN (
    SELECT DISTINCT sender_account_id
    FROM response_messages
    WHERE folder = 'bounced'
    AND sender_account_id IS NOT NULL
);

-- Log reset count
DO $$
DECLARE
    reset_count INTEGER;
BEGIN
    GET DIAGNOSTICS reset_count = ROW_COUNT;
    RAISE NOTICE 'Reset % inboxes that had no campaign bounces in response_messages', reset_count;
END $$;

-- Summary: Compare before/after
DO $$
DECLARE
    before_total INTEGER;
    after_total INTEGER;
BEGIN
    SELECT COALESCE(SUM(hard_bounces_24h + hard_bounces_7d), 0) INTO before_total
    FROM _migration_053_bounce_backup;

    SELECT COALESCE(SUM(hard_bounces_24h + hard_bounces_7d), 0) INTO after_total
    FROM sender_accounts;

    RAISE NOTICE 'Before: % total bounce counter value', before_total;
    RAISE NOTICE 'After: % total bounce counter value', after_total;
    RAISE NOTICE 'Reduced by: % (removed warmup bounce pollution)', before_total - after_total;
END $$;

COMMIT;

-- Rollback script (run manually if needed):
-- UPDATE sender_accounts sa
-- SET
--     hard_bounces_24h = b.hard_bounces_24h,
--     hard_bounces_7d = b.hard_bounces_7d,
--     hard_blocked_24h = b.hard_blocked_24h,
--     hard_unknown_24h = b.hard_unknown_24h
-- FROM _migration_053_bounce_backup b
-- WHERE sa.id = b.id;
