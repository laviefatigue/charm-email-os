# Charm OS revamp plan

Canonical sequencing for evolving Charm Email OS from "operator UI + manual agent prompt copy-paste" to "operator-CEO dashboard with markdown-producing agent supporters." Grounded in [paperclip-reference.md](./paperclip-reference.md) and what's actually shipped today.

> **Status as of 2026-05-18**
>
> The schema + API + frontend for tasks / projects / agents / comments / documents / interactions is **complete on disk** (migrations 112-118, [api/routes/tasks.py](../../api/routes/tasks.py) at 871 LOC, [app/tasks/[id]/page.tsx](../../charm-email-os/app/tasks/[id]/page.tsx) at 989 LOC). What's missing is the agent runtime. The current execution path is [components/charm/prepare-agent-run-modal.tsx](../../charm-email-os/components/charm/prepare-agent-run-modal.tsx) — a clipboard-copy modal we are removing. Background: the survey transcript in `docs/architecture/notes/` (this conversation).

## Mental model

The model differs deliberately from paperclip:

| | Paperclip | Charm |
|---|---|---|
| **Who's in charge** | CEO is an agent | Operator is the CEO |
| **What agents do** | Take action autonomously (file PRs, hire other agents, ship code) | Produce markdown reports + analyses for the operator to act on |
| **Primary output shape** | Code changes, external work products (PR URLs, deployed services) | Markdown documents stored as task_documents |
| **Default UX destination after a run** | `/{COMPANY}/issues/{ID}` — see the agent working | Task page with the updated document in the Documents tab |
| **Approval surface** | Optional gate, runtime can be autonomous | The operator approves what gets shipped, always |

Charm agents do **research, analysis, drafting** — not execution. The Assets tab is the surface for the operator to find, review, and chat about those outputs across workspaces and tasks.

## Phase 0 — Cleanup + asset-chat shape

**Goal:** remove the copy-paste workflow, make the Assets-chat experience work for human-to-human collaboration today so the data model is real and proven before Phase 1's runtime arrives.

**Duration:** ~1 week.

### Concrete deliverables

| # | Change | Path | Effort |
|---|--------|------|--------|
| 1 | Migration 119: add `task_comments.document_id` (nullable FK → `task_documents`) + `task_comments.document_revision_number` (nullable int) | [migrations/119_comments_on_documents.sql](../../migrations/119_comments_on_documents.sql) | XS |
| 2 | Migration 120: add `document_templates` table + `agents.primary_output_doc_key` column. Seed 6 templates. Backfill from agent roles. | [migrations/120_document_templates.sql](../../migrations/120_document_templates.sql) | S |
| 3 | Migration 121: UPDATE agent `prompt_template` to add operator-CEO preamble. Strip autonomy-implying verbs ("commit pending notes", "merge PRs", etc.) — replace with "propose" / "draft for operator approval". | [migrations/121_operator_ceo_prompts.sql](../../migrations/121_operator_ceo_prompts.sql) | S |
| 4 | Delete [components/charm/prepare-agent-run-modal.tsx](../../charm-email-os/components/charm/prepare-agent-run-modal.tsx) + remove import + remove "Prepare agent run" button. Replace with disabled "Run agent" button + tooltip "Agent runtime ships in Phase 1." | [app/tasks/[id]/page.tsx](../../charm-email-os/app/tasks/[id]/page.tsx) + components index | XS |
| 5 | API: extend `POST /tasks/{id}/comments` to accept optional `document_id` + `document_revision_number`. Validate doc belongs to task. | [api/routes/tasks.py](../../api/routes/tasks.py) | XS |
| 6 | Frontend: Documents tab — when an agent updates a doc, show "Discuss this revision" button. Opens a thread filtered to comments with `document_id=this.id`. | [app/tasks/[id]/page.tsx](../../charm-email-os/app/tasks/[id]/page.tsx) | M |
| 7 | Frontend: Assets tab — show `document_templates.title` instead of raw `doc_key`. Add per-template icon + tooltip. Filter chips per doc_key. | [app/workspaces/[id]/assets/page.tsx](../../charm-email-os/app/workspaces/[id]/assets/page.tsx) | S |
| 8 | Frontend: render `task_documents.cited_context` as a "Sources" sidebar in MarkdownView. | [components/charm/markdown-view.tsx](../../charm-email-os/components/charm/markdown-view.tsx) | S |
| 9 | Delete root-level `app/tasks/`, `app/projects/`, `app/campaigns/`. Keep `/recommendations` + `/timeline` as global cross-workspace rollups. | (mass delete) | XS |
| 10 | Add a one-line subheader to the workspace overview: "You're the CEO of {Client} — agents propose, you approve." Dismissible per user. | [app/workspaces/[id]/page.tsx](../../charm-email-os/app/workspaces/[id]/page.tsx) | XS |

