-- Migration: 034_bounce_counter_reset.sql
-- Purpose: Add infrastructure for 24h bounce counter reset
-- Related: Option C - Data Integrity First

-- Create a function to reset 24h bounce counters at midnight
-- This prevents false positives from stale counter accumulation

CREATE OR REPLACE FUNCTION reset_24h_bounce_counters()
RETURNS void AS $$
BEGIN
    UPDATE sender_accounts
    SET
        hard_bounces_24h = 0,
        hard_blocked_24h = 0,
        hard_unknown_24h = 0,
        updated_at = NOW()
    WHERE (hard_bounces_24h > 0 OR hard_blocked_24h > 0 OR hard_unknown_24h > 0)
      AND is_active = TRUE;

    RAISE NOTICE 'Reset 24h bounce counters at %', NOW();
END;
$$ LANGUAGE plpgsql;

-- Add a tracking table for counter reset history
CREATE TABLE IF NOT EXISTS bounce_counter_resets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    reset_at TIMESTAMP DEFAULT NOW(),
    accounts_reset INTEGER DEFAULT 0,
    notes TEXT
);

-- Create index for retention queries
CREATE INDEX IF NOT EXISTS idx_bounce_resets_timestamp ON bounce_counter_resets(reset_at DESC);

-- Note: The actual scheduled job should be set up via:
-- 1. pg_cron extension (if available): SELECT cron.schedule('reset-bounce-counters', '0 0 * * *', 'SELECT reset_24h_bounce_counters()');
-- 2. Or external scheduler calling the sync worker with --reset-counters flag
-- 3. Or the sync worker's daily maintenance routine

COMMENT ON FUNCTION reset_24h_bounce_counters() IS 'Resets 24h bounce counters at midnight to prevent false positives';

SELECT 'Migration 034_bounce_counter_reset complete' AS status;
