---
title: Event-Driven Architecture — Plan & Migration Path
created: 2026-05-05
status: PHASES 1-5 SHIPPED on feature/event-driven-architecture (gated off in prod via EVENT_DRIVEN_ENABLED=false). Awaiting incubation-watcher Phase 4 cutover (Phase 1 of cutover runbook) before flag flip.
related-adrs:
  - adr-006-tagging-kill-overhaul-2026-04-27 (workspace-scoped EB API keys)
  - adr-009-connection-state-separated-from-kill-state-2026-04-30
  - adr-010-lifetime-rate-kill-rule-2026-05-04
related-plans:
  - INBOX-INTEGRITY-PROGRAM.md (master tracker)
  - cross-workspace-integrity-firewall.md (Plan A — already event-driven at DB CHECK constraint layer)
related-docs:
  - docs/concepts/kill-triggers.md
  - docs/local-development/emailbison-sync-worker.md
  - docs/operations/2026-05-05-event-driven-cutover-runbook.md (operator cutover procedure)
---

# Event-Driven Architecture — Plan & Migration Path

## TL;DR

Move every internal state transition from polling-based evaluation to
event-driven handlers via Postgres triggers + LISTEN/NOTIFY +
`event_log` durable queue. Keep external EmailBison ingestion as polling
(EB has no webhooks). Split EB tag writes from DB state changes:
DB transitions are real-time, EB tag synchronization is batched per
workspace every 30 minutes.

Long-term goal: drop state-polling entirely. Every state change in DB
fires a trigger that records the change in `event_log` and emits
`pg_notify`. The listener consumes notifications in <1s; missed
notifications are recovered on reconnect by reading `event_log` rows
in `status='emitted'`. **State polling becomes redundant once we prove
trigger reliability.**

This plan is gated by validation testing — no production deploy until
each gate passes. Total effort ~3-4 days engineering + 4-6 weeks
soak/validation. All work happens on `feature/event-driven-architecture`
branch.

## Why this exists

### Today's pain (post-2026-05-05 Option-1 polling)

Even after shortening polls to 5 min health / 60s workspace_writes,
the kill→promote chain has up to ~7 min latency. A killed inbox can
still be assigned to campaigns for ~7 min. The poll loop also can't
detect silent failures — handlers that crash mid-flight or fail to
apply a tag in EB leave drift that goes undetected until the next
audit.

The lifecycle workflow is also a sequence of well-defined state
transitions that map cleanly to events:

1. Pickup — inbox first appears in workspace (INSERT into sender_accounts)
2. Validation — does this inbox belong here? (Plan A CHECK constraint, already event-driven)
3. Warmup enabled — incubation starts (`warmup_enabled_since` timestamp)
4. Graduation — 14 business days of warmup → `inventory_lifecycle_status='active'`
5. Pool assignment — graduated inbox enters `live` or `reserve` pool
6. Promotion — when live count drops below target, reserve → live
7. Kill — when bounce rate > 5%, inbox → dead, tag in EB, promote replacement

Polling re-evaluates every cycle. Events fire exactly once per
transition.

### Two real failure modes events catch that polling can't

1. **Silent handler failures.** Today, kill_processor processes a kill
   row, EB API call fails, exception logged, DB row says "flagged."
   No alert fires. Tomorrow, `event_log.status='failed'` is queryable
   in one SQL.

2. **Tag drift from missed reconciliation.** Today's audit found 329
   stale `flagged_*` tags + 77 missing `flagged_spam_complaint` tags
   from kill_processor cycles that silently failed weeks ago. The
   two-stage event log makes this class of bug visible immediately
   instead of surfacing months later in audit.

### Why "drop polling" is achievable, not aspirational

I previously said "polling stays as backstop forever." That's wrong.
There are two kinds of polling:

| Kind | Description | Long-term fate |
|---|---|---|
| **State polling** | Every 60s scan business tables, re-evaluate "did anything need action?" | Goes away |
| **Event-log catch-up** | On worker startup, query `event_log WHERE status='emitted'` to process anything that fired while listener was offline | Stays — but it's reading our own durable queue, not re-evaluating business state |
| **External ingestion polling** | Poll EB API for senders / replies / campaigns | Stays — EB has no webhooks |

