-- Migration 075: Fix A-Set/B-Set distribution views to use actual graduated count
-- Created: 2026-03-05
-- Purpose: Fix percentage calculation to use COUNT of actual graduated inboxes
--          instead of expected_inbox_count (which is always 50 for Entra)
--
-- Bug fixed:
-- - Old: target_a_set = FLOOR(expected_inbox_count * 0.80) = 40 always
-- - New: target_a_set = FLOOR(graduated_count * 0.80) = dynamic

BEGIN;

-- Drop existing views (must drop in order due to dependencies)
DROP VIEW IF EXISTS v_inbox_set_assignment;
DROP VIEW IF EXISTS v_inbox_set_distribution;

-- =============================================================================
-- VIEW: INBOX SET DISTRIBUTION (per domain)
-- =============================================================================
-- Shows A-Set/B-Set distribution per domain with targets based on ACTUAL graduated count

CREATE VIEW v_inbox_set_distribution AS
WITH domain_stats AS (
    SELECT
        d.id as domain_id,
        d.domain_name,
        d.workspace_id,
        w.workspace_name,
        COALESCE(d.infrastructure_type,
            CASE
                WHEN EXISTS (SELECT 1 FROM sender_accounts sa2 WHERE sa2.domain_id = d.id AND sa2.esp = 'microsoft') THEN 'entra'
                WHEN EXISTS (SELECT 1 FROM sender_accounts sa2 WHERE sa2.domain_id = d.id AND sa2.esp = 'gmail') THEN 'google'
                ELSE 'unknown'
            END
        ) as provider,
        COALESCE(d.expected_inbox_count,
            CASE WHEN d.infrastructure_type = 'google' THEN 3 ELSE 50 END
        ) as expected_inbox_count,

        -- Total live inboxes (regardless of connection status)
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,

        -- Lifecycle status
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') as incubating,

        -- ACTUAL graduated count (the KEY fix)
        -- Only count connected + graduated + not quarantined
        COUNT(*) FILTER (
            WHERE sa.inbox_state = 'live'
            AND sa.status = 'Connected'
            AND COALESCE(sa.inventory_pool_status, 'reserve') != 'quarantined'
            AND (
                sa.inventory_lifecycle_status = 'active'
                OR (sa.warmup_started_at IS NOT NULL AND sa.warmup_started_at <= NOW() - INTERVAL '14 days')
            )
        ) as graduated_count,

        -- Current pool assignment
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed' AND sa.inbox_state = 'live') as current_a_set,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve' AND sa.inbox_state = 'live') as current_b_set,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'quarantined' AND sa.inbox_state = 'live') as quarantined

    FROM domains d
    JOIN workspaces w ON d.workspace_id = w.id
    LEFT JOIN sender_accounts sa ON sa.domain_id = d.id AND sa.is_active = TRUE
    WHERE d.is_active = TRUE
    GROUP BY d.id, d.domain_name, d.workspace_id, w.workspace_name, d.infrastructure_type, d.expected_inbox_count
)
SELECT
    domain_id,
    domain_name,
    workspace_id,
    workspace_name,
    provider,
    expected_inbox_count,

    -- Counts
    live_inboxes,
    connected,
    incubating,
    graduated_count,
    current_a_set,
    current_b_set,
    quarantined,

    -- Target state based on ACTUAL graduated count (not expected)
    FLOOR(graduated_count * 0.80)::INTEGER as target_a_set,
    graduated_count - FLOOR(graduated_count * 0.80)::INTEGER as target_b_set,

    -- Actions needed
    CASE
        WHEN graduated_count <= FLOOR(graduated_count * 0.80) THEN 0
        ELSE graduated_count - FLOOR(graduated_count * 0.80)::INTEGER - current_b_set
    END as need_to_move_to_b_set,

    -- Status
    CASE
        WHEN quarantined > 0 THEN 'quarantined'
        WHEN live_inboxes = 0 THEN 'no_inboxes'
        WHEN graduated_count = 0 THEN 'all_incubating'
        WHEN current_b_set > 0 THEN 'has_reserve'
        WHEN graduated_count > FLOOR(graduated_count * 0.80) AND current_b_set = 0 THEN 'needs_bset_tagging'
        ELSE 'at_capacity'
    END as set_status

FROM domain_stats
WHERE live_inboxes > 0 OR incubating > 0;

COMMENT ON VIEW v_inbox_set_distribution IS
'Shows A-Set/B-Set distribution per domain.
FIXED: Targets calculated from ACTUAL graduated_count, not expected_inbox_count.
Example: 15 graduated inboxes -> target_a_set = 12, target_b_set = 3 (80/20 split)';

