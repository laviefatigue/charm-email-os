-- Domain Sourcing Phase 2 Enhancements
-- Adds columns for inline price checking and purchase tracking

-- Add cached price and timestamps to domains table
ALTER TABLE domains ADD COLUMN IF NOT EXISTS cached_price DECIMAL(10,2);
ALTER TABLE domains ADD COLUMN IF NOT EXISTS price_checked_at TIMESTAMP;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS purchased_at TIMESTAMP;

-- Ensure domain_generation_jobs table exists with all columns
CREATE TABLE IF NOT EXISTS domain_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    count INTEGER DEFAULT 10,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Add index for faster job polling
CREATE INDEX IF NOT EXISTS idx_domain_jobs_status ON domain_generation_jobs(status, created_at);

-- Add index for faster domain status lookups
CREATE INDEX IF NOT EXISTS idx_domains_approval_status ON domains(workspace_id, approval_status);
