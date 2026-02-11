-- Migration: 015_onboarding_extended_fields.sql
-- Purpose: Add missing fields that the external onboarding form collects but database doesn't store
-- These fields are needed for stablekernel-style campaign document generation

-- Industry/Vertical (needed for campaign header)
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS industry VARCHAR(100);

-- Section 4: Audience - Competitors and Differentiators
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS competitors TEXT[];
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS key_differentiators TEXT;

-- Section 4: Global objections and triggers (form has these at top level, not just per-persona)
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS common_objections TEXT;
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS buying_triggers_global TEXT;

-- Section 5: Process - Current performance metrics
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS monthly_volume VARCHAR(50);
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS current_open_rate VARCHAR(20);
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS current_reply_rate VARCHAR(20);
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS other_channels TEXT;

-- Section 5: What's worked and what hasn't
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS messages_worked TEXT;
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS approaches_failed TEXT;

-- Section 6: Messaging - Additional fields
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS case_studies TEXT;
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS industry_jargon TEXT;

-- Section 7: Goals - Additional context
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS engagement_win TEXT;
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS additional_context TEXT;

-- Tech stack / Core vendors (for {{core_vendor}} variable)
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS core_vendors TEXT[];

-- Annual revenue (form collects this but wasn't stored)
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS annual_revenue VARCHAR(50);

-- Self-serve percentage (form collects this)
ALTER TABLE client_onboarding_submissions ADD COLUMN IF NOT EXISTS self_serve_pct VARCHAR(50);

-- Create indexes for commonly queried fields
CREATE INDEX IF NOT EXISTS idx_onboarding_submissions_industry ON client_onboarding_submissions(industry);

COMMENT ON COLUMN client_onboarding_submissions.industry IS 'Industry/Vertical for campaign targeting (e.g., Financial Services, SaaS, Healthcare)';
COMMENT ON COLUMN client_onboarding_submissions.competitors IS 'Array of competitor names prospect compares against';
COMMENT ON COLUMN client_onboarding_submissions.key_differentiators IS 'What sets the client apart from competitors';
COMMENT ON COLUMN client_onboarding_submissions.common_objections IS 'Typical pushback/objections from prospects';
COMMENT ON COLUMN client_onboarding_submissions.messages_worked IS 'Messaging approaches that have worked in the past';
COMMENT ON COLUMN client_onboarding_submissions.approaches_failed IS 'Approaches that did not work - patterns to avoid';
COMMENT ON COLUMN client_onboarding_submissions.case_studies IS 'Case study summaries by segment';
COMMENT ON COLUMN client_onboarding_submissions.industry_jargon IS 'Industry terms to use or avoid';
COMMENT ON COLUMN client_onboarding_submissions.core_vendors IS 'Array of core tech vendors (e.g., Fiserv, Salesforce) for targeting';
