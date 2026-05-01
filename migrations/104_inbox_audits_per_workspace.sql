-- Migration 104: Inbox Audit Overhaul Phase 1 — per-workspace + snapshot schema
--
-- Plan reference: docs/plans/inbox-audit-overhaul.md Phase 1
-- Master tracker: docs/plans/INBOX-INTEGRITY-PROGRAM.md §3.7
--
-- WHY THIS EXISTS
-- ───────────────
-- The current inbox_audits schema (migration 063, shipped 2026-02-18) has
-- two structural problems documented as schema gaps S-1 and S-2 in the
-- overhaul plan:
--
--   S-1: No workspace_id. Every audit is fleet-aggregate. Cannot answer
--        "is Sammy specifically in trouble?" without re-running queries
--        against live data.
--
--   S-2: Only aggregate counts, no inbox-set snapshot. Today's audit
--        captures total_kills=380 for 2026-04-29 but no record of WHICH
--        380. Investigation after the fact is impossible.
--
-- Plus a third gap surfaced 2026-04-30:
--
--   S-3: No structured per-domain rollup for the subscription-cancel
--        signal (which Hypertide subscriptions can be cancelled because
--        the entire domain is dead).
--
-- WHAT THIS ADDS
-- ──────────────
--   workspace_id UUID FK     — per-workspace audit row (S-1)
--   inbox_id_set JSONB        — snapshot of which inboxes were in scope
--                               at audit time (S-2). Stored as a JSON
--                               array of UUIDs for fleet-row compat;
--                               per-section breakdowns live in audit_data.
--   audit_data JSONB          — structured bag for integrity sections
--                               I-1 through I-9 + S-3 subscription-cancel
--                               rollup. Phase 3 of the overhaul fills
--                               this column; this migration just creates
--                               it so subsequent code changes don't
--                               require another schema bump.
--
-- WHY JSONB INSTEAD OF SEPARATE COLUMNS
-- ─────────────────────────────────────
-- 1. Integrity sections will evolve (I-10, I-11 added as new patterns
--    surface). Adding new typed columns each time = schema churn.
-- 2. Each audit produces a structured report that's better held together
--    than split across 30+ typed columns.
-- 3. JSONB is queryable when needed (jsonb_path_query, ?>, etc.) and
--    indexable per-key.
-- 4. The fields that drive OPERATOR WORKFLOW (status, reviewed_by, notes)
--    stay typed because the workflow tooling depends on them.
--
-- INDEXES
-- ───────
-- Two indexes for the dominant query patterns:
--   1. "give me the latest audit for workspace X" — (workspace_id, audit_date DESC)
--   2. "find pending reviews for SLA enforcement" — partial index on status='pending'
--
-- BACKWARD COMPATIBILITY
-- ──────────────────────
-- Existing rows (created via the legacy fleet-aggregate audit) will have
-- NULL workspace_id and NULL audit_data. They remain queryable via the
-- existing total_kills / total_disconnected columns. Phase 2 of the
-- overhaul rewrites the audit query to populate workspace_id going
-- forward. Old rows can be soft-archived or left as-is.
--
-- ROLLBACK SAFETY
-- ───────────────
-- All adds are nullable, no DEFAULT side-effects. DROP COLUMN reverses
-- cleanly. Reversible.

ALTER TABLE inbox_audits
    ADD COLUMN IF NOT EXISTS workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS inbox_id_set JSONB,
    ADD COLUMN IF NOT EXISTS audit_data JSONB;

-- Per-workspace latest-audit lookup. The DESC on audit_date matches the
-- query "SELECT ... ORDER BY audit_date DESC LIMIT 1" pattern.
CREATE INDEX IF NOT EXISTS idx_inbox_audits_workspace_date
    ON inbox_audits (workspace_id, audit_date DESC)
    WHERE workspace_id IS NOT NULL;

-- SLA enforcement — partial index on pending reviews. Currently 72 of
-- 72 audits are pending and never reviewed (per overhaul plan context).
-- The SLA work in Phase 6 needs fast access to "what's pending and
-- older than 24h / 7d".
CREATE INDEX IF NOT EXISTS idx_inbox_audits_pending
    ON inbox_audits (status, created_at)
    WHERE status = 'pending';

COMMENT ON COLUMN inbox_audits.workspace_id IS
    'Per-workspace audit scope (Plan: inbox-audit-overhaul.md S-1). NULL for '
    'legacy fleet-aggregate rows created before migration 104. Phase 2 of '
    'the overhaul rewrites the audit query to populate this column going '
    'forward.';

COMMENT ON COLUMN inbox_audits.inbox_id_set IS
    'JSON array of sender_account UUIDs in scope at audit time (S-2). '
    'Lets investigators answer "which inboxes were in this audit?" without '
    'replaying queries against live data. May be partial when audit_data '
    'breaks the set into integrity-section sub-arrays.';

COMMENT ON COLUMN inbox_audits.audit_data IS
    'Structured report payload for integrity sections I-1 through I-9 + '
    'S-3 subscription-cancel rollup. Schema is documented in '
    'docs/plans/inbox-audit-overhaul.md and lives in the JSONB so it can '
    'evolve without schema migrations. Phase 3 of the overhaul fills this '
    'column. Legacy rows have NULL.';