The thing the operator doesn't want — "polling and events firing on
same condition causing double-action" — is specifically state polling.
That can be removed once triggers are proven reliable.

## Architecture: two tiers + watchdog

```
┌────────────────────────────────────────────────────────────────────┐
│  TIER 1 — DB state transitions (event-driven, sub-second)          │
│                                                                     │
│  TRIGGER fires on state change                                      │
│      ↓                                                              │
│  Atomic same-transaction:                                           │
│    1. INSERT INTO event_log (status='emitted')                      │
│    2. pg_notify(channel, payload_json)                              │
│      ↓                                                              │
│  Listener (asyncpg LISTEN, single connection):                      │
│    1. Receive notification                                          │
│    2. UPDATE event_log SET status='processing', handler_started_at  │
│    3. Run handler — DB-only work, no EB API calls                   │
│    4. Handler enqueues tag_op events into event_log if needed       │
│    5. UPDATE event_log SET status='completed', handler_completed_at │
│                                                                     │
│  On listener disconnect: events still write to event_log via        │
│  trigger. On reconnect: drain rows WHERE status='emitted'.          │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│  TIER 2 — EB tag synchronization (per-workspace, every 30 min)     │
│                                                                     │
│  For each workspace W:                                              │
│    With workspace-scoped EB client (key from workspace_api_keys):  │
│      SELECT * FROM event_log                                        │
│        WHERE event_type LIKE 'tag_op_%'                             │
│          AND status = 'pending'                                     │
│          AND workspace_id = W                                       │
│        ORDER BY emitted_at LIMIT 500;                               │
│      Group by tag_id → bulk EB API calls                            │
│      Mark each tag_op completed/failed in event_log                 │
│                                                                     │
│  Failures are workspace-scoped. Workspace A's expired key doesn't  │
│  block workspace B's batch. Concurrency: SYNC_WORKSPACE_CONCURRENCY │
│  workspaces in parallel, each with its own EB session.              │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│  TIER 3 — Reconciliation watchdog (every 5 min)                    │
│                                                                     │
│  Find orphaned events:                                              │
│    SELECT * FROM event_log                                          │
│      WHERE status = 'processing'                                    │
│        AND handler_started_at < NOW() - INTERVAL '5 minutes';       │
│  Mark them 'orphaned'. Slack alert. Allow re-emission if safe.     │
│                                                                     │
│  Find stalled tag_op queues per workspace:                          │
│    Alert if any workspace has >100 pending tag_ops or oldest       │
│    pending > 2 hours. Likely workspace API key issue.               │
└────────────────────────────────────────────────────────────────────┘
```

## Hard rules (no exceptions)

### Rule 1 — Per-workspace partitioning at every EB-touching layer

**Every EB API call uses a workspace-scoped key.** The system never has
a "global EB key." This is enforced today and must be inherited by the
event-driven design.

Mechanisms:

- `event_log.workspace_id` is **NOT NULL for any tag_op event** (CHECK
  constraint). A handler trying to enqueue a tag_op without a
  workspace_id will fail at the DB layer.
- Tag batch worker iterates per-workspace via the existing
  `_fetch_workspaces_with_keys()` query, using the same
  `EmailBisonClient(api_key=ws['key_token'], is_workspace_scoped=True)`
  pattern as `workspace_writes.py`.
- Listener (Tier 1) never touches EB directly — DB-only. No
  workspace-key dependency on the listener side.
- Concurrency: `SYNC_WORKSPACE_CONCURRENCY` semaphore (currently 3 in
  production) caps parallel workspaces. Each gets its own client
  lifecycle. Workspace A failures don't cascade to workspace B.

### Rule 2 — Triggers run in same transaction as state change

`AFTER INSERT OR UPDATE` triggers in Postgres execute within the
calling transaction by default. If the state change commits, the
event_log row commits with it. If the state change rolls back, the
event_log row rolls back too. **There is no "missed event" failure
mode at write time.**

This is the load-bearing invariant for "drop polling completely."

