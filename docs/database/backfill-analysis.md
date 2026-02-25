# Database Schema & Backfill Analysis

**Document ID:** DB-BACKFILL-001
**Date:** 2026-02-23
**Purpose:** Analyze database schema, data availability, and backfill requirements for Health V3 and client dashboard

---

## Executive Summary

**Database Status:** 42 migrations applied, comprehensive schema in place
**Data Availability:** Mixed - some tables have data, some are schema-only
**Backfill Priority:** HIGH - Several critical tables need data population

### Key Findings

1. **Schema is 95% complete** - All tables exist, well-documented
2. **Data gaps exist** - Many tables are schema-only, awaiting backfill
3. **Daily snapshots table just created** (Migration 041, 2026-02-23)
4. **RBL checking schema exists** but worker not running
5. **Campaign burn tracking ready** but needs population

---

## Database Architecture

### Connection Information
- **Host:** charm-postgres (production) / localhost (dev)
- **Port:** 5432
- **Database:** postgres
- **Schema:** public
- **Version:** PostgreSQL 15.8+

### Configuration
Located in `/charm-email-os/api/config.py`:
```python
POSTGRES_HOST: str (from env)
POSTGRES_PORT: int = 5432
POSTGRES_DB: str = "postgres"
POSTGRES_USER: str (from env)
POSTGRES_PASSWORD: str (from env)
POSTGRES_SCHEMA: str = "public"
```

---

## Core Tables Overview

### 1. Inbox Management

#### `sender_accounts` (Primary inbox table)
**Status:** ✅ DATA EXISTS (populated by EmailBison sync)
**Last Updated:** Continuous (every 15-30 min via sync worker)

**Key Columns:**
```sql
-- Identity
id UUID PRIMARY KEY
email VARCHAR(255) UNIQUE
domain VARCHAR(255)
workspace_id UUID → workspaces(id)

-- Health & Status
health_score INTEGER (0-100, calculated locally)
inbox_state VARCHAR(50) ('live', 'dead')
inventory_lifecycle_status VARCHAR(50) ('incubating', 'active', 'deployed', 'reserve')

-- Bounce Tracking
hard_bounces_24h INTEGER
hard_bounces_7d INTEGER
hard_blocked_24h INTEGER (550 5.7.x - reputation issues)
hard_unknown_24h INTEGER (550 5.1.1 - bad addresses)
bounce_rate_7d DECIMAL(5,2)

-- Warmup Tracking
warmup_enabled BOOLEAN
warmup_started_at TIMESTAMP
warmup_stopped_at TIMESTAMP
sending_started_at TIMESTAMP

-- Kill Tracking
killed_at TIMESTAMP
death_reason TEXT

-- All-time Metrics (from EmailBison)
emails_sent_all_time INTEGER
replies_all_time INTEGER
bounces_all_time INTEGER
complaints_lifetime INTEGER (1 = instant kill)
daily_limit INTEGER

-- Timestamps
created_at, updated_at, first_seen_at, last_sync_at
```

**Data Quality:**
- ✅ Synced from EmailBison every 15-30 minutes
- ✅ Health scores calculated locally
- ✅ Kill triggers detected and tracked
- ✅ Bounce counters maintained

---

#### `kill_queue` (Kill safety window)
**Status:** ✅ DATA EXISTS (populated by health checks)
**Purpose:** 24-hour safety window before inbox killing

**Key Columns:**
```sql
id UUID PRIMARY KEY
inbox_id UUID → sender_accounts(id)
workspace_id UUID
trigger_type VARCHAR(100) (e.g., 'spam_complaint', 'hard_bounces_24h')
trigger_reason TEXT
status VARCHAR(50) ('pending', 'flagged', 'cancelled')
detected_at TIMESTAMP
flagged_at TIMESTAMP
```

**Flow:**
1. Health check detects kill trigger → Insert with status='pending'
2. 24 hours pass (safety window)
3. Kill processor tags inbox in EmailBison → Update status='flagged'
4. Local `inbox_state` set to 'dead'

