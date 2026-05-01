-- Migration 084: Dynamic Domain Velocity & Swap Eligibility
-- Created: 2026-03-12
-- Purpose: Replace static capacity thresholds with dynamic burn-rate-aware rotation
--
-- Key Changes:
-- 1. burn_velocity_30d: kills per 30-day period per domain (from campaign_burn_events)
-- 2. projected_days_to_critical: predicted days until domain hits 50% capacity
-- 3. swap_eligible: whether HyperTide can provision a replacement (Entra=yes, Google=no yet)
-- 4. Waterfall view uses velocity projections instead of static connected < 40 thresholds
--
-- Dynamic Rotation Logic:
-- - Spam complaints → rotate_now (unchanged)
-- - All disconnected → rotate_now (unchanged)
-- - Connected < 50% of expected → rotate_now (NEW: non-viable)
-- - Projected critical ≤ 14 days → rotate_now (NEW: imminent failure)
-- - Projected critical ≤ 42 days → consider_rotate (NEW: degrading)
-- - 2+ hard blocks → consider_rotate (unchanged)
-- - Projected critical ≤ 90 days → monitor (NEW: slow degradation)
-- - 1 hard block → monitor (unchanged)
-- - Disconnected inboxes → monitor (unchanged)

-- =====================================================
-- 1. ADD NEW COLUMNS TO DOMAINS TABLE
-- =====================================================

ALTER TABLE domains ADD COLUMN IF NOT EXISTS burn_velocity_30d NUMERIC(6,2) DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS projected_days_to_critical INTEGER;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS velocity_calculated_at TIMESTAMPTZ;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS swap_eligible BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN domains.burn_velocity_30d IS 'Inbox kills in last 30 days for this domain';
COMMENT ON COLUMN domains.projected_days_to_critical IS 'Predicted days until connected inboxes drop below 50% of expected (NULL = no burns)';
COMMENT ON COLUMN domains.velocity_calculated_at IS 'When velocity was last recalculated';
COMMENT ON COLUMN domains.swap_eligible IS 'Whether HyperTide can provision replacement infrastructure (Entra=true, Google=false)';

-- =====================================================
-- 2. BACKFILL SWAP ELIGIBILITY FROM PROVIDER
-- =====================================================

-- Entra/Microsoft domains are swap-eligible (HyperTide provisions replacements)
UPDATE domains d SET swap_eligible = TRUE
WHERE d.id IN (
    SELECT DISTINCT sa.domain_id
    FROM sender_accounts sa
    WHERE sa.esp = 'microsoft' AND sa.domain_id IS NOT NULL
);
-- Google domains stay FALSE (default) — no automated swap path yet

-- =====================================================
-- 3. VELOCITY CALCULATION FUNCTION (per domain)
-- =====================================================

CREATE OR REPLACE FUNCTION recalculate_domain_velocity(p_domain_id UUID)
RETURNS VOID AS $$
DECLARE
    v_burns_30d INTEGER;
    v_connected INTEGER;
    v_expected INTEGER;
    v_velocity NUMERIC(6,2);
    v_days_to_critical INTEGER;
    v_critical_threshold NUMERIC;
BEGIN
    -- Count burns in last 30 days from campaign_burn_events
    SELECT COUNT(*) INTO v_burns_30d
    FROM campaign_burn_events
    WHERE domain_id = p_domain_id
      AND burned_at >= NOW() - INTERVAL '30 days';

    v_velocity := v_burns_30d;  -- Already per-30-day window

    -- Get current connected count and provider-based expected count
    SELECT
        COUNT(*) FILTER (WHERE inbox_state = 'live' AND status = 'Connected'),
        CASE
            WHEN MAX(CASE WHEN esp = 'microsoft' THEN 1 ELSE 0 END) = 1 THEN 50
            ELSE 3
        END
    INTO v_connected, v_expected
    FROM sender_accounts
    WHERE domain_id = p_domain_id;

    -- Use domains.expected_inbox_count if set (overrides provider default)
    SELECT COALESCE(expected_inbox_count, v_expected)
    INTO v_expected
    FROM domains WHERE id = p_domain_id;

    -- Calculate projected days to critical (50% of expected)
    v_critical_threshold := v_expected * 0.5;

    IF v_velocity > 0 AND v_connected > v_critical_threshold THEN
        -- Formula: (inboxes_above_critical / burns_per_30d) * 30 days
        v_days_to_critical := ROUND(
            ((v_connected - v_critical_threshold) / v_velocity) * 30
        );
    ELSE
        v_days_to_critical := NULL;  -- No burns = infinite runway
    END IF;

    UPDATE domains SET
        burn_velocity_30d = v_velocity,
        projected_days_to_critical = v_days_to_critical,
        velocity_calculated_at = NOW()
    WHERE id = p_domain_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION recalculate_domain_velocity(UUID) IS
