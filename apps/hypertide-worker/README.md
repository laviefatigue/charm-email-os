# hypertide-worker

Hypertide reconciliation service. Single source of truth for HT-side state and the bridge into our `domains` table.

**See:** [docs/architecture/hypertide-service.md](../../docs/architecture/hypertide-service.md) for the architectural plan and phased roadmap. [docs/integrations/hypertide-api.md](../../docs/integrations/hypertide-api.md) for HT API specifics. [docs/plans/hypertide-data-model-and-change-tracking.md](../../docs/plans/hypertide-data-model-and-change-tracking.md) for the 2026-05 data-model rework (chs binding, change tracking, verdict columns) — superseded the original parity model.

## Current scope (Phase 1 + data-model rework, 2026-05-19)

Read-only HT data collection + subscription-keyed binding + change tracking. Pulls `/orders/active` + `verify-revert` per audit pass and:

1. **chs sync** (`chs_sync.py`) — for every HT sub, ensures a `client_hypertide_subscriptions` row exists. Touches `last_seen_at` for existing; first-sight subs get auto-classified by `sending_tool` (Email Bison / Instantly.ai → `client_status='client'`, Smartlead / unknown → `friends_and_family`) and a new `clients` row created on demand.
2. **change detection** (`change_detector.py`) — chs rows whose `last_seen_at` predates the current audit's start = subs that disappeared from `/orders/active`. INSERTs a `hypertide_status_events` row with verdict joining `domains.qualifies_for_cancellation_*` (set by kill-trigger evaluator per migration 125): `justified` (we burned it first), `unjustified` (HT/operator acted out-of-band), `pending` (no kill evidence).
3. **per-record snapshot** (`audit.py`) — matches HT records to `domains` rows by `domain_name`, populates `hypertide_*` columns. Drift detection (HT cancelled but EB still connected) surfaced.

**No writes to Hypertide.** Cancel/order flows are Phase 2/3.

## Module layout

```
src/hypertide_worker/
├── ht_client.py        # async HT API client (httpx, no curl)
├── classifier.py       # HT-record decision tree (live/cancelled/scheduled/drift)
├── chs_sync.py         # subscription-keyed binding + first-sync auto-classification
├── change_detector.py  # cancellation / reappearance detection per audit pass
├── audit.py            # orchestration: pull HT → chs_sync → change_detector → per-record UPDATEs
├── backfill.py         # is_legacy flagging + gated --onboard-workspace INSERT
├── cli.py              # audit | backfill | inspect-domain | mark-legacy
└── jobs/audit_drift.py # cron-entrypoint wrapper around run_audit(apply=True)
```

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
