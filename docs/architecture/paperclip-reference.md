# Paperclip — reference documentation

> Read-only reference doc for the Charm team. We do not depend on paperclip; we lift patterns from it. The full canonical source lives at `D:\Work\paperclip-reference\` (a clone of `github.com/laviefatigue/paperclip`, isolated from Charm). The modified instance from our earlier experiments is preserved at `D:\Work\paperclip.modified\`.
>
> Everything in this doc is sourced directly from paperclip's code at the snapshot we pulled, not from memory or third-party summaries. Where useful, links point into `D:\Work\paperclip-reference\` so a curious reader can verify.

## 1. What paperclip actually is

A Node.js server + React UI that runs **AI companies**: a Company has Agents, Agents pick up Tasks (called Issues in the schema), and Agents are invoked by a Heartbeat scheduler. Each agent invocation is a `heartbeat_run`. Agents talk to LLMs through pluggable **adapters** — `claude-local`, `codex-local`, `cursor-local`, `bash`, `http`, plus a plugin ecosystem.

Key shape:

- **Self-hosted, single binary feel.** `pnpm dev` spins up an embedded PostgreSQL (port 54329) + Node API (port 3100) + UI on the same port.
- **No cloud control plane.** Per-instance data lives in `~/.paperclip/instances/{id}/`.
- **Zero credentials stored for LLMs.** Adapters spawn whatever CLI is already authenticated on the host (see §3).
- **Issue-centric UX.** The first thing the operator sees after onboarding is the issue page for the first task, not a dashboard.

Top-level repo layout:

```
paperclip-reference/
├── cli/                              # paperclipai onboarder
├── server/                           # Express + Drizzle + scheduler
├── ui/                               # React UI
├── packages/
│   ├── db/                           # Drizzle schema (74 tables)
│   ├── adapters/
│   │   ├── claude-local/             # The reference adapter — our lift target
│   │   ├── codex-local/
│   │   ├── cursor-local/
│   │   └── ...
│   ├── plugins/                      # SDK + example plugins
│   └── shared/                       # cross-package types
├── skills/                           # paperclip-managed Claude skills
└── docs/                             # paperclip's own docs
```

## 2. Onboarding wizard — 4 steps

The canonical first-run flow is `Company → Agent → Task → Launch`. Screenshots: [docs/design-system/references/paperclip-screenshots/fresh/](../design-system/references/paperclip-screenshots/fresh/).

| Step | Fields | Notes |
|------|--------|-------|
| **Company** ([01](../design-system/references/paperclip-screenshots/fresh/01-company.png)) | name, mission (optional) | Two fields total. No SSO, no billing, no permissions. |
| **Agent** ([02](../design-system/references/paperclip-screenshots/fresh/02-agent.png)) | name (default "CEO"), adapter type (Claude Code or Codex flagged Recommended), model (Default), **adapter env probe** ([02b](../design-system/references/paperclip-screenshots/fresh/02b-agent-probe-passed.png)) | "More Agent Adapter Types" hides the long tail. The "Test now" button is the load-bearing UX (see §3). |
| **Task** ([03](../design-system/references/paperclip-screenshots/fresh/03-task.png)) | title, description (optional) | Wizard prefills suggested copy. |
| **Launch** ([04](../design-system/references/paperclip-screenshots/fresh/04-launch.png)) | recap card | CTA is "Create & Open Issue" — routes straight to `/{CODE}/issues/{CODE}-1` ([05](../design-system/references/paperclip-screenshots/fresh/05-issue-detail.png)). |

After launch, the dashboard at `/{CODE}/dashboard` ([06](../design-system/references/paperclip-screenshots/fresh/06-company-home.png)) shows the populated company. URL slug is auto-generated from company name (`Charm Email OS` → `CHA`).

**Three design choices worth lifting:**

1. **Two fields max per step.** Everything else defers.
2. **Defaults that work.** Agent name "CEO", adapter "Claude Code", model "Default", task copy pre-filled. The wizard is clickable end-to-end without typing anything.
3. **Land on the work, not the dashboard.** "Create & Open Issue" routes to the actual issue page where the agent is already running.

## 3. Claude account connection — the probe pattern

**Paperclip stores zero Anthropic credentials.** It piggybacks on whatever auth state the local `claude` CLI already has from `claude login`.

The "Test now" button in the Agent step runs `claude-local`'s `testEnvironment()` from [packages/adapters/claude-local/src/server/test.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/test.ts). The probe is:

```bash
claude --print - --output-format stream-json --verbose
  + stdin: "Respond with hello."
