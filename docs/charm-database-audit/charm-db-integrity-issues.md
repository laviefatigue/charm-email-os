---
title: Charm Email OS - Database Integrity Issues
created: 2026-02-23
updated: 2026-02-23
tags: [database, integrity, bugs, todo, charm-email-os]
status: needs-attention
---

# Database Integrity Issues - Charm Email OS

Known data integrity issues discovered during database audit on 2026-02-23.

## 🎯 Quick Team Assignment Matrix

| Team | Critical Issues | High Priority | Medium/Low | Total |
|------|----------------|---------------|------------|-------|
| **DBA/Backend** | #1, #2, #15 | #10, #11, #7 | #3, #4, #14 | 9 issues |
| **Domain Team** | - | #5 | #6, #8, #9 | 4 issues |
| **Campaign Team** | - | #12 | #13 | 2 issues |
| **Frontend/Analytics** | #15 (shared) | - | #16 | 2 issues |
| **DevOps** | - | #9 (shared) | #14 (shared) | 2 issues |

**Start Here (Parallel Execution):**
- **DBA Team**: Run Quick Fixes SQL → Add triggers → Create indexes
- **Backend Team**: Fix workspace aggregate query cross join bug
- **Domain Team**: Add is_owned flag → Update domain queries
- **Frontend Team**: Update dashboards with corrected queries
- **Campaign Team**: Add inbox validation → Review over-provisioned campaigns

## Summary

Overall database integrity is **good** with proper foreign key constraints and no orphaned records. However, several data synchronization and classification issues exist.

**Key Stats:**
- ✅ No orphaned records or broken foreign keys
- 🔴 3 critical issues requiring immediate attention
- 🟡 8 high/moderate priority issues
- 🟢 5 minor issues
- 📊 Affects: 1,475+ inboxes, 16 issues total, 6 teams involved

## ✅ What's Working

- No orphaned domains (all have valid workspaces)
- No clients without workspaces
- No duplicate domain names
- No orphaned sender accounts
- No duplicate workspace-client mappings
- No timestamp inconsistencies
- No NULL values in critical fields
- All foreign key constraints are intact

## 🔴 Critical Issues

### 1. Dead Domains Still Marked as Active

**Status:** Critical
**Impact:** High - 1,475 inboxes in dead domains still marked "Connected", risk of using burned domains

**Problem:**
Multiple domains are marked as `domain_state = 'dead'` but still have `is_active = true`, and contain thousands of sender accounts marked as "Connected".

**Evidence:**
```sql
-- 1,475 inboxes marked "Connected" but in dead domains
SELECT COUNT(*) FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE d.domain_state = 'dead' AND sa.status = 'Connected';
-- Returns: 1,475

-- Examples by workspace:
-- Spout: 861 connected inboxes in dead domains
-- Hello Hero: 518 connected inboxes in dead domains
-- Sammy: 51 connected inboxes in dead domains
```

**Specific Cases for Charm:**
- usehirecharm.com: dead, is_active=true, 52 "Not connected" inboxes
- lovecharmgtm.com: dead, is_active=true, 51 "Not connected" inboxes
- globaloutreachclub.com: dead, is_active=true, 3 "Not connected" inboxes
- urosaf-bio.com: dead, is_active=true, 3 "Not connected" inboxes
- eudalie-bio.com: dead, is_active=true, 3 "Not connected" inboxes
- usecharmgtm.com: dead, is_active=true (nameserver_status=failed), 51 "Not connected" inboxes

**Fix Required:**
1. When domain_state changes to 'dead', set is_active = false
2. When domain_state = 'dead', update all sender_accounts to status = 'Not connected'
3. Add database trigger to enforce this
4. Backfill existing data

```sql
-- Immediate fix
UPDATE domains SET is_active = false WHERE domain_state = 'dead';

UPDATE sender_accounts sa
SET status = 'Not connected'
FROM domains d
WHERE sa.domain_id = d.id AND d.domain_state = 'dead';

-- Add trigger to prevent future occurrences
CREATE OR REPLACE FUNCTION sync_domain_state()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.domain_state = 'dead' THEN
    NEW.is_active = false;
    -- Also update all sender accounts
    UPDATE sender_accounts SET status = 'Not connected'
    WHERE domain_id = NEW.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER domain_state_sync
BEFORE UPDATE ON domains
FOR EACH ROW EXECUTE FUNCTION sync_domain_state();
```

