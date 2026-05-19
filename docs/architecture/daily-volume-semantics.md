---
title: Daily Volume & Capacity Semantics
created: 2026-05-18
updated: 2026-05-18
status: canonical
tags: [data-model, daily-volume-snapshots, capacity, warmup, emailbison, sync]
---

# Daily Volume & Capacity Semantics

> **Purpose**: single source of truth for what `daily_volume_snapshots`, the `/api/health/daily-volume/{client_id}` endpoint, and the Infrastructure dashboard chart actually mean. Multiple older docs (migration 041 COMMENTs, [docs/database/schema.md](../database/schema.md), [docs/engine/sync-engine.md](../engine/sync-engine.md), [docs/client-dashboard/CLIENT-DASHBOARD-IMPLEMENTATION-PLAN.md](../client-dashboard/CLIENT-DASHBOARD-IMPLEMENTATION-PLAN.md)) say "daily" when they mean cumulative; this doc supersedes those descriptions.
>
> **TL;DR** —
> 1. `emails_sent` in `daily_volume_snapshots` is **cumulative-to-date**, not a daily delta. Diff consecutive rows to get a daily figure.
> 2. `daily_capacity_available` is the **total daily quota** across active + incubating + warning inboxes. Incubating inboxes' quota is mostly consumed by EmailBison warmup automation, so it OVERSTATES production capacity by ~2× when the workspace has a large warming pipeline.
> 3. **Warmup volume is invisible at daily resolution** — EmailBison only exposes warmup as an aggregate, not per-day. The bars you see on the dashboard chart contain campaign sends only.
> 4. The `capacity_utilization_pct` column is mathematically broken (cumulative / per-day cap). Ignore it. Compute your own from deltas.

## The data flow

```
EmailBison API
  ├─ /campaigns/{id} → campaign.emails_sent  ◀ LIFETIME cumulative per campaign
  └─ /sender-emails → inbox.daily_limit      ◀ EB-throttled cap (scales with warmup_progress)
        │
        ▼ sync_modules/sync_campaigns.py:174
        │ → INSERT into campaign_snapshots with the cumulative value (multiple per day)
        │
        ▼ sync_modules/daily_snapshot.py @ 00:05 UTC daily
        │
        │ 1. emails_sent rollup:
        │    SELECT DISTINCT ON (campaign_id) emails_sent
        │      FROM campaign_snapshots
        │      WHERE DATE(snapshot_timestamp) = $day
        │      ORDER BY campaign_id, snapshot_timestamp DESC
        │    → SUM(emails_sent) across campaigns
        │    → INSERT cumulative-as-of-end-of-day into daily_volume_snapshots.emails_sent
        │
        │ 2. daily_capacity rollup:
        │    SUM(sender_accounts.daily_limit)
        │      FILTERED by inbox_state='live' AND status='Connected'
        │      (excluding ESP-aware disconnects: 48h Microsoft / 24h other)
        │    → INSERT into daily_volume_snapshots.daily_capacity_available
        │
        ▼ api/routes/health.py:2160
        Returns the raw cumulative + capacity values; no transformation.
        │
        ▼ Frontend (app/workspaces/[id]/infrastructure)
        MUST diff consecutive days to compute true daily sends.
```

## What each `daily_volume_snapshots` column actually means

| Column | Type | What's in it |
|---|---|---|
| `emails_sent` | INTEGER | **Cumulative-to-date** total across all campaigns in this workspace as of end of `snapshot_date`. Diff to get daily. |
| `emails_delivered` | INTEGER | Cumulative deliveries (`emails_sent - emails_bounced`). Same diffing rule. |
| `emails_bounced` | INTEGER | Cumulative bounces. Same diffing rule. |
| `emails_complained` | INTEGER | Cumulative complaints. Currently always 0 (not in `campaign_snapshots` yet). |
| `daily_capacity_available` | INTEGER | SUM of `daily_limit` across **all connected live inboxes** (includes incubating). End-of-day snapshot. NOT a delta. |
| `capacity_utilization_pct` | DECIMAL | **BROKEN — DO NOT USE.** Computed as `(cumulative / capacity) * 100`, climbs monotonically past 100%. Capped at 999.99 to fit `NUMERIC(5,2)`. Retained for backward compat. |
| `live_inboxes` | INTEGER | Snapshot count of `sender_accounts.inbox_state='live'`. Includes active + incubating. |
| `incubating_inboxes` | INTEGER | Snapshot count of `inventory_lifecycle_status='incubating'` (warming). |
| `dead_inboxes` | INTEGER | Snapshot count of `inbox_state='dead'`. |
| `kills_that_day` | INTEGER | **TRUE daily delta** — count of inboxes with `killed_at::DATE = snapshot_date`. Only delta-like column on the table. |

