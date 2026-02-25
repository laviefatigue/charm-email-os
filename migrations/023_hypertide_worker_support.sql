-- Migration 023: Hypertide Worker Support
-- Extends inbox_purchase_jobs for external worker processing
-- Adds domain_purchase_jobs for registrar purchases (Dynadot/Porkbun)

-- =============================================================================
-- Extend inbox_purchase_jobs for external worker
-- =============================================================================

-- Add worker tracking columns
ALTER TABLE inbox_purchase_jobs
ADD COLUMN IF NOT EXISTS worker_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS worker_started_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS max_retries INTEGER DEFAULT 3,
ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(20) DEFAULT 'background_task';
-- execution_mode: 'background_task' (legacy in-process), 'worker' (external worker)

-- Index for worker to find pending jobs
CREATE INDEX IF NOT EXISTS idx_purchase_jobs_pending_worker
ON inbox_purchase_jobs(status, execution_mode)
WHERE status = 'pending' AND execution_mode = 'worker';

-- Index for worker to reclaim stale jobs (worker crashed during execution)
CREATE INDEX IF NOT EXISTS idx_purchase_jobs_stale
ON inbox_purchase_jobs(worker_started_at, status)
WHERE status = 'executing';

COMMENT ON COLUMN inbox_purchase_jobs.worker_id IS 'ID of worker processing this job (for multi-worker setups)';
COMMENT ON COLUMN inbox_purchase_jobs.execution_mode IS 'background_task=in-process, worker=external hypertide worker';

-- =============================================================================
-- Domain Purchase Jobs (for registrar purchases - Dynadot/Porkbun)
-- =============================================================================

CREATE TABLE IF NOT EXISTS domain_purchase_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES workspaces(id),

    -- Domain selection
    domain_ids UUID[] NOT NULL,
    domain_names TEXT[],
    registrar VARCHAR(20) NOT NULL,  -- 'dynadot' | 'porkbun'

    -- Status tracking
    status VARCHAR(50) DEFAULT 'pending',  -- pending, processing, completed, failed
    current_domain TEXT,  -- Currently processing domain name

    -- Results
    successful_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    total_cost DECIMAL(10,2) DEFAULT 0,
    results JSONB,  -- Per-domain results: [{domain, success, order_id, error, price}]

    -- Worker tracking
    worker_id VARCHAR(100),
    worker_started_at TIMESTAMP WITH TIME ZONE,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Error handling
    error_message TEXT,
    errors TEXT[],

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Index for worker polling
CREATE INDEX IF NOT EXISTS idx_domain_purchase_jobs_pending
ON domain_purchase_jobs(status)
WHERE status = 'pending';

-- Index for client history
CREATE INDEX IF NOT EXISTS idx_domain_purchase_jobs_client
ON domain_purchase_jobs(client_id, created_at DESC);

COMMENT ON TABLE domain_purchase_jobs IS 'Job queue for domain purchases from registrars (Dynadot, Porkbun). Processed by hypertide_worker.';

-- =============================================================================
-- Feature flag for worker mode
-- =============================================================================

INSERT INTO feature_flags (flag_name, flag_value, config)
VALUES (
    'HYPERTIDE_WORKER_MODE',
    FALSE,
    '{"description": "When enabled, inbox purchases are processed by external worker instead of in-process BackgroundTasks"}'
)
ON CONFLICT (flag_name) WHERE workspace_id IS NULL AND client_id IS NULL
DO NOTHING;