**Data Quality:**
- ✅ Continuously populated by `health_checks.py`
- ✅ Processed by `kill_processor.py`

---

#### `kill_trigger_events` (Audit log)
**Status:** ✅ DATA EXISTS
**Purpose:** Permanent audit trail of all kill trigger detections

**Key Columns:**
```sql
id UUID PRIMARY KEY
inbox_id UUID
workspace_id UUID
trigger_type VARCHAR(100)
trigger_details JSONB
detected_at TIMESTAMP
```

**Data Quality:**
- ✅ Every kill trigger detection logged
- ✅ Permanent record (never deleted)

---

### 2. Domain Management

#### `domains` (Domain health tracking)
**Status:** ✅ DATA EXISTS (populated by sync worker)

**Key Columns:**
```sql
domain VARCHAR(255) PRIMARY KEY
workspace_id UUID
provider VARCHAR(50) ('microsoft', 'google')
status VARCHAR(50) ('active', 'flagged', 'dead', 'pending_dns')
phase VARCHAR(50) ('warming', 'ramping', 'establishing', 'peak', 'monitoring', 'rotation')

-- Health Metrics
total_inboxes INTEGER
active_inbox_count INTEGER (total - dead)
dead_inbox_count INTEGER
health_score INTEGER

-- RBL Tracking
latest_blacklist_count INTEGER (from rbl_check_logs)
is_clean BOOLEAN
last_checked_at TIMESTAMP

-- Capacity
daily_capacity INTEGER (calculated: active_inboxes × emails/day)
expected_capacity INTEGER (from Hypertide specs)

-- Domain Age
domain_age_days INTEGER
created_at, purchased_at
```

**Data Quality:**
- ✅ Basic info populated (domain, provider, inbox counts)
- ⚠️ RBL fields exist but **worker not running** (latest_blacklist_count always 0)
- ✅ Capacity calculations working

---

#### `rbl_check_logs` (Blacklist check results)
**Status:** ⚠️ SCHEMA ONLY - **NO DATA** (worker not implemented)
**Created:** Migration 018 (2026-02-13)

**Key Columns:**
```sql
id UUID PRIMARY KEY
domain VARCHAR(255)
provider VARCHAR(100) (e.g., 'zen.spamhaus.org')
is_listed BOOLEAN
response_code VARCHAR(50)
checked_at TIMESTAMP
```

**Action Required:**
- 🔴 **HIGH PRIORITY:** Implement RBL checking worker
- See: `/secure-openclaw/research/2026-02-23_RBL_IMPLEMENTATION_GUIDE.md`
- Recommended: Self-built DNS querying (free, fast)

---

### 3. Campaign Tracking

#### `campaigns` (Campaign master table)
**Status:** ✅ DATA EXISTS (synced from EmailBison)

**Key Columns:**
```sql
id UUID PRIMARY KEY
workspace_id UUID
name VARCHAR(255)
status VARCHAR(50)
created_at, updated_at
```

**Data Quality:**
- ✅ Synced from EmailBison
- ✅ Basic campaign info available

---

#### `campaign_inboxes` (Campaign-inbox mapping)
**Status:** ✅ DATA EXISTS
**Purpose:** Links campaigns to inboxes (for burn attribution)

**Key Columns:**
```sql
campaign_id UUID → campaigns(id)
inbox_id UUID → sender_accounts(id)
assigned_at TIMESTAMP
```

**Data Quality:**
- ✅ Populated when inboxes assigned to campaigns
- ✅ Used for burn attribution

---

#### `campaign_burn_events` (Campaign death attribution)
**Status:** ⚠️ SCHEMA ONLY - **NEEDS POPULATION**
**Created:** Migration 036 (2026-02-22)

**Key Columns:**
```sql
id UUID PRIMARY KEY
campaign_id UUID → campaigns(id)
inbox_id UUID → sender_accounts(id)
workspace_id UUID
burned_at TIMESTAMP
burn_reason VARCHAR(100) (trigger type)
trigger_details JSONB
```