### 2. sender_account_count Never Updated

**Status:** Critical
**Impact:** High - Reporting inaccuracies, dashboard metrics incorrect

**Problem:**
The `domains.sender_account_count` column is always `0`, even for domains with active inboxes.

**Evidence:**
```sql
-- All 14 domains with actual inboxes show sender_account_count = 0
SELECT domain_name, sender_account_count, COUNT(sa.id) as actual_count
FROM domains d
LEFT JOIN sender_accounts sa ON sa.domain_id = d.id
WHERE d.workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd'
GROUP BY d.id
HAVING COUNT(sa.id) > 0;

-- Results show sender_account_count = 0 but actual_count = 3-52
```

**Root Cause:**
The field appears to be a denormalized counter that is never updated via:
- Database triggers
- Application code
- Background jobs

**Fix Required:**
1. Add database trigger to update `sender_account_count` on sender_account INSERT/DELETE
2. Run one-time migration to backfill correct counts
3. OR: Remove the column and always JOIN to get count (remove denormalization)

**Recommended Approach:**
```sql
-- Option 1: Add trigger (best for performance)
CREATE OR REPLACE FUNCTION update_domain_sender_count()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    UPDATE domains SET sender_account_count = sender_account_count + 1
    WHERE id = NEW.domain_id;
  ELSIF TG_OP = 'DELETE' THEN
    UPDATE domains SET sender_account_count = sender_account_count - 1
    WHERE id = OLD.domain_id;
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sender_account_count_trigger
AFTER INSERT OR DELETE ON sender_accounts
FOR EACH ROW EXECUTE FUNCTION update_domain_sender_count();

-- Backfill existing counts
UPDATE domains d
SET sender_account_count = (
  SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id
);
```

## 🟡 Moderate Issues

### 2. Live/Dead Inbox Count Mismatch

**Status:** Moderate
**Impact:** Medium - Confusing metrics, unclear inbox states

**Problem:**
The `live_inbox_count` vs `dead_inbox_count` don't match the actual connection status.

**Evidence:**
- 24 sender accounts have `status = 'Connected'`
- But only 21 are counted in `live_inbox_count`
- The counting logic is unclear

**Investigation Needed:**
```sql
-- Check the actual logic for live vs dead
SELECT
  sa.status,
  sa.inbox_state,
  COUNT(*)
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE d.workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd'
GROUP BY sa.status, sa.inbox_state;
```

**Questions:**
1. What determines if an inbox is "live" vs "dead"?
2. Is it based on `status` column or `inbox_state` column?
3. Should "Connected" but flagged inboxes count as live?

**Fix Required:**
- Document the business logic for live/dead classification
- Add database view or function with clear rules
- Update any code that manually calculates these counts

### 3. Status Field Inconsistent Casing

**Status:** Minor
**Impact:** Low - Code fragility

**Problem:**
Sender account statuses use inconsistent casing:
- "Connected" (capital C)
- "Not connected" (lowercase n)

**Evidence:**
```sql
SELECT DISTINCT status FROM sender_accounts;
-- Returns: 'Connected', 'Not connected'
```

**Fix Required:**
1. Standardize to lowercase: 'connected', 'not_connected'
2. OR: Add CHECK constraint to enforce valid values
3. Update all queries to handle case-insensitively

**Recommended:**
```sql
-- Add enum type for status
CREATE TYPE sender_status AS ENUM ('connected', 'not_connected', 'error', 'pending');

-- Migrate column
ALTER TABLE sender_accounts
  ALTER COLUMN status TYPE sender_status
  USING LOWER(REPLACE(status, ' ', '_'))::sender_status;
```

## 🟠 Data Quality Issues

### 4. Generated Domains Marked as "Live"

**Status:** Data Quality
**Impact:** Medium - Misleading counts, unclear inventory

**Problem:**
93 domains are marked as `domain_state = 'live'` but have:
- 0 inboxes
- No purchase date
- `approval_status IN ('pending', 'available')`

These are AI-generated domain suggestions, not actually owned domains.

**Current State:**
```
Live domains: 100 total
├── 93 suggested (0 inboxes, not owned)
└── 7 actual owned domains (21 inboxes)
```

**Confusion:**
- "Live" implies operational, but these domains don't exist yet
- Hard to distinguish suggested vs owned domains in queries
- Dashboards likely over-report domain inventory

**Fix Options:**

