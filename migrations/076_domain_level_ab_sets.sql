-- Migration 076: Domain-Level A/B Set Allocation
-- Created: 2026-03-05
-- Purpose: Entire domains are A-Set or B-Set, not individual inboxes
--
-- TERMINOLOGY (matches EmailBison tags):
-- - 'live'     = A-Set: Deployed to campaigns, actively sending
-- - 'reserve'  = B-Set: Warmed reserve, ready to promote when A-Set burns
-- - 'burned'   = Compromised by spam complaint, permanently retired
--
-- RATIONALE:
-- When a domain-killing trigger (spam_complaint) fires, ALL inboxes on that
-- domain are compromised. Mixed A/B per domain means B-Set is useless when
-- the domain burns. By allocating entire domains to A or B set:
-- - Live domains are deployed to campaigns
-- - Reserve domains are warmed reserve, completely isolated
-- - When live domain burns, promote a reserve domain to replace it
-- - Reserve domains are never exposed to campaign risk
--
-- ALLOCATION RULE:
-- - Client gets N domains for a package
-- - Half are live (deployed), half are reserve
-- - Only split when odd number (e.g., 5 domains = 3 live, 2 reserve)

BEGIN;

-- =====================================================
-- 1. ADD DOMAIN POOL STATUS
-- =====================================================

ALTER TABLE domains
ADD COLUMN IF NOT EXISTS pool_status VARCHAR(20) DEFAULT 'unassigned',
ADD COLUMN IF NOT EXISTS pool_assigned_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS promoted_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS burned_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS burn_trigger VARCHAR(50);

-- Valid statuses (matches inbox tagging: live/reserve)
COMMENT ON COLUMN domains.pool_status IS
'Domain pool allocation: unassigned (new), live (deployed to campaigns), reserve (warmed B-Set), burned (compromised, do not use)';

-- Add constraint
ALTER TABLE domains DROP CONSTRAINT IF EXISTS valid_pool_status;
ALTER TABLE domains ADD CONSTRAINT valid_pool_status
    CHECK (pool_status IN ('unassigned', 'live', 'reserve', 'burned'));

-- =====================================================
-- 2. DOMAIN POOL HISTORY (AUDIT TRAIL)
-- =====================================================

CREATE TABLE IF NOT EXISTS domain_pool_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,

    old_status VARCHAR(20),
    new_status VARCHAR(20) NOT NULL,

    -- Context
    reason VARCHAR(100),        -- 'initial_allocation', 'promotion', 'burn', 'manual'
    trigger_type VARCHAR(50),   -- If burned, what trigger caused it
    replacing_domain_id UUID REFERENCES domains(id),  -- If promoted, which A-Set domain it replaces

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_domain_pool_history_domain
    ON domain_pool_history(domain_id, created_at DESC);

-- =====================================================
-- 3. FUNCTION: ALLOCATE DOMAINS TO A/B SETS
-- =====================================================
-- For a workspace, allocate unassigned domains: half A-Set, half B-Set

CREATE OR REPLACE FUNCTION allocate_domain_sets(p_workspace_id UUID)
RETURNS TABLE (
    domain_id UUID,
    domain_name VARCHAR,
    new_status VARCHAR,
    action VARCHAR
) AS $$
DECLARE
    v_total_unassigned INTEGER;
    v_a_set_count INTEGER;
    v_current_a INTEGER;
    v_current_b INTEGER;
BEGIN
    -- Count current allocation
    SELECT
        COUNT(*) FILTER (WHERE pool_status = 'live'),
        COUNT(*) FILTER (WHERE pool_status = 'reserve')
    INTO v_current_a, v_current_b
    FROM domains
    WHERE workspace_id = p_workspace_id AND is_active = TRUE;

    -- Count unassigned
    SELECT COUNT(*) INTO v_total_unassigned
    FROM domains
    WHERE workspace_id = p_workspace_id
    AND is_active = TRUE
    AND pool_status = 'unassigned';

    IF v_total_unassigned = 0 THEN
        RETURN;
    END IF;

    -- Calculate how many should be A-Set
    -- Goal: equal split, but if uneven, prefer A-Set
    -- Also consider existing allocation
    v_a_set_count := CEIL(v_total_unassigned::NUMERIC / 2);

    -- Adjust if we already have imbalance
    IF v_current_a > v_current_b THEN
        -- More A than B, new domains should be B-heavy
        v_a_set_count := FLOOR(v_total_unassigned::NUMERIC / 2);
    END IF;

    -- Allocate domains
    RETURN QUERY
    WITH ranked_domains AS (
        SELECT
            d.id,
            d.domain_name,
            ROW_NUMBER() OVER (ORDER BY d.created_at ASC) as rn
        FROM domains d
        WHERE d.workspace_id = p_workspace_id
        AND d.is_active = TRUE
        AND d.pool_status = 'unassigned'
    ),
    updated AS (
        UPDATE domains d
        SET
            pool_status = CASE
                WHEN rd.rn <= v_a_set_count THEN 'live'
                ELSE 'reserve'
            END,
            pool_assigned_at = NOW()
        FROM ranked_domains rd
        WHERE d.id = rd.id
        RETURNING d.id, d.domain_name, d.pool_status
    )
    SELECT
        u.id as domain_id,
        u.domain_name,
        u.pool_status as new_status,
        'allocated'::VARCHAR as action
    FROM updated u;

