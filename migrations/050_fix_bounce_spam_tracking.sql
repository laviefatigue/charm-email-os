-- Migration: 050_fix_bounce_spam_tracking.sql
-- Purpose: Fix bounce/spam tracking accuracy
--
-- Problems fixed:
-- 1. complaints_lifetime was being seeded from warmup_spam_count (WRONG)
-- 2. Disconnected inboxes were marked as dead (should stay live with status tracking)
-- 3. Warmup metrics not tracked separately for monitoring
--
-- Key distinction:
-- - warmup_spam_count = emails landing in spam during warmup (NOT a complaint, expected behavior)
-- - complaints_lifetime = actual FBL spam complaints from recipients (triggers kill)
-- - inbox_state = usability for campaigns (live/dead from kill triggers)
-- - status = connection state (Connected/Not connected/Disabled)

BEGIN;

-- ============================================================================
-- 1. Add warmup monitoring columns (NOT used for kill triggers)
-- ============================================================================

ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS warmup_score INTEGER,
ADD COLUMN IF NOT EXISTS warmup_spam_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS warmup_bounces_received INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS warmup_bounces_caused INTEGER DEFAULT 0;

COMMENT ON COLUMN sender_accounts.warmup_score IS 'EmailBison warmup score 0-100 - for monitoring only, NOT kill triggers';
COMMENT ON COLUMN sender_accounts.warmup_spam_count IS 'Warmup emails landing in spam folder - expected during warmup, NOT a spam complaint';
COMMENT ON COLUMN sender_accounts.warmup_bounces_received IS 'Bounces received during warmup exchanges';
COMMENT ON COLUMN sender_accounts.warmup_bounces_caused IS 'Bounces caused to warmup network partners';

-- ============================================================================
-- 2. Reset complaints_lifetime that was incorrectly seeded from warmup_spam_count
-- Only keep complaints verified from actual bounce/response analysis
-- ============================================================================

-- First, backup the current values for audit
CREATE TABLE IF NOT EXISTS _migration_050_complaints_backup AS
SELECT id, email_address, complaints_lifetime, warmup_spam_count, kill_trigger
FROM sender_accounts
WHERE complaints_lifetime > 0;

-- Reset complaints_lifetime to 0 for accounts that:
-- 1. Have complaints but NO kill_trigger of 'spam_complaint' (meaning it was seeded, not detected)
-- 2. Were never actually killed for spam
UPDATE sender_accounts
SET complaints_lifetime = 0
WHERE complaints_lifetime > 0
AND (kill_trigger IS NULL OR kill_trigger != 'spam_complaint')
AND killed_at IS NULL;

-- Log how many were reset
DO $$
DECLARE
    reset_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO reset_count
    FROM sender_accounts
    WHERE complaints_lifetime = 0
    AND id IN (SELECT id FROM _migration_050_complaints_backup);

    RAISE NOTICE 'Reset complaints_lifetime for % accounts (were incorrectly seeded from warmup_spam_count)', reset_count;
END $$;

-- ============================================================================
-- 3. Fix inbox_state for disconnected inboxes that were incorrectly marked dead
-- Disconnected != Dead. Dead = killed by trigger for bad behavior.
-- ============================================================================

-- Restore disconnected inboxes to 'live' if they weren't killed by a trigger
UPDATE sender_accounts
SET
    inbox_state = 'live',
    inventory_lifecycle_status = CASE
        WHEN created_at > NOW() - INTERVAL '14 days' THEN 'incubating'
        ELSE 'active'
    END,
    inventory_pool_status = 'reserve',
    updated_at = NOW()
WHERE status IN ('Not connected', 'Disconnected')
AND inbox_state = 'dead'
AND killed_at IS NULL
AND kill_trigger IS NULL;

-- Log how many were restored
DO $$
DECLARE
    restored_count INTEGER;
BEGIN
    GET DIAGNOSTICS restored_count = ROW_COUNT;
    RAISE NOTICE 'Restored % disconnected inboxes from dead to live (were not killed by trigger)', restored_count;
END $$;

-- ============================================================================
-- 4. Add index for efficient disconnection queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_sender_accounts_disconnected
ON sender_accounts (status, disconnected_at)
WHERE status = 'Not connected';

-- ============================================================================
-- 5. Update column comments for clarity
-- ============================================================================

COMMENT ON COLUMN sender_accounts.inbox_state IS 'Usability state: live (available for campaigns) or dead (killed by trigger). Disconnected inboxes remain live.';
COMMENT ON COLUMN sender_accounts.status IS 'Connection status from EmailBison: Connected, Not connected, Disabled. Tracks current state, not usability.';
COMMENT ON COLUMN sender_accounts.complaints_lifetime IS 'Actual FBL spam complaints from recipients. Kill trigger fires at >= 1. NOT seeded from warmup_spam_count.';
COMMENT ON COLUMN sender_accounts.kill_trigger IS 'The specific trigger that killed this inbox (spam_complaint, fresh_inbox_bounce, etc). NULL if never killed.';

COMMIT;
