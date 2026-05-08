---
title: EOD Campaign Reapply Service
status: v1 SHIPPED (operator-invoked CLI, 209 tests passing) — awaiting L5 real-EB staging gate; v2 scheduler still scoped
created: 2026-04-29
updated: 2026-05-08 (post event-driven cutover refresh; warmup-disable-on-kill design added)
tags: [plan, emailbison, campaign, reapply, timezone, kill-triggers, scope, event-driven]
related-plans:
  - INBOX-INTEGRITY-PROGRAM.md (master tracker)
  - event-driven-architecture.md (Tier 1+2 LIVE — affects how live tag is applied)
---

# EOD Campaign Reapply Service

A small, independent app that reapplies the `live` inbox tag set to every active EmailBison campaign once per local-day, after that campaign's send window closes. Its only job is to keep each active campaign's attached senders in sync with the current `live` set, so kill-triggered inboxes drop off the next sending day automatically.

## Status (as of 2026-05-08)

| Layer | State |
|---|---|
| **v1 — operator-invoked CLI** | ✅ SHIPPED at [`apps/eod-reapply/`](../../apps/eod-reapply/). 209 tests passing (99% coverage). Tested through L4 (mocked unit + integration). |
| **L5 — real-EB staging gate** | ⏳ NOT YET RUN. Mandatory before any production use. See [`apps/eod-reapply/STAGING-RUNBOOK.md`](../../apps/eod-reapply/STAGING-RUNBOOK.md). Pilot candidate: Barrena (2 active campaigns, 35 live inboxes, smallest blast radius). |
| **v2 — scheduler / daemon** | ⏳ NOT YET BUILT. Roadmapped: `campaign_schedules` + `campaign_reapply_runs` tables, poll loop, time-zone gate, daemon mode. The library function `reapply_campaign(...)` already supports being called from the v2 scheduler unchanged. |

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
│                    3. GET  /sender-emails?tag_ids[]=live  ──┤   │
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
                            │
                            ▼
                ┌──────────────────────┐
                │ Shared Postgres      │
                │  (charm-email-os DB) │
                ├──────────────────────┤
                │ READ:                │
                │  workspaces          │
                │  workspace_api_keys  │
                │  emailbison_campaigns│
                │  sender_accounts (for cross-check only)
                │                      │
                │ WRITE (own tables):  │
                │  campaign_schedules  │
                │  campaign_reapply_runs│
                └──────────────────────┘
```

## Schema additions

Two new tables, owned by this service. Migrations live in `apps/eod-reapply/migrations/`.

```sql
-- Pulled fresh from EB each cycle. Source of truth is EB; this is a cache.
CREATE TABLE campaign_schedules (
    campaign_id        UUID PRIMARY KEY REFERENCES emailbison_campaigns(id) ON DELETE CASCADE,
    eb_schedule_id     INTEGER,
    monday             BOOLEAN NOT NULL,
    tuesday            BOOLEAN NOT NULL,
    wednesday          BOOLEAN NOT NULL,
    thursday           BOOLEAN NOT NULL,
    friday             BOOLEAN NOT NULL,
    saturday           BOOLEAN NOT NULL,
    sunday             BOOLEAN NOT NULL,
    start_time         TIME    NOT NULL,
    end_time           TIME    NOT NULL,
    timezone           TEXT    NOT NULL,         -- IANA name, e.g. 'Australia/Sydney'
    reapply_buffer_min INTEGER NOT NULL DEFAULT 60,  -- minutes after end_time before we act
    eb_created_at      TIMESTAMPTZ,
    eb_updated_at      TIMESTAMPTZ,
    synced_at          TIMESTAMPTZ NOT NULL,
    CONSTRAINT campaign_schedules_tz_iana CHECK (timezone ~ '^[A-Za-z_]+/[A-Za-z_]+(/[A-Za-z_]+)?$')
);
CREATE INDEX idx_campaign_schedules_synced_at ON campaign_schedules(synced_at);