**Purpose:**
- Links inbox deaths to specific campaigns
- Enables "Campaign Burn Analysis" chart
- Quarantine trigger: 2+ burns in 7 days

**Action Required:**
- ⚠️ **MEDIUM PRIORITY:** Modify `kill_processor.py` to populate this table
- Logic: When inbox killed → Look up campaign_inboxes → Insert burn event
- See: IMPLEMENTATION_PLAN.md Task 6

---

#### Campaign Burn Views
**Created:** Migration 036

```sql
-- v_campaign_burn_summary: Aggregates by campaign
SELECT campaign_id, campaign_name, total_burns, burn_rate, should_quarantine

-- v_campaign_burn_breakdown: By trigger type
SELECT campaign_id, burn_reason, burn_count

-- v_campaign_burn_timeline: Weekly trends
SELECT campaign_id, week, burns_that_week
```

**Data Quality:**
- ✅ Views exist and functional
- ⚠️ Return zero rows (no data in campaign_burn_events yet)

---

### 4. Daily Snapshots

#### `daily_volume_snapshots` (Time-series data)
**Status:** ⚠️ SCHEMA ONLY - **NEEDS BACKFILL**
**Created:** Migration 041 (2026-02-23) - **TODAY!**

**Key Columns:**
```sql
id UUID PRIMARY KEY
workspace_id UUID
snapshot_date DATE

-- Volume metrics
emails_sent INTEGER
emails_delivered INTEGER
emails_bounced INTEGER
emails_complained INTEGER

-- Capacity metrics
live_inboxes INTEGER
incubating_inboxes INTEGER
dead_inboxes INTEGER
daily_capacity_available INTEGER

-- Derived
capacity_utilization_pct DECIMAL(5,2)
kills_that_day INTEGER

UNIQUE(workspace_id, snapshot_date)
```

**Helper Functions:**
```sql
-- Snapshot one workspace for one day
SELECT snapshot_daily_volume(workspace_id, date);

-- Snapshot all workspaces for one day
SELECT snapshot_all_workspaces(date);
```

**Action Required:**
- 🔴 **HIGH PRIORITY:** Backfill last 30-90 days
- 🔴 **HIGH PRIORITY:** Add to sync worker cron (run daily at 00:05 UTC)
- Data source: Aggregate from sender_accounts + campaign metrics

**Backfill Strategy:**
```sql
-- Backfill last 30 days for all workspaces
DO $$
DECLARE
    v_date DATE;
BEGIN
    FOR v_date IN
        SELECT generate_series(
            CURRENT_DATE - INTERVAL '30 days',
            CURRENT_DATE - INTERVAL '1 day',
            INTERVAL '1 day'
        )::DATE
    LOOP
        PERFORM snapshot_all_workspaces(v_date);
        RAISE NOTICE 'Snapshotted: %', v_date;
    END LOOP;
END $$;
```

---

### 5. Health Snapshots

#### `inbox_health_snapshots` (Inbox health time-series)
**Status:** ✅ DATA EXISTS (populated by sync worker)
**Purpose:** Historical health score trends

**Key Columns:**
```sql
id UUID PRIMARY KEY
inbox_id UUID
workspace_id UUID
health_score INTEGER
snapshot_at TIMESTAMP
```

**Data Quality:**
- ✅ Snapshots taken during sync (every 15-30 min)
- ✅ Enables health trend charting

---

#### `sender_warmup_snapshots` (Warmup progress tracking)
**Status:** ✅ DATA EXISTS
**Created:** Migration 026 (2026-02-13)

**Key Columns:**
```sql
id UUID PRIMARY KEY
sender_account_id UUID
warmup_enabled BOOLEAN
warmup_score INTEGER (0-100 from EmailBison)
warmup_emails_sent INTEGER
warmup_replies_received INTEGER
warmup_bounces_received_count INTEGER
warmup_emails_saved_from_spam INTEGER
snapshot_at TIMESTAMP
```

**Data Quality:**
- ✅ Populated during sync if warmup_enabled = true
- ✅ Tracks warmup progress over time

---

### 6. Capacity Planning

