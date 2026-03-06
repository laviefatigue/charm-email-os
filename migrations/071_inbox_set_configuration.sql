-- Migration 071: Inbox Set Configuration (A-Set / B-Set)
-- Created: 2026-03-05
-- Purpose: Configurable live/reserve set percentages with automated tagging
--
-- A-Set (live): Inboxes actively assigned to campaigns
-- B-Set (bset): Reserve inboxes, warmed and ready to promote when A-Set inboxes die
--
-- Default configuration:
-- - Entra: 80% A-Set, 20% B-Set (40/10 split on 50-inbox domain)
-- - Google: 100% A-Set, 0% B-Set (reserve at domain level instead)

BEGIN;

-- =====================================================
-- 0. WORKSPACE TAG CONFIGURATION
-- =====================================================
-- Add columns to track tag naming convention per workspace
-- Some workspaces use 'A Set'/'B Set', others use 'live'/'bset'

ALTER TABLE workspaces
ADD COLUMN IF NOT EXISTS a_set_tag_name VARCHAR(50) DEFAULT NULL,
ADD COLUMN IF NOT EXISTS b_set_tag_name VARCHAR(50) DEFAULT NULL;

COMMENT ON COLUMN workspaces.a_set_tag_name IS
'EmailBison tag name for A-Set (live/deployed). Default: "live", Legacy: "A Set"';

COMMENT ON COLUMN workspaces.b_set_tag_name IS
'EmailBison tag name for B-Set (reserve). Default: "bset", Legacy: "B Set"';

-- =====================================================
-- 1. SET CONFIGURATION TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS set_configurations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scope (global, workspace, or domain-specific)
    scope VARCHAR(20) NOT NULL DEFAULT 'global',
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    domain_id UUID REFERENCES domains(id) ON DELETE CASCADE,

    -- Provider (entra or google)
    provider VARCHAR(20) NOT NULL,

    -- Set percentages (must sum to 100)
    live_percentage INTEGER NOT NULL DEFAULT 80,  -- A-Set
    bset_percentage INTEGER NOT NULL DEFAULT 20,  -- B-Set (reserve)

    -- Constraints
    CONSTRAINT valid_percentages CHECK (live_percentage + bset_percentage = 100),
    CONSTRAINT valid_live_range CHECK (live_percentage BETWEEN 50 AND 100),
    CONSTRAINT valid_bset_range CHECK (bset_percentage BETWEEN 0 AND 50),
    CONSTRAINT valid_provider CHECK (provider IN ('entra', 'google')),
    CONSTRAINT valid_scope CHECK (scope IN ('global', 'workspace', 'domain')),

    -- Metadata
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

-- Unique constraints per scope
CREATE UNIQUE INDEX IF NOT EXISTS idx_set_config_global
    ON set_configurations(scope, provider)
    WHERE scope = 'global' AND is_active = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_set_config_workspace
    ON set_configurations(workspace_id, provider)
    WHERE scope = 'workspace' AND is_active = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_set_config_domain
    ON set_configurations(domain_id, provider)
    WHERE scope = 'domain' AND is_active = TRUE;

-- =====================================================
-- 2. CONFIGURATION HISTORY (AUDIT TRAIL)
-- =====================================================

CREATE TABLE IF NOT EXISTS set_configuration_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    config_id UUID NOT NULL REFERENCES set_configurations(id) ON DELETE CASCADE,

    old_live_percentage INTEGER,
    new_live_percentage INTEGER,
    old_bset_percentage INTEGER,
    new_bset_percentage INTEGER,

    changed_by UUID REFERENCES users(id),
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_set_config_history_config
    ON set_configuration_history(config_id, changed_at DESC);

-- =====================================================
-- 3. INSERT DEFAULT CONFIGURATIONS
-- =====================================================

INSERT INTO set_configurations (scope, provider, live_percentage, bset_percentage)
VALUES
    ('global', 'entra', 80, 20),   -- Entra: 80% live, 20% reserve
    ('global', 'google', 80, 20)   -- Google: 80% live, 20% reserve (domain-level swap)
ON CONFLICT DO NOTHING;

-- =====================================================
-- 4. FUNCTION: GET EFFECTIVE SET CONFIG
-- =====================================================
-- Returns the configuration for a domain with inheritance:
-- domain config > workspace config > global config

