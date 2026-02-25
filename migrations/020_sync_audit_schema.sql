-- Migration: 020_sync_audit_schema.sql
-- Purpose: Schema for EmailBison daily sync application
-- Tables: sync_audit_log, response_messages, kill_queue

-- ============================================================================
-- SYNC AUDIT LOG
-- Tracks every sync operation for debugging and monitoring
-- ============================================================================
CREATE TABLE IF NOT EXISTS sync_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_type VARCHAR(50) NOT NULL,  -- 'accounts', 'campaigns', 'events', 'health', 'kill_queue', 'retention'
    workspace_id UUID REFERENCES workspaces(id),
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',  -- 'running', 'completed', 'failed', 'partial'
    records_processed INTEGER DEFAULT 0,
    records_created INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_message TEXT,
    error_details JSONB,  -- Stack trace, failed record IDs, API errors
    metadata JSONB,  -- Extra context: API response times, pagination info, etc.
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_audit_type_status ON sync_audit_log(sync_type, status);
CREATE INDEX IF NOT EXISTS idx_sync_audit_workspace ON sync_audit_log(workspace_id);
CREATE INDEX IF NOT EXISTS idx_sync_audit_started ON sync_audit_log(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_audit_retention ON sync_audit_log(started_at);

-- ============================================================================
-- RESPONSE MESSAGES
-- Stores actual reply/bounce content for campaign copy analysis
-- ============================================================================
CREATE TABLE IF NOT EXISTS response_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_event_id UUID REFERENCES campaign_events(id),
    campaign_id UUID REFERENCES emailbison_campaigns(id),
    workspace_id UUID REFERENCES workspaces(id),
    emailbison_reply_id INTEGER,

    -- Message metadata
    folder VARCHAR(20) NOT NULL,  -- 'inbox', 'bounced', 'spam'
    from_email VARCHAR(255),
    from_name VARCHAR(255),
    to_inbox_email VARCHAR(255),  -- Which sender inbox received this
    sender_account_id UUID REFERENCES sender_accounts(id),

    -- Message content
    subject TEXT,
    body_preview TEXT,  -- First 500 chars for quick scanning
    body_full TEXT,     -- Complete message for analysis

    -- Timestamps
    received_at TIMESTAMP,
    processed_at TIMESTAMP DEFAULT NOW(),

    -- Classification
    is_interested BOOLEAN DEFAULT FALSE,
    is_automated BOOLEAN DEFAULT FALSE,  -- Auto-reply detection
    sentiment VARCHAR(20),  -- 'positive', 'negative', 'neutral', 'out_of_office'

    -- Bounce-specific fields (only for folder='bounced')
    bounce_type VARCHAR(50),  -- 'hard_unknown', 'hard_blocked', 'soft_full', 'soft_temp'
    bounce_reason TEXT,       -- Raw bounce reason from ESP

    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(emailbison_reply_id, campaign_id)
);

CREATE INDEX IF NOT EXISTS idx_response_campaign ON response_messages(campaign_id);
CREATE INDEX IF NOT EXISTS idx_response_workspace ON response_messages(workspace_id);
CREATE INDEX IF NOT EXISTS idx_response_folder ON response_messages(folder);
CREATE INDEX IF NOT EXISTS idx_response_received ON response_messages(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_response_interested ON response_messages(is_interested) WHERE is_interested = TRUE;
CREATE INDEX IF NOT EXISTS idx_response_bounce_type ON response_messages(bounce_type) WHERE folder = 'bounced';
-- Retention index for bounces only (non-bounces kept indefinitely)
CREATE INDEX IF NOT EXISTS idx_response_bounce_retention ON response_messages(received_at) WHERE folder = 'bounced';

-- ============================================================================
-- KILL QUEUE
-- Tracks inboxes queued for deletion with 24hr waiting period
-- ============================================================================
CREATE TABLE IF NOT EXISTS kill_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),

    -- Trigger info
    trigger_type VARCHAR(50) NOT NULL,  -- 'hard_bounces_24h', 'bounce_rate_7d', 'fresh_inbox_bounce', etc.
    trigger_value DECIMAL(10,4),         -- Actual value that triggered
    trigger_threshold DECIMAL(10,4),     -- Threshold that was exceeded

    -- Queue timestamps
    queued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    tagged_at TIMESTAMP,                 -- When EmailBison tag was applied
    tag_name VARCHAR(100),               -- e.g., 'delete_queue_20260211'
    scheduled_delete_at TIMESTAMP,       -- 24hrs after tagged_at
    deleted_at TIMESTAMP,

    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'tagged', 'deleted', 'cancelled', 'failed'
    error_message TEXT,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_kill_queue_status ON kill_queue(status);
CREATE INDEX IF NOT EXISTS idx_kill_queue_inbox ON kill_queue(inbox_id);
CREATE INDEX IF NOT EXISTS idx_kill_queue_workspace ON kill_queue(workspace_id);
CREATE INDEX IF NOT EXISTS idx_kill_queue_scheduled ON kill_queue(scheduled_delete_at) WHERE status = 'tagged';
CREATE INDEX IF NOT EXISTS idx_kill_queue_retention ON kill_queue(created_at) WHERE status IN ('deleted', 'cancelled');

-- ============================================================================
-- SYNC STATUS TABLE
-- Tracks last successful sync time per workspace/type for incremental sync
-- ============================================================================
CREATE TABLE IF NOT EXISTS sync_status (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID REFERENCES workspaces(id),
    sync_type VARCHAR(50) NOT NULL,  -- 'accounts', 'campaigns', 'events'
    last_successful_sync TIMESTAMP,
    last_sync_record_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(workspace_id, sync_type)
);

CREATE INDEX IF NOT EXISTS idx_sync_status_lookup ON sync_status(workspace_id, sync_type);

-- ============================================================================
-- COMMENTS
-- ============================================================================
COMMENT ON TABLE sync_audit_log IS 'Tracks every sync operation for debugging and monitoring';
COMMENT ON TABLE response_messages IS 'Stores reply/bounce content for campaign analysis. Non-bounce messages retained indefinitely.';
COMMENT ON TABLE kill_queue IS 'Tracks inboxes queued for deletion with 24hr waiting period';
COMMENT ON TABLE sync_status IS 'Tracks last sync time per workspace for incremental syncing';

COMMENT ON COLUMN response_messages.bounce_type IS 'hard_unknown=bad email, hard_blocked=reputation, soft_full=mailbox full, soft_temp=temporary';
COMMENT ON COLUMN kill_queue.status IS 'pending=waiting to tag, tagged=in 24hr queue, deleted=completed, cancelled=manual override, failed=error';
