-- Migration 010: Add infrastructure_type to domains
-- Tracks whether domain uses Entra (Microsoft 365) or Google Workspace infrastructure

-- Add infrastructure_type column
ALTER TABLE domains ADD COLUMN IF NOT EXISTS infrastructure_type VARCHAR(20);
-- Valid values: 'entra', 'google', NULL (not yet provisioned)

-- Add timestamp for when infrastructure was provisioned
ALTER TABLE domains ADD COLUMN IF NOT EXISTS infrastructure_set_at TIMESTAMP;

-- Index for efficient querying by workspace and infrastructure type
CREATE INDEX IF NOT EXISTS idx_domains_infrastructure
ON domains(workspace_id, infrastructure_type)
WHERE infrastructure_type IS NOT NULL;
