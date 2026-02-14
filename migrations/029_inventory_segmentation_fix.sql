-- Migration: 029_inventory_segmentation_fix.sql
-- Purpose: Fix pool status calculation to properly distinguish Reserve vs Incubating
-- Date: 2026-02-13
--
-- Changes:
-- - Reserve: 14+ days old AND warmup_enabled = TRUE (ready to deploy)
-- - Incubating: under 14 days OR warmup not enabled (still warming)
-- - This aligns with business logic: Reserve = deployment-ready inboxes only

-- =============================================================
-- 1. UPDATE THE VIEW with corrected pool status logic
-- =============================================================

CREATE OR REPLACE VIEW v_inbox_inventory_status AS
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

    -- Lifecycle status calculation:
    -- dead = inbox_state is dead
    -- incubating = < 14 days old OR on warming domain
    -- active = everything else
    CASE
        WHEN sa.inbox_state = 'dead' THEN 'dead'
        WHEN sa.created_at > NOW() - INTERVAL '14 days' THEN 'incubating'
        WHEN d.approval_status = 'warming' THEN 'incubating'
        ELSE 'active'
    END as calculated_lifecycle_status,

    -- Pool status calculation:
    -- null = dead inbox
    -- warning = has bounces (1+ in 24h OR 3+ in 7d)
    -- deployed = in active campaigns
    -- reserve = 14+ days AND warmup enabled (ready to deploy)
    -- incubating = under 14 days OR warmup not enabled (still warming)
    CASE
        WHEN sa.inbox_state = 'dead' THEN NULL
        WHEN COALESCE(sa.hard_bounces_24h, 0) >= 1
             OR COALESCE(sa.hard_bounces_7d, 0) >= 3 THEN 'warning'
        WHEN EXISTS (
            SELECT 1 FROM campaign_inboxes ci
            WHERE ci.sender_account_id = sa.id
            AND ci.is_active = TRUE
        ) THEN 'deployed'
        -- Reserve: 14+ days AND warmup enabled (deployment-ready)
        WHEN sa.created_at <= NOW() - INTERVAL '14 days'
             AND COALESCE(sa.warmup_enabled, TRUE) = TRUE THEN 'reserve'
        -- Incubating: everything else (under 14 days OR warmup not enabled)
        ELSE 'incubating'
    END as calculated_pool_status,

    -- Associated campaigns (for deployed inboxes)
    (
        SELECT ARRAY_AGG(DISTINCT ci.campaign_id)
        FROM campaign_inboxes ci
        WHERE ci.sender_account_id = sa.id
        AND ci.is_active = TRUE
        AND ci.campaign_id IS NOT NULL
    ) as associated_campaign_ids,

    -- Age in days
    EXTRACT(DAY FROM NOW() - sa.created_at)::INTEGER as age_days,

    -- Domain info
    SPLIT_PART(sa.email_address, '@', 2) as domain_name,
    d.approval_status as domain_status,
    d.latest_health_score as domain_health_score,
    d.infrastructure_type as domain_infrastructure_type

FROM sender_accounts sa
LEFT JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
    AND sa.workspace_id = d.workspace_id;

COMMENT ON VIEW v_inbox_inventory_status IS
'Real-time inventory status view with calculated pool and lifecycle statuses. Reserve = 14+ days + warmup enabled. Incubating = under 14 days or warmup not enabled.';

-- =============================================================
-- 2. UPDATE EXISTING POOL STATUS VALUES (optional - recalculate)
-- =============================================================

-- Set pool status based on new logic (14+ days + warmup enabled for reserve)
UPDATE sender_accounts sa
SET inventory_pool_status = CASE
    WHEN sa.inbox_state = 'dead' THEN NULL
    WHEN COALESCE(sa.hard_bounces_24h, 0) >= 1 OR COALESCE(sa.hard_bounces_7d, 0) >= 3 THEN 'warning'
    WHEN EXISTS (SELECT 1 FROM campaign_inboxes ci WHERE ci.sender_account_id = sa.id AND ci.is_active) THEN 'deployed'
    -- Reserve: 14+ days AND warmup enabled
    WHEN sa.created_at <= NOW() - INTERVAL '14 days'
         AND COALESCE(sa.warmup_enabled, TRUE) = TRUE THEN 'reserve'
    -- Incubating: everything else
    ELSE 'incubating'
END
WHERE sa.inbox_state = 'live';

-- Done!
SELECT 'Migration 029_inventory_segmentation_fix complete' AS status;
