---
title: Charm Email OS - Database Fixes by Team
created: 2026-02-23
tags: [database, team-assignments, action-items]
---

# Database Fixes - Team Assignment Breakdown

Quick reference for parallel execution. Each team can work independently.

---

## 🗄️ DBA/BACKEND TEAM (Priority: CRITICAL)

**Team Lead:** [Assign DBA Lead]
**Estimated Effort:** 2-3 days
**Dependencies:** None (can start immediately)

### Immediate Actions (Today)

```sql
-- 1. Fix dead domain state sync (CRITICAL - Issue #1)
UPDATE domains SET is_active = false WHERE domain_state = 'dead';

UPDATE sender_accounts sa
SET status = 'Not connected'
FROM domains d
WHERE sa.domain_id = d.id AND d.domain_state = 'dead';

-- 2. Backfill sender_account_count (CRITICAL - Issue #2)
UPDATE domains d
SET sender_account_count = (
  SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id
);

-- 3. Clean up orphaned records (Issue #7)
DELETE FROM campaign_inboxes WHERE campaign_id IS NULL;

-- 4. Add priority indexes (Issue #10)
CREATE INDEX CONCURRENTLY idx_response_messages_campaign_event ON response_messages(campaign_event_id);
CREATE INDEX CONCURRENTLY idx_response_messages_sender_account ON response_messages(sender_account_id);
CREATE INDEX CONCURRENTLY idx_kill_trigger_events_domain ON kill_trigger_events(domain_id);
CREATE INDEX CONCURRENTLY idx_kill_trigger_events_replacement ON kill_trigger_events(replacement_inbox_id);

-- 5. Analyze large table (Issue #11)
ANALYZE sender_warmup_snapshots;
```

### Add Database Triggers (Day 2)

```sql
-- Trigger for domain state sync
CREATE OR REPLACE FUNCTION sync_domain_state()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.domain_state = 'dead' THEN
    NEW.is_active = false;
    UPDATE sender_accounts SET status = 'Not connected'
    WHERE domain_id = NEW.id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER domain_state_sync
BEFORE UPDATE ON domains
FOR EACH ROW EXECUTE FUNCTION sync_domain_state();

-- Trigger for sender_account_count
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
```

### Create Remaining Indexes (Day 3)

```sql
-- Add remaining 22 indexes (Issue #10)
CREATE INDEX CONCURRENTLY idx_domain_purchase_jobs_workspace ON domain_purchase_jobs(workspace_id);
CREATE INDEX CONCURRENTLY idx_domain_purchase_queue_domain ON domain_purchase_queue(domain_id);
CREATE INDEX CONCURRENTLY idx_domains_purchase_job ON domains(purchase_job_id);
CREATE INDEX CONCURRENTLY idx_inbox_purchase_jobs_workspace ON inbox_purchase_jobs(workspace_id);
CREATE INDEX CONCURRENTLY idx_lead_pull_jobs_suggestion ON lead_pull_jobs(suggestion_id);
CREATE INDEX CONCURRENTLY idx_lead_pull_jobs_submission ON lead_pull_jobs(submission_id);
CREATE INDEX CONCURRENTLY idx_strategy_gen_jobs_strategy ON strategy_generation_jobs(strategy_id);
CREATE INDEX CONCURRENTLY idx_strategy_gen_jobs_revision ON strategy_generation_jobs(revision_of);
CREATE INDEX CONCURRENTLY idx_webhook_logs_user ON webhook_logs(user_id);
-- Add more as needed from full list in main doc
```

### Future Enhancements

- Issue #3: Document live/dead count logic
- Issue #4: Standardize status field (create enum)
- Issue #14: Optimize PostgreSQL config

---

## 📊 DOMAIN MANAGEMENT TEAM (Priority: HIGH)

**Team Lead:** [Assign Domain Team Lead]
**Estimated Effort:** 1-2 days
**Dependencies:** Wait for DBA team to finish sender_account_count fix

### Immediate Actions (Day 1)

```sql
-- 1. Add is_owned flag (Issue #5)
ALTER TABLE domains ADD COLUMN is_owned BOOLEAN DEFAULT FALSE;

UPDATE domains
SET is_owned = TRUE
WHERE approval_status IN ('legacy', 'purchased')
   OR purchased_at IS NOT NULL
   OR sender_account_count > 0;

-- 2. Backfill purchased_at dates (Issue #6)
UPDATE domains d
SET purchased_at = dpj.completed_at
FROM domain_purchase_jobs dpj
WHERE d.id = ANY(dpj.domain_ids)
  AND d.approval_status = 'purchased'
  AND d.purchased_at IS NULL
  AND dpj.completed_at IS NOT NULL;
```

