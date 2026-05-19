# Skill outputs contract

> Authoritative mapping of agents → document templates → required structure. Operators read this to know "if I assign this agent, where does the output land and what does it contain." Skills read this to know what shape their output must take.
>
> Lives alongside [charm-revamp-plan.md](./charm-revamp-plan.md). Schema is in [migration 120](../../migrations/120_document_templates.sql).

## The model

```
agent          → primary_output_doc_key    → document_template
  │                                          │
  │                                          ├── required_sections: [TL;DR, Findings, …]
  │                                          ├── requires_citations: bool
  │                                          └── primary_agent_role: data_analyst | …
  │
  └── skills (capabilities) ───── fill the sections ─────┘
```

Three rules:

1. **One primary doc_key per agent.** An agent's `primary_output_doc_key` says where every run's output lands. Operators can find the output even if they don't remember the run.
2. **Templates declare structure, not skills.** A `document_template` lists the sections a doc of that kind must contain. Skills know how to *fill* sections; templates know what sections *must exist*.
3. **Skills are capabilities, not artifacts.** A skill like `sql-query` doesn't have its own doc — it's a tool the DataAnalyst uses while filling §Findings of an `analysis` doc.

## The 6 document templates

| `doc_key` | Title | Primary agent role | Required sections | Citations required |
|-----------|-------|--------------------|-------------------|--------------------|
| `analysis` | Analysis Report | `data_analyst` | TL;DR, Findings, SQL Queries, Charts, Recommendations | yes |
| `research_report` | Research Report | `researcher` | TL;DR, Findings, Sources, Recommendations | yes |
| `review_summary` | Review Summary | `day_ai_reviewer` | TL;DR, Themes, Sentiment, Action Items, Voice-Rule Drift | no |
| `repo_op` | Repo Operations Log | `github_admin` | Operations, Commits, PRs, Conflicts | no |
| `plan` | Plan | (operator) | (free-form) | no |
| `notes` | Notes | (operator) | (free-form) | no |

**`plan` and `notes` are operator-authored** — they have no required structure and no primary agent. They exist so operators can attach a draft work plan or general notes to a task without it looking like an agent's output.

## The 4 agents and their primary outputs

### DataAnalyst → `analysis`

Reads CharmDB + workspace context. Always groups by ESP (Entra 52/domain vs Google 3/domain — [esp-aware-data-interpretation](../concepts/esp-aware-data-interpretation.md)). Output `analysis` always contains:

- **TL;DR** (3 sentences max)
- **Findings** (numbered, each cites a SQL query)
- **SQL Queries** (the actual `SELECT … FROM …` text used)
- **Charts** (Recharts JSON spec via `chart-spec` skill, optional)
- **Recommendations** (concrete actions ranked by impact)

Skills available: `sql-query`, `burn-velocity-analysis`, `kill-cascade-forensics`, `esp-split-rollup`, `chart-spec`, `report-writing`.

### Researcher → `research_report`

External research with verified citations. Output `research_report` always contains:

- **TL;DR**
- **Findings** (each load-bearing claim has ≥2 independent sources)
- **Sources** (full bibliography — `[Title](URL) — accessed YYYY-MM-DD`)
- **Recommendations**

Skills available: `research-methodology`, `fact-verification`, `report-writing`. Can request DataAnalyst grounding via task_interaction with `kind=request_confirmation` ("DataAnalyst, can you confirm X?") — but never DM the DataAnalyst directly; operator approves the cross-agent ask.

### DayAIReviewer → `review_summary`

Reads `notes/transcripts/` from the workspace's context repo (deposited by Day AI). Output `review_summary` always contains:

- **TL;DR**
- **Themes** (5-10 bullets)
- **Sentiment** (per-segment scoring with timeline, not aggregate)
- **Action Items** (explicit commitments + flagged implicit ones)
- **Voice-Rule Drift** (cross-referenced against `feedback/*.md` in the context repo)

Skills available: `transcript-analysis`, `sentiment-detection`, `action-extraction`, `report-writing`.

