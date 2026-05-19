-- Migration 125: burn_domain_and_promote writes qualifies_for_cancellation_*
--
-- Step 8 of docs/plans/hypertide-data-model-and-change-tracking.md (DECISION 6).
--
-- When the kill-trigger evaluator burns a domain, we now ALSO persist the
-- "our system said this should be cancelled" verdict on the same row. The
-- Phase 2 change tracker (step 9) reads these columns to label HT-side
-- cancellations as justified (we said so first) vs unjustified (HT or operator
-- acted out-of-band).
--
-- Why persist at burn-time rather than re-derive at HT-transition time?
-- Kill-trigger rules and rule-state evolve between fire and HT-cancel-execution.
-- ADR-010 (lifetime-rate rewrite, 2026-05-04) was a real rule change; a domain
-- burned under the old count-based rule would re-derive WRONG under the new
-- lifetime-rate rule weeks later. The verdict at fire-time is the only honest
-- answer. See docs/plans/hypertide-data-model-and-change-tracking.md DECISION 6.
--
-- Idempotency: re-firing burn on an already-burned domain refreshes the
-- timestamp (replaces the prior verdict — most-recent burn wins). The
-- function's WHERE clause restricts to pool_status IN ('live','reserve') so
-- repeated calls on an already-burned domain are no-ops (NOT FOUND → early
-- return) and don't update the verdict columns.
--
-- Revert path: not wired in this migration. Operator scripts that
-- resurrect a falsely-burned domain (e.g. scripts/resurrect_false_positive_kills.py)
-- should NULL qualifies_for_cancellation_at + reason for affected domains.
-- A NULL verdict reads correctly through the change tracker as "no, we did
-- not justify this cancellation" — so leaving it unwired is non-fatal; it
-- just gives the operator the cleanup-or-not call when reverting.
--
-- Safe to re-run: CREATE OR REPLACE FUNCTION is idempotent.

BEGIN;

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
    v_old_pool VARCHAR;
    v_promoted_id UUID;
    v_promoted_name VARCHAR;
BEGIN
    -- Get workspace and current pool status
    SELECT workspace_id, domain_name, pool_status
    INTO v_workspace_id, v_burned_name, v_old_pool
    FROM domains WHERE id = p_domain_id;

    -- Burn the domain (live OR reserve), AND persist the verdict
    -- (DECISION 6: qualifies_for_cancellation_* lets the change tracker
    -- label HT cancellations as justified or unjustified — see header).
    UPDATE domains
    SET
        pool_status = 'burned',
        burned_at = NOW(),
        burn_trigger = p_trigger_type,
        qualifies_for_cancellation_at = NOW(),
        qualifies_for_cancellation_reason = p_trigger_type
    WHERE id = p_domain_id
    AND pool_status IN ('live', 'reserve');

    IF NOT FOUND THEN
        RETURN QUERY SELECT
            p_domain_id,
            v_burned_name,
            NULL::UUID,
            NULL::VARCHAR,
            'not_burnable'::VARCHAR;
        RETURN;
    END IF;

    -- Log the burn
    INSERT INTO domain_pool_history (domain_id, old_status, new_status, reason, trigger_type)
    VALUES (p_domain_id, v_old_pool, 'burned', 'domain_burned', p_trigger_type);

    -- Only promote a replacement when burning a LIVE domain.
    -- Burning a reserve domain does not require replacement — it was backup inventory.
    IF v_old_pool != 'live' THEN
        RETURN QUERY SELECT
            p_domain_id,
            v_burned_name,
            NULL::UUID,
            NULL::VARCHAR,
            'burned_reserve'::VARCHAR;
        RETURN;
    END IF;

    -- Find healthiest reserve domain to promote.
    -- Health gate: complaint rate below flagged threshold AND not in dead/monitoring state.
    -- If all reserves are compromised, return 'no_reserve' — better to have no
    -- replacement than to promote a domain that will immediately trigger another burn.
    SELECT id, domain_name INTO v_promoted_id, v_promoted_name
    FROM domains
    WHERE workspace_id = v_workspace_id
    AND pool_status = 'reserve'
    AND is_active = TRUE
    AND COALESCE(domain_complaint_rate_7d, 0) < 0.003
    AND domain_state NOT IN ('dead', 'monitoring')
    ORDER BY pool_assigned_at ASC  -- Oldest reserve first
    LIMIT 1;

    IF v_promoted_id IS NOT NULL THEN
        -- Promote reserve to live
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
        -- No healthy reserve available
        RETURN QUERY SELECT
            p_domain_id,
            v_burned_name,
            NULL::UUID,
            NULL::VARCHAR,
            'no_reserve'::VARCHAR;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMIT;
