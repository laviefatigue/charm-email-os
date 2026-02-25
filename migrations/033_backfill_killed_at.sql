-- Migration: 033_backfill_killed_at.sql
-- Purpose: Backfill killed_at timestamp for existing dead inboxes
-- Related: Option A - Schema First (data integrity)

-- Problem: Some inboxes were marked as 'dead' before kill_processor set killed_at
-- Solution: Use updated_at as proxy for when they were killed

-- Backfill killed_at for dead inboxes that are missing the timestamp
UPDATE sender_accounts
SET killed_at = COALESCE(
    -- Prefer the kill_queue tagged_at if available
    (SELECT tagged_at FROM kill_queue kq WHERE kq.inbox_id = sender_accounts.id ORDER BY tagged_at DESC LIMIT 1),
    -- Otherwise use updated_at as proxy
    updated_at,
    -- Last resort: use NOW() if both are NULL
    NOW()
)
WHERE inbox_state = 'dead'
  AND killed_at IS NULL;

-- Also ensure kill_trigger is set if we can determine it from kill_queue
UPDATE sender_accounts sa
SET kill_trigger = (
    SELECT kq.trigger_type::kill_trigger_type
    FROM kill_queue kq
    WHERE kq.inbox_id = sa.id
    ORDER BY kq.updated_at DESC
    LIMIT 1
)
WHERE sa.inbox_state = 'dead'
  AND sa.kill_trigger IS NULL
  AND EXISTS (SELECT 1 FROM kill_queue kq WHERE kq.inbox_id = sa.id);

-- Report stats
SELECT
    COUNT(*) FILTER (WHERE inbox_state = 'dead') as total_dead,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND killed_at IS NOT NULL) as has_killed_at,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND kill_trigger IS NOT NULL) as has_kill_trigger
FROM sender_accounts;

SELECT 'Migration 033_backfill_killed_at complete' AS status;