-- =============================================================================
-- VIEW: INBOX-LEVEL SET ASSIGNMENT
-- =============================================================================
-- Shows exactly which inboxes should be in A-Set vs B-Set

CREATE VIEW v_inbox_set_assignment AS
WITH domain_graduated AS (
    -- First, get graduated count per domain for percentage calculation
    SELECT
        domain_id,
        COUNT(*) as graduated_count
    FROM sender_accounts
    WHERE is_active = TRUE
    AND inbox_state = 'live'
    AND status = 'Connected'
    AND COALESCE(inventory_pool_status, 'reserve') != 'quarantined'
    AND (
        inventory_lifecycle_status = 'active'
        OR (warmup_started_at IS NOT NULL AND warmup_started_at <= NOW() - INTERVAL '14 days')
    )
    GROUP BY domain_id
),
ranked_inboxes AS (
    SELECT
        sa.id as inbox_id,
        sa.email_address,
        sa.domain_id,
        d.domain_name,
        COALESCE(d.infrastructure_type,
            CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
        ) as provider,
        dg.graduated_count,
        sa.inbox_state,
        sa.status,
        sa.inventory_lifecycle_status,
        sa.inventory_pool_status as current_pool,
        sa.warmup_started_at,
        sa.health_score,
        -- Rank inboxes within domain by priority for A-Set assignment
        ROW_NUMBER() OVER (
            PARTITION BY sa.domain_id
            ORDER BY
                CASE WHEN sa.status = 'Connected' THEN 0 ELSE 1 END,
                CASE WHEN sa.inventory_pool_status = 'deployed' THEN 0 ELSE 1 END,
                sa.warmup_started_at ASC NULLS LAST,
                sa.health_score DESC NULLS LAST
        ) as priority_rank
    FROM sender_accounts sa
    JOIN domains d ON sa.domain_id = d.id
    JOIN domain_graduated dg ON dg.domain_id = sa.domain_id
    WHERE sa.is_active = TRUE
    AND sa.inbox_state = 'live'
    AND sa.status = 'Connected'
    AND COALESCE(sa.inventory_pool_status, 'reserve') != 'quarantined'
    AND (
        sa.inventory_lifecycle_status = 'active'
        OR (sa.warmup_started_at IS NOT NULL AND sa.warmup_started_at <= NOW() - INTERVAL '14 days')
    )
    AND d.is_active = TRUE
)
SELECT
    inbox_id,
    email_address,
    domain_id,
    domain_name,
    provider,
    graduated_count,
    inbox_state,
    status,
    inventory_lifecycle_status,
    current_pool,
    warmup_started_at,
    health_score,
    priority_rank,

    -- Target set based on rank within ACTUAL graduated count (80/20 split)
    CASE
        WHEN priority_rank <= FLOOR(graduated_count * 0.80) THEN 'live'
        ELSE 'bset'
    END as target_set,

    -- Action needed
    CASE
        WHEN priority_rank <= FLOOR(graduated_count * 0.80) AND current_pool != 'deployed' THEN 'tag_live'
        WHEN priority_rank > FLOOR(graduated_count * 0.80) AND current_pool != 'reserve' THEN 'tag_bset'
        ELSE 'no_change'
    END as action_needed

FROM ranked_inboxes
ORDER BY domain_name, priority_rank;

COMMENT ON VIEW v_inbox_set_assignment IS
'Shows inbox-level A-Set/B-Set assignment based on priority ranking.
FIXED: Uses ACTUAL graduated count, not expected_inbox_count.
Ranking: Connected first, already deployed first, oldest warmup, highest health.';

COMMIT;

-- Log migration and show sample
DO $$
DECLARE
    sample_domain RECORD;
BEGIN
    RAISE NOTICE 'Migration 075: Fixed set distribution views to use actual graduated count';

    -- Show a sample domain to verify fix
    SELECT domain_name, graduated_count, target_a_set, target_b_set, set_status
    INTO sample_domain
    FROM v_inbox_set_distribution
    WHERE graduated_count > 0 AND graduated_count < 50
    LIMIT 1;

    IF FOUND THEN
        RAISE NOTICE 'Sample: % has % graduated -> target A-Set: %, B-Set: % (status: %)',
            sample_domain.domain_name,
            sample_domain.graduated_count,
            sample_domain.target_a_set,
            sample_domain.target_b_set,
            sample_domain.set_status;
    END IF;
END $$;
