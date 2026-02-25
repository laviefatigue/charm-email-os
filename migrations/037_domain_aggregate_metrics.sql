-- Migration 037: Domain Aggregate Metrics
-- Adds domain-wide bounce rate calculation for V3 compliance
-- Created: 2026-02-22

-- ============================================================================
-- ADD AGGREGATE COLUMNS TO DOMAINS TABLE
-- ============================================================================

-- Domain-wide bounce rate (aggregate of all inbox bounce rates)
ALTER TABLE domains
ADD COLUMN IF NOT EXISTS domain_bounce_rate_7d DECIMAL(5,4) DEFAULT 0;

-- Domain-wide sends (sum of all inbox sends)
ALTER TABLE domains
ADD COLUMN IF NOT EXISTS domain_sends_7d INTEGER DEFAULT 0;

-- Domain-wide bounces (sum of all inbox bounces)
ALTER TABLE domains
ADD COLUMN IF NOT EXISTS domain_bounces_7d INTEGER DEFAULT 0;

-- Burn count by trigger type (JSONB for flexibility)
-- Example: {"spam_complaint": 2, "hard_blocked_24h": 1, "fresh_inbox_bounce": 3}
ALTER TABLE domains
ADD COLUMN IF NOT EXISTS burn_breakdown JSONB DEFAULT '{}';

-- Last aggregate calculation timestamp
ALTER TABLE domains
ADD COLUMN IF NOT EXISTS metrics_calculated_at TIMESTAMPTZ;

-- ============================================================================
-- ADD CROSS-INBOX PATTERN DETECTION COLUMNS
-- ============================================================================

-- Count of inboxes with complaints (for cross-inbox detection)
ALTER TABLE domains
ADD COLUMN IF NOT EXISTS inboxes_with_complaints INTEGER DEFAULT 0;

-- Count of inboxes with blocks (for cross-inbox detection)
ALTER TABLE domains
ADD COLUMN IF NOT EXISTS inboxes_with_blocks INTEGER DEFAULT 0;

-- ============================================================================
-- CREATE FUNCTION TO RECALCULATE DOMAIN METRICS
-- ============================================================================

CREATE OR REPLACE FUNCTION recalculate_domain_metrics(p_domain_id UUID)
RETURNS void AS $$
DECLARE
    v_bounce_rate DECIMAL(5,4);
    v_total_sends INTEGER;
    v_total_bounces INTEGER;
    v_complaints_count INTEGER;
    v_blocks_count INTEGER;
    v_burn_breakdown JSONB;
BEGIN
    -- Calculate aggregate metrics from all inboxes on this domain
    SELECT
        COALESCE(SUM(total_sends_7d), 0),
        COALESCE(SUM(hard_bounces_7d + soft_bounces_7d), 0),
        COUNT(*) FILTER (WHERE complaints_lifetime > 0),
        COUNT(*) FILTER (WHERE hard_blocked_24h > 0)
    INTO v_total_sends, v_total_bounces, v_complaints_count, v_blocks_count
    FROM sender_accounts
    WHERE domain_id = p_domain_id
      AND is_active = TRUE;

    -- Calculate bounce rate
    IF v_total_sends > 0 THEN
        v_bounce_rate := v_total_bounces::DECIMAL / v_total_sends;
    ELSE
        v_bounce_rate := 0;
    END IF;

    -- Calculate burn breakdown from campaign_burn_events
    SELECT COALESCE(
        jsonb_object_agg(kill_trigger_type, burn_count),
        '{}'::JSONB
    )
    INTO v_burn_breakdown
    FROM (
        SELECT kill_trigger_type, COUNT(*) as burn_count
        FROM campaign_burn_events
        WHERE domain_id = p_domain_id
        GROUP BY kill_trigger_type
    ) sub;

    -- Update domain record
    UPDATE domains
    SET
        domain_bounce_rate_7d = v_bounce_rate,
        domain_sends_7d = v_total_sends,
        domain_bounces_7d = v_total_bounces,
        inboxes_with_complaints = v_complaints_count,
        inboxes_with_blocks = v_blocks_count,
        burn_breakdown = v_burn_breakdown,
        metrics_calculated_at = NOW(),
        updated_at = NOW()
    WHERE id = p_domain_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- CREATE FUNCTION TO RECALCULATE ALL DOMAINS IN WORKSPACE
