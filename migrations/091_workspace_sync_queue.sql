-- Migration 091: Workspace Sync Queue
--
-- Implements a persistent job queue for concurrent, workspace-scoped data sync.
--
-- Problem this solves:
--   The old sync worker processed workspaces sequentially using a single shared
--   EmailBison client with switch_workspace() calls between each workspace.
--   With 9 workspaces and 5 sync types, this serialised ~45 API sessions end-to-end.
--
-- New model:
--   Each workspace has a scoped API key (workspace_api_keys, migration 089).
--   Workspace-scoped keys are context-bound — no switch_workspace() needed.
--   Jobs are claimed atomically with FOR UPDATE SKIP LOCKED, enabling true
--   concurrent processing at a configurable batch size (default 3).
--
-- Design notes:
--   - Partial unique index on (workspace_id, sync_type) WHERE status='pending'
--     prevents duplicate pending jobs; ON CONFLICT DO NOTHING is safe.
--   - FOR UPDATE SKIP LOCKED in the batch consumer prevents double-claiming
--     across multiple worker instances (future horizontal scaling).
--   - Failed jobs reappear in the scheduler on the next tick because the
--     scheduler checks sync_status.last_successful_sync, not the queue table.
--     Natural retry with no explicit retry counter needed.
--   - High-priority jobs (force-refresh from client dashboard) use priority=10;
--     normal scheduler-inserted jobs use priority=0.
--
-- Related tables:
--   workspace_api_keys  (089) — source of per-workspace EB tokens
--   sync_status         (020) — tracks last successful sync per workspace+type
--   sync_audit_log      (020) — per-job audit trail (unchanged)

CREATE TABLE IF NOT EXISTS workspace_sync_queue (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID        NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    sync_type        VARCHAR(20) NOT NULL,
        -- Valid values: 'accounts' | 'campaigns' | 'events' | 'warmup' | 'engagement'
    status           VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- Life cycle:  pending → running → complete | failed
    priority         INTEGER     NOT NULL DEFAULT 0,
        -- Normal scheduler jobs = 0. Force-refresh from dashboard = 10.
        -- Consumer orders by: priority DESC, queued_at ASC.
    is_force_refresh BOOLEAN     NOT NULL DEFAULT FALSE,
        -- TRUE when job was triggered by client dashboard refresh request.
        -- Used for metrics and to skip the "already synced recently" suppression.
    queued_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    error_message    TEXT,
        -- Last exception message. Populated on status='failed'.
    records_synced   INTEGER
        -- Records processed by the sync module. Populated on status='complete'.
);

-- ── Primary consumer index ────────────────────────────────────────────────────
-- Covers the SELECT in process_pending_batch():
--   WHERE status = 'pending'
--   ORDER BY priority DESC, queued_at ASC
--   FOR UPDATE SKIP LOCKED
CREATE INDEX IF NOT EXISTS idx_sync_queue_pending_consumer
    ON workspace_sync_queue (priority DESC, queued_at ASC)
    WHERE status = 'pending';

-- ── Deduplication guard ───────────────────────────────────────────────────────
-- Ensures at most one pending job per (workspace, sync_type).
-- insert_pending_job() uses ON CONFLICT DO NOTHING against this index.
-- Once a job transitions to running/complete/failed the constraint no longer
-- applies, so the next scheduler tick can queue the workspace again.
CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_queue_no_dup_pending
    ON workspace_sync_queue (workspace_id, sync_type)
    WHERE status = 'pending';

-- ── Status monitoring index ───────────────────────────────────────────────────
-- Powers GET /api/sync/workspaces/{id}/status and queue depth dashboards.
CREATE INDEX IF NOT EXISTS idx_sync_queue_workspace_status
    ON workspace_sync_queue (workspace_id, status, queued_at DESC);

-- ── Cleanup index ─────────────────────────────────────────────────────────────
-- Retention task prunes jobs older than 30 days: WHERE completed_at < NOW() - 30d
CREATE INDEX IF NOT EXISTS idx_sync_queue_completed_at
    ON workspace_sync_queue (completed_at)
    WHERE status IN ('complete', 'failed');

-- ── Column comments ───────────────────────────────────────────────────────────
COMMENT ON TABLE workspace_sync_queue IS
    'Job queue for concurrent per-workspace EmailBison data sync. '
    'Scheduler inserts pending jobs; consumer claims batches via FOR UPDATE SKIP LOCKED.';

COMMENT ON COLUMN workspace_sync_queue.sync_type IS
    'Sync module to run: accounts | campaigns | events | warmup | engagement';

COMMENT ON COLUMN workspace_sync_queue.status IS
    'Job lifecycle: pending → running → complete | failed';

COMMENT ON COLUMN workspace_sync_queue.priority IS
    'Consumer sort key. Normal=0, force-refresh=10. Higher = processed first.';

COMMENT ON COLUMN workspace_sync_queue.is_force_refresh IS
    'TRUE when enqueued by client dashboard refresh endpoint (POST /api/sync/workspaces/{id}/refresh).';

COMMENT ON COLUMN workspace_sync_queue.error_message IS
    'Exception message from the sync module. NULL on success.';
