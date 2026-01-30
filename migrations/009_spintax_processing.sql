-- Migration: 009_spintax_processing.sql
-- Purpose: Add spintax processing jobs table and spintaxed content column
-- Date: 2026-01-22

-- Spintax processing jobs table
-- Tracks jobs for applying spintax/liquid syntax to approved sequences
CREATE TABLE IF NOT EXISTS spintax_processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequence_id UUID NOT NULL REFERENCES strategy_suggestions(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id),
    status VARCHAR(50) DEFAULT 'pending',
    -- Status values: pending, processing, completed, failed
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Indexes for efficient job polling and lookups
CREATE INDEX IF NOT EXISTS idx_spintax_jobs_status
    ON spintax_processing_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_spintax_jobs_sequence
    ON spintax_processing_jobs(sequence_id);
CREATE INDEX IF NOT EXISTS idx_spintax_jobs_client
    ON spintax_processing_jobs(client_id);

-- Add column for spintaxed sequence content (parallel to sequence_data)
-- Stores the transformed emails with spintax patterns and liquid syntax
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS spintaxed_sequence_data JSONB;

-- Comment on the new column
COMMENT ON COLUMN strategy_suggestions.spintaxed_sequence_data IS
    'Spintaxed version of sequence_data with variation patterns and liquid syntax applied';
