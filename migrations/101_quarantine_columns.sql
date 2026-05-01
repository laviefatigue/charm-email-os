-- Migration 101: Cross-workspace integrity firewall — quarantine columns
--
-- Plan A Phase 1 of docs/plans/cross-workspace-integrity-firewall.md.
--
-- ADDS THREE COLUMNS to sender_accounts (schema-only; no enforcement yet):
--   is_quarantined          BOOLEAN  — TRUE if email_address fails the
--                                      workspace's clients.domain_pattern
--                                      substring match (HR-2)
--   quarantine_reason       VARCHAR  — human-readable why (e.g.
--                                      'pattern_mismatch:expected=charm,
--                                       got=mydomain.com')
--   quarantine_detected_at  TIMESTAMPTZ — when the firewall first flagged
--                                         this row
--
-- ADDS PARTIAL INDEX on is_quarantined=TRUE only:
--   This is a small subset (currently 0 rows; even after backfill, expected
--   to be a single-digit % of fleet). Partial index keeps the cost
--   negligible while making "list all quarantined inboxes" fast.
--
-- DELIBERATELY EXCLUDED from this migration:
--   1. The CHECK constraint chk_quarantined_no_pool
--      (Phase 4 / migration 103 — must come AFTER Phase 3 backfill nulls
--      inventory_pool_status on existing pollution. Adding the CHECK first
--      would fail to apply on existing live+foreign rows.)
--   2. Any code that SETS is_quarantined=TRUE
--      (Phase 5 — gate at sync_accounts.upsert and downstream filters)
--
-- ROLLBACK SAFETY:
--   This migration is reversible — DROP COLUMN works as long as no code
--   depends on the columns. Phase 5 introduces those dependencies; until
--   then, this migration can be reverted without data loss.
--
-- WHY NOW:
--   clients.domain_pattern was populated 2026-05-01 via Phase 0+2 (commit
--   9c799b1). Phase 1 readies the schema to receive Phase 5's writes when
--   that ships. Schema-only changes are safe to land ahead of code.

ALTER TABLE sender_accounts
    ADD COLUMN IF NOT EXISTS is_quarantined BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS quarantine_reason VARCHAR,
    ADD COLUMN IF NOT EXISTS quarantine_detected_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_sender_accounts_quarantined
    ON sender_accounts (is_quarantined)
    WHERE is_quarantined = TRUE;

COMMENT ON COLUMN sender_accounts.is_quarantined IS
    'Cross-workspace integrity firewall — TRUE when email_address fails the '
    'workspace''s clients.domain_pattern substring match. Set by Phase 5 gate '
    'at sync_accounts.upsert and downstream filters. CHECK constraint '
    'chk_quarantined_no_pool added in migration 103 enforces that quarantined '
    'rows can never carry a pool tag (HR-1).';

COMMENT ON COLUMN sender_accounts.quarantine_reason IS
    'Human-readable explanation of why this row was quarantined. Format: '
    '"pattern_mismatch:expected={pattern},got={domain}" or '
    '"null_pattern_workspace" when client.domain_pattern is NULL (HR-5).';

COMMENT ON COLUMN sender_accounts.quarantine_detected_at IS
    'Timestamp when the firewall first set is_quarantined=TRUE for this '
    'row. Used by audit reports and the operator review surface to show '
    'time-since-detection.';