## What warmup volume includes (and why we can't show it)

EmailBison has two ways an inbox emits email:

1. **Production campaigns** — emails to leads. Counted per-campaign in `campaign_snapshots.emails_sent`. Visible.
2. **Warmup automation** — inbox-to-inbox reputation emails. Counted per-inbox in EB's warmup stats endpoint but **only as a lifetime aggregate**. EmailBison does not expose per-day warmup volume.

The `sender_accounts.daily_limit` field is the **combined cap** for both kinds of sending. A warming inbox with `daily_limit=20` might emit 12 warmup emails + 8 campaign emails per day; both come out of the same 20-cap. As `warmup_progress` increases, EmailBison raises `daily_limit` toward the fully-warmed maximum (~50/inbox).

**Implication for dashboards**: when you sum `daily_capacity_available` across all connected inboxes, you're summing quota that's split between warmup and production. If most of your inboxes are incubating, most of that quota is going to warmup — invisible in the bars.

Reference: [sync_modules/daily_snapshot.py:375](../../sync_modules/daily_snapshot.py#L375) for the explicit "warmup_emails_sent: not tracked per-sync, EB only gives aggregated."

## Production capacity ≠ total daily quota

Two different ceilings, often conflated in older docs and visualizations:

**Production capacity** — the realistic max for campaign sends.
```
SUM(sender_accounts.daily_limit) FILTERED BY
  inbox_state = 'live'
  AND status = 'Connected'
  AND inventory_lifecycle_status IN ('active', 'incubating')  -- excluded for production
                                                              -- (still in pool but quota → warmup)
  -- → use active + warning only
```
The Infrastructure dashboard renders this as `(active_count + warning_count) × 20` using `DEFAULT_DAILY_LIMIT_PER_INBOX` from `workspace_packages`. This is what bars should be measured against.

**Total daily quota** — the inbox base's outbound capacity including warming.
```
SUM(sender_accounts.daily_limit) FILTERED BY
  inbox_state = 'live'
  AND status = 'Connected'
```
This is what `daily_capacity_available` stores. Useful context ("look at all the warming capacity coming online") but NOT the right denominator for utilization calculations.

For a workspace with 49 active + 90 incubating connected inboxes, total quota ≈ 2,100/day while production capacity ≈ 1,080/day. Measuring sends against the wrong one paints a misleading "we're at 6% utilization" picture instead of the truthful "13%" — and obscures the lever the AE actually has (graduate incubating inboxes to active to grow the production line).

## How consumers should read the data

### To compute "how many emails were sent on day N"

```sql
SELECT today.emails_sent - yesterday.emails_sent AS daily_sends
FROM daily_volume_snapshots today
LEFT JOIN daily_volume_snapshots yesterday
  ON yesterday.workspace_id = today.workspace_id
  AND yesterday.snapshot_date = today.snapshot_date - INTERVAL '1 day'
WHERE today.workspace_id = $1
  AND today.snapshot_date = $2;
-- Apply GREATEST(0, ...) to guard against negative deltas from backfill ordering.
```

### To compute realistic production utilization

```sql
WITH daily AS (
  SELECT
    today.snapshot_date,
    GREATEST(0, today.emails_sent - yesterday.emails_sent) AS daily_sends,
    -- Production capacity requires joining current inventory_overview,
    -- which is NOT stored per-day. Use today's active+warning count as a proxy
    -- for recent days, or accept some imprecision in historical math.
    20::INTEGER * (today.live_inboxes - today.incubating_inboxes) AS approx_production_capacity
  FROM daily_volume_snapshots today
  LEFT JOIN daily_volume_snapshots yesterday
    ON yesterday.workspace_id = today.workspace_id
    AND yesterday.snapshot_date = today.snapshot_date - INTERVAL '1 day'
  WHERE today.workspace_id = $1
)
SELECT
  snapshot_date,
  daily_sends,
  approx_production_capacity,
  CASE WHEN approx_production_capacity > 0
    THEN (daily_sends::DECIMAL / approx_production_capacity) * 100
    ELSE NULL END AS production_utilization_pct
FROM daily
ORDER BY snapshot_date;
```

### What NOT to do

- ❌ Use `daily_volume_snapshots.emails_sent` directly as a daily figure.
- ❌ Use `daily_volume_snapshots.capacity_utilization_pct` for anything.
- ❌ Sum `emails_sent` across days to get a period total. It double-counts. Use `last - first` instead.
- ❌ Compare bar values to `daily_capacity_available` as if it's a production ceiling.

## What's broken that should be fixed at the source

Frontend currently corrects for these by transforming on read. The cleaner fix is in the snapshot writer. Listing as backend follow-ups:

1. **Store daily deltas in `daily_volume_snapshots`, not cumulative.** [sync_modules/daily_snapshot.py:120-137](../../sync_modules/daily_snapshot.py#L120) should subtract the previous day's cumulative before INSERT. Then run [scripts/backfill_daily_volume.py](../../scripts/backfill_daily_volume.py) to convert existing historical rows. Migration 041's column comment (now corrected by 133) can drop the "cumulative" caveat once this lands.

2. **Add `production_capacity_available` column.** A second SUM filtered to active + warning lifecycle only. Lets dashboards stop computing it themselves from `inventory_overview` (which only has today's number, not history).

3. **Add `warmup_emails_sent_estimate` column** (optional). Even if EmailBison doesn't expose per-day warmup, we can estimate: `(incubating_inboxes × avg_daily_limit_for_incubating) - production_sends_from_incubating`. Lets the chart stack warmup as a faint band beneath production sends.

4. **Drop `capacity_utilization_pct` column.** It's broken by design. Better to remove than to have it sit there as a footgun.

These are not blocking the Infrastructure dashboard demo — the frontend now does the corrections client-side. But every additional consumer (agents reading this data, future reports) has to repeat the same correction code, so getting the source right pays compounding dividends.

## Cross-references

- Schema: [migrations/041_daily_volume_snapshots.sql](../../migrations/041_daily_volume_snapshots.sql), [migrations/137_daily_volume_semantic_comments.sql](../../migrations/137_daily_volume_semantic_comments.sql)
- Sync: [sync_modules/daily_snapshot.py](../../sync_modules/daily_snapshot.py), [sync_modules/sync_campaigns.py](../../sync_modules/sync_campaigns.py)
- API: [api/routes/health.py:2113-2242](../../api/routes/health.py#L2113) — `get_daily_volume_history`
- Frontend: [charm-email-os/app/workspaces/[id]/infrastructure/page.tsx](../../charm-email-os/app/workspaces/[id]/infrastructure/page.tsx) — applies the cumulative→delta correction + production-vs-total capacity split
- ADR: [docs/adr/adr-006-tagging-kill-overhaul-2026-04-27.md §3](../adr/adr-006-tagging-kill-overhaul-2026-04-27.md) — documents the `capacity_utilization_pct` overflow symptom
- Earlier (correct) note: [docs/audits/2026-05-18-selery-bounce-deep-dive.md:399](../audits/2026-05-18-selery-bounce-deep-dive.md#L399)
- Capacity by warmup-progress (different code path): [api/routes/health.py:1789-1792](../../api/routes/health.py#L1789) — `get_emailbison_capacity` uses `warmup_progress / 100 × max_daily=50`. This is a separate live-from-EB endpoint, not the snapshot reader.
