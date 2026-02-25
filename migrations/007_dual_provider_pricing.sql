-- Phase 3: Dual Provider Pricing Support
-- Adds columns for Porkbun + Dynadot pricing comparison

-- Add provider-specific pricing columns to domains table
ALTER TABLE domains ADD COLUMN IF NOT EXISTS porkbun_price DECIMAL(10,2);
ALTER TABLE domains ADD COLUMN IF NOT EXISTS porkbun_available BOOLEAN;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dynadot_price DECIMAL(10,2);
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dynadot_available BOOLEAN;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS selected_provider VARCHAR(20);
ALTER TABLE domains ADD COLUMN IF NOT EXISTS job_id UUID;

-- Create purchase queue table for safe batch purchasing
CREATE TABLE IF NOT EXISTS domain_purchase_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    provider VARCHAR(20) NOT NULL,
    expected_price DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,
    CONSTRAINT valid_provider CHECK (provider IN ('porkbun', 'dynadot'))
);

-- Index for efficient queue polling
CREATE INDEX IF NOT EXISTS idx_purchase_queue_status ON domain_purchase_queue(status, created_at);

-- Index for domain lookup by job
CREATE INDEX IF NOT EXISTS idx_domains_job_id ON domains(job_id);