#### Capacity Views (Created: Migration 038-039, 2026-02-23)

**`v_domain_capacity`** - Per-domain capacity
```sql
SELECT
    domain,
    total_inboxes,
    active_inboxes,
    dead_inboxes,
    daily_capacity_conservative (active × 3),
    daily_capacity_aggressive (active × 4),
    capacity_utilization_pct (active / total × 100),
    viability_status ('healthy', 'warning', 'critical', 'deprecated'),
    rotation_recommendation
FROM v_domain_capacity;
```

**`v_workspace_capacity_summary`** - Workspace aggregates
```sql
SELECT
    workspace_id,
    provider_type,
    total_domains,
    live_domains,
    total_inboxes,
    live_inboxes,
    incubating_inboxes,
    daily_capacity_available
FROM v_workspace_capacity_summary;
```

**`v_client_capacity`** - Client subscription tracking
```sql
SELECT
    client_name,
    entra_packages,
    entra_domains_target,
    entra_domains_actual,
    entra_domain_gap,
    google_packages,
    google_domain_gap,
    buffer_percentage,
    buffer_status ('healthy', 'adequate', 'low', 'critical')
FROM v_client_capacity;
```

**`v_hypertide_order_queue`** - Actionable orders needed
```sql
SELECT
    client_id,
    provider_type,
    orders_needed,
    order_type,
    priority
FROM v_hypertide_order_queue
WHERE orders_needed > 0;
```

**Data Quality:**
- ✅ Views functional and querying live data
- ✅ Calculations accurate
- ⚠️ **Client subscriptions may not be populated** (entra_packages, google_packages)

---

### 7. List Management

#### `list_segments` (List quality tracking)
**Status:** ⚠️ SCHEMA ONLY - **MINIMAL DATA**
**Created:** Migration 031 (2026-02-22)

**Key Columns:**
```sql
id UUID PRIMARY KEY
workspace_id UUID
segment_name VARCHAR(255)
status VARCHAR(50) ('active', 'quarantined', 'purged')
bounce_count INTEGER
quarantined_at TIMESTAMP
purged_at TIMESTAMP
```

**Purpose:**
- Track list segment quality
- Quarantine segments with 2+ bounces
- Purge segments with 3+ bounces

**Action Required:**
- ⚠️ **MEDIUM PRIORITY:** Implement list segment tracker
- Track which segments cause bounces
- Auto-quarantine bad segments

---

#### `enrichment_providers` (Provider tracking)
**Status:** ⚠️ SCHEMA ONLY - **NO DATA**
**Created:** Migration 031

**Key Columns:**
```sql
id UUID PRIMARY KEY
provider_name VARCHAR(255)
bounce_count INTEGER
is_flagged BOOLEAN
flagged_at TIMESTAMP
```

**Purpose:**
- Track enrichment provider quality
- Flag providers with 3+ bounces

**Action Required:**
- ⚠️ **LOW PRIORITY:** Implement provider tracking
- Requires enrichment provider field in leads/contacts

---

### 8. Domain Rotation (Hypertide-specific)

#### Domain Rotation Tables - **NOT YET CREATED**

Based on `/secure-openclaw/research/2026-02-23_HYPERTIDE_DOMAIN_ROTATION_POLICY.md`, these tables are needed:

