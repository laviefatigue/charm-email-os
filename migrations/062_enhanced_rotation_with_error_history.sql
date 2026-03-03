-- Migration 062: Enhanced Rotation Recommendation with Error History
-- Created: 2026-03-03
-- Purpose: Factor error history into rotation recommendations
--
-- Key Changes:
-- 1. Spam complaints or hard blocks = rotate_now (don't reconnect compromised inboxes)
-- 2. Multiple inboxes with issues = consider_rotate (domain is degrading)
-- 3. Disconnected with clean history = monitor (worth reconnecting)
-- 4. Adds has_compromised_inboxes flag for UI display
--
-- Philosophy: "Why reconnect if we're going to rotate anyway?"

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

    -- Fulfillment tracking
    d.expected_inbox_count,
    d.max_inboxes_seen,
    d.fulfillment_status,

    -- Capacity remaining percentage
    CASE
        WHEN COALESCE(d.expected_inbox_count, 0) = 0 THEN NULL
        ELSE ROUND(
            COALESCE(inbox_stats.connected_count, 0)::NUMERIC /
            d.expected_inbox_count * 100,
            1
        )
    END AS capacity_remaining_pct,

    -- Error history indicators (from domains table)
    d.burn_breakdown,
    COALESCE(d.inboxes_with_complaints, 0) AS inboxes_with_complaints,
    COALESCE(d.inboxes_with_blocks, 0) AS inboxes_with_blocks,

    -- NEW: Has compromised inboxes (spam complaints or hard blocks)
    (
        COALESCE(d.inboxes_with_complaints, 0) > 0
        OR COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) > 0
        OR COALESCE((d.burn_breakdown->>'hard_blocked_24h')::int, 0) > 0
    ) AS has_compromised_inboxes,

    -- ENHANCED: Rotation recommendation with error history
    CASE
        -- No inboxes yet = not applicable
        WHEN COALESCE(inbox_stats.total_count, 0) = 0 THEN 'not_applicable'

        -- PRIORITY 1: Compromised domain (spam complaints) = rotate_now
        -- Don't waste time reconnecting, the domain is burned
        WHEN COALESCE(d.inboxes_with_complaints, 0) > 0 THEN 'rotate_now'
        WHEN COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) > 0 THEN 'rotate_now'

        -- PRIORITY 2: All live inboxes disconnected = rotate_now
        WHEN COALESCE(inbox_stats.connected_count, 0) = 0
            AND COALESCE(inbox_stats.live_count, 0) > 0
            THEN 'rotate_now'

        -- PRIORITY 3: Multiple inboxes with hard blocks = consider_rotate
        -- Pattern suggests domain-level issue
        WHEN COALESCE(d.inboxes_with_blocks, 0) >= 2 THEN 'consider_rotate'
        WHEN COALESCE((d.burn_breakdown->>'hard_blocked_24h')::int, 0) >= 2 THEN 'consider_rotate'

        -- PRIORITY 4: Capacity thresholds (existing logic)
        -- Entra: connected < 40 (80% of 50) = consider rotation
        WHEN inbox_stats.detected_provider = 'entra'
            AND COALESCE(inbox_stats.connected_count, 0) < 40
            THEN 'consider_rotate'

        -- Google: connected < 2 (67% of 3) = consider rotation
        WHEN inbox_stats.detected_provider = 'google'
            AND COALESCE(inbox_stats.connected_count, 0) < 2
            THEN 'consider_rotate'

        -- PRIORITY 5: Single hard block or approaching threshold = monitor
        WHEN COALESCE(d.inboxes_with_blocks, 0) = 1 THEN 'monitor'
        WHEN COALESCE((d.burn_breakdown->>'hard_blocked_24h')::int, 0) = 1 THEN 'monitor'

        -- Entra: connected < 45 (90% of 50) = monitor
        WHEN inbox_stats.detected_provider = 'entra'
            AND COALESCE(inbox_stats.connected_count, 0) < 45
            THEN 'monitor'

        -- Google: connected = 2 (67% of 3) = monitor
        WHEN inbox_stats.detected_provider = 'google'
            AND COALESCE(inbox_stats.connected_count, 0) = 2
            THEN 'monitor'

        -- PRIORITY 6: Has disconnected inboxes (but clean history) = monitor
        -- These are worth reconnecting
        WHEN COALESCE(inbox_stats.disconnected_count, 0) > 0 THEN 'monitor'

        -- Otherwise healthy
        ELSE 'healthy'
    END AS rotation_recommendation,

    -- NEW: Recommended action (more granular than rotation_recommendation)
    CASE
        WHEN COALESCE(inbox_stats.total_count, 0) = 0 THEN 'none'

        -- Compromised = rotate, don't reconnect
        WHEN COALESCE(d.inboxes_with_complaints, 0) > 0 THEN 'rotate'
        WHEN COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) > 0 THEN 'rotate'

        -- All disconnected = rotate
        WHEN COALESCE(inbox_stats.connected_count, 0) = 0
            AND COALESCE(inbox_stats.live_count, 0) > 0
            THEN 'rotate'

        -- Pattern of issues = rotate
        WHEN COALESCE(d.inboxes_with_blocks, 0) >= 2 THEN 'rotate'

        -- Below capacity thresholds = rotate
        WHEN inbox_stats.detected_provider = 'entra'
            AND COALESCE(inbox_stats.connected_count, 0) < 40
            THEN 'rotate'
        WHEN inbox_stats.detected_provider = 'google'
            AND COALESCE(inbox_stats.connected_count, 0) < 2
            THEN 'rotate'

        -- Disconnected with clean history = reconnect
        WHEN COALESCE(inbox_stats.disconnected_count, 0) > 0
            AND COALESCE(d.inboxes_with_complaints, 0) = 0
            AND COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) = 0
            THEN 'reconnect'

        -- Monitoring but no action needed yet
        WHEN COALESCE(d.inboxes_with_blocks, 0) = 1 THEN 'watch'

        ELSE 'none'
    END AS recommended_action,

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
'Infrastructure waterfall view with error-aware rotation recommendations.

Rotation priority:
1. Spam complaints = rotate_now (domain is burned, don''t reconnect)
2. All disconnected = rotate_now (no capacity)
3. Multiple hard blocks = consider_rotate (pattern of issues)
4. Below capacity threshold = consider_rotate
5. Single hard block = monitor (watch for escalation)
6. Disconnected with clean history = monitor (reconnect candidate)
7. Above thresholds, no issues = healthy

recommended_action values:
- rotate: Domain should be replaced
- reconnect: Disconnected inboxes are worth saving
- watch: Monitor but no action yet
- none: Healthy, no action needed';

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Show rotation recommendations with error context
SELECT
    domain_name,
    assigned_provider,
    connected_inbox_count,
    disconnected_inbox_count,
    inboxes_with_complaints,
    inboxes_with_blocks,
    has_compromised_inboxes,
    rotation_recommendation,
    recommended_action
FROM v_infrastructure_waterfall
WHERE synced_inbox_count > 0
ORDER BY
    CASE rotation_recommendation
        WHEN 'rotate_now' THEN 1
        WHEN 'consider_rotate' THEN 2
        WHEN 'monitor' THEN 3
        ELSE 4
    END,
    inboxes_with_complaints DESC
LIMIT 20;

-- Count by action needed
SELECT
    recommended_action,
    COUNT(*) as domain_count
FROM v_infrastructure_waterfall
WHERE synced_inbox_count > 0
GROUP BY recommended_action
ORDER BY domain_count DESC;

SELECT 'Migration 062_enhanced_rotation_with_error_history complete' AS status;
