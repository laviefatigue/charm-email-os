---
title: Database Migrations
created: 2026-01-16
updated: 2026-04-13
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

Migrations `001` → `091` are applied in production as of 2026-04-13.

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

## Writing New Migrations

- Use `IF NOT EXISTS` / `IF EXISTS` everywhere — migrations must be idempotent if partially applied
- Wrap in a transaction (the runner does this for you)
- Test locally with `docker compose -f docker-compose.local.yml up` before pushing
- Never modify an applied migration — write a new one

## Related

- [[emailbison-sync]] — sync worker that uses workspace_sync_queue
- `api/migration_runner.py` — runner implementation
- `migrations/` — all SQL files