CREATE OR REPLACE FUNCTION get_set_config(
    p_domain_id UUID,
    p_provider VARCHAR
) RETURNS TABLE (
    live_percentage INTEGER,
    bset_percentage INTEGER,
    config_source VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        sc.live_percentage,
        sc.bset_percentage,
        sc.scope as config_source
    FROM set_configurations sc
    LEFT JOIN domains d ON d.id = p_domain_id
    WHERE sc.is_active = TRUE
    AND sc.provider = p_provider
    AND (
        (sc.scope = 'domain' AND sc.domain_id = p_domain_id)
        OR (sc.scope = 'workspace' AND sc.workspace_id = d.workspace_id)
        OR (sc.scope = 'global')
    )
    ORDER BY
        CASE sc.scope
            WHEN 'domain' THEN 1
            WHEN 'workspace' THEN 2
            WHEN 'global' THEN 3
        END
    LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;

-- =====================================================
-- 5. VIEW: CURRENT SET DISTRIBUTION
-- =====================================================
-- Shows current A-Set/B-Set distribution per domain

CREATE OR REPLACE VIEW v_inbox_set_distribution AS
WITH domain_config AS (
    SELECT
        d.id as domain_id,
        d.domain_name,
        d.workspace_id,
        w.workspace_name,
        COALESCE(d.infrastructure_type,
            CASE WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id AND sa.esp = 'microsoft') THEN 'entra'
                 WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id AND sa.esp = 'gmail') THEN 'google'
                 ELSE 'unknown' END
        ) as provider,
        COALESCE(d.expected_inbox_count,
            CASE WHEN d.infrastructure_type = 'google' THEN 3 ELSE 50 END
        ) as expected_inbox_count
    FROM domains d
    JOIN workspaces w ON d.workspace_id = w.id
    WHERE d.is_active = TRUE
),
inbox_counts AS (
    SELECT
        sa.domain_id,
        -- Total counts
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,

        -- Lifecycle status
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'incubating') as incubating,
        COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'active') as graduated,

        -- Current pool assignment
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'deployed' AND sa.inbox_state = 'live') as current_a_set,
        COUNT(*) FILTER (WHERE sa.inventory_pool_status = 'reserve' AND sa.inbox_state = 'live') as current_b_set,

        -- Eligible for A/B set (graduated + connected)
        COUNT(*) FILTER (
            WHERE sa.inbox_state = 'live'
            AND sa.inventory_lifecycle_status = 'active'
            AND sa.status = 'Connected'
        ) as eligible_for_sets

    FROM sender_accounts sa
    WHERE sa.is_active = TRUE
    GROUP BY sa.domain_id
)
SELECT
    dc.domain_id,
    dc.domain_name,
    dc.workspace_name,
    dc.provider,
    dc.expected_inbox_count,

    -- Current state
    COALESCE(ic.live_inboxes, 0) as live_inboxes,
    COALESCE(ic.connected, 0) as connected,
    COALESCE(ic.incubating, 0) as incubating,
    COALESCE(ic.graduated, 0) as graduated,
    COALESCE(ic.eligible_for_sets, 0) as eligible_for_sets,
    COALESCE(ic.current_a_set, 0) as current_a_set,
    COALESCE(ic.current_b_set, 0) as current_b_set,

    -- Target state (80/20 for both providers)
    FLOOR(dc.expected_inbox_count * 0.80)::INTEGER as target_a_set,
    CEIL(dc.expected_inbox_count * 0.20)::INTEGER as target_b_set,

    -- Actions needed
    CASE
        WHEN COALESCE(ic.graduated, 0) <= FLOOR(dc.expected_inbox_count * 0.80) THEN 0  -- All graduated should be A-set
        ELSE COALESCE(ic.graduated, 0) - FLOOR(dc.expected_inbox_count * 0.80)::INTEGER
    END as need_to_move_to_b_set,

    -- Status
    CASE
        WHEN COALESCE(ic.live_inboxes, 0) = 0 THEN 'no_inboxes'
        WHEN COALESCE(ic.graduated, 0) = 0 THEN 'all_incubating'
        WHEN COALESCE(ic.current_b_set, 0) > 0 THEN 'has_reserve'
        WHEN COALESCE(ic.graduated, 0) > FLOOR(dc.expected_inbox_count * 0.80) THEN 'needs_bset_tagging'
        ELSE 'under_capacity'
    END as set_status

FROM domain_config dc
LEFT JOIN inbox_counts ic ON dc.domain_id = ic.domain_id
WHERE COALESCE(ic.live_inboxes, 0) > 0;

