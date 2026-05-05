---
title: 2026-05-05 — Migration runner unblock + event-driven plan refinement
created: 2026-05-05
related-plans:
  - event-driven-architecture.md
  - INBOX-INTEGRITY-PROGRAM.md
related-work-logs:
  - 2026-05-04-kill-rule-rate-rewrite-and-revival.md
---

# 2026-05-05 — Migration runner unblock + event-driven plan refinement

## What shipped today

### 1. EB tag drift cleanup (329 + 77 actions)

`scripts/cleanup_eb_tag_drift.py` (new, committed in `f6140b7`).
One-shot fixer for two pre-existing EB ↔ DB tag drifts:

- **Drift A** — 329 stale `flagged_*` tags on live inboxes (legacy
  `flagged_fresh_inbox_*`, `flagged_provider_block_*` from removed
  triggers): removed via per-workspace EB API calls.
- **Drift B** — 77 dead-by-`spam_complaint` inboxes missing the
  `flagged_spam_complaint` tag in EB (kill_processor silent failures
  from earlier cycles): re-applied via per-workspace EB API calls.

0 errors. Audit log written. Post-cleanup audit shows:
`drift_live_has_flagged_tag = 0` and `drift_dead_missing_flagged_tag = 0`.

### 2. Polling cycle compression (Option 1)

Env-var changes via `scripts/coolify.py env-set`:
- `SYNC_INTERVAL_HEALTH`: 900 → **300** (15 min → 5 min)
- `SYNC_INTERVAL_KILL`: 900 → **60** (15 min → 60 s)

Worst-case kill → tag → promote chain dropped from **~75 min to ~7 min**
without any code changes. Just sync worker env reconfiguration.

### 3. Latent-capacity warning patch (silent-skip detection)

`sync_modules/workspace_writes.py`. When a workspace has `package_id IS
NULL`, `_maintain_pool_thresholds` was a silent skip — Charm sat with
45 graduated Gmail reserves idle for ~6 months because no signal fired.
Patched the caller to log a WARNING when graduated Gmail reserves > 0
on a workspace without a package.

After deploy, fired exactly as expected:
- Charm: 42 graduated Gmail reserves idle
- Selery: 23 reserves idle
- Search Atlas: 1 reserve idle
- Stable Kernel: 9 reserves idle

(Counts shifted slightly through the day as 1:1 kill-driven promotion
ran. The point of the warning is to surface latent-capacity stalls
that would otherwise stay invisible.)

### 4. Critical regression caught and prevented

