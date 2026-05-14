-- Migration 111: EOD campaign reapply scaffolding (PR 1 of 3).
--
-- Adds the schema the v2 daemon needs to run in dry-run-only mode:
--   1. workspaces.eod_reapply_enabled  — per-workspace controlled rollout
--      flag (defaults FALSE; flipped to TRUE per workspace once ready).
--   2. campaign_reapply_jobs           — future-tense work queue. One row
--      per (campaign, run_local_date). Status enum tracks lifecycle.
--   3. Partial index on (scheduled_for) WHERE status='pending' for the
--      daemon's MIN(scheduled_for) scan.
--   4. Broaden event_log CHECK constraint to permit the new event_type
--      'campaign_reapply_due' (same pattern migration 109 used for
--      warmup_disable).
--
-- What we deliberately do NOT add in this migration:
--   - The DB trigger on emailbison_campaigns that auto-enqueues jobs on
--     schedule changes. Plan calls for it, but PR 1 ships the daemon
--     with a startup-time enqueuer; the trigger is a follow-up
--     optimization. Adding both at once muddies the dry-run validation.
--   - Any campaign_reapply_runs table. Per plan doc §"What we
--     deliberately don't add", event_log is the past-tense audit log;
--     a parallel runs table would be a second source of truth.
--
-- Idempotent: every step uses IF NOT EXISTS / DROP IF EXISTS so re-running
-- is safe. The CHECK constraint is dropped + recreated.

BEGIN;

-- =====================================================================
-- 1. Per-workspace rollout flag
-- =====================================================================

ALTER TABLE workspaces
    ADD COLUMN IF NOT EXISTS eod_reapply_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN workspaces.eod_reapply_enabled IS
    'When TRUE, the EOD reapply daemon will fire for active campaigns in '
    'this workspace at their end_time + buffer in the campaign''s tz. '
    'Default FALSE — flipped per workspace during controlled rollout. '
    'See docs/plans/eod-campaign-reapply.md.';

-- =====================================================================
-- 2. Job queue: campaign_reapply_jobs
-- =====================================================================

CREATE TABLE IF NOT EXISTS campaign_reapply_jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    campaign_id         UUID NOT NULL REFERENCES emailbison_campaigns(id) ON DELETE CASCADE,

    -- When the daemon should wake up to fire this campaign's reapply.
    -- Stored as TIMESTAMPTZ — daemon uses UTC for comparisons.
    scheduled_for       TIMESTAMPTZ NOT NULL,

    -- Idempotency key in the campaign's local timezone. A single UTC day
    -- can span two local dates (and vice versa), so using UTC date here
    -- would either double-fire or skip days near tz boundaries.
    run_local_date      DATE NOT NULL,

    -- Preserved for audit / debug. Daemon recomputes from campaign tz
    -- each time it (re)enqueues; persisted here so we can answer "what
    -- tz was this scheduled in?" after a campaign schedule change.
    run_local_tz        TEXT NOT NULL,

    -- Lifecycle:
    --   'pending'   — created by enqueuer; not yet claimed
    --   'flagged'   — daemon claimed via SELECT FOR UPDATE SKIP LOCKED;
    --                 corresponding event_log row exists
    --   'completed' — handler returned (any orchestrator status; details
    --                 in the event_log row via triggered_event_id)
    --   'failed'    — handler threw before completing (will be retried
    --                 by a future watchdog; PR 1 just logs)
    --   'skipped'   — workspace not enabled, campaign no longer active,
    --                 or time gate refused at fire time
    status              TEXT NOT NULL DEFAULT 'pending',

    -- Pointer to the past-tense audit row in event_log emitted on claim.
    -- NULL until the daemon claims the job.
    triggered_event_id  UUID,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    error_message       TEXT,

    -- Idempotency: at most one job per campaign per local date. Re-running
    -- the enqueuer is a no-op (handled by ON CONFLICT DO NOTHING upstream).
    CONSTRAINT campaign_reapply_jobs_unique_local_day
        UNIQUE (campaign_id, run_local_date),

    -- Status is a closed enum at the app layer; CHECK as a belt-and-braces
    -- guard against typos / direct INSERT mistakes.
    CONSTRAINT campaign_reapply_jobs_status_enum
        CHECK (status IN ('pending', 'flagged', 'completed', 'failed', 'skipped'))
);

COMMENT ON TABLE campaign_reapply_jobs IS
    'Future-tense work queue for the EOD campaign-reapply daemon. One '
    'row per (campaign, run_local_date). The daemon claims pending rows '
    'whose scheduled_for has arrived, emits a campaign_reapply_due event '
    'in event_log, runs the orchestrator, and writes the outcome back. '
    'Past-tense audit lives in event_log, not here.';

-- =====================================================================
-- 3. Partial index for daemon's next-job scan
-- =====================================================================

-- The daemon's tight loop is: SELECT MIN(scheduled_for) FROM jobs WHERE
-- status='pending'. Without a partial index this scans the table; with
-- this index it's O(log n) regardless of how many completed rows
-- accumulate. Mirrors idx_event_log_pending_warmup_disable in shape.
CREATE INDEX IF NOT EXISTS idx_campaign_reapply_jobs_pending
    ON campaign_reapply_jobs (scheduled_for)
    WHERE status = 'pending';

-- Secondary index for the workspace-scoped startup enqueuer. Used when
-- the daemon (re)enqueues today's jobs for an enabled workspace: it
-- needs to look up which campaigns already have a pending row.
CREATE INDEX IF NOT EXISTS idx_campaign_reapply_jobs_workspace_status
    ON campaign_reapply_jobs (workspace_id, status);

-- =====================================================================
-- 4. Broaden event_log CHECK to allow campaign_reapply_due
--    Same pattern as migration 109 used for warmup_disable.
-- =====================================================================

ALTER TABLE event_log
    DROP CONSTRAINT IF EXISTS event_log_workspace_scoped_requires_workspace;

ALTER TABLE event_log
    ADD CONSTRAINT event_log_workspace_scoped_requires_workspace
    CHECK (
        (event_type NOT LIKE 'tag_op_%'
         AND event_type <> 'warmup_disable'
         AND event_type <> 'campaign_reapply_due')
        OR workspace_id IS NOT NULL
    );

COMMENT ON COLUMN event_log.event_type IS
    'Event channel name. Convention: snake_case verb_noun. Workspace-scoped '
    'events (CHECK constraint enforces workspace_id IS NOT NULL): '
    'tag_op_attach, tag_op_remove, warmup_disable, campaign_reapply_due. '
    'Others: inbox_pickup, kill_queued, inbox_died, pool_changed, '
    'domain_burned, bounce_observed, sender_ban_detected, '
    'disconnect_observed, reconnected, graduated, package_assigned, '
    'workspace_paused.';

COMMIT;
