-- Migration 044: Fix Warmup Observation Timestamps
-- Created: 2026-02-24
--
-- Context:
-- Previous logic estimated warmup_started_at as created_at + 7 days.
-- This was inaccurate - we should record when we OBSERVED the state change.
--
-- Fix:
-- Set warmup_started_at = first_seen_at for all historical records.
-- first_seen_at is when we first synced the account, which is a better approximation.
--
-- Business Rule:
-- If an inbox is connected to EmailBison, it SHOULD be warming (warmup_enabled=TRUE).
-- warmup_started_at tracks when we first observed this state.
-- warmup_stopped_at tracks when warmup was disabled (a problem state).

-- Step 1: Fix historical warmup_started_at to use first_seen_at
-- This removes the arbitrary +7 day estimation
UPDATE sender_accounts
SET warmup_started_at = first_seen_at
WHERE warmup_started_at IS NOT NULL
  AND first_seen_at IS NOT NULL;

-- Step 2: Add column comments to document the observation-based approach
COMMENT ON COLUMN sender_accounts.warmup_enabled IS
  'Current warmup status from EmailBison API. TRUE = warming (healthy), FALSE = not warming (investigate)';

COMMENT ON COLUMN sender_accounts.warmup_started_at IS
  'Timestamp when sync worker FIRST OBSERVED warmup_enabled=TRUE for this inbox';

COMMENT ON COLUMN sender_accounts.warmup_stopped_at IS
  'Timestamp when sync worker OBSERVED warmup_enabled change from TRUE to FALSE (problem event)';

-- Verification query (run manually):
-- SELECT COUNT(*) as total,
--        COUNT(*) FILTER (WHERE warmup_started_at = first_seen_at) as aligned
-- FROM sender_accounts
-- WHERE warmup_started_at IS NOT NULL;
-- Expected: total = aligned