END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 4. FUNCTION: BURN DOMAIN AND PROMOTE B-SET
-- =====================================================
-- When A-Set domain burns, mark it and promote a B-Set domain

CREATE OR REPLACE FUNCTION burn_domain_and_promote(
    p_domain_id UUID,
    p_trigger_type VARCHAR
) RETURNS TABLE (
    burned_domain_id UUID,
    burned_domain_name VARCHAR,
    promoted_domain_id UUID,
    promoted_domain_name VARCHAR,
    action VARCHAR
) AS $$
DECLARE
    v_workspace_id UUID;
    v_burned_name VARCHAR;
    v_promoted_id UUID;
    v_promoted_name VARCHAR;
BEGIN
    -- Get workspace
    SELECT workspace_id, domain_name INTO v_workspace_id, v_burned_name
    FROM domains WHERE id = p_domain_id;

    -- Mark domain as burned
    UPDATE domains
    SET
        pool_status = 'burned',
        burned_at = NOW(),
        burn_trigger = p_trigger_type
    WHERE id = p_domain_id
    AND pool_status = 'live';  -- Only burn A-Set domains

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            p_domain_id,
            v_burned_name,
            NULL::UUID,
            NULL::VARCHAR,
            'not_live'::VARCHAR;
        RETURN;
    END IF;

    -- Log the burn
    INSERT INTO domain_pool_history (domain_id, old_status, new_status, reason, trigger_type)
    VALUES (p_domain_id, 'live', 'burned', 'domain_burned', p_trigger_type);

    -- Find oldest B-Set domain to promote
    SELECT id, domain_name INTO v_promoted_id, v_promoted_name
    FROM domains
    WHERE workspace_id = v_workspace_id
    AND pool_status = 'reserve'
    AND is_active = TRUE
    ORDER BY pool_assigned_at ASC  -- Oldest B-Set first
    LIMIT 1;

    IF v_promoted_id IS NOT NULL THEN
        -- Promote B-Set to A-Set
        UPDATE domains
        SET
            pool_status = 'live',
            promoted_at = NOW()
        WHERE id = v_promoted_id;

        -- Log the promotion
        INSERT INTO domain_pool_history (domain_id, old_status, new_status, reason, replacing_domain_id)
        VALUES (v_promoted_id, 'reserve', 'live', 'promotion', p_domain_id);

        RETURN QUERY SELECT
            p_domain_id,
            v_burned_name,
            v_promoted_id,
            v_promoted_name,
            'promoted'::VARCHAR;
    ELSE
        -- No B-Set available
        RETURN QUERY SELECT
            p_domain_id,
            v_burned_name,
            NULL::UUID,
            NULL::VARCHAR,
            'no_reserve'::VARCHAR;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 5. VIEW: DOMAIN SET OVERVIEW
-- =====================================================

CREATE OR REPLACE VIEW v_domain_sets AS
SELECT
    d.id as domain_id,
    d.domain_name,
    d.pool_status,
    d.pool_assigned_at,
    d.promoted_at,
    d.burned_at,
    d.burn_trigger,
    w.workspace_name,
    w.id as workspace_id,

    -- Inbox stats
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,
    COUNT(*) FILTER (WHERE sa.inventory_lifecycle_status = 'active') as graduated_inboxes,

    -- Capacity
    COALESCE(d.expected_inbox_count,
        CASE WHEN d.infrastructure_type = 'google' THEN 3 ELSE 50 END
    ) as expected_inboxes,

    -- Health
    CASE
        WHEN d.pool_status = 'burned' THEN 'burned'
        WHEN COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') = 0 THEN 'disconnected'
        WHEN COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') <
             COALESCE(d.expected_inbox_count, 50) * 0.5 THEN 'degraded'
        ELSE 'healthy'
    END as domain_health,

    d.infrastructure_type as provider

FROM domains d
JOIN workspaces w ON d.workspace_id = w.id
LEFT JOIN sender_accounts sa ON sa.domain_id = d.id AND sa.is_active = TRUE
WHERE d.is_active = TRUE
GROUP BY d.id, d.domain_name, d.pool_status, d.pool_assigned_at, d.promoted_at,
         d.burned_at, d.burn_trigger, w.workspace_name, w.id, d.expected_inbox_count,
         d.infrastructure_type;

