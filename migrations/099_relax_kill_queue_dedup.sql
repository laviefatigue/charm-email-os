-- Migration 099: relax kill_queue dedup index to allow re-queueing after flagged
--
-- Pre-existing partial unique index:
--   idx_kill_queue_inbox_pending ON kill_queue(inbox_id) WHERE status IN ('pending', 'flagged')
--
-- Problem this fixes:
-- Pre-2026-04-29 the dedup index assumed `flagged` = "kill processed, inbox is
-- dead in DB." That assumption holds for the current code path
-- (kill_processor.py is DB-first then EB-second, line 336-360 — both happen
-- inside a single try block, so a successful DB step sets BOTH
-- kill_queue.status='flagged' AND sender_accounts.inbox_state='dead'),
-- but pre-overhaul code had the opposite ordering. The result was 76 inboxes
-- (all `provider_block_*` flagged from March 2026) that ended up
-- inbox_state='live' + kill_queue.status='flagged'. The partial unique index
-- treated them as "already handled" and SILENTLY blocked any new kill
-- (e.g. spam_complaint) from being queued for those inboxes — they
-- accumulated bounce signals indefinitely without intervention.
--
-- Fix: narrow the index to only block on `pending`. After a kill is `flagged`,
-- if the inbox is still alive (legacy/edge state), health_checks will see it
-- via its WHERE inbox_state='live' filter and re-queue. The kill_processor's
-- existing logic handles the new pending row normally. Properly-dead inboxes
-- aren't affected because health_checks filters them out (won't re-queue).
--
-- Companion changes shipping in this commit:
--   - sync_modules/health_checks.py queue_for_kill ON CONFLICT clause
--     updated to match the new index condition
--   - sync_modules/overhaul_audit.py adds `flagged_but_alive_count` metric
--     so any future regression to the buggy state is surfaced daily
--
-- This migration is idempotent — it drops then recreates the index with the
-- narrower condition. Existing rows are not modified.

BEGIN;

DROP INDEX IF EXISTS idx_kill_queue_inbox_pending;

-- Narrow partial unique index: only blocks duplicate `pending` rows.
-- Allows re-queueing after a kill has been `flagged` if the inbox is somehow
-- still alive (which it shouldn't be in the steady-state, but the index
-- shouldn't be the structural blocker if it happens).
CREATE UNIQUE INDEX idx_kill_queue_inbox_pending
ON kill_queue (inbox_id)
WHERE status = 'pending';

COMMIT;
