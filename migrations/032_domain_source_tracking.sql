-- Migration: 032_domain_source_tracking.sql
-- Purpose: Add explicit domain_source column to track origin of domains
-- Related: Option A - Schema First

-- Add domain_source enum column
-- Values: 'generated' (AI-generated), 'purchased' (bought via system), 'legacy' (pre-1/22/26)
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_source VARCHAR(20)
    DEFAULT 'legacy'
    CHECK (domain_source IN ('generated', 'purchased', 'legacy'));

-- Backfill based on existing data patterns:
-- 1. If purchased_at IS NOT NULL AND selected_provider IS NOT NULL -> 'purchased'
-- 2. If status = 'legacy' -> 'legacy'
-- 3. If status IN ('available', 'pending', 'pending_approval', 'approved') -> 'generated'
-- 4. Everything else stays 'legacy' (safe default)

-- Mark purchased domains
UPDATE domains
SET domain_source = 'purchased'
WHERE purchased_at IS NOT NULL
  AND selected_provider IS NOT NULL
  AND domain_source = 'legacy';

-- Mark generated domains (available for purchase but not yet bought)
UPDATE domains
SET domain_source = 'generated'
WHERE status IN ('available', 'pending', 'pending_approval', 'approved')
  AND purchased_at IS NULL
  AND domain_source = 'legacy';

-- Add index for filtering by source
CREATE INDEX IF NOT EXISTS idx_domains_source ON domains(domain_source);

-- Composite index for common query pattern (workspace + source + status)
CREATE INDEX IF NOT EXISTS idx_domains_workspace_source ON domains(workspace_id, domain_source, status);

-- Add comment for documentation
COMMENT ON COLUMN domains.domain_source IS 'Origin of domain: generated (AI), purchased (via system), legacy (pre-1/22/26)';

SELECT 'Migration 032_domain_source_tracking complete' AS status;