```

It then parses the stream-json output looking for the word "hello" (case-insensitive) in the result. Success → green "Passed" pill. The probe also runs three preflight checks before invoking Claude:

| Check | Code | Level |
|-------|------|-------|
| `cwd` is a valid absolute directory (creates if missing) | `claude_cwd_valid` / `claude_cwd_invalid` | info / error |
| `command` is resolvable on PATH | `claude_command_resolvable` / `claude_command_unresolvable` | info / error |
| Auth mode detection (see below) | varies | varies |

### The three auth modes

From `resolveClaudeBillingType()` in [execute.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/execute.ts):

```ts
function resolveClaudeBillingType(env): "api" | "subscription" | "metered_api" {
  if (isBedrockAuth(env)) return "metered_api";
  return hasNonEmptyEnvValue(env, "ANTHROPIC_API_KEY") ? "api" : "subscription";
}
```

| Mode | Detection | Probe treatment |
|------|-----------|-----------------|
| **Subscription (Pro/Max)** | `ANTHROPIC_API_KEY` unset + `claude login` complete | Default / preferred. `claude_subscription_mode_possible` (info). |
| **API key** | `ANTHROPIC_API_KEY` set (anywhere) | **Warns** with `claude_anthropic_api_key_overrides_subscription` + hint: "Unset ANTHROPIC_API_KEY if you want subscription-based Claude login behavior." |
| **AWS Bedrock** | `CLAUDE_CODE_USE_BEDROCK=1` or `ANTHROPIC_BEDROCK_BASE_URL` set | Info. Assumes AWS creds (`AWS_ACCESS_KEY_ID` etc.) are present. |

A fourth state — **login required** — is detected by parsing the CLI's stream-json output via `detectClaudeLoginRequired()` ([parse.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/parse.ts)). Surfaces a hint with the login URL: "Run `claude login` and complete sign-in at {url}, then retry."

### Subscription quota readout

[quota.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/quota.ts) shows paperclip can also *read* Claude subscription quota two ways:

- **OAuth token** — reads the OAuth token from `~/.claude/` and hits Anthropic's quota API directly (preferred).
- **CLI scrape** — runs `claude` and parses the ANSI-stripped output of the `/usage` panel as a fallback.

Both deliberately strip `ANTHROPIC_*` env vars before invocation so quota always reports on the subscription, never on an overridden API key.

## 4. Agent runtime — how a heartbeat actually runs

Reading `execute()` in [execute.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/execute.ts) (777 lines, this is the load-bearing file), one invocation flows like this:

```
1. buildClaudeRuntimeConfig(input)
   - resolves cwd (workspace > config > process.cwd())
   - builds env (merging buildPaperclipEnv(agent) + config.env + process.env)
   - resolves command path
   - decides billing type (subscription / api / metered_api)

2. prepareClaudePromptBundle({ companyId, skills, instructionsContents, onLog })
   - computes content-addressed bundleKey = sha256 of (instructions + sorted skill contents)
   - materializes ~/.paperclip/instances/{id}/companies/{cid}/claude-prompt-cache/{bundleKey}/.claude/skills/
   - skills are symlinked into the bundle dir
   - instructions written as agent-instructions.md (atomic via tmp + rename)
   - returns { bundleKey, rootDir, addDir, instructionsFilePath }

3. Build prompt by joining sections in order:
   - renderedBootstrapPrompt (template, on cold start only)
   - wakePrompt (heartbeat context — what woke us up)
   - sessionHandoffNote (from prior run)
   - taskContextNote (issue body)
   - renderedPrompt (the default template)

4. Build argv:
   claude --print - --output-format stream-json --verbose
     [--resume {sessionId}]                       # if continuing
     [--dangerously-skip-permissions]             # default true
     [--model {id}]                               # if set (Bedrock validates)
     [--effort {level}]
     [--max-turns {N}]
     [--append-system-prompt-file {instructions}] # only on fresh session
     --add-dir {promptBundle.addDir}              # always
     [...extraArgs]

5. Spawn subprocess with the joined prompt on stdin.

6. parseClaudeStreamJson(stdout) — extract sessionIdAfter, usage, result.