### Rule 3 — Handlers must be idempotent

Every handler must be safe to run twice on the same event row. Common
patterns:

- `SELECT ... FOR UPDATE SKIP LOCKED` claims an event without blocking
  others.
- Status check before action: `IF status != 'emitted' THEN return`.
- Side effects guarded: `UPDATE sender_accounts SET ... WHERE id = $1
  AND inbox_state = 'live'` — no-op if already transitioned.

### Rule 4 — Tier 1 handlers don't call EB

Tier 1 handlers do DB work + enqueue tag_ops. They never call EB.
This guarantees:

- Listener doesn't need workspace API keys
- Listener can run as a single coroutine serving all workspaces
- EB API rate limits never block Tier 1
- All EB calls are batched + per-workspace in Tier 2

## Schema: event_log table

```sql
-- Migration 107 (after migration runner unblock — see INBOX-INTEGRITY-PROGRAM)
CREATE TABLE event_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- WHAT
    event_type      TEXT NOT NULL,
                    -- 'inbox_pickup', 'warmup_enabled', 'graduated',
                    -- 'pool_changed', 'inbox_died', 'kill_queued',
                    -- 'domain_burned', 'bounce_observed',
                    -- 'tag_op_attach', 'tag_op_remove'

    entity_type     TEXT NOT NULL,
                    -- 'inbox' | 'domain' | 'kill_queue' | 'workspace' | 'response_message'
    entity_id       UUID NOT NULL,

    payload         JSONB NOT NULL DEFAULT '{}',

    -- TWO-STAGE TRACKING
    emitted_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    handler_started_at  TIMESTAMP,
    handler_completed_at TIMESTAMP,

    -- STATUS LIFECYCLE
    status          TEXT NOT NULL DEFAULT 'emitted',
                    -- 'emitted'    → trigger fired, no handler yet
                    -- 'processing' → handler claimed it, working
                    -- 'completed'  → handler finished successfully
                    -- 'failed'     → handler raised; retry_after may be set
                    -- 'orphaned'   → claimed but never completed (watchdog marks)
                    -- 'pending'    → for tag_op events: waiting in batch queue
                    -- 'cancelled'  → superseded or workspace deactivated

    error_message   TEXT,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    retry_after     TIMESTAMP,

    -- WORKSPACE SCOPE — required for any tag_op
    workspace_id    UUID REFERENCES workspaces(id),

    handler_name    TEXT,
    metadata        JSONB DEFAULT '{}',

    -- CHECK: tag_op events must have workspace_id
    CONSTRAINT tag_op_requires_workspace
        CHECK (NOT (event_type LIKE 'tag_op_%') OR workspace_id IS NOT NULL)
);

CREATE INDEX idx_event_log_status_emitted   ON event_log (status, emitted_at);
CREATE INDEX idx_event_log_pending_tag_ops  ON event_log (workspace_id, emitted_at)
    WHERE status = 'pending' AND event_type LIKE 'tag_op_%';
CREATE INDEX idx_event_log_orphan_check     ON event_log (handler_started_at)
    WHERE status = 'processing';
CREATE INDEX idx_event_log_entity           ON event_log (entity_type, entity_id);
CREATE INDEX idx_event_log_workspace        ON event_log (workspace_id, emitted_at DESC);
CREATE INDEX idx_event_log_failed           ON event_log (event_type, emitted_at)
    WHERE status = 'failed';
```

### Operational queries this enables

```sql
-- "Did the kill at 14:23 actually fire?"
SELECT * FROM event_log WHERE event_type = 'inbox_died'
  AND entity_id = '<inbox_uuid>' ORDER BY emitted_at DESC LIMIT 1;

-- "What's stuck right now?"
SELECT event_type, COUNT(*), MIN(emitted_at) AS oldest
FROM event_log WHERE status IN ('processing', 'pending')
GROUP BY event_type;

-- "What failed in the last hour?"
SELECT event_type, error_message, COUNT(*) FROM event_log
WHERE status = 'failed' AND emitted_at > NOW() - INTERVAL '1 hour'
GROUP BY event_type, error_message;

-- "Tag ops backlog per workspace"
SELECT w.workspace_name, el.event_type, COUNT(*) AS pending,
       MIN(el.emitted_at) AS oldest
FROM event_log el JOIN workspaces w ON el.workspace_id = w.id
WHERE el.event_type LIKE 'tag_op_%' AND el.status = 'pending'
GROUP BY w.workspace_name, el.event_type
ORDER BY pending DESC;

-- "End-to-end trace for a specific inbox"
SELECT event_type, status, emitted_at, handler_completed_at,
       error_message
FROM event_log WHERE entity_id = '<inbox_uuid>'
ORDER BY emitted_at;
```