### Code Changes Required

**File:** `api/routes/domains.py`
```python
# Update domain listing to filter owned domains
@router.get("/")
async def list_domains(owned_only: bool = True):
    query = "SELECT * FROM domains WHERE workspace_id = $1"
    if owned_only:
        query += " AND is_owned = TRUE"
    # ... rest of query
```

### Investigation Tasks

- Issue #8: Re-fetch pricing for 21 domains with selected_provider but no price
- Issue #9: Check why health monitoring isn't running
  - Check: `docker ps | grep health`
  - Check logs: `docker logs charm-health-monitor`
  - Verify cron job is configured

---

## 📧 CAMPAIGN TEAM (Priority: HIGH)

**Team Lead:** [Assign Campaign Lead]
**Estimated Effort:** 1 day
**Dependencies:** None

### Code Changes Required

**File:** `api/routes/campaigns.py`
```python
# Add validation before campaign activation
async def activate_campaign(campaign_id: UUID):
    inbox_count = await db.fetch_val(
        "SELECT COUNT(*) FROM campaign_inboxes WHERE campaign_id = $1",
        campaign_id
    )
    if inbox_count == 0:
        raise HTTPException(400, "Cannot activate campaign without inboxes")
```

**File:** `charm-email-os/app/campaigns/[id]/page.tsx`
```typescript
// Add warning for over-provisioned campaigns
{inboxCount > 100 && (
  <Alert severity="warning">
    This campaign has {inboxCount} inboxes. Consider reducing to 50-100 for optimal performance.
  </Alert>
)}
```

### Investigation Tasks

```sql
-- Investigate 60 campaigns without inboxes (Issue #12)
SELECT id, name, status, created_at
FROM emailbison_campaigns ec
LEFT JOIN campaign_inboxes ci ON ci.campaign_id = ec.id
WHERE ci.id IS NULL
ORDER BY created_at DESC;

-- Review over-provisioned campaigns (Issue #13)
SELECT campaign_id, COUNT(*) as inbox_count
FROM campaign_inboxes
WHERE campaign_id IS NOT NULL
GROUP BY campaign_id
HAVING COUNT(*) > 100
ORDER BY inbox_count DESC;
```

**Action:** Decide whether to auto-assign inboxes or mark as drafts

---

## 📈 FRONTEND/ANALYTICS TEAM (Priority: CRITICAL)

**Team Lead:** [Assign Frontend Lead]
**Estimated Effort:** 1-2 days
**Dependencies:** Wait for DBA to fix sender_account_count

### Critical Bug Fix (Issue #15)

**Problem:** Workspace aggregate queries have cross join bug causing massively inflated counts.

**Files to Review:**
- `api/routes/workspaces.py`
- `charm-email-os/app/clients/[clientId]/page.tsx`
- Any component fetching workspace-level stats

**Bad Pattern (DO NOT USE):**
```sql
-- This causes cross join multiplication
SELECT
    w.id,
    COUNT(d.id) as domain_count,
    COUNT(sa.id) as inbox_count
FROM workspaces w
LEFT JOIN domains d ON d.workspace_id = w.id
LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id
GROUP BY w.id;
-- Results in multiplied counts!
```

**Correct Pattern (USE THIS):**
```sql
-- Use subqueries or DISTINCT COUNT
SELECT
    w.id,
    (SELECT COUNT(*) FROM domains WHERE workspace_id = w.id) as domain_count,
    (SELECT COUNT(*) FROM sender_accounts WHERE workspace_id = w.id) as inbox_count
FROM workspaces w;

-- OR use DISTINCT COUNT with proper joins
SELECT
    w.id,
    COUNT(DISTINCT d.id) as domain_count,
    COUNT(DISTINCT sa.id) as inbox_count
FROM workspaces w
LEFT JOIN domains d ON d.workspace_id = w.id
LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id
GROUP BY w.id;
```

### Dashboard Updates Required

**Update filters to use is_owned flag:**
```typescript
// charm-email-os/app/domains/page.tsx
const { data: domains } = useQuery({
  queryKey: ['domains', workspaceId, 'owned'],
  queryFn: () => fetchDomains(workspaceId, { ownedOnly: true })
});
```

