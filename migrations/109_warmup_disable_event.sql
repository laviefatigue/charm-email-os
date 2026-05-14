-- Migration 109: Add warmup_disable to the workspace-scoped event types.
--
-- Plan F: warmup-disable on kill (event-driven). Closes the post-kill
-- bleed where dead inboxes still receive bounces because their EB
-- warmup_enabled flag is left TRUE.
--
-- See docs/plans/eod-campaign-reapply.md "Sister mechanism" + master
-- tracker INBOX-INTEGRITY-PROGRAM.md §3.5c.
--
-- Changes:
--   1. Drop existing event_log_tag_op_requires_workspace CHECK and
--      replace with a broader event_log_workspace_scoped_requires_workspace
--      that also covers warmup_disable. ADR-006 partitioning rule applies
--      to any event that produces an EB API call routed by workspace key.
--   2. Add a partial index for the Tier 2 worker's per-workspace
--      polling on warmup_disable events (mirrors the tag_op index).
--   3. Update column comments to reflect the new event type.
--
-- Idempotent: re-running drops + recreates the constraint and uses
-- IF NOT EXISTS for the index. Safe to apply multiple times.

BEGIN;

-- =====================================================================
-- 1. Replace CHECK constraint with the broader version
-- =====================================================================

ALTER TABLE event_log
    DROP CONSTRAINT IF EXISTS event_log_tag_op_requires_workspace;

-- Combined rule: tag_op_* OR warmup_disable both require workspace_id
-- because both produce an EB API call routed by workspace-scoped key
-- (ADR-006). If you add another workspace-scoped event_type later,
-- extend this constraint rather than adding a parallel one.
ALTER TABLE event_log
    ADD CONSTRAINT event_log_workspace_scoped_requires_workspace
    CHECK (
        (event_type NOT LIKE 'tag_op_%' AND event_type <> 'warmup_disable')
        OR workspace_id IS NOT NULL
    );

-- =====================================================================
-- 2. Index for Tier 2 polling on warmup_disable events
-- =====================================================================

-- Fast scan for pending warmup_disable events per workspace.
-- Mirrors idx_event_log_pending_tag_ops in shape.
CREATE INDEX IF NOT EXISTS idx_event_log_pending_warmup_disable
    ON event_log (workspace_id, emitted_at)
    WHERE status = 'pending' AND event_type = 'warmup_disable';

-- =====================================================================
-- 3. Update column comments
-- =====================================================================

COMMENT ON COLUMN event_log.event_type IS
    'Event channel name. Convention: snake_case verb_noun. Examples: '
    'inbox_pickup, kill_queued, inbox_died, pool_changed, domain_burned, '
    'tag_op_attach, tag_op_remove, warmup_disable, bounce_observed, '
    'sender_ban_detected, disconnect_observed, reconnected, graduated, '
    'package_assigned, workspace_paused.';

COMMENT ON COLUMN event_log.workspace_id IS
    'Required for tag_op_* and warmup_disable events (CHECK constraint). '
    'Optional for other event types. Both event-type families produce an '
    'EB API call routed by workspace-scoped key per ADR-006.';

COMMIT;