-- ============================================================================

CREATE OR REPLACE FUNCTION recalculate_workspace_domain_metrics(p_workspace_id UUID)
RETURNS INTEGER AS $$
DECLARE
    v_domain_id UUID;
    v_count INTEGER := 0;
BEGIN
    FOR v_domain_id IN
        SELECT id FROM domains WHERE workspace_id = p_workspace_id
    LOOP
        PERFORM recalculate_domain_metrics(v_domain_id);
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- BACKFILL DOMAIN METRICS FOR ALL EXISTING DOMAINS
-- ============================================================================

DO $$
DECLARE
    v_domain_id UUID;
    v_count INTEGER := 0;
BEGIN
    FOR v_domain_id IN
        SELECT id FROM domains
    LOOP
        PERFORM recalculate_domain_metrics(v_domain_id);
        v_count := v_count + 1;
    END LOOP;

    RAISE NOTICE 'Recalculated metrics for % domains', v_count;
END $$;

-- ============================================================================
-- INDEX FOR DOMAIN HEALTH QUERIES
-- ============================================================================

-- Fast lookup for domains with high bounce rate
CREATE INDEX IF NOT EXISTS idx_domains_bounce_rate
ON domains(domain_bounce_rate_7d DESC)
WHERE domain_bounce_rate_7d > 0;

-- Fast lookup for domains with cross-inbox issues
CREATE INDEX IF NOT EXISTS idx_domains_cross_inbox_issues
ON domains(inboxes_with_complaints, inboxes_with_blocks)
WHERE inboxes_with_complaints > 1 OR inboxes_with_blocks > 1;

-- ============================================================================
-- VIEW FOR DOMAIN HEALTH ALERTS
-- ============================================================================

CREATE OR REPLACE VIEW domain_health_alerts AS
SELECT
    d.id as domain_id,
    d.domain_name,
    d.workspace_id,
    d.domain_state,
    d.domain_bounce_rate_7d,
    d.dead_inbox_count,
    d.live_inbox_count,
    d.inboxes_with_complaints,
    d.inboxes_with_blocks,
    d.burn_breakdown,
    -- Alert conditions
    CASE
        WHEN d.domain_bounce_rate_7d > 0.05 THEN 'critical'
        WHEN d.domain_bounce_rate_7d > 0.03 THEN 'warning'
        WHEN d.inboxes_with_complaints >= 2 THEN 'warning'
        WHEN d.inboxes_with_blocks >= 2 THEN 'warning'
        ELSE 'healthy'
    END as alert_level,
    -- Alert reasons (array)
    ARRAY_REMOVE(ARRAY[
        CASE WHEN d.domain_bounce_rate_7d > 0.05 THEN 'Bounce rate >5%' END,
        CASE WHEN d.inboxes_with_complaints >= 2 THEN 'Complaints across ' || d.inboxes_with_complaints || ' inboxes' END,
        CASE WHEN d.inboxes_with_blocks >= 2 THEN 'Blocks across ' || d.inboxes_with_blocks || ' inboxes' END,
        CASE WHEN d.dead_inbox_count >= 2 THEN d.dead_inbox_count || ' dead inboxes' END
    ], NULL) as alert_reasons
FROM domains d
WHERE d.domain_bounce_rate_7d > 0.03
   OR d.inboxes_with_complaints >= 2
   OR d.inboxes_with_blocks >= 2
   OR d.dead_inbox_count >= 2;

COMMENT ON VIEW domain_health_alerts IS
'Surfaces domains that need attention based on V3 thresholds:
- Bounce rate >5% = critical
- Cross-inbox complaints/blocks = warning
- 2+ dead inboxes = review required';

COMMENT ON FUNCTION recalculate_domain_metrics IS
'Recalculates aggregate metrics for a single domain.
Call after inbox death or during periodic health checks.';
