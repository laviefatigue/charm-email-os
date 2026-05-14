-- Migration 110: Hypertide domain state + workspace classification flags.
--
-- Phase 1 of the hypertide-service rollout. See
-- docs/architecture/hypertide-service.md for the full plan.
--
-- This migration is read-side: it adds columns that will be populated by
-- the new apps/hypertide-worker reconcile process. No application code
-- depends on these columns yet — Phase 2+ wires them into health/rotation.
--
-- Two changes:
--   1. workspaces.manages_via_hypertide / occupancy_only — workspace-level
--      classification. Workspaces flagged manages_via_hypertide=FALSE are
--      skipped by every Hypertide process (audit, sync, drift alerts).
--      Used for friend-occupancy or pre-HT clients (Estrada, Neon,
--      EventPanda).
--   2. domains.hypertide_* + is_legacy + expected_inbox_count — per-domain
--      Hypertide linkage. is_legacy flags domains in HT-managed workspaces
--      that have no HT record (pre-HT or out-of-band provisioned).
--
-- Field semantics:
--   hypertide_last_synced_at - timestamp of the last successful audit pass.
--     Used by readers for staleness checks. Must advance on every audit.
--   hypertide_last_seen_at  - timestamp of the last audit pass where this
--     hypertide_record_id appeared in /orders/active. If this stops
--     advancing while the row exists, HT has purged the record vendor-side.
--     Don't auto-delete the row; flag for review instead.
--   expected_inbox_count    - 52 for entra (Microsoft) plan, 3 for google.
--     Populated from HT plan metadata. Used by Phase 2 provisioning
--     watchdog: if sender_account count < expected, alert.
--
-- Idempotent: every ADD COLUMN uses IF NOT EXISTS via DO block;
-- safe to re-run.

BEGIN;

-- =====================================================================
-- 1. Workspace classification flags
-- =====================================================================
-- manages_via_hypertide = FALSE  → workspace skipped by every HT process
-- occupancy_only        = TRUE   → "we host them but they're not a billed
--                                   client" (friend-occupancy)
-- The two flags are independent: occupancy_only=TRUE typically implies
-- manages_via_hypertide=FALSE but the inverse is not always true (some
-- legacy clients are billed but pre-date HT).

ALTER TABLE workspaces
    ADD COLUMN IF NOT EXISTS manages_via_hypertide BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS occupancy_only        BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN workspaces.manages_via_hypertide IS
    'When FALSE, every Hypertide reconcile process skips this workspace. '
    'Set FALSE for friend-occupancy or pre-HT clients with no HT footprint.';
COMMENT ON COLUMN workspaces.occupancy_only IS
    'TRUE if we host this workspace but they are not a billed client. '
    'Useful for filtering reports and dashboards.';


-- =====================================================================
-- 2. Domain Hypertide linkage + legacy flag
-- =====================================================================

ALTER TABLE domains
    ADD COLUMN IF NOT EXISTS is_legacy                  BOOLEAN     NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS hypertide_record_id        TEXT,
    ADD COLUMN IF NOT EXISTS hypertide_subscription_id  TEXT,
    ADD COLUMN IF NOT EXISTS hypertide_product_id       TEXT,
    ADD COLUMN IF NOT EXISTS hypertide_status           VARCHAR(16),
    ADD COLUMN IF NOT EXISTS hypertide_payment_status   VARCHAR(16),
    ADD COLUMN IF NOT EXISTS hypertide_sending_tool     VARCHAR(20),
    ADD COLUMN IF NOT EXISTS hypertide_cancellation_type VARCHAR(24),
    ADD COLUMN IF NOT EXISTS hypertide_to_be_cancelled  BOOLEAN     DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS hypertide_last_synced_at   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS hypertide_last_seen_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS expected_inbox_count       INTEGER;

