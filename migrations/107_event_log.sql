-- Migration 107: event_log table for event-driven architecture
--
-- Plan: docs/plans/event-driven-architecture.md
--
-- Purpose
-- ───────
-- Durable, queryable event queue for the two-tier event-driven design.
-- Triggers (migration 108) will INSERT rows here in the same transaction
-- as the state change that produced them. Listeners read by LISTEN/NOTIFY
-- in real time + drain unprocessed rows on reconnect.
--
-- Two-stage tracking is the key feature: every event records BOTH "what
-- should happen" (status='emitted', emitted_at) AND "did it occur"
-- (status='completed' / 'failed' / 'orphaned', handler_started_at,
-- handler_completed_at). If a handler claims an event but never finishes,
-- the watchdog catches it and either re-emits or escalates.
--
-- Per-workspace partitioning (load-bearing rule)
-- ──────────────────────────────────────────────
-- Every EB-touching operation uses workspace-scoped API keys per ADR-006.
-- The CHECK constraint below enforces that any tag_op event MUST carry
-- workspace_id, so the Tier 2 batch worker can route it correctly.
-- A handler that tries to enqueue a tag_op without workspace_id will
-- fail at the DB layer.
--
-- Status lifecycle
-- ────────────────
--   emitted    → trigger fired, no handler yet
--   processing → handler claimed it (SELECT FOR UPDATE), working
--   completed  → handler finished successfully
--   failed     → handler raised; retry_after may be set
--   orphaned   → claimed but never completed (watchdog marks)
--   pending    → for tag_op events: waiting in batch queue
--   cancelled  → superseded or workspace deactivated

BEGIN;

CREATE TABLE IF NOT EXISTS event_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- WHAT
    event_type      TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    entity_id       UUID NOT NULL,

    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- TWO-STAGE TRACKING
    emitted_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    handler_started_at      TIMESTAMP,
    handler_completed_at    TIMESTAMP,

    -- STATUS LIFECYCLE
    status          TEXT NOT NULL DEFAULT 'emitted',

    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    retry_after     TIMESTAMP,

    -- WORKSPACE SCOPE (NOT NULL for tag_op events)
    workspace_id    UUID REFERENCES workspaces(id),

    handler_name    TEXT,
    metadata        JSONB DEFAULT '{}'::jsonb,

    -- INVARIANTS

    -- Tag op events MUST have workspace_id so the Tier 2 batch worker
    -- can route them through the workspace-scoped EB key. ADR-006 rule.
    CONSTRAINT event_log_tag_op_requires_workspace
        CHECK (
            event_type NOT LIKE 'tag_op_%'
            OR workspace_id IS NOT NULL
        ),

    -- Status must be one of the defined lifecycle values
    CONSTRAINT event_log_valid_status
        CHECK (status IN (
            'emitted', 'processing', 'completed',
            'failed', 'orphaned', 'pending', 'cancelled'
        )),

    -- Handler-completed events must have a handler_started_at
    CONSTRAINT event_log_completion_requires_start
        CHECK (
            handler_completed_at IS NULL
            OR handler_started_at IS NOT NULL
        )
);

-- INDEXES

-- Fast scan for unprocessed events on listener reconnect
CREATE INDEX IF NOT EXISTS idx_event_log_status_emitted
    ON event_log (status, emitted_at)
    WHERE status IN ('emitted', 'processing', 'pending');

-- Tag op queue per workspace (Tier 2 batch worker)
CREATE INDEX IF NOT EXISTS idx_event_log_pending_tag_ops
    ON event_log (workspace_id, emitted_at)
    WHERE status = 'pending' AND event_type LIKE 'tag_op_%';

-- Watchdog: find events that started processing but never completed
CREATE INDEX IF NOT EXISTS idx_event_log_orphan_check
    ON event_log (handler_started_at)
    WHERE status = 'processing';

-- Entity lookup ("what happened to inbox X?")
CREATE INDEX IF NOT EXISTS idx_event_log_entity
    ON event_log (entity_type, entity_id, emitted_at DESC);

-- Workspace timeline ("what happened in workspace W?")
CREATE INDEX IF NOT EXISTS idx_event_log_workspace
    ON event_log (workspace_id, emitted_at DESC)
    WHERE workspace_id IS NOT NULL;

-- Failed events for diagnostics
CREATE INDEX IF NOT EXISTS idx_event_log_failed
    ON event_log (event_type, emitted_at DESC)
    WHERE status = 'failed';

-- COMMENTS

COMMENT ON TABLE event_log IS
    'Durable event queue + audit log for event-driven architecture. '
    'Every state change writes a row in same transaction. Listener reads via LISTEN/NOTIFY. '
    'See docs/plans/event-driven-architecture.md.';

COMMENT ON COLUMN event_log.event_type IS
    'Event channel name. Convention: snake_case verb_noun. Examples: '
    'inbox_pickup, kill_queued, inbox_died, pool_changed, domain_burned, '
    'tag_op_attach, tag_op_remove, bounce_observed, sender_ban_detected, '
    'disconnect_observed, reconnected, graduated, package_assigned, workspace_paused.';

COMMENT ON COLUMN event_log.status IS
    'emitted=fired, processing=claimed, completed=done, failed=raised, '
    'orphaned=claimed-but-stalled, pending=tag-op-queued, cancelled=superseded.';

COMMENT ON COLUMN event_log.workspace_id IS
    'Required for tag_op_* events (CHECK constraint). Optional for other event types.';

COMMIT;

-- Verify (read-only):
-- SELECT COUNT(*) FROM event_log;
-- \d+ event_log
