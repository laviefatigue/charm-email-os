---
title: Agent Runtime (Paperclip Pattern, Charm Adaptation)
status: spec — pre-implementation
created: 2026-05-15
owners: elliott
related:
  - [[design-system/brand-brief]]
  - [[design-system/references/ref-paperclip]]
  - [docs/concepts/esp-aware-data-interpretation.md]
---

# Charm Agent Runtime — Paperclip Pattern Adaptation

**Status:** Spec / pre-implementation. Captures the architectural direction agreed 2026-05-15 — Charm adopts paperclip's agent runtime + skills + adapters + auth + cost-tracking model, applied to email-infrastructure analyst-agents.

This doc is the source of truth for backend implementation. The design-system doc family ([[design-system/brand-brief]], [[design-system/references/ref-paperclip]]) consumes this spec for IA and component planning.

## Why Adopt Paperclip's Runtime

Two coexisting tiers handle Charm's operational work:

| Tier | Examples | Behavior |
|------|----------|----------|
| **Daemons** (existing) | EOD reapply, Plan F warmup-disable, hypertide audit, tag op worker | State-machine, deterministic. Execute policy. No LLM. Observable via `event_log`. |
| **Analyst Agents** (new — this spec) | Performance Analyst, Health Monitor, Domain Insights, Account Manager | LLM-backed (Claude via API). Reason over data. Propose policy via `request_confirmation`. Observable via new `agent_run_log`. |

Daemons we already have. Agents are new. Rather than build agent orchestration from scratch (heartbeat scheduler, adapter abstraction, JWT auth, cost tracking, recommendation surfacing, secret encryption), we lift paperclip's pattern verbatim. See [D:/Work/paperclip/docs/](D:\Work\paperclip\docs\).

## The Analyst Agents

| Agent | Skills (markdown) | Reads | Recommends | Cadence |
|-------|-------------------|-------|------------|---------|
| **Performance Analyst** | `burn-velocity-analysis`, `kill-cascade-forensics`, `deliverability-trends` | `event_log`, `inbox_metrics`, `domain_kill_history`, ESP-split reports, **client context repo** (voice, recent feedback, decisions) | "Workspace X approaching kill threshold — rotate domains A, B, C" | Daily timer + on-event (kill cascade fires) |
| **Infrastructure Health Monitor** | `drift-detection`, `warmup-audit`, `hypertide-reconcile` | `inbox_state`, `warmup_status`, `hypertide_subscriptions`, EB API state, **client context repo** (infra decisions, banned vendors) | "12 inboxes have warmup drift between EB and DB — reconcile?" | Every 4h timer + on-demand |
| **Domain Insights Advisor** | `burn-forecast`, `rotation-strategy`, `registrar-optimization` | `domain_lifecycle`, `burn_rate_history`, `registrar_spend`, Dynadot inventory, **client context repo** (ICP, domain-naming feedback) | "Workspace Y burn rate +18% MoM — pre-emptive rotation slate of 8 domains" | Weekly timer + on-demand |
| **Account Manager** *(later)* | `per-client-synthesis`, `capacity-planning`, `integration-orchestration` | All of the above + day.ai data + **client context repo** (full client card, decisions, stakeholders) | "Client Z over-capacity — pause incubation queue?" | Daily timer + on-demand |

**Client context repo** is a per-workspace GitHub-hosted Foam-markdown repo (scaffolded from `charm-client-template`) that holds AE notes, feedback, decisions, contracts, onboarding materials, and the client card. CharmDB syncs from these repos and exposes a context-query API. See [[client-context-sync]] for the full spec.

Each agent is a configured instance per workspace (or global, with workspace-filter context). Some skills are shared across agents (`drift-detection` could be invoked by Health Monitor and Performance Analyst).

## Runtime Architecture (paperclip pattern, lifted)

### Heartbeat Loop

Discrete runs, not continuous. Per paperclip's [agents-runtime.md](D:\Work\paperclip\docs\agents-runtime.md) and [heartbeat-protocol.md](D:\Work\paperclip\docs\guides\agent-developer\heartbeat-protocol.md):

