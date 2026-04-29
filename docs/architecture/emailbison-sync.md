---
title: EmailBison Sync Worker
created: 2026-04-13
updated: 2026-04-28
tags: [sync, emailbison, worker, architecture, queue, overhaul-2026-04-27]
---

# EmailBison Sync Worker

`emailbison_sync_worker.py` — background worker that keeps our database in sync with EmailBison and manages inbox lifecycle.

> **2026-04-27 tagging-kill overhaul**: tag writes are now workspace-scoped and concurrent (was: serial via shared admin key). Per-inbox `inventory_pool_status` is the sole authority for set tag reconciliation (was: derived from domain.pool_status every cycle). See [[2026-04-27-tagging-kill-overhaul-plan]] for the full design + handoff doc, or the "Tag Write Orchestrator" section below for the operational summary.

## Two Responsibilities

The worker does two distinct things. They share the same process but are architecturally separate:

| Responsibility | Modules | Direction | Concurrency |
|---------------|---------|-----------|-------------|
| **Data pull** | sync_accounts, sync_campaigns, sync_events, sync_warmup, sync_engagement | EB → DB | 3 workspaces concurrent (semaphore) |
| **Tag write** | workspace_writes (orchestrator) → lifecycle_tag_sync → set_tag_sync → kill_processor | DB → EB | 3 workspaces concurrent (semaphore); sequential within each workspace |

### Tag writes — concurrent post-overhaul

Pre-overhaul, tag writes were serial because they all used the shared admin API key and called `switch_workspace()` between workspaces. That race was eliminated by migration 089's `workspace_api_keys` table — every tag write now goes through a workspace-scoped client (no `switch_workspace()` needed), so multiple workspaces can run their tag writes in parallel without any shared state.

Within a single workspace, the orchestrator still runs lifecycle → set → kill **sequentially** because the three phases have hard ordering constraints (graduate must complete before set tag reconciliation; reconciliation must complete before kill processing). Cross-workspace concurrency is bounded by `SYNC_WORKSPACE_CONCURRENCY` (default 3) — same semaphore as data pulls.

---

## Data Pull: Concurrent Queue Architecture

### Old Model (removed)

```
admin key → switch_workspace(A) → sync A → switch_workspace(B) → sync B → ...
Total time = sum of all workspace sync times
```

### New Model

```
workspace_sync_queue table
        │
        ├─ schedule_overdue_syncs()   ← inserts jobs for workspaces past their interval
        │
        └─ process_pending_batch()    ← claims 3 jobs atomically (FOR UPDATE SKIP LOCKED)
                │
                ├─ _run_job(workspace A)  ─┐
                ├─ _run_job(workspace B)  ─┤─ asyncio.gather(), concurrent
                └─ _run_job(workspace C)  ─┘
                        │
                        └─ workspace-scoped API key from workspace_api_keys
                           → EmailBisonClient(api_key=<scoped_key>)
                           → no switch_workspace() needed
```

Total time ≈ max(single workspace sync) × ⌈N / 3⌉ instead of sum(all).

### Workspace-Scoped API Keys

#### Why they replace switch_workspace()

EmailBison uses Laravel Sanctum for API auth. When you create a token scoped to a specific workspace, every request made with that token is automatically restricted to that workspace — no `switch_workspace()` call is needed and none is possible. The key itself *is* the workspace context.

The old model used a single shared admin key and called `switch_workspace(eb_workspace_id)` before each sync. This was:
- **Sequential by design** — two concurrent callers using the same key would fight over which workspace it was "switched" to
- **Fragile** — a crash between switch and sync left the client in the wrong workspace for the next call
- **Slow** — every `switch_workspace()` was a round-trip API call before the actual work started

With per-workspace keys, each `EmailBisonClient` instance is independent. Ten can run in parallel with no coordination.

#### Table structure (`workspace_api_keys`, migration 089)

```sql
workspace_api_keys (
    id                     UUID PRIMARY KEY,
    workspace_id           UUID REFERENCES workspaces(id),  -- our internal ID
    emailbison_workspace_id INT,                             -- EB numeric ID (for reference)
    key_name               VARCHAR,                         -- human label
    key_token              TEXT,                            -- the actual Bearer token
    is_active              BOOLEAN DEFAULT TRUE,
    created_at / updated_at TIMESTAMPTZ
)
```

One row per workspace. `UNIQUE(workspace_id)` — only one active key per workspace at a time.

#### How keys are provisioned

New workspaces discovered by the daily workspace discovery task are auto-provisioned: the task calls the EB API to generate a scoped token and inserts it into `workspace_api_keys` immediately. No manual steps.

