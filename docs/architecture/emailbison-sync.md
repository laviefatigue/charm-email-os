---
title: EmailBison Sync Worker
created: 2026-04-13
updated: 2026-04-13
tags: [sync, emailbison, worker, architecture, queue]
---

# EmailBison Sync Worker

`emailbison_sync_worker.py` — background worker that keeps our database in sync with EmailBison and manages inbox lifecycle.

## Two Responsibilities

The worker does two distinct things. They share the same process but are architecturally separate:

| Responsibility | Modules | Direction | Concurrency |
|---------------|---------|-----------|-------------|
| **Data pull** | sync_accounts, sync_campaigns, sync_events, sync_warmup, sync_engagement | EB → DB | 3 workspaces concurrent |
| **Tag write** | lifecycle_tag_sync, set_tag_sync, kill_processor | DB → EB | Sequential (all workspaces per run) |

Data pull is managed by `WorkspaceSyncQueue`. Tag writes are called directly from the poll loop on their own schedules and remain sequential — they use the shared admin API key and manage their own workspace context.

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

### Workspace-Scoped Keys

Each workspace has its own EB API token stored in `workspace_api_keys` (migration 089). The token is context-bound to that workspace — no `switch_workspace()` call is needed. The queue loads the key at job dispatch time.

```sql
-- Check key status
SELECT w.workspace_name, w.emailbison_workspace_id::text as eb_id,
       (wak.id IS NOT NULL) as has_key
FROM workspaces w
LEFT JOIN workspace_api_keys wak ON wak.workspace_id = w.id AND wak.is_active = TRUE
WHERE w.is_active = TRUE ORDER BY w.workspace_name;
```

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

Every 15 min:  run_health_checks()
Every 30 min:  run_kill_processing() (currently DISABLED)
               run_lifecycle_tag_sync()
Daily:         retention cleanup, 24h counter reset, engagement sync (via queue)
```

---

## Module Map

```
sync_modules/
├── workspace_sync_queue.py    ← queue manager: schedule, claim, dispatch, status
├── sync_accounts.py           ← data pull: inbox list from /sender-emails
├── sync_campaigns.py          ← data pull: campaigns + inbox assignments
├── sync_events.py             ← data pull: replies/bounces/spam per campaign
├── sync_warmup.py             ← data pull: warmup stats + auto-enable logic
├── sync_engagement.py         ← data pull: daily engagement snapshots
├── lifecycle_tag_sync.py      ← tag write: incubating/live/flagged lifecycle
├── set_tag_sync.py            ← tag write: A-Set/B-Set pool tags
├── kill_processor.py          ← tag write: process kill queue
├── emailbison_client.py       ← HTTP client wrapper for EB API
├── audit_logger.py            ← sync_audit_log + sync_status writes
└── slack_alerter.py           ← Slack webhook notifications
```

---

## Key Environment Variables

Set on the `emailbison-sync` Coolify service:

| Variable | Default | Description |
|----------|---------|-------------|
| `SYNC_WORKSPACE_CONCURRENCY` | `3` | Workspaces processed in parallel |
| `SYNC_INTERVAL_PRIORITY` | `30` | Seconds between priority-queue polls |
| `ENABLE_LIFECYCLE_TAGGING` | `true` | Enable lifecycle tag writes to EB |
| `ENABLE_KILL_PROCESSING` | `false` | Enable kill queue processing |
| `EMAILBISON_API_KEY` | — | Admin-level key for discovery + tagging |
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