### Add Tests

```typescript
// Test workspace counts match reality
describe('Workspace Stats', () => {
  it('should return accurate domain count', async () => {
    const stats = await getWorkspaceStats(workspaceId);
    const actualCount = await db.query(
      'SELECT COUNT(*) FROM domains WHERE workspace_id = $1',
      [workspaceId]
    );
    expect(stats.domainCount).toBe(actualCount);
  });
});
```

---

## 🔧 DEVOPS TEAM (Priority: MODERATE)

**Team Lead:** [Assign DevOps Lead]
**Estimated Effort:** 1 day
**Dependencies:** None

### Health Monitoring Investigation (Issue #9)

**Check worker status:**
```bash
# Check if health worker is running
docker ps | grep health

# Check worker logs
docker logs charm-health-monitor --tail 100

# Check database for recent health checks
psql -c "SELECT MAX(created_at) FROM health_events;"
```

**Expected findings:**
- Worker may not be deployed
- Worker may be crashing
- Worker may not be configured for all workspaces

**Action:** Redeploy health monitoring worker with proper config

### Database Configuration (Issue #14)

**File:** `/etc/postgresql/14/main/postgresql.conf` (or equivalent)

```conf
# Optimize for 8GB RAM server with SSD
shared_buffers = 2GB
effective_cache_size = 6GB
work_mem = 16MB
maintenance_work_mem = 512MB
random_page_cost = 1.1
effective_io_concurrency = 200
max_connections = 100
```

**Apply changes:**
```bash
# Restart PostgreSQL
sudo systemctl restart postgresql

# OR if using Docker
docker restart charm-postgres
```

---

## 👥 PRODUCT/FRONTEND TEAM (Priority: LOW)

**Team Lead:** [Assign Product Lead]
**Estimated Effort:** 0.5 day
**Dependencies:** None (low priority)

### Onboarding Data Migration (Issue #16)

**Options:**

**Option A: Migrate existing data**
```sql
-- Migrate what data exists
UPDATE clients
SET onboarding_data = jsonb_build_object(
  'primaryDomain', website,
  'industry', industry,
  'contactFirstNames', ARRAY[contact_name]
)
WHERE onboarding_complete = true AND onboarding_data IS NULL;
```

**Option B: Re-onboard clients**
```sql
-- Mark as incomplete and re-onboard
UPDATE clients
SET onboarding_complete = false
WHERE onboarding_data IS NULL;
```

**Recommendation:** Option A for existing clients, improve onboarding flow for new ones.

---

## ✅ Verification Checklist

After all teams complete their work, run these verification queries:

```sql
-- 1. Verify no dead domains are active
SELECT COUNT(*) FROM domains
WHERE domain_state = 'dead' AND is_active = true;
-- Should return: 0

-- 2. Verify sender_account_count is accurate
SELECT COUNT(*) FROM domains d
WHERE d.sender_account_count != (
  SELECT COUNT(*) FROM sender_accounts WHERE domain_id = d.id
);
-- Should return: 0

-- 3. Verify no orphaned campaign inboxes
SELECT COUNT(*) FROM campaign_inboxes
WHERE campaign_id IS NULL;
-- Should return: 0

-- 4. Verify workspace counts are accurate
SELECT
  w.workspace_name,
  (SELECT COUNT(*) FROM domains WHERE workspace_id = w.id) as actual_domains,
  -- Compare with your dashboard
FROM workspaces w
WHERE w.id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd';
-- Charm should show: 107 domains, 187 inboxes

-- 5. Verify indexes were created
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE indexname LIKE 'idx_%'
  AND indexname IN (
    'idx_response_messages_campaign_event',
    'idx_response_messages_sender_account',
    'idx_kill_trigger_events_domain'
  );
-- Should return: 3 rows
```

---

## 📞 Coordination Notes

**Daily Standup Questions:**
1. DBA Team: Triggers deployed? Indexes created?
2. Backend Team: Workspace query bug fixed?
3. Domain Team: is_owned flag added? Queries updated?
4. Frontend Team: Dashboards showing correct counts?
5. Campaign Team: Validation added? Empty campaigns resolved?

**Blockers:**
- Frontend team blocked until DBA completes sender_account_count fix
- Domain team blocked until DBA completes sender_account_count fix
- All teams should complete work within 3 days for parallel execution

**Communication Channel:** [Slack #charm-db-fixes]
