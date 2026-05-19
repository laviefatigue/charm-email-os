-- Migration 126: hypertide_status_events — change-tracking log per subscription
--
-- Step 9 of docs/plans/hypertide-data-model-and-change-tracking.md (DECISION 4).
--
-- Captures lifecycle events on HT subscriptions detected by the worker:
--   - 'cancelled'         — sub was in chs and stopped appearing in /orders/active
--   - 'reappeared'        — chs sub appeared again after a prior cancellation event
--   - 'organization_renamed' — HT changed organizationName for a sub (audit trail)
--
-- Each cancellation event carries a verdict by joining to domains.qualifies_for_cancellation_*:
--   - 'justified'    — any domain for this sub's client has qualifies_for_cancellation_at populated
--   - 'unjustified'  — no kill-trigger verdict; HT or operator cancelled out-of-band
--   - 'pending'      — verdict columns not yet populated (e.g. historical burns pre-migration 125)
--
-- Detection happens worker-side in apps/hypertide-worker on each audit pass:
--   1. After chs_sync touches last_seen_at for every sub in current /orders/active,
--      query chs rows WHERE last_seen_at < this_audit_started_at (didn't appear)
--   2. For each, check whether a 'cancelled' event already exists since their last
--      sighting — if so, skip (already tracked); if not, INSERT a new event
--   3. Verdict computed by joining domains.qualifies_for_cancellation_at on the
--      sub's client_id (any populated → justified)
--
-- Idempotency:
--   - PK on id (gen_random_uuid)
--   - Worker check "no 'cancelled' event for this sub since chs.last_seen_at"
--     prevents duplicate events on subsequent audits where the sub stays absent
--   - On reappearance, worker writes 'reappeared' event; future absences become
--     a new 'cancelled' event (the prior one belongs to the prior cancellation cycle)
--
-- Why not a Postgres trigger: triggers can't see external HT state. The
-- detection is necessarily an audit-pass operation (compare prior chs to
-- current /orders/active). The "trigger" in DECISION 4's name is the worker's
-- detect_status_changes pass, not a DB trigger.

BEGIN;

CREATE TABLE IF NOT EXISTS hypertide_status_events (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscription_id   TEXT NOT NULL REFERENCES client_hypertide_subscriptions(subscription_id) ON DELETE CASCADE,
    client_id         UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    event_type        VARCHAR(32) NOT NULL,
    event_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detected_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    prior_last_seen_at TIMESTAMPTZ,
    verdict           VARCHAR(24),
    verdict_reasons   TEXT[],
    affected_domain_count INTEGER,
    notes             TEXT
);

ALTER TABLE hypertide_status_events
    DROP CONSTRAINT IF EXISTS hse_event_type_check,
    ADD CONSTRAINT hse_event_type_check
        CHECK (event_type IN ('cancelled', 'reappeared', 'organization_renamed'));

ALTER TABLE hypertide_status_events
    DROP CONSTRAINT IF EXISTS hse_verdict_check,
    ADD CONSTRAINT hse_verdict_check
        CHECK (verdict IS NULL OR verdict IN ('justified', 'unjustified', 'pending'));

CREATE INDEX IF NOT EXISTS hse_subscription_event_at_idx
    ON hypertide_status_events(subscription_id, event_at DESC);

CREATE INDEX IF NOT EXISTS hse_event_at_idx
    ON hypertide_status_events(event_at DESC);

CREATE INDEX IF NOT EXISTS hse_unjustified_idx
    ON hypertide_status_events(event_at DESC)
    WHERE event_type = 'cancelled' AND verdict = 'unjustified';

COMMENT ON TABLE hypertide_status_events IS
    'Lifecycle event log for HT subscriptions, written by hypertide-worker '
    'on each audit pass. Each ''cancelled'' event carries a verdict joining '
    'domains.qualifies_for_cancellation_* to label HT cancellations as '
    'justified (we said so first) vs unjustified (HT or operator acted '
    'out-of-band). See migration 125 + DECISION 6 for the verdict source.';

COMMENT ON COLUMN hypertide_status_events.event_type IS
    'cancelled | reappeared | organization_renamed. Cancellation events fire '
    'on first audit pass that doesn''t see a previously-known sub. Reappearance '
    'fires if a previously-cancelled sub comes back into /orders/active.';

COMMENT ON COLUMN hypertide_status_events.verdict IS
    'For event_type=cancelled only. justified = at least one domain for this '
    'sub''s client has qualifies_for_cancellation_at set (we burned it first). '
    'unjustified = HT cancelled without a kill-trigger justification — flag '
    'for operator review. pending = no kill-trigger writes yet (e.g. burned '
    'before migration 125 shipped).';

COMMENT ON COLUMN hypertide_status_events.prior_last_seen_at IS
    'Snapshot of chs.last_seen_at at detection time. Lets the reconstruction '
    'queries know the (last sighting, first absence) window without joining '
    'chs which may have moved on by then.';

COMMIT;