## Trigger catalog

Each trigger writes one event_log row + emits one pg_notify.

### Inbox lifecycle triggers (sender_accounts)

| Trigger | Fires on | event_type | Handler does |
|---|---|---|---|
| `notify_inbox_pickup` | INSERT | `inbox_pickup` | Run cross-workspace soft-validation extras (Plan A handles hard rejection); audit log |
| `notify_warmup_enabled` | UPDATE WHERE warmup_enabled flipped FALSE→TRUE | `warmup_enabled` | Audit incubation start (no DB action — informational) |
| `notify_graduated` | UPDATE WHERE inventory_lifecycle_status='incubating'→'active' | `graduated` | Run pool assignment: `live` if below target + package set, else `reserve` |
| `notify_pool_changed` | UPDATE WHERE inventory_pool_status changed | `pool_changed` | Enqueue tag_op_attach (new tag) + tag_op_remove (old tag) |
| `notify_inbox_died` | UPDATE WHERE inbox_state='live'→'dead' | `inbox_died` | Run pool_promotion (if package set); enqueue tag_op_remove for live tag |

### Kill chain triggers

| Trigger | Fires on | event_type | Handler does |
|---|---|---|---|
| `notify_bounce_observed` | response_messages INSERT WHERE bounce_type IN (hard_blocked, hard_unknown) | `bounce_observed` | Recompute lifetime rate for inbox; if > 5%, INSERT into kill_queue |
| `notify_kill_queued` | kill_queue INSERT WHERE status='pending' | `kill_queued` | Process single kill: set inbox_state='dead', set kill_trigger, enqueue tag_op_attach (flagged_*), enqueue tag_op_remove (live) |
| `notify_complaint_observed` | response_messages INSERT WHERE detect_spam_in_response matches | `complaint_observed` | Recompute complaints_lifetime; if ≥1, INSERT into kill_queue with trigger='spam_complaint' |

### Domain triggers

| Trigger | Fires on | event_type | Handler does |
|---|---|---|---|
| `notify_domain_burned` | domains UPDATE WHERE pool_status='burned' | `domain_burned` | For every inbox on this domain: set inventory_pool_status=NULL; enqueue tag_op_remove for live + reserve tags |

### Workspace config triggers

| Trigger | Fires on | event_type | Handler does |
|---|---|---|---|
| `notify_package_assigned` | workspaces UPDATE WHERE package_id NULL→non-NULL | `package_assigned` | Run `_maintain_pool_thresholds` for that workspace immediately |
| `notify_workspace_paused` | workspaces UPDATE WHERE pause_pool_transitions=TRUE | `workspace_paused` | Cancel pending tag_ops for that workspace (status='cancelled') |

### Connection state triggers (folds in Plan B Phase 2)

[connection-state-machine.md](connection-state-machine.md) Phase 2 calls
for a disconnect notification ladder (24h / 3d / 7d / 20d). Implementing
it as event-handlers folds cleanly into the event-driven design instead
of building a separate notification system.

| Trigger | Fires on | event_type | Handler does |
|---|---|---|---|
| `notify_disconnect_observed` | sender_accounts UPDATE WHERE status transitions Connected → 'Not connected' / 'Disconnected' | `disconnect_observed` | Stamp `disconnected_at` if not set; schedule the first ladder rung |
| `notify_reconnected` | sender_accounts UPDATE WHERE status transitions back to 'Connected' | `reconnected` | Clear `disconnected_at`; cancel any scheduled ladder events |

