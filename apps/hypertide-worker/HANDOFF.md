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

## How the audit runs (freshness-timer model)

The container CMD is a **24h timer loop**, not `sleep infinity`. Unlike
`apps/eod-reapply` / `apps/incubation-watcher` (operator tools), this app's
job is keeping the DB mirror of Hypertide state current — background
freshness. So the container:

```
run `hypertide-worker audit --apply`  ->  sleep 24h  ->  repeat
```

- First iteration runs immediately on container start (a deploy = instant fresh audit)
- A crashed audit does NOT crashloop — the loop sleeps 24h then retries
- `audit --apply` is idempotent and read-only toward Hypertide (only UPDATEs
  our own `hypertide_*` columns; never INSERTs; never calls HT write APIs)

This is **not** the Phase 2 job-queue daemon. Phase 2 replaces this loop
with a process that claims rows from `hypertide_jobs`.

### Optional: precise scheduling via Coolify scheduled task

The 24h loop runs daily relative to *container start time*, not a wall-clock
hour. If you want the audit at exactly 06:00 UTC:

1. Coolify -> hypertide-worker -> Scheduled Tasks -> Add new
2. Name: `daily_audit`, Command: `hypertide-worker audit --apply`, Frequency: `0 6 * * *`
3. Then change the Dockerfile CMD back to `["sleep", "infinity"]` so the
   timer loop and the scheduled task don't both run.

Not required — the timer loop is sufficient for "daily fresh." This is only
for operators who want wall-clock precision.

## Daily operations

Check audit health:

```sql
SELECT (metadata->>'parity_pct')                       AS parity_pct,
       records_updated,
       (metadata->>'drift_ht_cancelled_inboxes_connected') AS drift_cancelled_connected,
       (metadata->>'ht_incoming_count')                AS incoming,
       (metadata->>'ht_friends_and_family')            AS friends_family,
       started_at
FROM sync_audit_log
WHERE sync_type = 'hypertide_audit'
ORDER BY created_at DESC
LIMIT 7;
```

What the numbers mean:
- **parity_pct** — % of our managed domains linked to an HT record. Should
  trend up as backfill + ongoing matching closes gaps. A *drop* means new
  DB rows appeared without HT matches (investigate) or HT purged records.
- **drift_cancelled_connected** — HT cancelled the sub but EmailBison still
  shows connected inboxes. Should trend toward zero as EB's reaper catches
  up. A persistent high number means inboxes are sending through dead
  tenants — operator should disable them in EB.
- **incoming** — HT records with status Todo/In progress and no DB row yet.
  Domains we ordered, still in the 24-48h provisioning window before
  EmailBison sees their inboxes. Expected to be non-zero when actively
  ordering; should clear as inboxes land.
- **friends_family** — HT records (status Done) with no DB row. Vendor-side
  subscriptions outside our GTM work. Informational; we deliberately do not
  mirror these.

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