**Option A: New domain_state values**
```sql
-- Add new states
ALTER TYPE domain_state ADD VALUE 'suggested';
ALTER TYPE domain_state ADD VALUE 'approved';

-- Migrate
UPDATE domains
SET domain_state = 'suggested'
WHERE approval_status IN ('pending', 'available')
  AND purchased_at IS NULL
  AND sender_account_count = 0;
```

**Option B: Add is_owned flag**
```sql
ALTER TABLE domains ADD COLUMN is_owned BOOLEAN DEFAULT FALSE;

UPDATE domains
SET is_owned = TRUE
WHERE approval_status IN ('legacy', 'purchased')
   OR purchased_at IS NOT NULL
   OR sender_account_count > 0;
```

**Recommended:** Option B (clearer, backward compatible)

### 5. Purchased Domains Missing Purchase Date

**Status:** Moderate
**Impact:** Medium - Cannot track purchase timeline, billing issues

**Problem:**
7 domains marked as `approval_status = 'purchased'` but have `purchased_at = NULL`.

**Evidence:**
```sql
-- All purchased domains for Charm have no purchase date
SELECT domain_name FROM domains
WHERE approval_status = 'purchased' AND purchased_at IS NULL;

-- Results:
-- outboundwithcharm.com
-- scalewithcharm.co
-- staffingwithcharm.com
-- outreachwithcharm.com
-- growthwithcharm.com
-- revenuewithcharm.com
-- pipelinewithcharm.com
```

**Fix Required:**
- Add NOT NULL constraint with default value
- Backfill from domain_purchase_jobs.completed_at or created_at
- Update purchase workflow to always set purchased_at

### 6. Orphaned Campaign Inbox Assignments

**Status:** Moderate
**Impact:** Medium - 446 campaign inbox records pointing to deleted campaigns

**Problem:**
446 records in `campaign_inboxes` table reference campaigns that no longer exist.

**Evidence:**
```sql
SELECT COUNT(*) FROM campaign_inboxes ci
LEFT JOIN emailbison_campaigns ec ON ci.campaign_id = ec.id
WHERE ec.id IS NULL;
-- Returns: 446

-- All have NULL campaign_id
SELECT campaign_id, COUNT(*) FROM campaign_inboxes ci
LEFT JOIN emailbison_campaigns ec ON ci.campaign_id = ec.id
WHERE ec.id IS NULL
GROUP BY campaign_id;
-- campaign_id = NULL, count = 446
```

**Date Range:** Created between 2026-02-19 and 2026-02-22

**Fix Required:**
1. Add ON DELETE CASCADE to foreign key constraint
2. Clean up existing orphaned records
3. Investigate why campaign_id is NULL

```sql
-- Cleanup
DELETE FROM campaign_inboxes WHERE campaign_id IS NULL;

-- Fix foreign key
ALTER TABLE campaign_inboxes
DROP CONSTRAINT IF EXISTS campaign_inboxes_campaign_id_fkey;

ALTER TABLE campaign_inboxes
ADD CONSTRAINT campaign_inboxes_campaign_id_fkey
FOREIGN KEY (campaign_id) REFERENCES emailbison_campaigns(id)
ON DELETE CASCADE;
```

### 7. Selected Provider Without Price Data

**Status:** Minor
**Impact:** Low - UX confusion, purchase errors possible

**Problem:**
21 domains have `selected_provider` set but no price data for that provider.

**Evidence:**
```sql
SELECT COUNT(*) FROM domains
WHERE selected_provider IS NOT NULL AND
      ((selected_provider = 'porkbun' AND porkbun_price IS NULL) OR
       (selected_provider = 'dynadot' AND dynadot_price IS NULL));
-- Returns: 21
```

**Fix Required:**
- Validate that price exists before setting selected_provider
- Add CHECK constraint
- Re-fetch prices for affected domains

### 8. Health Monitoring Not Running

**Status:** Moderate
**Impact:** Medium - No visibility into domain/inbox health

**Problem:**
Only 14 out of 107 domains have health scores, and NONE have check timestamps.

**Evidence:**
```sql
-- Only 14 domains have health scores
-- 0 domains have last_checked_at set
-- 0 domains have next_check_at set
```

**Fix Required:**
- Verify health monitoring job is running
- Check if job is configured for all workspaces
- Manually trigger initial health check for all domains

### 9. Onboarding Data Missing for Most Clients

