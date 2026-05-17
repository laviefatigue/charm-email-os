-- Migration 112: Analyst agents (paperclip-pattern, Charm-specialized)
--
-- Why this exists
-- ───────────────
-- Charm adopts paperclip's agent runtime pattern for analyst agents that operate
-- against CharmDB + client context. The operator (AE) picks an agent, assigns a
-- task, agent runs against its skill set, produces a stored report (issue document).
-- See docs/architecture/agent-runtime.md for the full spec.
--
-- This migration seeds 4 specialized agents per the IA decision (2026-05-16):
--   • Data Analyst       — queries CharmDB, produces analyses
--   • Researcher         — external research with citations
--   • Day AI Reviewer    — reviews call transcripts in client context repo
--   • GitHub Repo Admin  — manages context-repo pull/push lifecycle
--
-- Agent execution adapter (claude_local / process / http) is NOT shipped in this
-- migration — agents start in status='active' but heartbeat runtime lands later.
-- For now, operators can assign tasks to agents and manually fill in documents,
-- which validates the workflow end-to-end before the runtime ships.
--
-- Specialization is prompt_template + skill subset + role, NOT structural DB
-- differences per agent.

CREATE TABLE IF NOT EXISTS agents (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                     TEXT UNIQUE NOT NULL,           -- 'DataAnalyst', 'Researcher', etc. (@-mention target)
    role                     TEXT NOT NULL,                  -- 'data_analyst', 'researcher', 'day_ai_reviewer', 'github_admin'
    title                    TEXT NOT NULL,                  -- 'Data Analyst', 'Researcher', etc. (display)
    description              TEXT,                            -- One-liner shown in roster
    capabilities             TEXT,                            -- Free-text describing what this agent does
    adapter_type             TEXT NOT NULL DEFAULT 'claude_local', -- claude_local | process | http
    adapter_config           JSONB NOT NULL DEFAULT '{}'::jsonb,   -- promptTemplate, model, timeoutSec, envVars, etc.
    budget_monthly_cents     INTEGER NOT NULL DEFAULT 5000,  -- $50/mo default per agent
    spent_monthly_cents      INTEGER NOT NULL DEFAULT 0,     -- updated by agent_runs
    status                   TEXT NOT NULL DEFAULT 'active',
                             -- 'active' | 'idle' | 'running' | 'error' | 'paused' | 'terminated'
    heartbeat_policy         JSONB NOT NULL DEFAULT
                             '{"enabled":false,"intervalSec":300,"wakeOnAssignment":true,"cooldownSec":60}'::jsonb,
    last_run_at              TIMESTAMPTZ,
    last_error               TEXT,
    is_active                BOOLEAN NOT NULL DEFAULT TRUE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT agents_role_valid CHECK (
        role IN ('data_analyst', 'researcher', 'day_ai_reviewer', 'github_admin', 'general')
    ),
    CONSTRAINT agents_status_valid CHECK (
        status IN ('active', 'idle', 'running', 'error', 'paused', 'terminated')
    ),
    CONSTRAINT agents_adapter_valid CHECK (
        adapter_type IN ('claude_local', 'process', 'http')
    )
);

COMMENT ON TABLE agents IS
    'Analyst agents (paperclip-pattern). 4 seeded specialized agents that operate '
    'against CharmDB + client context. Specialization = prompt_template + skill '
    'subset (see agent_skill_mappings) + role label. Hybrid scope: each agent row '
    'serves all workspaces — concurrent runs allowed, gated by budget + adapter.';

COMMENT ON COLUMN agents.name IS
    'Unique identifier used for @-mentions in task comments. Case-insensitive match.';

COMMENT ON COLUMN agents.adapter_config IS
    'JSON config for the runtime adapter. For claude_local: {"promptTemplate", "model", '
    '"timeoutSec", "envVars"}. The promptTemplate is the primary specialization vehicle.';

COMMENT ON COLUMN agents.heartbeat_policy IS
    'Scheduling config: {"enabled", "intervalSec", "wakeOnAssignment", "cooldownSec"}. '
    'enabled=false until runtime ships; wakeOnAssignment=true so assigning a task to '
    'this agent will trigger a heartbeat once the runtime exists.';

CREATE INDEX IF NOT EXISTS idx_agents_role ON agents (role);
CREATE INDEX IF NOT EXISTS idx_agents_is_active ON agents (is_active) WHERE is_active = TRUE;