The notification ladder itself runs as a periodic task (every 1h) that
queries `event_log WHERE event_type='disconnect_observed' AND ...`
combined with current `disconnected_at` to identify which rung any
inbox should fire next. This is "calendar-style" polling on top of
event-recorded state — clean separation.

### Sender-ban code detection (folds in Plan D Pass 3)

[kill-trigger-accuracy.md](kill-trigger-accuracy.md) Pass 3 currently
alerts on Microsoft sender-ban codes (5.7.501/502/503/511/606-649/
703/705/708/750/800) but does not auto-kill. The plan called for "flip
to instant-kill once we trust the signal." Event-driven IS that flip:

| Trigger | Fires on | event_type | Handler does |
|---|---|---|---|
| `notify_sender_ban_detected` | response_messages INSERT WHERE bounce_body matches sender-ban code regex | `sender_ban_detected` | Slack alert (existing behavior); + queue instant-kill row (new behavior, gated by `SENDER_BAN_INSTANT_KILL` env flag for safe rollout) |

Soft rollout: `SENDER_BAN_INSTANT_KILL=false` initial deploy keeps
alert-only behavior. After observing N days of sender-ban events
without false positives, flip to `true`. Existing `event_log`
gives us the audit trail to validate.

### Recap of folded work

This plan absorbs:
- **Plan B Phase 2** (disconnect ladder) — implemented as Tier 1 events
  + a 1h-cadence ladder evaluator. No separate notification system.
- **Plan D Pass 3** (sender-ban instant-kill) — implemented as a
  Tier 1 trigger with a feature-flag soft rollout.
- **Plan F Phase 5** (kill-rule cleanup) — Phase 7 of this plan removes
  the `_24h`/`_7d` columns and `aggregate_bounce_counts_from_events`
  since the event-driven kill chain doesn't need them.

Each of those plans should reference this one as the implementation
vehicle.

## What stays as polling

| Layer | Mechanism | Why |
|---|---|---|
| EB → DB sync (senders, replies, campaigns) | Poll EB API | EB has no webhooks |
| HyperTide order completion | Poll HT API | No webhooks |
| Daily counter resets, snapshots, audits | Cron-driven | Calendar events, not state events |
| Daily Slack audit (7 AM Pacific) | Cron-driven | Calendar event |
| Workspace discovery | Poll every 5 min | Polls EB for new workspaces |
| **Watchdog (Tier 3)** | Poll event_log every 5 min | Catches orphaned 'processing' events; this IS the safety net |

## Branch strategy

```
master  ────●────●────●────────●─── (production, current behavior)
                         ╲
                          ╲
feature/event-driven  ────●●●●──●●──●●── (all work happens here)
                                          ↓
                                   merged when validation passes
```

- All Phase 1-6 code lives on `feature/event-driven-architecture`.
- Master keeps shipping unrelated work (rule tweaks, package assignments,
  doc updates) unchanged.
- Branch is rebased onto master before each merge to avoid drift.
- `EVENT_DRIVEN_ENABLED=false` env flag gates the listener at runtime
  even after merge — so we can deploy code but keep events disabled
  until validation passes.

## Validation gates

Each gate must pass before next phase ships. No production deploy
until Gate 4. Code can land on master under feature flag (still
disabled) at Gate 3 boundary if convenient.

### Gate 1 — Trigger correctness (synthetic tests)

`tests/test_event_triggers.py`. Per trigger:
- Fixture creates the state change.
- Assert: `event_log` row exists with correct `event_type`, `payload`,
  `status='emitted'`, correct `entity_id` + `workspace_id`.
- Assert: `pg_notify` was emitted on the correct channel.

Pass: every defined trigger emits correctly under all expected state
transitions.

### Gate 2 — Handler idempotency (synthetic tests)

`tests/test_event_handlers.py`. Per handler:
- Run handler twice on the same event row.
- Assert: second run is a no-op, no duplicate side effects, event_log
  remains in `completed` state.
- Run handler against partially-completed state (status='processing'
  from a prior crash) → recovers correctly.

Pass: every handler is provably idempotent.