'Recalculate burn velocity and projected days-to-critical for a single domain.
Called after each inbox kill and during daily snapshot.
Uses 30-day window from campaign_burn_events.
Critical threshold = 50% of expected inbox count.';

-- =====================================================
-- 4. BULK VELOCITY FUNCTION (for daily snapshot)
-- =====================================================

CREATE OR REPLACE FUNCTION recalculate_all_domain_velocities()
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER := 0;
    v_domain_id UUID;
BEGIN
    FOR v_domain_id IN
        SELECT DISTINCT d.id
        FROM domains d
        JOIN sender_accounts sa ON sa.domain_id = d.id
        WHERE d.is_active = TRUE
    LOOP
        PERFORM recalculate_domain_velocity(v_domain_id);
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION recalculate_all_domain_velocities() IS
'Bulk recalculate velocity for all active domains with inboxes.
Called once per day during daily snapshot.
Also picks up domains where burns have aged out of the 30-day window (velocity decreases).';

-- =====================================================
-- 5. BACKFILL VELOCITY FROM EXISTING DATA
-- =====================================================

SELECT recalculate_all_domain_velocities();

-- =====================================================
-- 6. UPDATED WATERFALL VIEW WITH DYNAMIC ROTATION
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

    -- Has compromised inboxes (spam complaints or hard blocks)
    (
        COALESCE(d.inboxes_with_complaints, 0) > 0
        OR COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) > 0
        OR COALESCE((d.burn_breakdown->>'hard_blocked_24h')::int, 0) > 0
    ) AS has_compromised_inboxes,

    -- NEW: Velocity and swap columns
    COALESCE(d.burn_velocity_30d, 0) AS burn_velocity_30d,
    d.projected_days_to_critical,
    d.swap_eligible,

    -- DYNAMIC: Rotation recommendation with velocity projections
    CASE
        -- No inboxes yet = not applicable
        WHEN COALESCE(inbox_stats.total_count, 0) = 0 THEN 'not_applicable'

        -- P1: Spam complaints = rotate_now (domain reputation burned)
        WHEN COALESCE(d.inboxes_with_complaints, 0) > 0 THEN 'rotate_now'
        WHEN COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) > 0 THEN 'rotate_now'

        -- P2: All live inboxes disconnected = rotate_now (zero capacity)
        WHEN COALESCE(inbox_stats.connected_count, 0) = 0
            AND COALESCE(inbox_stats.live_count, 0) > 0
            THEN 'rotate_now'

        -- P3: Already below 50% capacity = rotate_now (non-viable)
        WHEN COALESCE(
                d.expected_inbox_count,
                CASE WHEN inbox_stats.detected_provider = 'google' THEN 3 ELSE 50 END
             ) > 0
            AND COALESCE(inbox_stats.connected_count, 0)::NUMERIC /
                COALESCE(
                    d.expected_inbox_count,
                    CASE WHEN inbox_stats.detected_provider = 'google' THEN 3 ELSE 50 END
                ) < 0.5
            THEN 'rotate_now'

        -- P4: Projected to hit critical within 14 days = rotate_now
        WHEN d.projected_days_to_critical IS NOT NULL
            AND d.projected_days_to_critical <= 14
            THEN 'rotate_now'

        -- P5: Projected to hit critical within 42 days (6 weeks) = consider_rotate
        WHEN d.projected_days_to_critical IS NOT NULL
            AND d.projected_days_to_critical <= 42
            THEN 'consider_rotate'

        -- P6: Multiple hard blocks = consider_rotate (pattern of issues)
        WHEN COALESCE(d.inboxes_with_blocks, 0) >= 2 THEN 'consider_rotate'
        WHEN COALESCE((d.burn_breakdown->>'hard_blocked_24h')::int, 0) >= 2 THEN 'consider_rotate'

        -- P7: Projected to hit critical within 90 days = monitor
        WHEN d.projected_days_to_critical IS NOT NULL
            AND d.projected_days_to_critical <= 90
            THEN 'monitor'

        -- P8: Single hard block = monitor
        WHEN COALESCE(d.inboxes_with_blocks, 0) = 1 THEN 'monitor'
        WHEN COALESCE((d.burn_breakdown->>'hard_blocked_24h')::int, 0) = 1 THEN 'monitor'

        -- P9: Has disconnected inboxes (clean history) = monitor
        WHEN COALESCE(inbox_stats.disconnected_count, 0) > 0 THEN 'monitor'

        ELSE 'healthy'
    END AS rotation_recommendation,

    -- Recommended action (velocity-aware)
    CASE
        WHEN COALESCE(inbox_stats.total_count, 0) = 0 THEN 'none'

        -- Compromised = rotate, don't reconnect
        WHEN COALESCE(d.inboxes_with_complaints, 0) > 0 THEN 'rotate'
        WHEN COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) > 0 THEN 'rotate'

        -- All disconnected = rotate
        WHEN COALESCE(inbox_stats.connected_count, 0) = 0
            AND COALESCE(inbox_stats.live_count, 0) > 0
            THEN 'rotate'

        -- Below 50% capacity = rotate
        WHEN COALESCE(
                d.expected_inbox_count,
                CASE WHEN inbox_stats.detected_provider = 'google' THEN 3 ELSE 50 END
             ) > 0
            AND COALESCE(inbox_stats.connected_count, 0)::NUMERIC /
                COALESCE(
                    d.expected_inbox_count,
                    CASE WHEN inbox_stats.detected_provider = 'google' THEN 3 ELSE 50 END
                ) < 0.5
            THEN 'rotate'

        -- Projected critical within 14 days = rotate
        WHEN d.projected_days_to_critical IS NOT NULL
            AND d.projected_days_to_critical <= 14
            THEN 'rotate'

        -- Projected critical within 42 days = rotate (plan replacement)
        WHEN d.projected_days_to_critical IS NOT NULL
            AND d.projected_days_to_critical <= 42
            AND d.swap_eligible = TRUE
            THEN 'rotate'

        -- Pattern of issues = rotate
        WHEN COALESCE(d.inboxes_with_blocks, 0) >= 2 THEN 'rotate'

        -- Disconnected with clean history = reconnect
        WHEN COALESCE(inbox_stats.disconnected_count, 0) > 0
            AND COALESCE(d.inboxes_with_complaints, 0) = 0
            AND COALESCE((d.burn_breakdown->>'spam_complaint')::int, 0) = 0
            THEN 'reconnect'

        -- Monitoring but no action needed yet
        WHEN COALESCE(d.inboxes_with_blocks, 0) = 1 THEN 'watch'

        -- Slow degradation = watch
        WHEN d.projected_days_to_critical IS NOT NULL
            AND d.projected_days_to_critical <= 90
            THEN 'watch'

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
'Infrastructure waterfall view with velocity-aware dynamic rotation recommendations.