**Status:** Minor
**Impact:** Low - Limited personalization, harder to regenerate suggestions

**Problem:**
Only Charm client has onboarding data. 14 out of 15 clients have `onboarding_complete = true` but `onboarding_data = null`.

**Evidence:**
```sql
SELECT COUNT(*) FROM clients
WHERE onboarding_complete = true AND onboarding_data IS NULL;
-- Returns: 14 out of 15 clients
```

**Fix Required:**
- Migrate old client data into onboarding_data JSONB
- OR: Mark onboarding_complete = false and re-run onboarding
- Document what fields are required vs optional

## 🟠 Performance & Infrastructure Issues

### 10. Missing Foreign Key Indexes (26 tables)

**Status:** Moderate
**Impact:** Medium - Slow JOIN queries, poor query performance

**Problem:**
26 foreign key columns lack indexes, causing slow JOINs and table scans.

**Critical Missing Indexes:**
```sql
-- High-traffic tables without FK indexes:
- response_messages.campaign_event_id (8,255 rows)
- response_messages.sender_account_id (8,255 rows)
- campaign_inboxes.sender_account_id (implied from usage)
- kill_trigger_events.domain_id
- kill_trigger_events.replacement_inbox_id
- domains.purchase_job_id
```

**Full List of Missing Indexes:**
- client_subscriptions.package_template_id
- cost_logs.company_id, person_id
- domain_purchase_jobs.workspace_id
- domain_purchase_queue.domain_id
- domains.purchase_job_id
- hypertide_healing_jobs.change_id
- hypertide_ui_changes.healing_job_id, baseline_snapshot_id, current_snapshot_id
- hypertide_ui_snapshots.baseline_id
- inbox_purchase_jobs.workspace_id
- kill_trigger_events.domain_id, replacement_inbox_id
- lead_pull_jobs.suggestion_id, submission_id
- predicted_emails.company_id
- response_messages.campaign_event_id, sender_account_id
- reviews.layer_output_id
- strategy_generation_jobs.strategy_id, revision_of
- strategy_revision_requests.variant_id
- strategy_suggestions.original_suggestion_id, previous_version_id
- webhook_logs.user_id

**Fix Required:**
```sql
-- Priority indexes (add these first)
CREATE INDEX idx_response_messages_campaign_event ON response_messages(campaign_event_id);
CREATE INDEX idx_response_messages_sender_account ON response_messages(sender_account_id);
CREATE INDEX idx_kill_trigger_events_domain ON kill_trigger_events(domain_id);
CREATE INDEX idx_kill_trigger_events_replacement ON kill_trigger_events(replacement_inbox_id);
CREATE INDEX idx_domain_purchase_jobs_workspace ON domain_purchase_jobs(workspace_id);
```

### 11. Large Table Without Proper Maintenance

**Status:** Moderate
**Impact:** Medium - Bloat, slow queries

**Problem:**
`sender_warmup_snapshots` table is 544 MB with 96,475 rows and has NEVER been analyzed.

**Evidence:**
```sql
-- Table size: 544 MB
-- Rows: 96,475
-- last_analyze: NULL
-- last_autoanalyze: NULL
```

**Impact:**
- Query planner has no statistics
- May choose poor execution plans
- Possible table bloat

**Fix Required:**
```sql
-- Manual analyze
ANALYZE sender_warmup_snapshots;

-- Enable auto-analyze if disabled
ALTER TABLE sender_warmup_snapshots SET (autovacuum_enabled = true);

-- Check for bloat and consider VACUUM FULL if needed
VACUUM ANALYZE sender_warmup_snapshots;
```

### 12. Campaigns Without Inboxes

**Status:** Moderate
**Impact:** Medium - 60 campaigns can't send emails

**Problem:**
60 active campaigns have no assigned inboxes.

**Evidence:**
```sql
SELECT COUNT(DISTINCT ec.id) FROM emailbison_campaigns ec
LEFT JOIN campaign_inboxes ci ON ci.campaign_id = ec.id
WHERE ci.id IS NULL;
-- Returns: 60
```

**Fix Required:**
- Investigate if these are draft/paused campaigns
- Add validation to prevent campaign activation without inboxes
- Clean up or assign inboxes

### 13. Over-Provisioned Campaigns

**Status:** Minor
**Impact:** Low - Waste of resources

**Problem:**
39 campaigns have >100 inboxes assigned (excessive for most use cases).

