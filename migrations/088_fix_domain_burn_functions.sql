-- Migration 088: Fix Domain Burn Functions
--
-- Fixes two critical SQL functions:
--
-- 1. recalculate_domain_complaint_rate(): Changes denominator from
--    SUM(emails_sent_all_time) to COUNT(*) of active inboxes. The old
--    sends-based denominator made Microsoft domains (52 inboxes, thousands
--    of sends) nearly impossible to burn, while Google domains (3 inboxes,
--    low sends) burned instantly from 1 complaint. The rate should be
--    "what % of inboxes on this domain were killed by spam in the last 7 days."
--
-- 2. burn_domain_and_promote(): Allows reserve domain burns (previously
--    only live domains could be burned), adds health check on promotion
--    candidate (prevents promoting a compromised reserve domain).

-- ============================================================================
-- 1. Fix recalculate_domain_complaint_rate — inbox-count denominator
-- ============================================================================
-- OLD: rate = spam_killed_inboxes_7d / emails_sent_all_time   (sends-based)
-- NEW: rate = spam_killed_inboxes_7d / total_active_inboxes    (inbox-count)
--
-- Thresholds designed for inbox-count rates:
--   >= 1.0%  → domain dead (instant burn)
--   >= 0.3%  → domain flagged (enter monitoring)
--   <  0.1%  → healthy
--
-- Examples with new denominator:
--   Google (3 inboxes), 1 spam kill:  1/3 = 33%  → instant burn (correct)
--   Microsoft (52 inboxes), 1 spam kill: 1/52 = 1.9% → rate exceeds 1% but
--     ESP-aware logic in kill_processor.py requires 3+ spam kills for Entra
--     domains before burning → enters monitoring instead (correct)
--   Microsoft (52 inboxes), 3 spam kills: 3/52 = 5.8% → burn (pattern confirmed)
--   Microsoft (52 inboxes), 0 spam kills: 0/52 = 0% → healthy (correct)
--
-- NOTE: This SQL function is ESP-agnostic — it only calculates the rate.
-- ESP-aware burn decisions (Google=1 kill, Entra=3 kills) are enforced in
-- kill_processor.py using ESP_BURN_MIN_COMPLAINTS thresholds.

CREATE OR REPLACE FUNCTION recalculate_domain_complaint_rate(p_domain_id UUID)
RETURNS VOID AS $$
DECLARE
    v_complaints_7d INTEGER;
    v_total_inboxes INTEGER;
    v_rate DECIMAL(8,6);
BEGIN
    SELECT
        COALESCE(
            COUNT(*) FILTER (WHERE inbox_state = 'dead'
                AND kill_trigger = 'spam_complaint'
                AND killed_at >= NOW() - INTERVAL '7 days'),
            0
        ),
        COUNT(*)
    INTO v_complaints_7d, v_total_inboxes
    FROM sender_accounts
    WHERE domain_id = p_domain_id
      AND is_active = TRUE;

    -- Calculate rate (avoid division by zero)
    IF v_total_inboxes > 0 THEN
        v_rate := v_complaints_7d::DECIMAL / v_total_inboxes;
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
-- 2. Fix burn_domain_and_promote — reserve burns + promotion health gate
-- ============================================================================
-- Changes from original (migration 076):
--   a) pool_status IN ('live', 'reserve') instead of = 'live'
--   b) Reserve burns return 'burned_reserve' action (no promotion needed)
--   c) Promotion candidate must pass health check:
--      - domain_complaint_rate_7d < 0.003 (below flagged threshold)
--      - domain_state NOT IN ('dead', 'monitoring')
--   d) If no healthy reserve available, returns 'no_reserve' (Slack alert fires)

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

    -- Burn the domain (live OR reserve)
    UPDATE domains
    SET
        pool_status = 'burned',
        burned_at = NOW(),
        burn_trigger = p_trigger_type
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

-- ============================================================================
-- 3. Backfill: Recalculate all complaint rates with new inbox-count denominator
-- ============================================================================
DO $$
DECLARE
    v_ws RECORD;
    v_count INTEGER;
BEGIN
    FOR v_ws IN SELECT DISTINCT id FROM workspaces WHERE is_active = TRUE
    LOOP
        SELECT recalculate_all_domain_complaint_rates(v_ws.id) INTO v_count;
        RAISE NOTICE 'Workspace %: recalculated % domains', v_ws.id, v_count;
    END LOOP;
END;
$$;
