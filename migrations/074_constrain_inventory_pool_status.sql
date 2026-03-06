-- Migration 074: Constrain inventory_pool_status values
-- Created: 2026-03-05
-- Purpose: Add CHECK constraint for valid pool status values
--
-- Valid values:
-- - deployed: A-Set, actively assigned to campaigns
-- - reserve: B-Set, warmed and ready to promote
-- - warning: Needs cooldown due to bounces
-- - quarantined: Domain compromised, do NOT promote
-- - NULL: Dead or not yet assigned

BEGIN;

-- First, clean up any invalid values (set to NULL for killed inboxes)
UPDATE sender_accounts
SET inventory_pool_status = NULL
WHERE inventory_pool_status IS NOT NULL
AND inventory_pool_status NOT IN ('deployed', 'reserve', 'warning', 'quarantined');

-- Drop existing constraint if present (idempotent)
ALTER TABLE sender_accounts
DROP CONSTRAINT IF EXISTS chk_inventory_pool_status;

-- Add CHECK constraint
ALTER TABLE sender_accounts
ADD CONSTRAINT chk_inventory_pool_status
CHECK (
    inventory_pool_status IS NULL
    OR inventory_pool_status IN ('deployed', 'reserve', 'warning', 'quarantined')
);

-- Update column comment
COMMENT ON COLUMN sender_accounts.inventory_pool_status IS
'Pool status for inbox inventory management:
- deployed: A-Set, actively assigned to campaigns
- reserve: B-Set, warmed and ready to promote
- warning: Needs cooldown due to bounces
- quarantined: Domain compromised, do NOT promote
- NULL: Dead or not yet assigned';

COMMIT;

-- Log migration
DO $$
DECLARE
    deployed_count INTEGER;
    reserve_count INTEGER;
    quarantined_count INTEGER;
BEGIN
    SELECT
        COUNT(*) FILTER (WHERE inventory_pool_status = 'deployed'),
        COUNT(*) FILTER (WHERE inventory_pool_status = 'reserve'),
        COUNT(*) FILTER (WHERE inventory_pool_status = 'quarantined')
    INTO deployed_count, reserve_count, quarantined_count
    FROM sender_accounts
    WHERE inbox_state = 'live';

    RAISE NOTICE 'Migration 074: Added constraint on inventory_pool_status';
    RAISE NOTICE 'Current distribution - Deployed: %, Reserve: %, Quarantined: %',
        deployed_count, reserve_count, quarantined_count;
END $$;