**Evidence:**
```sql
SELECT campaign_id, COUNT(*) as inbox_count
FROM campaign_inboxes
WHERE campaign_id IS NOT NULL
GROUP BY campaign_id
HAVING COUNT(*) > 100;
-- Returns: 39 campaigns with 100+ inboxes
```

**Fix Required:**
- Review campaign inbox allocation strategy
- Add warnings in UI for campaigns with >100 inboxes
- Document recommended inbox counts per campaign

### 14. Database Configuration Sub-Optimal

**Status:** Minor
**Impact:** Low-Medium - Not optimized for workload

**Problem:**
PostgreSQL default configuration not tuned for production workload.

**Current Settings:**
- `shared_buffers`: 128 MB (too low for 500+ MB database)
- `effective_cache_size`: 4 GB (should be ~75% of RAM)
- `work_mem`: 4 MB (too low for complex queries)
- `maintenance_work_mem`: 64 MB (too low for VACUUM)
- `random_page_cost`: 4 (too high for SSD)
- `effective_io_concurrency`: 1 (too low for SSD)

**Recommended Settings** (for 8GB RAM server with SSD):
```sql
-- postgresql.conf or ALTER SYSTEM
shared_buffers = '2GB'
effective_cache_size = '6GB'
work_mem = '16MB'
maintenance_work_mem = '512MB'
random_page_cost = 1.1
effective_io_concurrency = 200
```

### 15. Workspace-Level Domain Count Calculation Error

**Status:** Critical (Data Bug)
**Impact:** High - Severely inflated counts in queries

**Problem:**
Workspace-level counts are MASSIVELY inflated due to CROSS JOIN issue in aggregate query.

**Example for Charm:**
- Actual: 107 domains, 187 inboxes
- Reported in workspace aggregate: 14,586 "dead but active domains" (should be 6)

**This affects ALL workspace-level dashboards and reports.**

**Root Cause:**
The query joining workspaces → domains → sender_accounts is likely doing a CROSS JOIN somewhere, multiplying counts.

**Fix Required:**
- Review all workspace-level aggregate queries
- Use DISTINCT COUNT or subqueries to prevent multiplication
- Add tests to verify counts match reality

## 📊 Affected Metrics

These issues affect:

1. **Client Dashboard**
   - Domain counts (inflated by 93 suggested domains)
   - Inbox counts (always shows 0 due to sender_account_count bug)

2. **Inventory Reports**
   - Total domains appears inflated
   - Utilization metrics incorrect

3. **Domain Management UI**
   - Hard to filter "my actual domains"
   - Confusion between suggested and owned

## 🏗️ Issues by Platform Component

### 🗄️ DATABASE LAYER (DBA/Backend Team)

**CRITICAL - Immediate Action Required:**
- Issue #1: Dead domains marked active (1,475 inboxes at risk)
- Issue #2: sender_account_count never updated
- Issue #15: Workspace count calculation bug (cross join)

**High Priority:**
- Issue #10: Missing 26 foreign key indexes
- Issue #11: 544 MB table never analyzed
- Issue #14: Database configuration not optimized

**Medium Priority:**
- Issue #3: Live/dead count mismatch logic
- Issue #6: Orphaned campaign_inbox records (446)
- Issue #4: Status field inconsistent casing

**SQL Scripts Needed:**
```sql
-- 1. Add database triggers for domain state sync
-- 2. Add sender_account_count triggers
-- 3. Create missing indexes (26 total)
-- 4. Backfill data corrections
-- 5. Add CHECK constraints
-- 6. Optimize PostgreSQL config
```

### 📊 DOMAIN MANAGEMENT (Domain Team)

**CRITICAL:**
- Issue #5: 93 generated domains marked "live" (not owned)

**High Priority:**
- Issue #7: Purchased domains missing purchase_at dates
- Issue #8: Selected provider without price data

**Medium Priority:**
- Issue #9: Health monitoring not running

**Tasks:**
- Add `is_owned` boolean flag to domains table
- Backfill purchase dates from job records
- Re-fetch pricing for 21 domains
- Investigate health monitoring worker
- Update domain classification logic

### 📧 CAMPAIGN SYSTEM (Campaign Team)

**High Priority:**
- Issue #12: 60 campaigns without inboxes
- Issue #13: 39 campaigns with >100 inboxes

