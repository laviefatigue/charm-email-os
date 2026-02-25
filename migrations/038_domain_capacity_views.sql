-- Migration: 038_domain_capacity_views.sql
-- Purpose: Domain capacity tracking using EXISTING data (no automation changes)
-- Date: 2026-02-23
--
-- This migration creates views that calculate domain capacity from data
-- we're ALREADY syncing from EmailBison:
--   - sender_accounts.daily_limit (actual send capacity per inbox)
--   - sender_accounts.esp (google, microsoft)
--   - sender_accounts.inbox_state (live, dead)
--
-- HyperTide capacity model:
--   - Entra: 50 inboxes/domain × 2 emails/day = 100 emails/day expected
--   - Google: 3 inboxes/domain × 15-20 emails/day = 45-60 emails/day expected

-- =====================================================
-- VIEW 1: Domain Capacity Summary
-- Shows current vs expected capacity per domain
-- =====================================================

CREATE OR REPLACE VIEW v_domain_capacity AS
SELECT
    d.id AS domain_id,
    d.domain_name,
    d.workspace_id,
    d.domain_state,
    d.is_active,

    -- Provider type: derive from ESP of inboxes on domain
    -- If ANY inbox is microsoft, it's an Entra domain; otherwise Google
    CASE
        WHEN EXISTS (
            SELECT 1 FROM sender_accounts sa
            WHERE SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
              AND sa.workspace_id = d.workspace_id
              AND sa.esp = 'microsoft'
        ) THEN 'entra'
        ELSE 'google'
    END AS provider_type,

    -- Inbox counts
    COUNT(sa.id) AS total_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') AS live_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') AS dead_inboxes,

    -- Actual capacity from daily_limit (what EmailBison allows)
    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0) AS current_daily_capacity,
    COALESCE(SUM(sa.daily_limit), 0) AS total_provisioned_capacity,

    -- Expected capacity based on HyperTide model
    CASE
        WHEN EXISTS (
            SELECT 1 FROM sender_accounts sa2
            WHERE SPLIT_PART(sa2.email_address, '@', 2) = d.domain_name
              AND sa2.workspace_id = d.workspace_id
              AND sa2.esp = 'microsoft'
        ) THEN 100  -- Entra: 50 inboxes × 2 emails/day
        ELSE 60     -- Google: 3 inboxes × 20 emails/day
    END AS expected_daily_capacity,

    -- Capacity utilization (current / expected)
    ROUND(
        COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0)::NUMERIC /
        NULLIF(
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM sender_accounts sa3
                    WHERE SPLIT_PART(sa3.email_address, '@', 2) = d.domain_name
                      AND sa3.workspace_id = d.workspace_id
                      AND sa3.esp = 'microsoft'
                ) THEN 100
                ELSE 60
            END,
            0
        ) * 100,
        1
    ) AS capacity_utilization_pct,

    -- Viability status
    CASE
        WHEN COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') = 0 THEN 'deprecated'
        WHEN COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0)::NUMERIC /
             NULLIF(
                 CASE
                     WHEN EXISTS (
                         SELECT 1 FROM sender_accounts sa4
                         WHERE SPLIT_PART(sa4.email_address, '@', 2) = d.domain_name
                           AND sa4.workspace_id = d.workspace_id
                           AND sa4.esp = 'microsoft'
                     ) THEN 100
                     ELSE 60
                 END, 0
             ) < 0.40 THEN 'critical'
        WHEN COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0)::NUMERIC /
             NULLIF(
                 CASE
                     WHEN EXISTS (
                         SELECT 1 FROM sender_accounts sa5
                         WHERE SPLIT_PART(sa5.email_address, '@', 2) = d.domain_name
                           AND sa5.workspace_id = d.workspace_id
                           AND sa5.esp = 'microsoft'
                     ) THEN 100
                     ELSE 60
                 END, 0
             ) < 0.70 THEN 'warning'
        ELSE 'healthy'
    END AS viability_status,

    -- Capacity lost (from dead inboxes)
    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'dead'), 0) AS capacity_lost,

    -- Average daily_limit per inbox (for validation)
    ROUND(AVG(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 1) AS avg_daily_limit_per_inbox

FROM domains d
LEFT JOIN sender_accounts sa
    ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
    AND sa.workspace_id = d.workspace_id
WHERE d.is_active = TRUE
GROUP BY d.id, d.domain_name, d.workspace_id, d.domain_state, d.is_active;


-- =====================================================
-- VIEW 2: Workspace Capacity Summary
-- Aggregated capacity by workspace and provider
-- =====================================================

CREATE OR REPLACE VIEW v_workspace_capacity_summary AS
SELECT
    dc.workspace_id,
    dc.provider_type,

    -- Domain counts by viability
    COUNT(*) AS total_domains,
    COUNT(*) FILTER (WHERE dc.viability_status = 'healthy') AS healthy_domains,
    COUNT(*) FILTER (WHERE dc.viability_status = 'warning') AS warning_domains,
    COUNT(*) FILTER (WHERE dc.viability_status = 'critical') AS critical_domains,
    COUNT(*) FILTER (WHERE dc.viability_status = 'deprecated') AS deprecated_domains,

    -- Inbox totals
    SUM(dc.total_inboxes) AS total_inboxes,
    SUM(dc.live_inboxes) AS live_inboxes,
    SUM(dc.dead_inboxes) AS dead_inboxes,

    -- Capacity totals
    SUM(dc.expected_daily_capacity) AS expected_daily_capacity,
    SUM(dc.current_daily_capacity) AS current_daily_capacity,
    SUM(dc.capacity_lost) AS total_capacity_lost,

    -- Overall utilization
    ROUND(
        SUM(dc.current_daily_capacity)::NUMERIC /
        NULLIF(SUM(dc.expected_daily_capacity), 0) * 100,
        1
    ) AS overall_utilization_pct

FROM v_domain_capacity dc
GROUP BY dc.workspace_id, dc.provider_type;


-- =====================================================
-- VIEW 3: Domains At Risk
-- Domains below 70% capacity utilization
-- =====================================================

CREATE OR REPLACE VIEW v_domains_at_risk AS
SELECT
    dc.domain_id,
    dc.domain_name,
    dc.workspace_id,
    dc.provider_type,
    dc.live_inboxes,
    dc.dead_inboxes,
    dc.current_daily_capacity,
    dc.expected_daily_capacity,
    dc.capacity_utilization_pct,
    dc.viability_status,
    dc.capacity_lost,

    -- Estimated days until deprecated (if killing continues at current rate)
    CASE
        WHEN dc.live_inboxes > 0 AND dc.dead_inboxes > 0 THEN
            ROUND(
                dc.live_inboxes::NUMERIC /
                (dc.dead_inboxes::NUMERIC / GREATEST(1,
                    EXTRACT(days FROM NOW() - d.created_at)
                ))
            )::INTEGER
        ELSE NULL
    END AS estimated_days_until_deprecated

FROM v_domain_capacity dc
JOIN domains d ON d.id = dc.domain_id
WHERE dc.viability_status IN ('warning', 'critical')
ORDER BY dc.capacity_utilization_pct ASC;


-- =====================================================
-- VIEW 4: Capacity Validation
-- Cross-check daily_limit against expected values
-- =====================================================

CREATE OR REPLACE VIEW v_capacity_validation AS
SELECT
    dc.domain_id,
    dc.domain_name,
    dc.workspace_id,
    dc.provider_type,
    dc.live_inboxes,
    dc.avg_daily_limit_per_inbox,

    -- Expected daily_limit based on provider
    CASE dc.provider_type
        WHEN 'entra' THEN 2
        WHEN 'google' THEN 20
        ELSE NULL
    END AS expected_daily_limit,

    -- Validation: does actual match expected?
    CASE
        WHEN dc.provider_type = 'entra' AND dc.avg_daily_limit_per_inbox BETWEEN 1 AND 5 THEN 'valid'
        WHEN dc.provider_type = 'google' AND dc.avg_daily_limit_per_inbox BETWEEN 15 AND 25 THEN 'valid'
        WHEN dc.avg_daily_limit_per_inbox IS NULL THEN 'no_data'
        ELSE 'mismatch'
    END AS validation_status,

    -- Warning message if mismatch
    CASE
        WHEN dc.provider_type = 'entra' AND dc.avg_daily_limit_per_inbox NOT BETWEEN 1 AND 5
            THEN 'Entra domain has unexpected daily_limit: ' || dc.avg_daily_limit_per_inbox::TEXT || ' (expected ~2)'
        WHEN dc.provider_type = 'google' AND dc.avg_daily_limit_per_inbox NOT BETWEEN 15 AND 25
            THEN 'Google domain has unexpected daily_limit: ' || dc.avg_daily_limit_per_inbox::TEXT || ' (expected ~20)'
        ELSE NULL
    END AS validation_message

FROM v_domain_capacity dc
WHERE dc.live_inboxes > 0;


-- =====================================================
-- Sample Queries
-- =====================================================

-- Query 1: Get capacity dashboard for a workspace
-- SELECT * FROM v_workspace_capacity_summary WHERE workspace_id = 'your-workspace-id';

-- Query 2: Get domains at risk
-- SELECT * FROM v_domains_at_risk WHERE workspace_id = 'your-workspace-id';

-- Query 3: Validate capacity data
-- SELECT * FROM v_capacity_validation WHERE validation_status = 'mismatch';

-- Query 4: Full domain capacity details
-- SELECT * FROM v_domain_capacity WHERE workspace_id = 'your-workspace-id' ORDER BY capacity_utilization_pct ASC;


COMMENT ON VIEW v_domain_capacity IS 'Per-domain capacity metrics calculated from existing EmailBison sync data';
COMMENT ON VIEW v_workspace_capacity_summary IS 'Aggregated capacity by workspace and provider type (Entra vs Google)';
COMMENT ON VIEW v_domains_at_risk IS 'Domains below 70% capacity utilization that need attention';
COMMENT ON VIEW v_capacity_validation IS 'Cross-validates daily_limit against expected HyperTide values';

SELECT 'Migration 038_domain_capacity_views complete' AS status;