-- updated_at trigger
CREATE OR REPLACE FUNCTION agents_touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agents_touch_updated_at ON agents;
CREATE TRIGGER trg_agents_touch_updated_at
    BEFORE UPDATE ON agents
    FOR EACH ROW
    EXECUTE FUNCTION agents_touch_updated_at();

-- ──────────────────────────────────────────────────────────────────────────────
-- Seed the 4 specialized analyst agents
-- ──────────────────────────────────────────────────────────────────────────────
INSERT INTO agents (name, role, title, description, capabilities, adapter_config) VALUES

('DataAnalyst', 'data_analyst', 'Data Analyst',
 'Queries CharmDB + produces analyses on burn velocity, kill cascades, deliverability, capacity, ESP-split rollups.',
 'Reads sender_accounts, event_log, kill triggers, campaign metrics, package targets. Output: markdown report with SQL, charts, recommendations.',
 jsonb_build_object(
     'promptTemplate',
     E'You are the Data Analyst for Charm Email OS. You query the production CharmDB to produce analyses on email infrastructure performance.\n\nCRITICAL: Always group by ESP (Entra vs Google). Entra has 52 inboxes/domain; Google has 3. Mixing the two breaks every aggregate. See docs/concepts/esp-aware-data-interpretation.md.\n\nLoad skills relevant to the task. Produce reports as issue documents (key=`analysis`). Cite SQL queries, sample sizes, and confidence in your conclusions. Flag stale context if the workspace context repo hasn''t been synced recently.',
     'model', 'claude-opus-4-7',
     'timeoutSec', 600
 )),

('Researcher', 'researcher', 'Researcher',
 'External research with citations — competitor moves, deliverability best-practice, vendor changes, market context.',
 'Reads web + client context repo. Output: markdown report with sourced citations (URL + access date + relevance).',
 jsonb_build_object(
     'promptTemplate',
     E'You are the Researcher for Charm Email OS. You verify facts, cross-reference sources, and produce well-cited research reports for the AE team.\n\nEvery claim cites a source. Format: [Source Title](URL) — accessed YYYY-MM-DD. Distinguish primary sources from secondary. Flag uncertainty explicitly.\n\nProduce reports as issue documents (key=`research_report`). Use the Data Analyst (via @-mention) when you need DB-grounded facts.',
     'model', 'claude-opus-4-7',
     'timeoutSec', 900
 )),

('DayAIReviewer', 'day_ai_reviewer', 'Day AI Reviewer',
 'Reviews client call transcripts from the context repo. Extracts themes, sentiment, action items, banned phrases drift.',
 'Reads notes/transcripts/ from the client context repo (Day AI landing zone). Output: review summary with action items + sentiment scoring.',
 jsonb_build_object(
     'promptTemplate',
     E'You are the Day AI Reviewer for Charm Email OS. Day AI deposits call transcripts as markdown into the client''s context repo (notes/transcripts/). You read those and surface what matters for the AE team.\n\nFor each transcript: identify themes, surface action items, score sentiment, flag client corrections (banned phrases / voice rule violations). Cross-reference against feedback/*.md in the same repo.\n\nProduce reviews as issue documents (key=`review_summary`). Use @GitHubAdmin to ensure latest pull before reviewing.',
     'model', 'claude-opus-4-7',
     'timeoutSec', 600
 )),

('GitHubAdmin', 'github_admin', 'GitHub Repo Admin',
 'Manages the client context repo: pull latest, commit AE notes, merge PRs, resolve conflicts, ensure Foam-protocol compliance.',
 'Operates on github.com/hirecharm/charm-{client} repos via the Charm Context Sync GitHub App. Output: repo_op log with commits/branches/PRs touched.',
 jsonb_build_object(
     'promptTemplate',
     E'You are the GitHub Repo Admin for Charm Email OS. You operate the client context repos: pull latest, commit pending notes, surface stale branches, ensure Foam protocol (frontmatter + wiki-links + MOC registration) is followed.\n\nFor every operation: log to issue document (key=`repo_op`) with commit SHAs, branches affected, PR numbers. Flag any drift from charm-client-template conventions. Never force-push.',
     'model', 'claude-opus-4-7',
     'timeoutSec', 300
 ))

ON CONFLICT (name) DO NOTHING;
