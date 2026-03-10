-- Selery Domain Allocation Verification & Application
-- Run in Coolify: Projects → charm-email-os → postgres → Terminal
-- Connect: psql -U charm -d postgres
-- Then copy-paste sections into psql

-- =====================================================
-- STEP 1: View Current Capacity & Calculate Reserve
-- Shows: target vs live vs surplus vs reserve capacity
-- =====================================================

\echo '=== SELERY CAPACITY ANALYSIS ==='
WITH capacity AS (
    SELECT
        client_name,
        COALESCE(entra_inboxes_target, 0) as entra_target,
        COALESCE(entra_inboxes_live, 0) as entra_live,
        COALESCE(google_inboxes_target, 0) as google_target,
        COALESCE(google_inboxes_live, 0) as google_live,
        COALESCE(target_buffer_ratio, 0.15) as spare_ratio
    FROM v_client_capacity
    WHERE client_name = 'Selery'
)
SELECT
    client_name,
    '--- ENTRA ---' as section,
    entra_target as target,
    entra_live as live,
    (entra_live - entra_target) as surplus,
    LEAST(FLOOR(entra_target * spare_ratio), GREATEST(0, entra_live - entra_target))::int as reserve_cap_inboxes
FROM capacity
UNION ALL
SELECT
    client_name,
    '--- GOOGLE ---',
    google_target,
    google_live,
    (google_live - google_target),
    LEAST(FLOOR(google_target * spare_ratio), GREATEST(0, google_live - google_target))::int
FROM capacity
WHERE client_name = 'Selery';

-- =====================================================
-- STEP 2: Domain Health Ranking with Allocation Preview
-- Shows each domain scored, with preview allocation
-- =====================================================

\echo ''
\echo '=== DOMAIN HEALTH SCORES & ALLOCATION PREVIEW ==='
WITH capacity AS (
    SELECT
        workspace_id,
        COALESCE(entra_inboxes_target, 0) as entra_target,
        COALESCE(entra_inboxes_live, 0) as entra_live,
        COALESCE(google_inboxes_target, 0) as google_target,
        COALESCE(google_inboxes_live, 0) as google_live,
        COALESCE(target_buffer_ratio, 0.15) as spare_ratio
    FROM v_client_capacity
    WHERE client_name = 'Selery'
),
reserve_caps AS (
    SELECT
        workspace_id,
        LEAST(FLOOR(entra_target * spare_ratio), GREATEST(0, entra_live - entra_target))::int as entra_reserve_cap,
        LEAST(FLOOR(google_target * spare_ratio), GREATEST(0, google_live - google_target))::int as google_reserve_cap
    FROM capacity
),
domain_metrics AS (
    SELECT
        d.id as domain_id,
        d.domain_name,
        d.workspace_id,
        CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END as provider,
        COUNT(sa.id) as inbox_count,
        ROUND(AVG(sa.health_score)::numeric, 1) as avg_health,
        ROUND(AVG(COALESCE(sa.bounce_rate_7d, 0))::numeric, 4) as avg_bounce,
        -- Health score calculation
        100.0
            - CASE WHEN BOOL_OR(sa.kill_trigger::text = 'spam_complaint') THEN 200 ELSE 0 END
            - CASE WHEN BOOL_OR(sa.kill_trigger::text LIKE 'provider_block%') THEN 100 ELSE 0 END
            - (AVG(COALESCE(sa.bounce_rate_7d, 0)) * 500)
            + ((AVG(sa.health_score) - 80) * 2)
            - ((COUNT(sa.id) FILTER (WHERE COALESCE(sa.bounce_rate_7d, 0) > 0.02)::float / GREATEST(COUNT(sa.id), 1)) * 50)
            + CASE WHEN COUNT(sa.id) >= 50 THEN 10 WHEN COUNT(sa.id) >= 3 THEN 5 ELSE 0 END
        AS domain_score
    FROM domains d
    JOIN sender_accounts sa ON sa.domain_id = d.id
    JOIN workspaces w ON d.workspace_id = w.id
    WHERE w.workspace_name = 'Selery'
      AND d.is_active = TRUE
      AND sa.inbox_state = 'live'
      AND sa.is_active = TRUE
    GROUP BY d.id, d.domain_name, d.workspace_id, sa.esp
),
ranked AS (
    SELECT
        dm.*,
        rc.entra_reserve_cap,
        rc.google_reserve_cap,
        SUM(dm.inbox_count) OVER (PARTITION BY dm.provider ORDER BY dm.domain_score DESC) as cumulative_inboxes
    FROM domain_metrics dm
    JOIN reserve_caps rc ON dm.workspace_id = rc.workspace_id
)
SELECT
    provider,
    domain_name,
    inbox_count,
    avg_health,
    ROUND(domain_score::numeric, 1) as score,
    cumulative_inboxes as running_total,
    CASE provider WHEN 'entra' THEN entra_reserve_cap ELSE google_reserve_cap END as reserve_cap,
    CASE
        WHEN cumulative_inboxes <= CASE provider WHEN 'entra' THEN entra_reserve_cap ELSE google_reserve_cap END
        THEN 'RESERVE'
        ELSE 'LIVE'
    END as allocation
