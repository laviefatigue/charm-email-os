-- Migration 051: Fix Domain Health Calculation
-- Problem: Domains with 0 total inboxes (never provisioned) are counted as "deprecated" (dead)
--          This inflates the "dead" count and makes health % look worse than reality
-- Solution:
--   1. Add 'awaiting_provisioning' status for domains with 0 total inboxes
--   2. Reserve 'deprecated' for domains that HAD inboxes but all died
--   3. Update v_client_capacity to exclude awaiting_provisioning from health calculation

-- ============================================
-- STEP 1: Recreate v_domain_capacity with corrected viability_status
-- ============================================

DROP VIEW IF EXISTS v_client_capacity CASCADE;
DROP VIEW IF EXISTS v_domains_at_risk CASCADE;
DROP VIEW IF EXISTS v_domain_capacity CASCADE;

CREATE VIEW v_domain_capacity AS
SELECT
    d.id AS domain_id,
    d.domain_name,
    d.workspace_id,
    d.domain_state,
    d.is_active,
    -- Provider detection (Entra if any Microsoft inbox exists)
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
    -- Capacity metrics
    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0) AS current_daily_capacity,
    COALESCE(SUM(sa.daily_limit), 0) AS total_provisioned_capacity,
    -- Expected capacity (Entra: 100/day, Google: 60/day per domain)
    CASE
        WHEN EXISTS (
            SELECT 1 FROM sender_accounts sa2
            WHERE SPLIT_PART(sa2.email_address, '@', 2) = d.domain_name
            AND sa2.workspace_id = d.workspace_id
            AND sa2.esp = 'microsoft'
        ) THEN 100
        ELSE 60
    END AS expected_daily_capacity,
    -- Capacity utilization percentage
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
            END, 0
        )::NUMERIC * 100, 1
    ) AS capacity_utilization_pct,
    -- FIXED viability_status: distinguish awaiting_provisioning from deprecated
    CASE
        -- Never had any inboxes = awaiting provisioning (not counted in health)
        WHEN COUNT(sa.id) = 0 THEN 'awaiting_provisioning'
        -- Had inboxes but all are now dead = deprecated (actually dead)
        WHEN COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') = 0 THEN 'deprecated'
        -- Has live inboxes but capacity < 40% = critical
        WHEN (
            COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0)::NUMERIC /
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
            )::NUMERIC
        ) < 0.40 THEN 'critical'
        -- Capacity < 70% = warning
        WHEN (
            COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0)::NUMERIC /
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
            )::NUMERIC
        ) < 0.70 THEN 'warning'
        -- Capacity >= 70% = healthy
        ELSE 'healthy'
    END AS viability_status,
    -- Capacity lost to dead inboxes
    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'dead'), 0) AS capacity_lost,
    -- Average daily limit per live inbox
    ROUND(AVG(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 1) AS avg_daily_limit_per_inbox
FROM domains d
LEFT JOIN sender_accounts sa ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
    AND sa.workspace_id = d.workspace_id
WHERE d.is_active = true
GROUP BY d.id, d.domain_name, d.workspace_id, d.domain_state, d.is_active;

COMMENT ON VIEW v_domain_capacity IS 'Domain-level capacity and health metrics. viability_status: awaiting_provisioning (no inboxes yet), deprecated (all inboxes dead), critical (<40% capacity), warning (<70% capacity), healthy (>=70% capacity)';

-- ============================================
-- STEP 2: Recreate v_domains_at_risk
-- ============================================

CREATE VIEW v_domains_at_risk AS
SELECT *
FROM v_domain_capacity
WHERE viability_status IN ('warning', 'critical', 'deprecated')
ORDER BY
    CASE viability_status
        WHEN 'deprecated' THEN 1
        WHEN 'critical' THEN 2
        WHEN 'warning' THEN 3
    END,
    capacity_utilization_pct ASC NULLS FIRST;

-- ============================================
-- STEP 3: Recreate v_client_capacity with FIXED health calculation
-- Only count domains with at least 1 inbox (ever) in health metrics
-- ============================================

CREATE VIEW v_client_capacity AS
WITH client_workspace AS (
    SELECT
        c.id AS client_id,
        c.name AS client_name,
        c.workspace_id
    FROM clients c
    WHERE c.workspace_id IS NOT NULL
),
subscription_targets AS (
    SELECT
        cs.client_id,
        cs.entra_packages,
        cs.entra_domains_per_package,
        cs.entra_inboxes_per_domain,
        cs.entra_packages * cs.entra_domains_per_package AS entra_domains_target,
        cs.entra_packages * cs.entra_domains_per_package * cs.entra_inboxes_per_domain AS entra_inboxes_target,
        cs.google_packages,
        cs.google_domains_per_package,
        cs.google_inboxes_per_domain,
        cs.google_packages * cs.google_domains_per_package AS google_domains_target,
        cs.google_packages * cs.google_domains_per_package * cs.google_inboxes_per_domain AS google_inboxes_target,
        cs.spare_ratio,
        CEIL((cs.entra_packages * cs.entra_domains_per_package * cs.entra_inboxes_per_domain)::NUMERIC * (1 + cs.spare_ratio)) AS entra_inboxes_with_spare,
        CEIL((cs.google_packages * cs.google_domains_per_package * cs.google_inboxes_per_domain)::NUMERIC * (1 + cs.spare_ratio)) AS google_inboxes_with_spare
    FROM client_subscriptions cs
    WHERE cs.status = 'active'
),
inbox_counts AS (
    SELECT
        sa.workspace_id,
        CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END AS provider_type,
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') AS incubating_count,
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'active') AS active_count,
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'dead' OR sa.inbox_state = 'dead') AS dead_count,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve') AS reserve_count,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed') AS deployed_count,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'warning') AS warning_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live') AS live_count,
        COUNT(*) AS total_count
    FROM sender_accounts sa
    GROUP BY sa.workspace_id, CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
),
domain_counts AS (
    SELECT
        dc.workspace_id,
        dc.provider_type,
        -- Total domains (including awaiting provisioning)
        COUNT(*) AS total_domains,
        -- Provisioned domains (have at least 1 inbox ever) = excludes awaiting_provisioning
        COUNT(*) FILTER (WHERE dc.viability_status != 'awaiting_provisioning') AS provisioned_domains,
        -- Awaiting provisioning (never had inboxes)
        COUNT(*) FILTER (WHERE dc.viability_status = 'awaiting_provisioning') AS awaiting_provisioning_domains,
        -- Health metrics (only from provisioned domains)
        COUNT(*) FILTER (WHERE dc.viability_status = 'healthy') AS healthy_domains,
        COUNT(*) FILTER (WHERE dc.viability_status IN ('warning', 'critical')) AS at_risk_domains,
        COUNT(*) FILTER (WHERE dc.viability_status = 'deprecated') AS deprecated_domains
    FROM v_domain_capacity dc
    GROUP BY dc.workspace_id, dc.provider_type
)
SELECT
    cw.client_id,
    cw.client_name,
    cw.workspace_id,
    -- Entra targets
    st.entra_packages,
    st.entra_domains_target,
    st.entra_inboxes_target,
    st.entra_inboxes_with_spare AS entra_inboxes_target_with_spare,
    -- Entra actuals (domains_actual = PROVISIONED domains only, for accurate health %)
    COALESCE(dc_entra.provisioned_domains, 0) AS entra_domains_actual,
    COALESCE(dc_entra.healthy_domains, 0) AS entra_domains_healthy,
    COALESCE(dc_entra.at_risk_domains, 0) AS entra_domains_at_risk,
    COALESCE(dc_entra.deprecated_domains, 0) AS entra_domains_deprecated,
    COALESCE(dc_entra.awaiting_provisioning_domains, 0) AS entra_domains_awaiting,
    COALESCE(dc_entra.total_domains, 0) AS entra_domains_total,
    COALESCE(ic_entra.live_count, 0) AS entra_inboxes_live,
    COALESCE(ic_entra.incubating_count, 0) AS entra_inboxes_incubating,
    COALESCE(ic_entra.active_count, 0) AS entra_inboxes_active,
    COALESCE(ic_entra.dead_count, 0) AS entra_inboxes_dead,
    COALESCE(ic_entra.reserve_count, 0) AS entra_inboxes_reserve,
    -- Entra gaps (against provisioned, not total)
    GREATEST(0, st.entra_inboxes_target - COALESCE(ic_entra.live_count, 0)) AS entra_inbox_gap,
    GREATEST(0, st.entra_domains_target - (COALESCE(dc_entra.provisioned_domains, 0) - COALESCE(dc_entra.deprecated_domains, 0))) AS entra_domain_gap,
    CEIL(GREATEST(0, st.entra_domains_target - (COALESCE(dc_entra.provisioned_domains, 0) - COALESCE(dc_entra.deprecated_domains, 0)))::NUMERIC / NULLIF(st.entra_domains_per_package, 0)::NUMERIC) AS entra_orders_needed,
    -- Google targets
    st.google_packages,
    st.google_domains_target,
    st.google_inboxes_target,
    st.google_inboxes_with_spare AS google_inboxes_target_with_spare,
    -- Google actuals (domains_actual = PROVISIONED domains only)
    COALESCE(dc_google.provisioned_domains, 0) AS google_domains_actual,
    COALESCE(dc_google.healthy_domains, 0) AS google_domains_healthy,
    COALESCE(dc_google.at_risk_domains, 0) AS google_domains_at_risk,
    COALESCE(dc_google.deprecated_domains, 0) AS google_domains_deprecated,
    COALESCE(dc_google.awaiting_provisioning_domains, 0) AS google_domains_awaiting,
    COALESCE(dc_google.total_domains, 0) AS google_domains_total,
    COALESCE(ic_google.live_count, 0) AS google_inboxes_live,
    COALESCE(ic_google.incubating_count, 0) AS google_inboxes_incubating,
    COALESCE(ic_google.active_count, 0) AS google_inboxes_active,
    COALESCE(ic_google.dead_count, 0) AS google_inboxes_dead,
    COALESCE(ic_google.reserve_count, 0) AS google_inboxes_reserve,
    -- Google gaps
    GREATEST(0, st.google_inboxes_target - COALESCE(ic_google.live_count, 0)) AS google_inbox_gap,
    GREATEST(0, st.google_domains_target - (COALESCE(dc_google.provisioned_domains, 0) - COALESCE(dc_google.deprecated_domains, 0))) AS google_domain_gap,
    CEIL(GREATEST(0, st.google_domains_target - (COALESCE(dc_google.provisioned_domains, 0) - COALESCE(dc_google.deprecated_domains, 0)))::NUMERIC / NULLIF(st.google_domains_per_package, 0)::NUMERIC) AS google_orders_needed,
    -- Pipeline buffer (incubating + reserve)
    COALESCE(ic_entra.incubating_count, 0) + COALESCE(ic_entra.reserve_count, 0) AS entra_pipeline_buffer,
    COALESCE(ic_google.incubating_count, 0) + COALESCE(ic_google.reserve_count, 0) AS google_pipeline_buffer,
    -- Buffer ratios
    ROUND((COALESCE(ic_entra.incubating_count, 0) + COALESCE(ic_entra.reserve_count, 0))::NUMERIC / NULLIF(COALESCE(ic_entra.active_count, 0), 0)::NUMERIC, 2) AS entra_buffer_ratio,
    ROUND((COALESCE(ic_google.incubating_count, 0) + COALESCE(ic_google.reserve_count, 0))::NUMERIC / NULLIF(COALESCE(ic_google.active_count, 0), 0)::NUMERIC, 2) AS google_buffer_ratio,
    st.spare_ratio AS target_buffer_ratio