7. Detect special outcomes:
   - max_turns hit  → retryable
   - unknown session → drop sessionId and retry fresh
   - login required → surface login URL to operator
   - transient upstream error → schedule retry with backoff (parses --retry-after)

8. Return AdapterExecutionResult { exitCode, sessionId, usage, result, ... }
```

### Session continuity

Paperclip persists `sessionId` between heartbeats so multi-turn conversations don't restart. The `sessionCodec` in [server/index.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/index.ts) serializes `{ sessionId, cwd, promptBundleKey, workspaceId, repoUrl, repoRef }`. On the next invocation, the runtime only resumes the session if **all of these match**:

- `sessionId` is non-empty
- `promptBundleKey` matches (skills + instructions are unchanged — otherwise the cached system prompt is stale)
- `cwd` matches
- `remoteExecution` identity matches (for remote execution targets)

If any drift, it starts a fresh session and logs why. This is the "no silent context corruption" pattern — if you change skills, you don't accidentally resume a stale session.

### Important Claude CLI subtleties paperclip learned the hard way

These are coded into `runAttempt()` and worth lifting verbatim:

- `--append-system-prompt-file` and `--resume` are **mutually exclusive** in the CLI. Don't re-inject instructions on resumed sessions — they're already in the session cache, and re-sending wastes 5-10K tokens per heartbeat.
- For Bedrock, the `--model` flag must be a Bedrock-native ID (`us.anthropic.*` or ARN). Anthropic-style IDs like `claude-opus-4-7` get rejected. Solution: skip `--model` entirely on Bedrock and let the CLI use its own configured model.
- The instructions file gets a path directive appended so Claude resolves sibling instruction files (`HEARTBEAT.md`, `SOUL.md`, `TOOLS.md`) from the right base directory.

## 5. Skills & content-addressed prompt cache

From [prompt-cache.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/prompt-cache.ts):

```
~/.paperclip/
└── instances/
    └── {instanceId}/                # "default" or PAPERCLIP_INSTANCE_ID
        └── companies/
            └── {companyId}/
                └── claude-prompt-cache/
                    └── {bundleKey}/              # sha256 of (instructions + skills)
                        ├── agent-instructions.md
                        └── .claude/
                            └── skills/
                                ├── skill-a/      # symlink → source
                                ├── skill-b/      # symlink → source
                                └── ...
```

- **`bundleKey` is a sha256.** Inputs: paperclip version tag (`v1`), instructions contents, then for each skill (sorted by `runtimeName`): the skill key + a recursive directory hash that walks symlinks safely (tracks `seenDirectories` to handle cycles).
- **Skills are symlinks**, not copies. The bundle dir is essentially a manifest.
- **Bundle is content-addressed** — if neither instructions nor skills change, the same `bundleKey` is reused, so the Claude CLI's own prompt cache stays warm.
- **`--add-dir {bundleDir}`** is always passed so Claude can read the materialized skills.
- **Atomic writes**: instructions file is written to `{target}.{pid}.{timestamp}.tmp` then renamed.

The skills listing API ([skills.ts](../../../paperclip-reference/packages/adapters/claude-local/src/server/skills.ts)) distinguishes:

- `paperclip_required` — required by paperclip itself (always materialized)
- `company_managed` — opt-in per company
- `user_installed` — discovered in `~/.claude/skills/` outside paperclip's control (read-only)

## 6. Database schema

Embedded PostgreSQL, Drizzle ORM. **74 tables.** Listing at [packages/db/src/schema/](../../../paperclip-reference/packages/db/src/schema/).

### Load-bearing tables (the ones to lift)

#### `agents` ([agents.ts](../../../paperclip-reference/packages/db/src/schema/agents.ts))

```
id                          uuid PK
company_id                  uuid FK companies(id)
name                        text
role                        text default "general"
title, icon                 text
status                      text default "idle"
reports_to                  uuid FK agents(id)            -- org chart
capabilities                text
adapter_type                text default "process"
adapter_config              jsonb default {}              -- per-adapter shape
runtime_config              jsonb default {}
default_environment_id      uuid FK environments(id)
budget_monthly_cents        int default 0                 -- stop-loss
spent_monthly_cents         int default 0
pause_reason                text                          -- kill switch
paused_at                   timestamptz
permissions                 jsonb default {}
last_heartbeat_at           timestamptz
metadata                    jsonb
created_at, updated_at      timestamptz
```

Indexes: `(company_id, status)`, `(company_id, reports_to)`, `(company_id, default_environment_id)`.

#### `heartbeat_runs` ([heartbeat_runs.ts](../../../paperclip-reference/packages/db/src/schema/heartbeat_runs.ts))

One row per agent invocation. The full execution forensics table.

```
id                          uuid PK
company_id, agent_id        uuid FK
invocation_source           text default "on_demand"
trigger_detail              text
wakeup_request_id           uuid FK agent_wakeup_requests(id)