-- =====================================================
-- 6. VIEW: INBOX-LEVEL SET ASSIGNMENT
-- =====================================================
-- Shows exactly which inboxes should be in A-Set vs B-Set

CREATE OR REPLACE VIEW v_inbox_set_assignment AS
WITH ranked_inboxes AS (
    SELECT
        sa.id as inbox_id,
        sa.email_address,
        sa.domain_id,
        d.domain_name,
        COALESCE(d.infrastructure_type,
            CASE WHEN sa.esp = 'microsoft' THEN 'entra' ELSE 'google' END
        ) as provider,
        COALESCE(d.expected_inbox_count,
            CASE WHEN d.infrastructure_type = 'google' THEN 3 ELSE 50 END
        ) as expected_inbox_count,
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
                CASE WHEN sa.status = 'Connected' THEN 0 ELSE 1 END,  -- Connected first
                sa.warmup_started_at ASC NULLS LAST,                   -- Oldest warmup first
                sa.health_score DESC NULLS LAST                        -- Highest health
        ) as priority_rank
    FROM sender_accounts sa
    JOIN domains d ON sa.domain_id = d.id
    WHERE sa.is_active = TRUE
    AND sa.inbox_state = 'live'
    AND sa.inventory_lifecycle_status = 'active'  -- Only graduated inboxes
    AND d.is_active = TRUE
)
SELECT
    inbox_id,
    email_address,
    domain_id,
    domain_name,
    provider,
    inbox_state,
    status,
    inventory_lifecycle_status,
    current_pool,
    warmup_started_at,
    health_score,
    priority_rank,

    -- Target set based on rank (80/20 for both providers)
    CASE
        WHEN priority_rank <= FLOOR(expected_inbox_count * 0.80) THEN 'live'
        ELSE 'bset'
    END as target_set,

    -- Action needed
    CASE
        WHEN priority_rank <= FLOOR(expected_inbox_count * 0.80) AND current_pool != 'deployed' THEN 'tag_live'
        WHEN priority_rank > FLOOR(expected_inbox_count * 0.80) AND current_pool != 'reserve' THEN 'tag_bset'
        ELSE 'no_change'
    END as action_needed

FROM ranked_inboxes
ORDER BY domain_name, priority_rank;

-- =====================================================
-- 7. SUMMARY QUERY
-- =====================================================

-- Show current distribution summary
SELECT
    workspace_name,
    provider,
    COUNT(*) as domains,
    SUM(live_inboxes) as total_live,
    SUM(graduated) as total_graduated,
    SUM(current_a_set) as in_a_set,
    SUM(current_b_set) as in_b_set,
    SUM(target_a_set) as target_a,
    SUM(target_b_set) as target_b,
    SUM(need_to_move_to_b_set) as need_to_move
FROM v_inbox_set_distribution
GROUP BY workspace_name, provider
ORDER BY workspace_name, provider;

-- Show domains needing B-set tagging
SELECT
    workspace_name,
    domain_name,
    provider,
    graduated,
    current_a_set,
    current_b_set,
    target_a_set,
    target_b_set,
    need_to_move_to_b_set,
    set_status
FROM v_inbox_set_distribution
WHERE set_status = 'needs_bset_tagging'
ORDER BY need_to_move_to_b_set DESC
LIMIT 20;

-- =====================================================
-- 8. INDEXES FOR PERFORMANCE
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_sender_accounts_set_assignment
    ON sender_accounts(domain_id, inbox_state, inventory_lifecycle_status, status)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_sender_accounts_pool_lookup
    ON sender_accounts(domain_id, inventory_pool_status)
    WHERE inbox_state = 'live' AND is_active = TRUE;

-- =====================================================
-- 9. COMMENTS
-- =====================================================

COMMENT ON TABLE set_configurations IS
'Configurable A-Set/B-Set percentages per provider.
A-Set (live): Actively assigned to campaigns.
B-Set (bset): Reserve pool, ready to promote when A-Set inboxes die.
Default: Entra 80/20, Google 100/0 (Google uses domain-level reserve).';

COMMENT ON VIEW v_inbox_set_distribution IS
'Shows A-Set/B-Set distribution per domain with targets and actions needed.';

COMMENT ON VIEW v_inbox_set_assignment IS
'Inbox-level view showing which inboxes should be in A-Set vs B-Set based on priority ranking.';

COMMIT;

-- Show migration result
SELECT 'Migration 071_inbox_set_configuration complete' AS status;
