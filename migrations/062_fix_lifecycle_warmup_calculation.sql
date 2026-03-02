-- Migration: 062_fix_lifecycle_warmup_calculation.sql
-- Purpose: Fix lifecycle calculation to use warmup_started_at instead of created_at
-- Date: 2026-03-01
--
-- PROBLEM:
-- The 14-day incubation period was incorrectly calculated from created_at (when
-- the record was synced to our database) instead of warmup_started_at (when
-- warmup was enabled in EmailBison).
--
-- LOGIC:
-- - warmup_started_at IS NULL -> 'incubating' (never started warmup)
-- - warmup_started_at > NOW() - 14 days -> 'incubating' (still warming)
-- - warmup_started_at <= NOW() - 14 days -> 'active' (graduated)

BEGIN;

-- ============================================================================
-- STEP 1: Fix inventory_lifecycle_status based on warmup_started_at
-- ============================================================================

-- Mark inboxes as 'incubating' if warmup hasn't started or is recent
UPDATE sender_accounts
SET
    inventory_lifecycle_status = 'incubating',
    updated_at = NOW()
WHERE inbox_state = 'live'
  AND (warmup_started_at IS NULL OR warmup_started_at > NOW() - INTERVAL '14 days')
  AND inventory_lifecycle_status != 'incubating';

-- Mark inboxes as 'active' if warmup completed (14+ days)
UPDATE sender_accounts
SET
    inventory_lifecycle_status = 'active',
    updated_at = NOW()
WHERE inbox_state = 'live'
  AND warmup_started_at IS NOT NULL
  AND warmup_started_at <= NOW() - INTERVAL '14 days'
  AND inventory_lifecycle_status != 'active';

-- ============================================================================
-- STEP 2: Fix inventory_pool_status (reserve requires graduated from incubation)
-- ============================================================================

-- Inboxes still incubating should not be in 'reserve'
UPDATE sender_accounts
SET
    inventory_pool_status = NULL,
    updated_at = NOW()
WHERE inbox_state = 'live'
  AND (warmup_started_at IS NULL OR warmup_started_at > NOW() - INTERVAL '14 days')
  AND inventory_pool_status = 'reserve';

-- Graduated inboxes with warmup enabled and no bounces can be 'reserve'
UPDATE sender_accounts
SET
    inventory_pool_status = 'reserve',
    updated_at = NOW()
WHERE inbox_state = 'live'
  AND warmup_started_at IS NOT NULL
  AND warmup_started_at <= NOW() - INTERVAL '14 days'
  AND COALESCE(warmup_enabled, TRUE) = TRUE
  AND COALESCE(hard_bounces_24h, 0) < 1
  AND COALESCE(hard_bounces_7d, 0) < 3
  AND NOT EXISTS (
    SELECT 1 FROM campaign_inboxes ci
    WHERE ci.sender_account_id = sender_accounts.id AND ci.is_active = TRUE
  )
  AND (inventory_pool_status IS NULL OR inventory_pool_status = 'incubating');

-- ============================================================================
-- STEP 3: Recreate v_inbox_inventory_status view with correct logic
-- ============================================================================

DROP VIEW IF EXISTS v_inbox_inventory_status;

CREATE VIEW v_inbox_inventory_status AS
SELECT
    sa.id,
    sa.email_address,
    sa.workspace_id,
    sa.inbox_state,
    sa.pool_tier,
    sa.health_score,
    sa.hard_bounces_24h,
    sa.hard_bounces_7d,
    sa.total_sends_7d,
    sa.created_at,
    sa.warmup_enabled,
    sa.warmup_started_at,

    -- FIXED: Lifecycle status uses warmup_started_at, not created_at
    CASE
        WHEN sa.inbox_state = 'dead' THEN 'dead'
        WHEN sa.warmup_started_at IS NULL THEN 'incubating'
        WHEN sa.warmup_started_at > NOW() - INTERVAL '14 days' THEN 'incubating'
        WHEN d.approval_status = 'warming' THEN 'incubating'
        ELSE 'active'
    END as calculated_lifecycle_status,

    -- FIXED: Pool status uses warmup_started_at for reserve eligibility
    CASE
        WHEN sa.inbox_state = 'dead' THEN NULL
        WHEN COALESCE(sa.hard_bounces_24h, 0) >= 1
             OR COALESCE(sa.hard_bounces_7d, 0) >= 3 THEN 'warning'
        WHEN EXISTS (
            SELECT 1 FROM campaign_inboxes ci
            WHERE ci.sender_account_id = sa.id
            AND ci.is_active = TRUE
        ) THEN 'deployed'
        -- Reserve: warmup complete (14+ days) AND warmup enabled
        WHEN sa.warmup_started_at IS NOT NULL
             AND sa.warmup_started_at <= NOW() - INTERVAL '14 days'
             AND COALESCE(sa.warmup_enabled, TRUE) = TRUE THEN 'reserve'
        -- Everything else (incubating or not in warmup)
        ELSE NULL
    END as calculated_pool_status,

    (
        SELECT ARRAY_AGG(DISTINCT ci.campaign_id)
        FROM campaign_inboxes ci
        WHERE ci.sender_account_id = sa.id
        AND ci.is_active = TRUE
        AND ci.campaign_id IS NOT NULL
    ) as associated_campaign_ids,

    -- Warmup age based on warmup_started_at
    CASE
        WHEN sa.warmup_started_at IS NOT NULL THEN
            EXTRACT(DAY FROM NOW() - sa.warmup_started_at)::INTEGER
        ELSE NULL
    END as warmup_age_days,

    SPLIT_PART(sa.email_address, '@', 2) as domain_name,
    d.approval_status as domain_status,
    d.latest_health_score as domain_health_score,
    d.infrastructure_type as domain_infrastructure_type

FROM sender_accounts sa
LEFT JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
    AND sa.workspace_id = d.workspace_id;

COMMIT;

-- ============================================================================
-- VERIFICATION: Check the fix results
-- ============================================================================

SELECT
    'After Fix' as status,
    inventory_lifecycle_status,
    COUNT(*) as total_count,
    COUNT(*) FILTER (WHERE warmup_started_at IS NULL) as no_warmup_started,
    COUNT(*) FILTER (WHERE warmup_started_at > NOW() - INTERVAL '14 days') as recently_started,
    COUNT(*) FILTER (WHERE warmup_started_at <= NOW() - INTERVAL '14 days') as graduated
FROM sender_accounts
WHERE inbox_state = 'live'
GROUP BY inventory_lifecycle_status
ORDER BY inventory_lifecycle_status;
