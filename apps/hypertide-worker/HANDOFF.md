# hypertide-worker — Operator Handoff

> Phase 1 lives. Step 5 of [docs/plans/hypertide-data-model-and-change-tracking.md](../../docs/plans/hypertide-data-model-and-change-tracking.md) shipped 2026-05-18 — ingest is now subscription-keyed via `client_hypertide_subscriptions`. Phase 2+ (cancellation, order placement, web UI) deferred per [docs/architecture/hypertide-service.md](../../docs/architecture/hypertide-service.md).

## What this service owns

- **Subscription-keyed binding (chs sync).** Every HT subscription in `/orders/active` gets a row in `client_hypertide_subscriptions` per audit pass. Last-seen-at touched; first-sight subs auto-classified by `sending_tool` per DECISION 5 (revised): Email Bison / Instantly.ai → `client_status='client'`, Smartlead.ai / unknown → `friends_and_family`. New `clients` rows are created on demand for unknown HT subscriptions.
- **Change tracking (step 9 / DECISION 4).** After chs sync, detects subs that disappeared from `/orders/active` since the prior audit and writes `hypertide_status_events` rows (`event_type='cancelled'`). Each cancellation carries a verdict joining `domains.qualifies_for_cancellation_*` within the last 90 days: `justified` (we burned it first), `unjustified` (HT/operator acted out-of-band — flag for operator review), `pending` (no domain-level evidence yet, common for Instantly-only clients). Reappearances written as `event_type='reappeared'`.
- **Source of truth for HT state in our DB.** Populates `domains.hypertide_*` columns from HT API (per-record snapshot UPDATE; uses `domain_name` join for the record-to-domain link).
- **Drift detection.** Logs gaps between HT (`/orders/active`, `verify-revert`) and `domains` table to `sync_audit_log`. Also detects HT-cancelled-but-EB-still-connected (the money-leaking case).
- **Legacy classification.** Flags domains in HT-managed workspaces with no matching HT record as `is_legacy=TRUE` (semantic = "acquired outside HT pipeline", per Concern C in the plan).
- **New domain row creation.** Only via explicit `backfill --onboard-workspace 'X'` operator flag. Default audit does NOT auto-INSERT domains.

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
       (metadata->>'ht_no_db_row')                     AS ht_no_db_row,
       (metadata->'chs_sync'->>'subs_seen')            AS subs_seen,
       (metadata->'chs_sync'->>'new_clients_client_status') AS new_client_subs,
       (metadata->'chs_sync'->>'new_clients_fnf')      AS new_fnf_subs,
       (metadata->'change_detector'->>'cancelled_events_written') AS new_cancellations,
       (metadata->'change_detector'->>'verdict_unjustified')      AS unjustified_cancellations,
       (metadata->'change_detector'->>'reappeared_events_written') AS reappearances,
       started_at
FROM sync_audit_log
WHERE sync_type = 'hypertide_audit'
ORDER BY created_at DESC
LIMIT 7;
```

Tail of recent unjustified cancellations (where HT or operator cancelled without our kill-trigger firing first — worth a review):

```sql
SELECT e.event_at, c.name AS client_name, e.subscription_id,
       e.verdict, e.affected_domain_count, e.notes
FROM hypertide_status_events e
JOIN clients c ON c.id = e.client_id
WHERE e.event_type = 'cancelled' AND e.verdict = 'unjustified'
ORDER BY e.event_at DESC
LIMIT 20;
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
- **ht_no_db_row** — per-record count of HT orders (status Done) whose domain
  isn't in our `domains` table. Includes both F&F and Instantly-extraction-pending.
  Subscription-level classification is on the `chs.client_status` column —
  this counter is per-record diagnostic only.
- **new_client_subs / new_fnf_subs** — newly-discovered HT subscriptions
  classified into `clients` rows this audit (DECISION 5 dispatch). A non-zero
  number on a steady-state audit means an HT sub got created since the prior
  pass. Operator should sanity-check `clients` for the auto-created row and
  promote/demote `client_status` if the auto-classification is wrong.

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
