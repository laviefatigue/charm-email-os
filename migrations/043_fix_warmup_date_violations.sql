-- Migration 043: Fix Warmup Date Violations
-- Created: 2026-02-24
--
-- Problem: 501 records have warmup_stopped_at < warmup_started_at which is logically invalid.
-- This occurred due to sync timing issues where stopped_at was set before started_at was updated.
--
-- Solution: Swap the dates where stopped < started to restore logical consistency,
-- then add a CHECK constraint to prevent future violations.

-- Step 1: Fix existing violations by swapping the dates
-- This preserves both timestamps while making them logically valid
UPDATE sender_accounts
SET
    warmup_started_at = warmup_stopped_at,
    warmup_stopped_at = warmup_started_at
WHERE warmup_stopped_at IS NOT NULL
  AND warmup_started_at IS NOT NULL
  AND warmup_stopped_at < warmup_started_at;

-- Step 2: Add CHECK constraint to prevent future violations
-- The constraint allows:
-- - Both NULL (warmup never started/stopped)
-- - started IS NOT NULL, stopped IS NULL (currently warming)
-- - Both NOT NULL with stopped >= started (normal completed warmup)
ALTER TABLE sender_accounts
ADD CONSTRAINT chk_warmup_dates_logical
CHECK (
    warmup_stopped_at IS NULL
    OR warmup_started_at IS NULL
    OR warmup_stopped_at >= warmup_started_at
);

-- Verify fix (for manual confirmation during migration)
-- SELECT COUNT(*) FROM sender_accounts
-- WHERE warmup_stopped_at < warmup_started_at;
-- Expected: 0