**`domain_rotation_events`** - Rotation history
```sql
CREATE TABLE domain_rotation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain VARCHAR(255) NOT NULL,
    workspace_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    -- 'redistribute', 'replace_requested', 'replace_completed', 'retired'
    reason TEXT,
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**`domain_replacement_queue`** - Pending replacements
```sql
CREATE TABLE domain_replacement_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    old_domain VARCHAR(255) NOT NULL,
    workspace_id UUID NOT NULL,
    replacement_reason TEXT NOT NULL,
    priority VARCHAR(20) NOT NULL, -- 'critical', 'high', 'medium', 'low'
    status VARCHAR(50) DEFAULT 'pending',
    -- 'pending', 'in_progress', 'completed', 'cancelled'
    requested_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    new_domain VARCHAR(255),
    notes TEXT
);
```

**Action Required:**
- 🟡 **NEW FEATURE:** Create migration 043 for rotation tables
- See: HYPERTIDE_VS_HEALTH_V3_IMPACT_ANALYSIS.md

---

## Data Availability Matrix

| Table | Schema | Data | Sync | Quality |
|-------|--------|------|------|---------|
| **sender_accounts** | ✅ | ✅ | Every 15-30 min | Excellent |
| **kill_queue** | ✅ | ✅ | Real-time | Excellent |
| **kill_trigger_events** | ✅ | ✅ | Real-time | Excellent |
| **domains** | ✅ | ✅ | Every 15-30 min | Good |
| **rbl_check_logs** | ✅ | ❌ | **NONE** | Empty |
| **campaigns** | ✅ | ✅ | Every 15-30 min | Good |
| **campaign_inboxes** | ✅ | ✅ | Real-time | Good |
| **campaign_burn_events** | ✅ | ❌ | **NONE** | Empty |
| **daily_volume_snapshots** | ✅ | ❌ | **NONE** | Empty (new) |
| **inbox_health_snapshots** | ✅ | ✅ | Every 15-30 min | Good |
| **sender_warmup_snapshots** | ✅ | ✅ | Every 15-30 min | Good |
| **list_segments** | ✅ | ⚠️ | Manual | Minimal |
| **enrichment_providers** | ✅ | ❌ | Manual | Empty |
| **domain_rotation_events** | ❌ | ❌ | N/A | Not created |
| **domain_replacement_queue** | ❌ | ❌ | N/A | Not created |

**Legend:**
- ✅ Complete
- ⚠️ Partial/minimal
- ❌ Missing/empty
- **NONE** = No worker/sync running

---

## Backfill Priority & Actions

### 🔴 HIGH PRIORITY (Week 1)

#### 1. Daily Volume Snapshots Backfill
**Table:** `daily_volume_snapshots`
**Why:** Client dashboard "Sending Capacity Chart" needs historical data
**Action:**
```sql
-- Run once to backfill last 30 days
DO $$
DECLARE
    v_date DATE;
    v_workspaces INTEGER;
BEGIN
    FOR v_date IN
        SELECT generate_series(
            CURRENT_DATE - INTERVAL '30 days',
            CURRENT_DATE - INTERVAL '1 day',
            INTERVAL '1 day'
        )::DATE
    LOOP
        SELECT snapshot_all_workspaces(v_date) INTO v_workspaces;
        RAISE NOTICE 'Date: % - Workspaces: %', v_date, v_workspaces;
    END LOOP;
END $$;
```

**Then add to cron:**
```python
# In emailbison_sync_worker.py
@schedule.every().day.at("00:05")
def daily_snapshot():
    """Snapshot previous day's volume at 00:05 UTC"""
    yesterday = (datetime.now() - timedelta(days=1)).date()
    with get_db_connection() as conn:
        conn.execute("SELECT snapshot_all_workspaces(%s)", (yesterday,))
    logger.info(f"Daily snapshot completed for {yesterday}")
```

**Time:** 1-2 hours
**Impact:** Enables capacity trend chart on dashboard

---

#### 2. RBL Checking Worker Implementation
**Table:** `rbl_check_logs`
**Why:** Dashboard shows "flagged_domains" but always 0 (no checks running)
**Action:**
1. Create `rbl_check_worker.py` using guide: `RBL_IMPLEMENTATION_GUIDE.md`
2. Check Spamhaus, Barracuda, SpamCop via DNS
3. Insert results into `rbl_check_logs`
4. Update `domains.latest_blacklist_count`, `is_clean`, `last_checked_at`
5. Schedule: Every 6-12 hours

**Time:** 8-12 hours (implementation + testing)
**Impact:** Domain blacklist alerts functional

---

### ⚠️ MEDIUM PRIORITY (Week 2)

#### 3. Campaign Burn Events Population
**Table:** `campaign_burn_events`
**Why:** Kill trigger breakdown chart needs "why" data
**Action:**
Modify `kill_processor.py`:
```python
def _track_campaign_burn(self, inbox, trigger_type):
    """Link inbox death to campaign"""
    # Get campaign assignment
    campaign_id = self._get_inbox_campaign(inbox.id)

    if campaign_id:
        # Insert burn event
        self.conn.execute("""
            INSERT INTO campaign_burn_events (
                campaign_id, inbox_id, workspace_id,
                burned_at, burn_reason, trigger_details
            ) VALUES (%s, %s, %s, NOW(), %s, %s)
        """, (campaign_id, inbox.id, inbox.workspace_id,
              trigger_type, json.dumps(inbox.health_metrics)))

        # Check for campaign quarantine (2+ burns in 7d)
        recent_burns = self._get_campaign_burns_7d(campaign_id)
        if len(recent_burns) >= 2:
            self._quarantine_campaign(campaign_id, "2+ burns in 7 days")
