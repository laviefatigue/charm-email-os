-- Migration: 055_cleanup_kill_trigger_accuracy.sql
-- Purpose: Clean up kill trigger data for accuracy after sync fixes
--
-- This migration addresses several data accuracy issues:
-- 1. Fresh inbox kills were calculated from first_seen_at, not warmup_started_at
-- 2. Bounce counters may have been polluted by warmup bounces (fixed in 053)
-- 3. Kill queue may have stale/incorrect entries
--
-- Run AFTER deploying all sync fixes (053, 054, health_checks.py changes)

BEGIN;

-- =============================================================================
-- PART 1: Identify inboxes that were incorrectly killed as "fresh_inbox_bounce"
-- =============================================================================

-- An inbox was incorrectly killed as "fresh_inbox_bounce" if:
-- 1. It was killed with trigger_type = 'fresh_inbox_bounce'
-- 2. At the time of kill, warmup_started_at was more than 14 days ago
--    (meaning it wasn't actually a fresh inbox in incubation)

-- First, create a backup of potentially affected inboxes
CREATE TABLE IF NOT EXISTS _migration_055_fresh_inbox_review AS
SELECT
    sa.id,
    sa.email_address,
    sa.kill_trigger,
    sa.killed_at,
    sa.warmup_started_at,
    sa.first_seen_at,
    sa.created_at,
    -- Calculate actual age at time of kill
    CASE
        WHEN sa.killed_at IS NOT NULL AND sa.warmup_started_at IS NOT NULL
        THEN EXTRACT(DAYS FROM (sa.killed_at - sa.warmup_started_at))
        ELSE NULL
    END as warmup_age_at_kill,
    -- Was this a false positive fresh inbox kill?
    CASE
        WHEN sa.kill_trigger = 'fresh_inbox_bounce'
             AND sa.warmup_started_at IS NOT NULL
             AND EXTRACT(DAYS FROM (sa.killed_at - sa.warmup_started_at)) >= 14
        THEN TRUE
        ELSE FALSE
    END as potentially_incorrect_kill
FROM sender_accounts sa
WHERE sa.kill_trigger = 'fresh_inbox_bounce'
   OR sa.killed_at IS NOT NULL;

-- Log count of potentially incorrect kills
DO $$
DECLARE
    total_kills INTEGER;
    fresh_inbox_kills INTEGER;
    potentially_incorrect INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_kills FROM _migration_055_fresh_inbox_review;
    SELECT COUNT(*) INTO fresh_inbox_kills FROM _migration_055_fresh_inbox_review WHERE kill_trigger = 'fresh_inbox_bounce';
    SELECT COUNT(*) INTO potentially_incorrect FROM _migration_055_fresh_inbox_review WHERE potentially_incorrect_kill = TRUE;

    RAISE NOTICE 'Kill trigger review:';
    RAISE NOTICE '  Total killed inboxes: %', total_kills;
    RAISE NOTICE '  Fresh inbox bounce kills: %', fresh_inbox_kills;
    RAISE NOTICE '  Potentially incorrect (age >= 14 days at kill): %', potentially_incorrect;
END $$;

-- =============================================================================
-- PART 2: Clean up kill_queue entries
-- =============================================================================

-- Remove any stale pending entries from kill_queue
-- (entries that haven't been processed in over 24 hours are likely stuck)
DELETE FROM kill_queue
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '24 hours';

-- Log cleanup
DO $$
DECLARE
    deleted_count INTEGER;
BEGIN
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RAISE NOTICE 'Removed % stale kill_queue entries', deleted_count;
END $$;

-- =============================================================================
-- PART 3: Recalculate bounce counters from response_messages (source of truth)
-- =============================================================================

-- This ensures bounce counters accurately reflect campaign bounces only
-- (warmup bounces are excluded since they don't go through response_messages)

WITH bounce_counts AS (
    SELECT
        sender_account_id,
        -- 24-hour counts
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '24 hours'
            AND bounce_type LIKE 'hard%'
        ) as hard_bounces_24h,
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '24 hours'
            AND bounce_type = 'hard_blocked'
        ) as hard_blocked_24h,
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '24 hours'
            AND bounce_type = 'hard_unknown'
        ) as hard_unknown_24h,
        -- 7-day counts
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '7 days'
            AND bounce_type LIKE 'hard%'
        ) as hard_bounces_7d,
        COUNT(*) FILTER (
            WHERE received_at > NOW() - INTERVAL '7 days'
            AND bounce_type LIKE 'soft%'
        ) as soft_bounces_7d
    FROM response_messages
    WHERE folder = 'bounced'
      AND sender_account_id IS NOT NULL
    GROUP BY sender_account_id
)
UPDATE sender_accounts sa
SET
    hard_bounces_24h = COALESCE(bc.hard_bounces_24h, 0),
    hard_blocked_24h = COALESCE(bc.hard_blocked_24h, 0),
    hard_unknown_24h = COALESCE(bc.hard_unknown_24h, 0),
    hard_bounces_7d = COALESCE(bc.hard_bounces_7d, 0),
    soft_bounces_7d = COALESCE(bc.soft_bounces_7d, 0),
    updated_at = NOW()