For manual provisioning (e.g. re-keying a workspace): use the internal `_tmp_create_key.py` script, which calls the EB token creation endpoint and inserts the result.

```sql
-- Check which active workspaces have keys
SELECT w.workspace_name, w.emailbison_workspace_id::text as eb_id,
       (wak.id IS NOT NULL) as has_key
FROM workspaces w
LEFT JOIN workspace_api_keys wak ON wak.workspace_id = w.id AND wak.is_active = TRUE
WHERE w.is_active = TRUE ORDER BY w.workspace_name;
```

Workspaces without a key are excluded from queue scheduling. `log_missing_keys()` logs a warning at worker startup listing any that are missing.

### Sync Types and Intervals

| Sync Type | Interval | What it does |
|-----------|----------|-------------|
| `events` | 5 min | Replies, bounces, spam per campaign inbox |
| `accounts` | 1 hr | Inbox list, status, metrics from `/sender-emails` |
| `campaigns` | 1 hr | Campaign list and inbox assignments |
| `warmup` | 30 min | Warmup stats per inbox; auto-enables warmup for connected inboxes |
| `engagement` | 24 hr | Daily engagement snapshots (opens, replies, interested) |

Post-hooks (called by the queue dispatcher after the module's `sync_workspace()` completes):
- **accounts** → `sync_all_domains()` — creates missing domain rows, updates health scores
- **campaigns** → `sync_campaign_inbox_assignments(workspace_id)` — maps campaign↔inbox pairings

### Job Lifecycle

```
pending → running → complete
                 ↘ failed
```

Failed jobs are not retried immediately. The scheduler re-queues any workspace where `sync_status.last_successful_sync` is older than the interval, so a failure naturally re-enters the queue on the next scheduler tick (~30s later for events, ~1hr for accounts).

The partial unique index `ON workspace_sync_queue(workspace_id, sync_type) WHERE status='pending'` prevents duplicate pending jobs. `ON CONFLICT DO NOTHING` is safe to call repeatedly.

---

## Force-Refresh API

Client dashboard can trigger immediate sync for any workspace:

```
POST /api/sync/workspaces/{workspace_id}/refresh
```

Inserts all 5 sync types at `priority=10`. The worker's 30-second priority poll loop picks them up within ~30 seconds. Returns which types were queued vs already running.

```
GET /api/sync/workspaces/{workspace_id}/status
```

Returns `last_successful_sync` per type and current pending/running queue jobs. Used to show sync freshness in the client dashboard.

Both endpoints require a valid user session (`get_current_user`) and validate that the workspace exists and is active.

---

## Poll Loop Schedule

```
Every 30s:
  1. process_priority_batch()   ← pick up any priority=10 force-refresh jobs
  2. schedule_overdue_syncs()   ← insert pending jobs for overdue workspaces
  3. process_pending_batch()    ← claim and execute next batch of 3

Every 15 min:  run_health_checks()           ← compute kill triggers, update kill_queue
               run_workspace_writes()        ← lifecycle → threshold → set → kill per workspace
Every 5 min:   run_workspace_discovery()     ← detect new EB workspaces, auto-provision
Daily:         retention_cleanup, daily_counter_reset, daily_snapshot,
               onboarding_monitor, run_overhaul_audit
```

`run_workspace_writes()` replaces the old separate `run_lifecycle_tag_sync()` + `run_kill_processing()` path. Both feature flags still apply: `ENABLE_LIFECYCLE_TAGGING` gates lifecycle + set tagging; `ENABLE_KILL_PROCESSING` gates the kill queue branch. When both are false the orchestrator is skipped entirely.

---

## Module Map

```
sync_modules/
├── workspace_sync_queue.py    ← queue manager: schedule, claim, dispatch, status
├── workspace_writes.py        ← NEW: tag-write orchestrator (lifecycle→threshold→set→kill, concurrent per workspace)
├── pool_promotion.py          ← NEW: shared promotion picker (domain-aware, used by kill + threshold)
├── overhaul_audit.py          ← NEW: daily drift detector (dual-tag, stuck-incubation, burned-in-campaigns, ...)
├── sync_accounts.py           ← data pull: inbox list from /sender-emails
├── sync_campaigns.py          ← data pull: campaigns + inbox assignments
├── sync_events.py             ← data pull: replies/bounces/spam per campaign
├── sync_warmup.py             ← data pull: warmup stats + auto-enable logic
├── sync_engagement.py         ← data pull: daily engagement snapshots
├── lifecycle_tag_sync.py      ← tag write: graduate (incubating→reserve|live), tag new, untag dead, untag orphan incubating
├── set_tag_sync.py            ← tag write: per-inbox `inventory_pool_status` reconciliation (live/reserve/none)
├── kill_processor.py          ← tag write: process kill_queue, cross-domain promote, small-domain safety net
├── health_checks.py           ← compute kill triggers (with 20-send floor)
├── emailbison_client.py       ← HTTP client wrapper; supports `is_workspace_scoped` flag
├── audit_logger.py            ← sync_audit_log + sync_status writes (metadata jsonb merge on complete)
└── slack_alerter.py           ← Slack webhook notifications
```

---

## Tag Write Orchestrator (post-overhaul)

`WorkspaceWriteOrchestrator` (in [sync_modules/workspace_writes.py](../../sync_modules/workspace_writes.py)) drives DB→EB writes per workspace, with concurrency bounded by the same semaphore that gates data pulls.

### Per-workspace pipeline

```
for each workspace W (concurrency = SYNC_WORKSPACE_CONCURRENCY):
    if W.pause_pool_transitions: skip
    client = EmailBisonClient(api_key=W.workspace_api_key, is_workspace_scoped=True)

    1. lifecycle_tag_sync.sync_workspace_tags(W, client)
         a. _graduate_mature_inboxes        — incubating → reserve|live (ESP-aware) at 14 BD
         b. _tag_new_warmup_inboxes         — NULL or 'incubating' → tag 'incubating' in EB (idempotent self-heal)
         c. _remove_live_from_dead          — safety net for dead inboxes that still carry 'live'
         d. _untag_incubating_from_active   — orphan-tag cleanup driven by inbox_rotation_history (last 24h)

    2. orchestrator._maintain_pool_thresholds(W) [only if W.package_id IS NOT NULL]
         — read workspace_effective_targets view, compute deficit, promote reserve → deployed
           via pool_promotion.pick_promotion_candidates (domain-aware ordering)

    3. set_tag_sync.sync_workspace_sets(W, client)
         — per-inbox reconciliation: tag-first/untag-second discipline, MS pin, circuit breaker

    4. kill_processor.process_workspace_queue(W.id, W.name)
         — drain kill_queue rows for this workspace; cross-domain promote on each kill;
           Google instant burn; MS skip cross-domain promote (legacy ride-to-death)
```

### Per-inbox pool authority (set_tag_sync)

Pre-overhaul: `domain.pool_status` was authoritative — every cycle re-derived each inbox's tag from its domain's pool. This blocked cross-domain promotion (the next set_tag_sync cycle reverted it).

Post-overhaul: `sender_accounts.inventory_pool_status` is the SOLE authority. Each inbox carries its own pool tag decision. `domain.pool_status` is now a default for new graduations and a scope marker for burn events — it does not drive tag reconciliation.

Mapping:

| `inventory_pool_status` | EB tags |
|---|---|
| `'live'` | `live` (and untag `reserve`) |
| `'reserve'` | `reserve` (and untag `live`) |
| `'warning'` | NEITHER (active circuit breaker; auto-clears when bounces subside) |
| `'quarantined'` | NEITHER (active circuit breaker) |
| `NULL` | NEITHER (unallocated, no pool) |

### ESP differentiation

- **Microsoft Entra (legacy)**: pinned to `live` in set_tag_sync regardless of pool. Per CEO Rule C2 ("ride to death"), Microsoft inboxes never go to reserve and never have their `live` tag stripped by the warning circuit breaker.
- **Google**: full pool authority applies — reserve, live, warning all enforced.

### Tag-first / untag-second ordering

```
for each inbox:
    1. TAG TARGET FIRST   ← if target_tag_id is not None
    2. UNTAG OPPOSITE     ← only after tag succeeded
```

Failure-mode reasoning: if untag-first, a transient tag failure leaves the inbox with NO pool tag (campaigns can't pick it). With tag-first, a failure on untag leaves a transient dual-tag that self-heals on the next 15-min cycle. Dual tags are operationally less harmful than orphans.

### Reconciling untag every cycle

set_tag_sync issues an idempotent untag of the OPPOSITE pool tag on every cycle, even when DB and EB already match. This fixes a historic skip-bug where mismatched stale tags persisted because the per-cycle "did anything change?" check was too eager to skip.

### What "Connected" check gates

set_tag_sync skips inboxes where EB `status != 'Connected'` at line 436. This means:

- Disconnected inboxes that flipped to `pool='warning'` keep their stale `live`/`reserve` EB tags until either reconnection OR the 21-day `disconnected_timeout` kill path fires.
- This is a conservative design — we accept some stale tags rather than risk a tag operation against an unstable inbox connection.

---

## Daily Overhaul Audit

[sync_modules/overhaul_audit.py](../../sync_modules/overhaul_audit.py) runs once per UTC day from the worker's poll loop. Read-only; reports drift via Slack alert when any anomaly count is non-zero.

| Metric | What it measures |
|---|---|
| `dual_tag_candidates` | DB heuristic — graduated reserve inboxes whose population pre-overhaul was at risk of stale `live` tags. Should trend to 0 post-deploy. (Note: this is a population count, not a real-time EB tag check — see scripts/audit_tags_fleet.py for the EB-side check.) |
| `warmup_disabled_active_24h` | Live inboxes whose warmup_enabled flipped to FALSE more than 24h ago — they will not graduate. |
| `orphan_inactive_live_count` | Inboxes with `is_active=FALSE` AND `inbox_state='live'` AND a real `emailbison_account_id`. Invisible to all sync paths but EB may still send through them. |
| `stuck_incubation_14bd` | Inboxes still `lifecycle='incubating'` after 14 business days of warmup_enabled. Should be 0 post-deploy. |
| `incubating_in_campaigns` | Bypass guard for the Stable Kernel ODSC pattern — inboxes still incubating but pushed to a real EB campaign. |
| `burned_inboxes_in_campaigns` | Reputation risk — inboxes on burned/cancelled domains still in active campaigns. Currently manual cleanup; auto-cleanup function pending. |
| `kill_queue_pending_over_2h` | (added ADR-007 — replaces deprecated `pool_warning_should_have_no_pool_tag`) Pending kills older than 2h. kill_processor runs every 15 min, so this should be 0 in steady state. Non-zero indicates stuck queue, worker health issue, or workspace API key invalid. |
| `flagged_but_alive_count` | (added migration 099) kill_queue rows with `status='flagged'` for inboxes still at `inbox_state='live' AND killed_at IS NULL`. Should be 0 — current kill_processor is DB-first inside a single try block so flagged → dead is atomic. Drift indicates resurrection or legacy partial-kill state. |

The audit's `complete()` writes the metric counts into `sync_audit_log.metadata` (jsonb merge), so the historical trend is queryable.

For an EB-side validation (actual tag state, not DB-derived heuristics), use [scripts/audit_tags_fleet.py](../../scripts/audit_tags_fleet.py) — fleet-wide DB↔EB tag comparison via workspace-scoped API keys.

---

## Per-Workspace Module Contract

Each data pull module was refactored from a global orchestrator to a single-workspace unit. This is what changed and what the contract looks like now.

### What was removed from every module

| Removed | Why |
|---------|-----|
| `sync_all_workspaces()` | Replaced by `WorkspaceSyncQueue.schedule_overdue_syncs()` |
| `emailbison_workspace_id: int` parameter | No longer needed — client is pre-scoped |
| `switch_workspace(eb_workspace_id)` call | Eliminated by workspace-scoped API keys |
| `inter_batch_delay()` calls | No shared client = no shared rate limit to throttle |

### What every data pull module looks like now

```python
class SomeSyncModule:
    def __init__(self, db, client, audit_logger, alerter):
        # client is already scoped to one workspace — caller's responsibility
        self.client = client
        ...

    async def sync_workspace(self, workspace_id: UUID, workspace_name: str) -> SyncResult:
        # Operates on exactly one workspace.
        # No switch_workspace(). No global queries across workspaces.
        # Returns SyncResult so the queue can mark the job complete/failed.
        ...
```

`WorkspaceSyncQueue._dispatch()` instantiates the module, passes the pre-scoped client, calls `sync_workspace()`, then calls any post-hooks.

### Module-specific notes

**sync_events.py** — Unlike the others, events sync iterates campaigns (not inboxes directly). The new `sync_workspace()` queries `emailbison_campaigns WHERE workspace_id = $1` to scope it. The old `sync_all_active_campaigns()` is retained in the file as `DEPRECATED` — it still uses `switch_workspace()` and is valid for one-off manual backfills but must never be called from the concurrent worker.

**sync_warmup.py** — `auto_enable_warmup_for_connected()` was previously called by the orchestrator after the warmup sync. It's now called as a post-step *inside* `sync_workspace_warmup()`, since the workspace-scoped client is already available there. The queue doesn't need to know about it.

**sync_engagement.py** — `backfill_workspace()` is retained unchanged as a standalone script helper for historical data loads. It's not called from the worker.

**sync_campaigns.py** — `sync_campaign_inbox_assignments()` was previously global (iterated all workspaces, called `switch_workspace()` between each). It's now workspace-scoped: takes `workspace_id` and only processes that workspace's inboxes. The queue calls it as a post-hook after `sync_workspace()` completes.

### Writing a new data pull module

If you add a sixth sync type:

1. Create `sync_modules/sync_something.py` with `sync_workspace(workspace_id, workspace_name) -> SyncResult`
2. Add `'something'` to `SYNC_TYPES` in `workspace_sync_queue.py`
3. Add an interval to `DEFAULT_INTERVALS`
4. Add a dispatch branch in `_dispatch()`
5. Add the interval to the worker's `run_data_sync()` call
6. Add tests to `tests/test_workspace_sync_queue.py`

The module must not call `switch_workspace()`, must not make cross-workspace queries, and must not call `inter_batch_delay()`.

---

## Key Environment Variables

Set on the `emailbison-sync` Coolify service:

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_WORKSPACE_CONCURRENCY` | `3` | Workspaces processed in parallel (data pulls AND tag writes) |
| `SYNC_INTERVAL_PRIORITY` | `30` | Seconds between priority-queue polls |
| `SYNC_INTERVAL_KILL` | `900` | Seconds between workspace_writes runs (15 min) — drives lifecycle + threshold + set + kill |
| `ENABLE_LIFECYCLE_TAGGING` | `true` | Enable lifecycle + set tag writes to EB |
| `ENABLE_KILL_PROCESSING` | `true` | Enable kill queue processing (was `false` pre-overhaul) |
| `EMAILBISON_API_KEY` | — | Admin-level key — used ONLY for workspace discovery (legitimate cross-workspace path). NOT used for tag writes anymore. |
| `POSTGRES_*` | — | Database connection |

---

## Monitoring

### Queue State

```sql
-- Current job status breakdown
SELECT sync_type, status, COUNT(*) as cnt
FROM workspace_sync_queue
GROUP BY sync_type, status
ORDER BY sync_type, status;

-- Recent failures
SELECT w.workspace_name, q.sync_type, q.error_message, q.completed_at
FROM workspace_sync_queue q
JOIN workspaces w ON w.id = q.workspace_id
WHERE q.status = 'failed'
ORDER BY q.completed_at DESC
LIMIT 20;

-- Stuck jobs (running > 30 min)
SELECT workspace_id, sync_type, started_at,
       NOW() - started_at AS elapsed
FROM workspace_sync_queue
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '30 minutes';
```

### Sync Freshness

```sql
-- Last successful sync per type
SELECT sync_type,
       COUNT(*) as workspaces,
       MIN(last_successful_sync) as oldest,
       MAX(last_successful_sync) as newest
FROM sync_status
GROUP BY sync_type ORDER BY sync_type;
```

### Log Patterns

```
[EventSync] [Workspace Name] Syncing events for N campaigns
[AccountSync] [Workspace Name] Synced N accounts
[WarmupSync] [Workspace Name] N inboxes enabled
[SyncQueue] Scheduled N overdue sync jobs          ← scheduler inserted jobs
[SyncQueue] Missing API keys for N workspaces      ← startup warning
[ERROR] Poll loop error: ...                       ← check immediately
```

---

## Adding a New Workspace

New workspaces are discovered automatically via the daily workspace discovery task. When a new EB workspace is found:

1. A `workspaces` DB row is created
2. A `clients` row is created
3. An OAuth queue entry is added
4. A workspace-scoped API key is auto-generated and stored in `workspace_api_keys`
5. A force-refresh is queued so all 5 sync types run immediately

No manual steps required.

---

## Troubleshooting

**Worker starts but poll loop errors immediately:**
Check for SQL type inference issues — asyncpg extended protocol is strict. Look at the error detail for the parameter number.

**Workspace not being synced:**
```sql
-- Check if workspace has an active API key
SELECT has_key FROM (
  SELECT (wak.id IS NOT NULL) as has_key
  FROM workspaces w
  LEFT JOIN workspace_api_keys wak ON wak.workspace_id = w.id AND wak.is_active = TRUE
  WHERE w.workspace_name = 'Workspace Name'
) x;
```

**Jobs stuck in `running` status:**
The worker crashed mid-job. Safe to reset:
```sql
UPDATE workspace_sync_queue
SET status = 'failed', error_message = 'Reset after worker crash'
WHERE status = 'running'
  AND started_at < NOW() - INTERVAL '30 minutes';
```

**Force-refresh not picked up quickly:**
Check `SYNC_INTERVAL_PRIORITY` env var — should be `30` (seconds). If it's `300`, force-refresh latency is 5 minutes.
