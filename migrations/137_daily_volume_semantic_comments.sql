-- Migration 137: Correct the COMMENT statements on daily_volume_snapshots
-- (renumbered from 133 to clear collision with master's 133_drop_legacy_ht_columns.sql
--  and 133_v_campaigns_union_view.sql)
--
-- Why this exists
-- ───────────────
-- The original 041 COMMENTs say emails_sent is "Total emails sent across all
-- campaigns in this workspace on this date" — but the actual ingest path stores
-- CUMULATIVE-AS-OF-END-OF-DAY values, not daily deltas. This drift propagated to
-- docs/database/schema.md, docs/engine/sync-engine.md, and the client dashboard
-- plan; consumers built broken math (e.g. capacity_utilization_pct of 102% that
-- overflowed NUMERIC(5,2) — see adr-006 §3) on top of the wrong contract.
--
-- This migration rewrites the COMMENTs so future maintainers and any LLM/tool
-- reading the schema get the truth. No data change. No column change. Just text.
--
-- Canonical reference for the full semantics:
--   docs/architecture/daily-volume-semantics.md (lands in the same PR as this migration)
--
-- Verified facts behind the corrected comments:
--   1. sync_modules/sync_campaigns.py:174 writes campaign_snapshots.emails_sent as
--      EmailBison's per-campaign lifetime cumulative.
--   2. sync_modules/daily_snapshot.py:118-137 picks the LATEST snapshot per
--      campaign per day, SUMs across campaigns, stores result as
--      daily_volume_snapshots.emails_sent — so the column is cumulative-to-date,
--      not a daily delta.
--   3. sync_modules/daily_snapshot.py:94 sums daily_limit FILTERED by
--      inbox_state='live' AND status='Connected' — includes incubating inboxes
--      whose daily_limit is largely consumed by EmailBison's warmup automation,
--      not by production campaigns.
--   4. sync_modules/daily_snapshot.py:375 documents that warmup_emails_sent is
--      NOT tracked per-sync — EmailBison only exposes warmup volume as an
--      aggregate. Per-day warmup volume cannot be reconstructed from CharmDB.
--   5. api/routes/health.py:2160 returns the raw cumulative value without
--      computing a delta — every consumer must compute deltas themselves.

COMMENT ON TABLE daily_volume_snapshots IS
    'Daily end-of-day snapshot of cumulative campaign sends + inbox capacity per workspace. '
    'NOTE: emails_sent, emails_delivered, emails_bounced, emails_complained are '
    'CUMULATIVE-TO-DATE values from EmailBison''s per-campaign lifetime counters, '
    'NOT daily deltas. To get a daily figure, diff consecutive days. '
    'Warmup volume is NOT captured here (EmailBison only exposes warmup as an '
    'aggregate, not per-day) — see warmup_snapshots for incubating-inbox tracking. '
    'Populated by sync_modules/daily_snapshot.py at 00:05 UTC daily. '
    'Canonical reference: docs/architecture/daily-volume-semantics.md.';

COMMENT ON COLUMN daily_volume_snapshots.emails_sent IS
    'CUMULATIVE-TO-DATE total across all campaigns in this workspace as of end of '
    'snapshot_date. Computed by SUM(latest snapshot per campaign per day) where the '
    'per-campaign value is EmailBison''s lifetime emails_sent counter. To derive a '
    '"sent on this day" figure, diff today''s value against the previous day''s row. '
    'Counts campaign sends only — warmup volume is invisible at daily resolution.';

COMMENT ON COLUMN daily_volume_snapshots.emails_delivered IS
    'CUMULATIVE-TO-DATE deliveries (emails_sent - emails_bounced). Same diffing '
    'rule as emails_sent applies.';

COMMENT ON COLUMN daily_volume_snapshots.emails_bounced IS
    'CUMULATIVE-TO-DATE bounces. Same diffing rule as emails_sent applies.';

COMMENT ON COLUMN daily_volume_snapshots.emails_complained IS
    'CUMULATIVE-TO-DATE complaints. Not tracked in campaign_snapshots today, '
    'persisted as 0. Reserved for when EmailBison exposes complaint volume per campaign.';

COMMENT ON COLUMN daily_volume_snapshots.daily_capacity_available IS
    'SUM(sender_accounts.daily_limit) FILTERED by inbox_state=''live'' AND status=''Connected'' '
    'as of end of snapshot_date. This includes incubating inboxes whose daily_limit is '
    'largely consumed by EmailBison''s warmup automation — so it OVERSTATES production '
    'capacity. For a production-only ceiling use lifecycle_status=''active'' + ''warning'' '
    'instead. Disconnected inboxes are excluded with an ESP-aware threshold '
    '(48h Microsoft, 24h other) per sync_modules/daily_snapshot.py:87-89.';

COMMENT ON COLUMN daily_volume_snapshots.capacity_utilization_pct IS
    'CAUTION: computed at snapshot time as (cumulative emails_sent / daily_capacity) * 100. '
    'This is MATHEMATICALLY MEANINGLESS because emails_sent is cumulative-to-date but '
    'daily_capacity is a per-day cap — values grow monotonically and routinely exceed 100%. '
    'Snapshot writer caps at 999.99 to fit NUMERIC(5,2). Consumers must compute their own '
    'utilization from day-over-day deltas. This column is retained for backward compat '
    'but operator dashboards should ignore it.';

COMMENT ON COLUMN daily_volume_snapshots.live_inboxes IS
    'Snapshot count of sender_accounts with inbox_state=''live'' for this workspace at '
    'end of snapshot_date. Includes both active and incubating lifecycle states.';

COMMENT ON COLUMN daily_volume_snapshots.incubating_inboxes IS
    'Snapshot count of sender_accounts with inventory_lifecycle_status=''incubating'' '
    '(warming up) for this workspace at end of snapshot_date.';

COMMENT ON COLUMN daily_volume_snapshots.dead_inboxes IS
    'Snapshot count of sender_accounts with inbox_state=''dead'' for this workspace at '
    'end of snapshot_date.';

COMMENT ON COLUMN daily_volume_snapshots.kills_that_day IS
    'Count of sender_accounts with killed_at::DATE = snapshot_date. This IS a daily '
    'delta (unlike emails_sent) because killed_at is a single timestamp per inbox.';

-- Function-level comment too, so anyone running snapshot_daily_volume() manually
-- understands what they're producing.
COMMENT ON FUNCTION snapshot_daily_volume IS
    'Creates/updates a daily_volume_snapshots row for one workspace. emails_sent in '
    'the output is CUMULATIVE-TO-DATE, not a daily delta — see column comments. '
    'NOTE: the SQL body declared in migration 041 hardcodes v_emails_sent := 0; the '
    'real production population path is sync_modules/daily_snapshot.py, which '
    'reads campaign_snapshots and stores cumulative values.';
