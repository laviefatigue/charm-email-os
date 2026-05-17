-- Migration 113: Agent skill library + per-agent skill assignments
--
-- Why this exists
-- ───────────────
-- Paperclip's skills model: skills are reusable markdown packages (SKILL.md
-- format) referenced by agents via slug. An agent's prompt sees skill metadata
-- (name + description); the agent loads full body on-demand when the task is
-- relevant. This separates "what the agent CAN do" from "what the agent loads".
--
-- agent_skills    — global skill library (one row per skill)
-- agent_skill_mappings — which agents have which skills (M:N)
--
-- Seeded skills cover the 4 specialized agents' core capabilities. Skill bodies
-- are minimal stubs here; expand them with /docs/skills/{slug}/SKILL.md files
-- (or admin UI) as agents need them.

CREATE TABLE IF NOT EXISTS agent_skills (
    slug                TEXT PRIMARY KEY,                -- 'sql-query', 'burn-velocity-analysis'
    name                TEXT NOT NULL,                   -- Human-readable name
    description         TEXT NOT NULL,                   -- One-liner — what the skill is for
    body_markdown       TEXT NOT NULL DEFAULT '',        -- Full SKILL.md content (loaded by agent when relevant)
    version             TEXT NOT NULL DEFAULT '1.0.0',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE agent_skills IS
    'Global skill library. Skills are markdown packages an agent can load on demand. '
    'Agent prompts see metadata (name + description) only; body_markdown is loaded '
    'when the agent decides the skill is relevant to its current task.';

CREATE TABLE IF NOT EXISTS agent_skill_mappings (
    agent_id        UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    skill_slug      TEXT NOT NULL REFERENCES agent_skills(slug) ON DELETE CASCADE,
    assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (agent_id, skill_slug)
);

COMMENT ON TABLE agent_skill_mappings IS
    'Which agents are configured with which skills (subset of the global library). '
    'The agent only sees + can load skills mapped here. Operators can add/remove '
    'mappings to evolve agent capabilities without code changes.';

CREATE INDEX IF NOT EXISTS idx_agent_skill_mappings_skill ON agent_skill_mappings (skill_slug);

-- ──────────────────────────────────────────────────────────────────────────────
-- Seed the initial skill library
-- ──────────────────────────────────────────────────────────────────────────────
INSERT INTO agent_skills (slug, name, description, body_markdown) VALUES

('sql-query', 'SQL Query',
 'Run read-only SQL against CharmDB. ESP-aware grouping enforced.',
 E'# SQL Query\n\nUse parameterized queries. Always GROUP BY esp when aggregating sender metrics. Never SELECT * in production reports — pick exact columns.\n\nCommon tables: sender_accounts, domains, campaigns, event_log, workspace_packages, client_subscriptions.\n\nSee [[docs/concepts/esp-aware-data-interpretation]] before any rate/ratio query.'),

('burn-velocity-analysis', 'Burn Velocity Analysis',
 'Model the rate at which inboxes are entering dead/burned state. Flag accelerating workspaces.',
 E'# Burn Velocity Analysis\n\nQuery event_log for warmup_disable + kill events grouped by workspace + week. Compute slope. Flag workspaces with +15% MoM acceleration. Output: chart spec + recommendation (rotate now / monitor / no action).'),

('kill-cascade-forensics', 'Kill Cascade Forensics',
 'Post-mortem on cluster-of-kills events. Identify common cause (ESP throttle, domain group, time-of-day).',
 E'# Kill Cascade Forensics\n\nGiven a window where >N inboxes died in <T hours, isolate: which domains, which ESP, which campaigns sending. Cross-reference with EmailBison + Hypertide events. Output: root-cause narrative + preventative recommendation.'),

('esp-split-rollup', 'ESP-Split Rollup',
 'Aggregate metrics correctly across Entra (52/domain) vs Google (3/domain).',
 E'# ESP-Split Rollup\n\nAny metric expressed per-domain or per-inbox MUST be split. Total counts are misleading without ESP context. Output format: separate Entra section + Google section, then combined totals with the per-ESP weights stated.'),

('chart-spec', 'Chart Spec',
 'Produce Recharts-ready chart configurations (data + axes + colors from Village tokens).',
 E'# Chart Spec\n\nOutput JSON ready for Recharts: {type, data, xAxisKey, yAxisKeys, colors: [amber, sage, copper, sky, rose-deep], stacked?, threshold?}. No hex colors — use Charm token names; the renderer resolves them.'),

('research-methodology', 'Research Methodology',
 'Structured research: question framing, source triage, primary-vs-secondary distinction, contradicting evidence.',
 E'# Research Methodology\n\nEvery research question gets: (1) explicit framing, (2) source list with primary/secondary tags, (3) confidence level on each claim, (4) explicit list of what could contradict the finding.'),

('fact-verification', 'Fact Verification',
 'Cross-check claims against multiple independent sources. Mark unverifiable claims explicitly.',
 E'# Fact Verification\n\nFor every load-bearing claim: ≥2 independent sources. Mark with verification status. Unverified claims labeled [UNVERIFIED] in the report so the operator can decide whether to act.'),

('report-writing', 'Report Writing',
 'Markdown reports with consistent structure: TL;DR + findings + sources + recommendations.',
 E'# Report Writing\n\nEvery report opens with TL;DR (3 sentences max). Then: Findings (numbered, evidence-backed). Sources (cited inline + listed at end). Recommendations (concrete, actionable, ranked).'),

('transcript-analysis', 'Transcript Analysis',
 'Extract themes, action items, sentiment, and voice-rule drift from call transcripts.',
 E'# Transcript Analysis\n\nFor each transcript: themes (5–10 bullets), explicit action items (with owner + deadline if stated), sentiment (positive/neutral/negative + 1-line rationale), voice-rule violations (cross-reference client feedback/*.md).'),

('sentiment-detection', 'Sentiment Detection',
 'Score call sentiment per-segment, not just aggregate. Flag inflection points.',
 E'# Sentiment Detection\n\nDon''t average sentiment across an hour-long call. Score per-segment (5-min windows). Flag any 2+ segment swing from positive → negative as an inflection. Report includes timeline.'),

('action-extraction', 'Action Item Extraction',
 'Pull explicit commitments out of transcripts. Mark owner + due date if stated; flag implicit.',
 E'# Action Item Extraction\n\nExplicit: speaker says "I''ll send X by Y" — record verbatim. Implicit: speaker implies but doesn''t commit — flag as [IMPLIED] and ask for clarification next call.'),

('git-workflow', 'Git Workflow',
 'Standard pull/commit/push operations on client context repos. Branch-review-merge compliant.',
 E'# Git Workflow\n\nNever force-push. Always work on a branch prefixed ae/{name}/{short-desc}. Commit messages: present tense, ≤72 char subject. Push triggers the branch-review-merge system.'),

('pr-management', 'PR Management',
 'Create, review, merge PRs on context repos via the GitHub App installation.',
 E'# PR Management\n\nUse the gh CLI authenticated via the App installation token. PR titles match commit subject. Body includes: what changed (3 bullets max), why (1 line), Charm OS record ID reference.'),

('changelog-generation', 'Changelog Generation',
 'Summarize a diff range into a human-readable changelog for the AE team.',
 E'# Changelog Generation\n\nGiven a commit range, output: chronological list of significant changes (skip whitespace + .md cleanup). Group by file area (gtm/, decisions/, notes/, feedback/). One line per change.'),

('conflict-resolution', 'Conflict Resolution',
 'Resolve merge conflicts on text-only files conservatively. Escalate binary or structured conflicts.',
 E'# Conflict Resolution\n\nFor text conflicts in notes/feedback/decisions: prefer both-sides (concatenate with clear separator). For YAML frontmatter conflicts: prefer most-recent. For any binary or structured-data conflict: STOP and surface to operator via @-mention.')

ON CONFLICT (slug) DO NOTHING;

-- ──────────────────────────────────────────────────────────────────────────────
-- Map skills to the 4 seeded agents
-- ──────────────────────────────────────────────────────────────────────────────
-- DataAnalyst skills
INSERT INTO agent_skill_mappings (agent_id, skill_slug)
SELECT a.id, s
FROM agents a, unnest(ARRAY[
    'sql-query', 'burn-velocity-analysis', 'kill-cascade-forensics',
    'esp-split-rollup', 'chart-spec', 'report-writing'
]) AS s
WHERE a.name = 'DataAnalyst'
ON CONFLICT DO NOTHING;

-- Researcher skills
INSERT INTO agent_skill_mappings (agent_id, skill_slug)
SELECT a.id, s
FROM agents a, unnest(ARRAY[
    'research-methodology', 'fact-verification', 'report-writing'
]) AS s
WHERE a.name = 'Researcher'
ON CONFLICT DO NOTHING;

-- DayAIReviewer skills
INSERT INTO agent_skill_mappings (agent_id, skill_slug)
SELECT a.id, s
FROM agents a, unnest(ARRAY[
    'transcript-analysis', 'sentiment-detection', 'action-extraction', 'report-writing'
]) AS s
WHERE a.name = 'DayAIReviewer'
ON CONFLICT DO NOTHING;

-- GitHubAdmin skills
INSERT INTO agent_skill_mappings (agent_id, skill_slug)
SELECT a.id, s
FROM agents a, unnest(ARRAY[
    'git-workflow', 'pr-management', 'changelog-generation', 'conflict-resolution'
]) AS s
WHERE a.name = 'GitHubAdmin'
ON CONFLICT DO NOTHING;
