---
title: Database Migrations
created: 2026-01-16
updated: 2026-04-28
tags: [database, migrations]
---

# Database Migrations

## How Migrations Run

Migrations are plain SQL files in `migrations/` numbered sequentially (`001_*.sql` → `091_*.sql`). They run automatically on API startup via `api/migration_runner.py`.

The runner tracks applied migrations in a `_migrations` table. On each startup it:
1. Finds all `.sql` files not yet in `_migrations`
2. Runs them in filename order, each in a transaction
3. Stops on first failure (fix the file, redeploy to retry)

**To apply a migration**: add the `.sql` file, commit, push, deploy `charm-api`. The runner applies it on next startup.

**To check what's applied** (via admin SQL endpoint):
```sql
SELECT name, applied_at FROM _migrations ORDER BY name;
```

---

## Current Range

Migrations `001` → `097` are applied in production as of 2026-04-28.

Notable recent migrations:

| Migration | What it does |
|-----------|-------------|
| `085_rate_based_domain_burns.sql` | ESP-aware burn thresholds (Google vs Entra) |
| `086_engagement_counters.sql` | Engagement columns on sender_accounts, inbox_engagement_snapshots table, v_esp_performance view |
| `087_client_kickoff_columns.sql` | Client kickoff tracking columns |
| `088_fix_domain_burn_functions.sql` | Fixed domain burn function edge cases |
| `089_workspace_api_keys.sql` | Per-workspace EB API tokens for concurrent sync |
| `090_suppression_module.sql` | Domain suppression lists per client |
| `091_workspace_sync_queue.sql` | Persistent job queue for concurrent workspace sync |
| `092_domain_pipeline_queue.sql` | Domain purchase pipeline queue |
| `093_dayai_watcher_state.sql` | dayai watcher state + runs tables |
| `094_warmup_enabled_since.sql` | **Overhaul:** `warmup_enabled_since`, `warmup_disabled_at` columns + maintenance trigger + 4,172-row backfill from `warmup_started_at`. Continuous-tracking warmup state for the 14 BD graduation timer |
| `095_total_sends_24h.sql` | **Overhaul:** `total_sends_24h INTEGER` column + index. Used by health_checks for the 20-send floor on count-based kill triggers |
| `096_warmup_trigger_handles_insert.sql` | **Overhaul:** Bug fix to migration 094 — original trigger fired on UPDATE only, missing INSERT. Without this, newly-synced inboxes never got `warmup_enabled_since` stamped → graduation eligibility broken for new fleet |
| `097_workspace_packages.sql` | **Overhaul:** `workspace_packages` reference table (seeded with `50k_google` and `100k_google`) + `workspaces.package_id`, `target_live_count_override`, `pause_pool_transitions`, `package_assigned_at` columns + validation trigger + `workspace_effective_targets` view |

---

## Migration 091: workspace_sync_queue

The most architecturally significant recent migration. Creates the job queue that drives the concurrent sync worker.

Key design decisions:
- `FOR UPDATE SKIP LOCKED` in the batch consumer prevents double-claiming across concurrent consumers
- Partial unique index `ON workspace_sync_queue(workspace_id, sync_type) WHERE status='pending'` prevents duplicate pending jobs — `ON CONFLICT DO NOTHING` is always safe
- `priority` field: normal jobs = 0, force-refresh from client dashboard = 10
- Failed jobs are not auto-retried — the scheduler re-queues on next tick when `last_successful_sync` is stale

See [[emailbison-sync]] for full architecture documentation.

---

## Migrations 094–097: Tagging-Kill Overhaul (2026-04-27)

Schema additions for the 2026-04-27 overhaul. See [[../adr/adr-006-tagging-kill-overhaul-2026-04-27]] for the full architectural decision record and [[../work-logs/2026-04-27-tagging-kill-overhaul-plan]] for the handoff doc.

**094 — `warmup_enabled_since`**

Adds `warmup_enabled_since` and `warmup_disabled_at` columns on `sender_accounts`, plus a `track_warmup_enabled_transition` trigger that maintains them on `warmup_enabled` flips. The trigger:
- Stamps `warmup_enabled_since=NOW()` and clears `warmup_disabled_at` on TRUE transition
- Stamps `warmup_disabled_at=NOW()` and clears `warmup_enabled_since` on FALSE/NULL transition
- Initial value (INSERT path) handled by migration 096 fix

This enables the 14 business-day graduation timer to count CONTINUOUS warmup-enabled time (paused-then-resumed warmup resets the clock). 4,172-row backfill from `warmup_started_at` for existing inboxes.

**095 — `total_sends_24h`**

Adds `total_sends_24h INTEGER NOT NULL DEFAULT 0` column on `sender_accounts` plus an index. Populated by `sync_accounts.upsert` from the same delta that updates `total_sends_7d`.

Used by `health_checks` for the 20-send floor on count-based kill triggers (`KILL_THRESHOLD_MIN_SENDS_24H_FOR_COUNT_TRIGGER=20`). Falls back to `total_sends_7d ≥ 20` until the column populates fleet-wide.

**096 — `warmup_trigger_handles_insert`**

Bug fix to migration 094. The original trigger function referenced `OLD.warmup_enabled` directly, so it only fired on UPDATE. Newly-synced inboxes via INSERT never got `warmup_enabled_since` stamped → graduation eligibility broken for the new fleet.

Function rewritten with `IF TG_OP = 'INSERT'` branch; trigger fires on `BEFORE INSERT OR UPDATE OF warmup_enabled`.

**097 — `workspace_packages`**

Reference table for the post-overhaul package model (replaces the Starter/Growth Entra+Google mix; CEO directive: 100% Google going forward):

```sql
CREATE TABLE workspace_packages (
    package_id            VARCHAR PRIMARY KEY,    -- '50k_google' / '100k_google'
    package_name          VARCHAR NOT NULL,
    monthly_send_volume   INTEGER NOT NULL,
    target_live_count     INTEGER NOT NULL,
    target_reserve_count  INTEGER NOT NULL,
    description           TEXT
);
```

Seeded:
- `50k_google`: 150 live + 30 reserve (10 orders + 2 reserve)
- `100k_google`: 300 live + 60 reserve (20 orders + 4 reserve)

Adds `workspaces.package_id` (FK), `target_live_count_override` (operator lower-only), `pause_pool_transitions` (emergency stop), `package_assigned_at`. Validation trigger enforces `override ≤ package.target_live_count`. View `workspace_effective_targets` rolls up the effective live target per workspace for the threshold-driven promotion path.

---

## Writing New Migrations

- Use `IF NOT EXISTS` / `IF EXISTS` everywhere — migrations must be idempotent if partially applied
- Wrap in a transaction (the runner does this for you)
- Test locally with `docker compose -f docker-compose.local.yml up` before pushing
- Never modify an applied migration — write a new one

## Related

- [[emailbison-sync]] — sync worker that uses workspace_sync_queue
- `api/migration_runner.py` — runner implementation
- `migrations/` — all SQL files