FROM client_workspace cw
LEFT JOIN subscription_targets st ON st.client_id = cw.client_id
LEFT JOIN inbox_counts ic_entra ON ic_entra.workspace_id = cw.workspace_id AND ic_entra.provider_type = 'entra'
LEFT JOIN inbox_counts ic_google ON ic_google.workspace_id = cw.workspace_id AND ic_google.provider_type = 'google'
LEFT JOIN domain_counts dc_entra ON dc_entra.workspace_id = cw.workspace_id AND dc_entra.provider_type = 'entra'
LEFT JOIN domain_counts dc_google ON dc_google.workspace_id = cw.workspace_id AND dc_google.provider_type = 'google';

COMMENT ON VIEW v_client_capacity IS 'Client infrastructure capacity. domains_actual = provisioned domains (with inboxes). Health % = healthy / (healthy + at_risk + deprecated). Excludes awaiting_provisioning from health calculation.';

-- ============================================
-- VERIFICATION
-- ============================================

-- Show the corrected domain counts for verification
SELECT 'Before fix: domains with 0 inboxes were counted as deprecated (dead)' AS note;
SELECT 'After fix: domains with 0 inboxes are now awaiting_provisioning (excluded from health)' AS note;

-- Verify the fix for Selery
SELECT
    client_name,
    'Entra' AS provider,
    entra_domains_actual AS provisioned,
    entra_domains_healthy AS healthy,
    entra_domains_at_risk AS at_risk,
    entra_domains_deprecated AS deprecated,
    entra_domains_awaiting AS awaiting,
    entra_domains_total AS total,
    CASE WHEN entra_domains_actual > 0
        THEN ROUND(entra_domains_healthy::NUMERIC / entra_domains_actual * 100, 1)
        ELSE 0
    END AS health_pct
FROM v_client_capacity
WHERE client_name = 'Selery'
UNION ALL
SELECT
    client_name,
    'Google' AS provider,
    google_domains_actual,
    google_domains_healthy,
    google_domains_at_risk,
    google_domains_deprecated,
    google_domains_awaiting,
    google_domains_total,
    CASE WHEN google_domains_actual > 0
        THEN ROUND(google_domains_healthy::NUMERIC / google_domains_actual * 100, 1)
        ELSE 0
    END AS health_pct
FROM v_client_capacity
WHERE client_name = 'Selery';