-- Lifecycle
status                      text default "queued"         -- queued | running | finished | error
started_at, finished_at     timestamptz
exit_code, signal           int / text
error, error_code           text

-- LLM output
usage_json                  jsonb                         -- token usage
result_json                 jsonb                         -- final result blob
session_id_before           text                          -- Claude session continuity
session_id_after            text

-- Log addressing (offload bulky logs)
log_store                   text                          -- "disk" | "s3" | "db"
log_ref                     text                          -- key into the store
log_bytes                   bigint
log_sha256                  text
log_compressed              bool default false
stdout_excerpt              text                          -- inline preview
stderr_excerpt              text

-- Process management (clean kill + liveness)
external_run_id             text
process_pid                 int
process_group_id            int
process_started_at          timestamptz
last_output_at              timestamptz
last_output_seq             int default 0
last_output_stream          text
last_output_bytes           bigint
liveness_state              text                          -- alive | stalled | dead
liveness_reason             text

-- Retry tree
retry_of_run_id             uuid FK heartbeat_runs(id)
process_loss_retry_count    int default 0
scheduled_retry_at          timestamptz
scheduled_retry_attempt     int default 0
scheduled_retry_reason      text

-- Multi-turn continuation
continuation_attempt        int default 0
last_useful_action_at       timestamptz
next_action                 text
context_snapshot            jsonb

