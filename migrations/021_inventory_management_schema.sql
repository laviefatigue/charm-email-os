-- Migration: 021_inventory_management_schema.sql
-- Purpose: Add inventory pool status tracking, auto-kill feature flag, and audit logging
-- Date: 2026-02-12

-- =============================================================
-- 1. INVENTORY STATUS COLUMNS ON SENDER_ACCOUNTS
-- =============================================================

-- Pool status: where inbox is in the inventory flow
-- Values: 'deployed' (in active campaigns), 'warning' (needs cooldown), 'reserve' (ready pool)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS inventory_pool_status VARCHAR(20) DEFAULT 'reserve';

-- Lifecycle status: maturity of the inbox
-- Values: 'active' (mature, healthy), 'incubating' (in warmup), 'dead' (killed)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS inventory_lifecycle_status VARCHAR(20) DEFAULT 'incubating';

-- Warning/cooldown tracking
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS warning_started_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS warning_reason TEXT;

ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS cooldown_ends_at TIMESTAMP WITH TIME ZONE;

-- Index for inventory queries
CREATE INDEX IF NOT EXISTS idx_sender_accounts_inventory
ON sender_accounts(workspace_id, inventory_pool_status, inventory_lifecycle_status);

CREATE INDEX IF NOT EXISTS idx_sender_accounts_inventory_pool
ON sender_accounts(inventory_pool_status) WHERE inbox_state = 'live';

-- =============================================================
-- 2. FEATURE FLAGS TABLE
-- =============================================================

CREATE TABLE IF NOT EXISTS feature_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
    flag_name VARCHAR(100) NOT NULL,
    flag_value BOOLEAN DEFAULT FALSE,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT unique_flag_per_scope UNIQUE (workspace_id, client_id, flag_name)
);

-- Index for flag lookups
CREATE INDEX IF NOT EXISTS idx_feature_flags_lookup
ON feature_flags(flag_name, workspace_id, client_id);

-- Insert default AUTO_KILL flag (disabled by default, global)
INSERT INTO feature_flags (workspace_id, client_id, flag_name, flag_value, config)
VALUES (NULL, NULL, 'AUTO_KILL_ENABLED', FALSE, '{"cooldown_hours": 48, "auto_replace": true, "notify_on_kill": true}')
ON CONFLICT (workspace_id, client_id, flag_name) DO NOTHING;

-- =============================================================
-- 3. KILL TRIGGER EVENTS - Add campaign attribution columns
-- =============================================================

ALTER TABLE kill_trigger_events
ADD COLUMN IF NOT EXISTS associated_campaign_ids UUID[];

ALTER TABLE kill_trigger_events
ADD COLUMN IF NOT EXISTS replacement_inbox_id UUID REFERENCES sender_accounts(id) ON DELETE SET NULL;

ALTER TABLE kill_trigger_events
ADD COLUMN IF NOT EXISTS auto_killed BOOLEAN DEFAULT FALSE;

ALTER TABLE kill_trigger_events
ADD COLUMN IF NOT EXISTS processing_status VARCHAR(20) DEFAULT 'pending';

-- =============================================================
-- 4. INVENTORY AUDIT LOG
-- =============================================================

CREATE TABLE IF NOT EXISTS inventory_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,
    inbox_id UUID REFERENCES sender_accounts(id) ON DELETE SET NULL,
    inbox_email VARCHAR(255),

    -- Event type: pool_change, lifecycle_change, auto_kill, manual_kill, replacement, cooldown_start, cooldown_end
    event_type VARCHAR(50) NOT NULL,

    -- Before/after states
    previous_pool_status VARCHAR(20),
    new_pool_status VARCHAR(20),
    previous_lifecycle_status VARCHAR(20),
    new_lifecycle_status VARCHAR(20),

    -- Context
    reason TEXT,
    triggered_by VARCHAR(100),  -- 'system', 'auto_kill', user email
    related_campaign_ids UUID[],
    replacement_for_inbox_id UUID,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inventory_audit_workspace
