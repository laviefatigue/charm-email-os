-- Migration: 026_warmup_tracking_schema.sql
-- Purpose: Add warmup tracking columns and snapshots table
-- Date: 2026-02-13

-- =============================================================
-- 1. SENDER_ACCOUNTS: Warmup tracking columns
-- =============================================================

-- Warmup enabled status (synced from EmailBison)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS warmup_enabled BOOLEAN DEFAULT FALSE;

-- When warmup was first enabled (tracked locally when first seen)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS warmup_started_at TIMESTAMP WITH TIME ZONE;

-- When warmup was disabled (tracked locally when transition detected)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS warmup_stopped_at TIMESTAMP WITH TIME ZONE;

-- When sending started (first campaign assignment after warmup complete)
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS sending_started_at TIMESTAMP WITH TIME ZONE;

-- Index for warmup queries
CREATE INDEX IF NOT EXISTS idx_sender_accounts_warmup
ON sender_accounts (warmup_enabled, warmup_started_at)
WHERE is_active = TRUE;

-- =============================================================
-- 2. SENDER_WARMUP_SNAPSHOTS: Time-series warmup statistics
-- =============================================================

CREATE TABLE IF NOT EXISTS sender_warmup_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sender_account_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,

    -- Snapshot timestamp
    snapshot_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Period covered by this snapshot (from EmailBison API date range)
    period_start TIMESTAMP WITH TIME ZONE,
    period_end TIMESTAMP WITH TIME ZONE,

    -- Warmup status
    warmup_enabled BOOLEAN DEFAULT FALSE,
    warmup_score INTEGER,  -- 0-100 from EmailBison

    -- Warmup metrics
    warmup_emails_sent INTEGER DEFAULT 0,
    warmup_replies_received INTEGER DEFAULT 0,
    warmup_bounces_received_count INTEGER DEFAULT 0,
    warmup_bounces_caused_count INTEGER DEFAULT 0,
    warmup_emails_saved_from_spam INTEGER DEFAULT 0,

    -- Connection status at time of snapshot
    sender_email_status VARCHAR(50),  -- Connected, Not connected, etc.

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for snapshot queries
CREATE INDEX IF NOT EXISTS idx_warmup_snapshots_sender
ON sender_warmup_snapshots(sender_account_id, snapshot_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_warmup_snapshots_timestamp
ON sender_warmup_snapshots(snapshot_timestamp DESC);

-- =============================================================
-- 3. WARMUP_CHECK_RUNS: Audit log for warmup sync runs
-- =============================================================

CREATE TABLE IF NOT EXISTS warmup_check_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL,

    -- Run details
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Results
    accounts_checked INTEGER DEFAULT 0,
    accounts_with_warmup INTEGER DEFAULT 0,
    warmup_enabled_count INTEGER DEFAULT 0,
    warmup_disabled_count INTEGER DEFAULT 0,
    auto_enabled_count INTEGER DEFAULT 0,

    -- Status
    status VARCHAR(20) DEFAULT 'running',  -- running, completed, failed
    error_message TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_warmup_check_runs_workspace
ON warmup_check_runs(workspace_id, started_at DESC);

-- =============================================================
-- 4. COMMENTS
-- =============================================================

COMMENT ON COLUMN sender_accounts.warmup_enabled IS 'Whether warmup is currently enabled in EmailBison';
COMMENT ON COLUMN sender_accounts.warmup_started_at IS 'When warmup was first detected as enabled (tracked locally)';
COMMENT ON COLUMN sender_accounts.warmup_stopped_at IS 'When warmup was detected as disabled (tracked locally)';
COMMENT ON COLUMN sender_accounts.sending_started_at IS 'When inbox was first deployed to a campaign';
COMMENT ON TABLE sender_warmup_snapshots IS 'Time-series warmup statistics from EmailBison API';
COMMENT ON TABLE warmup_check_runs IS 'Audit log of warmup sync runs';

-- =============================================================
-- 5. BACKFILL: Defer to sync worker
-- =============================================================

-- NOTE: Backfill is NOT done here because:
-- 1. warmup_enabled column was just added with DEFAULT FALSE
-- 2. We don't know which accounts actually have warmup enabled until sync runs
-- 3. Setting warmup_started_at without warmup_enabled=TRUE creates inconsistent state
--
-- The sync worker (sync_warmup.py and sync_accounts.py) will:
-- 1. Sync warmup_enabled from EmailBison
-- 2. Set warmup_started_at = first_seen_at + 7 days when warmup first detected
-- 3. Auto-enable warmup for connected inboxes without it
--
-- After first sync completes, warmup_started_at will be populated correctly.

-- Done!
SELECT 'Migration 026_warmup_tracking_schema complete' AS status;