### Acceptance criteria for Phase 0

- [ ] `PrepareAgentRunModal` no longer exists. No clipboard-copy paths anywhere in the UI.
- [ ] Operators can create a `task_document` from the UI (drafting an analysis manually) and others can comment on a specific revision of it.
- [ ] Migration 120 applied; every existing agent has a `primary_output_doc_key`.
- [ ] All 6 document templates display in the Assets tab with proper titles and icons.
- [ ] No root-level `/tasks` or `/projects` paths exist; all task/project navigation routes through `/workspaces/{id}/...`.
- [ ] Agent prompts pass a one-paragraph review: no autonomy-implying language, explicit "operator is the decision-maker" preamble.

### Explicitly out of scope for Phase 0

- Local helper daemon, probe endpoint, agent runtime — all Phase 1.
- @-mention wake-on-mention behaviour — hide the affordance until Phase 1 can fulfill the promise.
- `agent_runs` / `agent_run_events` tables — Phase 1 migration 122.
- Multi-agent contribution to one document — Phase 2.

## Phase 1 — Local helper + first probe + first run

**Goal:** prove the cloud↔localhost transport with one agent (any agent) running a hello-world skill that posts a comment on a task. Zero copy-paste.

**Duration:** ~3-4 weeks.

### Scope

- **`@charm/agent-helper`** — Node daemon, distributed as a single npm package. Exposes:
  - `GET /probe` — runs the paperclip-style `claude --print -` hello probe, returns `{ status: pass|warn|fail, checks: [...] }`. Mirror [packages/adapters/claude-local/src/server/test.ts](../../paperclip-reference/packages/adapters/claude-local/src/server/test.ts).
  - `POST /run` — accepts `{ runId, agentId, promptBundle, skills, cwd }`, spawns `claude` with the paperclip incantation (`--print - --output-format stream-json --verbose --add-dir {bundle}`), returns `{ runId, streamUrl }`.
  - `GET /runs/{id}/stream` — SSE stream of stream-json events. Cloud subscribes to update the UI live.
