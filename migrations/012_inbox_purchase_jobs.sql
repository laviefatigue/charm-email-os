-- Migration 012: Inbox Purchase Jobs
-- Adds persistent storage for inbox purchase jobs with retry capability

-- Create inbox_purchase_jobs table for job persistence
CREATE TABLE IF NOT EXISTS inbox_purchase_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id),

    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending',  -- pending, executing, completed, failed, superseded
    current_step TEXT,

    -- Order metadata
    provider_type VARCHAR(20),  -- 'entra' or 'google'
    domain_ids UUID[],
    domain_names TEXT[],
    entra_orders INTEGER DEFAULT 0,
    google_orders INTEGER DEFAULT 0,
    orders_completed INTEGER DEFAULT 0,
    orders_total INTEGER DEFAULT 0,
    total_inboxes INTEGER DEFAULT 0,
    monthly_cost DECIMAL(10,2),

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Results (JSONB for flexibility)
    results JSONB,  -- Array of {success, orderType, inboxesCreated, error, ...}
    errors TEXT[],  -- Array of error messages

    -- Request data for retry
    request_data JSONB,

    -- Flags
    override_age_check BOOLEAN DEFAULT FALSE,
    custom_purchase BOOLEAN DEFAULT FALSE
);

-- Index for efficient querying by client
CREATE INDEX IF NOT EXISTS idx_purchase_jobs_client ON inbox_purchase_jobs(client_id, created_at DESC);

-- Index for filtering by status
CREATE INDEX IF NOT EXISTS idx_purchase_jobs_status ON inbox_purchase_jobs(status);

-- Index for finding jobs that can be retried
CREATE INDEX IF NOT EXISTS idx_purchase_jobs_retry ON inbox_purchase_jobs(status) WHERE status = 'failed';

-- Comments for documentation
COMMENT ON TABLE inbox_purchase_jobs IS 'Persistent storage for inbox purchase jobs, enabling job history and retry capability';
COMMENT ON COLUMN inbox_purchase_jobs.status IS 'Job status: pending, executing, completed, failed, superseded';
COMMENT ON COLUMN inbox_purchase_jobs.request_data IS 'Original request data stored for retry capability';
COMMENT ON COLUMN inbox_purchase_jobs.results IS 'JSONB array of order results with success/failure details';