1. **Wake trigger:** timer (cron), on-event (kill fired), on-demand (operator clicks "Analyze now"), or assignment (operator manually queues an analysis task)
2. **Coalesce:** if agent is already running, merge wakeups
3. **Spawn adapter:** Charm scheduler invokes the agent's configured adapter (e.g., `claude_local`) with full env-var injection
4. **Agent runs heartbeat:**
   - `GET /api/agents/me` → check identity + budget
   - If `CHARM_APPROVAL_ID` is set → resolve a pending confirmation first
   - `GET /api/issues?assigneeAgentId=...&status=todo,in_progress,in_review,blocked` → get assigned analysis tasks
   - Atomic checkout: `POST /api/issues/{id}/checkout` (409 = different agent owns it, never retry)
   - Read context, query Charm DB via skill-instructed SQL or HTTP API
   - Comment on progress (durable)
   - On completion: `PATCH /api/issues/{id}` with `status: done` + final comment
   - Optionally: create `request_confirmation` interaction with recommendation payload
5. **Adapter captures:** stdout/stderr, exit code, token usage, cost
6. **Server records:** `agent_run_log` row, cost-event, status update; pushes WebSocket update to UI

### Skills

Markdown files at `skills/{skill-name}/SKILL.md` with frontmatter — same format as paperclip's [writing-a-skill.md](D:\Work\paperclip\docs\guides\agent-developer\writing-a-skill.md).

```
skills/
  burn-velocity-analysis/
    SKILL.md                         # main instructions
    references/
      esp-aware-queries.md            # the actual SQL patterns
      historical-benchmarks.md
  drift-detection/
    SKILL.md
  rotation-strategy/
    SKILL.md
```

Skills are routing instructions — agents read skill descriptions first, load full content only when relevant. Skills teach the agent *what queries to run* against Charm DB and *how to structure the recommendation payload*.

Injection (per [claude-local.md](D:\Work\paperclip\docs\adapters\claude-local.md)): adapter symlinks skill directory into a temp dir, passes via `--add-dir` to Claude Code CLI. No pollution of agent working directory.

### Adapters

Built-in adapters available from paperclip (lift directly):

- `claude_local` — runs Claude Code CLI locally with `ANTHROPIC_API_KEY` env (or subscription). Primary for v1.
- `process` — arbitrary subprocess (Python analyst script). Useful when ESP-split logic is easier in pandas than prompted Claude.
- `http` — fire-and-forget webhook to external agent. For future remote-execution.

Adapter contract: receives `ExecutionContext`, spawns runtime, captures structured result (status, tokens, errors, cost). See [adapters/overview.md](D:\Work\paperclip\docs\adapters\overview.md).

### Authentication (verbatim lift)

Per [api/authentication.md](D:\Work\paperclip\docs\api\authentication.md):

- **Operator → Charm server:** Better Auth (cookie-session). Same as paperclip's web UI.
- **Agent → Charm server:** short-lived JWT injected per heartbeat as `CHARM_API_KEY` env var. Scoped to agent + run.
- **Long-lived agent keys** (for self-managed agents): `POST /api/agents/{id}/keys`. Hashed at rest.
- **Charm server → LLM provider:** secrets encrypted with local master key (`~/.charm/instances/default/secrets/master.key`), decrypted at runtime, injected as `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` env vars to adapter.
- **Strict mode** (`CHARM_SECRETS_STRICT_MODE=true` in production): enforce that agent configs reference secrets by ID, never inline values.

### Environment Variables Injected (full set, lift from paperclip's [environment-variables.md](D:\Work\paperclip\docs\deploy\environment-variables.md))

```
CHARM_AGENT_ID
CHARM_WORKSPACE_ID
CHARM_API_URL
CHARM_API_KEY                 # short-lived JWT
CHARM_RUN_ID
CHARM_TASK_ID                 # if any
CHARM_WAKE_REASON             # timer | event | on_demand | assignment | approval
CHARM_WAKE_EVENT_ID           # if waked by kill cascade etc.
CHARM_APPROVAL_ID             # if resumed after operator decision
CHARM_APPROVAL_STATUS         # approved | rejected
CHARM_LINKED_ISSUE_IDS        # comma-separated
ANTHROPIC_API_KEY             # decrypted from secret store
```

