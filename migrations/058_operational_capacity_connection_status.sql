-- Migration 058: Update Capacity Views to Use Connection Status
-- Problem: Capacity calculations count all live inboxes, but disconnected inboxes have 0 operational capacity
-- Solution: Filter capacity calculations by status = 'Connected' (OAuth active)
--
-- OPERATIONAL CAPACITY = CONNECTED live inboxes only
-- A live but disconnected inbox:
--   - Has NOT been killed (inbox_state = 'live')
--   - BUT has no OAuth connection (status = 'Not connected' or 'Disconnected')
--   - Therefore has 0 operational capacity (cannot send emails)
--
-- This aligns with the sync worker (daily_snapshot.py) which already does this correctly.

-- ============================================
-- STEP 1: Drop dependent views in correct order
-- ============================================

DROP VIEW IF EXISTS v_client_capacity CASCADE;
DROP VIEW IF EXISTS v_domains_at_risk CASCADE;
DROP VIEW IF EXISTS v_domain_capacity CASCADE;

-- ============================================
-- STEP 2: Recreate v_domain_capacity with connection status
-- ============================================

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
    -- Inbox counts (total)
    COUNT(sa.id) AS total_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') AS live_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') AS dead_inboxes,
    -- NEW: Connection status for live inboxes
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS connected_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')) AS disconnected_inboxes,
    -- OPERATIONAL CAPACITY = CONNECTED live inboxes only
    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected'), 0) AS current_daily_capacity,
    COALESCE(SUM(sa.daily_limit), 0) AS total_provisioned_capacity,
    -- Capacity that would be available if all disconnected inboxes reconnected
    COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live'), 0) AS potential_daily_capacity,
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
    -- Capacity utilization % (based on CONNECTED capacity)
    ROUND(
        COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected'), 0)::NUMERIC /
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
    -- Connection ratio (what % of live inboxes are connected)
    ROUND(
        CASE
            WHEN COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') > 0
            THEN COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected')::NUMERIC /
                 COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live')::NUMERIC * 100
            ELSE 0
        END, 1
    ) AS connection_ratio_pct,
    -- UPDATED viability_status: includes all_disconnected status
    CASE
        -- Never had any inboxes = awaiting provisioning (not counted in health)
        WHEN COUNT(sa.id) = 0 THEN 'awaiting_provisioning'
        -- Had inboxes but all are now dead = deprecated (actually dead)
        WHEN COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') = 0 THEN 'deprecated'
        -- NEW: Has live inboxes but ALL are disconnected = all_disconnected (0 operational capacity)
        WHEN COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') = 0
             AND COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') > 0 THEN 'all_disconnected'
        -- Has CONNECTED inboxes but capacity < 40% = critical
        WHEN (
            COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected'), 0)::NUMERIC /
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
            COALESCE(SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected'), 0)::NUMERIC /
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
    -- Average daily limit per CONNECTED inbox
    ROUND(AVG(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected'), 1) AS avg_daily_limit_per_inbox
FROM domains d
LEFT JOIN sender_accounts sa ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
    AND sa.workspace_id = d.workspace_id
WHERE d.is_active = true
GROUP BY d.id, d.domain_name, d.workspace_id, d.domain_state, d.is_active;

COMMENT ON VIEW v_domain_capacity IS
'Domain-level capacity based on CONNECTED inboxes only. Statuses:
- awaiting_provisioning: No inboxes yet (excluded from health)
- deprecated: All inboxes dead (killed by triggers)
- all_disconnected: Has live inboxes but all OAuth disconnected (0 operational capacity)
- critical: <40% connected capacity
- warning: <70% connected capacity
- healthy: >=70% connected capacity

New columns:
- connected_inboxes: Live inboxes with active OAuth
- disconnected_inboxes: Live inboxes with expired OAuth
- connection_ratio_pct: % of live inboxes that are connected
- potential_daily_capacity: Capacity if all disconnected inboxes reconnected';

-- ============================================
-- STEP 3: Recreate v_domains_at_risk with new status
-- ============================================

CREATE VIEW v_domains_at_risk AS
SELECT *
FROM v_domain_capacity
WHERE viability_status IN ('warning', 'critical', 'deprecated', 'all_disconnected')
ORDER BY
    CASE viability_status
        WHEN 'deprecated' THEN 1      -- Completely dead (no live inboxes)
        WHEN 'all_disconnected' THEN 2 -- 0 operational capacity (needs reconnection)
        WHEN 'critical' THEN 3         -- <40% connected capacity
        WHEN 'warning' THEN 4          -- <70% connected capacity
    END,
    capacity_utilization_pct ASC NULLS FIRST;

COMMENT ON VIEW v_domains_at_risk IS
'Domains needing attention. Priority: deprecated > all_disconnected > critical > warning.
all_disconnected domains have live inboxes but 0 operational capacity due to OAuth expiration.';

-- ============================================
-- STEP 4: Recreate v_client_capacity with connection status
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
        -- NEW: Connection status counts
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS connected_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')) AS disconnected_count,
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
        -- NEW: All disconnected (live inboxes but 0 connected)
        COUNT(*) FILTER (WHERE dc.viability_status = 'all_disconnected') AS all_disconnected_domains,
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
    -- Entra actuals (domains_actual = PROVISIONED domains only)
    COALESCE(dc_entra.provisioned_domains, 0) AS entra_domains_actual,
    COALESCE(dc_entra.healthy_domains, 0) AS entra_domains_healthy,
    COALESCE(dc_entra.at_risk_domains, 0) AS entra_domains_at_risk,
    COALESCE(dc_entra.deprecated_domains, 0) AS entra_domains_deprecated,
    COALESCE(dc_entra.all_disconnected_domains, 0) AS entra_domains_all_disconnected,
    COALESCE(dc_entra.awaiting_provisioning_domains, 0) AS entra_domains_awaiting,
    COALESCE(dc_entra.total_domains, 0) AS entra_domains_total,
    COALESCE(ic_entra.live_count, 0) AS entra_inboxes_live,
    -- NEW: Connected vs disconnected inbox counts
    COALESCE(ic_entra.connected_count, 0) AS entra_inboxes_connected,
    COALESCE(ic_entra.disconnected_count, 0) AS entra_inboxes_disconnected,
    COALESCE(ic_entra.incubating_count, 0) AS entra_inboxes_incubating,
    COALESCE(ic_entra.active_count, 0) AS entra_inboxes_active,
    COALESCE(ic_entra.dead_count, 0) AS entra_inboxes_dead,
    COALESCE(ic_entra.reserve_count, 0) AS entra_inboxes_reserve,
    -- Entra gaps (against CONNECTED inboxes for operational capacity)
    GREATEST(0, st.entra_inboxes_target - COALESCE(ic_entra.connected_count, 0)) AS entra_inbox_gap,
    GREATEST(0, st.entra_domains_target - (COALESCE(dc_entra.provisioned_domains, 0) - COALESCE(dc_entra.deprecated_domains, 0) - COALESCE(dc_entra.all_disconnected_domains, 0))) AS entra_domain_gap,
    CEIL(GREATEST(0, st.entra_domains_target - (COALESCE(dc_entra.provisioned_domains, 0) - COALESCE(dc_entra.deprecated_domains, 0) - COALESCE(dc_entra.all_disconnected_domains, 0)))::NUMERIC / NULLIF(st.entra_domains_per_package, 0)::NUMERIC) AS entra_orders_needed,
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
    COALESCE(dc_google.all_disconnected_domains, 0) AS google_domains_all_disconnected,
    COALESCE(dc_google.awaiting_provisioning_domains, 0) AS google_domains_awaiting,
    COALESCE(dc_google.total_domains, 0) AS google_domains_total,
    COALESCE(ic_google.live_count, 0) AS google_inboxes_live,
    -- NEW: Connected vs disconnected inbox counts
    COALESCE(ic_google.connected_count, 0) AS google_inboxes_connected,
    COALESCE(ic_google.disconnected_count, 0) AS google_inboxes_disconnected,
    COALESCE(ic_google.incubating_count, 0) AS google_inboxes_incubating,
    COALESCE(ic_google.active_count, 0) AS google_inboxes_active,
    COALESCE(ic_google.dead_count, 0) AS google_inboxes_dead,
    COALESCE(ic_google.reserve_count, 0) AS google_inboxes_reserve,
    -- Google gaps (against CONNECTED inboxes for operational capacity)
    GREATEST(0, st.google_inboxes_target - COALESCE(ic_google.connected_count, 0)) AS google_inbox_gap,
    GREATEST(0, st.google_domains_target - (COALESCE(dc_google.provisioned_domains, 0) - COALESCE(dc_google.deprecated_domains, 0) - COALESCE(dc_google.all_disconnected_domains, 0))) AS google_domain_gap,
    CEIL(GREATEST(0, st.google_domains_target - (COALESCE(dc_google.provisioned_domains, 0) - COALESCE(dc_google.deprecated_domains, 0) - COALESCE(dc_google.all_disconnected_domains, 0)))::NUMERIC / NULLIF(st.google_domains_per_package, 0)::NUMERIC) AS google_orders_needed,
    -- Pipeline buffer (incubating + reserve)
    COALESCE(ic_entra.incubating_count, 0) + COALESCE(ic_entra.reserve_count, 0) AS entra_pipeline_buffer,
    COALESCE(ic_google.incubating_count, 0) + COALESCE(ic_google.reserve_count, 0) AS google_pipeline_buffer,
    -- Buffer ratios
    ROUND((COALESCE(ic_entra.incubating_count, 0) + COALESCE(ic_entra.reserve_count, 0))::NUMERIC / NULLIF(COALESCE(ic_entra.active_count, 0), 0)::NUMERIC, 2) AS entra_buffer_ratio,
    ROUND((COALESCE(ic_google.incubating_count, 0) + COALESCE(ic_google.reserve_count, 0))::NUMERIC / NULLIF(COALESCE(ic_google.active_count, 0), 0)::NUMERIC, 2) AS google_buffer_ratio,
    st.spare_ratio AS target_buffer_ratio,
    -- NEW: Connection ratios (operational health)
    ROUND(COALESCE(ic_entra.connected_count, 0)::NUMERIC / NULLIF(COALESCE(ic_entra.live_count, 0), 0)::NUMERIC * 100, 1) AS entra_connection_ratio_pct,
    ROUND(COALESCE(ic_google.connected_count, 0)::NUMERIC / NULLIF(COALESCE(ic_google.live_count, 0), 0)::NUMERIC * 100, 1) AS google_connection_ratio_pct
FROM client_workspace cw
LEFT JOIN subscription_targets st ON st.client_id = cw.client_id
LEFT JOIN inbox_counts ic_entra ON ic_entra.workspace_id = cw.workspace_id AND ic_entra.provider_type = 'entra'
LEFT JOIN inbox_counts ic_google ON ic_google.workspace_id = cw.workspace_id AND ic_google.provider_type = 'google'
LEFT JOIN domain_counts dc_entra ON dc_entra.workspace_id = cw.workspace_id AND dc_entra.provider_type = 'entra'
LEFT JOIN domain_counts dc_google ON dc_google.workspace_id = cw.workspace_id AND dc_google.provider_type = 'google';

COMMENT ON VIEW v_client_capacity IS
'Client infrastructure capacity based on CONNECTED inboxes.

Key changes from previous version:
- inbox_gap now compares against connected_count (not live_count)
- domain_gap excludes all_disconnected domains (no operational capacity)
- New columns: *_inboxes_connected, *_inboxes_disconnected, *_domains_all_disconnected, *_connection_ratio_pct

Operational capacity = Connected inboxes only. Disconnected inboxes need OAuth reconnection via HyperTide.';

-- ============================================
-- VERIFICATION QUERIES
-- ============================================

-- Show current state by viability_status
SELECT
    'Domain Viability Summary' AS report,
    viability_status,
    COUNT(*) AS domain_count,
    SUM(live_inboxes) AS total_live_inboxes,
    SUM(connected_inboxes) AS total_connected_inboxes,
    SUM(disconnected_inboxes) AS total_disconnected_inboxes,
    SUM(current_daily_capacity) AS total_operational_capacity,
    SUM(potential_daily_capacity) AS total_potential_capacity
FROM v_domain_capacity
GROUP BY viability_status
ORDER BY
    CASE viability_status
        WHEN 'awaiting_provisioning' THEN 1
        WHEN 'deprecated' THEN 2
        WHEN 'all_disconnected' THEN 3
        WHEN 'critical' THEN 4
        WHEN 'warning' THEN 5
        WHEN 'healthy' THEN 6
    END;

-- Show domains needing attention
SELECT
    'Domains At Risk' AS report,
    domain_name,
    viability_status,
    live_inboxes,
    connected_inboxes,
    disconnected_inboxes,
    connection_ratio_pct,
    current_daily_capacity AS operational_capacity,
    potential_daily_capacity AS potential_if_reconnected
FROM v_domains_at_risk
LIMIT 20;