Rotation priority (dynamic):
1. Spam complaints = rotate_now (domain reputation burned)
2. All disconnected = rotate_now (zero capacity)
3. Connected < 50% expected = rotate_now (non-viable)
4. Projected critical ≤ 14 days = rotate_now (imminent failure)
5. Projected critical ≤ 42 days = consider_rotate (degrading)
6. 2+ hard blocks = consider_rotate (pattern of issues)
7. Projected critical ≤ 90 days = monitor (slow degradation)
8. 1 hard block = monitor (watch for escalation)
9. Disconnected (clean history) = monitor (reconnect candidate)
10. No issues = healthy

Key formula:
  critical_threshold = expected_inboxes × 0.5
  projected_days = ((connected - critical_threshold) / burns_30d) × 30

swap_eligible: TRUE for Entra (HyperTide), FALSE for Google (no swap path yet)';

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Show velocity data
SELECT
    domain_name,
    COALESCE(d.infrastructure_type, 'unknown') AS provider,
    burn_velocity_30d,
    projected_days_to_critical,
    swap_eligible
FROM domains d
WHERE burn_velocity_30d > 0
ORDER BY burn_velocity_30d DESC
LIMIT 20;

-- Show rotation recommendations with velocity context
SELECT
    domain_name,
    assigned_provider,
    connected_inbox_count,
    burn_velocity_30d,
    projected_days_to_critical,
    swap_eligible,
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
    projected_days_to_critical ASC NULLS LAST
LIMIT 20;

-- Compare old vs new rotation distribution
SELECT
    rotation_recommendation,
    COUNT(*) as domain_count,
    COUNT(*) FILTER (WHERE swap_eligible) as swap_eligible_count
FROM v_infrastructure_waterfall
WHERE synced_inbox_count > 0
GROUP BY rotation_recommendation
ORDER BY
    CASE rotation_recommendation
        WHEN 'rotate_now' THEN 1
        WHEN 'consider_rotate' THEN 2
        WHEN 'monitor' THEN 3
        WHEN 'healthy' THEN 4
        ELSE 5
    END;

-- Swap capacity summary
SELECT
    CASE WHEN swap_eligible THEN 'Swap Eligible (Entra)' ELSE 'No Swap Path (Google)' END as swap_status,
    COUNT(*) FILTER (WHERE rotation_recommendation = 'rotate_now') as rotate_now,
    COUNT(*) FILTER (WHERE rotation_recommendation = 'consider_rotate') as consider_rotate,
    COUNT(*) FILTER (WHERE rotation_recommendation = 'monitor') as monitor,
    COUNT(*) FILTER (WHERE rotation_recommendation = 'healthy') as healthy
FROM v_infrastructure_waterfall
WHERE synced_inbox_count > 0
GROUP BY swap_eligible;

SELECT 'Migration 084_domain_velocity_and_swap complete' AS status;
