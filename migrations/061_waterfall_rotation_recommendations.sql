-- Migration 061: Waterfall View with Rotation Recommendations
-- Created: 2026-03-03
-- Purpose: Add fulfillment tracking and rotation recommendations to infrastructure waterfall
--
-- Adds to v_infrastructure_waterfall:
-- - expected_inbox_count (from domains table)
-- - max_inboxes_seen (from domains table)
-- - fulfillment_status (from domains table)
-- - capacity_remaining_pct (connected / expected * 100)
-- - rotation_recommendation (healthy, monitor, consider_rotate, rotate_now)
--
-- Rotation Logic:
-- - Entra (50 expected): rotate when connected < 40 (80%)
-- - Google (3 expected): rotate when connected < 2 (67%)
-- - All disconnected: rotate_now regardless of count

-- =====================================================
-- DROP AND RECREATE VIEW
-- =====================================================

DROP VIEW IF EXISTS v_infrastructure_waterfall;

CREATE VIEW v_infrastructure_waterfall AS
SELECT
    d.id AS domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,
    d.created_at AS generated_at,
    d.legitimacy_score,
    COALESCE(d.domain_source, 'legacy') AS domain_source,

    -- Pricing columns
    d.price_checked_at,
    d.cached_price,
    d.selected_provider,
    d.porkbun_price,
    d.porkbun_available,
    d.dynadot_price,
    d.dynadot_available,
    CASE
        WHEN d.price_checked_at IS NULL THEN 'not_checked'
        WHEN d.price_checked_at < NOW() - INTERVAL '24 hours' THEN 'stale'
        WHEN d.porkbun_available = false AND d.dynadot_available = false THEN 'unavailable'
        ELSE 'valid'
    END AS price_status,

    -- Purchase tracking
    d.purchased_at,
    d.job_id AS domain_purchase_job_id,
    d.purchase_job_id,

    -- DNS columns
    d.nameservers_updated_at,
    d.current_nameservers,
    CASE
        WHEN d.nameservers_updated_at IS NULL THEN 'not_set'
        WHEN d.nameservers_updated_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
        ELSE 'propagated'
    END AS dns_migration_status,
    d.nameserver_status,
    d.nameserver_verified_at,
    COALESCE(d.spf_configured, false) AS spf_configured,
    COALESCE(d.dkim_configured, false) AS dkim_configured,
    COALESCE(d.dmarc_configured, false) AS dmarc_configured,
    COALESCE(d.mx_configured, false) AS mx_configured,
    COALESCE(d.dns_records_configured, false) AS dns_records_configured,

    -- Provider assignment
    COALESCE(d.infrastructure_type, inbox_stats.detected_provider::varchar) AS assigned_provider,
    inbox_stats.detected_provider,

    -- HyperTide order tracking
    ipj.id AS hypertide_order_job_id,
    ipj.status AS hypertide_order_status,
    ipj.current_step AS hypertide_current_step,
    ipj.created_at AS hypertide_ordered_at,

    -- Inbox counts
    COALESCE(inbox_stats.live_count, 0) AS live_inbox_count,
    COALESCE(inbox_stats.dead_count, 0) AS dead_inbox_count,
    COALESCE(inbox_stats.total_count, 0) AS synced_inbox_count,
    inbox_stats.last_synced_at AS last_inbox_synced_at,
    COALESCE(inbox_stats.connected_count, 0) AS connected_inbox_count,
    COALESCE(inbox_stats.disconnected_count, 0) AS disconnected_inbox_count,

    -- NEW: Fulfillment tracking columns
    d.expected_inbox_count,
    d.max_inboxes_seen,
    d.fulfillment_status,

    -- NEW: Capacity remaining percentage (connected / expected * 100)
    CASE
        WHEN COALESCE(d.expected_inbox_count, 0) = 0 THEN NULL
        ELSE ROUND(
            COALESCE(inbox_stats.connected_count, 0)::NUMERIC /
            d.expected_inbox_count * 100,
            1
        )
    END AS capacity_remaining_pct,

    -- NEW: Rotation recommendation based on capacity thresholds
    CASE
        -- No inboxes yet = not applicable
        WHEN COALESCE(inbox_stats.total_count, 0) = 0 THEN 'not_applicable'

        -- All live inboxes are disconnected = rotate immediately
        WHEN COALESCE(inbox_stats.connected_count, 0) = 0
            AND COALESCE(inbox_stats.live_count, 0) > 0
            THEN 'rotate_now'

        -- Entra: connected < 40 (80% of 50) = consider rotation
        WHEN inbox_stats.detected_provider = 'entra'
            AND COALESCE(inbox_stats.connected_count, 0) < 40
            THEN 'consider_rotate'

        -- Google: connected < 2 (67% of 3) = consider rotation
        WHEN inbox_stats.detected_provider = 'google'
            AND COALESCE(inbox_stats.connected_count, 0) < 2
            THEN 'consider_rotate'

        -- Entra: connected < 45 (90% of 50) = monitor
        WHEN inbox_stats.detected_provider = 'entra'
            AND COALESCE(inbox_stats.connected_count, 0) < 45
            THEN 'monitor'

        -- Google: connected = 2 (67% of 3) = monitor
        WHEN inbox_stats.detected_provider = 'google'
            AND COALESCE(inbox_stats.connected_count, 0) = 2
            THEN 'monitor'

        -- Otherwise healthy
        ELSE 'healthy'
    END AS rotation_recommendation,

    -- Current stage (unchanged)
    CASE
        WHEN COALESCE(inbox_stats.total_count, 0) > 0 THEN 9
        WHEN ipj.status = 'completed' THEN 8
        WHEN ipj.id IS NOT NULL THEN 7
        WHEN d.infrastructure_type IS NOT NULL THEN 6
        WHEN d.nameserver_status = 'verified' THEN 5
        WHEN d.nameservers_updated_at IS NOT NULL THEN 4
        WHEN d.purchased_at IS NOT NULL THEN 3
        WHEN d.price_checked_at IS NOT NULL THEN 2
        ELSE 1
    END AS current_stage,

    d.approval_status = 'owned' AS owned_by_client,
    COALESCE(inbox_stats.total_count, 0) > 0 AS deployed_to_production

FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE sa.inbox_state <> 'dead' OR sa.inbox_state IS NULL) AS live_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') AS dead_count,
        COUNT(*) AS total_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS connected_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')) AS disconnected_count,
        MAX(sa.created_at) AS last_synced_at,
        CASE
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
            ELSE NULL
        END AS detected_provider
    FROM sender_accounts sa
    WHERE sa.domain_id = d.id
) inbox_stats ON true
WHERE d.is_active = true;

-- =====================================================
-- ADD COMMENTS
-- =====================================================

COMMENT ON VIEW v_infrastructure_waterfall IS
    'Infrastructure waterfall view with domain fulfillment tracking and rotation recommendations';

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Show rotation recommendations by provider
SELECT
    assigned_provider,
    rotation_recommendation,
    COUNT(*) as domain_count,
    AVG(connected_inbox_count) as avg_connected,
    AVG(expected_inbox_count) as avg_expected,
    AVG(capacity_remaining_pct) as avg_capacity_pct
FROM v_infrastructure_waterfall
WHERE synced_inbox_count > 0
GROUP BY assigned_provider, rotation_recommendation
ORDER BY assigned_provider, rotation_recommendation;

-- Show domains needing attention
SELECT
    domain_name,
    assigned_provider,
    connected_inbox_count,
    expected_inbox_count,
    capacity_remaining_pct,
    rotation_recommendation,
    fulfillment_status
FROM v_infrastructure_waterfall
WHERE rotation_recommendation IN ('consider_rotate', 'rotate_now', 'monitor')
ORDER BY rotation_recommendation DESC, capacity_remaining_pct ASC
LIMIT 20;

SELECT 'Migration 061_waterfall_rotation_recommendations complete' AS status;
