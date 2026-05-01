-- Migration 078: Update Domain Allocation to 80/20
-- Created: 2026-03-06
-- Purpose: Allocate 80% of domains to live (A-Set), 20% to reserve (B-Set)
--
-- RATIONALE:
-- - 80% domains actively sending = maximum capacity utilization
-- - 20% domains in reserve = buffer for domain burns
-- - ALL inboxes on a domain are the same set (no blast radius bleed)
--
-- Example: 10 domains → 8 live, 2 reserve
-- Each domain has 50 inboxes → 400 deployed, 100 reserve

BEGIN;

-- =====================================================
-- 1. UPDATE ALLOCATION FUNCTION TO 80/20
-- =====================================================

CREATE OR REPLACE FUNCTION allocate_domain_sets(p_workspace_id UUID)
RETURNS TABLE (
    domain_id UUID,
    domain_name VARCHAR,
    new_status VARCHAR,
    action VARCHAR
) AS $$
DECLARE
    v_total_unassigned INTEGER;
    v_live_count INTEGER;
    v_current_live INTEGER;
    v_current_reserve INTEGER;
    v_target_live_pct NUMERIC := 0.80;  -- 80% live, 20% reserve
BEGIN
    -- Count current allocation
    SELECT
        COUNT(*) FILTER (WHERE pool_status = 'live'),
        COUNT(*) FILTER (WHERE pool_status = 'reserve')
    INTO v_current_live, v_current_reserve
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

    -- Calculate how many should be live (80%)
    -- Round up to prefer more live capacity
    v_live_count := CEIL(v_total_unassigned * v_target_live_pct);

    -- Ensure at least 1 reserve if we have 2+ domains
    IF v_total_unassigned >= 2 AND v_live_count = v_total_unassigned THEN
        v_live_count := v_total_unassigned - 1;
    END IF;

    -- Adjust if current allocation is already imbalanced
    -- Goal: maintain ~80/20 ratio across all domains
    IF v_current_live + v_current_reserve > 0 THEN
        DECLARE
            v_total_after INTEGER := v_current_live + v_current_reserve + v_total_unassigned;
            v_target_live INTEGER := CEIL(v_total_after * v_target_live_pct);
            v_needed_live INTEGER := v_target_live - v_current_live;
        BEGIN
            -- Clamp to available unassigned domains
            IF v_needed_live > v_total_unassigned THEN
                v_live_count := v_total_unassigned;
            ELSIF v_needed_live < 0 THEN
                v_live_count := 0;
            ELSE
                v_live_count := v_needed_live;
            END IF;
        END;
    END IF;

    -- Allocate domains (oldest first for stability)
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
                WHEN rd.rn <= v_live_count THEN 'live'
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

COMMENT ON FUNCTION allocate_domain_sets IS
'Allocate unassigned domains to live (80%) or reserve (20%).
ALL inboxes on a domain follow the domain pool_status.
80/20 ratio provides capacity while maintaining burn buffer.';

-- =====================================================
-- 2. UPDATE DOCUMENTATION COMMENTS
-- =====================================================

COMMENT ON COLUMN domains.pool_status IS
'Domain pool allocation: unassigned (new), live (80% - deployed to campaigns), reserve (20% - warmed backup), burned (compromised)';

COMMIT;

SELECT 'Migration 078_domain_allocation_80_20 complete' AS status;