- **Migration 122** — `agent_runs` + `agent_run_events` tables (lift paperclip's `heartbeat_runs` shape, trim goal/budget/plugin/environment columns).
- **Migration 123** — `agent_helper_registrations` — operator registers a helper (one per laptop) with a `helper_token` and a `last_heartbeat_at`. Cloud verifies token on each `/run` POST.
- **Cloud endpoint** `POST /api/agents/{id}/run` — enqueues a run, returns the runId. A queue worker picks it up, looks up the operator's registered helper, POSTs to it.
- **First skill: `/say-hello`** — agent reads task, posts a comment "Hello from {agentName}. I see this task is about: {summary}." That's it. Proves the end-to-end loop with zero risk.
- **UI** — replace the disabled "Run agent" button with a real one. Click → spawns a run → live-streams "agent working…" → renders the resulting comment in the thread.

### Acceptance criteria for Phase 1

- [ ] Operator can install `@charm/agent-helper` locally (`npx @charm/agent-helper install`).
- [ ] The Probe button in the agent config UI returns Pass/Warn/Fail with the same check codes paperclip emits.
- [ ] Clicking "Run agent" on a task with an assigned agent successfully runs the hello skill end-to-end with zero copy-paste.
- [ ] `agent_runs` row exists with `usage_json`, `result_json`, `session_id_after`, `log_ref` populated.
- [ ] No Anthropic credentials ever leave the operator's machine.

### Explicitly out of scope for Phase 1

- Real analytical skills (those are Phase 2). The first agent run produces only a "hello" comment.
- Wake-on-assignment auto-runs (operator clicks the button manually).
- Multi-helper / shared-helper / cloud-runner deployments.
- Budget enforcement (declared, not enforced).

## Phase 2 — Real skills + multi-agent collaboration

**Goal:** the four seeded agents produce their real outputs (analysis, research_report, review_summary, repo_op) and multiple agents can contribute to one document.

**Duration:** ongoing.

### Scope (sketch only — re-plan after Phase 1 ships)

- Harden each of the 17 seeded skills: every output-producing skill enforces its target doc_key + required sections from `document_templates`.
- Wake-on-assignment: when operator assigns a task to an agent, automatically enqueue a run. When operator @-mentions an agent in a comment, the agent wakes.
- Multi-agent on one document: revisions of a `task_document` track `created_by_agent_id` per revision. Two agents can append sections; the document is the meeting point.
- The Assets tab becomes a real "knowledge base view" — search across documents, filter by template/agent/workspace/freshness, click to chat with the agent(s) who wrote it.
- Continuation policy resolution: when an interaction is decided, the chosen `continuation_policy` (`wake_assignee` / `update_status`) actually fires.

### Acceptance criteria for Phase 2

- [ ] Operator assigns DataAnalyst to "audit Stable Kernel inbox health" → automatic run → `analysis` doc appears, populated with the 5 required sections, citations rendered.
- [ ] Operator can comment on a specific revision of the analysis with `@Researcher add competitor benchmarks` → Researcher wakes → appends §Competitor Benchmarks → comments back.
- [ ] Assets tab search returns ranked results across all documents in the operator's workspaces.
- [ ] Operator clicks an interaction's Approve button → the agent that filed it wakes and continues from the decision point.

## Strategic decisions made

1. **Skills decree their output doc_key.** Operators cannot choose at run-time. Each output-producing skill declares which `target_doc_key` (and optionally `target_section`) it writes to. This is what makes "access them collectively" tractable — operators always know where the artifact lives.
2. **`document_templates` is the canonical structure registry.** Required sections per doc_key are enforced at the prompt level (skill prompt + agent prompt both reference the template). The Assets tab uses template metadata for display.
3. **Operator-CEO framing is explicit in every agent prompt.** Preamble: "You support the operator (the CEO of this account). You produce {primary_output_doc_key} markdown reports. You never take external action without an explicit operator approval via a task_interaction." Migration 121 enforces this.
4. **Chat is anchored on either task OR document, never floating.** `task_comments.document_id` is nullable: NULL = thread-level comment, non-NULL = document-revision comment. Operators choose by clicking either the thread or a doc revision.
5. **Phase 0 ships before any agent runtime.** De-risks the data model + UX shape under real human-to-human use before agents amplify any mistakes.

## What we are NOT lifting from paperclip

(Cross-reference: [paperclip-reference.md §10](./paperclip-reference.md).)

- Paperclip's 74-table footprint. We have ~15 application tables for the agent surface and that's enough.
- The `environments` / `execution_workspaces` / `workspace_operations` sandbox model. Our agents run inside the operator's already-trusted local helper.
- `companies` → `agents` 1:N hierarchy. We slot agents under `workspaces`, never under a separate "company" layer.
- "Open Issue" as the canonical post-launch destination. Our equivalent is "Open Task with updated document."
- The `goals` / `project_goals` / `routines` ecosystem — premature; can revisit in Phase 2+.

## References

- [paperclip-reference.md](./paperclip-reference.md) — canonical reference for paperclip patterns we lift.
- [skill-outputs-contract.md](./skill-outputs-contract.md) — the agent → doc_key → template mapping.
- [agent-runtime.md](./agent-runtime.md) — pre-existing spec for the runtime (predates this plan; cross-check at Phase 1 kickoff).
- [client-context-sync.md](./client-context-sync.md) — context-repo sync spec; relevant for `cited_context` and GitHubAdmin.
- Migrations: [112_agents.sql](../../migrations/112_agents.sql) through [118_task_interactions.sql](../../migrations/118_task_interactions.sql) (existing); 119-121 land in Phase 0; 122-123 in Phase 1.