FROM ranked
ORDER BY provider, domain_score DESC;

-- =====================================================
-- STEP 3: Allocation Summary
-- =====================================================

\echo ''
\echo '=== ALLOCATION SUMMARY ==='
WITH capacity AS (
    SELECT
        workspace_id,
        LEAST(FLOOR(COALESCE(entra_inboxes_target, 0) * COALESCE(target_buffer_ratio, 0.15)),
              GREATEST(0, COALESCE(entra_inboxes_live, 0) - COALESCE(entra_inboxes_target, 0)))::int as entra_reserve_cap,
        LEAST(FLOOR(COALESCE(google_inboxes_target, 0) * COALESCE(target_buffer_ratio, 0.15)),
              GREATEST(0, COALESCE(google_inboxes_live, 0) - COALESCE(google_inboxes_target, 0)))::int as google_reserve_cap
    FROM v_client_capacity WHERE client_name = 'Selery'
),
domain_metrics AS (
    SELECT
        d.id,
        d.workspace_id,
        CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END as provider,
        COUNT(sa.id) as inbox_count,
        100.0 - CASE WHEN BOOL_OR(sa.kill_trigger::text = 'spam_complaint') THEN 200 ELSE 0 END
              - CASE WHEN BOOL_OR(sa.kill_trigger::text LIKE 'provider_block%') THEN 100 ELSE 0 END
              - (AVG(COALESCE(sa.bounce_rate_7d, 0)) * 500)
              + ((AVG(sa.health_score) - 80) * 2)
        AS domain_score
    FROM domains d
    JOIN sender_accounts sa ON sa.domain_id = d.id
    JOIN workspaces w ON d.workspace_id = w.id
    WHERE w.workspace_name = 'Selery' AND d.is_active = TRUE AND sa.inbox_state = 'live' AND sa.is_active = TRUE
    GROUP BY d.id, d.workspace_id, sa.esp
),
ranked AS (
    SELECT dm.*,
        CASE dm.provider WHEN 'entra' THEN c.entra_reserve_cap ELSE c.google_reserve_cap END as reserve_cap,
        SUM(dm.inbox_count) OVER (PARTITION BY dm.provider ORDER BY dm.domain_score DESC) as cumulative
    FROM domain_metrics dm JOIN capacity c ON dm.workspace_id = c.workspace_id
),
allocated AS (
    SELECT *, CASE WHEN cumulative <= reserve_cap THEN 'reserve' ELSE 'live' END as pool FROM ranked
)
SELECT
    provider,
    COUNT(*) as total_domains,
    SUM(inbox_count) as total_inboxes,
    COUNT(*) FILTER (WHERE pool = 'reserve') as reserve_domains,
    SUM(inbox_count) FILTER (WHERE pool = 'reserve') as reserve_inboxes,
    COUNT(*) FILTER (WHERE pool = 'live') as live_domains,
    SUM(inbox_count) FILTER (WHERE pool = 'live') as live_inboxes,
    ROUND(100.0 * SUM(inbox_count) FILTER (WHERE pool = 'reserve') / SUM(inbox_count), 1) as reserve_pct
