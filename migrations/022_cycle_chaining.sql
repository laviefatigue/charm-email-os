-- Migration: 022_cycle_chaining.sql
-- Purpose: Add cycle chaining support where new cycles can "build off" previous cycles
-- Enables: Cycle 2 builds on Cycle 1, Cycle 4 builds on Cycle 3, etc.

-- 1. Add parent_cycle_id to campaign_cycles for chaining
ALTER TABLE campaign_cycles
ADD COLUMN IF NOT EXISTS parent_cycle_id UUID REFERENCES campaign_cycles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_campaign_cycles_parent ON campaign_cycles(parent_cycle_id);

COMMENT ON COLUMN campaign_cycles.parent_cycle_id IS 'Reference to previous cycle this one builds upon';

-- 2. Add chain_position to track which cycle number in the chain
ALTER TABLE campaign_cycles
ADD COLUMN IF NOT EXISTS chain_position INTEGER DEFAULT 1;

COMMENT ON COLUMN campaign_cycles.chain_position IS 'Position in the cycle chain (1 = first, 2 = builds on 1, etc.)';

-- 3. Create view for cycle chain analysis
CREATE OR REPLACE VIEW v_cycle_chain AS
SELECT
    c.id,
    c.client_id,
    c.cycle_number,
    c.chain_position,
    c.parent_cycle_id,
    c.status,
    c.start_date,
    c.end_date,
    c.created_at,
    -- Parent cycle info
    pc.cycle_number as parent_cycle_number,
    pc.status as parent_status,
    -- Count of campaigns in this cycle
    (SELECT COUNT(*) FROM campaign_documents cd WHERE cd.cycle_id = c.id) as campaign_count,
    -- Approved campaigns from parent (for building upon)
    (SELECT COUNT(*) FROM campaign_documents cd
     WHERE cd.cycle_id = c.parent_cycle_id
     AND cd.status = 'approved') as parent_approved_campaigns
FROM campaign_cycles c
LEFT JOIN campaign_cycles pc ON c.parent_cycle_id = pc.id;

COMMENT ON VIEW v_cycle_chain IS 'View showing cycle chain relationships and parent cycle info';

-- 4. Function to get the latest completed cycle for a client
CREATE OR REPLACE FUNCTION get_latest_completed_cycle(p_client_id UUID)
RETURNS TABLE (
    cycle_id UUID,
    cycle_number INTEGER,
    completed_at TIMESTAMP
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.id as cycle_id,
        cc.cycle_number,
        cc.updated_at as completed_at
    FROM campaign_cycles cc
    WHERE cc.client_id = p_client_id
    AND cc.status IN ('completed', 'active')
    ORDER BY cc.cycle_number DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_latest_completed_cycle IS 'Get the most recent completed/active cycle for a client to build upon';
