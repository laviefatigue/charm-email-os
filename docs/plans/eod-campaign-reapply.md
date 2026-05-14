---
title: EOD Campaign Reapply Service
status: v2 daemon LIVE IN APPLY-MODE. Validated end-to-end against SPUI campaign 101 — real mutation + EB-API correctness proof. 249 tests passing.
created: 2026-04-29
updated: 2026-05-14 (apply-mode cutover + first real apply-run on SPUI 101; verify-loop fetch-retry bug found & fixed)
tags: [plan, emailbison, campaign, reapply, timezone, kill-triggers, scope, event-driven]
related-plans:
  - INBOX-INTEGRITY-PROGRAM.md (master tracker)
  - event-driven-architecture.md (Tier 1+2 LIVE — affects how live tag is applied)
---

# EOD Campaign Reapply Service

A small, independent app that reapplies the `live` inbox tag set to every active EmailBison campaign once per local-day, after that campaign's send window closes. Its only job is to keep each active campaign's attached senders in sync with the current `live` set, so kill-triggered inboxes drop off the next sending day automatically.

## Status (as of 2026-05-14)

| Layer | State |
|---|---|
| **v1 — operator-invoked CLI** | ✅ SHIPPED at [`apps/eod-reapply/`](../../apps/eod-reapply/). |
| **L5 — real-EB staging gate** | ✅ ATTACH path validated 2026-05-13 against Charm Test-Campaign 271. Two latent bugs found + fixed (filter-shape silent-ignore, async-delete false-negative). See [`apps/eod-reapply/docs/staging-results.md`](../../apps/eod-reapply/docs/staging-results.md). |
| **v2 PR 1 — daemon scaffold** | ✅ SHIPPED + DEPLOYED 2026-05-13. Migration 111 adds `campaign_reapply_jobs` + `workspaces.eod_reapply_enabled` flag (default FALSE). `eod-reapply daemon`: enqueuer (walks enabled workspaces × active campaigns, fetches schedules from EB, computes per-tz `trigger_at`, inserts pending jobs) + worker (claims due jobs via SELECT FOR UPDATE SKIP LOCKED, emits `campaign_reapply_due` event_log row, runs orchestrator, finalizes). Deployed as Coolify `eod-reapply-daemon` (Dockerfile.daemon). |
| **v2 PR 2 — apply-mode + crash recovery** | ✅ SHIPPED 2026-05-14. Apply-mode toggled by the `EOD_APPLY_MODE` env var (Coolify ignores CMD-overrides for Dockerfile builds, so apply-mode is env-var-driven, not a flag baked into the image). Startup `recover_orphaned_jobs` scan: any job stuck in `flagged` from a prior crash has its campaign checked and resumed if left paused mid-reapply; also sweeps stuck `processing` event_log rows. **Slack alerting deliberately skipped** — `event_log` rows + loud daemon logs are the observability layer. |
| **APPLY-MODE CUTOVER** | ✅ LIVE 2026-05-14. `EOD_APPLY_MODE=true` set on the Coolify daemon; startup log confirms `MODE: APPLY`. Per-workspace scope: `workspaces.eod_reapply_enabled` — currently **Charm + SPUI** enabled. |
| **First real apply-run** | ✅ VALIDATED 2026-05-14 on SPUI campaign 101. Daemon executed pause → DELETE 8 stale senders → verify → resume against production EB. Campaign went 95 → 87 attached, all 8 kill-flagged senders detached, campaign resumed to `active`. **EB-API correctness proof**: post-run query confirms `attached == live` exactly (all 87 attached senders carry the `live` tag id 342; zero non-live senders attached; zero live senders missing). The run also surfaced a real verify-loop bug — see below. |
| **v2 PR 3 — validation audit** | ⏳ OPTIONAL / DEFERRED. Daily check that killed inboxes don't show sends from a campaign after `T_eod`. Not blocking — `event_log` outcomes already give per-run visibility. |

### Verify-loop fetch-retry bug (found & fixed 2026-05-14, commit `89e58a0`)

