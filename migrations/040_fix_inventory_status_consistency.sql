-- Migration: 040_fix_inventory_status_consistency.sql
-- Purpose: Fix inconsistent inventory_lifecycle_status and inventory_pool_status values
-- Date: 2026-02-23
--
-- Problem: These columns were set during migrations 021/029 but never updated by:
--   - sync_accounts.py (on each sync)
--   - kill_processor.py (when killing inboxes)
--
-- This migration fixes the existing data inconsistencies.

-- =============================================================
-- 1. FIX LIFECYCLE STATUS
-- =============================================================

-- Dead inboxes should have lifecycle_status = 'dead'
UPDATE sender_accounts
SET inventory_lifecycle_status = 'dead'
WHERE inbox_state = 'dead'
  AND inventory_lifecycle_status != 'dead';

-- Live inboxes < 14 days old should be 'incubating'
UPDATE sender_accounts
SET inventory_lifecycle_status = 'incubating'
WHERE inbox_state = 'live'
  AND created_at > NOW() - INTERVAL '14 days'
  AND inventory_lifecycle_status != 'incubating';

-- Live inboxes >= 14 days old should be 'active'
UPDATE sender_accounts
SET inventory_lifecycle_status = 'active'
WHERE inbox_state = 'live'
  AND created_at <= NOW() - INTERVAL '14 days'
  AND inventory_lifecycle_status != 'active';

-- =============================================================
-- 2. FIX POOL STATUS
-- =============================================================

-- Dead inboxes should have pool_status = NULL
UPDATE sender_accounts
SET inventory_pool_status = NULL
WHERE inbox_state = 'dead'
  AND inventory_pool_status IS NOT NULL;

-- Live inboxes with bounces should be 'warning'
UPDATE sender_accounts
SET inventory_pool_status = 'warning'
WHERE inbox_state = 'live'
  AND (COALESCE(hard_bounces_24h, 0) >= 1 OR COALESCE(hard_bounces_7d, 0) >= 3)
  AND inventory_pool_status != 'warning';

-- Live inboxes in campaigns should be 'deployed'
UPDATE sender_accounts sa
SET inventory_pool_status = 'deployed'
WHERE inbox_state = 'live'
  AND inventory_pool_status NOT IN ('deployed', 'warning')
  AND EXISTS (
    SELECT 1 FROM campaign_inboxes ci
    WHERE ci.sender_account_id = sa.id
    AND ci.is_active = TRUE
  );

-- Live inboxes 14+ days + warmup enabled should be 'reserve'
UPDATE sender_accounts
SET inventory_pool_status = 'reserve'
WHERE inbox_state = 'live'
  AND created_at <= NOW() - INTERVAL '14 days'
  AND COALESCE(warmup_enabled, TRUE) = TRUE
  AND inventory_pool_status NOT IN ('deployed', 'warning', 'reserve');

-- Everything else that's live should be 'incubating'
UPDATE sender_accounts
SET inventory_pool_status = 'incubating'
WHERE inbox_state = 'live'
  AND inventory_pool_status IS NULL;

-- =============================================================
-- 3. VERIFICATION
-- =============================================================

-- Show the fixed counts
SELECT
    'After Fix' as status,
    inventory_lifecycle_status,
    inbox_state,
    COUNT(*) as count
FROM sender_accounts
GROUP BY inventory_lifecycle_status, inbox_state
ORDER BY inventory_lifecycle_status, inbox_state;

SELECT 'Migration 040_fix_inventory_status_consistency complete' AS status;
