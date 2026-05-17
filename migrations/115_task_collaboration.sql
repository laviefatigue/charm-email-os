-- Migration 115: Task collaboration — comments + documents + document revisions
--
-- Why this exists
-- ───────────────
-- Per paperclip's pattern:
--   • Comments are the cross-agent communication channel. @-mentions wake the
--     mentioned agent (when runtime ships). Lightweight, append-only.
--   • Documents are the durable artifact store. Each task can have multiple
--     documents keyed by purpose: 'analysis', 'research_report', 'review_summary',
--     'repo_op', 'plan', 'notes'. Revisions are append-only for audit.
--
-- The DISTINCTION matters: reports go in documents (queryable, citable, revisioned).
-- Status updates and questions go in comments (fast, conversational).

-- ──────────────────────────────────────────────────────────────────────────────
-- task_comments — append-only conversation thread
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_comments (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                 UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    actor_type              TEXT NOT NULL,                  -- 'operator' | 'agent' | 'system'
    actor_agent_id          UUID REFERENCES agents(id),     -- when actor_type='agent'
    actor_user_id           UUID,                            -- when actor_type='operator'
    body_markdown           TEXT NOT NULL,
    mentioned_agent_ids     UUID[] NOT NULL DEFAULT '{}',   -- Parsed from @AgentName patterns
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT task_comments_actor_valid CHECK (
        actor_type IN ('operator', 'agent', 'system')
    ),
    CONSTRAINT task_comments_actor_consistency CHECK (
        (actor_type = 'agent' AND actor_agent_id IS NOT NULL) OR
        (actor_type = 'operator' AND actor_user_id IS NOT NULL) OR
        (actor_type = 'system')
    )
);

COMMENT ON TABLE task_comments IS
    'Conversation thread on tasks. Append-only. @-mentions are pre-parsed into '
    'mentioned_agent_ids for fast lookup (when the runtime is wired, mentioning an '
    'agent triggers a heartbeat).';

CREATE INDEX IF NOT EXISTS idx_task_comments_task_created ON task_comments (task_id, created_at);
CREATE INDEX IF NOT EXISTS idx_task_comments_mentions ON task_comments USING gin (mentioned_agent_ids);

-- ──────────────────────────────────────────────────────────────────────────────
-- task_documents — keyed reports + analyses
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_documents (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id                     UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    doc_key                     TEXT NOT NULL,
                                -- 'analysis' | 'research_report' | 'review_summary' | 'repo_op'
                                -- | 'plan' | 'notes' | custom
    title                       TEXT,
    format                      TEXT NOT NULL DEFAULT 'markdown',
                                -- 'markdown' | 'plain_text' | 'json'
    body                        TEXT NOT NULL DEFAULT '',
    latest_revision_number      INTEGER NOT NULL DEFAULT 0,
    created_by_agent_id         UUID REFERENCES agents(id),
    created_by_user_id          UUID,
    updated_by_agent_id         UUID REFERENCES agents(id),
    updated_by_user_id          UUID,
    cited_context               JSONB,
                                -- Array of {path, commit_sha, relevance} when agent
                                -- cites context-repo docs. NULL for operator drafts.
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT task_documents_format_valid CHECK (
        format IN ('markdown', 'plain_text', 'json')
    ),
    -- One document per (task, key) pair. Multiple documents per task allowed via
    -- different keys (e.g. 'analysis' + 'notes' on the same task).
    UNIQUE (task_id, doc_key)
);

COMMENT ON TABLE task_documents IS
    'Durable artifacts attached to tasks — analyses, reports, plans. Keyed so '
    'an agent always knows where to write (e.g. DataAnalyst writes to doc_key=`analysis`). '
    'Revisions are append-only via task_document_revisions; current body is the '
    'latest revision.';

COMMENT ON COLUMN task_documents.doc_key IS
    'Stable key per document purpose. Convention: analysis, research_report, '
    'review_summary, repo_op, plan, notes. Custom keys allowed but discourage proliferation.';

COMMENT ON COLUMN task_documents.cited_context IS
    'JSONB array of context citations when an agent grounded the document in '
    'specific repo docs. Shape: [{path, commit_sha, relevance}]. '
    'See docs/architecture/client-context-sync.md.';

CREATE INDEX IF NOT EXISTS idx_task_documents_task ON task_documents (task_id);
CREATE INDEX IF NOT EXISTS idx_task_documents_key ON task_documents (doc_key);
CREATE INDEX IF NOT EXISTS idx_task_documents_updated ON task_documents (updated_at DESC);

-- updated_at trigger
CREATE OR REPLACE FUNCTION task_documents_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_task_documents_touch_updated_at ON task_documents;
CREATE TRIGGER trg_task_documents_touch_updated_at
    BEFORE UPDATE ON task_documents
    FOR EACH ROW
    EXECUTE FUNCTION task_documents_touch_updated_at();

-- ──────────────────────────────────────────────────────────────────────────────
-- task_document_revisions — append-only audit trail
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_document_revisions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id         UUID NOT NULL REFERENCES task_documents(id) ON DELETE CASCADE,
    revision_number     INTEGER NOT NULL,
    body                TEXT NOT NULL,
    created_by_agent_id UUID REFERENCES agents(id),
    created_by_user_id  UUID,
    change_summary      TEXT,               -- Optional one-liner from the writer
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, revision_number)
);

COMMENT ON TABLE task_document_revisions IS
    'Append-only history of every write to a task document. Lets the operator see '
    'how an analysis evolved across agent runs and pin any prior version.';

CREATE INDEX IF NOT EXISTS idx_task_document_revisions_document
    ON task_document_revisions (document_id, revision_number DESC);