### GitHubAdmin → `repo_op`

Operates context repos on the operator's behalf — but **all mutations are proposals**. The operator approves via task_interaction before anything pushes / merges. Output `repo_op` always contains:

- **Operations** (chronological log of what was proposed / done)
- **Commits** (proposed commits with their diffs)
- **PRs** (proposed / opened — never auto-merged)
- **Conflicts** (anything that needed operator intervention)

Skills available: `git-workflow`, `pr-management`, `changelog-generation`, `conflict-resolution`.

> **GitHubAdmin is the agent that diverges most from Charm's operator-CEO posture if not constrained.** Migration 121 strips autonomy verbs from its prompt: never "merge", "force-push", "auto-commit". Every mutation = a proposal that lands in `repo_op` for operator review.

## How to add a new doc_key

1. Decide if the new doc is operator-authored (like `plan`) or agent-produced (like `analysis`).
2. If agent-produced: also pick or create the agent that owns it (`primary_agent_role`).
3. Add an INSERT to a new migration extending `document_templates`. Required: `doc_key`, `title`, `description`, `required_sections`, `requires_citations`.
4. Update the agent's `primary_output_doc_key` if you created a new agent.
5. Update [this doc](./skill-outputs-contract.md) with the new template's row.

Counter-rules to keep the namespace clean:

- **Don't add a new doc_key for a one-off task.** Use `notes` if it's ephemeral.
- **Don't fork an existing doc_key to mean something slightly different.** Either the existing template covers it, or it's a new template — never an overloaded one.
- **Don't add a doc_key without an agent owning it (unless it's operator-authored).** Orphan doc_keys clutter the Assets tab.

## How to add a new agent

1. Decide the agent's primary output (which `doc_key`).
2. Insert into `agents` with `primary_output_doc_key` set + `prompt_template` written per the operator-CEO conventions (see [migration 121](../../migrations/121_operator_ceo_prompts.sql) for the preamble pattern).
3. Map relevant skills via `agent_skill_mappings`.
4. Update [this doc](./skill-outputs-contract.md) §"The N agents and their primary outputs" section.

## Prompt template conventions (operator-CEO model)

Every agent's `prompt_template` begins with:

```
You are the {Title} for Charm Email OS. You support the operator — the human
Account Executive who is the CEO of this account. You produce {primary_output_doc_key}
markdown reports for the operator to review.

You never take external action (sending email, merging code, paying invoices,
contacting clients) without the operator's explicit approval via a task_interaction
with kind=request_confirmation.

Your output always lands as a task_document with doc_key={primary_output_doc_key}
following the {required_sections} structure.
```

Then the agent-specific guidance (what data to read, what skills to use, what tone).

## What this contract does NOT do

- **Does not enforce sections at the DB level.** The template lists `required_sections` as metadata; enforcement happens in the agent prompt + post-run validation. We choose flexibility over rigidity because real agents sometimes need to skip a section if there's nothing to put there.
- **Does not lock skills to one doc_key.** A skill like `report-writing` is used by every agent. `chart-spec` could be used by both DataAnalyst and Researcher. Skills don't decree their parent doc; agents do.
- **Does not version templates.** v1 of the template stands until v2 ships in a new migration. No template-schema-versioning machinery.

## References

- [charm-revamp-plan.md](./charm-revamp-plan.md) — phase plan that introduces this contract.
- [paperclip-reference.md](./paperclip-reference.md) §5 — paperclip's skills+prompt-cache pattern (we lift the discipline, not the file layout).
- [client-context-sync.md](./client-context-sync.md) — `cited_context` JSONB sourcing for DataAnalyst/Researcher/DayAIReviewer.
- [migration 113](../../migrations/113_agent_skills.sql) — the 17 seeded skill bodies.
- [migration 120](../../migrations/120_document_templates.sql) — the schema this contract is built on.
- [migration 121](../../migrations/121_operator_ceo_prompts.sql) — the operator-CEO prompt preamble for all agents.
