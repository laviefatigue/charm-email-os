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
2. **Operator decision** on workspace package assignments.
   Recommendations + analysis already in yesterday's session report.
3. **Once incubation-watcher Phase 4 cuts over**, kick off event-driven
   Phase 1 on `feature/event-driven-architecture` branch. Foundation
   work: migration 107 (event_log table), listener module, feature
   flag scaffold. ~1 day.
