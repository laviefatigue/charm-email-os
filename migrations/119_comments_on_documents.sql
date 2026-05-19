-- Migration 119: Anchor task comments to documents + revisions
--
-- Why this exists
-- ───────────────
-- Phase 0 of the revamp plan (docs/architecture/charm-revamp-plan.md) introduces
-- asset-centric chat. Today, task_comments only carry task_id — so when an
-- operator wants to discuss a specific document (or a specific revision of one),
-- there's nowhere to anchor the thread.
--
-- This migration adds two NULLABLE columns:
--   • document_id           → which task_document the comment is about (NULL = thread-level)
--   • document_revision_number → which revision of that document (NULL = "latest")
--
-- NULL document_id = legacy / thread-level comment (the default before this
-- migration). Non-NULL = document-scoped comment that renders in the document
-- panel, not the main thread.
--
-- This is the foundation for "chat with one or multiple agents on that particular
-- asset" (the user's words). In Phase 2, an agent reading new comments will know
-- to scope its response to the cited revision.

ALTER TABLE task_comments
    ADD COLUMN IF NOT EXISTS document_id UUID
        REFERENCES task_documents(id) ON DELETE CASCADE;

ALTER TABLE task_comments
    ADD COLUMN IF NOT EXISTS document_revision_number INTEGER;

-- A comment that names a revision must also name the document.
ALTER TABLE task_comments
    DROP CONSTRAINT IF EXISTS task_comments_revision_requires_document;
ALTER TABLE task_comments
    ADD CONSTRAINT task_comments_revision_requires_document CHECK (
        document_revision_number IS NULL OR document_id IS NOT NULL
    );

COMMENT ON COLUMN task_comments.document_id IS
    'When non-NULL, this comment is scoped to a specific task_document and renders '
    'in the document panel instead of the main task thread. The doc must belong to '
    'the same task (validated in the API layer, not as an FK trigger).';

COMMENT ON COLUMN task_comments.document_revision_number IS
    'Optional revision pin. When set, the comment is anchored to that specific '
    'revision of the document — useful for "I disagree with the v3 conclusion." '
    'NULL = comment applies to the latest revision (or document overall).';

-- Index for "show me all comments on this document" (Documents tab discuss view).
CREATE INDEX IF NOT EXISTS idx_task_comments_document
    ON task_comments (document_id, created_at)
    WHERE document_id IS NOT NULL;