ON inventory_audit_log(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_inventory_audit_inbox
ON inventory_audit_log(inbox_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_inventory_audit_type
ON inventory_audit_log(event_type, created_at DESC);

-- =============================================================
-- 5. VIEW: Calculate inventory status in real-time
-- =============================================================

CREATE OR REPLACE VIEW v_inbox_inventory_status AS
SELECT
    sa.id,
    sa.email_address,
    sa.workspace_id,
    sa.inbox_state,
    sa.pool_tier,
    sa.health_score,
    sa.hard_bounces_24h,
    sa.hard_bounces_7d,
    sa.total_sends_7d,
    sa.created_at,

    -- Lifecycle status calculation:
    -- dead = inbox_state is dead
    -- incubating = < 14 days old OR on warming domain
    -- active = everything else
    CASE
        WHEN sa.inbox_state = 'dead' THEN 'dead'
        WHEN sa.created_at > NOW() - INTERVAL '14 days' THEN 'incubating'
        WHEN d.approval_status = 'warming' THEN 'incubating'
        ELSE 'active'
    END as calculated_lifecycle_status,

    -- Pool status calculation:
    -- null = dead inbox
    -- warning = has bounces (1+ in 24h OR 3+ in 7d)
    -- deployed = in active campaigns
    -- reserve = everything else (ready pool)
    CASE
        WHEN sa.inbox_state = 'dead' THEN NULL
        WHEN COALESCE(sa.hard_bounces_24h, 0) >= 1
             OR COALESCE(sa.hard_bounces_7d, 0) >= 3 THEN 'warning'
        WHEN EXISTS (
            SELECT 1 FROM campaign_inboxes ci
            WHERE ci.sender_account_id = sa.id
            AND ci.is_active = TRUE
        ) THEN 'deployed'
        ELSE 'reserve'
    END as calculated_pool_status,

    -- Associated campaigns (for deployed inboxes)
    (
        SELECT ARRAY_AGG(DISTINCT ci.campaign_id)
        FROM campaign_inboxes ci
        WHERE ci.sender_account_id = sa.id
        AND ci.is_active = TRUE
        AND ci.campaign_id IS NOT NULL
    ) as associated_campaign_ids,

    -- Age in days
    EXTRACT(DAY FROM NOW() - sa.created_at)::INTEGER as age_days,

    -- Domain info
    SPLIT_PART(sa.email_address, '@', 2) as domain_name,
    d.approval_status as domain_status,
    d.latest_health_score as domain_health_score

FROM sender_accounts sa
LEFT JOIN domains d ON SPLIT_PART(sa.email_address, '@', 2) = d.domain_name
    AND sa.workspace_id = d.workspace_id;

COMMENT ON VIEW v_inbox_inventory_status IS
'Real-time inventory status view with calculated pool and lifecycle statuses based on bounces, age, and campaign assignments';

-- =============================================================
-- 6. FUNCTION: Update inventory status and log changes
-- =============================================================

CREATE OR REPLACE FUNCTION update_inventory_status(
    p_inbox_id UUID,
    p_new_pool_status VARCHAR(20),
    p_new_lifecycle_status VARCHAR(20),
    p_reason TEXT DEFAULT NULL,
    p_triggered_by VARCHAR(100) DEFAULT 'system'
)
RETURNS void AS $$
DECLARE
    v_old_pool VARCHAR(20);
    v_old_lifecycle VARCHAR(20);
    v_workspace_id UUID;
    v_inbox_email VARCHAR(255);
BEGIN
    -- Get current values
    SELECT inventory_pool_status, inventory_lifecycle_status, workspace_id, email_address
    INTO v_old_pool, v_old_lifecycle, v_workspace_id, v_inbox_email
    FROM sender_accounts
    WHERE id = p_inbox_id;

    -- Update if changed
    IF v_old_pool IS DISTINCT FROM p_new_pool_status
       OR v_old_lifecycle IS DISTINCT FROM p_new_lifecycle_status THEN

        -- Update the record
        UPDATE sender_accounts
        SET inventory_pool_status = p_new_pool_status,
            inventory_lifecycle_status = p_new_lifecycle_status,
            updated_at = NOW()
        WHERE id = p_inbox_id;

        -- Log the change
        INSERT INTO inventory_audit_log (
            workspace_id, inbox_id, inbox_email, event_type,
            previous_pool_status, new_pool_status,
            previous_lifecycle_status, new_lifecycle_status,
            reason, triggered_by
        ) VALUES (
            v_workspace_id, p_inbox_id, v_inbox_email,
            CASE
                WHEN p_new_lifecycle_status = 'dead' THEN 'manual_kill'
                WHEN p_new_pool_status = 'warning' THEN 'cooldown_start'
                WHEN v_old_pool = 'warning' AND p_new_pool_status != 'warning' THEN 'cooldown_end'
                ELSE 'pool_change'
            END,
            v_old_pool, p_new_pool_status,
            v_old_lifecycle, p_new_lifecycle_status,
            p_reason, p_triggered_by
        );
    END IF;
END;
$$ LANGUAGE plpgsql;

-- =============================================================
-- 7. INITIALIZE EXISTING INBOXES WITH CALCULATED STATUSES
-- =============================================================

-- Set lifecycle status based on age and state
UPDATE sender_accounts
SET inventory_lifecycle_status = CASE
    WHEN inbox_state = 'dead' THEN 'dead'
    WHEN created_at > NOW() - INTERVAL '14 days' THEN 'incubating'
    ELSE 'active'
END
WHERE inventory_lifecycle_status IS NULL OR inventory_lifecycle_status = 'incubating';

-- Set pool status based on bounces and campaign assignment
UPDATE sender_accounts sa
SET inventory_pool_status = CASE
    WHEN sa.inbox_state = 'dead' THEN NULL
    WHEN COALESCE(sa.hard_bounces_24h, 0) >= 1 OR COALESCE(sa.hard_bounces_7d, 0) >= 3 THEN 'warning'
    WHEN EXISTS (SELECT 1 FROM campaign_inboxes ci WHERE ci.sender_account_id = sa.id AND ci.is_active) THEN 'deployed'
    ELSE 'reserve'
END
WHERE sa.inbox_state = 'live';

-- =============================================================
-- COMMENTS
-- =============================================================

COMMENT ON COLUMN sender_accounts.inventory_pool_status IS 'Pool status: deployed (in campaigns), warning (needs cooldown), reserve (ready pool)';
COMMENT ON COLUMN sender_accounts.inventory_lifecycle_status IS 'Lifecycle status: active (mature), incubating (warmup), dead (killed)';
COMMENT ON COLUMN sender_accounts.warning_started_at IS 'When inbox entered warning status';
COMMENT ON COLUMN sender_accounts.cooldown_ends_at IS 'When cooldown period ends and inbox can return to reserve';
COMMENT ON TABLE feature_flags IS 'Feature flags for controlling system behavior (e.g., AUTO_KILL_ENABLED)';
COMMENT ON TABLE inventory_audit_log IS 'Audit trail of all inventory status changes';

-- Done!
SELECT 'Migration 021_inventory_management_schema complete' AS status;
