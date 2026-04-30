---
title: EmailBison-Sync Decomposition — Service Split Plan
created: 2026-04-30
updated: 2026-04-30
status: PROPOSED — pending operator decisions on §6 boundaries and §11 sequencing
related:
  - docs/plans/cross-workspace-integrity-firewall.md
  - apps/eod-reapply/HANDOFF.md (the reference architecture)
  - production/coolify/services.md
non-goal:
  - Deprecating emailbison-sync until each extracted service is proven equivalent
  - Rewriting business logic — this is structural, not behavioral
---

# EmailBison-Sync Decomposition

## 0. TL;DR

The current `emailbison-sync` Coolify service runs ~10 distinct concerns in a single poll loop. Bugs in one (e.g., Sammy's `lifecycle_tag_sync` dead since 2026-04-13) are invisible because the others keep running. This plan splits the worker into focused services along a single principle:

> **One service per state-machine concern. Each service owns its lifecycle of an inbox in isolation. No service silently fails into another's blind spot.**

The split is staged — existing `emailbison-sync` keeps running unmodified while each extracted service is built, validated, and only then deprecated from the parent. Zero downtime, zero feature regression risk.

The user's specific question on `set_tag_sync` and `pool_promotion`: **`set_tag_sync` extracts as its own service, `pool_promotion` does NOT — it folds into inventory-manager (along with cap enforcement and future demotion). Reasoning in §6.5.**

---

## 1. The boundary principle (the test for "is this a service?")

A concern earns its own service if it satisfies all four:

1. **Owns a single state-machine concern** — incubation graduation, kill detection, EB-tag mirroring, etc. NOT a grab-bag.
2. **Has a distinct failure signature** — "incubation-watcher is unhealthy" tells you a specific class of bug, not "something is wrong somewhere."
3. **Can complete its work end-to-end without coordinating mid-flow with another service** — DB-mediated handoffs are fine, mid-flow RPC is not.
4. **Has a real cadence requirement** — daemon (continuous), scheduled (cron-like), or event-driven (queue-consumer). NOT "runs whenever the parent does."

Concerns that fail any of these tests stay in the parent.

---

## 2. Anti-principle (where I argue against more services)

Three traps I'm explicitly avoiding:

### 2.1 The micro-service trap
Decomposing every module into its own service produces a system harder to operate than a monolith. Each service has:
- Coolify config + env var sprawl
- Its own DB connection pool (total connections multiply)
- Its own deployment cycle
- Its own health check + alerting
- Its own log stream to correlate

By the time we have 12 services for what was 1 worker, debugging an incident is a query across 12 log streams. **The win isn't "more services" — it's "the right granularity of services."**

### 2.2 The premature abstraction trap
We have one cross-workspace concern (`workspace_api_keys.key_token`) that's already abstracted and proven via eod-reapply. We don't need a "shared workspace context manager" service. Each service reads `workspace_api_keys` directly, same pattern.

### 2.3 The deprecate-before-validating trap
The old `emailbison-sync` works (mostly). If we delete it before the new services prove they handle every edge case correctly, we lose data. The plan keeps `emailbison-sync` running until each extracted concern is shadowed in the new service AND audit confirms parity for ≥ 7 days.

---

## 3. Current state — what `emailbison-sync` is actually doing

Per [emailbison_sync_worker.py](emailbison_sync_worker.py) (top-level entry) and `sync_modules/`:

| Concern | Module | What it does | Cadence today |
|---------|--------|--------------|---------------|
| Account sync | `sync_accounts.py` | EB sender-emails → `sender_accounts` rows | every 1h per workspace (queue) |
| Campaign sync | `sync_campaigns.py` | EB campaigns → `campaigns` + `campaign_inboxes` | every 1h per workspace |
| Engagement sync | `sync_engagement.py` | EB campaign metrics → `inbox_engagement_snapshots` | every 24h per workspace |
| Warmup sync | `sync_warmup.py` | EB warmup state → `sender_accounts.warmup_*` | every 30min per workspace |
| Events sync | `sync_events.py` | EB events → various | every 5min per workspace |
| Lifecycle tags | `lifecycle_tag_sync.py` | Graduate incubating → reserve/live; tag new warmup; untag dead | every 30min per workspace |
| Set tag mirror | `set_tag_sync.py` | DB pool_status → EB tag (drift reconciler) | every 30min per workspace |
| Pool promotion | `pool_promotion.py` | Deficit-driven reserve → live | event-driven (called by kill_processor) |
| Kill detection | `health_checks.py` | Compute kill candidates from metrics | every 30min per workspace |
| Kill processing | `kill_processor.py` | Drain kill_queue: untag in EB, mark dead, promote replacement | every 15min per workspace |
| Domain integrity | `overhaul_audit.py` | Daily DB-only audit (9 metrics) | once per day, fleet |
| Slack reports | `slack_audit.py` | Twice-daily Slack alert | 6am/1pm Pacific |
| Domain post-hook | `sync_all_domains` (in sync_accounts) | Reverse-extract domains from senders | after every account sync |
| Workspace discovery | `workspace_discovery.py` | Find new EB workspaces | every 5min |

That's 14 distinct concerns. All running in one process, all sharing one main loop, all dependent on `workspace_sync_queue` for fanout.

The bug that exposed the chaos: when the queue stopped enqueuing `lifecycle_tags` for Sammy on 2026-04-13, it was invisible because account/campaign/engagement sync kept running. Sammy looked healthy externally — until graduation just stopped happening.

---

## 4. Service decomposition — proposed final state

Five services, with `emailbison-sync` slimmed to its actual job (data ingestion only).

### Service A: `emailbison-sync` (slimmed — data ingestion ONLY)

**Owns**: pulling data from EB into our DB. No state machine logic, no EB writes (except via tag-writer service).

**Modules**: `sync_accounts`, `sync_campaigns`, `sync_engagement`, `sync_warmup`, `sync_events`, `sync_all_domains`, `workspace_discovery`.

**API key**: workspace-scoped via `workspace_api_keys.key_token` (already current pattern).

**Cadence**: per-workspace via `workspace_sync_queue` (already current). Different sync types have different intervals (events 5m, warmup 30m, accounts 1h, engagement 24h).

**Output**: pure DB writes. No EB writes. No DB transitions of `inventory_pool_status` or `inventory_lifecycle_status` — those live in the state-machine services.

### Service B: `incubation-watcher` (NEW)

**Owns**: the incubation → graduation state machine. Per-workspace, runs continuously.

**Modules**: extracted `lifecycle_tag_sync.py` (slimmed to graduation + new-warmup tagging only).

**API key**: workspace-scoped (same Sanctum tokens).

**Cadence**: every 30min per active workspace (own poll loop, NOT via workspace_sync_queue — its own scheduling).

**State machine**:
- New warmup-on inbox without lifecycle → tag `incubating` in EB, set `lifecycle_status='incubating'`
- 14 BD elapsed since `warmup_enabled_since` → untag `incubating`, tag `reserve` (Google) or `live` (Microsoft), set `lifecycle_status='active'`, `pool_status='reserve'` or `'live'`
- Inbox already at `lifecycle='active'` but still has incubating tag → untag (orphan cleanup)

**Health check**: `/health` returns 200 if last successful pass < 1h ago; service-level alert if any active workspace has not been processed in > 2h.

### Service C: `inventory-manager` (NEW)

**Owns**: workspace inventory accounting. Reserve → live promotion, cap enforcement, future demotion.

**Modules**: extracted `pool_promotion.py` + new cap-enforcement logic + future `pool_demotion.py`.

**API key**: workspace-scoped.

**Cadence**: every 15min per active workspace (poll for deficit) + on-demand via API endpoint (kill_processor calls "now" when a live inbox dies).

**State machine**:
- Live count < target_live_count → pick eligible reserves, promote up to deficit (current `pool_promotion.pick_promotion_candidates`)
- Live count > target_live_count → ALERT (per §6.4 — no auto-demote in v1)
- Reserve inbox reconnects after disconnect → re-evaluate for promotion (NEW — closes the silent-fail gap)

**Critical change**: drop `status = 'Connected'` filter from candidate query (per the user's directive — promote unconditionally, connection is monitored separately by kill-watcher).

**Health check**: alert if any workspace has `live_count < target_live_count` AND eligible reserves > 0 for > 30min — that means promotion is broken.

### Service D: `kill-watcher` (NEW)

**Owns**: kill detection + kill processing + connection state machine + Hypertide escalation.

**Modules**: extracted `health_checks.py` + `kill_processor.py` + new `hypertide_disconnect_notifier.py`.

**API key**: workspace-scoped.

**Cadence**: every 15min per active workspace.

**State machine**:
- Bounce/spam thresholds met → enqueue kill → drain kill_queue (untag EB, mark dead in DB, request promotion from inventory-manager)
- 24h disconnected (Gmail) / 48h (Microsoft) → ping Hypertide (NEW)
- 21+ days disconnected → auto-kill (existing logic)

**Health check**: alert if `kill_queue` has rows in `pending` for > 1h, or if disconnect ping to Hypertide fails ≥ 3 times in a row.

### Service E: `tag-writer` (NEW)

**Owns**: writing EB tags as a reflection of DB authority. Drift reconciler.

**Modules**: extracted `set_tag_sync.py`.

**API key**: workspace-scoped.

**Cadence**: every 30min per active workspace.

**Job**: read DB rows where `inventory_pool_status` differs from current EB tag; reconcile by writing EB tag to match DB. Tag-first / untag-second ordering preserved.

**Health check**: alert if drift count (DB ≠ EB) > N for > 2 cycles in a row.

### Service F: `integrity-auditor` (NEW — covered by separate plan, mentioned for completeness)

**Owns**: daily audits. Per-workspace. Replaces and absorbs `inbox_audits` Slack reports.

**Modules**: extracted `overhaul_audit.py` + new cross-workspace pollution scanner + workspace-orphan detection.

**Cadence**: daily.

(Detail TBD in `docs/plans/inbox-audit-overhaul.md` per the deferred priority.)

### Final Coolify service map

| Service | Existing? | Modules owned |
|---------|-----------|---------------|
| `emailbison-sync` | EXISTING (slim down) | sync_accounts, sync_campaigns, sync_engagement, sync_warmup, sync_events, workspace_discovery, sync_all_domains |
| `incubation-watcher` | NEW | lifecycle_tag_sync (graduation + new-warmup) |
| `inventory-manager` | NEW | pool_promotion, cap enforcement, future demotion |
| `kill-watcher` | NEW | health_checks, kill_processor, hypertide_disconnect_notifier |
| `tag-writer` | NEW | set_tag_sync (DB→EB drift reconciler) |
| `integrity-auditor` | NEW (later) | overhaul_audit, cross-workspace pollution scan |
| `slack-audit` | KEEP (or extract later) | slack_audit |

Total: 7 services, up from 1. (`slack-audit` could stay folded if extraction adds nothing.)

---

## 5. Why these specific boundaries — and where I'd push back

### 5.1 `incubation-watcher` — strong yes

Single concern (graduation), distinct failure mode (Sammy), service-level health = answer to "is graduation happening for X workspace." Easy decision.

### 5.2 `kill-watcher` — strong yes

Owns the connection state machine end-to-end (detect disconnect, monitor 24h/48h, ping Hypertide, auto-kill at 21d). Currently fragmented across `health_checks`, `slack_audit`, and a missing Hypertide notifier. Consolidating makes the rule "what happens when an inbox disconnects?" answerable in one place.

### 5.3 `tag-writer` — yes, but smaller scope than I initially thought

Original instinct: extract `set_tag_sync` because it's the EB write boundary and deserves its own visibility.

**Critical pushback I'd make**: `set_tag_sync` is ALREADY a "drift reconciler" — it doesn't drive transitions, it mirrors them. Each state-machine service (incubation, inventory-manager, kill-watcher) already writes EB tags inline as part of its transitions. `tag-writer` is the janitor that catches drift after the fact.

So its scope shrinks: not "the EB write service" — just "the periodic drift detector + corrector." Could even be folded into `integrity-auditor` if drift incidents are rare. **My vote**: extract for now to maintain the current behavior, but evaluate after 30 days whether it's pulling its weight. If drift counts are reliably 0, fold it.

### 5.4 `inventory-manager` — strong yes

This answers your specific question (§6.5 below). Promotion + cap + future demotion are all "inventory accounting" — same source of truth (`workspace_packages`, `target_live_count`), same authority (DB writes to `inventory_pool_status`).

### 5.5 What does NOT extract — and why

**`workspace_discovery`** — runs every 5min, just looks for new EB workspaces. Folds into `emailbison-sync` data ingestion. Distinct service buys nothing.

**`sync_all_domains`** — pure SQL post-hook on account sync. Always runs alongside accounts. Folds into `emailbison-sync`.

**`workspace_sync_queue` itself** — it's a coordination primitive (Postgres queue), not a service. Stays in `emailbison-sync` because that's the only service that uses queue-driven fanout.

The other extracted services (`incubation-watcher`, `inventory-manager`, etc.) use SIMPLE poll loops, not the queue. The queue's complexity (priority, FOR UPDATE SKIP LOCKED, dedup) is overkill for a "every 30 min, scan all active workspaces, do work" pattern.

---

## 6. Specific decisions

### 6.1 Where do EB tag writes live?

Three options:
- **(a) Centralized**: only `tag-writer` writes EB tags. Other services update DB; tag-writer mirrors to EB.
- **(b) Distributed**: each service writes its own EB tags inline. tag-writer only reconciles drift.
- **(c) Hybrid**: state-transition writes go via a shared library (call this `eb_tag_write.py`), tag-writer is the periodic drift sweep.

**I recommend (b).** Reason: each state-machine service should atomically write DB + EB. Centralizing in tag-writer creates an eventual-consistency window where DB says live, EB still says reserve, and a campaign tries to send via the EB tag. **Atomicity is more important than centralization.**

The `tag-writer` then becomes purely a janitor — drift should be 0 if (b) works. Its existence is insurance, not the primary path.

### 6.2 Workspace API keys — shared library vs duplicated

Each extracted service needs `workspace_api_keys` lookup. Three options:
- **(a) Shared Python library** (a pip-installable `charm_workspace_clients` package) used by every service.
- **(b) Each service reimplements** (~50 lines of similar code per service).
- **(c) Sidecar pattern** — a separate "workspace context provider" service.

**I recommend (a).** The eod-reapply pattern already has this code (`apps/eod-reapply/src/eod_reapply/db.py` + `eb_client.py`). Promote it to a shared package or just copy-paste. (a) is cleanest; (b) is acceptable; (c) is over-engineering. **No to (c).**

### 6.3 DB connection pooling

Each service has its own asyncpg pool. Default pool size is 10 connections. Six services × 10 = 60 connections. The DB instance probably handles 100. Tight but fine.

If we hit limits, swap to a shared PgBouncer (one container, all services connect through it). Don't pre-optimize.

### 6.4 Cap-exceeded behavior

User asked earlier: when live_count > target_live_count, what happens?

**Three options**:
- (a) Auto-demote oldest live → reserve to bring count down. **Risky** — could disconnect a working campaign.
- (b) Alert only, no demotion. **Safer** — operator decides.
- (c) Block further promotion until count drops naturally via kills.

**I recommend (b)** for v1. Per the user's earlier-stated preference. (c) is implicitly true via deficit-driven promotion (no deficit = no promotion).

`inventory-manager` emits a Slack alert when `live_count > target_live_count` and includes the inboxes that are above target.

### 6.5 SHOULD `set_tag_sync` AND `pool_promotion` BE INDEPENDENT APPS — your direct question

**`set_tag_sync` → YES, its own service (`tag-writer`)**

Justification:
- Distinct failure mode: drift between DB and EB. Service health = "did anything fall out of sync in last cycle?"
- Distinct cadence (every 30min, drift sweep — vs. event-driven for state machines)
- Distinct API surface (only writes EB tags, never updates DB state)
- BUT scope shrinks per §6.1: it's the janitor, not the primary writer

**`pool_promotion` → NO, folds into `inventory-manager`**

Justification:
- It's not a standalone concern — it's one operation in the broader "inventory accounting" domain
- The other operations (cap enforcement, future demotion) need the same data (`workspace_packages`, `target_live_count`, `live_count`)
- Splitting promotion from cap enforcement creates two services that need the same SQL, same cadence, same alerting. Wasted overhead.
- "Inventory manager" is a coherent mental model; "pool_promotion-only service" is fragmented

**Combined: 5 new services + 1 slimmed = 6 total. Not 7.**

The "let's split it further" instinct is good — but the test is whether the split owns a distinct concern. `pool_promotion` alone doesn't.

---

## 7. Migration plan — DO NOT DEPRECATE existing code

This is the load-bearing principle. Approach:

### Phase 1 — Build & deploy alongside
For each new service:
1. Build the Coolify service (Dockerfile, env vars, health endpoint)
2. Move the relevant `sync_modules/` code into `apps/<service-name>/src/`
3. **Leave the original module in place in `emailbison-sync` and continue running it**
4. Run new service in **shadow mode** — same logic, but emits no EB writes (only logs what it would have done)
5. Compare shadow output vs production output for ≥ 7 days

### Phase 2 — Switch ownership
Once shadow output matches production for 7+ days:
1. Disable the module in `emailbison-sync` (feature flag: `ENABLE_LIFECYCLE_TAG_SYNC=false`)
2. Enable real writes in the new service
3. Monitor for 7 days
4. **Keep the disabled module in `emailbison-sync` as backup** — can re-enable instantly if the new service breaks

### Phase 3 — Remove dead code
After 30 days of stable operation in new service:
1. Delete the module from `emailbison-sync`
2. Update Dockerfile to not COPY it
3. Remove env-var feature flag

### Phase 4 — Slim emailbison-sync
After all five extractions land:
1. emailbison-sync is now data-ingestion-only
2. Rename if desired (`data-sync-worker`?)
3. Optimize: data ingestion can run faster without state-machine overhead

**Critical**: at every phase, the existing system is running and working. We have a rollback at every step. No big-bang migration.

---

## 8. Shared infrastructure

### 8.1 Code sharing
- `charm_workspace_clients` (NEW shared package) — workspace API key lookup, scoped EB client. Used by all services. Source: lift from `apps/eod-reapply/src/eod_reapply/db.py` + `eb_client.py`.
- `charm_audit_logger` (existing `sync_modules/audit_logger.py`) — promote to shared.
- `charm_slack_alerter` (existing `sync_modules/slack_alerter.py`) — promote to shared.

Implementation: monorepo, each service includes the shared package via `pip install -e ../shared/`. Or copy-paste if monorepo tooling is overkill.

### 8.2 Database access
Each service has its own asyncpg pool. Shared schema, no service-private tables. Migrations stay in `migrations/` and run from `charm-api` startup (existing pattern).

### 8.3 Observability
Each service:
- Health endpoint at `/health` (200 = OK, 503 = degraded)
- Structured logs to stdout (JSON) — Coolify aggregates
- Per-service Slack channel optional, or keep single `#inbox-audits`

### 8.4 Deployment topology

```
┌─────────────────────────────────────────────────────────────┐
│  Coolify (single VPS or cluster)                             │
│                                                              │
│  ┌─────────────────────┐   ┌─────────────────────────────┐  │
│  │ charm-api           │   │ charm-frontend              │  │
│  │ (FastAPI)           │   │ (Next.js)                   │  │
│  └─────────────────────┘   └─────────────────────────────┘  │
│                                                              │
│  ┌─────────────────────┐   ┌─────────────────────────────┐  │
│  │ emailbison-sync     │   │ incubation-watcher  ← NEW   │  │
│  │ (data ingestion)    │   │ (graduation only)           │  │
│  └─────────────────────┘   └─────────────────────────────┘  │
│                                                              │
│  ┌─────────────────────┐   ┌─────────────────────────────┐  │
│  │ inventory-manager   │   │ kill-watcher        ← NEW   │  │
│  │ ← NEW               │   │ (kill + connection)         │  │
│  │ (promotion + cap)   │   │                             │  │
│  └─────────────────────┘   └─────────────────────────────┘  │
│                                                              │
│  ┌─────────────────────┐   ┌─────────────────────────────┐  │
│  │ tag-writer  ← NEW   │   │ integrity-auditor   ← LATER │  │
│  │ (drift reconciler)  │   │ (audit + scan)              │  │
│  └─────────────────────┘   └─────────────────────────────┘  │
│                                                              │
│  ┌─────────────────────┐                                    │
│  │ Other services...   │                                    │
│  │ hypertide-worker    │                                    │
│  │ price-checker       │                                    │
│  │ dayai-watcher       │                                    │
│  │ executive-dashboard │                                    │
│  │ domain-worker       │                                    │
│  └─────────────────────┘                                    │
└─────────────────────────────────────────────────────────────┘
```

Total: 13 Coolify services post-extraction, up from 8.

---

## 9. Critical risks — what could go wrong

### 9.1 Race conditions between services

**Risk**: incubation-watcher graduates an inbox to `pool='reserve'` at T=0. Inventory-manager polls at T+1s, sees a deficit, picks the just-graduated reserve. Tag-writer hasn't written `reserve` to EB yet. Inventory-manager promotes it to `live`, writes `live` tag. EB now has `live` without ever having `reserve`. Confusing but not broken.

**Mitigation**: each service writes EB tag atomically with DB (per §6.1). The intermediate state never persists in EB.

**Worse case**: incubation-watcher updates DB to `lifecycle='active', pool='reserve'`, fails the EB write, raises an error. DB row says reserve, EB has nothing. Tag-writer's drift sweep catches it on next cycle — fixes EB. Acceptable.

### 9.2 Coordinated deploy failures

**Risk**: a schema migration breaks ONE service's queries. We have to roll forward (services share schema).

**Mitigation**: schema changes are additive-only (per existing migration discipline). Drop columns in a separate migration only after all consumers are updated.

### 9.3 Shadow-mode false positives

**Risk**: shadow mode says "I would have graduated 5 inboxes" but production graduated 4. Is that a bug or correct? Need a comparison harness.

**Mitigation**: comparison runs daily during Phase 1. Differences > expected variance trigger investigation BEFORE enabling writes.

### 9.4 Service explosion of audit_log writes

**Risk**: each service writes to `sync_audit_log`. Six services × every cycle = 6× the rows. Storage blows up.

**Mitigation**: partition `sync_audit_log` by month if not already. Retention policy: drop > 90 days.

### 9.5 Shared library version skew

**Risk**: `charm_workspace_clients` v1.2 in incubation-watcher, v1.1 in kill-watcher. Behavior diverges.

**Mitigation**: pin version in each service's `pyproject.toml`. CI gate on shared lib changes.

### 9.6 Network/auth failures during cross-service handoff

**Risk**: kill-watcher kills an inbox, calls `inventory-manager` API for replacement promotion. Network blip → no replacement → workspace under-cap.

**Mitigation**: NO synchronous service-to-service RPC. All handoffs are DB-mediated:
- kill-watcher writes `kill_queue` row → inventory-manager polls and promotes on next cycle (15min later). Bounded staleness, no network dependency.

This is the eod-reapply principle: services share state via DB, not via API calls.

### 9.7 Operator confusion

**Risk**: 13 services is a lot. "Which service handles X?" becomes a non-trivial question.

**Mitigation**: per-service README + the [production/coolify/services.md](production/coolify/services.md) gets a "concerns matrix" — what concerns each service owns. Single page reference.

---

## 10. Specific cost estimate

| Service | Effort | Risk | Validation period |
|---------|--------|------|-------------------|
| `incubation-watcher` | 1.5 days | Low — module is well-isolated | 7 days shadow + 7 days primary |
| `inventory-manager` | 2 days | Medium — promotion logic is intricate | 14 days shadow (multiple cycles) |
| `kill-watcher` | 2 days | Medium — kill_processor is the most complex | 14 days shadow + 7 days primary |
| `tag-writer` | 1 day | Low — already a reconciler | 7 days shadow |
| `emailbison-sync` slim | 0.5 days | Low — just removing modules | 7 days post-extraction |
| Total | **7 days dev + 4-5 weeks total elapsed (with shadow validation)** | | |

That's ~6-8 weeks calendar time to fully decompose with safety. If we collapse shadow validation to 3 days each, it's 3-4 weeks.

---

## 11. Sequencing — what extracts first

**Order**:

1. **`incubation-watcher`** (Week 1) — fixes the active Sammy bleed. Highest immediate value.
2. **`tag-writer`** (Week 2, parallel) — extracts cleanly, low risk, gives us a drift signal we don't have today.
3. **`kill-watcher`** (Week 3) — adds the Hypertide 24h ping, fixes connection-state machine.
4. **`inventory-manager`** (Week 4) — drops `status='Connected'` filter from promotion, adds cap-exceeded alerts.
5. **Slim emailbison-sync** (Week 5) — remove now-unused modules.
6. **`integrity-auditor`** (Week 6+) — covered by separate plan, follows once primary firewall is stable.

**Could be parallelized**: incubation-watcher + tag-writer in week 1-2 since they have different code. kill-watcher + inventory-manager have a coupling (kill triggers promotion) — better to do sequentially.

---

## 12. Decisions needed before this ships

| # | Decision | Default |
|---|----------|---------|
| D-1 | Shadow validation period: 3 days vs 7 days | 7 days (safer) |
| D-2 | Shared library: pip-installable package vs copy-paste | copy-paste for v1, package for v2 (less tooling overhead now) |
| D-3 | Cap-exceeded behavior: alert-only (b) vs auto-demote (a) | (b) alert-only |
| D-4 | EB tag writes: distributed inline vs centralized in tag-writer | distributed inline (atomic with DB) |
| D-5 | Where does the workspace_sync_queue stay? | emailbison-sync only — extracted services use simple poll loops |
| D-6 | Sammy fix urgency: ship lifecycle bug fix in current emailbison-sync FIRST, then extract? | Ship bug fix in current code now (1 hour), extract afterward (1 week). Don't block bug fix on extraction. |

D-6 is critical: Sammy is bleeding capacity NOW. We should fix the lifecycle_tag_sync silent failure (wrap `tag_inbox` in try/except, log + skip on workspace orphan) in the existing `emailbison-sync` THIS WEEK, then extract once that fix is stable. Don't tie the urgent fix to a multi-week refactor.

---

## 13. What this plan does NOT do

- Doesn't change business logic (graduation rules, kill thresholds, pool capacities).
- Doesn't fix Hypertide's upstream wrong-workspace bug (the firewall plan handles that).
- Doesn't reorganize the database schema (those are separate ADRs).
- Doesn't introduce a service mesh, Kubernetes, or any orchestration beyond Coolify.
- Doesn't deprecate `emailbison-sync` until after Phase 4 (week 5+).

---

## 14. Critical assessment — am I being honest?

Three things I want to be clear about:

**(1) This is structural, not behavioral.** Splitting into services doesn't directly fix any bug. It changes WHERE bugs surface and HOW visible they are. The silent-failure pattern in `lifecycle_tag_sync` exists in either architecture — extracted or not. We have to fix the try/except hiding the EB tag failure regardless.

**(2) I'm proposing 6 new services where you might be thinking 2-3.** Be honest with yourself on whether the operational cost (more containers, more configs, more deploys) is worth the visibility gain. If the answer is "we want one extracted service to prove the pattern," that's incubation-watcher. The rest is incremental.

**(3) The user's specific value proposition was "easier to pinpoint."** That's solved by 2-3 extracted services, not 6. If `incubation-watcher` proves the pattern works for graduation, deciding whether to extract `kill-watcher` is a separate evaluation. We don't have to commit to all 6 today.

**My recommendation if you want to start small**: extract `incubation-watcher` first as a proof of concept. If after 30 days it's clearly winning (visibility + faster bug isolation), extract the others. If it's not winning, you've learned cheaply.

---

## 15. Want to reduce scope?

Minimum viable decomposition (faster, lower risk):
- Extract `incubation-watcher` only.
- Fix lifecycle silent failures in-place in `emailbison-sync` for everything else.
- Add Hypertide 24h ping as a small new module in `emailbison-sync`.

That's 1.5 days dev + 1 week shadow. Catches Sammy. Doesn't introduce 5 new services.

Full decomposition (this plan) is right if you want long-term clarity. Minimum viable is right if you want a fix this week and decide later.

**Both are honest options. Pick which one.**