### Gate 3 — Failure mode tests (chaos tests)

For each entry in the failure-mode catalog below, write a test that
causes the failure and asserts:
- `event_log` captures the failure with correct status + error_message.
- Watchdog reaches the row (if applicable) and re-emits or escalates.
- Worker process does not crash.
- No data corruption, no double-processing.

### Gate 3.5 — Retroactive logic validation (2026-05-05 addition)

This gate validates **handler business logic** against historical
production data without deploying anything. Uses the existing
durable state in DB to reconstruct inputs at any point in time
(`response_messages.received_at`, `kill_queue.created_at`,
`inbox_rotation_history.executed_at`, etc.) and replays them through
the proposed handlers.

What it covers:
- ✓ Kill chain: would the new handler produce the same kill at the
  same moment given historical inputs?
- ✓ Promotion chain: would `pick_promotion_candidates` select the
  same reserve given historical workspace state?
- ✓ ESP-restriction compliance: validates ADR-006's
  Microsoft-ride-to-death rule against every historical promotion.
- ✓ Volume estimates: predicts tag op throughput so we know whether
  Tier 2 batch sizing is right.

What it does NOT cover (Gate 1 + Gate 4 still needed):
- ✗ Trigger SQL correctness (synthetic Gate 1)
- ✗ Listener LISTEN/NOTIFY delivery (synthetic Gate 1 + chaos Gate 3)
- ✗ event_log write atomicity (synthetic Gate 1)
- ✗ Real-time end-to-end latency (Gate 4 shadow soak)

Implementation: `scripts/validate_event_driven_retro.py` — read-only,
no production risk, runs in minutes.

**Initial run (2026-05-05):** 1,046 kills replayed across 60 days,
500 rotations validated, 0 unexplained mismatches. Strong baseline.
This gate gets re-run before each subsequent phase to catch any
regressions in handler logic during development.

Pass: ≥95% of mismatches in Section A explainable as deliberate
rule changes (e.g., `disconnected_timeout` removal per ADR-009);
0 non-Google promotions in Section B (per ADR-006); volume estimates
in Section C below 1000 tag ops/day fleet-wide.

### Gate 4 — Shadow mode soak (production data, no actions)

- Deploy feature branch to production with `EVENT_DRIVEN_ENABLED=true`,
  but handlers are **READ-ONLY**: they record what they would do in
  `event_log.metadata`, no DB writes, no EB calls.
- Existing polling continues to do real work.
- After **3 days** (reduced from 1 week — Gate 3.5 already validated
  handler logic; Gate 4 is now primarily validating the trigger →
  listener → event_log stack in real time): compare event_log
  "would-have-done" against polling's actual actions.

Pass: ≥99% match between events and polls. Any divergence diagnosed
and explained.

### Gate 5 — Co-execution (events do real work, polling still safety net)

- Flip handlers to actually execute.
- Polling cycles stay at current cadence (5 min health, 60s workspace_writes).
- Watch for double-processing — handlers must be idempotent enough
  that polls finding "already processed" rows are a no-op.
- **1 week** of clean operation (reduced from 2 weeks — Gate 3.5
  retroactive validation gives high logic confidence going in).

Pass: zero double-processing detected; all polling actions during
this window are no-ops because events handled them first.

### Gate 6 — Drop state polling

- Disable state-polling cycles via env flag.
- Keep event-log catch-up (worker startup) + external EB ingestion
  polling.
- 2 more weeks of operation.

Pass: zero state drift detected; event_log shows no orphans; all
kills/promotions/transitions traced end-to-end.

### Gate 7 — Remove polling code

- Delete state-polling code paths entirely.
- Final commit removes polling-only env vars + helpers.
- Update `docs/local-development/emailbison-sync-worker.md`.

## Failure mode test catalog (Gate 3)

Every entry needs a test in `tests/test_event_failure_modes.py`:

1. Worker crashes mid-handler (DB row left in `processing`)
   → Watchdog marks `orphaned` after 5 min, alerts.
2. Worker disconnects from Postgres LISTEN (events fire to dropped connection)
   → On reconnect, listener queries `WHERE status='emitted'` and drains.
