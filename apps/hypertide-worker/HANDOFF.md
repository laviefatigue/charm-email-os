# hypertide-worker — Operator Handoff

> Phase 1 lives. Phase 2+ (cancellation, order placement, web UI) deferred per [docs/architecture/hypertide-service.md](../../docs/architecture/hypertide-service.md).

## What this service owns

- **Source of truth for HT state in our DB.** Populates `domains.hypertide_*` columns from HT API.
- **Drift detection.** Logs gaps between HT (`/orders/active`, `verify-revert`) and `domains` table to `sync_audit_log`.
- **Legacy classification.** Flags domains in HT-managed workspaces with no matching HT record as `is_legacy=TRUE`.
- **New domain row creation.** When HT shows a record we don't have, INSERTs a new `domains` row with `domain_source='hypertide'`.

## What this service does NOT own (Phase 2+)

- Cancelling HT subscriptions
- Placing new HT orders
- Charging payment
- Provisioning SLA enforcement

## Daily operations

The cron-mode audit runs at 06:00 UTC daily. Check by:

```sql
SELECT * FROM sync_audit_log
WHERE sync_type = 'hypertide_audit'
ORDER BY created_at DESC
LIMIT 7;
```

`metadata->'drift_count'` should be near-zero in steady state. Spikes indicate either:
- HT-side changes we should investigate (cancellations executing, support staff cleanup)
- DB-side rows getting un-bound from their HT records (rare; needs investigation)

## Manual interventions

**A workspace was added that has HT-managed domains:**
1. Confirm `workspaces.manages_via_hypertide = TRUE` for it (default)
2. Run `hypertide-worker backfill` to bind matching domains
3. Verify via `hypertide-worker audit` — drift count should drop

**A workspace shouldn't be HT-tracked (friend occupancy):**
```sql
UPDATE workspaces SET manages_via_hypertide = FALSE WHERE workspace_name = 'X';
```
Subsequent audits skip it.

**A specific domain shows wrong state:**
```bash
hypertide-worker inspect-domain example.com
```
Shows DB row + matching HT record + `verify-revert` cancellation state side-by-side.

## Decommissioning the legacy worker

The previous `hypertide-worker` (Coolify app) polled `inbox_purchase_jobs`. That table is currently empty in production. Cutover plan:

1. Deploy this new app
2. Verify daily cron runs successfully for 24h
3. Stop legacy app in Coolify
4. After 7 days of clean operation: delete legacy app + `hypertide_api/worker.py` from repo

## Known limitations (Phase 1)

- `hypertide_record_id` for existing rows is set by domain-name match. Where domain_name is ambiguous (rare — `domain_name` is globally unique per migration 092), the first-found-by-API-order wins.
- Workspace assignment for newly-INSERTed rows uses domain-name pattern matching + HT `forwardingDomain` heuristic. Ambiguous cases set `workspace_id = NULL` and require operator review (see "Manual interventions").
- No alerting yet. Drift visible in `sync_audit_log` only. Slack alerting comes in Phase 2.

## Escalation

For production issues with this service, check `sync_audit_log` first. If the worker can't reach HT, `error_message` will explain. If it's running but data looks wrong, check the `metadata` JSONB on the most recent row — it includes per-workspace breakdowns.