FROM allocated
GROUP BY provider
ORDER BY provider;

-- =====================================================
-- STEP 4: APPLY ALLOCATION
-- Run this AFTER verifying the preview above
-- =====================================================

\echo ''
\echo '=== TO APPLY: Copy everything between BEGIN and COMMIT ==='
\echo ''

-- Uncomment and run to apply:

/*
BEGIN;

WITH capacity AS (
    SELECT
        workspace_id,
        LEAST(FLOOR(COALESCE(entra_inboxes_target, 0) * COALESCE(target_buffer_ratio, 0.15)),
              GREATEST(0, COALESCE(entra_inboxes_live, 0) - COALESCE(entra_inboxes_target, 0)))::int as entra_reserve_cap,
        LEAST(FLOOR(COALESCE(google_inboxes_target, 0) * COALESCE(target_buffer_ratio, 0.15)),
              GREATEST(0, COALESCE(google_inboxes_live, 0) - COALESCE(google_inboxes_target, 0)))::int as google_reserve_cap
    FROM v_client_capacity WHERE client_name = 'Selery'
),
domain_metrics AS (
    SELECT
        d.id as domain_id,
        d.workspace_id,
        CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END as provider,
        COUNT(sa.id) as inbox_count,
        100.0 - CASE WHEN BOOL_OR(sa.kill_trigger::text = 'spam_complaint') THEN 200 ELSE 0 END
              - CASE WHEN BOOL_OR(sa.kill_trigger::text LIKE 'provider_block%') THEN 100 ELSE 0 END
              - (AVG(COALESCE(sa.bounce_rate_7d, 0)) * 500)
              + ((AVG(sa.health_score) - 80) * 2)
        AS domain_score
    FROM domains d
    JOIN sender_accounts sa ON sa.domain_id = d.id
    JOIN workspaces w ON d.workspace_id = w.id
    WHERE w.workspace_name = 'Selery' AND d.is_active = TRUE AND sa.inbox_state = 'live' AND sa.is_active = TRUE
    GROUP BY d.id, d.workspace_id, sa.esp
),
ranked AS (
    SELECT dm.*,
        CASE dm.provider WHEN 'entra' THEN c.entra_reserve_cap ELSE c.google_reserve_cap END as reserve_cap,
        SUM(dm.inbox_count) OVER (PARTITION BY dm.provider ORDER BY dm.domain_score DESC) as cumulative
    FROM domain_metrics dm JOIN capacity c ON dm.workspace_id = c.workspace_id
),
reserve_domains AS (
    SELECT domain_id FROM ranked WHERE cumulative <= reserve_cap
)
UPDATE sender_accounts sa
SET
    inventory_pool_status = CASE
        WHEN sa.domain_id IN (SELECT domain_id FROM reserve_domains) THEN 'reserve'
        ELSE 'deployed'
    END,
    updated_at = NOW()
FROM domains d
JOIN workspaces w ON d.workspace_id = w.id
WHERE sa.domain_id = d.id
  AND w.workspace_name = 'Selery'
  AND sa.inbox_state = 'live'
  AND sa.is_active = TRUE;

-- Verify result
\echo 'RESULT:'
SELECT inventory_pool_status, COUNT(*) as inbox_count
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
JOIN workspaces w ON d.workspace_id = w.id
WHERE w.workspace_name = 'Selery' AND sa.inbox_state = 'live'
GROUP BY inventory_pool_status;

COMMIT;
*/