3. Trigger function has a bug and silently fails
   → Audit query `state changes WITHOUT corresponding event_log row` catches it.
4. Handler raises an exception we don't catch
   → Caught at outer dispatcher, status='failed', alert fires.
5. EB API returns 500 (during Tier 2 batch)
   → tag_op stays `pending`, retry_after set, next cycle picks up.
6. EB API returns 401 (workspace key expired)
   → tag_op marked `failed`; per-workspace alert; operator rotates key
     and re-emits failed events.
7. EB API returns 404 (tag deleted out from under us)
   → Handler logs + marks `failed` with diagnostic; doesn't crash.
8. Two events for same entity arrive in unexpected order
   → Idempotency in handler ensures correct final state regardless of order.
9. event_log row is somehow already in `completed` state when handler picks it up
   → Handler bails immediately, no double-action.
10. DB CHECK constraint rejects the state change a handler tried to write
    → Caught at handler boundary, `failed` status, alert.
11. Two listeners running concurrently (multi-worker future-proofing)
    → `SELECT ... FOR UPDATE SKIP LOCKED` ensures only one claims each row.
12. Workspace deactivated while tag_ops are pending
    → Reaper marks them `cancelled` with reason='workspace_deactivated'.

## Success criteria for "drop polling completely"

We don't drop polling until ALL are true:

- [ ] event_log shows zero orphaned events for 7 consecutive days
- [ ] event_log shows zero failed events that weren't operator-acknowledged
- [ ] Audit query: every state change in `sender_accounts`, `kill_queue`,
      `domains`, `response_messages` has a corresponding event_log row
      (100% of state changes are event-tracked)
- [ ] Polling cycles, when run side-by-side with events, find zero new
      work (every poll finds events already handled it)
- [ ] All Gate 3 failure modes pass
- [ ] Operator confidence: team is comfortable answering "what
      happened" with `SELECT FROM event_log` instead of grepping logs

If any criterion isn't true, polling stays.

## Implementation phases

Total: ~5-6 days engineering + **2-3 weeks soak** (reduced from 4-6 weeks
after Gate 3.5 retroactive validation was added 2026-05-05).

### Phase 1 — Foundation (1 day)
- New branch `feature/event-driven-architecture`
- Migration `107_event_log.sql` (after 076 unblock — see [migration runner backlog](INBOX-INTEGRITY-PROGRAM.md))
- New module `sync_modules/event_listener.py`
- New module `sync_modules/event_emitter.py` (helper for handlers to update event_log)
- `EVENT_DRIVEN_ENABLED` feature flag (default false)

### Phase 2 — Wire DB triggers (1.5 days)
- One trigger per row in the catalog above
- Each trigger: INSERT INTO event_log + pg_notify in same transaction
- Triggers committed under feature flag (no listener consumes yet)
- Gate 1 tests pass

### Phase 3 — Refactor kill_processor + pool_promotion to single-row (1 day)
- Add `process_one(kill_queue_id)` and `promote_one(workspace_id)`
- Existing batch methods stay as poll backstop
- Gate 2 tests pass

### Phase 4 — Tier 2 batch tag worker (1 day, **SHIPPED 2026-05-05 on feature branch**)
- ✅ Tier 1 handlers do not call EB API (Phase 2)
- ✅ Handlers emit `tag_op_attach` / `tag_op_remove` events into event_log
- ✅ New `sync_modules/tag_op_worker.py` (TagOpWorker class) — drains
  pending tag_ops per workspace using workspace-scoped EB clients
- ✅ Bulk endpoints added to `emailbison_client.py`
  (`tag_inboxes_bulk`, `untag_inboxes_bulk`)
- ✅ Wired into `emailbison_sync_worker.py` poll loop with
  `SYNC_INTERVAL_TAG_OP_DRAIN` env var (default 1800s = 30 min)
