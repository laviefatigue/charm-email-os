-- Migration 096: Fix warmup_enabled_since trigger to handle INSERT
--
-- Migration 094 created `track_warmup_enabled_transition` to stamp
-- `warmup_enabled_since` on FALSE/NULL → TRUE transitions of
-- `warmup_enabled`. The trigger fired only on UPDATE, which means new
-- inboxes inserted by sync_accounts.upsert would never get the column
-- populated even though they're inserted with `warmup_enabled=TRUE`.
--
-- Since lifecycle_tag_sync's graduation eligibility check requires
-- `warmup_enabled_since IS NOT NULL`, every newly-synced inbox would
-- be permanently ineligible to graduate until something else flipped
-- warmup_enabled off-then-on.
--
-- This migration:
--   1. Rewrites the function to branch on TG_OP so OLD is only read
--      when it actually exists (UPDATE).
--   2. Drops and recreates the trigger to fire on INSERT OR UPDATE.

CREATE OR REPLACE FUNCTION track_warmup_enabled_transition()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        -- New row: stamp warmup_enabled_since iff warmup_enabled is TRUE.
        -- Inserts with warmup_enabled=FALSE leave both timestamps NULL.
        IF NEW.warmup_enabled IS TRUE THEN
            NEW.warmup_enabled_since := NOW();
            NEW.warmup_disabled_at := NULL;
        END IF;
        RETURN NEW;
    END IF;

    -- TG_OP = 'UPDATE' from here: OLD is defined.
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

-- Note: BEFORE INSERT OR UPDATE OF warmup_enabled.
-- The WHEN clause from migration 094 is dropped because it referenced
-- OLD.warmup_enabled which is undefined on INSERT. Filtering for
-- relevant transitions now happens inside the function body.
CREATE TRIGGER trg_track_warmup_enabled_transition
    BEFORE INSERT OR UPDATE OF warmup_enabled ON sender_accounts
    FOR EACH ROW
    EXECUTE FUNCTION track_warmup_enabled_transition();

-- Backfill existing inboxes that were inserted before this fix landed.
-- Same rule as migration 094's backfill — but applies to any rows that
-- still have NULL warmup_enabled_since despite warmup_enabled=TRUE.
UPDATE sender_accounts
SET warmup_enabled_since = COALESCE(warmup_started_at, NOW())
WHERE warmup_enabled IS TRUE
  AND warmup_enabled_since IS NULL;
