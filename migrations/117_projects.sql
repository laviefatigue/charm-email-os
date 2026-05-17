-- Migration 117: Projects — long-term initiatives that contain tasks
--
-- Why this exists
-- ───────────────
-- Phase 2 of the platform redesign (2026-05-16): tasks need a parent container
-- so AEs can plan / track multi-task initiatives ("Hypertide Q3 capacity ramp",
-- "MSFT deprecation for Northwind", "ACME onboarding"). Projects also feed the
-- Gantt timeline view — bars positioned by start_at → target_end_at.
--
-- Hierarchy: Workspace → Project → Task → Subtask (parent_task_id already in 114)
--
-- Adds: projects table, tasks.project_id FK, tasks.start_at + estimated_hours
-- for Gantt placement, project_progress view for rollup.

-- ──────────────────────────────────────────────────────────────────────────────
-- projects table
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id             UUID REFERENCES workspaces(id) ON DELETE SET NULL,
                             -- NULL = cross-workspace (rare, but allowed)
    name                     TEXT NOT NULL,
    description              TEXT,                          -- Markdown — project brief, success criteria
    status                   TEXT NOT NULL DEFAULT 'planning',
                             -- 'planning' | 'active' | 'paused' | 'done' | 'cancelled'
    priority                 TEXT NOT NULL DEFAULT 'medium',
                             -- 'low' | 'medium' | 'high' | 'urgent'
    color                    TEXT,                          -- Hex/HSL hint for Gantt bar color
    owner_agent_id           UUID REFERENCES agents(id) ON DELETE SET NULL,
                             -- Optional "primary responsible agent"
    owner_user_id            UUID,                          -- Operator who owns it
    start_at                 TIMESTAMPTZ,                   -- Target start
    target_end_at            TIMESTAMPTZ,                   -- Target end (Gantt right edge)
    actual_end_at            TIMESTAMPTZ,                   -- Set when status → done
    created_by_user_id       UUID,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT projects_status_valid CHECK (
        status IN ('planning', 'active', 'paused', 'done', 'cancelled')
    ),
    CONSTRAINT projects_priority_valid CHECK (
        priority IN ('low', 'medium', 'high', 'urgent')
    ),
    CONSTRAINT projects_dates_valid CHECK (
        start_at IS NULL OR target_end_at IS NULL OR start_at <= target_end_at
    )
);

COMMENT ON TABLE projects IS
    'Long-term initiatives that group tasks. Project → Tasks → Subtasks. Feeds '
    'the Gantt timeline view via start_at + target_end_at. Workspace-scoped by '
    'convention (workspace_id NULL is allowed for cross-client initiatives but rare).';

CREATE INDEX IF NOT EXISTS idx_projects_workspace_status ON projects (workspace_id, status);
CREATE INDEX IF NOT EXISTS idx_projects_active ON projects (status) WHERE status IN ('planning', 'active', 'paused');
CREATE INDEX IF NOT EXISTS idx_projects_timeline ON projects (start_at, target_end_at)
    WHERE start_at IS NOT NULL AND target_end_at IS NOT NULL;

-- updated_at + actual_end_at trigger
CREATE OR REPLACE FUNCTION projects_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    -- Auto-set actual_end_at when status transitions to done/cancelled
    IF NEW.status IN ('done', 'cancelled') AND OLD.status NOT IN ('done', 'cancelled') THEN
        IF NEW.actual_end_at IS NULL THEN
            NEW.actual_end_at = NOW();
        END IF;
    END IF;
    IF NEW.status NOT IN ('done', 'cancelled') AND OLD.status IN ('done', 'cancelled') THEN
        NEW.actual_end_at = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_projects_touch_updated_at ON projects;
CREATE TRIGGER trg_projects_touch_updated_at
    BEFORE UPDATE ON projects
    FOR EACH ROW
    EXECUTE FUNCTION projects_touch_updated_at();

-- ──────────────────────────────────────────────────────────────────────────────
-- Extend tasks: project_id + Gantt placement fields
-- ──────────────────────────────────────────────────────────────────────────────
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE SET NULL;

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS start_at TIMESTAMPTZ;

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS estimated_hours NUMERIC(6, 2);
    -- For Gantt bar width when target_end is not set explicitly via due_at

COMMENT ON COLUMN tasks.project_id IS
    'Parent project. NULL = orphan task (allowed for quick one-offs).';

COMMENT ON COLUMN tasks.start_at IS
    'Planned start. Used as Gantt bar left edge. NULL = unscheduled.';

COMMENT ON COLUMN tasks.estimated_hours IS
    'Effort estimate. Used as Gantt bar width when due_at is absent. '
    'A 4h task starting Mon 9am draws a bar from Mon 9am to Mon 1pm.';

CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks (project_id) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_timeline ON tasks (start_at)
    WHERE start_at IS NOT NULL AND status NOT IN ('done', 'blocked');

-- ──────────────────────────────────────────────────────────────────────────────
-- project_progress view — rollup of tasks under each project
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW project_progress AS
SELECT
    p.id                            AS project_id,
    p.workspace_id                  AS workspace_id,
    p.name                          AS name,
    p.status                        AS project_status,
    p.start_at                      AS planned_start,
    p.target_end_at                 AS planned_end,
    p.actual_end_at                 AS actual_end,
    COUNT(t.id)                     AS total_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'done')              AS done_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'in_progress')       AS in_progress_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'in_review')         AS in_review_tasks,
    COUNT(t.id) FILTER (WHERE t.status = 'blocked')           AS blocked_tasks,
    COUNT(t.id) FILTER (
        WHERE t.due_at IS NOT NULL
          AND t.due_at < NOW()
          AND t.status NOT IN ('done', 'blocked')
    )                                                          AS overdue_tasks,
    CASE
        WHEN COUNT(t.id) = 0 THEN 0
        ELSE ROUND(
            (COUNT(t.id) FILTER (WHERE t.status = 'done')::NUMERIC / COUNT(t.id)) * 100,
            1
        )
    END                                                        AS percent_done,
    MIN(t.start_at)                                            AS earliest_task_start,
    MAX(COALESCE(t.due_at, t.start_at))                        AS latest_task_end
FROM projects p
LEFT JOIN tasks t ON t.project_id = p.id
GROUP BY p.id, p.workspace_id, p.name, p.status, p.start_at, p.target_end_at, p.actual_end_at;

COMMENT ON VIEW project_progress IS
    'Per-project rollup. percent_done, blocked + overdue counts, derived timeline bounds. '
    'Cheap LEFT JOIN — fine for direct query from the projects detail page. '
    'Promote to materialized view if hot path needs it.';
