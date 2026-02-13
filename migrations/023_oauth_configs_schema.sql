-- Migration: 023_oauth_configs_schema.sql
-- Purpose: Store OAuth configuration scraped from EmailBison UI
-- Author: Claude Code
-- Date: 2026-02-12

-- OAuth configurations table
-- Stores Google (and future Microsoft) OAuth Client IDs per workspace
CREATE TABLE IF NOT EXISTS oauth_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,

    -- Google OAuth
    google_client_id VARCHAR(255),
    google_app_name VARCHAR(100),

    -- Microsoft OAuth (future use)
    microsoft_client_id VARCHAR(255),
    microsoft_app_name VARCHAR(100),

    -- Verification tracking
    last_verified_at TIMESTAMP WITH TIME ZONE,
    verification_status VARCHAR(20) DEFAULT 'pending',  -- pending, verified, changed, error
    previous_google_client_id VARCHAR(255),  -- Track changes for alerting

    -- Timestamps
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT uq_oauth_configs_workspace UNIQUE(workspace_id)
);

-- Index for workspace lookups
CREATE INDEX IF NOT EXISTS idx_oauth_configs_workspace
    ON oauth_configs(workspace_id);

-- Index for verification status queries (monthly verification job)
CREATE INDEX IF NOT EXISTS idx_oauth_configs_verification
    ON oauth_configs(verification_status, last_verified_at);


-- OAuth sync queue table
-- Queues workspaces for OAuth config scraping (async processing)
CREATE TABLE IF NOT EXISTS oauth_sync_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    emailbison_workspace_id INTEGER NOT NULL,

    -- Processing status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE,

    -- Prevent duplicate queue entries
    CONSTRAINT uq_oauth_sync_queue_workspace UNIQUE(workspace_id)
);

-- Index for polling pending items
CREATE INDEX IF NOT EXISTS idx_oauth_sync_queue_status
    ON oauth_sync_queue(status, created_at)
    WHERE status IN ('pending', 'failed');

-- Index for workspace lookups
CREATE INDEX IF NOT EXISTS idx_oauth_sync_queue_workspace
    ON oauth_sync_queue(workspace_id);


-- Trigger to update updated_at on oauth_configs
CREATE OR REPLACE FUNCTION update_oauth_configs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_oauth_configs_updated_at ON oauth_configs;
CREATE TRIGGER trg_oauth_configs_updated_at
    BEFORE UPDATE ON oauth_configs
    FOR EACH ROW
    EXECUTE FUNCTION update_oauth_configs_updated_at();


-- Comments for documentation
COMMENT ON TABLE oauth_configs IS 'OAuth configurations (Client IDs) scraped from EmailBison UI per workspace';
COMMENT ON TABLE oauth_sync_queue IS 'Queue for async OAuth config scraping jobs';
COMMENT ON COLUMN oauth_configs.verification_status IS 'pending=never verified, verified=matches last scrape, changed=different from previous, error=scrape failed';
COMMENT ON COLUMN oauth_configs.previous_google_client_id IS 'Stored when Client ID changes, for alerting purposes';
COMMENT ON COLUMN oauth_sync_queue.status IS 'pending=awaiting processing, processing=in progress, completed=done, failed=error after retries';
