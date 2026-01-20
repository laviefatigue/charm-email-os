-- Migration: Strategy-Submission binding
-- Adds submission_id to strategies table to link strategies to their onboarding submissions

-- Add submission_id column to strategies table
ALTER TABLE strategies
ADD COLUMN IF NOT EXISTS submission_id UUID REFERENCES client_onboarding_submissions(id);

-- Create index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_strategies_submission ON strategies(submission_id);

-- Note: Existing strategies will have NULL submission_id, which is fine.
-- New strategies can optionally be linked to a submission when created.