### Cost Tracking

Per [api/costs.md](D:\Work\paperclip\docs\api\costs.md):

- After heartbeat: adapter parses Claude output for usage; `POST /api/workspaces/{id}/cost-events` with `agentId`, `provider`, `model`, `inputTokens`, `outputTokens`, `costCents`
- Agents check budget at start of heartbeat: `GET /api/agents/me` → check `spentMonthlyCents` vs `budgetMonthlyCents`
- Thresholds: 80% soft alert (agent self-throttles to critical work only); 100% hard stop (server sets `status: paused`, no more heartbeats until ops resets or new budget month)
- Window resets first of each month UTC

Display: per-workspace Costs page shows agent LLM spend broken down by agent + month; rolls up to workspace card on home.

### Routines (scheduled triggers)

Per [api/routines.md](D:\Work\paperclip\docs\api\routines.md):

- **Schedule** — cron expression + timezone. E.g., Performance Analyst runs daily at 06:00 UTC.
- **Webhook** — external system triggers (HMAC-signed). E.g., when Hypertide pushes a subscription update, the Health Monitor wakes.
- **API** — manual invocation only. Operator clicks "Analyze now" → `POST /api/routines/{id}/run`.

Concurrency: `coalesce_if_active` (default) — incoming run merges with active. Catch-up: `skip_missed` (don't backfill).

### Recommendation Surfacing (the load-bearing UX)

When an analyst agent has a proposal for the operator, it creates a **`request_confirmation` interaction** on the issue (per [task-workflow.md](D:\Work\paperclip\docs\guides\agent-developer\task-workflow.md) and [handling-approvals.md](D:\Work\paperclip\docs\guides\agent-developer\handling-approvals.md)):

```http
POST /api/issues/{issueId}/interactions
{
  "kind": "request_confirmation",
  "idempotencyKey": "rotation:{workspaceId}:{forecastWindowEnd}",
  "continuationPolicy": "wake_assignee",
  "payload": {
    "version": 1,
    "prompt": "Rotate these 5 domains into reserve before EOD?",
    "summary": "Workspace HYPERTIDE — burn rate +18% MoM, kill cascade modeled to trigger in 4–6d. Proposed: rotate vapor-pulse / echo-pearl / drift-anchor / mist-flare / silver-vine. Replacement slate from incubation: ...",
    "data": { ... full structured recommendation ... },
    "acceptLabel": "Approve rotation",
    "rejectLabel": "Request changes",
    "rejectRequiresReason": true,
    "supersedeOnUserComment": true
  }
}
```

Operator sees this as an inline card in the Recommendations mailbox. One-click Approve wakes the agent with `CHARM_APPROVAL_STATUS=approved`; the agent then either creates implementation sub-tasks (delegated to daemons or the operator) or directly invokes the rotation API (if granted permission).

This is the *combining dashboard with real tools* mechanic: analysis + proposed action + execution + audit all in one thread.

## Data Model Additions

| Table | Purpose | Approx columns |
|-------|---------|----------------|
| `agents` | Configured analyst agents | id, workspace_id, name, adapter_type, adapter_config (json), status, budget_monthly_cents, spent_monthly_cents, ... |
| `agent_skills` | Skills registered to agents (many-to-many) | agent_id, skill_path, version |
| `agent_runs` | Heartbeat history | id, agent_id, run_id, wake_reason, started_at, ended_at, status, tokens_in, tokens_out, cost_cents, error |
| `issues` | Work units (analyst tasks) | id, workspace_id, assignee_agent_id, title, body, status (todo|in_progress|in_review|done|blocked), parent_id, goal_id, created_at, ... |
| `issue_comments` | Durable progress | id, issue_id, actor_type (agent|operator), actor_id, body, created_at |
| `issue_interactions` | `request_confirmation` cards + decisions | id, issue_id, kind, idempotency_key, payload (jsonb), status, decided_at, decided_by, decision_reason |
| `cost_events` | Per-run cost records | id, workspace_id, agent_id, run_id, provider, model, input_tokens, output_tokens, cost_cents, created_at |
| `routines` | Scheduled triggers | id, workspace_id, agent_id, title, concurrency_policy, catch_up_policy, status, ... |
| `routine_triggers` | Schedule / webhook / api configs | id, routine_id, kind, cron_expression, timezone, webhook_signing_mode, ... |
| `secrets` | Encrypted LLM provider keys | id, workspace_id (nullable for global), name, ciphertext, version, created_at |
| `agent_run_log` | Immutable activity stream | id, workspace_id, actor_type, actor_id, action, entity_type, entity_id, details (jsonb), created_at |

## Implementation Roadmap (phased)

**Phase 0 — Frontend redesign carries the agent surfaces in mockup form.** UI shows agent cards, recommendation mailbox, agent detail pages — even before backend runtime exists. Mocked data initially. This locks the UX.

**Phase 1 — Auth + secrets foundation.** Better Auth for operators. Local-master-key secret store. JWT issuance for agents. No agents yet — just the auth infrastructure.

**Phase 2 — Issue + comment + interaction model.** Tables + REST endpoints (`/api/agents`, `/api/issues`, `/api/issues/{id}/checkout`, `/api/issues/{id}/interactions`). No real agents yet — operator can create issues + interactions manually for testing.

**Phase 3 — Adapter scaffold + first agent.** `claude_local` adapter (lifted from paperclip source if open-source, otherwise re-implemented from its docs). First skill: `burn-velocity-analysis`. First agent: Performance Analyst (read-only — surfaces recommendation, doesn't act yet).

**Phase 4 — Heartbeat scheduler + routines.** Cron-based timer triggers. Operator-triggered on-demand runs. Coalescing logic.

**Phase 5 — Cost tracking + budgets.** Per-agent monthly cap, 80%/100% thresholds, auto-pause.

**Phase 6 — Second agent + on-event triggers.** Health Monitor with `drift-detection`. Wired to event_log so kill cascades wake it.

**Phase 7 — Recommendation approval → action loop.** Agent's approved recommendation actually invokes Charm APIs (rotation, EOD pause, hypertide reconcile). Full closed-loop.

**Phase 8 — Account Manager + day.ai integration.** Cross-data-source analyst that synthesizes Charm + external integrations.

## Open Questions

- **Adapter source:** is paperclip's `claude_local` adapter source available, or do we re-implement from docs? Need to check paperclip license + repo access.
- **Better Auth integration:** which Better Auth providers? Email/password initially, or SSO (Google Workspace) day-one?
- **Skill versioning:** how do we track when a skill's instructions change (recommendations from v1 should be tagged with the skill version that produced them, for replay/audit)?
- **Agent permissions:** can the Performance Analyst directly call the rotation API once approved, or does it create a sub-task that a daemon (Plan E) executes? (Probably daemon-execution for safety — agent proposes, operator approves, daemon enforces.)
- **Cross-workspace agents:** is there a "Global Performance Analyst" that surveys all 5 workspaces, or only per-workspace agents that one global agent aggregates from?
- **MSFT deprecation:** Performance Analyst skills must encode ESP-aware logic (see [docs/concepts/esp-aware-data-interpretation.md](../concepts/esp-aware-data-interpretation.md)) since MSFT and Google data have different scales (3 vs 52 inboxes/domain).
- **Context staleness gating:** if `client-context-sync` reports last sync > 6h ago, should agents refuse to make recommendations or just include a staleness caveat? See [[client-context-sync]] §Context-Query API.

## See Also

- [[design-system/brand-brief]] — workspace = client control plane with analyst agents
- [[design-system/references/ref-paperclip]] — concept mapping, IA, sub-nav structure
- [docs/concepts/esp-aware-data-interpretation.md](../concepts/esp-aware-data-interpretation.md) — required reading for any analyst skill
- [docs/plans/INBOX-INTEGRITY-PROGRAM.md](../plans/INBOX-INTEGRITY-PROGRAM.md) — daemon-tier master tracker
- Paperclip source docs: [D:/Work/paperclip/docs/](D:\Work\paperclip\docs\)
