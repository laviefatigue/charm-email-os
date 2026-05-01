-- Migration 082: Domain Pipeline Views for Domain Engine V2
-- Created: 2026-03-08
-- Purpose: Add views for tracking domain lifecycle pipeline (Incubating → Reserve → Live)
--
-- LIFECYCLE STAGES:
-- 1. INCUBATING: Domain purchased + has inboxes + warming for < 14 days
-- 2. RESERVE: pool_status = 'reserve' (warmed B-Set, ready to deploy)
-- 3. LIVE: pool_status = 'live' (A-Set, actively sending)
-- 4. BURNED: pool_status = 'burned' (compromised, retired)
--
-- Note: Warmup age is calculated from MIN(sender_accounts.warmup_started_at) for the domain

BEGIN;

-- =====================================================
-- 1. VIEW: v_domain_pipeline
-- =====================================================
-- Shows all domains with their pipeline status and warmup progress

CREATE OR REPLACE VIEW v_domain_pipeline AS
WITH domain_warmup AS (
    -- Calculate domain-level warmup stats from sender_accounts
    SELECT
        sa.domain_id,
        MIN(sa.warmup_started_at) as domain_warmup_started_at,
        COUNT(*) as inbox_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected_count
    FROM sender_accounts sa
    WHERE sa.is_active = TRUE
    AND sa.domain_id IS NOT NULL
    GROUP BY sa.domain_id
)
SELECT
    d.id as domain_id,
    d.domain_name,
    d.workspace_id,
    c.id as client_id,
    d.infrastructure_type as provider,
    d.pool_status,
    d.pool_assigned_at,
    d.promoted_at,
    d.burned_at,
    d.burn_trigger,
    d.purchased_at,

    -- Warmup tracking
    dw.domain_warmup_started_at,
    COALESCE(dw.inbox_count, 0) as inbox_count,
    COALESCE(dw.connected_count, 0) as connected_count,
    CASE
        WHEN d.infrastructure_type = 'google' THEN 3
        ELSE 50
    END as max_inbox_count,

    -- Warmup age calculation
    CASE
        WHEN dw.domain_warmup_started_at IS NOT NULL THEN
            EXTRACT(DAY FROM NOW() - dw.domain_warmup_started_at)::INTEGER
        ELSE NULL
    END as warmup_age_days,

    -- Warmup period (Google = 7 days, Entra = 14 days)
    CASE
        WHEN d.infrastructure_type = 'google' THEN 7
        ELSE 14
    END as warmup_days_required,

    -- Warmup progress percentage
    CASE
        WHEN dw.domain_warmup_started_at IS NOT NULL THEN
            LEAST(100, ROUND(
                EXTRACT(EPOCH FROM NOW() - dw.domain_warmup_started_at) /
                EXTRACT(EPOCH FROM INTERVAL '14 days') * 100
            ))::INTEGER
        ELSE 0
    END as warmup_percent,

    -- Derived pipeline status
    CASE
        WHEN d.pool_status = 'burned' THEN 'burned'
        WHEN d.pool_status = 'live' THEN 'live'
        WHEN d.pool_status = 'reserve' THEN 'reserve'
        WHEN d.purchased_at IS NOT NULL
             AND dw.inbox_count > 0
             AND dw.domain_warmup_started_at > NOW() - INTERVAL '14 days' THEN 'incubating'
        WHEN d.pool_status = 'unassigned' THEN 'unassigned'
        ELSE 'unknown'
    END as pipeline_status,

    -- Days until ready for reserve (0 if already ready)
    CASE
        WHEN dw.domain_warmup_started_at IS NOT NULL THEN
            GREATEST(0, 14 - EXTRACT(DAY FROM NOW() - dw.domain_warmup_started_at))::INTEGER
        ELSE 14
    END as ready_in_days,

    -- Is warmup complete?
    CASE
        WHEN dw.domain_warmup_started_at IS NOT NULL
             AND dw.domain_warmup_started_at <= NOW() - INTERVAL '14 days' THEN TRUE
        ELSE FALSE
    END as warmup_complete,

    -- Daily capacity (connected inboxes only)
    CASE
        WHEN d.infrastructure_type = 'google' THEN COALESCE(dw.connected_count, 0) * 20
        ELSE COALESCE(dw.connected_count, 0) * 2
    END as daily_capacity

FROM domains d
LEFT JOIN domain_warmup dw ON dw.domain_id = d.id
LEFT JOIN workspaces w ON d.workspace_id = w.id
LEFT JOIN clients c ON c.workspace_id = w.id
WHERE d.is_active = TRUE
AND d.purchased_at IS NOT NULL;  -- Only purchased domains are in the pipeline

CREATE INDEX IF NOT EXISTS idx_domains_pipeline_lookup
    ON domains(workspace_id, pool_status, purchased_at)
    WHERE is_active = TRUE AND purchased_at IS NOT NULL;

-- =====================================================
-- 2. VIEW: v_domain_runway
-- =====================================================
-- Calculates reserve runway metrics per workspace/provider

