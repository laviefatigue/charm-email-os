# Database Documentation

Comprehensive documentation for the Charm Email OS database schema, migrations, and data management.

---

## Overview

**Database:** PostgreSQL 15.8+
**Schema:** public
**Tables:** 40+ tables across inbox management, domain health, campaigns, and capacity planning
**Migrations:** 42 applied (as of 2026-02-23)

---

## Key Documents

### Schema & Structure
- **[schema.md](./schema.md)** - Complete database schema documentation
- **[migrations.md](./migrations.md)** - Migration history and changelog
- **[index.md](./index.md)** - Quick reference index

### Data Management
- **[backfill-analysis.md](./backfill-analysis.md)** - ⭐ **NEW: Data availability and backfill requirements**
  - Current state: 95% schema complete, 70% data populated
  - Critical gaps: RBL data, daily snapshots, campaign burns
  - Backfill priorities and SQL scripts
  - Time to full data: 13-19 hours

---

## Quick Reference

### Core Tables

#### Inbox Management
- `sender_accounts` - Primary inbox table (✅ data exists)
- `kill_queue` - Kill safety window (✅ data exists)
- `kill_trigger_events` - Audit log (✅ data exists)
- `inbox_health_snapshots` - Health history (✅ data exists)
- `sender_warmup_snapshots` - Warmup tracking (✅ data exists)

#### Domain Health
- `domains` - Domain tracking (✅ data exists, ⚠️ RBL data missing)
- `rbl_check_logs` - Blacklist checks (❌ empty - worker not running)

#### Campaigns
- `campaigns` - Campaign master (✅ data exists)
- `campaign_inboxes` - Inbox assignments (✅ data exists)
- `campaign_burn_events` - Death attribution (❌ empty - logic missing)

#### Time-Series
- `daily_volume_snapshots` - Daily aggregates (❌ empty - just created)
- `inbox_health_snapshots` - Health trends (✅ data exists)

#### Capacity Planning
- `client_subscriptions` - Hypertide packages (⚠️ needs manual entry)
- `v_domain_capacity` - Domain capacity view (✅ functional)
- `v_client_capacity` - Client capacity view (✅ functional)
- `v_hypertide_order_queue` - Orders needed (✅ functional)

---

## Data Availability Status

### ✅ Excellent (Live Data)
- Sender accounts (inboxes)
- Kill tracking system
- Domain basic info
- Campaign data
- Health snapshots
- Warmup snapshots

### ⚠️ Partial (Needs Enhancement)
- Domain RBL status (schema exists, worker missing)
- Client subscriptions (manual entry needed)
- List segments (minimal data)

### ❌ Empty (Needs Implementation)
- RBL check logs (no worker)
- Campaign burn events (no logic)
- Daily volume snapshots (new table, needs backfill)

---

## Critical Actions Needed

### HIGH Priority (This Week)

1. **Backfill Daily Volume Snapshots** (1 hour)
   ```sql
   -- Run once to backfill last 30 days
   SELECT snapshot_all_workspaces(date)
   FROM generate_series(
       CURRENT_DATE - INTERVAL '30 days',
       CURRENT_DATE - INTERVAL '1 day',
       INTERVAL '1 day'
   ) AS date;
   ```

2. **Implement RBL Checking Worker** (8-12 hours)
   - See: `/docs/features/rbl-implementation-guide.md`
   - Check Spamhaus, Barracuda, SpamCop
   - Update `rbl_check_logs` and `domains.latest_blacklist_count`

3. **Add Daily Snapshot to Cron** (30 min)
   ```python
   # In emailbison_sync_worker.py
   @schedule.every().day.at("00:05")
   def daily_snapshot():
       yesterday = (datetime.now() - timedelta(days=1)).date()
       with get_db_connection() as conn:
           conn.execute("SELECT snapshot_all_workspaces(%s)", (yesterday,))
   ```

### MEDIUM Priority (Next 2 Weeks)

4. **Campaign Burn Tracking** (4-6 hours)
   - Modify `kill_processor.py` to populate `campaign_burn_events`
   - Link inbox deaths to campaigns
   - Enable kill trigger breakdown chart

5. **Client Subscription Data Entry** (1-2 hours)
   - Manually populate `client_subscriptions` table
   - Enables accurate capacity gap analysis

---

## Connection Configuration

Environment variables (set in `.env` or deployment config):
```bash
POSTGRES_HOST=charm-postgres
POSTGRES_PORT=5432
POSTGRES_DB=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secret>
POSTGRES_SCHEMA=public
```

Configuration loaded via: `/api/config.py`

---

