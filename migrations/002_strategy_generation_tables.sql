-- Migration: 002_strategy_generation_tables
-- Created: 2026-01-16
-- Purpose: Add tables for AI-powered strategy generation

-- Strategy generation jobs (tracks Claude Code runs)
CREATE TABLE IF NOT EXISTS strategy_generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    submission_id UUID REFERENCES client_onboarding_submissions(id),
    status VARCHAR(50) DEFAULT 'pending',
    -- Status values: pending → processing → review → completed | failed
    generation_round INTEGER DEFAULT 1,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_strategy_jobs_status ON strategy_generation_jobs(status);
CREATE INDEX IF NOT EXISTS idx_strategy_jobs_client ON strategy_generation_jobs(client_id);

-- Individual campaign variants (atomic, independently reviewable)
CREATE TABLE IF NOT EXISTS strategy_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),

    -- Email content
    variant_number INTEGER NOT NULL,  -- 1, 2, or 3
    subject_line TEXT NOT NULL,
    email_body TEXT NOT NULL,

    -- Metadata from skill
    score INTEGER,  -- 0-100 from QA scoring
    rationale TEXT,
    used_variables JSONB,  -- ["{{first_name}}", "{{company_name}}"]
    missing_variables JSONB,
    campaign_type VARCHAR(50),  -- custom_signal, creative_ideas, whole_offer, fallback

    -- Review status
    status VARCHAR(50) DEFAULT 'pending',
    -- Status values: pending, approved, denied, revision_requested
    human_comment TEXT,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP,

    generation_round INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_suggestions_job ON strategy_suggestions(job_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_client ON strategy_suggestions(client_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON strategy_suggestions(status);

-- Revision requests (human feedback for next generation)
CREATE TABLE IF NOT EXISTS strategy_revision_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
    client_id UUID NOT NULL REFERENCES clients(id),
    variant_id UUID REFERENCES strategy_suggestions(id),
    instruction TEXT NOT NULL,  -- "Make it shorter", "Add more proof points"
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_revision_requests_job ON strategy_revision_requests(job_id);
CREATE INDEX IF NOT EXISTS idx_revision_requests_client ON strategy_revision_requests(client_id);
