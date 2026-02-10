-- Migration: 016_campaign_documents.sql
-- Purpose: Create Campaign Document structure for stablekernel-style output
-- A Campaign Document contains multiple variants per email position, ICP mapping,
-- variable schema, QA scoring, and strategy notes

-- Main document table
CREATE TABLE IF NOT EXISTS campaign_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    strategy_id UUID REFERENCES strategies(id) ON DELETE SET NULL,

    -- Header metadata
    document_name VARCHAR(255) NOT NULL,
    document_version INTEGER DEFAULT 1,
    vertical VARCHAR(100),  -- Industry/vertical for targeting
    objective TEXT,  -- Primary GTM objective

    -- ICP & Objection Mapping (JSONB)
    -- Structure: {
    --   "target_icp": { "role": "...", "company_type": "...", "company_size": "..." },
    --   "pain_points": [{ "category": "...", "label": "...", "points": ["..."] }],
    --   "objections": [{ "objection": "...", "preemption": "..." }]
    -- }
    icp_mapping JSONB,

    -- Variable Schema (JSONB)
    -- Structure: {
    --   "core": [{ "name": "{{first_name}}", "description": "..." }],
    --   "high_signal": [{ "name": "{{core_vendor}}", "description": "...", "source": "..." }],
    --   "ai_generated": [{ "name": "{{ai_customer_type}}", "description": "..." }]
    -- }
    variable_schema JSONB,

    -- Sequence Summary (JSONB array)
    -- Structure: [{ "day": "Day 0", "title": "Email 1 - Poke the Bear", "description": "..." }]
    sequence_summary JSONB,

    -- QA Scoring for lead variant (JSONB)
    -- Structure: {
    --   "overall_score": 94,
    --   "verdict": "Ship it",
    --   "dimensions": [{ "name": "Situation Recognition", "score": "24/25", "notes": "..." }]
    -- }
    qa_scoring JSONB,

    -- Strategy Notes (JSONB)
    -- Structure: {
    --   "callouts": [{ "type": "recommendation|warning|info", "text": "..." }],
    --   "data_enrichment": [{ "variable": "{{core_vendor}}", "source": "Job postings, BuiltWith" }],
    --   "ab_testing": ["Test V1 vs V3 for Email 1", "..."]
    -- }
    strategy_notes JSONB,

    -- Status
    status VARCHAR(50) DEFAULT 'draft',  -- draft, review, approved, sent

    -- Review info
    human_comment TEXT,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_campaign_docs_client ON campaign_documents(client_id);
CREATE INDEX IF NOT EXISTS idx_campaign_docs_job ON campaign_documents(job_id);
CREATE INDEX IF NOT EXISTS idx_campaign_docs_strategy ON campaign_documents(strategy_id);
CREATE INDEX IF NOT EXISTS idx_campaign_docs_status ON campaign_documents(status);

COMMENT ON TABLE campaign_documents IS 'Campaign documents in stablekernel format with variants per email position';
COMMENT ON COLUMN campaign_documents.icp_mapping IS 'Target ICP, pain points, and objection preemptions';
COMMENT ON COLUMN campaign_documents.variable_schema IS 'Core, high-signal, and AI-generated variables with sources';
COMMENT ON COLUMN campaign_documents.qa_scoring IS 'QA scoring breakdown by dimension for lead variant';
COMMENT ON COLUMN campaign_documents.strategy_notes IS 'Callouts, data enrichment sources, A/B testing recommendations';


-- Email variants table (multiple variants per email position)
CREATE TABLE IF NOT EXISTS document_email_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES campaign_documents(id) ON DELETE CASCADE,

    -- Position info
    email_position INTEGER NOT NULL CHECK (email_position BETWEEN 1 AND 4),
    variant_number INTEGER NOT NULL,  -- V1, V2, V3...
    variant_name VARCHAR(255),  -- "Core Vendor Frustration", "Hiring Signal → Backlog Problem"
    is_recommended BOOLEAN DEFAULT FALSE,  -- Show "Recommended" badge

    -- Email content
    subject_line TEXT,  -- null for threaded emails
    email_body TEXT NOT NULL,

    -- Timing and threading
    wait_days INTEGER DEFAULT 0,
    thread_reply BOOLEAN DEFAULT FALSE,

    -- Stats
    word_count INTEGER,
    them_us_ratio VARCHAR(10),  -- "3:1"
    score INTEGER CHECK (score BETWEEN 0 AND 100),

    -- Targeting info
    angle VARCHAR(50),  -- custom_signal, persona_pain, case_study, risk_efficiency
    strategy TEXT,  -- Description of approach
    value_prop VARCHAR(50),  -- save_time, save_money, make_money

    -- Editing
    edited_subject_line TEXT,
    edited_email_body TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(document_id, email_position, variant_number)
);

CREATE INDEX IF NOT EXISTS idx_email_variants_doc ON document_email_variants(document_id);
CREATE INDEX IF NOT EXISTS idx_email_variants_position ON document_email_variants(document_id, email_position);
CREATE INDEX IF NOT EXISTS idx_email_variants_recommended ON document_email_variants(document_id, is_recommended) WHERE is_recommended = TRUE;

COMMENT ON TABLE document_email_variants IS 'Email variants within a campaign document, multiple variants per position';
COMMENT ON COLUMN document_email_variants.is_recommended IS 'Whether this variant is the recommended option for its position';


-- Subject line options table
CREATE TABLE IF NOT EXISTS document_subject_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES campaign_documents(id) ON DELETE CASCADE,
    email_position INTEGER NOT NULL CHECK (email_position BETWEEN 1 AND 4),
    subject_line TEXT NOT NULL,
    rationale TEXT,
    sort_order INTEGER DEFAULT 0,

    UNIQUE(document_id, email_position, subject_line)
);

CREATE INDEX IF NOT EXISTS idx_subject_options_doc ON document_subject_options(document_id);
CREATE INDEX IF NOT EXISTS idx_subject_options_position ON document_subject_options(document_id, email_position);

COMMENT ON TABLE document_subject_options IS 'Subject line options with rationale for each email position';


-- Add document_id to existing strategy_suggestions for backward compatibility
ALTER TABLE strategy_suggestions ADD COLUMN IF NOT EXISTS document_id UUID REFERENCES campaign_documents(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_suggestions_document ON strategy_suggestions(document_id);