- ✅ Coexists with `set_tag_sync` (both idempotent on EB side)
- ✅ Gate 2 tests (10 cases) covering: bulk grouping, per-workspace
  isolation, EB failure handling, retry_after backoff, missing
  emailbison_account_id, idempotency, tag id cache, CHECK constraint
  enforcement of workspace_id

  Tests parse + skip cleanly locally; run in CI.

  Set_tag_sync is NOT removed yet — both run in parallel during the
  rollout. After Gate 6 (drop state polling), set_tag_sync becomes
  redundant and can be removed in cleanup.

### Phase 5 — Shadow mode (1 week soak)
- Production deploy with handlers in READ-ONLY mode
- Gate 4 validation: event_log "would-have-done" vs polls' actual actions
- 99% match required to advance

### Phase 6 — Co-execution (2 weeks soak)
- Handlers execute real work; polls still run as safety net
- Gate 5: no double-processing

### Phase 7 — Drop state polling (2 weeks soak)
- Disable state-polling cycles
- Watchdog + event-log catch-up are the only "polling-like" mechanisms
- Gate 6: zero drift detected

### Phase 8 — Remove polling code (half day)
- Delete state-polling code paths
- Final commit + docs update

## Files that would change

| File | Change |
|------|--------|
| `migrations/107_event_log.sql` | NEW — event_log table + indexes + tag_op CHECK constraint |
| `migrations/108_event_triggers.sql` | NEW — all triggers + functions |
| `sync_modules/event_listener.py` | NEW — asyncpg LISTEN, dispatcher (Phase 1 ✅) |
| `sync_modules/event_handlers/` | NEW — one module per event_type (Phase 2 ✅) |
| `sync_modules/pool_promotion.py` | Added `promote_to_target` + `get_workspace_promotion_target` (Phase 3 ✅) |
| `sync_modules/workspace_writes.py` | DRY refactor: `_maintain_pool_thresholds` calls `promote_to_target` (Phase 3 ✅) |
| `sync_modules/tag_op_worker.py` | NEW — Tier 2 batch worker (Phase 4 ✅) |
| `sync_modules/emailbison_client.py` | Added `tag_inboxes_bulk` + `untag_inboxes_bulk` (Phase 4 ✅) |
| `sync_modules/set_tag_sync.py` | Untouched (coexists with TagOpWorker; removed post-Gate-6) |
| `emailbison_sync_worker.py` | Wired `run_tag_op_drain` into poll loop (Phase 4 ✅); EventListener wiring still pending |
| `tests/test_event_triggers.py` | NEW — Gate 1 |
| `tests/test_event_handlers.py` | NEW — Gate 2 |
| `tests/test_event_failure_modes.py` | NEW — Gate 3 |
| `docs/concepts/event-architecture.md` | NEW — design reference |
| `docs/local-development/emailbison-sync-worker.md` | UPDATE — describe two-tier architecture |

## Out of scope

- **EmailBison webhooks.** EB doesn't push events; ingestion stays polling forever.
- **Replacing the EmailBison sync worker.** Worker runs both listener
  and remaining polls in the same process. No new services.
- **Cross-service event bus.** Postgres LISTEN/NOTIFY is sufficient.
- **Replay / audit log beyond event_log.** event_log IS the audit log.
- **Plan A cross-workspace integrity.** Already event-driven via DB
  CHECK constraint. Untouched.

## Decision points before Phase 1 kickoff

1. **Branch name `feature/event-driven-architecture`?** ✓
2. **Validation cadence: 4-6 week total soak?** ✓
3. **`EVENT_DRIVEN_ENABLED` default false even after merge to master?** ✓
4. **Per-workspace partitioning enforced via CHECK constraint + per-workspace batch worker?** ✓
5. **Drop state polling at Gate 6, remove code at Gate 7?** ✓
6. **Any pre-Phase-1 work needed?** Yes: unblock migration runner (076)
   so migrations 107 + 108 can apply automatically. See INBOX-INTEGRITY-PROGRAM
   master tracker.

## Operator note: dual-remote push reminder

This work, like all production-affecting work, must be pushed to BOTH
`origin` (laviefatigue) AND `hirecharm` (production source) to deploy.
See INBOX-INTEGRITY-PROGRAM § 2.1 for the deploy gotcha that bit us
on 2026-05-04 (kill-rule rewrite).