COMMENT ON COLUMN domains.is_legacy IS
    'Domain in an HT-managed workspace but with no Hypertide record. '
    'Pre-HT manual provisioning or out-of-band acquired. Flag is set by '
    'reconcile when no HT match is found; never auto-cleared.';

COMMENT ON COLUMN domains.hypertide_record_id IS
    'Hypertide Airtable record ID (rec*). Globally unique. NULL means '
    'either (a) not yet matched to an HT record, or (b) is_legacy=TRUE.';

COMMENT ON COLUMN domains.hypertide_subscription_id IS
    'Stripe subscription ID (sub_*) of the HT subscription that includes '
    'this domain. Multiple domains can share one subscription.';

COMMENT ON COLUMN domains.hypertide_status IS
    'HT order processing status: Done, Todo, In progress, NPC. '
    'NPC = post-cancellation residue (HT retains the row, Stripe linkage '
    'removed). See docs/integrations/hypertide-api.md empirical observations.';

COMMENT ON COLUMN domains.hypertide_payment_status IS
    'HT billing channel: Paid (Stripe USD, Microsoft Entra), Google '
    '(Google Workspace billing), Google-Solo (3-inbox plan).';

COMMENT ON COLUMN domains.hypertide_cancellation_type IS
    'From verify-revert: none | full_subscription | partial | partial_product '
    '| cancelling | cancelled | executed | unknown. Records with NOT IN '
    '(cancelled, executed) are still being billed by HT.';

COMMENT ON COLUMN domains.hypertide_to_be_cancelled IS
    'Convenience flag mirroring HT verify-revert toBeCancelled. Maps to '
    'platform UI orange "To Be Cancelled" pill. TRUE when a cancellation '
    'is queued (regardless of whether it has executed yet).';

COMMENT ON COLUMN domains.hypertide_last_synced_at IS
    'Timestamp of last successful audit pass. Advances on every audit '
    'whether or not state changed. Use for staleness checks.';

COMMENT ON COLUMN domains.hypertide_last_seen_at IS
    'Timestamp of last audit pass where this hypertide_record_id appeared '
    'in /orders/active. If this stops advancing while the row exists, HT '
    'has purged the record vendor-side. Do NOT auto-delete; flag for review.';

COMMENT ON COLUMN domains.expected_inbox_count IS
    'Number of inboxes HT promised for this domain (52 for Entra/Microsoft, '
    '3 for Google). Populated at order time (Phase 3) or backfill from '
    'HT plan metadata. Used by Phase 2 provisioning watchdog: if '
    'COUNT(sender_accounts) < expected_inbox_count past the deadline, alert.';


-- =====================================================================
-- 3. Indexes
-- =====================================================================
-- Globally unique on hypertide_record_id when set. NULL allowed (legacy
-- + un-matched rows). Partial index keeps the unique constraint correct
-- without blocking NULL values.

CREATE UNIQUE INDEX IF NOT EXISTS domains_hypertide_record_id_uniq
    ON domains(hypertide_record_id)
    WHERE hypertide_record_id IS NOT NULL;

-- Lookup index for "find me all domains under this subscription" — used
-- by per-subscription operations (verify-revert refresh, partial cancel
-- recordIds gather).
CREATE INDEX IF NOT EXISTS domains_hypertide_subscription_id_idx
    ON domains(hypertide_subscription_id)
    WHERE hypertide_subscription_id IS NOT NULL;

-- Staleness index for the daily audit cron: "give me domains whose HT
-- state hasn't been refreshed in N hours."
CREATE INDEX IF NOT EXISTS domains_hypertide_last_synced_idx
    ON domains(hypertide_last_synced_at)
    WHERE hypertide_record_id IS NOT NULL;

-- Cancel-queued index: fast filter for "what's scheduled to cancel."
CREATE INDEX IF NOT EXISTS domains_hypertide_pending_cancel_idx
    ON domains(hypertide_subscription_id)
    WHERE hypertide_to_be_cancelled = TRUE;


COMMIT;
