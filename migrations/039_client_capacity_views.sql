-- Migration: 039_client_capacity_views.sql
-- Purpose: Client-level capacity tracking against purchased packages
-- Date: 2026-02-23
--
-- Ties together:
--   - client_subscriptions (purchased packages)
--   - v_domain_capacity (current capacity)
--   - sender_accounts lifecycle stages (incubating/active/dead)
--
-- Key insight: Dead inboxes aren't bad if we're rotating properly.
-- The question is: do we need to order more HyperTide packages?

-- =====================================================
-- VIEW 1: Client Capacity Dashboard
-- Shows purchased vs actual vs pipeline per client
-- =====================================================

CREATE OR REPLACE VIEW v_client_capacity AS
WITH client_workspace AS (
    -- Map clients to workspaces
    SELECT
        c.id AS client_id,
        c.name AS client_name,
        c.workspace_id
    FROM clients c
    WHERE c.workspace_id IS NOT NULL
),
subscription_targets AS (
    -- Calculate what each client SHOULD have based on subscription
    SELECT
        cs.client_id,
        -- Entra targets
        cs.entra_packages,
        cs.entra_domains_per_package,
        cs.entra_inboxes_per_domain,
        (cs.entra_packages * cs.entra_domains_per_package) AS entra_domains_target,
        (cs.entra_packages * cs.entra_domains_per_package * cs.entra_inboxes_per_domain) AS entra_inboxes_target,
        -- Google targets
        cs.google_packages,
        cs.google_domains_per_package,
        cs.google_inboxes_per_domain,
        (cs.google_packages * cs.google_domains_per_package) AS google_domains_target,
        (cs.google_packages * cs.google_domains_per_package * cs.google_inboxes_per_domain) AS google_inboxes_target,
        -- Spare ratio for buffer
        cs.spare_ratio,
        -- Total with spare
        CEIL((cs.entra_packages * cs.entra_domains_per_package * cs.entra_inboxes_per_domain) * (1 + cs.spare_ratio)) AS entra_inboxes_with_spare,
        CEIL((cs.google_packages * cs.google_domains_per_package * cs.google_inboxes_per_domain) * (1 + cs.spare_ratio)) AS google_inboxes_with_spare
    FROM client_subscriptions cs
    WHERE cs.status = 'active'
),
inbox_counts AS (
    -- Count inboxes by lifecycle stage per workspace/provider
    SELECT
        sa.workspace_id,
        CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END AS provider_type,
        -- By lifecycle status
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') AS incubating_count,
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'active') AS active_count,
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'dead' OR sa.inbox_state = 'dead') AS dead_count,
        -- By pool status
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve') AS reserve_count,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed') AS deployed_count,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'warning') AS warning_count,
        -- Total live (not dead)
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live') AS live_count,
        COUNT(*) AS total_count
    FROM sender_accounts sa
    GROUP BY sa.workspace_id,
             CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
),
domain_counts AS (
    -- Count domains by viability per workspace/provider
    SELECT
        dc.workspace_id,
        dc.provider_type,
        COUNT(*) AS total_domains,
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

    -- ========== ENTRA SECTION ==========
    st.entra_packages,
    st.entra_domains_target,
    st.entra_inboxes_target,
    st.entra_inboxes_with_spare AS entra_inboxes_target_with_spare,

    -- Current Entra counts
    COALESCE(dc_entra.total_domains, 0) AS entra_domains_actual,
    COALESCE(dc_entra.healthy_domains, 0) AS entra_domains_healthy,
    COALESCE(dc_entra.at_risk_domains, 0) AS entra_domains_at_risk,
    COALESCE(dc_entra.deprecated_domains, 0) AS entra_domains_deprecated,

    COALESCE(ic_entra.live_count, 0) AS entra_inboxes_live,
    COALESCE(ic_entra.incubating_count, 0) AS entra_inboxes_incubating,
    COALESCE(ic_entra.active_count, 0) AS entra_inboxes_active,
    COALESCE(ic_entra.dead_count, 0) AS entra_inboxes_dead,
    COALESCE(ic_entra.reserve_count, 0) AS entra_inboxes_reserve,

    -- Entra gap analysis
    GREATEST(0, st.entra_inboxes_target - COALESCE(ic_entra.live_count, 0)) AS entra_inbox_gap,
    GREATEST(0, st.entra_domains_target - (COALESCE(dc_entra.total_domains, 0) - COALESCE(dc_entra.deprecated_domains, 0))) AS entra_domain_gap,

    -- Entra HyperTide orders needed (1 order = entra_domains_per_package domains)
    CEIL(
        GREATEST(0, st.entra_domains_target - (COALESCE(dc_entra.total_domains, 0) - COALESCE(dc_entra.deprecated_domains, 0)))::NUMERIC
        / NULLIF(st.entra_domains_per_package, 0)
    ) AS entra_orders_needed,

    -- ========== GOOGLE SECTION ==========
    st.google_packages,
    st.google_domains_target,
    st.google_inboxes_target,
    st.google_inboxes_with_spare AS google_inboxes_target_with_spare,

    -- Current Google counts
    COALESCE(dc_google.total_domains, 0) AS google_domains_actual,
    COALESCE(dc_google.healthy_domains, 0) AS google_domains_healthy,
    COALESCE(dc_google.at_risk_domains, 0) AS google_domains_at_risk,
    COALESCE(dc_google.deprecated_domains, 0) AS google_domains_deprecated,

    COALESCE(ic_google.live_count, 0) AS google_inboxes_live,
    COALESCE(ic_google.incubating_count, 0) AS google_inboxes_incubating,
    COALESCE(ic_google.active_count, 0) AS google_inboxes_active,
    COALESCE(ic_google.dead_count, 0) AS google_inboxes_dead,
    COALESCE(ic_google.reserve_count, 0) AS google_inboxes_reserve,

    -- Google gap analysis
    GREATEST(0, st.google_inboxes_target - COALESCE(ic_google.live_count, 0)) AS google_inbox_gap,
    GREATEST(0, st.google_domains_target - (COALESCE(dc_google.total_domains, 0) - COALESCE(dc_google.deprecated_domains, 0))) AS google_domain_gap,

    -- Google HyperTide orders needed (1 order = google_domains_per_package domains)
    CEIL(
        GREATEST(0, st.google_domains_target - (COALESCE(dc_google.total_domains, 0) - COALESCE(dc_google.deprecated_domains, 0)))::NUMERIC
        / NULLIF(st.google_domains_per_package, 0)
    ) AS google_orders_needed,

    -- ========== PIPELINE HEALTH ==========
    -- Total pipeline capacity (incubating + reserve as buffer)
    COALESCE(ic_entra.incubating_count, 0) + COALESCE(ic_entra.reserve_count, 0) AS entra_pipeline_buffer,
    COALESCE(ic_google.incubating_count, 0) + COALESCE(ic_google.reserve_count, 0) AS google_pipeline_buffer,

    -- Buffer ratio (pipeline / active) - should be >= spare_ratio
    ROUND(
        (COALESCE(ic_entra.incubating_count, 0) + COALESCE(ic_entra.reserve_count, 0))::NUMERIC /
        NULLIF(COALESCE(ic_entra.active_count, 0), 0),
        2
    ) AS entra_buffer_ratio,
    ROUND(
        (COALESCE(ic_google.incubating_count, 0) + COALESCE(ic_google.reserve_count, 0))::NUMERIC /
        NULLIF(COALESCE(ic_google.active_count, 0), 0),
        2
    ) AS google_buffer_ratio,

    st.spare_ratio AS target_buffer_ratio

FROM client_workspace cw
LEFT JOIN subscription_targets st ON st.client_id = cw.client_id
LEFT JOIN inbox_counts ic_entra ON ic_entra.workspace_id = cw.workspace_id AND ic_entra.provider_type = 'entra'
LEFT JOIN inbox_counts ic_google ON ic_google.workspace_id = cw.workspace_id AND ic_google.provider_type = 'google'
LEFT JOIN domain_counts dc_entra ON dc_entra.workspace_id = cw.workspace_id AND dc_entra.provider_type = 'entra'
LEFT JOIN domain_counts dc_google ON dc_google.workspace_id = cw.workspace_id AND dc_google.provider_type = 'google';


-- =====================================================
-- VIEW 2: HyperTide Order Queue
-- Actionable list of orders needed across all clients
-- =====================================================

CREATE OR REPLACE VIEW v_hypertide_order_queue AS
SELECT
    cc.client_id,
    cc.client_name,
    'entra' AS provider_type,
    cc.entra_domains_target AS domains_target,
    cc.entra_domains_actual - cc.entra_domains_deprecated AS domains_active,
    cc.entra_domain_gap AS domain_gap,
    cc.entra_orders_needed AS orders_needed,
    cc.entra_inboxes_target AS inboxes_target,
    cc.entra_inboxes_live AS inboxes_live,
    cc.entra_inbox_gap AS inbox_gap,
    cc.entra_pipeline_buffer AS pipeline_buffer,
    CASE
        WHEN cc.entra_orders_needed > 0 THEN 'order_needed'
        WHEN cc.entra_buffer_ratio < cc.target_buffer_ratio THEN 'buffer_low'
        ELSE 'healthy'
    END AS status
FROM v_client_capacity cc
WHERE cc.entra_packages > 0

UNION ALL

SELECT
    cc.client_id,
    cc.client_name,
    'google' AS provider_type,
    cc.google_domains_target AS domains_target,
    cc.google_domains_actual - cc.google_domains_deprecated AS domains_active,
    cc.google_domain_gap AS domain_gap,
    cc.google_orders_needed AS orders_needed,
    cc.google_inboxes_target AS inboxes_target,
    cc.google_inboxes_live AS inboxes_live,
    cc.google_inbox_gap AS inbox_gap,
    cc.google_pipeline_buffer AS pipeline_buffer,
    CASE
        WHEN cc.google_orders_needed > 0 THEN 'order_needed'
        WHEN cc.google_buffer_ratio < cc.target_buffer_ratio THEN 'buffer_low'
        ELSE 'healthy'
    END AS status
FROM v_client_capacity cc
WHERE cc.google_packages > 0

ORDER BY orders_needed DESC NULLS LAST, status;


-- =====================================================
-- VIEW 3: Inbox Pipeline Status
-- Shows inbox flow through lifecycle stages per client
-- =====================================================

CREATE OR REPLACE VIEW v_inbox_pipeline AS
SELECT
    c.id AS client_id,
    c.name AS client_name,
    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END AS provider_type,
    sa.inventory_lifecycle_status,
    sa.inventory_pool_status,
    COUNT(*) AS inbox_count,
    SUM(sa.daily_limit) AS total_daily_capacity,
    AVG(sa.inbox_age_days)::INTEGER AS avg_age_days
FROM clients c
JOIN sender_accounts sa ON sa.workspace_id = c.workspace_id
GROUP BY
    c.id,
    c.name,
    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END,
    sa.inventory_lifecycle_status,
    sa.inventory_pool_status
ORDER BY c.name, provider_type, inventory_lifecycle_status, inventory_pool_status;


-- =====================================================
-- VIEW 4: Raw Workspace Volume (No Package Required)
-- Shows actual volume for ALL workspaces, package or not
-- =====================================================

CREATE OR REPLACE VIEW v_workspace_volume AS
SELECT
    w.id AS workspace_id,
    w.workspace_name,
    c.id AS client_id,
    c.name AS client_name,

    -- Provider breakdown
    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END AS provider_type,

    -- Domain counts
    COUNT(DISTINCT SPLIT_PART(sa.email_address, '@', 2)) AS total_domains,
    COUNT(DISTINCT SPLIT_PART(sa.email_address, '@', 2)) FILTER (
        WHERE sa.inbox_state = 'live'
    ) AS live_domains,

    -- Inbox counts by state
    COUNT(*) AS total_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') AS live_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') AS dead_inboxes,

    -- Inbox counts by lifecycle
    COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') AS incubating_inboxes,
    COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'active') AS active_inboxes,

    -- Inbox counts by pool status
    COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve') AS reserve_inboxes,
    COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed') AS deployed_inboxes,
    COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'warning') AS warning_inboxes,

    -- Capacity
    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0) AS live_daily_capacity,
    COALESCE(SUM(sa.daily_limit), 0) AS total_provisioned_capacity,

    -- Activity metrics
    COALESCE(SUM(sa.emails_sent_all_time), 0) AS total_emails_sent,
    COALESCE(SUM(sa.replies_all_time), 0) AS total_replies,

    -- Has subscription?
    CASE WHEN cs.id IS NOT NULL THEN TRUE ELSE FALSE END AS has_subscription

FROM workspaces w
LEFT JOIN clients c ON c.workspace_id = w.id
LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id
LEFT JOIN client_subscriptions cs ON cs.client_id = c.id AND cs.status = 'active'
WHERE sa.id IS NOT NULL  -- Only workspaces with inboxes
GROUP BY
    w.id,
    w.name,
    c.id,
    c.name,
    CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END,
    CASE WHEN cs.id IS NOT NULL THEN TRUE ELSE FALSE END
ORDER BY w.workspace_name, provider_type;


COMMENT ON VIEW v_client_capacity IS 'Client-level capacity vs purchased packages with gap analysis and HyperTide order needs';
COMMENT ON VIEW v_hypertide_order_queue IS 'Actionable queue of HyperTide orders needed to fill capacity gaps';
COMMENT ON VIEW v_inbox_pipeline IS 'Inbox counts by lifecycle and pool status per client';
COMMENT ON VIEW v_workspace_volume IS 'Raw volume metrics for ALL workspaces regardless of package configuration';

SELECT 'Migration 039_client_capacity_views complete' AS status;