The first real apply-run on SPUI 101 mutated correctly but the daemon reported `outcome=failed` — a **false failure**. Root cause: EB's async DELETE leaves pagination metadata transiently inconsistent — the post-remove verify fetch of `/campaigns/{id}/sender-emails` returned the correct 87 rows but `meta.total` still said 95, tripping `eb_client`'s pagination-consistency guard (which raises rather than return possibly-truncated data — the guard that catches silent truncation, Sammy #63). The verify loop's settle-wait retry only covered **set mismatch**; a fetch **exception** bailed immediately. Same async-delete root cause as the settle-wait already shipped, second manifestation path.

**Fix**: the verify loop now treats a `get_campaign_senders` exception the same as a set mismatch — settle and retry; only a fetch failing on the *final* attempt is a real failure. The truncation guard in `eb_client` is left strict (retry around it, don't loosen). The `verify_fetch` bail now also sets `FAILED_POST_RESUME` (was wrongly leaving the `FAILED_PRE_PAUSE` default — the campaign was already mutated + resumed by that point).

**Lesson**: this bug lived specifically in the post-mutation verify path — code that only executes when an actual mutation happens. Dry-run and unit tests structurally could not catch it; the real apply-run did. Validates doing a controlled real apply-run rather than trusting dry-run + tests alone.

## Purpose

Today, when an inbox dies:

- The kill cascade sets `inbox_state='dead'` in our DB and removes the `live` tag in EmailBison.
- **Post event-driven cutover (2026-05-05):** the live tag removal happens via [`sync_modules/event_handlers/kill_chain.py`](../../sync_modules/event_handlers/kill_chain.py) — `kill_queued_handler` enqueues a `tag_op_remove` event for the `live` tag. The Tier 2 `TagOpWorker` ([`sync_modules/tag_op_worker.py`](../../sync_modules/tag_op_worker.py)) drains the queue every 30 min and calls EB's bulk untag endpoint. `set_tag_sync` co-executes as the reconciler safety net (per Gate 5 of event-driven plan).
- (Pre-cutover this happened in `kill_processor.py` only; the path is now event-driven with set_tag_sync as backup.)
- The dead inbox is **not** automatically detached from the EB campaigns it was already attached to. It stops sending **campaigns** because the team manually re-runs "filter by `live` tag → attach to campaign" — or doesn't, and the dead inbox sits there sending in-flight or queued emails.
- Critically, the dead inbox **also keeps doing warmup sends** if `warmup_enabled=true` in EB — that's a separate mechanism EOD reapply does NOT address (see "Sister mechanism: warmup-disable on kill" below).

This service is the orchestrator that closes the campaign-attachment half of that loop. The warmup half is closed by the warmup-disable-on-kill mechanism designed elsewhere in this doc.

## Non-goals

- Not a campaign creator. Campaign creation stays in [api/routes/strategy.py](../../api/routes/strategy.py).
- Not a tag manager. The `live`/`reserve`/`incubating` lifecycle is owned by `lifecycle_tag_sync` (incubation) + the event-driven kill chain (`kill_queued_handler` enqueueing `tag_op_*` events drained by Tier 2 `TagOpWorker`) + `set_tag_sync` (reconciler).
- Not a kill-trigger evaluator. `health_checks` + the event-driven `bounce_observed_handler` keep that responsibility.
- Not a warmup manager. Warmup-disable-on-kill is a sibling event-driven mechanism (see "Sister mechanism" below); EOD reapply only touches campaign sender attachments.
- Not a replacement for `emailbison_sync_worker`. This service consumes data the sync worker writes (workspaces, campaigns, API keys).

## Relationship to event-driven architecture

The event-driven cutover (2026-05-05) didn't change the EOD design but did change two things adjacent to it:

1. **The `live` tag in EB is now updated faster.** Pre-cutover, `set_tag_sync` was the only writer of the live tag (every ~30s polling). Post-cutover, the event-driven Tier 2 `TagOpWorker` writes it ~real-time (within 30 min of any kill / pool change), with `set_tag_sync` continuing as reconciler. When EOD reads "senders with the `live` tag", it gets a more current snapshot than before.
2. **Tag drift is operationally close to zero.** `audit_tags_fleet.py` (post-2026-05-06 split) reports drift in two buckets: actionable (Connected inboxes) and informational (disconnected inboxes; preserved for resume-on-reconnect per ADR D-N). Actionable drift has been 0 since the cutover. EOD can trust the live-tag set in EB without an additional reconciliation pass.

**Net:** EOD's design is unchanged. It still uses the EB live tag as authority and reconciles campaign attachments to it. The cutover just made that source-of-truth more accurate.

## Sister mechanism: warmup-disable on kill (event-driven, designed 2026-05-08)

Audit on 2026-05-08 found **318 dead inboxes still receiving bounces, some on inboxes killed 3+ months ago**. Root cause: kill cascade marks DB state and applies `flagged_*` tag, but does NOT disable warmup. EB's warmup daemon keeps sending warmup mail from dead inboxes, tarnishing the reputation of their domain neighbors.

EOD reapply addresses **only the campaign-attachment half** of the bleed:
- ✅ Dead inbox detached from active campaigns → no more campaign sends
- ❌ Dead inbox still warming → still sending warmup mail

The warmup half is closed by an **event-driven warmup-disable mechanism** designed alongside this plan:

```
KILL CASCADE (today):
  bounce_observed → kill_queued → kill_queued_handler:
    1. UPDATE sender_accounts: inbox_state=dead, kill_trigger=…, killed_at=NOW(),
                               inventory_pool_status=NULL,
                               inventory_lifecycle_status=dead
    2. enqueue tag_op_attach (flagged_*)
    3. enqueue tag_op_remove (live)

KILL CASCADE (proposed addition):
    1. (same UPDATE, plus) warmup_enabled=FALSE
    4. enqueue warmup_disable event   ← NEW
                                       ↓
WARMUP_DISABLE EVENT (Tier 2 drain, per-workspace):
    Handler calls EB API to disable warmup on the inbox
    Marks event completed; idempotent (re-running on already-disabled is OK)
```

**Why event-driven (not procedural):**
- Same partitioning rules: workspace-scoped EB key (per ADR-006). The event_log CHECK constraint already enforces `workspace_id NOT NULL` for `tag_op_*` events; same will apply to `warmup_disable`.
- Same Tier 2 batching infrastructure: drain pending warmup_disable events per workspace, call EB in bulk if endpoint supports it (or per-inbox if not).
- Same retry/watchdog semantics: failed → retry with exponential backoff; orphan threshold; status tracking.
- Idempotent by design: setting warmup_enabled=FALSE on already-disabled is safe.

**Sequencing:** the kill_queued_handler runs in a single transaction, so the DB updates (inbox_state=dead AND warmup_enabled=FALSE) commit atomically. Tier 2 then drains the queued events on its 30-min cycle. Order between tag_op_remove (live) and warmup_disable doesn't matter because EB's flagged_* tag and warmup state are independent.

**Engineering scope (sketch — needs operator OK before building):**
1. Add `warmup_enabled = FALSE` to the UPDATE in `kill_queued_handler` (one line)
2. Add `enqueue_warmup_disable(...)` helper alongside `enqueue_tag_op(...)` in `_common.py`
3. Add `warmup_disable` to the event_type enum in `event_log` (or extend the CHECK constraint)
4. Either: extend `TagOpWorker` to handle `warmup_disable` events (simpler, reuses bulk batching), or create sibling `WarmupOpWorker` (cleaner separation, more code)
5. Add EB API method to `EmailBisonClient`: `disable_warmup(account_id)` or `set_warmup(account_id, enabled=false)` — needs OpenAPI lookup
6. Tests: handler logic, idempotency, partitioning enforcement
7. Backfill script (one-shot): for the existing 318 dead-with-bouncing inboxes, run warmup_disable retroactively

This is sized at ~1 day engineering + ~1 day backfill + tests.

## Why a separate app, not a module in charm-email-os

| Reason | Detail |
|---|---|
| Single-purpose blast radius | If this service crashes or has a bug, the rest of the sync engine, API, frontend, and workers keep running. |
| Different cadence | `emailbison_sync_worker` is a fast-tick poll loop (30s priority, 5min events). This service is a slow-tick scheduler — it polls every ~5 min and acts maybe once per campaign per day. Co-tenanting in the same process buries the slow-tick logic. |
| Independently roll-out-able | Phased deploy by workspace allowlist (see [Rollout](#rollout-plan)) is much cleaner with its own deploy unit. |
| Clear contract with the rest of the system | Reads `workspaces` + `workspace_api_keys` + `emailbison_campaigns`, writes its own `campaign_schedules` + `campaign_reapply_runs`. No shared mutable state with the sync worker. |
| Shared DB is fine | Same Postgres instance; no need for a network API between the two. The boundary is at the table level. |

**Recommendation:** new app, **shared DB**. Subdir of the charm-email-os monorepo at first (`apps/eod-reapply/`) for shared CI + migration tooling, with a module boundary that makes a future repo split a no-op.

## Architecture

### v2 design — fully event-driven (2026-05-12 revision per operator direction)

The original v2 design (preserved below for history) used a 5-minute polling
loop. **Per operator direction 2026-05-12, v2 is being redesigned to lean
into event-driven architecture** consistent with the rest of the inbox
state machine (event_log + LISTEN/NOTIFY + Tier 1+2 cutover already live
since 2026-05-05). No polling.

```
                  ┌────────────────────────────────────────────────┐
                  │ EOD Campaign Reapply Service v2                │
                  │ (apps/eod-reapply/ daemon mode)                │
                  └────────────────────────────────────────────────┘

CAMPAIGN CREATED OR SCHEDULE UPDATED IN EB
        │  sync_campaigns / EB webhook / manual operator action
        ▼
┌─────────────────────────────────────┐
│ DB trigger on emailbison_campaigns  │
│ INSERT or UPDATE of schedule fields │
│                                     │
│ compute next_eod_at =               │
│   today_local_end_time              │
│   + reapply_buffer_min              │
│   in campaign.timezone              │
│                                     │
│ INSERT INTO campaign_reapply_jobs   │
│   (workspace_id, campaign_id,       │
│    scheduled_for, status='pending') │
│ ON CONFLICT (campaign_id,           │
│   run_local_date) DO NOTHING        │
└─────────────────────────────────────┘
        │  pg_notify 'reapply_job_added'
        ▼
┌─────────────────────────────────────┐
│ EOD scheduler component             │
│ (lives inside apps/eod-reapply/     │
│  daemon, NOT inside emailbison-sync)│
│                                     │
│ LOOP:                               │
│   1. SELECT MIN(scheduled_for)      │
│      FROM campaign_reapply_jobs     │
│      WHERE status='pending'         │
│   2. pg_sleep_until(MIN) OR wake on │
│      NOTIFY 'reapply_job_added'     │
│   3. When MIN time arrives:         │
│      claim due rows with            │
│        FOR UPDATE SKIP LOCKED       │
│      UPDATE status='flagged'        │
│      emit one campaign_reapply_due  │
│      event per claimed row          │
└─────────────────────────────────────┘
        │  pg_notify per event (existing event_log + LISTEN/NOTIFY infra)
        ▼
┌─────────────────────────────────────┐
│ Listener in apps/eod-reapply/       │
│ (subscribes to 'campaign_reapply_   │
│  due' channel)                      │
│                                     │
│ For each notification:              │
│   asyncio.create_task(handle(evt))  │
│   Fresh pool conn per handler       │
│   (Phase 3 architecture)            │
└─────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────┐
│ campaign_reapply_due_handler        │
│ (per-workspace asyncio.Lock to      │
│  serialize same-workspace campaigns)│
│                                     │
│ 1. acquire workspace_lock           │
│ 2. open EB session (scoped key)     │
│ 3. PATCH /campaigns/{id}/pause      │
│ 4. GET current sender attachments   │
│ 5. GET senders with 'live' tag      │
│ 6. compute attach_set, remove_set   │
│ 7. POST attach-sender-emails        │
│ 8. DELETE remove-sender-emails      │
│ 9. verify set == target             │
│ 10. PATCH resume (in finally block) │
│ 11. mark event_log 'completed'      │
│ 12. mark job row 'completed'        │
└─────────────────────────────────────┘
        │
        ▼
   workspace_locks per workspace_id keep
   same-workspace campaigns sequential.
   Different-workspace campaigns run in
   parallel under SYNC_WORKSPACE_CONCURRENCY=3
   semaphore (same proven pattern as Tier 2
   TagOpWorker).
```

**What's truly event-driven vs the one unavoidable thing**

| Layer | Event-driven? | Notes |
|---|---|---|
| Job creation (campaign scheduled → job INSERTed) | ✅ DB trigger | fires only on state change |
| Notification of new job → sleeper wakes immediately | ✅ pg_notify | no polling |
| Time arrival → event emission | ⚠️ scheduler sleeps `pg_sleep_until(MIN)` | fundamental — wall-clock time has to come from somewhere |
| Event consumption | ✅ existing event_log + LISTEN/NOTIFY | Phase 1-5 infra |
| Handler dispatch | ✅ asyncio task per notification, fresh pool conn | Phase 3 architecture |
| Per-workspace EB API call | ✅ workspace-scoped per ADR-006 | proven in Tier 2 |

The scheduler does NOT poll every N minutes. It sleeps exactly until next due time. If a new job lands sooner, `NOTIFY 'reapply_job_added'` wakes it immediately. So wake-ups = `(number of distinct EOD times across all active campaigns)`, typically a handful per day — not 288 wake-ups/day like a 5-min poll.

### Concurrency model — multiple workspaces with simultaneous EOD events

When N campaigns are due at the same wall-clock instant (e.g., 6 PM Pacific:
3 Spout campaigns ending in Sydney time, 2 Selery, 1 Charm), this is the
data flow:

**Step 1: Scheduler wake-up (handles same-second collisions atomically)**

```sql
-- Single transaction:
UPDATE campaign_reapply_jobs
SET status = 'flagged'
WHERE id IN (
  SELECT id FROM campaign_reapply_jobs
  WHERE scheduled_for <= NOW() AND status = 'pending'
  ORDER BY scheduled_for
  FOR UPDATE SKIP LOCKED
)
RETURNING id, workspace_id, campaign_id;

-- For each returned row, INSERT a campaign_reapply_due event into event_log.
-- One pg_notify per event (the existing trigger on event_log handles this).
```

Six events fire in one DB transaction. Six pg_notify calls. All six listener
tasks spawn immediately on the consuming side.

**Step 2: Per-workspace serialization**

Inside `campaign_reapply_due_handler`:

```python
async with _workspace_locks[workspace_id]:
    async with EmailBisonClient(api_key=ws_key, is_workspace_scoped=True) as client:
        await reapply_campaign(client, db_conn, campaign_id, ...)
```

The 3 Spout handlers acquire the SAME lock and serialize. The Selery + Charm
handlers acquire DIFFERENT locks and run in parallel with Spout. This is
required because EB rate-limits per workspace key — three concurrent reapplies
on the same key would interfere.

**Step 3: Cross-workspace parallelism**

Wrap the entire handler dispatch in `asyncio.Semaphore(EOD_REAPPLY_WORKSPACE_CONCURRENCY)`
(default 3). At any moment, at most 3 distinct workspaces are processing.
Same pattern as `TagOpWorker._drain_workspace` already running in production.

**Step 4: Failure isolation**

Per-event try/except in the handler. The `pause → mutate → resume` cycle
has a `finally` block (already in v1's `reapply_campaign`) that guarantees
the campaign is resumed even if the body raises. A failure on Spout/c-201
doesn't touch Spout/c-202 (different event, different task), Selery
campaigns (different workspace), or anything else.

**Visual: 6 campaigns due at 18:00:00 UTC**

```
Time →
Spout/c-201    [pause→mutate→resume                          ]
Spout/c-202                                  [pause→mutate→resume]   ← waits for c-201
Spout/c-203                                                       [pause→mutate→resume]
Selery/c-101   [pause→mutate→resume]                                                   ← parallel
Selery/c-102                       [pause→mutate→resume]
Charm/c-301    [pause→mutate→resume]                                                   ← parallel
```

Total elapsed time = `max(time(Spout), time(Selery), time(Charm))` ≈ 90s
for the slowest workspace, not `sum(times)` ≈ 240s.

**Step 5: What the operator sees in event_log**

```
event_log
─────────
id   event_type              status      workspace_id  emitted_at  completed_at
─────────────────────────────────────────────────────────────────────────────
A    campaign_reapply_due    completed   spout         18:00:00    18:00:32
B    campaign_reapply_due    completed   spout         18:00:00    18:01:02
C    campaign_reapply_due    completed   spout         18:00:00    18:01:32
D    campaign_reapply_due    completed   selery        18:00:00    18:00:29
E    campaign_reapply_due    completed   selery        18:00:00    18:00:58
F    campaign_reapply_due    completed   charm         18:00:00    18:00:25
```

Per-campaign visibility, failure isolation traceable per row, audit log
permanent. Anything `failed` carries its `error_message`. The watchdog
re-emits failed events with exponential backoff.

### Schema discipline — what we add and what we deliberately don't

**Goal:** lean into event_log where possible. Add new tables only where the
data shape doesn't fit event_log.

**What we MUST add (justified):**

| New artifact | Why it can't be event_log |
|---|---|
| `campaign_reapply_jobs` table | event_log records what HAPPENED (emitted_at = past tense). Jobs record what SHOULD happen (scheduled_for = future). Different semantics; conflating them muddles the model. |
| ONE DB trigger on `emailbison_campaigns` | Fires job creation atomically with campaign change. No daemon polling EB. |
| ONE partial index for scheduler MIN scan | `(scheduled_for) WHERE status='pending'` — single-column, partial. Cheap. |
| Broaden `event_log_workspace_scoped_requires_workspace` CHECK | Extend to cover `campaign_reapply_due` (same way 109 did for `warmup_disable`). 1-line ALTER. |
| ONE new event_type `campaign_reapply_due` | Reuses existing event_log table — no schema change. |
| ONE new handler in `event_handlers/` | Reuses existing HANDLER_REGISTRY pattern. |

**What we deliberately DON'T add:**

| Considered but skipped | Why |
|---|---|
| `campaign_schedules` cache table (v1 design) | EB's `/campaigns/{id}/schedule` is the source of truth. Caching it adds a sync layer that drifts. The DB trigger on `emailbison_campaigns` recomputes `next_eod_at` from the campaign row directly. |
| `campaign_reapply_runs` history table (v1 design) | Redundant with event_log. Every reapply attempt already produces a `campaign_reapply_due` row in event_log with status + emitted_at + handler_completed_at + error_message. That IS the run history. |
| New columns on `emailbison_campaigns` (e.g., `next_reapply_at`) | Would need backfill on every schedule change. The `campaign_reapply_jobs` table holds this without cross-table writes. |
| pg_cron / pgAgent extension | Not installed on production Postgres (verified 2026-05-12). Would require ops change to install. Pure asyncpg LISTEN + pg_sleep_until is sufficient. |
| Separate `EmailBisonClient` pool for the EOD daemon | Reuses the existing client class with workspace-scoped key per ADR-006. |
| New Slack alerter or audit logger | Reuses existing SlackAlerter + AuditLogger. |

**Net schema delta:**
- 1 new table (`campaign_reapply_jobs`)
- 1 new partial index
- 1 ALTER on event_log CHECK constraint
- 1 new DB trigger
- 0 new columns on existing widely-used tables
- 0 new event_log row shape changes (just a new event_type value)

**Compare to original v1 plan**: was 2 new tables + new columns + new audit
log + new alerter. v2-event-driven cuts ~60% of the schema surface.

### Historical: v1 polling design (preserved for context)

```
┌────────────────────────────────────────────────────────────────┐
│ EOD Campaign Reapply Service                                    │
│                                                                 │
│  poll_loop (every 5 min)                                        │
│      │                                                          │
│      ├─ schedule_sync ─── GET /api/campaigns/{id}/schedule ─── │
│      │     persist into campaign_schedules                      │
│      │                                                          │
│      └─ window_evaluator                                        │
│              │  for each (workspace, active campaign):          │
│              │    - now_local = datetime.now(campaign.tz)       │
│              │    - if today is a sending day                   │
│              │      AND now_local > end_time + buffer           │
│              │      AND no campaign_reapply_runs row for        │
│              │          (campaign, run_local_date=today_local)  │
│              │    → enqueue reapply job                         │
│              │                                                  │
│              └─ reapply_orchestrator (per campaign)             │
│                    1. PATCH /campaigns/{id}/pause               │
│                    2. GET  /campaigns/{id}/sender-emails  ──┐   │
│                    3. GET  /sender-emails?tag_ids[0]={id} ──┤   │
│                    4. diff: target − current = attach_set    │   │
│                            current − target = remove_set    │   │
│                    5. POST /campaigns/{id}/attach-sender-…   │   │
│                    6. DEL  /campaigns/{id}/remove-sender-…   │   │
│                    7. GET  /campaigns/{id}/sender-emails    │   │
│                       verify set == target                    │   │
│                    8. PATCH /campaigns/{id}/resume          │   │
│                    9. write campaign_reapply_runs row       ──┘   │
│                                                                 │
│  All EB calls use workspace-scoped API key from                 │
│  workspace_api_keys table (Sanctum tokens).                     │
└────────────────────────────────────────────────────────────────┘
```

This design was sound but introduced a polling cadence inconsistent with
the rest of the system. v2 keeps the orchestration steps (pause→mutate→
resume) and the workspace-scoped key rule; replaces the polling layer
with event-driven scheduling.

## Schema additions (v2 — event-driven, 2026-05-12 revision)

**One new table** + the standard event-driven primitives (CHECK
constraint broaden + new event_type, both reusing migration 109's
pattern). Net schema delta is ~60% smaller than the v1 design.

### What we add (justified)

```sql
-- ─────────────────────────────────────────────────────────────────
-- Migration 111 (or next sequence): campaign_reapply_jobs
-- ─────────────────────────────────────────────────────────────────

-- Job queue: future work. Distinct from event_log (past tense audit).
CREATE TABLE campaign_reapply_jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id        UUID NOT NULL REFERENCES workspaces(id),
    campaign_id         UUID NOT NULL REFERENCES emailbison_campaigns(id) ON DELETE CASCADE,
    -- When the scheduler should wake up to fire the campaign_reapply_due event
    scheduled_for       TIMESTAMPTZ NOT NULL,
    run_local_date      DATE NOT NULL,        -- idempotency key (campaign tz)
    run_local_tz        TEXT NOT NULL,        -- preserved for audit/debug
    status              TEXT NOT NULL DEFAULT 'pending',
                        -- 'pending' / 'flagged' (claimed by scheduler) /
                        -- 'completed' / 'failed' / 'skipped'
    triggered_event_id  UUID,                 -- event_log row emitted on claim
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    error_message       TEXT,
    CONSTRAINT campaign_reapply_jobs_unique_local_day
        UNIQUE (campaign_id, run_local_date)
);

-- Partial index for the scheduler's MIN(scheduled_for) scan
CREATE INDEX idx_campaign_reapply_jobs_pending
    ON campaign_reapply_jobs (scheduled_for)
    WHERE status = 'pending';

-- ─────────────────────────────────────────────────────────────────
-- Broaden event_log CHECK constraint to cover the new event_type
-- (same pattern as migration 109 did for warmup_disable)
-- ─────────────────────────────────────────────────────────────────

ALTER TABLE event_log DROP CONSTRAINT IF EXISTS event_log_workspace_scoped_requires_workspace;
ALTER TABLE event_log ADD CONSTRAINT event_log_workspace_scoped_requires_workspace
    CHECK (
        (event_type NOT LIKE 'tag_op_%'
         AND event_type <> 'warmup_disable'
         AND event_type <> 'campaign_reapply_due')
        OR workspace_id IS NOT NULL
    );

-- ─────────────────────────────────────────────────────────────────
-- DB trigger on emailbison_campaigns: when a campaign's schedule
-- changes or is created, compute next_eod_at + INSERT/UPDATE the
-- job row. Trigger function uses ON CONFLICT (campaign_id,
-- run_local_date) DO NOTHING so re-running today's schedule sync
-- doesn't double-enqueue. pg_notify wakes the scheduler immediately.
-- ─────────────────────────────────────────────────────────────────

-- Function omitted here for brevity; full SQL in the migration file.
```

### Why no other tables

| v1 plan had | v2 doesn't need | Rationale |
|---|---|---|
| `campaign_schedules` cache table | dropped | EB's `/campaigns/{id}/schedule` is the source of truth. The DB trigger reads from `emailbison_campaigns` directly (which `sync_campaigns` already keeps fresh). No cache means no cache-drift bug. |
| `campaign_reapply_runs` history table | dropped | Every reapply already produces a `campaign_reapply_due` row in event_log with status + timestamps + error_message. That IS the audit log. Adding a parallel runs table creates two sources of truth. |
| Big status enum (`started/paused/diffed/attaching/...`) | simplified to 4 | `pending` / `flagged` / `completed` / `failed`. The fine-grained sub-statuses (paused/attaching/etc.) were operational-time-only state — they don't survive a process crash anyway. Use logs + event_log error_message for diagnosis. |

### Sub-status simplification

The v1 design had 13 statuses to track per-step progress (started, paused, diffed, attaching, ...). These were useful for crash-recovery diagnostics but mostly redundant — the handler is a single transaction with a `finally` block that guarantees campaign resume. If the daemon dies mid-handler, the event_log row stays in `processing` and the watchdog re-emits. The DB doesn't need to know which step we were on; the next attempt starts fresh from step 1 (pause is idempotent — pausing a paused campaign is a 200 no-op in EB).

Status enum (text, validated in app layer):

| Status | Meaning |
|---|---|
| `started` | Row inserted, pause not yet attempted |
| `paused` | Campaign paused, diff in progress |
| `diffed` | Target/prior/attach/remove sets computed |
| `attaching` | Attach call in flight |
| `removing` | Remove call in flight |
| `verifying` | Verification in flight |
| `resuming` | Resume call in flight |
| `succeeded` | Verify passed, resume succeeded |
| `skipped_empty_live` | Refused: live set is empty (alert raised) |
| `skipped_no_diff` | No-op: target == prior, nothing to do |
| `skipped_not_active` | Campaign no longer active by the time we got to it |
| `failed_left_paused` | Resume failed; **operator action required** |
| `failed_pre_pause` | Failed before pause; campaign untouched |
| `failed_post_resume_verify` | Resume succeeded but verify mismatched |

## EB API surface used

All workspace-scoped via `workspace_api_keys`. From [openapi spec](https://spellcast.hirecharm.com/api/reference.openapi):

| # | Method | Path | Purpose |
|---|---|---|---|
| 1 | `GET` | `/api/campaigns?status=active` | Discover active campaigns per workspace |
| 2 | `GET` | `/api/campaigns/{id}/schedule` | Pull schedule (read-only — never write) |
| 3 | `PATCH` | `/api/campaigns/{id}/pause` | Pause before mutation |
| 4 | `GET` | `/api/campaigns/{id}/sender-emails` | Current attachment set |
| 5 | `GET` | `/api/sender-emails?tag_ids[0]={live_tag_id}` | Target set (paginated). **NOT** `filters[tag_ids][]=...` — that shape is silently ignored by EB and returns the whole workspace (2026-05-13 incident: over-attached 157 senders to Test-Campaign 271). Client verifies every returned sender carries the requested tag in `tags[]` as a defense. |
| 6 | `POST` | `/api/campaigns/{id}/attach-sender-emails` | Attach `attach_set` |
| 7 | `DELETE` | `/api/campaigns/{id}/remove-sender-emails` | Detach `remove_set` |
| 8 | `PATCH` | `/api/campaigns/{id}/resume` | Resume |

The `live` tag ID is per-workspace. Resolve once per workspace per cycle via `GET /api/tags`, cache in memory for the run.

## Timezone handling — the safety-critical part

This is the load-bearing concern. The Sammy/Australia case is the canonical example.

### Rules

1. **Source of truth = `campaign_schedules.timezone`**, an IANA name (e.g. `Australia/Sydney`). Pulled from EB every poll cycle (5 min).
2. **All reapply-window math uses `zoneinfo.ZoneInfo(tz)`** (Python stdlib, no deps). UTC is *only* for storage and audit timestamps.
3. **"After EOD" predicate**, computed per-campaign:
   ```python
   now_utc = datetime.now(timezone.utc)
   tz = ZoneInfo(schedule.timezone)
   now_local = now_utc.astimezone(tz)
   today_local_date = now_local.date()
   today_local_weekday = now_local.weekday()  # 0=Mon..6=Sun
   end_local_today = datetime.combine(today_local_date, schedule.end_time, tzinfo=tz)
   trigger_at = end_local_today + timedelta(minutes=schedule.reapply_buffer_min)

   is_sending_day_today = schedule.send_days[today_local_weekday]
   already_ran = exists campaign_reapply_runs WHERE campaign_id=$1 AND run_local_date=today_local_date

   should_run = (
       is_sending_day_today
       AND now_local >= trigger_at
       AND not already_ran
       AND campaign.status in active-set
   )
   ```
4. **DST is handled by `ZoneInfo` automatically**. Do not roll your own offset math.
5. **Idempotency key is `(campaign_id, run_local_date)`** in the campaign's tz, not UTC. A single UTC day can span two local dates; using UTC date would either double-fire or skip days near the IDL.
6. **No assumption about workspace tz.** A single workspace can host campaigns in multiple zones. We never read a workspace-level tz; only per-campaign.

### What this means for Sammy

| Scenario | UTC | Sydney local | Action |
|---|---|---|---|
| Sammy campaign ends 17:00 Sydney, buffer 60min | 06:00 UTC (DST off) | 17:00 + 60m = 18:00 | Reapply fires at 06:00–06:05 UTC the same day |
| Today is Saturday Sydney, schedule has saturday=false | — | — | Skip; no row written |
| Daylight savings shift in Sydney | offset changes ±1hr | unchanged | `zoneinfo` handles it; no code change needed |

### Tests we must have green before any prod run

- `Australia/Sydney` end_time 17:00, fire at 18:00 local → asserts UTC trigger time across DST start/end.
- `America/New_York` end_time 17:00 → trigger 22:00 UTC EST, 21:00 UTC EDT.
- `Europe/London` → BST/GMT toggle.
- IANA-disagreement: campaign tz is `America/Los_Angeles`, server is UTC, run frozen-clock at 00:30 UTC → asserts run_local_date is *yesterday* (PST-side of midnight), not today.
- Saturday-skip: tz that has Sat=false; predicate returns `False`.
- Already-ran: row exists for today_local_date → predicate returns `False`.

## Idempotency & concurrency

- **Per campaign per local day**: enforced by `UNIQUE(campaign_id, run_local_date, is_dry_run)`. A second poll tick that re-evaluates the predicate as `True` will fail the insert and the orchestrator will short-circuit.
- **Distributed lock**: take a Postgres advisory lock on `hashtext('reapply:' || campaign_id::text)` for the duration of the orchestrator. If two service instances are running, only one acts.
- **Across workspaces**: bounded asyncio semaphore (default 3, matches existing sync worker concurrency in [docs/architecture/emailbison-sync.md:60-71](../architecture/emailbison-sync.md#L60-L71)).
- **Within workspace**: sequential per campaign by default. EB rate-limit posture per workspace is unknown; sequential is the safe default. Configurable.

## Failure modes & mitigations

| Failure | Mitigation |
|---|---|
| Pause succeeds, then process crashes | On startup, scan `campaign_reapply_runs` where `status NOT IN (succeeded, skipped_*, failed_pre_pause)` and `started_at < NOW() - 10min` → attempt resume + alert. |
| Empty live set (mass kill, tag bug) | Refuse to proceed if `len(target_set) == 0`. Status `skipped_empty_live`, Slack alert. |
| Diff = no change | Status `skipped_no_diff`, no pause/resume cycle (saves API calls and avoids a needless `Queued` flap). |
| Attach 200 but verify shows missing IDs | Status `failed_post_resume_verify`. Resume the campaign anyway (don't leave paused). Slack alert with diff details. |
| Resume fails | Status `failed_left_paused`. Slack page-level alert. **Operator must resume manually.** Auto-retry next poll tick — bounded to 3 attempts before giving up and demanding human action. |
| Campaign archived/deleted between discovery and orchestration | Pause returns 4xx; status `skipped_not_active`, no-op. |
| EB returns 429 | Backoff per the existing `EmailBisonClient` retry policy; don't fail the run. |
| `live` tag ID resolves to None for a workspace | Status `skipped_empty_live` with reason `tag_unresolved`. Alert. |
| Campaign tz is invalid IANA name | Refuse to load schedule; log + alert. Don't crash the loop. |

## Observability

- **Audit table**: every run writes a `campaign_reapply_runs` row with full set diffs.
- **Structured logs**: JSON, one line per state transition. Include `campaign_id`, `workspace_name`, `run_local_date`, `tz`, `status`, set sizes.
- **Slack alerts** (reuse `slack_alerter` module pattern from sync_modules):
  - Page-level: `failed_left_paused`, `failed_post_resume_verify`
  - Warning: `skipped_empty_live`, repeated `failed_*` for same campaign
  - Info (daily digest, optional): summary of N reapplies, M attached, K removed
- **Metrics** (Prometheus-style counters and gauges, to wire into the existing dashboard later):
  - `eod_reapply_runs_total{workspace,status}`
  - `eod_reapply_attached_total{workspace}`
  - `eod_reapply_removed_total{workspace}`
  - `eod_reapply_window_lag_seconds{workspace}` — how far past `trigger_at` did we actually run

## Configuration

Environment variables only. No on-disk config files. **No `POLL_INTERVAL_SECONDS` —
v2 is event-driven; scheduler sleeps until next due time via `pg_sleep_until` +
NOTIFY wake.**

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | (required) | Same Postgres as charm-email-os |
| `EMAILBISON_API_URL` | `https://spellcast.hirecharm.com/api` | EB base URL |
| `EOD_REAPPLY_WORKSPACE_CONCURRENCY` | `3` | Parallel workspaces (matches Tier 2 pattern) |
| `WORKSPACE_ALLOWLIST` | (unset = all) | Comma-sep workspace names; phased rollout gate |
| `WORKSPACE_DENYLIST` | (unset) | Inverse — explicit opt-outs |
| `DRY_RUN` | `false` | Compute and log but don't mutate EB |
| `DEFAULT_REAPPLY_BUFFER_MIN` | `60` | Fallback when emailbison_campaigns row has NULL buffer |
| `SLACK_WEBHOOK_URL` | (required) | Alerts |
| `MAX_RESUME_RETRIES` | `3` | Before giving up and paging |
| `SCHEDULER_MAX_SLEEP_SECONDS` | `3600` | Cap on pg_sleep_until to avoid sleeping past schedule drift; will wake at most once per hour even if no jobs are due (sanity floor) |

## Deployment (Coolify)

Deploys as a new Coolify service alongside the existing workers ([production/coolify/services.md](../../production/coolify/services.md)). Same posture as `emailbison-sync`:

| Field | Value |
|---|---|
| Service name | `eod-reapply` |
| Type | Background worker (no public URL) |
| Build | Dockerfile from `apps/eod-reapply/Dockerfile` |
| Health check | Internal HTTP `/healthz` on a loopback port (returns 200 if poll loop tick is < 2× `POLL_INTERVAL_SECONDS` old) |
| Restart policy | `unless-stopped` |
| Replicas | 1 (advisory lock allows >1 safely, but no need) |
| Same DB | Yes — reuses `DATABASE_URL` from the shared Postgres |
| Same EB base URL | Yes — reuses `EMAILBISON_API_URL` |

**Config in Coolify** (env vars from [Configuration](#configuration), set per-environment):
- Staging: `DRY_RUN=true`, `WORKSPACE_ALLOWLIST=<test-workspace>`
- Prod: `DRY_RUN=false`, allowlist driven by [Rollout](#rollout-plan) phase

**Migrations**: applied via the same flow as the rest of `migrations/` — this app's `apps/eod-reapply/migrations/001_*.sql` and `002_*.sql` should be picked up by the existing migration runner. Confirm before phase 0 deploy.

**Logs/alerts**: ship stdout to Coolify's log viewer; Slack webhook handles operator alerts independently.

**Add to `services.md`** when the service goes live (not before — keeps the doc reflecting actual reality).

## Project layout (v2 event-driven addition)

v1 (operator-invoked CLI) is already shipped — see `apps/eod-reapply/` tree
in the README. The v2 daemon adds these files on top:

```
apps/eod-reapply/
├── pyproject.toml                  (existing, unchanged)
├── Dockerfile                      (existing, unchanged)
├── README.md                       (existing)
├── src/eod_reapply/
│   ├── window.py                   (existing — pure tz predicate, reused)
│   ├── eb_client.py                (existing — reused)
│   ├── reapply.py                  (existing — reapply_campaign() reused as-is)
│   ├── check.py                    (existing — read-only diagnostic)
│   ├── db.py                       (existing)
│   ├── cli.py                      (existing — v1 CLI entrypoint preserved)
│   │
│   ├── daemon.py                   (NEW v2 — entrypoint: pool + scheduler + listener)
│   ├── scheduler.py                (NEW v2 — pg_sleep_until loop, claims due jobs)
│   ├── handler.py                  (NEW v2 — campaign_reapply_due_handler)
│   └── workspace_locks.py          (NEW v2 — asyncio.Lock per workspace_id)
│
└── tests/
    ├── test_window.py, test_eb_client.py, ...  (existing 209 tests)
    ├── test_daemon.py              (NEW v2 — sleeper wake-on-notify, claim race)
    ├── test_handler.py             (NEW v2 — handler dispatch + workspace lock)
    └── test_scheduler.py           (NEW v2 — atomic claim, multiple-due ordering)

charm-email-os repo (NOT under apps/eod-reapply/):
└── migrations/
    └── 111_campaign_reapply_jobs.sql  (NEW — job queue table + trigger + CHECK broaden)
└── sync_modules/event_handlers/
    └── campaign_reapply.py            (NEW — campaign_reapply_due_handler is in the
                                        shared event-driven module so the listener
                                        registers it via HANDLER_REGISTRY)
```

**Why the handler lives in `sync_modules/event_handlers/`, not in `apps/eod-reapply/`:**
The handler runs INSIDE the event listener (which is in `emailbison-sync` worker
or its successor). It dispatches the work — actual EB API calls happen via the
`reapply_campaign()` library function which IS in `apps/eod-reapply/`. Two-stage:
listener → dispatcher → reapply library. Same pattern as Tier 2 TagOpWorker.

**Alternative:** put the entire daemon (listener + scheduler + handler) in
`apps/eod-reapply/` as its own Coolify service. Cleaner blast radius. Decide
during implementation.

## Pre-requisites in charm-email-os (must land first)

These three changes block all rollout phases:

1. **Add `get_campaign_schedule(campaign_id)` to `EmailBisonClient`** in [sync_modules/emailbison_client.py](../../sync_modules/emailbison_client.py) — 3-line addition next to `get_campaign_details`. The new app uses its own subset client but having it here too keeps parity for any future read needs in the main API.
2. **Fix the hardcoded `America/New_York` in [api/routes/strategy.py:1572](../../api/routes/strategy.py#L1572)** — campaigns created via Strategy AI for non-US clients are getting the wrong tz baseline. Options: (a) require `client_timezone` parameter, (b) read it from a new `clients.timezone` column. Tracked separately; not strictly blocking the EOD app, but the EOD app will surface this bug as wrong-window reapplies for those campaigns. Flagging it now.
3. **Verify `workspace_api_keys.api_key` storage posture** — confirm whether the column is plaintext or encrypted at rest. The new app needs read access; the secret-handling pattern must match what the existing sync worker does.

## Rollout plan

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Pre-reqs** | Land the 3 items above. Deploy schedule sync only (no orchestrator). | One full week of `campaign_schedules` data persisted. Manually inspect 5+ campaigns across 3+ tzs (incl. Sammy/Australia) — verify schedule matches EB UI. |
| **1. Dry run, single campaign** | Orchestrator deployed with `DRY_RUN=true` and `WORKSPACE_ALLOWLIST=<one-test-workspace>`. Limit to one campaign by config. | One full week of dry-run logs. Diffs match what an operator would have done manually. Zero alerts. |
| **2. Live, one campaign** | `DRY_RUN=false`, same one allowlisted campaign. Pick smallest sender count, lowest-stakes campaign. | One week. Audit shows succeeded runs every sending day, no `failed_*` rows, sender list matches `live` tag set. |
| **3. One workspace, all campaigns** | Same workspace, expand to all active campaigns. | One week. Watch for cross-campaign timing collisions, EB rate-limit signs. |
| **4. Multi-workspace, allowlisted** | Add 2-3 more workspaces. Sammy explicitly included to validate non-US tz in production. | Two weeks. |
| **5. Default-on** | Allowlist removed; denylist for opt-outs. Remaining workspaces brought in. | Steady-state. |

**Hard gate between phases**: zero unresolved `failed_*` rows in audit, no Slack pages from this service, manual spot-check of 3 random reapply diffs.

## Testing strategy

### Unit (pure functions, frozen clock)
- `window.should_run(schedule, now_utc, last_run_local_date)` → exhaustive matrix across tz, DST, weekend, end_time, buffer.
- `live_set.diff(prior, target)` → empty, identical, partial overlap, single add/remove, single replace.
- Status transition validator (no skipping states).

### Integration (real Postgres, mocked EB)
- Full orchestrator happy path.
- Every failure mode in the table above, asserted by replaying canned EB responses.
- Idempotency: 100 concurrent invocations of the orchestrator on the same campaign — exactly one runs, rest are no-ops.
- Recovery: kill the process between pause and attach; restart; assert `recovery.py` resumes the campaign.

### Staging (real EB, throwaway test campaign)
- A dedicated test campaign per workspace with 3 senders. Run the full cycle nightly. Verify in EB UI.

### Production (phased per [Rollout](#rollout-plan))
- Each phase has its own go/no-go criteria. Don't advance until prior phase is green for the stated duration.

## Open questions for confirmation

1. **DB sharing**: confirm shared Postgres is acceptable, or do you want this on its own DB?
2. **Repo location**: `apps/eod-reapply/` subdir of charm-email-os, or net-new repo?
3. **`reapply_buffer_min` default**: 60 min reasonable, or do you want different default per campaign type?
4. **Resume retries on `failed_left_paused`**: 3 auto-retries then page, or page immediately and require manual?
5. **Schedule sync cadence**: every poll tick (5 min) is excessive for data that changes daily. Suggest hourly. Confirm.
6. **What counts as "active"** for the discovery step? EB statuses include `Active`, `Queued`, `Paused`, `Archived`, `Draft`. Reapply targets should be `Active` and `Queued` only — confirm.
7. **Rollout phase 1 & 2 candidate workspace**: which workspace, which campaign? Suggest a Charm-internal one before any client workspace touches this.

## Estimate

Excluding the pre-reqs, which are independent:

| Block | Effort |
|---|---|
| Schema + migrations | 0.5d |
| `eb_client` subset + `tag_resolver` | 0.5d |
| `schedule_sync` + persistence | 0.5d |
| `window.py` + exhaustive tz tests | 1d |
| `live_set` + `reapply` orchestrator | 1.5d |
| `audit` + `recovery` + `alerts` | 1d |
| `poll_loop` + `main` + config | 0.5d |
| Integration test harness + fixtures | 1d |
| Dockerfile + deploy wiring | 0.5d |
| **Subtotal: build** | **~7d** |
| Phase 0 + 1 dry-run watch + tweaks | 1-2 weeks calendar |
| Phase 2-5 rollout | 4-6 weeks calendar |

The build is small. The discipline is in not skipping rollout phases.
