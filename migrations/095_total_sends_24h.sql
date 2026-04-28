-- Migration 095: Daily-send-aware kill threshold floor
--
-- Why this exists
-- ───────────────
-- Phase 4 of the 2026-04-27 overhaul tightened count-based kill triggers
-- (hard_bounces_24h ≥ 2, hard_blocked_24h ≥ 2, hard_unknown_24h ≥ 3) with a
-- minimum-volume floor: do not kill an inbox for "2 hard bounces in 24h"
-- when the inbox barely sent anything in that window.
--
-- The interim implementation uses total_sends_7d ≥ 20 as a proxy for "this
-- inbox is actually sending." That works but is decayed daily by ~14% so
-- a single high-volume day from 5 days ago can keep an idle inbox above
-- the floor. CEO targets 15-20 daily sends per inbox, so a 24h-scoped
-- column is a more direct match.
--
-- Tracking model
-- ──────────────
-- total_sends_24h is populated by sync_warmup / sync_accounts when they
-- pull stats from EmailBison. We accept the same rolling-window decay
-- approach used for the 7d counters: reset_daily_counters resets the
-- value at midnight, sync writes the actual EB-reported "today" count
-- on each pull, and the kill threshold reads the current value at
-- evaluation time.
--
-- This migration only adds the column; population is wired into the
-- sync modules in the same overhaul commit.

ALTER TABLE sender_accounts
    ADD COLUMN IF NOT EXISTS total_sends_24h INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN sender_accounts.total_sends_24h IS
    'Rolling-day campaign-send count from EmailBison. Reset daily by '
    'reset_daily_counters and refreshed on every sync_warmup pull. Used '
    'by health_checks as the min-volume floor for count-based kill '
    'triggers (hard_bounces_24h, hard_blocked_24h, hard_unknown_24h).';

CREATE INDEX IF NOT EXISTS idx_sender_accounts_total_sends_24h
    ON sender_accounts (total_sends_24h)
    WHERE total_sends_24h > 0;