While the f6140b7 deploy was in-flight, audited Coolify env vars and
found `KILL_RULE_DRY_RUN` had **two conflicting entries** (`false` from
yesterday's Phase 4 flip, plus a leftover `true` from Phase 1 init).

Coolify's behavior on duplicates is undefined. The new container could
have started with `KILL_RULE_DRY_RUN=true`, silently reverting the kill
rule to dry-run mode and stopping kill production.

Fixed:
- Deleted the `=true` entry via raw API DELETE before the container swap.
- Patched `scripts/coolify.py env-set` to self-heal duplicates on every
  call (commit `c51ce9e`). All future env-set calls clean up duplicates.

### 5. Event-driven architecture plan finalized

[docs/plans/event-driven-architecture.md](../plans/event-driven-architecture.md)
rewritten with the operator's two-tier mental model:

- **Tier 1** — DB state transitions via Postgres triggers + LISTEN/NOTIFY
  + `event_log` durable queue. Sub-second handler latency.
- **Tier 2** — EB tag synchronization batched per workspace every 30 min.
  Each workspace processed with its own workspace-scoped EB key.
- **Tier 3** — Reconciliation watchdog every 5 min. Catches orphaned
  events (claimed by handler but never completed).

Two coordination opportunities folded in:

- **Plan B Phase 2** (disconnect ladder, 24h/3d/7d/20d notifications)
  becomes a `notify_disconnect_observed` trigger + 1h-cadence ladder
  evaluator. No separate notification system.
- **Plan D Pass 3** (sender-ban instant-kill, MS 5.7.501-503/etc.)
  becomes a `notify_sender_ban_detected` trigger with
  `SENDER_BAN_INSTANT_KILL` env flag for safe rollout.

7 validation gates with a feature branch + 4-6 week soak before any
state polling is removed. Long-term endpoint: drop state polling
entirely once event_log proves reliable.

### 6. Comprehensive conflict analysis

Mapped the entire production system against the proposed event-driven
architecture. Three real conflicts identified that needed resolution
before code:

1. **Migration runner blocked on 076** (gating dependency)
2. **set_tag_sync DB-state-driven vs event_log-driven** (Phase 4 of
   plan handles this; load-bearing for Gate 5 co-execution)
3. **incubation-watcher Phase 4 cutover** should complete first to
   eliminate dual-producer ambiguity during validation testing

Two coordination opportunities (folded above). Everything else
coexists through idempotent handlers + producer-agnostic triggers.

### 7. Migration runner unblocked

Previously: stuck on `076_domain_level_ab_sets.sql` since at least
2026-04-13. 18 migrations sat unrecorded. Migration 105 had to be
applied directly via admin endpoint as a workaround.

Diagnosis:
- 076 added a `valid_pool_status` CHECK constraint that didn't include
  `'cancelled'` (a pool_status value introduced later). Production had
  149 cancelled rows, so the constraint failed.
- The constraint was manually fixed (production DB has the broader
  `('unassigned','live','reserve','burned','cancelled')` shape now)
  but `_migrations` table never got the row.
- Same pattern for 17 other migrations: physically applied via psql
  during operator firefights, never recorded.

Audit + fix:
- Signature-checked all 18 unrecorded migrations against production
  DB schema (table existence, column existence, constraint existence,
  function existence, view existence).
- **13 were physically applied**, missing only `_migrations` records.
  Marked them via direct INSERT into `_migrations`:
  `076, 077, 078, 094, 095, 097, 098, 099, 100, 101, 102, 103, 104`.
- **5 were truly pending**: `082, 083, 084, 092, 096`. All used
  `CREATE IF NOT EXISTS` defensive patterns. Restarted charm-api;
  migration runner applied all 5 cleanly:
  ```
  INFO - Found 5 pending migration(s)
  INFO - Applied migration: 082_domain_pipeline_views.sql
  INFO - Applied migration: 083_warmup_snapshots.sql
  INFO - Applied migration: 084_domain_velocity_and_swap.sql
  INFO - Applied migration: 092_domain_pipeline_queue.sql
  INFO - Applied migration: 096_warmup_trigger_handles_insert.sql
  ```
- Final state: **`All 104 migrations already applied`**.

This also fixes two production daily-snapshot failures that had been
silently logging errors:
- `Failed to capture warmup snapshots: relation "warmup_snapshots" does not exist` (083)
- `Failed to recalculate domain velocities: function recalculate_all_domain_velocities() does not exist` (084)

The migration runner is now fully unblocked. Future migrations (107
event_log + 108 triggers for the event-driven rollout) will apply
cleanly on next deploy.

## Production state at end of session

- 11 active workspaces
- 4,229 active inboxes
- 2,909 live + 1,320 dead breakdown
- Daily fleet capacity: ~12,186 sends
- Kill rule (rate-based, ESP-agnostic, lifetime > 5%) load-bearing in
  production. 63 legitimate kills processed yesterday, 0 new kills
  today (steady state — yesterday's high-volume cleanup absorbed the
  backlog).
- 307 inboxes resurrected from yesterday's count-rule false positives.
- 329 + 77 EB tag drifts cleaned up today.

## Pending workstream queue

| Item | Status | Blocking |
|---|---|---|
| incubation-watcher Phase 4 cutover (decomposition plan) | Phase 3 shadow validation running, ~6 days remaining | Event-driven Phase 2 |
| Event-driven architecture Phase 1-8 | Plan complete; awaiting prerequisites | (1) above |
| Workspace package assignments (10 of 11 NULL) | Operator decision pending | None — operator-driven |
| Plan B Phase 2 disconnect ladder | Folded into event-driven | Event-driven Phase 1 |
| Plan D Pass 3 sender-ban instant-kill | Folded into event-driven | Event-driven Phase 1 |
| Plan F Phase 5 cleanup (drop legacy `_24h`/`_7d` columns) | Folded into event-driven | Event-driven Phase 7 |

## Files changed today

| File | Type | Change |
|------|------|--------|
| `scripts/cleanup_eb_tag_drift.py` | NEW | A/B drift fixer |
| `scripts/coolify.py` | EDIT | force=true default + env-set self-heals duplicates |
| `sync_modules/workspace_writes.py` | EDIT | latent-capacity warning patch |
| `docs/plans/event-driven-architecture.md` | REWRITE | Two-tier design + 7 validation gates + Plan B/D fold-in |
| `docs/plans/INBOX-INTEGRITY-PROGRAM.md` | EDIT | event-driven workstream + § 2.2 + § 2.3 |
| `docs/plans/kill-trigger-accuracy.md` | EDIT | Pass 3 fold-in note |
| `docs/plans/connection-state-machine.md` | EDIT | Phase 2 fold-in note |
| `docs/work-logs/2026-05-05-...md` | NEW | This file |

Migration runner state changes (DB-only, no commits):
- 13 migrations marked applied via direct `INSERT INTO _migrations`
- 5 migrations applied via charm-api startup runner

## What's NEXT

1. **Wait** for incubation-watcher Phase 3 shadow soak to complete
   (~6 days). Then operator decides on Phase 4 cutover.
2. **Operator decision** on Charm package assignment (other 7 done).

## Late-day update (event-driven feature branch — Phases 1-4 SHIPPED)

After unblocking the migration runner and assigning packages, kicked
off the event-driven workstream on `feature/event-driven-architecture`.
NOT MERGED to master. Production unaffected.

### Phase 1 (commit df06e85): foundation

- Migration `107_event_log.sql` — durable event queue with two-stage
  tracking (emitted → processing → completed/failed/orphaned).
  CHECK constraint enforces `workspace_id NOT NULL` for any tag_op_*
  event (per ADR-006 partitioning rule).
- Migration `108_event_triggers.sql` — 7 triggers + emit_event() helper.
  Triggers: bounce_observed, kill_queued, inbox_died, inbox_pickup,
  pool_changed, domain_burned, package_assigned.
- `sync_modules/event_listener.py` — asyncpg LISTEN/NOTIFY consumer
  with reconnect-resilient catch-up (drains status='emitted' on start)
  and watchdog for orphaned events.
- `tests/test_event_triggers.py` — 12 Gate 1 synthetic tests covering
  trigger correctness, transaction-rollback guarantees, and the CHECK
  constraint.

### Phase 2 (commit e71cb94): handler implementations

- `sync_modules/event_handlers/` package with 7 handlers + shared helpers.
- 5 full implementations: bounce_observed, kill_queued, pool_changed,
  domain_burned, inbox_pickup.
- 2 stubs (Phase 3 wires real promotion): inbox_died, package_assigned.
- HANDLER_REGISTRY exports for listener wiring.
- `tests/test_event_handlers.py` — 10 Gate 2 idempotency tests.

### Phase 3 (commit 34089bc): single-row promote_to_target + listener fix

- Listener architecture fix: handlers now get a fresh pool connection,
  not the LISTEN connection (which must stay free for notifications).
  EventHandler signature changed to `(event, conn)`.
- New `pool_promotion.promote_to_target(db, workspace_id, target)` —
  single-row entry point shared by polling cycle and event handlers.
  Returns structured result with promoted count, deficit, reserves
  available, no_candidates flag.
- `pool_promotion.get_workspace_promotion_target(conn, workspace_id)` —
  resolves effective target (override > package default > None).
- inbox_died_handler + package_assigned_handler stubs replaced with
  real implementations calling promote_to_target.
- `_maintain_pool_thresholds` in workspace_writes.py refactored to use
  shared `promote_to_target` (DRY). Reserve-runway and no-reserves
  alerts stay in the orchestrator (alerter is workspace-orchestrator-
  specific).

### Phase 4 (this commit): Tier 2 batch tag worker

- `sync_modules/tag_op_worker.py` — TagOpWorker class. Drains pending
  `tag_op_*` events from event_log per workspace. Each workspace gets
  its own EmailBisonClient (workspace-scoped key per ADR-006).
  Workspace-level failures isolated. Bulk per-tag grouping minimizes
  EB API calls. Per-workspace tag_id cache.
- `emailbison_client.py` — added `tag_inboxes_bulk` and
  `untag_inboxes_bulk` (the underlying EB endpoints already accept
  arrays; existing `tag_inbox` was just calling them with single-element
  lists).
- `tests/fakes.py` — extended FakeEmailBisonClient with bulk methods.
- `tests/test_tag_op_worker.py` — 10 Gate 2 tests covering bulk
  grouping, workspace isolation, EB failure handling, retry_after
  backoff, missing emailbison_account_id, idempotency, tag id cache,
  and the CHECK constraint.
- `emailbison_sync_worker.py` — wired `run_tag_op_drain` into poll loop
  with `SYNC_INTERVAL_TAG_OP_DRAIN` (default 30 min).
- `set_tag_sync.py` — untouched, but header annotated with the
  coexistence note. Both modules run side-by-side; tag operations are
  idempotent on EB so duplicate writes are 200 OK no-ops. Plan to
  remove set_tag_sync after Gate 6 (drop state polling).

### Test count across all phases

22 from Phase 1+2 + 10 from Phase 4 = **32 synthetic tests**. All
parse + skip cleanly without Docker (testcontainers required for
real-DB integration). CI runs them end-to-end.

Plus 1,046 historical kills + 500 historical promotions already
replayed through Gate 3.5 retroactive validator — 0 unexplained
mismatches.

### Gating

Pre-deploy: incubation-watcher Phase 4 cutover (~6 days remaining
shadow soak per the conflict analysis). After cutover, merge feature
branch to master, then deploy with `EVENT_DRIVEN_ENABLED=false`
(listener stays dormant). Then Gate 4 shadow mode (~3 days), Gate 5
co-execution (1 week), Gate 6 drop state polling (1 week), Gate 7
remove polling code.

Total remaining timeline: ~3-4 weeks of soak, no further engineering
work needed (Phase 5 disconnect ladder + sender-ban detection are
designed but not built — ship after Phase 4 proves out).

## End-of-day update (2026-05-05 evening)

### Incubation-watcher shadow validation: clean parity

Two SQL probes against production confirm shadow soak can be
compressed dramatically:

- **Overdue incubating check** (would lifecycle_tag_sync miss
  graduations the watcher would catch?) — **0 rows across all
  workspaces**. Zero divergence.
- **Recent graduations (last 7d, lifecycle_tag_sync triggered)** —
  Charm 248, SKMR 94, Sammy 5, Spout 1 = 348 total. Healthy throughput.

Conclusion: original 6-day soak estimate revised to **48h co-execution**
followed by drop-graduate-branch. The watcher's predicate currently
matches zero candidates lifecycle_tag_sync hasn't already handled, so
turning it on with APPLY=true is a no-op until the next graduation
window — and from there the same row gets handled by both for ~one
cycle, then by the watcher only.

### Phase 5: EventListener wired into emailbison_sync_worker

`emailbison_sync_worker.py` now imports + spawns the Tier 1 listener
and watchdog as background asyncio tasks, gated by
`EVENT_DRIVEN_ENABLED` (default `false`). Boot logs print
`Event-driven (Tier 1 listener): ON|OFF` so the flag state is
verifiable in Coolify logs.

Smoke-tested: with `EVENT_DRIVEN_ENABLED=false`, the orchestrator
constructs cleanly, no event-driven imports execute, no log lines fire.
Setting flag to true triggers `_start_event_driven` which:

1. Imports `EventListener`, `run_watchdog`, `HANDLER_REGISTRY`
2. Constructs `EventListener(db_dsn, db_pool)` with all 7 handlers
   registered
3. Spawns two named asyncio tasks (`event_listener`, `event_watchdog`)
4. Logs `Event-driven: listener registered 7 handlers, watchdog
   spawned`

Failures here are non-fatal — listener startup errors get logged +
alerted, polling continues unchanged.

`_stop_event_driven` is wired into the existing `finally` block in
`start()`, so SIGTERM cleanly cancels both tasks before the pool
closes.

### Cutover runbook published

`docs/operations/2026-05-05-event-driven-cutover-runbook.md` covers:

- Phase 1: incubation-watcher 24h shadow-compare → APPLY=true
  per-workspace → 48h soak → drop graduate branch
- Phase 2: feature branch → master → deploy with flag OFF →
  `EVENT_DRIVEN_ENABLED=true` → 24h gate → 7d shadow soak (Gate 5) →
  drop set_tag_sync (Gate 6)
- Verification cookbook with health/partitioning/idempotency queries
- 5 stop-the-line tripwires
- Rollback procedure for both phases (env-set false + redeploy is
  fully reversible; triggers stay armed and accumulate `emitted` rows
  the next listener catch-up drains)

### Status

- Engineering work complete on `feature/event-driven-architecture`
  through Phase 5
- Pre-deploy gate (incubation-watcher cutover) is operator-driven and
  follows the runbook
- After incubation-watcher 48h soak + drop, merge feature branch to
  master and follow Phase 2 of the runbook