-- Idempotency table: at most one row per campaign per local-day.
CREATE TABLE campaign_reapply_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id         UUID NOT NULL REFERENCES emailbison_campaigns(id) ON DELETE CASCADE,
    workspace_id        UUID NOT NULL REFERENCES workspaces(id),
    run_local_date      DATE NOT NULL,
    run_local_tz        TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL,           -- see status enum below
    target_sender_ids   INTEGER[] NOT NULL DEFAULT '{}',
    prior_sender_ids    INTEGER[] NOT NULL DEFAULT '{}',
    attached_ids        INTEGER[] NOT NULL DEFAULT '{}',
    removed_ids         INTEGER[] NOT NULL DEFAULT '{}',
    final_sender_ids    INTEGER[] NOT NULL DEFAULT '{}',
    verify_passed       BOOLEAN,
    error_message       TEXT,
    error_step          TEXT,
    is_dry_run          BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT campaign_reapply_runs_unique_local_day
        UNIQUE (campaign_id, run_local_date, is_dry_run)
);
CREATE INDEX idx_campaign_reapply_runs_status ON campaign_reapply_runs(status, started_at DESC);
CREATE INDEX idx_campaign_reapply_runs_workspace ON campaign_reapply_runs(workspace_id, run_local_date DESC);
```

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
| 5 | `GET` | `/api/sender-emails?filters.tag_ids[]={live_tag_id}` | Target set (paginated) |
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

Environment variables only. No on-disk config files.

| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | (required) | Same Postgres as charm-email-os |
| `EMAILBISON_API_URL` | `https://spellcast.hirecharm.com/api` | EB base URL |
| `POLL_INTERVAL_SECONDS` | `300` | How often to evaluate windows |
| `WORKSPACE_CONCURRENCY` | `3` | Parallel workspaces |
| `CAMPAIGN_CONCURRENCY_PER_WORKSPACE` | `1` | Sequential within workspace |
| `WORKSPACE_ALLOWLIST` | (unset = all) | Comma-sep workspace names; phased rollout gate |
| `WORKSPACE_DENYLIST` | (unset) | Inverse — explicit opt-outs |
| `DRY_RUN` | `false` | Compute and log but don't mutate EB |
| `DEFAULT_REAPPLY_BUFFER_MIN` | `60` | Fallback when schedule row has NULL |
| `SLACK_WEBHOOK_URL` | (required) | Alerts |
| `MAX_RESUME_RETRIES` | `3` | Before giving up and paging |

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

## Project layout

```
apps/eod-reapply/
├── pyproject.toml
├── Dockerfile
├── README.md
├── src/eod_reapply/
│   ├── __init__.py
│   ├── main.py                # entrypoint: build pool, start poll loop
│   ├── config.py              # env loading + validation (pydantic-settings)
│   ├── db.py                  # asyncpg pool factory
│   ├── eb_client.py           # subset of EmailBisonClient: only the 8 endpoints we use
│   ├── tag_resolver.py        # cache live_tag_id per workspace
│   ├── schedule_sync.py       # GET /schedule → upsert campaign_schedules
│   ├── window.py              # tz-aware predicate (PURE FN, fully testable)
│   ├── live_set.py            # paginated GET /sender-emails?tag=live
│   ├── reapply.py             # orchestrator (pause→diff→…→resume)
│   ├── audit.py               # campaign_reapply_runs writer with state transitions
│   ├── recovery.py            # startup scan for stuck rows + auto-resume
│   ├── alerts.py              # Slack
│   └── poll_loop.py           # the periodic tick
├── migrations/
│   ├── 001_campaign_schedules.sql
│   └── 002_campaign_reapply_runs.sql
└── tests/
    ├── test_window.py                 # tz math, DST, IDL, frozen clocks
    ├── test_reapply_orchestrator.py   # full happy path + every failure mode
    ├── test_live_set.py               # pagination, empty, partial
    ├── test_idempotency.py            # double-fire, advisory lock
    ├── test_recovery.py               # crashed mid-run scenarios
    └── fixtures/
        └── eb_responses/              # canned responses, golden files
```

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
