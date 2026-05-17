-- Migration 116: Operator action log — "all client work is context"
--
-- Why this exists
-- ───────────────
-- Per the 2026-05-16 design direction: every AE action (assign task, change
-- package, kill inbox, edit profile) becomes future context for agents. The
-- existing event_log captures DAEMON events. operator_actions captures the
-- human side. Together with agent_runs (later migration when runtime ships)
-- they form the complete activity stream the agent sees on next heartbeat.
--
-- Append-only. Indexed for "show me everything done to this workspace in the
-- last 7 days" + "show me everything done by this operator today".

CREATE TABLE IF NOT EXISTS operator_actions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id       UUID,                           -- Operator who performed the action
    actor_label         TEXT,                            -- Human-readable label if user system not authoritative
    action              TEXT NOT NULL,
                        -- e.g. 'task.create', 'task.assign', 'task.status_change',
                        -- 'task.comment', 'package.assign', 'inbox.kill', 'client.edit',
                        -- 'workspace.pause_pool_transitions', 'document.update'
    entity_type         TEXT NOT NULL,
                        -- 'task' | 'agent' | 'workspace' | 'client' | 'inbox' | 'domain'
                        -- | 'subscription' | 'document' | 'comment'
    entity_id           UUID,                            -- The thing acted on
    workspace_id        UUID REFERENCES workspaces(id) ON DELETE SET NULL,
                        -- Convenience FK so per-workspace activity is one query
    details             JSONB NOT NULL DEFAULT '{}'::jsonb,
                        -- Action-specific payload: before/after values, params, etc.
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE operator_actions IS
    'Append-only log of operator (AE) mutations. Feeds the "all client work is context" '
    'promise — agents read this on their next heartbeat to see what humans have been doing. '
    'Distinct from event_log (daemon-side) and agent_runs (agent-side).';

COMMENT ON COLUMN operator_actions.action IS
    'Dotted convention: entity.verb. Lowercase. Examples: task.create, task.assign, '
    'package.assign, inbox.kill, workspace.pause_pool_transitions, document.update.';

COMMENT ON COLUMN operator_actions.details IS
    'Action-specific JSONB payload. Convention: include "before" and "after" keys when '
    'mutating existing state. Include "params" key for create actions. Free-form beyond that.';

CREATE INDEX IF NOT EXISTS idx_operator_actions_workspace_created
    ON operator_actions (workspace_id, created_at DESC)
    WHERE workspace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_operator_actions_actor_created
    ON operator_actions (actor_user_id, created_at DESC)
    WHERE actor_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_operator_actions_entity
    ON operator_actions (entity_type, entity_id)
    WHERE entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_operator_actions_action_created
    ON operator_actions (action, created_at DESC);
