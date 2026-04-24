-- Migration 093: Day.AI watcher state tables
--
-- Supports the dayai-watcher service (HireCharm/dayai-watcher):
--   1. Polls Day.AI every N minutes for opportunities in the "Closed Won" stage
--   2. Diffs against dayai_watcher_state to find newly-won opportunities
--   3. POSTs each newly-won opp to charm-email-os /api/clients/pending-from-dayai
--   4. Records each poll cycle in dayai_watcher_runs for audit trail
--
-- Design: see DECISION_dayai_integration.md §4.4 in charm-kb.
-- Watcher is stateless at the process level — Postgres is source of truth.
--
-- Prereq: none for this migration. It does NOT reference the clients table
-- yet because Gate 2 hasn't shipped client_id FK plumbing. The charm_client_id
-- column is prepared but nullable + FK-less until clients table has the
-- shape described in DECISION_client_identity.md.
--
-- Idempotent.

-- ============================================================================
-- dayai_watcher_state — one row per Day.AI opportunity ever observed
-- ============================================================================
-- Lifecycle of a row:
--   t=0   INSERT with first_seen_at=now, dayai_snapshot=full opp JSON,
--         sent_to_charm_at=NULL, charm_client_id=NULL
--   t=1   Watcher POSTs to charm-email-os, gets client_id back:
--         UPDATE sent_to_charm_at=now, charm_client_id=<uuid>
--   t=n   Subsequent polls: UPDATE dayai_snapshot + last_poll_saw_at
--         (keeps audit of latest observed state without double-processing)

CREATE TABLE IF NOT EXISTS dayai_watcher_state (
    opp_id              VARCHAR(64) PRIMARY KEY,
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_poll_saw_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_to_charm_at    TIMESTAMPTZ,
    charm_client_id     UUID,
    dayai_snapshot      JSONB NOT NULL,

    CONSTRAINT dayai_watcher_state_snapshot_is_object
      CHECK (jsonb_typeof(dayai_snapshot) = 'object')
);

-- Find unsent opps quickly (partial index — only indexes rows not yet posted).
CREATE INDEX IF NOT EXISTS idx_dayai_watcher_state_pending
  ON dayai_watcher_state(first_seen_at)
  WHERE sent_to_charm_at IS NULL;

-- Find opps linked to a specific Charm client (for reverse lookup during audit).
CREATE INDEX IF NOT EXISTS idx_dayai_watcher_state_charm_client
  ON dayai_watcher_state(charm_client_id)
  WHERE charm_client_id IS NOT NULL;

-- Find opps not seen in recent polls (staleness / opp left the won stage).
CREATE INDEX IF NOT EXISTS idx_dayai_watcher_state_last_seen
  ON dayai_watcher_state(last_poll_saw_at);

COMMENT ON TABLE dayai_watcher_state IS
  'One row per Day.AI opportunity the watcher has ever observed in a watched stage. Source of truth for detection idempotency.';
COMMENT ON COLUMN dayai_watcher_state.opp_id IS
  'Day.AI opportunity objectId (UUID string). Primary key.';
COMMENT ON COLUMN dayai_watcher_state.first_seen_at IS
  'When the watcher first detected this opp in a watched stage.';
COMMENT ON COLUMN dayai_watcher_state.last_poll_saw_at IS
  'Most recent poll cycle that observed this opp. Updated every poll while opp remains in watched stage.';
COMMENT ON COLUMN dayai_watcher_state.sent_to_charm_at IS
  'Non-null once the watcher successfully POSTed this opp to /api/clients/pending-from-dayai.';
COMMENT ON COLUMN dayai_watcher_state.charm_client_id IS
  'FK-pending-implementation to clients(id). Set after charm-email-os acknowledges the pending client creation.';
COMMENT ON COLUMN dayai_watcher_state.dayai_snapshot IS
  'Full Day.AI opportunity object (JSONB) — preserved for audit + replay if charm-email-os is rebuilt.';

-- ============================================================================
-- dayai_watcher_runs — one row per poll cycle (audit + observability)
-- ============================================================================

CREATE TABLE IF NOT EXISTS dayai_watcher_runs (
    id                  BIGSERIAL PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at            TIMESTAMPTZ,
    opportunities_seen  INT NOT NULL DEFAULT 0,
    newly_won           INT NOT NULL DEFAULT 0,
    sent_to_charm       INT NOT NULL DEFAULT 0,
    errors              INT NOT NULL DEFAULT 0,
    error_messages      TEXT[]
);

-- Find recent runs / check if watcher has been polling.
CREATE INDEX IF NOT EXISTS idx_dayai_watcher_runs_started
  ON dayai_watcher_runs(started_at DESC);

-- Find failed runs for diagnostics.
CREATE INDEX IF NOT EXISTS idx_dayai_watcher_runs_errors
  ON dayai_watcher_runs(started_at DESC)
  WHERE errors > 0;

COMMENT ON TABLE dayai_watcher_runs IS
  'Audit log of watcher poll cycles. One row per invocation. Supports health checks + backfill reasoning.';
COMMENT ON COLUMN dayai_watcher_runs.started_at IS
  'When the poll cycle started (set on INSERT). Every run has a row, even if it crashes before ending.';
COMMENT ON COLUMN dayai_watcher_runs.ended_at IS
  'When the poll cycle finished (set on UPDATE at end). NULL = still running or crashed mid-cycle.';
COMMENT ON COLUMN dayai_watcher_runs.opportunities_seen IS
  'Total opps returned by the Day.AI query this cycle (regardless of previously-seen state).';
COMMENT ON COLUMN dayai_watcher_runs.newly_won IS
  'Count of opps this cycle that were NOT in dayai_watcher_state before this run.';
COMMENT ON COLUMN dayai_watcher_runs.sent_to_charm IS
  'Count of opps successfully POSTed to charm-email-os this cycle. In DETECT_ONLY=true mode, stays 0.';
COMMENT ON COLUMN dayai_watcher_runs.errors IS
  'Count of per-opp errors during this cycle. 0 = clean run; >0 = partial failure.';
COMMENT ON COLUMN dayai_watcher_runs.error_messages IS
  'Array of human-readable error strings. May be NULL if errors=0. Length caps not enforced — keep error messages short.';

-- ============================================================================
-- Configuration reference (informational only — no schema impact)
-- ============================================================================
-- The watcher reads these env vars in production Coolify:
--   WATCHED_WON_STAGE_IDS  = "bef2d697-5f90-4b8e-a421-b6ee3e359aed"
--                            (Charm's Sales Pipeline "Closed Won" stage ID,
--                             discovered 2026-04-23 via scripts/discover-stages.ts)
--   CHARM_API_URL          = "https://api.wizardgrimoire.cloud"
--   CHARM_API_TOKEN        = <bearer token for /api/clients/pending-from-dayai>
--   DETECT_ONLY            = "true" during initial 1-2 week observation phase
--
-- See HireCharm/dayai-watcher/.env.example for the full list.
