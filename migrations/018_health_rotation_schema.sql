-- Migration: 018_health_rotation_schema.sql
-- Purpose: Add health metrics columns and rotation tracking tables
-- Date: 2026-02-10

-- =============================================================
-- SENDER_ACCOUNTS: Health metrics columns
-- =============================================================

-- Core health state
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS inbox_state VARCHAR(20) DEFAULT 'live';

-- Bounce metrics (populated by EmailBison sync)
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS hard_bounces_24h INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS hard_bounces_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS total_sends_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS bounce_rate_7d DECIMAL(5,2) DEFAULT 0;

-- Health score (0-100)
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS health_score INTEGER DEFAULT 100;

-- EmailBison integration
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS emailbison_account_id VARCHAR(100);
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP;

-- Kill tracking
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS killed_at TIMESTAMP;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS kill_trigger VARCHAR(50);
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS kill_reason TEXT;

-- Pool tier for rotation (primary, hot_backup, warming, retired)
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS pool_tier VARCHAR(20) DEFAULT 'primary';

-- Indexes for health queries
CREATE INDEX IF NOT EXISTS idx_sender_accounts_inbox_state ON sender_accounts(inbox_state);
CREATE INDEX IF NOT EXISTS idx_sender_accounts_pool_tier ON sender_accounts(pool_tier);
CREATE INDEX IF NOT EXISTS idx_sender_accounts_health_score ON sender_accounts(health_score);
CREATE INDEX IF NOT EXISTS idx_sender_accounts_workspace_state ON sender_accounts(workspace_id, inbox_state);

-- =============================================================
-- DOMAINS: Health metrics columns
-- =============================================================

ALTER TABLE domains ADD COLUMN IF NOT EXISTS latest_health_score INTEGER DEFAULT 100;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS latest_blacklist_count INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS is_clean BOOLEAN DEFAULT TRUE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMP;

-- Indexes for domain health
CREATE INDEX IF NOT EXISTS idx_domains_health ON domains(workspace_id, is_clean, latest_health_score);

-- =============================================================
-- KILL_TRIGGER_EVENTS: Historical kill tracking
-- =============================================================

CREATE TABLE IF NOT EXISTS kill_trigger_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    inbox_id UUID REFERENCES sender_accounts(id) ON DELETE SET NULL,
    inbox_email VARCHAR(255) NOT NULL,
    domain_id UUID REFERENCES domains(id) ON DELETE SET NULL,
    domain_name VARCHAR(255),

    -- Trigger details
    trigger_type VARCHAR(50) NOT NULL,  -- hard_bounces_24h, bounce_rate_7d, fresh_inbox_bounce, etc.
    severity VARCHAR(20) NOT NULL,       -- instant, confirming
    value DECIMAL(10,4) NOT NULL,        -- Actual value that triggered
    threshold DECIMAL(10,4) NOT NULL,    -- Threshold that was exceeded

    -- Timestamps
    detected_at TIMESTAMP DEFAULT NOW(),
    retest_at TIMESTAMP,                 -- For confirming triggers
    resolved_at TIMESTAMP,

    -- Resolution
    action_taken VARCHAR(20) DEFAULT 'pending',  -- pending, killed, dismissed
    resolved_by VARCHAR(100),            -- 'system' or user email
    notes TEXT,

    -- Attribution
    campaign_id UUID,
    campaign_name VARCHAR(255),

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kill_events_workspace ON kill_trigger_events(workspace_id);
CREATE INDEX IF NOT EXISTS idx_kill_events_inbox ON kill_trigger_events(inbox_id);
CREATE INDEX IF NOT EXISTS idx_kill_events_detected ON kill_trigger_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_kill_events_action ON kill_trigger_events(action_taken);
CREATE INDEX IF NOT EXISTS idx_kill_events_pending ON kill_trigger_events(workspace_id, action_taken) WHERE action_taken = 'pending';

-- =============================================================
-- INBOX_HEALTH_SNAPSHOTS: Time-series health data
-- =============================================================

CREATE TABLE IF NOT EXISTS inbox_health_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id),

    -- Snapshot timestamp
    snapshot_timestamp TIMESTAMP DEFAULT NOW(),

    -- Metrics at this point in time
    health_score INTEGER,
    hard_bounces_24h INTEGER DEFAULT 0,
    hard_bounces_7d INTEGER DEFAULT 0,
    total_sends_24h INTEGER DEFAULT 0,
    total_sends_7d INTEGER DEFAULT 0,
    bounce_rate_7d DECIMAL(5,2) DEFAULT 0,

    -- Placement metrics (if available)
    inbox_placement_rate DECIMAL(5,2),
    spam_placement_rate DECIMAL(5,2),

    -- Warmup status
    warmup_enabled BOOLEAN DEFAULT FALSE,
    warmup_score INTEGER,

    -- Connection status
    connection_status VARCHAR(20),  -- connected, disconnected

    -- Data source
    source VARCHAR(20) DEFAULT 'emailbison'  -- emailbison, rbl, manual
);

CREATE INDEX IF NOT EXISTS idx_health_snapshots_inbox ON inbox_health_snapshots(inbox_id, snapshot_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_health_snapshots_workspace ON inbox_health_snapshots(workspace_id, snapshot_timestamp DESC);

-- =============================================================
-- INBOX_ROTATION_HISTORY: Rotation audit log
-- =============================================================

CREATE TABLE IF NOT EXISTS inbox_rotation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),

    -- Rotation type
    rotation_type VARCHAR(20) NOT NULL,  -- swap, promote, demote, retire

    -- Source inbox (being rotated out)
    source_inbox_id UUID REFERENCES sender_accounts(id) ON DELETE SET NULL,
    source_inbox_email VARCHAR(255),
    source_pool VARCHAR(20),

    -- Target inbox (being rotated in)
    target_inbox_id UUID REFERENCES sender_accounts(id) ON DELETE SET NULL,
    target_inbox_email VARCHAR(255),
    target_pool VARCHAR(20),

    -- Context
    reason TEXT,
    triggered_by VARCHAR(100),  -- 'system', 'kill_trigger', 'manual', user email

    -- Campaigns affected
    campaign_ids UUID[],

    -- Execution details
    executed_at TIMESTAMP DEFAULT NOW(),
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_rotation_history_workspace ON inbox_rotation_history(workspace_id, executed_at DESC);
CREATE INDEX IF NOT EXISTS idx_rotation_history_source ON inbox_rotation_history(source_inbox_id);
CREATE INDEX IF NOT EXISTS idx_rotation_history_target ON inbox_rotation_history(target_inbox_id);

-- =============================================================
-- COMMENTS
-- =============================================================

COMMENT ON COLUMN sender_accounts.inbox_state IS 'Current state: live, dead';
COMMENT ON COLUMN sender_accounts.pool_tier IS 'Rotation pool: primary (active sending), hot_backup (warmed, ready), warming (in warmup), retired (dead/rotated out)';
COMMENT ON COLUMN sender_accounts.kill_trigger IS 'The trigger type that caused the kill (e.g., hard_bounces_24h)';
COMMENT ON TABLE kill_trigger_events IS 'Tracks all detected kill triggers and their resolution status';
COMMENT ON TABLE inbox_health_snapshots IS 'Time-series health data for trending analysis';
COMMENT ON TABLE inbox_rotation_history IS 'Audit log of all inbox rotation events';

-- Done!
SELECT 'Migration 018_health_rotation_schema complete' AS status;
