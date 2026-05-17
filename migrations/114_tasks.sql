-- Migration 114: Tasks (paperclip-pattern issues, Charm-renamed)
--
-- Why this exists
-- ───────────────
-- The Tasks surface is the platform's work-intake mechanism per the 2026-05-16
-- IA decision. Operator (AE) creates a task, assigns to one of the 4 specialized
-- agents (or leaves unassigned for claim), tracks lifecycle. Inbound client work
-- ("Hypertide needs a new burn analysis by Friday") becomes a task with workspace_id
-- set + assignee_agent_id picked.
--
-- Lifted from paperclip's `issues` model:
--   • Status enum: backlog → todo → in_progress → in_review → done (+ blocked)
--   • Priority: low | medium | high | urgent
--   • Atomic checkout: prevents two agents working same task simultaneously
--   • Parent/child hierarchy for delegation (Researcher creates child task for DataAnalyst)
--
-- Workspace association is OPTIONAL (workspace_id NULLABLE) — tasks can be
-- cross-client (e.g. "audit all five workspaces for capacity gaps") or
-- workspace-scoped (e.g. "burn analysis for Hypertide").

CREATE TABLE IF NOT EXISTS tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID REFERENCES workspaces(id) ON DELETE SET NULL,
                        -- NULL = cross-workspace task
    title               TEXT NOT NULL,
    description         TEXT,                           -- Markdown — full context for the agent
    status              TEXT NOT NULL DEFAULT 'todo',
                        -- backlog | todo | in_progress | in_review | done | blocked
    priority            TEXT NOT NULL DEFAULT 'medium',
                        -- low | medium | high | urgent
    assignee_agent_id   UUID REFERENCES agents(id) ON DELETE SET NULL,
                        -- NULL = unassigned (claim queue)
    parent_task_id      UUID REFERENCES tasks(id) ON DELETE SET NULL,
                        -- Hierarchy: child tasks roll up to parent
    source              TEXT NOT NULL DEFAULT 'operator',
                        -- 'operator' (AE-created) | 'agent' (delegated) | 'inbound' (client-originated) | 'system' (auto)
    inbound_origin      TEXT,                           -- Free-text: 'slack', 'email', 'call', etc. (when source='inbound')
    created_by_user_id  UUID,                           -- Operator who created (matches user system if exists)
    checkout_token      UUID,                           -- Set during atomic claim, NULL when free
    checkout_at         TIMESTAMPTZ,                    -- When the current claim was made
    started_at          TIMESTAMPTZ,                    -- First transition to in_progress
    closed_at           TIMESTAMPTZ,                    -- Transition to done/blocked
    due_at              TIMESTAMPTZ,                    -- Optional soft deadline
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT tasks_status_valid CHECK (
        status IN ('backlog', 'todo', 'in_progress', 'in_review', 'done', 'blocked')
    ),
    CONSTRAINT tasks_priority_valid CHECK (
        priority IN ('low', 'medium', 'high', 'urgent')
    ),
    CONSTRAINT tasks_source_valid CHECK (
        source IN ('operator', 'agent', 'inbound', 'system')
    ),
    -- Self-reference cycle protection: parent must not be self
    CONSTRAINT tasks_parent_not_self CHECK (parent_task_id IS NULL OR parent_task_id != id)
);

COMMENT ON TABLE tasks IS
    'Work units. Paperclip-pattern issues. Created by operators or delegated by agents. '
    'assignee_agent_id NULL means unassigned (any agent can claim via checkout). '
    'workspace_id NULL means cross-workspace task. Hierarchy via parent_task_id for delegation.';

COMMENT ON COLUMN tasks.checkout_token IS
    'Atomic claim token. Set when an agent (or operator) takes the task. Other agents '
    'see this as locked and skip. NULL = free for claim. Released on status change to '
    'done/blocked/backlog.';

COMMENT ON COLUMN tasks.source IS
    'Where the task came from. inbound = client request (paste from email/slack/call). '
    'agent = another agent delegated this child task. operator = AE created directly. '
    'system = auto-created by daemon (future).';

CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks (status, priority);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks (assignee_agent_id) WHERE assignee_agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks (workspace_id) WHERE workspace_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks (parent_task_id) WHERE parent_task_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_active ON tasks (status) WHERE status NOT IN ('done', 'blocked');
CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks (due_at) WHERE due_at IS NOT NULL AND status NOT IN ('done', 'blocked');

-- ──────────────────────────────────────────────────────────────────────────────
-- updated_at trigger + lifecycle timestamp auto-set
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION tasks_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    -- Auto-set started_at on first in_progress transition
    IF NEW.status = 'in_progress' AND OLD.status != 'in_progress' AND NEW.started_at IS NULL THEN
        NEW.started_at = NOW();
    END IF;
    -- Auto-set closed_at on done/blocked transition
    IF NEW.status IN ('done', 'blocked') AND OLD.status NOT IN ('done', 'blocked') THEN
        NEW.closed_at = NOW();
        NEW.checkout_token = NULL;
        NEW.checkout_at = NULL;
    END IF;
    -- Auto-clear closed_at if reopened
    IF NEW.status NOT IN ('done', 'blocked') AND OLD.status IN ('done', 'blocked') THEN
        NEW.closed_at = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tasks_touch_updated_at ON tasks;
CREATE TRIGGER trg_tasks_touch_updated_at
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION tasks_touch_updated_at();
