-- Migration: 019_phased_generation.sql
-- Purpose: Enable phased strategy generation (scaffold + 4 campaign phases)
-- Solves: Single-run timeout issue when generating 4 campaigns (~15+ min)
-- Architecture: Scaffold phase creates ICP/variables/stubs, then 4 parallel campaign phases generate emails

-- 1. Create phases tracking table
CREATE TABLE IF NOT EXISTS strategy_generation_phases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id) ON DELETE CASCADE,

    -- Phase type: 'scaffold' (creates ICP, variables, campaign stubs) or 'campaign_copy' (generates emails)
    phase_type VARCHAR(50) NOT NULL CHECK (phase_type IN ('scaffold', 'campaign_copy')),

    -- Phase number: NULL for scaffold, 1-4 for campaign_copy phases
    phase_number INTEGER CHECK (phase_number IS NULL OR phase_number BETWEEN 1 AND 4),

    -- Link to campaign document (for campaign_copy phases)
    campaign_document_id UUID REFERENCES campaign_documents(id) ON DELETE SET NULL,

    -- Phase status: pending -> processing -> completed | failed
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),

    -- Error tracking
    error_message TEXT,

    -- Timing
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),

    -- Ensure unique phase per job (one scaffold, one of each campaign number)
    UNIQUE(parent_job_id, phase_type, phase_number)
);

-- Index for worker polling (find pending phases efficiently)
CREATE INDEX IF NOT EXISTS idx_phases_pending ON strategy_generation_phases(status, phase_type, created_at)
WHERE status = 'pending';

-- Index for looking up phases by parent job
CREATE INDEX IF NOT EXISTS idx_phases_parent ON strategy_generation_phases(parent_job_id);

-- Index for looking up phase by campaign document
CREATE INDEX IF NOT EXISTS idx_phases_campaign_doc ON strategy_generation_phases(campaign_document_id)
WHERE campaign_document_id IS NOT NULL;

COMMENT ON TABLE strategy_generation_phases IS 'Tracks individual phases of a phased generation job (scaffold + 4 campaigns)';
COMMENT ON COLUMN strategy_generation_phases.phase_type IS 'scaffold = ICP/variables/stubs, campaign_copy = generate emails for one campaign';
COMMENT ON COLUMN strategy_generation_phases.phase_number IS 'Campaign number (1-4) for campaign_copy phases, NULL for scaffold';


-- 2. Extend strategy_generation_jobs for phased generation
-- Add job_type to distinguish full vs scaffold vs campaign jobs
ALTER TABLE strategy_generation_jobs
ADD COLUMN IF NOT EXISTS job_type VARCHAR(20) DEFAULT 'full' CHECK (job_type IN ('full', 'scaffold', 'campaign'));

-- Add parent_job_id for child jobs (optional - phases table handles this, but useful for querying)
ALTER TABLE strategy_generation_jobs
ADD COLUMN IF NOT EXISTS parent_job_id UUID REFERENCES strategy_generation_jobs(id) ON DELETE CASCADE;

-- Add campaign_number for campaign-specific jobs
ALTER TABLE strategy_generation_jobs
ADD COLUMN IF NOT EXISTS campaign_number INTEGER CHECK (campaign_number IS NULL OR campaign_number BETWEEN 1 AND 4);

-- Add cycle_id to track which cycle this job is generating for
ALTER TABLE strategy_generation_jobs
ADD COLUMN IF NOT EXISTS cycle_id UUID REFERENCES campaign_cycles(id) ON DELETE SET NULL;

-- Index for finding child jobs
CREATE INDEX IF NOT EXISTS idx_jobs_parent ON strategy_generation_jobs(parent_job_id)
WHERE parent_job_id IS NOT NULL;

-- Index for finding jobs by cycle
CREATE INDEX IF NOT EXISTS idx_jobs_cycle ON strategy_generation_jobs(cycle_id)
WHERE cycle_id IS NOT NULL;

COMMENT ON COLUMN strategy_generation_jobs.job_type IS 'full = legacy single run, scaffold = ICP/variables only, campaign = emails for one campaign';
COMMENT ON COLUMN strategy_generation_jobs.parent_job_id IS 'For campaign jobs, references the scaffold job that created the cycle';
COMMENT ON COLUMN strategy_generation_jobs.campaign_number IS 'For campaign jobs, which campaign (1-4) this job generates';
COMMENT ON COLUMN strategy_generation_jobs.cycle_id IS 'The cycle this job is generating content for';


-- 3. Add angle column to campaign_documents (Campaign 1 = Custom Signal, etc.)
ALTER TABLE campaign_documents
ADD COLUMN IF NOT EXISTS angle VARCHAR(50) CHECK (angle IN ('custom_signal', 'persona_pain', 'case_study', 'risk_efficiency'));

COMMENT ON COLUMN campaign_documents.angle IS 'Campaign angle: custom_signal, persona_pain, case_study, or risk_efficiency';


-- 4. Add email_positions JSONB to campaign_documents for storing all email variants
-- This allows saving all emails in one update rather than inserting into document_email_variants
ALTER TABLE campaign_documents
ADD COLUMN IF NOT EXISTS email_positions JSONB;

COMMENT ON COLUMN campaign_documents.email_positions IS 'JSONB array of email positions with variants, for atomic saves during generation';

-- Structure of email_positions:
-- [
--   {
--     "position": 1,
--     "variants": [
--       {
--         "variant_number": 1,
--         "variant_name": "Core Vendor Frustration",
--         "is_recommended": true,
--         "subject_line": "...",
--         "email_body": "...",
--         "word_count": 65,
--         "angle": "custom_signal",
--         "value_prop": "save_time"
--       },
--       { "variant_number": 2, ... }
--     ]
--   },
--   { "position": 2, ... }
-- ]
