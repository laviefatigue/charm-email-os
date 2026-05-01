-- Migration 077: Standardize Set Terminology
-- Created: 2026-03-05
-- Purpose: Use consistent 'live'/'reserve' terminology instead of mixed 'bset'/'B Set'
--
-- STANDARD TAG NAMES:
-- - 'live'      = A-Set: deployed to campaigns, actively sending
-- - 'reserve'   = B-Set: warmed reserve, ready to promote when A-Set burns
-- - 'incubating' = warming up, not yet graduated (lifecycle status, not pool)
--
-- This migration updates views that still used 'bset' to use 'reserve'

BEGIN;

-- =====================================================
-- 1. UPDATE v_inbox_set_assignment VIEW
-- =====================================================
-- Fix target_set and action_needed to use 'reserve' instead of 'bset'

CREATE OR REPLACE VIEW v_inbox_set_assignment AS
WITH domain_graduated_counts AS (
    SELECT
        domain_id,
        COUNT(*) as graduated_count
    FROM sender_accounts
    WHERE is_active = TRUE
    AND inbox_state = 'live'
    AND inventory_lifecycle_status = 'active'
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
        COALESCE(dgc.graduated_count, 0) as graduated_count,
        sa.inbox_state,
        sa.status,
        sa.inventory_lifecycle_status,
        sa.inventory_pool_status as current_pool,
        sa.warmup_started_at,
        sa.health_score,
        -- Rank inboxes within domain by priority for A-set assignment
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
    LEFT JOIN domain_graduated_counts dgc ON dgc.domain_id = sa.domain_id
    WHERE sa.is_active = TRUE
    AND sa.inbox_state = 'live'
    AND sa.inventory_lifecycle_status = 'active'
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
    -- FIXED: Use 'reserve' instead of 'bset'
    CASE
        WHEN priority_rank <= FLOOR(graduated_count * 0.80) THEN 'live'
        ELSE 'reserve'
    END as target_set,

    -- Action needed
    -- FIXED: Use 'tag_reserve' instead of 'tag_bset'
    CASE
        WHEN priority_rank <= FLOOR(graduated_count * 0.80) AND current_pool != 'deployed' THEN 'tag_live'
        WHEN priority_rank > FLOOR(graduated_count * 0.80) AND current_pool != 'reserve' THEN 'tag_reserve'
        ELSE 'no_change'
    END as action_needed

FROM ranked_inboxes
ORDER BY domain_name, priority_rank;

COMMENT ON VIEW v_inbox_set_assignment IS
'Shows inbox-level A-Set/B-Set assignment based on priority ranking.
Standard terminology: live (A-Set deployed), reserve (B-Set warmed backup).
Ranking: Connected first, already deployed first, oldest warmup, highest health.';

-- =====================================================
-- 2. UPDATE WORKSPACE TAG NAME DEFAULTS
-- =====================================================
-- Update comment to reflect standard naming

COMMENT ON COLUMN workspaces.a_set_tag_name IS
'EmailBison tag name for A-Set (deployed). Standard: "live", Legacy: "A Set"';

COMMENT ON COLUMN workspaces.b_set_tag_name IS
'EmailBison tag name for B-Set (reserve). Standard: "reserve", Legacy: "B Set", "bset"';

-- =====================================================
-- 3. UPDATE SET CONFIGURATIONS COMMENT
-- =====================================================

COMMENT ON TABLE set_configurations IS
'Configurable A-Set/B-Set percentages per provider.
A-Set (live): Actively assigned to campaigns.
B-Set (reserve): Warmed backup pool, ready to promote when A-Set burns.
Default: 80% live, 20% reserve for both Entra and Google.';

COMMIT;

SELECT 'Migration 077_standardize_set_terminology complete' AS status;
