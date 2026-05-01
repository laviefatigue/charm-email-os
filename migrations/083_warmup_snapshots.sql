-- Migration 083: Warmup snapshots for incubating inbox tracking
--
-- Captures daily warmup metrics for incubating inboxes only.
-- Purpose: Track warmup curves during the 14-day incubation period.
-- After graduation to 'active', tracking stops (kill triggers take over).
-- 30-day retention — old rows purged by retention module.

CREATE TABLE IF NOT EXISTS warmup_snapshots (
    id BIGSERIAL PRIMARY KEY,
    sender_account_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    snapshot_date DATE NOT NULL,

    -- Warmup metrics (from EB API, aggregated over date range)
    warmup_score NUMERIC(6,2),           -- 0-100, EB's composite score
    warmup_emails_sent INTEGER DEFAULT 0, -- Warmup emails sent (cumulative from EB for period)
    warmup_replies_received INTEGER DEFAULT 0,
    warmup_emails_saved_from_spam INTEGER DEFAULT 0,
    warmup_bounces_received INTEGER DEFAULT 0,
    warmup_bounces_caused INTEGER DEFAULT 0,
    warmup_daily_limit INTEGER,           -- Current daily warmup limit

    -- Status flags
    warmup_enabled BOOLEAN NOT NULL DEFAULT TRUE,  -- FALSE = gap day (should self-heal)
    inbox_connected BOOLEAN NOT NULL DEFAULT TRUE,  -- FALSE = disconnected during warmup

    -- Context
    days_since_warmup_start INTEGER,      -- Days into incubation (0-14+)
    emails_sent_all_time INTEGER DEFAULT 0, -- Total sends for context

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One snapshot per inbox per day
    CONSTRAINT warmup_snapshots_unique UNIQUE (sender_account_id, snapshot_date)
);

-- Index for querying warmup curves per inbox
CREATE INDEX IF NOT EXISTS idx_warmup_snapshots_account_date
    ON warmup_snapshots (sender_account_id, snapshot_date);

-- Index for workspace-level warmup dashboard
CREATE INDEX IF NOT EXISTS idx_warmup_snapshots_workspace_date
    ON warmup_snapshots (workspace_id, snapshot_date);

-- Index for retention cleanup
CREATE INDEX IF NOT EXISTS idx_warmup_snapshots_date
    ON warmup_snapshots (snapshot_date);