**Tasks:**
- Add validation: prevent campaign activation without inboxes
- Review inbox allocation strategy
- Add UI warnings for over-provisioned campaigns
- Document recommended inbox counts
- Clean up or assign inboxes to empty campaigns

### 👥 CLIENT ONBOARDING (Frontend/Product Team)

**Low Priority:**
- Issue #16: 14 clients missing onboarding_data

**Tasks:**
- Migrate legacy client data to onboarding_data JSONB
- OR: Mark onboarding_complete = false and re-onboard
- Document required vs optional fields
- Update onboarding flow validation

### 📈 REPORTING & DASHBOARDS (Analytics/Frontend Team)

**CRITICAL:**
- Issue #15: Workspace aggregate queries showing inflated counts

**High Priority:**
- Update all workspace-level aggregate queries
- Fix cross join issues in reporting
- Update dashboard queries to filter `is_owned = true`

**Tasks:**
- Review all JOIN queries in dashboard components
- Add DISTINCT COUNT or use subqueries
- Add automated tests to verify count accuracy
- Update Client Dashboard metrics
- Fix Inventory Reports
- Update Domain Management UI filters

### 🔧 BACKGROUND WORKERS (DevOps/Backend Team)

**High Priority:**
- Issue #9: Health monitoring system not running

**Tasks:**
- Verify health monitoring worker is deployed
- Check worker logs for errors
- Manually trigger initial health check
- Add worker monitoring/alerting
- Document worker configuration

### 🎯 DATA QUALITY & MONITORING (Platform Team)

**Ongoing:**
- Set up daily integrity check job
- Add alerts for count mismatches
- Create data quality dashboard
- Monitor for orphaned records

**Tasks:**
- Create automated integrity check script
- Set up Slack/email alerts
- Build admin dashboard for data quality metrics
- Add monitoring for dead tuple percentage

## 🔧 Recommended Action Plan by Timeline

### 🚨 IMMEDIATE (Today - Week 1)

**Database Team:**
1. Run quick fix SQL (see Quick Fixes section)
2. Add domain state sync trigger
3. Add sender_account_count trigger
4. Create priority indexes (response_messages, kill_trigger_events)

**Backend Team:**
5. Fix workspace aggregate query cross join bug
6. Clean up 446 orphaned campaign_inbox records

**Domain Team:**
7. Add `is_owned` flag to domains
8. Update domain queries to filter owned domains

### 📅 SHORT TERM (Week 2-3)

**Database Team:**
9. Create remaining 23 indexes
10. Run ANALYZE on sender_warmup_snapshots
11. Optimize PostgreSQL configuration
12. Add ON DELETE CASCADE constraints

**Domain Team:**
13. Backfill purchased_at dates
14. Re-fetch pricing for affected domains
15. Investigate health monitoring

**Campaign Team:**
16. Add campaign validation logic
17. Review over-provisioned campaigns

**Frontend Team:**
18. Update dashboards to use corrected queries
19. Add domain ownership filters

### 🔄 MEDIUM TERM (Week 4+)

**Backend Team:**
20. Standardize status field values (add enum)
21. Document live/dead classification logic
22. Create database views for common queries

**Product Team:**
23. Migrate onboarding data for legacy clients
24. Update onboarding validation

**Platform Team:**
25. Build automated integrity check job
26. Set up data quality monitoring
27. Create admin data quality dashboard

## 📝 Testing Queries

Use these to verify fixes:

```sql
-- Verify sender_account_count is accurate
SELECT
  d.domain_name,
  d.sender_account_count as reported,
  COUNT(sa.id) as actual,
  d.sender_account_count = COUNT(sa.id) as matches
FROM domains d
LEFT JOIN sender_accounts sa ON sa.domain_id = d.id
GROUP BY d.id
HAVING d.sender_account_count != COUNT(sa.id);
-- Should return 0 rows

-- Verify live/dead counts add up
SELECT
  domain_name,
  live_inbox_count + dead_inbox_count as total_calculated,
  sender_account_count as total_reported
FROM domains
WHERE live_inbox_count + dead_inbox_count != sender_account_count;
-- Should return 0 rows

-- Verify domain ownership clarity
SELECT
  is_owned,
  COUNT(*) as count,
  SUM(sender_account_count) as total_inboxes
FROM domains
WHERE workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd'
GROUP BY is_owned;
-- Should clearly show owned vs suggested
```

## Database Connection Info

