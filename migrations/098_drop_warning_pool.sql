-- Migration 098: drain `inventory_pool_status='warning'` population
--
-- Per ADR-007 (2026-04-29): the pre-overhaul `warning` soft-pause
-- intermediate state is removed. v3 spec doesn't include a warning
-- buffer — inboxes that hit bounce thresholds queue for kill via
-- health_checks rather than entering an indefinite paused state.
--
-- This migration handles the 299 existing warning rows at deploy time
-- (75 Gmail + 224 Microsoft per pre-state snapshot
-- 2026-04-29_warning_drop_pre_state.json):
--
--   1. Gmail warning inboxes that meet the new `hard_bounces_24h >= 1`
--      threshold AND have >= 20 sends (24h or 7d) get a kill_queue row.
--      The kill_processor will drain these on next cycle.
--
--   2. All remaining warning inboxes get their pool restored:
--      - Microsoft → 'deployed' (CEO Rule C2 ride-to-death pin)
--      - Google → domain default ('live'→'deployed', 'reserve'→'reserve',
--                                else NULL)
--
-- Code changes shipping with this migration:
--   - sync_accounts.py: pool CASE no longer writes 'warning' or auto-clears
--   - set_tag_sync.py: drops the 'warning'/'quarantined' branch in
--     _pool_to_tag_targets
--   - health_checks.py: ESP-aware count thresholds (Google 1/1/1,
--     Microsoft 2/3/2 unchanged); 'warning' health_state removed
--   - overhaul_audit.py: replaces pool_warning metric with
--     kill_queue_pending_over_2h
--
-- Idempotency: re-running this migration is safe. The INSERT uses NOT EXISTS
-- to skip already-queued kills; the UPDATE only touches pool='warning' rows
-- which the new code stops creating.

BEGIN;

-- Step 1: Queue kills for Gmail warning inboxes that meet new thresholds.
-- (Pre-state snapshot showed 0 such inboxes due to the pre-bd4a25a
-- total_sends delta bug. Migration is still safe & idempotent if any
-- exist by deploy time.)
INSERT INTO kill_queue (
    inbox_id,
    workspace_id,
    trigger_type,
    trigger_value,
    trigger_threshold,
    status,
    queued_at,
    created_at
)
SELECT
    sa.id,
    sa.workspace_id,
    CASE
        WHEN sa.hard_blocked_24h >= 1 THEN 'hard_blocked_24h'
        WHEN sa.hard_unknown_24h >= 1 THEN 'hard_unknown_24h'
        ELSE 'hard_bounces_24h'
    END,
    GREATEST(
        COALESCE(sa.hard_blocked_24h, 0),
        COALESCE(sa.hard_unknown_24h, 0),
        COALESCE(sa.hard_bounces_24h, 0)
    ),
    1,
    'pending',
    NOW(),
    NOW()
FROM sender_accounts sa
WHERE sa.is_active = TRUE
  AND sa.inbox_state = 'live'
  AND sa.inventory_pool_status = 'warning'
  AND sa.esp = 'gmail'
  AND (
      COALESCE(sa.hard_blocked_24h, 0) >= 1
      OR COALESCE(sa.hard_unknown_24h, 0) >= 1
      OR COALESCE(sa.hard_bounces_24h, 0) >= 1
  )
  AND (
      COALESCE(sa.total_sends_24h, 0) >= 20
      OR COALESCE(sa.total_sends_7d, 0) >= 20
  )
  AND NOT EXISTS (
      SELECT 1 FROM kill_queue kq
      WHERE kq.inbox_id = sa.id AND kq.status = 'pending'
  );

-- Step 2: Restore pool for all remaining warning inboxes (those not just
-- queued for kill). Microsoft gets 'deployed' (pin behavior). Google
-- gets the domain default.
UPDATE sender_accounts sa
SET inventory_pool_status = (
    CASE
        WHEN sa.esp = 'microsoft' THEN 'deployed'
        ELSE (
            SELECT CASE d.pool_status
                WHEN 'live' THEN 'deployed'
                WHEN 'reserve' THEN 'reserve'
                ELSE NULL
            END
            FROM domains d WHERE d.id = sa.domain_id
        )
    END
),
updated_at = NOW()
WHERE sa.is_active = TRUE
  AND sa.inbox_state = 'live'
  AND sa.inventory_pool_status = 'warning'
  AND NOT EXISTS (
      SELECT 1 FROM kill_queue kq
      WHERE kq.inbox_id = sa.id
        AND kq.status = 'pending'
        AND kq.created_at > NOW() - INTERVAL '5 minutes'  -- only the kills we just queued
  );

-- Verification: log pool status distribution after migration.
DO $$
DECLARE
    remaining_warning INTEGER;
    queued_kills INTEGER;
BEGIN
    SELECT COUNT(*) INTO remaining_warning
    FROM sender_accounts
    WHERE inventory_pool_status = 'warning' AND is_active = TRUE AND inbox_state = 'live';

    SELECT COUNT(*) INTO queued_kills
    FROM kill_queue
    WHERE created_at > NOW() - INTERVAL '5 minutes' AND status = 'pending';

    RAISE NOTICE 'Migration 098 complete: % warning inboxes queued for kill, % active warning inboxes remaining',
        queued_kills, remaining_warning;
END $$;

COMMIT;
