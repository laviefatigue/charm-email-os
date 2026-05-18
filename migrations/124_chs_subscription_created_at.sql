-- Migration 124: client_hypertide_subscriptions.subscription_created_at
--
-- Preserves HT's `createdAt` per sub so we have a historical anchor (when HT
-- created the subscription, not when WE first saw the binding). Range across
-- the 211 active subs as of 2026-05-18: Nov 2024 → May 2026.
--
-- Splits the two timelines cleanly:
--   first_seen_at           = when our chs binding was inserted (operational —
--                             defaults to NOW, set by seed/worker)
--   subscription_created_at = when HT created the sub (historical anchor —
--                             populated from HT's createdAt field; date-only
--                             because HT returns YYYY-MM-DD)
--
-- HT exposes no /orders/cancelled enumeration, so subs cancelled before the
-- seed run can't be back-filled retroactively. From-now-forward cancellations
-- are tracked by DECISION 4 (hypertide_status_events, step 9).
--
-- Safe to re-run: ADD COLUMN IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.

BEGIN;

ALTER TABLE client_hypertide_subscriptions
    ADD COLUMN IF NOT EXISTS subscription_created_at DATE;

COMMENT ON COLUMN client_hypertide_subscriptions.subscription_created_at IS
    'HT createdAt for the subscription (date-only — HT returns YYYY-MM-DD). '
    'Historical anchor distinct from first_seen_at (which records when WE '
    'inserted the binding row). NULL only when HT did not return a createdAt '
    'for this sub at seed/first-sync time.';

CREATE INDEX IF NOT EXISTS chs_subscription_created_at_idx
    ON client_hypertide_subscriptions(subscription_created_at)
    WHERE subscription_created_at IS NOT NULL;

COMMIT;