CREATE OR REPLACE VIEW v_domain_runway AS
WITH domain_burns AS (
    -- Count domain burns in last 90 days
    SELECT
        d.workspace_id,
        d.infrastructure_type as provider,
        COUNT(*) as burn_count_90d
    FROM domain_rotation_events dre
    JOIN domains d ON dre.domain_id = d.id
    WHERE dre.event_type = 'quarantine'
    AND dre.created_at > NOW() - INTERVAL '90 days'
    GROUP BY d.workspace_id, d.infrastructure_type
),
domain_counts AS (
    -- Count domains by pool status and provider
    SELECT
        d.workspace_id,
        d.infrastructure_type as provider,
        COUNT(*) FILTER (WHERE d.pool_status = 'live') as live_count,
        COUNT(*) FILTER (WHERE d.pool_status = 'reserve') as reserve_count,
        COUNT(*) FILTER (WHERE d.pool_status = 'burned') as burned_count,
        COUNT(*) FILTER (WHERE d.pool_status = 'unassigned') as unassigned_count
    FROM domains d
    WHERE d.is_active = TRUE
    GROUP BY d.workspace_id, d.infrastructure_type
)
SELECT
    dc.workspace_id,
    c.id as client_id,
    dc.provider,
    dc.live_count,
    dc.reserve_count,
    dc.burned_count,
    dc.unassigned_count,

    -- Monthly burn rate (90-day average)
    COALESCE(db.burn_count_90d::NUMERIC / 3, 0) as monthly_burn_rate,

    -- Runway in months
    CASE
        WHEN COALESCE(db.burn_count_90d, 0) > 0 THEN
            dc.reserve_count::NUMERIC / (db.burn_count_90d::NUMERIC / 3)
        ELSE
            -- If no burns, estimate based on default rates
            CASE
                WHEN dc.provider = 'google' THEN dc.reserve_count * 10  -- Very low burn rate
                ELSE dc.reserve_count * 2  -- ~2 months per reserve domain
            END
    END as runway_months,

    -- Is runway healthy? (>= 2 months)
    CASE
        WHEN COALESCE(db.burn_count_90d, 0) > 0 THEN
            (dc.reserve_count::NUMERIC / (db.burn_count_90d::NUMERIC / 3)) >= 2
        ELSE
            dc.reserve_count >= 2
    END as runway_healthy,

    -- Domain kill cascade percentage (from economics model)
    CASE
        WHEN dc.provider = 'google' THEN 7   -- 7% of inbox kills cascade to domain
        ELSE 30                              -- 30% of inbox kills cascade to domain
    END as domain_kill_cascade_pct,

    -- 80/20 allocation metrics
    dc.live_count + dc.reserve_count as total_allocated,
    CASE
        WHEN dc.live_count + dc.reserve_count > 0 THEN
            ROUND(dc.live_count::NUMERIC / (dc.live_count + dc.reserve_count) * 100)
        ELSE 0
    END as live_percent,
    CASE
        WHEN dc.live_count + dc.reserve_count > 0 THEN
            ROUND(dc.reserve_count::NUMERIC / (dc.live_count + dc.reserve_count) * 100)
        ELSE 0
    END as reserve_percent,

    -- Gap to 80/20 target
    CEIL((dc.live_count + dc.reserve_count) * 0.8)::INTEGER - dc.live_count as live_gap_to_target

FROM domain_counts dc
LEFT JOIN domain_burns db ON db.workspace_id = dc.workspace_id AND db.provider = dc.provider
LEFT JOIN workspaces w ON dc.workspace_id = w.id
LEFT JOIN clients c ON c.workspace_id = w.id;

-- =====================================================
-- 3. FUNCTION: Get Pipeline Summary
-- =====================================================
-- Returns pipeline counts for a client

CREATE OR REPLACE FUNCTION get_pipeline_summary(p_client_id UUID)
RETURNS TABLE (
    incubating_count INTEGER,
    reserve_count INTEGER,
    live_count INTEGER,
    burned_count INTEGER,
    incubating_entra INTEGER,
    incubating_google INTEGER,
    reserve_entra INTEGER,
    reserve_google INTEGER,
    live_entra INTEGER,
    live_google INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'incubating')::INTEGER as incubating_count,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'reserve')::INTEGER as reserve_count,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'live')::INTEGER as live_count,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'burned')::INTEGER as burned_count,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'incubating' AND dp.provider = 'microsoft')::INTEGER as incubating_entra,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'incubating' AND dp.provider = 'google')::INTEGER as incubating_google,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'reserve' AND dp.provider = 'microsoft')::INTEGER as reserve_entra,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'reserve' AND dp.provider = 'google')::INTEGER as reserve_google,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'live' AND dp.provider = 'microsoft')::INTEGER as live_entra,
        COUNT(*) FILTER (WHERE dp.pipeline_status = 'live' AND dp.provider = 'google')::INTEGER as live_google
    FROM v_domain_pipeline dp
    WHERE dp.client_id = p_client_id;
END;
$$ LANGUAGE plpgsql STABLE;

COMMIT;

SELECT 'Migration 082_domain_pipeline_views complete' AS status;
