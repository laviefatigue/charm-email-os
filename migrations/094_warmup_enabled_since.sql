-- Migration 094: Continuous warmup tracking
--
-- Why this exists
-- ───────────────
-- Phase 3 of the 2026-04-27 tagging-kill overhaul requires graduating an
-- inbox only after warmup has been continuously enabled for 14 business
-- days. Without a transition timestamp we can only check the current
-- value of warmup_enabled, which masks the case "warmup paused for a
-- week, then resumed yesterday — should still be incubating."
--
-- This migration adds:
--   sender_accounts.warmup_enabled_since TIMESTAMPTZ
--     Set to NOW() when warmup_enabled transitions from FALSE/NULL → TRUE.
--     Cleared (NULL) when warmup_enabled transitions to FALSE.
--     Maintained by a trigger so application code does not need to know
--     about it.
--
--   sender_accounts.warmup_disabled_at TIMESTAMPTZ
--     Snapshot of when the most recent FALSE transition happened, used
--     by the daily reconciliation alert to flag inboxes whose warmup
--     was disabled silently and are still active in the fleet.
--
-- Backfill for existing rows: if warmup_enabled = TRUE and
-- warmup_started_at IS NOT NULL, treat the original warmup_started_at as
-- the warmup_enabled_since value. This is a best-effort approximation
-- since we have no history; new graduations from this point onward will
-- have accurate continuous tracking.

ALTER TABLE sender_accounts
    ADD COLUMN IF NOT EXISTS warmup_enabled_since TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS warmup_disabled_at   TIMESTAMPTZ;

COMMENT ON COLUMN sender_accounts.warmup_enabled_since IS
    'Timestamp of most recent FALSE/NULL → TRUE transition of warmup_enabled. '
    'Used by lifecycle_tag_sync to enforce continuous-enabled requirement '
    'for graduation. Maintained by trigger track_warmup_enabled_transition.';
COMMENT ON COLUMN sender_accounts.warmup_disabled_at IS
    'Timestamp of most recent TRUE → FALSE transition of warmup_enabled. '
    'Used by daily reconciliation to alert on silent warmup disablement '
    'on otherwise-active inboxes.';

-- One-time backfill for historical rows that already have warmup running.
UPDATE sender_accounts
SET warmup_enabled_since = warmup_started_at
WHERE warmup_enabled IS TRUE
  AND warmup_started_at IS NOT NULL
  AND warmup_enabled_since IS NULL;

-- Trigger function: maintain transition timestamps automatically.
CREATE OR REPLACE FUNCTION track_warmup_enabled_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF (NEW.warmup_enabled IS TRUE)
       AND (OLD.warmup_enabled IS DISTINCT FROM TRUE) THEN
        -- FALSE/NULL → TRUE: stamp the moment warmup was turned on.
        NEW.warmup_enabled_since := NOW();
        NEW.warmup_disabled_at := NULL;
    ELSIF (NEW.warmup_enabled IS NOT TRUE)
          AND (OLD.warmup_enabled IS TRUE) THEN
        -- TRUE → FALSE/NULL: clear since-timestamp, record disable moment.
        NEW.warmup_enabled_since := NULL;
        NEW.warmup_disabled_at := NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_track_warmup_enabled_transition ON sender_accounts;
CREATE TRIGGER trg_track_warmup_enabled_transition
    BEFORE UPDATE OF warmup_enabled ON sender_accounts
    FOR EACH ROW
    WHEN (OLD.warmup_enabled IS DISTINCT FROM NEW.warmup_enabled)
    EXECUTE FUNCTION track_warmup_enabled_transition();

-- Index supports the lifecycle_tag_sync graduation query and the daily
-- reconciliation "warmup disabled silently" detector.
CREATE INDEX IF NOT EXISTS idx_sender_accounts_warmup_enabled_since
    ON sender_accounts (warmup_enabled_since)
    WHERE warmup_enabled IS TRUE;

CREATE INDEX IF NOT EXISTS idx_sender_accounts_warmup_disabled_at
    ON sender_accounts (warmup_disabled_at)
    WHERE warmup_enabled IS NOT TRUE
      AND inbox_state = 'live';