```

**Time:** 4-6 hours
**Impact:** Campaign burn analysis chart functional

---

#### 4. Client Subscription Data Entry
**Table:** `client_subscriptions`
**Why:** Capacity views show "orders needed" based on subscriptions
**Action:**
Manual data entry for each client:
```sql
INSERT INTO client_subscriptions (
    workspace_id,
    entra_packages,
    entra_domains_per_package,
    entra_inboxes_per_domain,
    google_packages,
    google_domains_per_package,
    google_inboxes_per_domain,
    spare_ratio,
    status
) VALUES (
    'client-uuid',
    2,    -- 2 Entra packages
    2,    -- 2 domains per package (standard)
    52,   -- 52 inboxes per domain (standard)
    1,    -- 1 Google package
    5,    -- 5 domains per package (standard)
    3,    -- 3 inboxes per domain (standard)
    0.15, -- 15% buffer
    'active'
);
```

**Time:** 1-2 hours (for all clients)
**Impact:** Accurate capacity gap analysis

---

### 🟢 LOW PRIORITY (Month 2+)

#### 5. List Segment Tracking
**Tables:** `list_segments`, `enrichment_providers`
**Why:** V3 compliance, list quality management
**Action:**
1. Add segment field to leads/contacts
2. Track which segments cause bounces
3. Auto-quarantine segments with 2+ bounces

**Time:** 10-15 hours
**Impact:** Better list quality management

---

#### 6. Domain Rotation Tables
**Tables:** `domain_rotation_events`, `domain_replacement_queue`
**Why:** Hypertide domain rotation workflow
**Action:**
Create migration 043:
```sql
-- See HYPERTIDE_VS_HEALTH_V3_IMPACT_ANALYSIS.md for full schema
CREATE TABLE domain_rotation_events (...);
CREATE TABLE domain_replacement_queue (...);
```

**Time:** 2-3 hours
**Impact:** Domain rotation workflow tracking

---

## Sync Worker Analysis

### EmailBison Sync Worker
**File:** `/charm-email-os/emailbison_sync_worker.py`
**Status:** ✅ Running
**Frequency:** Every 15-30 minutes

**What it syncs:**
- ✅ Sender accounts (inboxes)
- ✅ Health scores (calculated locally)
- ✅ Bounce counters
- ✅ Campaign data
- ✅ Warmup status
- ✅ Domain info
- ✅ Health snapshots
- ✅ Warmup snapshots

**What it doesn't sync:**
- ❌ RBL checks (no worker)
- ❌ Daily volume snapshots (needs cron)
- ❌ Campaign burn events (needs logic)

---

### Health Check Worker
**File:** `/charm-email-os/sync_modules/health_checks.py`
**Status:** ✅ Running (part of sync worker)
**Frequency:** Every sync cycle (15-30 min)

**What it does:**
- ✅ Detects kill triggers
- ✅ Inserts into kill_queue
- ✅ Calculates warning levels (critical/warning/watching)
- ✅ Logs to kill_trigger_events

---

### Kill Processor
**File:** `/charm-email-os/sync_modules/kill_processor.py`
**Status:** ✅ Running
**Frequency:** Every sync cycle

**What it does:**
- ✅ Processes kill_queue (24hr safety window)
- ✅ Tags inboxes in EmailBison
- ✅ Updates inbox_state to 'dead'
- ✅ Records killed_at timestamp

**What it should do:**
- ⚠️ Track campaign burns (not implemented)

---

## Data Quality Issues

### Issue 1: RBL Data Always Zero
**Symptom:** `domains.latest_blacklist_count` always 0
**Cause:** No RBL checking worker running
**Impact:** Dashboard shows "0 flagged domains" even if blacklisted
**Fix:** Implement RBL worker (HIGH PRIORITY)

---

### Issue 2: No Historical Volume Data
**Symptom:** Sending Capacity Chart shows "No data"
**Cause:** `daily_volume_snapshots` table empty (just created today)
**Impact:** Can't see capacity trends
**Fix:** Backfill 30 days + add to cron (HIGH PRIORITY)

---

### Issue 3: Campaign Burn Attribution Missing
**Symptom:** Kill Breakdown API returns zeros
**Cause:** `campaign_burn_events` table empty
**Impact:** Can't see WHY inboxes died by campaign
**Fix:** Modify kill_processor to populate (MEDIUM PRIORITY)

---

### Issue 4: Client Subscriptions Unknown
**Symptom:** Capacity views show NULL for package counts
**Cause:** `client_subscriptions` not populated
**Impact:** Can't calculate "orders needed"
**Fix:** Manual data entry (MEDIUM PRIORITY)

---

## Recommendations

### Immediate (This Week)
1. ✅ Backfill daily_volume_snapshots (30 days)
2. ✅ Add daily snapshot to sync worker cron
3. ✅ Implement RBL checking worker
4. ✅ Test all capacity views with real data

### Short-Term (Next 2 Weeks)
1. Modify kill_processor for campaign burn tracking
2. Populate client_subscriptions table
3. Verify all dashboard queries working
4. Monitor sync worker performance

### Long-Term (Month 2+)
1. Implement list segment tracking
2. Create domain rotation tables
3. Add enrichment provider tracking
4. Consider data retention policies (archive old snapshots)

---

## Database Performance Notes

### Indexes
- ✅ All primary keys indexed
- ✅ Foreign keys indexed
- ✅ Workspace queries optimized
- ✅ Date range queries optimized (daily_volume_snapshots)

### Query Performance
Most queries are fast (<100ms):
- Inbox health queries: ~50ms
- Domain capacity views: ~100ms
- Dashboard summary: ~200ms (aggregates multiple tables)

### Potential Bottlenecks
- Daily snapshot function on large workspaces (>10K inboxes)
- Campaign burn aggregation across time (needs testing with data)

---

## Related Documents

- **IMPLEMENTATION_PLAN.md** - Dashboard beta launch tasks
- **HYPERTIDE_DOMAIN_ROTATION_POLICY.md** - Rotation constraints
- **HYPERTIDE_VS_HEALTH_V3_IMPACT_ANALYSIS.md** - System impacts
- **RBL_IMPLEMENTATION_GUIDE.md** - RBL worker implementation
- **DASHBOARD_REVIEW.md** - Current dashboard assessment

---

## Summary

### What We Have ✅
- Comprehensive schema (42 migrations)
- Core inbox and domain data (synced continuously)
- Kill trigger system (working)
- Health scoring (working)
- Capacity views (working)

### What's Missing ❌
- RBL checking data (worker not running)
- Historical volume snapshots (table just created, empty)
- Campaign burn attribution (table exists, logic missing)
- Client subscription data (manual entry needed)

### Critical Path to Beta
1. Backfill daily snapshots (1 hour)
2. Implement RBL worker (8-12 hours)
3. Add campaign burn tracking (4-6 hours)

**Total: 13-19 hours to full data availability**

After these, all dashboard features will have real data to display.

---

**Document Version:** 1.0
**Last Updated:** 2026-02-23
**Status:** Analysis Complete
**Next Steps:** Execute HIGH priority backfill tasks