```bash
# Local database (development)
Host: postgres
Port: 5432
Database: postgres
User: postgres
Password: localdevpassword

# Production database
Host: charm-postgres
Port: 5432
Database: postgres
User: postgres
Password: [see .env file]
```

## Issue Summary Table

| # | Issue | Severity | Component | Owner Team | Affected Records | Impact |
|---|-------|----------|-----------|------------|-----------------|--------|
| 1 | Dead domains marked active | 🔴 Critical | Database | DBA/Backend | 1,475 inboxes | Using burned domains |
| 2 | sender_account_count always 0 | 🔴 Critical | Database | DBA/Backend | All domains | Wrong metrics |
| 15 | Workspace count calculation bug | 🔴 Critical | Reporting | Analytics/Frontend | All workspaces | Inflated metrics |
| 10 | Missing foreign key indexes | 🟡 High | Database | DBA | 26 tables | Slow JOINs |
| 11 | Large table never analyzed | 🟡 High | Database | DBA | 96K rows | Poor query plans |
| 12 | Campaigns without inboxes | 🟡 High | Campaigns | Campaign Team | 60 campaigns | Can't send |
| 5 | Generated domains marked "live" | 🟡 High | Domains | Domain Team | 93 domains | Inflated counts |
| 6 | Purchased domains no date | 🟡 Moderate | Domains | Domain Team | 7 domains | Can't track timeline |
| 7 | Orphaned campaign inboxes | 🟡 Moderate | Database | Backend | 446 records | Database bloat |
| 8 | Selected provider no price | 🟡 Moderate | Domains | Domain Team | 21 domains | UX confusion |
| 9 | Health monitoring not running | 🟡 Moderate | Workers | DevOps/Backend | 93 domains | No health visibility |
| 3 | Live/dead count mismatch | 🟡 Moderate | Database | DBA/Backend | All domains | Confusing metrics |
| 4 | Status field inconsistent casing | 🟡 Moderate | Database | DBA | All accounts | Code fragility |
| 13 | Over-provisioned campaigns | 🟢 Minor | Campaigns | Campaign Team | 39 campaigns | Resource waste |
| 14 | Database config sub-optimal | 🟢 Minor | Database | DBA/DevOps | All queries | Slower performance |
| 16 | Missing onboarding data | 🟢 Minor | Onboarding | Frontend/Product | 14 clients | Limited features |

## Quick Fixes

Copy and paste these to fix the most critical issues immediately:

```sql
-- FIX #1: Sync dead domain state (CRITICAL - DO THIS FIRST!)
UPDATE domains SET is_active = false WHERE domain_state = 'dead';

UPDATE sender_accounts sa
SET status = 'Not connected'
FROM domains d
WHERE sa.domain_id = d.id AND d.domain_state = 'dead';

-- FIX #2: Backfill sender_account_count
UPDATE domains d
SET sender_account_count = (
  SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id
);

-- FIX #7: Clean up orphaned campaign inboxes
DELETE FROM campaign_inboxes WHERE campaign_id IS NULL;

-- FIX #11: Add critical missing indexes (improves query performance)
CREATE INDEX CONCURRENTLY idx_response_messages_campaign_event ON response_messages(campaign_event_id);
CREATE INDEX CONCURRENTLY idx_response_messages_sender_account ON response_messages(sender_account_id);
CREATE INDEX CONCURRENTLY idx_kill_trigger_events_domain ON kill_trigger_events(domain_id);

-- FIX #12: Analyze large table
ANALYZE sender_warmup_snapshots;
```

## Changelog

- **2026-02-23**: Initial audit and documentation
  - Discovered sender_account_count bug
  - Identified domain classification issues
  - Documented status field inconsistencies
- **2026-02-23** (Evening): Extended audit findings
  - 🚨 CRITICAL: Found 1,475 active inboxes in dead domains
  - Found 446 orphaned campaign inbox records
  - Identified health monitoring system not running
  - Found purchased domains missing purchase dates
  - Identified pricing data inconsistencies
- **2026-02-23** (System-wide audit): Infrastructure & performance issues
  - 🚨 CRITICAL: Workspace-level counts massively inflated (cross join bug)
  - Found 26 missing foreign key indexes (major performance issue)
  - 544 MB table never analyzed (sender_warmup_snapshots)
  - 60 campaigns without inboxes
  - 39 over-provisioned campaigns (>100 inboxes)
  - Database configuration not optimized for production
  - 359 domains with live+dead count mismatch
