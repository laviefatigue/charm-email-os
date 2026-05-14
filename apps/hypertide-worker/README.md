# hypertide-worker

Hypertide reconciliation service. Single source of truth for HT-side state and the bridge into our `domains` table.

**See:** [docs/architecture/hypertide-service.md](../../docs/architecture/hypertide-service.md) for the architectural plan and phased roadmap. [docs/integrations/hypertide-api.md](../../docs/integrations/hypertide-api.md) for HT API specifics.

## Phase 1 scope (current)

Read-only data collection. Pulls `/orders/active` + `verify-revert`, matches to `domains` rows by `domain_name`, populates `hypertide_*` columns. INSERTs new rows for HT records that don't match any DB row in an HT-managed workspace. Flags unmatched in-scope domains as `is_legacy=TRUE`.

**No writes to Hypertide.** Cancel/order flows are Phase 2/3.

## Commands

```bash
hypertide-worker audit                  # full fleet audit (dry-run report only)
hypertide-worker audit --apply          # write hypertide_* columns to DB
hypertide-worker backfill               # one-time backfill of all in-scope domains
hypertide-worker mark-legacy            # set is_legacy=TRUE on unmatched in-scope rows
hypertide-worker inspect-domain <name>  # debug single domain across HT + DB
```

## Environment

| var | required | purpose |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection (`postgresql://user:pass@host:port/db`) |
| `HYPERTIDE_API_KEY` | yes | HT API key with `orders:read` + `subscriptions:cancel` permissions |
| `HYPERTIDE_API_URL` | no | Default `https://backend.hypertide.io`. Override for staging |

## Coolify deployment

Phase 1 mode: operator-invoked + daily cron.

- Build context: `apps/hypertide-worker/`
- Dockerfile: `./Dockerfile`
- Cron: `0 6 * * *` running `hypertide-worker audit --apply`
- For ad-hoc commands: `docker exec <container> hypertide-worker <cmd>`

## Replaces

This app replaces the legacy `hypertide-worker` Coolify app, which polled `inbox_purchase_jobs` (currently empty in production — safe to decommission). The legacy `hypertide_api/worker.py` will be removed in a follow-up commit once the new app is verified live.

## Phase 2+

- Cancellation orchestration (job queue, worker daemon mode, `/api/hypertide/cancellations` endpoints in charm-api)
- Order placement (web UI, two-step charge gating)
- Provisioning watchdog (24-48h SLA)

See [HANDOFF.md](./HANDOFF.md) for operator handoff notes.
