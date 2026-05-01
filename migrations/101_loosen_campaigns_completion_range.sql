-- Migration 101: Loosen emailbison_campaigns_completion_range to permit >100%
--
-- Why this exists
-- ───────────────
-- The original constraint (from migration 070-ish era):
--
--     CHECK (completion_percentage IS NULL
--            OR (completion_percentage >= 0
--                AND completion_percentage <= 100))
--
-- enforced the assumption that completion never exceeds 100%. In practice,
-- EmailBison legitimately reports completion_percentage > 100 when:
--
--   1. Leads are added to an already-running campaign (the denominator
--      grows but the numerator — already-sent emails — overshoots)
--   2. Multi-touch campaigns where total_emails_sent > unique_leads, and
--      EB's percentage formula is sends / leads_contacted (sends > leads
--      when followups are sent).
--
-- Verified on 2026-05-01 against production sync errors:
--
--     MBC (Hello Hero):                    completion_percentage = 129.47
--     Cycle 1: Campaign 6: Healthcare:     completion_percentage = 118.38
--     Sammy v3 - Painters:                 completion_percentage = 115.73
--     Cycle 3: Campaign 14, FBA Refugees:  completion_percentage = 104.49
--
-- The CHECK constraint rejected ~242 campaign upsert attempts in 24h
-- (sync_audit_log records_failed for sync_type='campaigns' on 2026-05-01).
-- Counts were tracked in error_details JSONB; root cause was opaque until
-- the JSONB was queried directly.
--
-- Fix: Drop the upper bound. Keep the lower bound (negative completion is
-- still nonsensical and indicates a real bug). Leave NULL allowed.

ALTER TABLE emailbison_campaigns
    DROP CONSTRAINT IF EXISTS emailbison_campaigns_completion_range;

ALTER TABLE emailbison_campaigns
    ADD CONSTRAINT emailbison_campaigns_completion_range
    CHECK (completion_percentage IS NULL OR completion_percentage >= 0);

-- Document the constraint semantics in the column comment
COMMENT ON COLUMN emailbison_campaigns.completion_percentage IS
    'EmailBison-reported campaign completion. Can exceed 100 when leads are '
    'added mid-campaign or when multi-touch sends per lead exceed initial '
    'cohort size. Migration 101 (2026-05-01) loosened the prior 0..100 '
    'CHECK constraint to permit values >100 after observing 242 daily '
    'sync failures from legitimate >100% campaigns.';