-- Issue feedback loop
issue_comment_status                          text default "not_applicable"
issue_comment_satisfied_by_comment_id         uuid
issue_comment_retry_queued_at                 timestamptz
```

Indexes optimized for the watchdog and the recent-activity view: `(company_id, agent_id, started_at)`, `(company_id, liveness_state, created_at)`, `(company_id, status, last_output_at)`, `(company_id, status, process_started_at)`.

#### `issue_thread_interactions` ([issue_thread_interactions.ts](../../../paperclip-reference/packages/db/src/schema/issue_thread_interactions.ts))

The "agent needs operator input" pattern. One row per pending decision attached to an issue.

```
id                                uuid PK
company_id, issue_id              uuid FK
kind                              text                    -- request_confirmation | approval | ...
status                            text default "pending"
continuation_policy               text default "wake_assignee"
idempotency_key                   text                    -- partial UQ on (company_id, issue_id, key)
source_comment_id                 uuid FK issue_comments(id)
source_run_id                     uuid FK heartbeat_runs(id)
title, summary                    text
created_by_agent_id               uuid FK agents(id)
created_by_user_id                text
resolved_by_agent_id              uuid FK agents(id)
resolved_by_user_id               text
payload                           jsonb (typed)
result                            jsonb (typed)
resolved_at                       timestamptz
```

The `(company_id, issue_id, idempotency_key)` partial unique index (where `idempotency_key IS NOT NULL`) is the load-bearing piece: an agent retry can't accidentally create a duplicate pending interaction.

### The full 74-table footprint (clustered)

What each cluster is for, briefly. We will not lift most of these.

| Cluster | Tables | Purpose |
|---------|--------|---------|
| **Org** | companies, company_memberships, company_logos, company_user_sidebar_preferences, instance_user_roles, instance_settings | Multi-tenant company layer |
| **Auth** | auth, board_api_keys, cli_auth_challenges, invites, join_requests, principal_permission_grants | Better Auth + CLI tokens + invitations |
| **Agents** | agents, agent_api_keys, agent_config_revisions, agent_runtime_state, agent_task_sessions, agent_wakeup_requests | Agent lifecycle + config history |
| **Runs** | heartbeat_runs, heartbeat_run_events, heartbeat_run_watchdog_decisions | Execution log + event stream + watchdog audit |
| **Issues** | issues, issue_comments, issue_labels, labels, issue_relations, issue_attachments, issue_documents, issue_read_states, issue_reference_mentions, issue_thread_interactions, issue_tree_holds, issue_tree_hold_members, issue_inbox_archives, issue_work_products, issue_execution_decisions, issue_approvals | The issue tracker model |
| **Approvals** | approvals, approval_comments, issue_approvals | Three different approval shapes — global, threaded, issue-attached |
| **Goals / Projects** | goals, projects, project_goals, project_workspaces | The "everything traces to a goal" layer |
| **Routines** | routines | Scheduled / recurring work |
| **Budget** | budget_policies, budget_incidents, cost_events, finance_events | Per-agent + per-company financial governance |
| **Execution** | environments, environment_leases, execution_workspaces, workspace_operations, workspace_runtime_services | Sandbox model for agent code execution |
| **Documents** | documents, document_revisions, assets | Content store outside the issue thread |
| **Secrets** | company_secrets, company_secret_versions | Encrypted secret storage |
| **Skills** | company_skills | Per-company skill enablement |
| **Plugins** | plugins, plugin_company_settings, plugin_config, plugin_database, plugin_entities, plugin_jobs, plugin_logs, plugin_state, plugin_webhooks | BYO-agent adapter ecosystem |
| **Feedback** | feedback_votes, feedback_exports | UX feedback loop |
| **Audit** | activity_log | Cross-cutting activity stream |
| **UI prefs** | user_sidebar_preferences, company_user_sidebar_preferences, inbox_dismissals | Per-user UI state |

## 7. Adapter contract (for non-Claude adapters)

The pattern that lets paperclip support multiple agents. Each adapter package (e.g. `@paperclipai/adapter-claude-local`) exports from its `server/index.ts`:

- `execute(ctx)` — main entry point; spawns the CLI and returns `AdapterExecutionResult`
- `runClaudeLogin()` — auth flow trigger (adapter-specific)
- `testEnvironment(ctx)` — the probe; returns `{ status: pass|warn|fail, checks: [...] }`
- `listClaudeModels()` / `listClaudeSkills(ctx)` / `syncClaudeSkills(ctx, desired)` — capability discovery
- `getQuotaWindows()` / `fetchClaudeQuota()` / `fetchClaudeCliQuota()` — quota readout
- `sessionCodec` — `{ serialize, deserialize, getDisplayId }` for session persistence

There's also a parser pair: `parseClaudeStreamJson`, `describeClaudeFailure`, `isClaudeMaxTurnsResult`, `isClaudeUnknownSessionError`. Each adapter implements its own.

The shared infrastructure (`@paperclipai/adapter-utils`) provides: `runChildProcess`, env helpers (`ensurePathInEnv`, `applyPaperclipWorkspaceEnv`, `buildPaperclipEnv`), prompt template helpers (`renderPaperclipWakePrompt`, `joinPromptSections`), skill discovery (`readPaperclipRuntimeSkillEntries`), and the remote execution target layer.

## 8. Process management & liveness

This is the part most agent runners get wrong. Paperclip's model:

- **Track `process_pid`, `process_group_id`, `process_started_at` on `heartbeat_runs`.** Needed for clean SIGTERM on the whole process tree.
- **Stream output through a sequence counter.** `last_output_at`, `last_output_seq`, `last_output_stream`, `last_output_bytes` — the watchdog uses these to decide "still alive vs stalled vs dead."
- **Separate `liveness_state` (watchdog opinion) from `status` (run lifecycle).** A run can be `status=running, liveness_state=stalled` — the run hasn't exited but the watchdog flagged it as unhealthy.
- **`heartbeat_run_watchdog_decisions` audits every watchdog action.** When the watchdog decides to kill or retry a run, it records why. Useful for debugging "why did my agent get killed."
- **Retry tree via `retry_of_run_id`.** Each retry is a new run, FK-linked to its parent. Lets you reconstruct "run A failed, run B retried it, run C resumed B's session."
- **Two retry counters.** `process_loss_retry_count` (the watchdog gave up on the process) vs `scheduled_retry_attempt` (planned retry from a previous failure). Different policies.

## 9. Lift priorities for Charm

In rough value-for-effort order. Each entry has explicit scope so we don't accidentally lift the whole platform.

| # | Pattern | Lift target | Effort | Notes |
|---|---------|-------------|--------|-------|
| 1 | **Adapter probe ("Test now")** | Local helper `GET /probe` + cloud UI status pill | S | Solves the "no copy-paste credentials" requirement. The probe runs the same hello-prompt paperclip uses. |
| 2 | **`heartbeat_runs` log shape** | New `charm.agent_runs` table with `log_store / log_ref / log_sha256` columns | M | Run history in CharmDB, bulky logs offloaded to disk/S3. Don't store stdout inline. |
| 3 | **`issue_thread_interactions` idempotency + continuation_policy** | Rename to `task_interactions`, attach to `tasks.id` instead of `issues.id` | M | The cleanest "agent asks, operator answers, agent resumes" model. Partial unique index on idempotency_key is critical. |
| 4 | **`adapter_type` + `adapter_config` jsonb** | Two columns on `charm.agents` | XS | Future-proofs for non-Claude adapters without schema churn. Mirror paperclip's exact shape. |
| 5 | **Per-agent monthly budget** | `budget_monthly_cents` + `spent_monthly_cents` int columns on `charm.agents` | XS | Stop-loss without a real budgeting system. |
| 6 | **`reports_to` self-FK + `role` text** | Two columns on `charm.agents` | XS | When we hire a second agent per workspace, we already have the org graph. |
| 7 | **`pause_reason` + `paused_at`** | Two columns on `charm.agents` | XS | Kill switch with audit trail, no separate table. |
| 8 | **Content-addressed prompt bundle** | Replicate `prompt-cache.ts` in our local helper | M | sha256 over (instructions + skills), symlink skills, `--add-dir` the bundle. Keeps Claude's prompt cache warm. |
| 9 | **Session continuity rules** | `sessionId` only resumed if `(promptBundleKey, cwd, remoteExecution)` all match | M | The "no silent context corruption" pattern. Log every drift case. |
| 10 | **Three auth-mode detection** | Mirror `resolveClaudeBillingType()` in helper + surface in UI | S | If we ever see `ANTHROPIC_API_KEY`, warn the operator they're paying per-token instead of using their subscription. |
| 11 | **Process liveness watchdog** | `last_output_at` / `last_output_seq` on agent_runs + a separate `liveness_state` | M | Differentiate "running" from "alive." |
| 12 | **Retry tree** | `retry_of_run_id` FK on agent_runs | XS | Reconstruct the retry chain after the fact. |

## 10. What to NOT lift

- **The 74-table footprint.** Most is goal/budget/plugin/approval ecosystem we don't need yet.
- **The `environments` / `execution_workspaces` / `workspace_operations` triple.** Paperclip needs a sandbox model because agents can spawn arbitrary code. Our agents run inside the operator's already-trusted local helper; the helper *is* the sandbox.
- **The `companies` → `agents` 1:N hierarchy.** Charm already has clients → workspaces; we slot agents under workspace, not under a separate "company" concept.
- **"Open Issue" as the canonical post-launch destination.** Charm operators don't think in issues — they think in tasks attached to projects attached to workspaces. The recap-step pattern still works; the destination changes (`/workspaces/{id}/tasks/{taskId}`).
- **Better Auth + invites + join_requests.** We have our own auth model coming. Don't import paperclip's.
- **The plugin/webhook ecosystem.** Premature for us; we can revisit once we have >1 adapter in production.
- **Their own `skills/` directory.** We bring our own. The bundle/cache mechanism is what we lift, not their skill content.

## Appendix — useful file pointers

| Reference file (in `D:\Work\paperclip-reference\`) | What it shows |
|---------------------------------------------------|---------------|
| `packages/adapters/claude-local/src/server/test.ts` | The full probe + auth-mode detection (250 lines) |
| `packages/adapters/claude-local/src/server/execute.ts` | The 777-line subprocess runner — the load-bearing file |
| `packages/adapters/claude-local/src/server/prompt-cache.ts` | Content-addressed bundle (sha256 + symlinks + atomic writes) |
| `packages/adapters/claude-local/src/server/skills.ts` | Skill discovery and origin classification |
| `packages/adapters/claude-local/src/server/parse.ts` | stream-json parser + login-required detector + retry-after extractor |
| `packages/adapters/claude-local/src/server/quota.ts` | OAuth-token + CLI-scrape subscription quota readout |
| `packages/db/src/schema/agents.ts` | `agents` table |
| `packages/db/src/schema/heartbeat_runs.ts` | `heartbeat_runs` table (the forensics shape) |
| `packages/db/src/schema/issue_thread_interactions.ts` | The interaction/idempotency pattern |
| `cli/src/index.ts` | The `npx paperclipai onboard --yes` entry — bind presets, instance setup |
| `server/` | Express app, scheduler, watchdog, all the wiring |