-- =====================================================
-- 6. VIEW: WORKSPACE SET SUMMARY
-- =====================================================

CREATE OR REPLACE VIEW v_workspace_domain_sets AS
SELECT
    w.id as workspace_id,
    w.workspace_name,

    -- Domain counts by status
    COUNT(*) FILTER (WHERE d.pool_status = 'live') as a_set_domains,
    COUNT(*) FILTER (WHERE d.pool_status = 'reserve') as b_set_domains,
    COUNT(*) FILTER (WHERE d.pool_status = 'burned') as burned_domains,
    COUNT(*) FILTER (WHERE d.pool_status = 'unassigned') as unassigned_domains,

    -- Inbox capacity (A-Set only - what's deployed)
    SUM(CASE WHEN d.pool_status = 'live' THEN
        (SELECT COUNT(*) FROM sender_accounts sa
         WHERE sa.domain_id = d.id AND sa.inbox_state = 'live' AND sa.status = 'Connected')
    ELSE 0 END) as a_set_connected_inboxes,

    -- Reserve capacity (B-Set)
    SUM(CASE WHEN d.pool_status = 'reserve' THEN
        (SELECT COUNT(*) FROM sender_accounts sa
         WHERE sa.domain_id = d.id AND sa.inbox_state = 'live' AND sa.status = 'Connected')
    ELSE 0 END) as b_set_connected_inboxes,

    -- Health indicators
    COUNT(*) FILTER (WHERE d.pool_status = 'live' AND d.domain_state = 'flagged') as flagged_a_set,

    -- Alerts
    CASE
        WHEN COUNT(*) FILTER (WHERE d.pool_status = 'reserve') = 0
             AND COUNT(*) FILTER (WHERE d.pool_status = 'live') > 0
        THEN 'no_reserve'
        WHEN COUNT(*) FILTER (WHERE d.pool_status = 'reserve') = 1 THEN 'low_reserve'
        WHEN COUNT(*) FILTER (WHERE d.pool_status = 'unassigned') > 0 THEN 'needs_allocation'
        ELSE 'healthy'
    END as reserve_status

FROM workspaces w
LEFT JOIN domains d ON d.workspace_id = w.id AND d.is_active = TRUE
WHERE w.is_active = TRUE
GROUP BY w.id, w.workspace_name
HAVING COUNT(*) FILTER (WHERE d.id IS NOT NULL) > 0;

-- =====================================================
-- 7. BACKFILL: ASSIGN EXISTING DOMAINS
-- =====================================================
-- Mark existing domains based on current state:
-- - Domains with spam_complaint kills → burned
-- - Remaining domains → allocate 50/50

-- First, mark burned domains
UPDATE domains d
SET
    pool_status = 'burned',
    burned_at = COALESCE(
        (SELECT MIN(sa.killed_at) FROM sender_accounts sa
         WHERE sa.domain_id = d.id AND sa.kill_trigger = 'spam_complaint'),
        NOW()
    ),
    burn_trigger = 'spam_complaint'
WHERE d.is_active = TRUE
AND d.pool_status = 'unassigned'
AND EXISTS (
    SELECT 1 FROM sender_accounts sa
    WHERE sa.domain_id = d.id
    AND sa.kill_trigger = 'spam_complaint'
);

-- Log backfill
INSERT INTO domain_pool_history (domain_id, old_status, new_status, reason, trigger_type)
SELECT
    d.id,
    'unassigned',
    'burned',
    'backfill_spam_complaint',
    'spam_complaint'
FROM domains d
WHERE d.pool_status = 'burned'
AND NOT EXISTS (
    SELECT 1 FROM domain_pool_history dph
    WHERE dph.domain_id = d.id
);

-- =====================================================
-- 8. INDEXES
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_domains_pool_status
    ON domains(workspace_id, pool_status)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_domains_pool_promotion
    ON domains(workspace_id, pool_status, pool_assigned_at)
    WHERE pool_status = 'reserve' AND is_active = TRUE;

-- =====================================================
-- 9. SUMMARY OUTPUT
-- =====================================================

-- Show domain allocation needs
SELECT
    workspace_name,
    COUNT(*) FILTER (WHERE pool_status = 'unassigned') as needs_allocation,
    COUNT(*) FILTER (WHERE pool_status = 'live') as a_set,
    COUNT(*) FILTER (WHERE pool_status = 'reserve') as b_set,
    COUNT(*) FILTER (WHERE pool_status = 'burned') as burned
FROM domains d
JOIN workspaces w ON d.workspace_id = w.id
WHERE d.is_active = TRUE
GROUP BY workspace_name
ORDER BY needs_allocation DESC;

COMMIT;

SELECT 'Migration 076_domain_level_ab_sets complete' AS status;
