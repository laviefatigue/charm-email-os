-- Migration 118: Task interactions — paperclip-pattern request_confirmation surface
--
-- Why this exists
-- ───────────────
-- Paperclip distinguishes COMMENTS (conversational) from INTERACTIONS
-- (structured ask: "approve / reject with reason"). When an agent (or operator)
-- needs a formal yes/no on a proposed action, it posts an interaction. UI
-- renders interactions as bold approval cards with Approve/Reject buttons,
-- not as comments in the thread.
--
-- Examples for Charm:
--   • Data Analyst: "Approve this rotation slate of 5 domains?"
--   • Researcher: "Use methodology A or B for this analysis?"
--   • Day AI Reviewer: "Surface this client complaint to operator now?"
--   • GitHub Admin: "Merge this PR with conflicts?"
--
-- Idempotency: same logical question shouldn't double-fire. idempotency_key
-- enforces uniqueness per-task-per-question.
--
-- Continuation policy: when operator decides, what happens?
--   • wake_assignee: notify the agent (when runtime ships) to resume work
--   • update_status: auto-transition the task on approve/reject
--   • none: just record the decision

CREATE TABLE IF NOT EXISTS task_interactions (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                  UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    kind                     TEXT NOT NULL DEFAULT 'request_confirmation',
                             -- 'request_confirmation' is the only kind for v1.
                             -- Future: 'request_revision', 'multi_choice', 'data_input'
    idempotency_key          TEXT NOT NULL,
                             -- Prevents duplicate interactions for the same logical ask
    continuation_policy      TEXT NOT NULL DEFAULT 'wake_assignee',
                             -- 'wake_assignee' | 'update_status' | 'none'
    payload                  JSONB NOT NULL,
                             -- Structured ask. Convention for request_confirmation:
                             -- {
                             --   "version": 1,
                             --   "prompt": "Approve rotation slate?",
                             --   "summary": "Burn rate +18% MoM…",
                             --   "data": { … action-specific payload … },
                             --   "acceptLabel": "Approve",
                             --   "rejectLabel": "Reject",
                             --   "rejectRequiresReason": true,
                             --   "supersedeOnUserComment": false,
                             --   "citedContext": [{ path, commitSha, relevance }]
                             -- }
    status                   TEXT NOT NULL DEFAULT 'pending',
                             -- 'pending' | 'approved' | 'rejected' | 'superseded' | 'expired'
    created_by_agent_id      UUID REFERENCES agents(id),
    created_by_user_id       UUID,
    decided_at               TIMESTAMPTZ,
    decided_by_user_id       UUID,                              -- operator who decided
    decided_by_agent_id      UUID REFERENCES agents(id),        -- rare (agent-vs-agent gate)
    decision_reason          TEXT,                              -- required if rejectRequiresReason
    expires_at               TIMESTAMPTZ,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT task_interactions_kind_valid CHECK (
        kind IN ('request_confirmation', 'request_revision', 'multi_choice', 'data_input')
    ),
    CONSTRAINT task_interactions_status_valid CHECK (
        status IN ('pending', 'approved', 'rejected', 'superseded', 'expired')
    ),
    CONSTRAINT task_interactions_continuation_valid CHECK (
        continuation_policy IN ('wake_assignee', 'update_status', 'none')
    ),
    CONSTRAINT task_interactions_decided_consistency CHECK (
        (status = 'pending' AND decided_at IS NULL)
        OR (status IN ('approved', 'rejected', 'superseded', 'expired') AND
            (decided_at IS NOT NULL OR status IN ('superseded', 'expired')))
    ),
    UNIQUE (task_id, idempotency_key)
);

COMMENT ON TABLE task_interactions IS
    'Structured approval/decision cards on tasks. Distinct from task_comments '
    '(conversational). Renders in UI as bold-shadow cards with Approve/Reject. '
    'Lifted verbatim from paperclip''s request_confirmation pattern.';

COMMENT ON COLUMN task_interactions.idempotency_key IS
    'Unique per (task_id, key). Prevents agent-retry from creating duplicate '
    'asks. Convention: <action>:<entity>:<version> e.g. "rotation:domain-set-42:v1".';

COMMENT ON COLUMN task_interactions.continuation_policy IS
    'wake_assignee: notify the assignee agent to resume work on decide (default). '
    'update_status: auto-transition the task on approve (e.g. to done) or '
    'reject (back to in_progress). none: record decision only.';

COMMENT ON COLUMN task_interactions.payload IS
    'Action-specific JSONB. For request_confirmation: prompt, summary, data, '
    'acceptLabel, rejectLabel, rejectRequiresReason, citedContext. UI renders '
    'this as the operator-facing card.';

CREATE INDEX IF NOT EXISTS idx_task_interactions_task_status
    ON task_interactions (task_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_task_interactions_pending
    ON task_interactions (created_at DESC)
    WHERE status = 'pending';

-- updated_at trigger
CREATE OR REPLACE FUNCTION task_interactions_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    -- Auto-stamp decided_at when status moves from pending
    IF NEW.status != 'pending' AND OLD.status = 'pending' AND NEW.decided_at IS NULL THEN
        NEW.decided_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_task_interactions_touch_updated_at ON task_interactions;
CREATE TRIGGER trg_task_interactions_touch_updated_at
    BEFORE UPDATE ON task_interactions
    FOR EACH ROW
    EXECUTE FUNCTION task_interactions_touch_updated_at();