FROM bounce_counts bc
WHERE sa.id = bc.sender_account_id;

-- Also reset counters for inboxes with no bounce records
UPDATE sender_accounts
SET
    hard_bounces_24h = 0,
    hard_blocked_24h = 0,
    hard_unknown_24h = 0,
    hard_bounces_7d = 0,
    soft_bounces_7d = 0,
    updated_at = NOW()
WHERE inbox_state = 'live'
  AND id NOT IN (
      SELECT DISTINCT sender_account_id
      FROM response_messages
      WHERE folder = 'bounced'
      AND sender_account_id IS NOT NULL
  )
  AND (hard_bounces_24h > 0 OR hard_bounces_7d > 0);

-- =============================================================================
-- PART 4: Recalculate spam complaint counts from response_messages
-- =============================================================================

WITH spam_counts AS (
    SELECT
        sender_account_id,
        COUNT(*) as spam_complaints
    FROM response_messages
    WHERE folder = 'spam'
      AND sender_account_id IS NOT NULL
    GROUP BY sender_account_id
)
UPDATE sender_accounts sa
SET
    complaints_lifetime = GREATEST(
        COALESCE(sa.complaints_lifetime, 0),
        COALESCE(sc.spam_complaints, 0)
    ),
    updated_at = NOW()
FROM spam_counts sc
WHERE sa.id = sc.sender_account_id;

-- =============================================================================
-- PART 5: Summary report
-- =============================================================================

DO $$
DECLARE
    live_count INTEGER;
    dead_count INTEGER;
    with_bounces INTEGER;
    with_complaints INTEGER;
BEGIN
    SELECT COUNT(*) INTO live_count FROM sender_accounts WHERE inbox_state = 'live';
    SELECT COUNT(*) INTO dead_count FROM sender_accounts WHERE inbox_state = 'dead';
    SELECT COUNT(*) INTO with_bounces FROM sender_accounts WHERE hard_bounces_7d > 0;
    SELECT COUNT(*) INTO with_complaints FROM sender_accounts WHERE complaints_lifetime > 0;

    RAISE NOTICE '=== Migration 055 Complete ===';
    RAISE NOTICE 'Live inboxes: %', live_count;
    RAISE NOTICE 'Dead inboxes: %', dead_count;
    RAISE NOTICE 'Inboxes with bounces (7d): %', with_bounces;
    RAISE NOTICE 'Inboxes with complaints: %', with_complaints;
END $$;

COMMIT;

-- =============================================================================
-- MANUAL REVIEW: Potentially incorrect fresh_inbox_bounce kills
-- =============================================================================
-- Run this query after migration to review inboxes that may have been
-- incorrectly killed as "fresh inbox" when they were actually mature:
--
-- SELECT * FROM _migration_055_fresh_inbox_review
-- WHERE potentially_incorrect_kill = TRUE
-- ORDER BY killed_at DESC;
--
-- If you want to resurrect these inboxes, run:
-- UPDATE sender_accounts
-- SET inbox_state = 'live', killed_at = NULL, kill_trigger = NULL
-- WHERE id IN (SELECT id FROM _migration_055_fresh_inbox_review WHERE potentially_incorrect_kill = TRUE);
