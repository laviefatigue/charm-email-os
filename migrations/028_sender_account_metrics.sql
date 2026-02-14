-- Migration: 028_sender_account_metrics.sql
-- Purpose: Add all-time sending metrics to match EmailBison UI
-- Date: 2026-02-13

-- =============================================================
-- 1. ALL-TIME METRICS (from EmailBison API)
-- =============================================================

-- All-time emails sent (from EmailBison emails_sent_count)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS emails_sent_all_time INTEGER DEFAULT 0;

-- All-time replies received (from EmailBison total_replied_count)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS replies_all_time INTEGER DEFAULT 0;

-- All-time bounces (from EmailBison bounced_count)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS bounces_all_time INTEGER DEFAULT 0;

-- Daily sending limit (from EmailBison daily_limit)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS daily_limit INTEGER DEFAULT 0;

-- =============================================================
-- 2. INDEX FOR METRICS QUERIES
-- =============================================================

CREATE INDEX IF NOT EXISTS idx_sender_accounts_metrics
ON sender_accounts (emails_sent_all_time, bounces_all_time)
WHERE is_active = TRUE;

-- =============================================================
-- 3. COMMENTS
-- =============================================================

COMMENT ON COLUMN sender_accounts.emails_sent_all_time IS 'All-time emails sent (from EmailBison emails_sent_count)';
COMMENT ON COLUMN sender_accounts.replies_all_time IS 'All-time replies received (from EmailBison total_replied_count)';
COMMENT ON COLUMN sender_accounts.bounces_all_time IS 'All-time bounces (from EmailBison bounced_count)';
COMMENT ON COLUMN sender_accounts.daily_limit IS 'Daily sending limit (from EmailBison daily_limit)';

-- Done!
SELECT 'Migration 028_sender_account_metrics complete' AS status;
