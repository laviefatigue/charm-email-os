-- Migration 120: Document templates + agent primary output binding
--
-- Why this exists
-- ───────────────
-- Per docs/architecture/skill-outputs-contract.md, we need one canonical place
-- to declare what each doc_key MEANS — title, description, required sections,
-- whether citations are required, and which agent role owns it by default.
--
-- And we need each agent to declare its primary_output_doc_key so the runtime
-- (Phase 1) knows where to write, and so operators know where to look.
--
-- These two together replace prose conventions ("DataAnalyst writes to
-- doc_key=analysis, you just have to know") with a data-grounded contract.

-- ──────────────────────────────────────────────────────────────────────────────
-- document_templates — declared shape per doc_key
-- ──────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS document_templates (
    doc_key             TEXT PRIMARY KEY,
    title               TEXT NOT NULL,                       -- 'Analysis Report', 'Research Report', …
    description         TEXT NOT NULL,                       -- One-liner for tooltips + onboarding
    required_sections   TEXT[] NOT NULL DEFAULT '{}',        -- Ordered list of section headings the doc must contain
    requires_citations  BOOLEAN NOT NULL DEFAULT FALSE,      -- If TRUE, agent prompt enforces inline citations
    primary_agent_role  TEXT,                                 -- Which agent role owns this doc_key by default (NULL = operator-authored)
    icon_hint           TEXT,                                 -- Hint for Assets-tab icon (lucide name)
    notes               TEXT,                                 -- Internal guidance for skill authors
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT document_templates_role_valid CHECK (
        primary_agent_role IS NULL OR
        primary_agent_role IN ('data_analyst', 'researcher', 'day_ai_reviewer', 'github_admin', 'general')
    )
);

COMMENT ON TABLE document_templates IS
    'Canonical structure registry for task_documents. Each doc_key has exactly one '
    'template that declares its sections + agent owner + citation requirements. '
    'Operators and skills both read this to know what shape a doc of this kind takes.';

COMMENT ON COLUMN document_templates.required_sections IS
    'Ordered list of markdown section headings (without leading "#") that the doc '
    'is expected to contain. Enforced at the prompt level + post-run validation, '
    'NOT as a DB constraint (some real-world cases require skipping a section).';

COMMENT ON COLUMN document_templates.primary_agent_role IS
    'Default owner. NULL means operator-authored (e.g. plan, notes). Operators can '
    'still create + edit any doc_key manually.';

-- updated_at trigger
CREATE OR REPLACE FUNCTION document_templates_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_document_templates_touch_updated_at ON document_templates;
CREATE TRIGGER trg_document_templates_touch_updated_at
    BEFORE UPDATE ON document_templates
    FOR EACH ROW
    EXECUTE FUNCTION document_templates_touch_updated_at();

-- ──────────────────────────────────────────────────────────────────────────────
-- Seed the 6 known templates
-- ──────────────────────────────────────────────────────────────────────────────
INSERT INTO document_templates (
    doc_key, title, description, required_sections, requires_citations, primary_agent_role, icon_hint, notes
) VALUES

('analysis', 'Analysis Report',
 'Data-grounded analysis from the Data Analyst. CharmDB queries with ESP-aware aggregation.',
 ARRAY['TL;DR', 'Findings', 'SQL Queries', 'Charts', 'Recommendations'],
 TRUE, 'data_analyst', 'BarChart3',
 'Every finding must cite the SQL query that produced it. Charts section uses Recharts JSON spec via chart-spec skill.'),

('research_report', 'Research Report',
 'External research with verified citations from the Researcher.',
 ARRAY['TL;DR', 'Findings', 'Sources', 'Recommendations'],
 TRUE, 'researcher', 'FileSearch',
 'Every load-bearing claim needs ≥2 independent sources. Sources section is the full bibliography.'),

('review_summary', 'Review Summary',
 'Call transcript review from the Day AI Reviewer.',
 ARRAY['TL;DR', 'Themes', 'Sentiment', 'Action Items', 'Voice-Rule Drift'],
 FALSE, 'day_ai_reviewer', 'MessagesSquare',
 'Sentiment is per-segment, not aggregate. Voice-Rule Drift cross-references feedback/*.md in the context repo.'),

('repo_op', 'Repo Operations Log',
 'Context-repo operations log from the GitHub Admin. All mutations are proposals — operator approves before push/merge.',
 ARRAY['Operations', 'Commits', 'PRs', 'Conflicts'],
 FALSE, 'github_admin', 'GitBranch',
 'GitHubAdmin never auto-merges or force-pushes. Every commit/PR is logged as a proposal; operator approves via task_interaction.'),

('plan', 'Plan',
 'Operator-authored work plan. Free-form structure.',
 ARRAY[]::TEXT[], FALSE, NULL, 'ClipboardList',
 'Operator-owned. Used for drafting work approach, decision rationale, multi-step initiatives.'),

('notes', 'Notes',
 'Free-form notes — anything that doesn''t fit another template.',
 ARRAY[]::TEXT[], FALSE, NULL, 'StickyNote',
 'Operator-owned. Use sparingly — prefer a more specific doc_key when one fits.')

ON CONFLICT (doc_key) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────
-- agents.primary_output_doc_key — one column binding each agent to one template
-- ──────────────────────────────────────────────────────────────────────────────
ALTER TABLE agents
    ADD COLUMN IF NOT EXISTS primary_output_doc_key TEXT
        REFERENCES document_templates(doc_key);

COMMENT ON COLUMN agents.primary_output_doc_key IS
    'The doc_key this agent writes to on every run. Phase 1 runtime uses this to '
    'know where to UPSERT the output. Operators use this in the Agents page to '
    'understand "what does this agent produce."';

-- Backfill from role
UPDATE agents SET primary_output_doc_key = 'analysis'        WHERE role = 'data_analyst'      AND primary_output_doc_key IS NULL;
UPDATE agents SET primary_output_doc_key = 'research_report' WHERE role = 'researcher'        AND primary_output_doc_key IS NULL;
UPDATE agents SET primary_output_doc_key = 'review_summary'  WHERE role = 'day_ai_reviewer'   AND primary_output_doc_key IS NULL;
UPDATE agents SET primary_output_doc_key = 'repo_op'         WHERE role = 'github_admin'      AND primary_output_doc_key IS NULL;
