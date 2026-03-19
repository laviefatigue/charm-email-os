-- Migration 085: Rate-Based Domain Burns
-- Replaces count-based domain burn logic (2+ inbox kills = burn) with
-- rate-based evaluation + observation windows + workspace circuit breaker.
--
-- Context: Production data showed 56% of burned domains had complaint rates
-- below 0.1% (Google's "excellent" threshold). The count-based "2 inbox" rule
-- was size-blind: 2/52 on Microsoft (4%) vs 2/3 on Gmail (67%).
-- Industry measures domain reputation via aggregate spam RATE, not inbox counts.

-- ============================================================================
-- 1. Add 'monitoring' to domain_state enum
-- ============================================================================
-- 'monitoring' = domain has potential reputation issue, observing complaint rate
-- over 7-day window before deciding to burn or recover.
-- Distinct from 'flagged' (1 reputation kill, informational warning).
ALTER TYPE domain_state ADD VALUE IF NOT EXISTS 'monitoring' AFTER 'flagged';

-- ============================================================================
-- 2. New columns on domains table for rate-based evaluation
-- ============================================================================
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_complaint_rate_7d DECIMAL(8,6) DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_complaints_7d INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS monitoring_started_at TIMESTAMPTZ;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS monitoring_reason TEXT;

-- ============================================================================
-- 3. Recalculate domain complaint rate for a single domain
-- ============================================================================
-- Uses killed_at timestamps from sender_accounts (not response_messages,
-- which has zero folder='spam' records — complaints detected via FBL in bounces).
CREATE OR REPLACE FUNCTION recalculate_domain_complaint_rate(p_domain_id UUID)
RETURNS VOID AS $$
DECLARE
    v_complaints_7d INTEGER;
    v_total_sends BIGINT;
    v_rate DECIMAL(8,6);
BEGIN
    -- Count complaints in last 7 days from dead inboxes killed by spam_complaint.
    -- We use killed_at as the complaint timestamp (complaints_lifetime is all-time,
    -- not windowed, so we can't use it for 7-day rates).
    -- Note: killed inboxes retain is_active = TRUE in our system.
    SELECT
        COALESCE(
            COUNT(*) FILTER (WHERE inbox_state = 'dead'
                AND kill_trigger = 'spam_complaint'
                AND killed_at >= NOW() - INTERVAL '7 days'),
            0
        ),
        -- Total sends across all inboxes on domain (all-time as proxy for volume)
        -- TODO: Use domain_sends_7d when reliably populated
        COALESCE(SUM(emails_sent_all_time), 0)
    INTO v_complaints_7d, v_total_sends
    FROM sender_accounts
    WHERE domain_id = p_domain_id
      AND is_active = TRUE;

    -- Calculate rate (avoid division by zero)
    IF v_total_sends > 0 THEN
        v_rate := v_complaints_7d::DECIMAL / v_total_sends;
    ELSE
        v_rate := 0;
    END IF;

    -- Update domain
    UPDATE domains
    SET domain_complaint_rate_7d = v_rate,
        domain_complaints_7d = v_complaints_7d,
        updated_at = NOW()
    WHERE id = p_domain_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 4. Bulk recalculate complaint rates for all domains in a workspace
-- ============================================================================
CREATE OR REPLACE FUNCTION recalculate_all_domain_complaint_rates(p_workspace_id UUID)
RETURNS INTEGER AS $$
DECLARE
    v_domain RECORD;
    v_count INTEGER := 0;
BEGIN
    FOR v_domain IN
        SELECT id FROM domains
        WHERE workspace_id = p_workspace_id
          AND is_active = TRUE
          AND pool_status NOT IN ('cancelled', 'unassigned')
    LOOP
        PERFORM recalculate_domain_complaint_rate(v_domain.id);
        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 5. Update v_infrastructure_waterfall to handle 'monitoring' state
-- ============================================================================
-- The waterfall view's rotation_recommendation CASE needs to recognize monitoring.
-- We add a priority entry for monitoring domains: they show as 'monitor' recommendation
-- (not 'rotate_now') since they're under observation.
--
-- Rather than recreating the entire complex view, we add a comment noting that
-- the Python code handles monitoring domains before the waterfall view is consulted.
-- The view already has a 'monitor' recommendation which is appropriate.
-- Domains in monitoring state with inboxes_with_complaints > 0 will naturally
-- hit the existing 'rotate_now' rule, which is overridden by the Python code
-- that checks domain_state = 'monitoring' and defers to the observation window.

-- ============================================================================
-- 6. Backfill: Calculate complaint rates for all existing domains
-- ============================================================================
DO $$
DECLARE
    v_ws RECORD;
    v_count INTEGER;
BEGIN
    FOR v_ws IN SELECT DISTINCT workspace_id FROM domains WHERE is_active = TRUE
    LOOP
        SELECT recalculate_all_domain_complaint_rates(v_ws.workspace_id) INTO v_count;
        RAISE NOTICE 'Workspace %: recalculated % domains', v_ws.workspace_id, v_count;
    END LOOP;
END;
$$;
