-- Migration: Add differentiated bounce counter columns
-- Purpose: Separate hard_blocked (spam/policy rejection) from hard_unknown (bad addresses)
-- per user request: hard_blocked_24h >= 1 instant kill, hard_unknown_24h >= 3 kill

-- Add differentiated bounce counter columns to sender_accounts
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS hard_blocked_24h INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS hard_unknown_24h INTEGER DEFAULT 0;

-- Add index for health check queries (optional, for performance)
CREATE INDEX IF NOT EXISTS idx_sender_accounts_bounce_types
ON sender_accounts (hard_blocked_24h, hard_unknown_24h)
WHERE is_active = TRUE AND inbox_state = 'live';

-- Note: Existing hard_bounces_24h column remains as combined counter (fallback)
-- New counters start at 0 and will be incremented by sync worker
-- No backfill needed - fresh start on differentiated tracking