## Sync Workers

### EmailBison Sync Worker
- **File:** `/emailbison_sync_worker.py`
- **Status:** ✅ Running
- **Frequency:** Every 15-30 minutes
- **Syncs:** Inboxes, domains, campaigns, health scores, bounces, warmup status

### Health Check Worker
- **File:** `/sync_modules/health_checks.py`
- **Status:** ✅ Running
- **Frequency:** Every sync cycle
- **Does:** Kill trigger detection, warning levels, queue management

### Kill Processor
- **File:** `/sync_modules/kill_processor.py`
- **Status:** ✅ Running (needs enhancement)
- **Frequency:** Every sync cycle
- **Does:** Process kill queue, tag inboxes, update states
- **TODO:** Add campaign burn tracking

### RBL Checker
- **Status:** ❌ NOT IMPLEMENTED
- **Priority:** HIGH
- **See:** `/docs/features/rbl-implementation-guide.md`

### Daily Snapshot Scheduler
- **Status:** ❌ NOT SCHEDULED
- **Priority:** HIGH
- **TODO:** Add to sync worker cron

---

## Migration Guidelines

### Creating New Migrations

1. **Naming Convention:**
   ```
   XXX_descriptive_name.sql
   ```
   Where XXX is next sequential number (e.g., `043_domain_rotation_tables.sql`)

2. **Template:**
   ```sql
   -- Migration XXX: Description
   -- Created: YYYY-MM-DD
   -- Purpose: What this migration does

   -- =============================================================
   -- 1. CREATE TABLES
   -- =============================================================

   CREATE TABLE IF NOT EXISTS table_name (...);

   -- =============================================================
   -- 2. INDEXES
   -- =============================================================

   CREATE INDEX IF NOT EXISTS idx_name ON table_name(...);

   -- =============================================================
   -- 3. COMMENTS
   -- =============================================================

   COMMENT ON TABLE table_name IS 'Description';

   -- =============================================================
   -- 4. VERIFICATION
   -- =============================================================

   SELECT 'Migration XXX complete' AS status;
   ```

3. **Testing:**
   - Test locally first
   - Run in transaction to verify
   - Check for conflicts with existing schema
   - Document in migrations.md

---

## Performance Notes

### Query Performance
Most queries are fast (<100ms):
- Inbox health queries: ~50ms
- Domain capacity views: ~100ms
- Dashboard summary: ~200ms

### Indexes
- ✅ All primary keys indexed
- ✅ Foreign keys indexed
- ✅ Workspace queries optimized
- ✅ Date range queries optimized

### Potential Bottlenecks
- Daily snapshot function on large workspaces (>10K inboxes)
- Campaign burn aggregation across time (needs testing with data)

---

## Related Documentation

### Infrastructure
- **[hypertide-rotation-policy.md](../infrastructure/hypertide-rotation-policy.md)** - Domain rotation constraints
- **[coolify.md](../infrastructure/coolify.md)** - Deployment configuration

### Features
- **[health-monitoring.md](../features/health-monitoring.md)** - Health V3 system
- **[hypertide-health-v3-impact.md](../features/hypertide-health-v3-impact.md)** - System integration analysis
- **[rbl-implementation-guide.md](../features/rbl-implementation-guide.md)** - RBL worker implementation
- **[v3-compliance-gap-analysis.md](../features/v3-compliance-gap-analysis.md)** - V3 compliance status

---

## Troubleshooting

### Empty Dashboard Charts
**Symptom:** Sending Capacity Chart shows "No data"
**Cause:** `daily_volume_snapshots` table is empty
**Fix:** Run backfill script (see backfill-analysis.md)

### Domain Blacklist Always Zero
**Symptom:** Dashboard shows "0 flagged domains" always
**Cause:** RBL checking worker not running
**Fix:** Implement RBL worker (see rbl-implementation-guide.md)

### Kill Trigger Breakdown Shows Zeros
**Symptom:** Kill breakdown API returns all zeros
**Cause:** `campaign_burn_events` table is empty
**Fix:** Enhance kill_processor to track campaign burns

### Missing Capacity Data
**Symptom:** "Orders needed" shows NULL
**Cause:** `client_subscriptions` not populated
**Fix:** Manual data entry for each client's Hypertide packages

---

## Contact

For database questions or migration issues, refer to:
- Database schema documentation (schema.md)
- Migration history (migrations.md)
- Backfill analysis (backfill-analysis.md)

---

**Last Updated:** 2026-02-23
**Version:** 1.0
**Migrations:** 42 applied
**Next Actions:** HIGH priority backfill tasks
