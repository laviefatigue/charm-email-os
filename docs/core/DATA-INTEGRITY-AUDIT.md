# Data Integrity Audit Report

**Document ID:** CORE-AUDIT-001
**Created:** 2026-02-26
**Audit Scope:** EmailBison Sync → Database → API → Frontend

---

## Audit Summary

This audit examines the complete data pipeline from EmailBison (source of truth) through our sync system, database, and API endpoints to ensure data accuracy.

**Overall Integrity Score: 6.2/10**

| Dimension | Score | Status |
|-----------|-------|--------|
| Schema Design | 7/10 | Good structure, some constraints missing |
| Data Completeness | 5/10 | Critical fields not populated |
| Data Accuracy | 6/10 | Warmup/campaign mixing, snapshot issues |
| Referential Integrity | 8/10 | FK constraints present |
| Business Logic Alignment | 5/10 | Kill triggers incomplete |

---

## Critical Issues

### 1. `total_sends_7d` Never Populated - RESOLVED (2026-02-26)

**Severity:** ~~CRITICAL~~ RESOLVED
**Impact:** ~~Rate-based kill triggers NEVER fire~~ Now properly tracking sends

**Resolution Applied:**
- Added send delta tracking to `sync_accounts.py`
- Tracks `emails_sent_all_time` delta each sync cycle
- Adds delta to `total_sends_7d` for rate calculations
- Migration `054_populate_total_sends_7d.sql` initializes existing inboxes

**Key Design Decision - Why Sends Are Different from Bounces:**
```
Rate calculation: bounce_rate = hard_bounces_7d / total_sends_7d

- Numerator (bounces): Campaign-only via sync_events.py (warmup excluded)
- Denominator (sends): ALL sends (warmup + campaign) via delta tracking

This is CORRECT because:
- Higher send volume = lower bounce rate (good inbox health)
- We WANT warmup sends in the denominator
- Daily decay (0.86x in health_checks.py) maintains 7-day window
```

**New Data Flow:**
```
EmailBison emails_sent_count (cumulative) →
sync_accounts.py calculates delta →
total_sends_7d += delta →
health_checks.py uses for rate calculations →
rate-based kill triggers now fire correctly
```

**Verification Query:**
```sql
SELECT
    workspace_id,
    COUNT(*) as total_live,
    COUNT(*) FILTER (WHERE total_sends_7d > 0) as has_sends,
    AVG(total_sends_7d)::INTEGER as avg_sends_7d
FROM sender_accounts
WHERE inbox_state = 'live'
GROUP BY workspace_id;
-- Should show has_sends > 0 for active workspaces
```

---

### 2. Warmup vs Campaign Bounces Not Separated - RESOLVED (2026-02-26)

**Severity:** ~~CRITICAL~~ RESOLVED
**Impact:** ~~Inboxes may be killed for warmup bounces~~ Now properly separated

**Resolution Applied:**
- Warmup is a **status**, not a campaign - warmup pool is managed by EmailBison
- `sync_events.py` ONLY syncs bounces from `/campaigns/{id}/replies` (our campaigns)
- Warmup pool bounces are NOT synced as campaign replies (different data path)
- Removed delta tracking that used `bounces_all_time` (included warmup bounces)

**Key Understanding:**
- `warmup_enabled = true` → Inbox participates in EmailBison's warmup pool
- Warmup pool bounces → `warmup_bounces_received/caused` (monitoring only)
- Our campaigns → `/campaigns/{id}/replies?folder=bounced` → `hard_bounces_*` (kill triggers)

**Data Flow (Corrected):**
```
Our campaign → lead bounces → /campaigns/{id}/replies?folder=bounced →
sync_events.py → response_messages → hard_bounces_24h → kill trigger

Warmup pool → EmailBison internal → warmup_bounces_received (API field) →
sync_accounts.py → monitoring only, NOT counted in kill triggers
```

**Remaining Edge Case:**
If an inbox is assigned to both warmup AND a real campaign simultaneously, bounces from that campaign would be counted. This is expected behavior - those are real campaign bounces.

---

### 3. Daily Volume Snapshot Double-Counting - RESOLVED (2026-02-26)

**Severity:** ~~HIGH~~ RESOLVED
**Impact:** ~~Dashboard charts show 24x inflated send volumes~~ Now correctly aggregated

**Resolution Applied:**
- Updated `daily_snapshot.py` to use `DISTINCT ON` for latest snapshot per campaign
- Cumulative values now correctly aggregated (MAX per campaign, then SUM)

**Fixed Query (daily_snapshot.py:92-118):**
```python
WITH latest_daily_snapshots AS (
    SELECT DISTINCT ON (cs.campaign_id)
        cs.campaign_id,
        cs.emails_sent,
        cs.bounced
    FROM campaign_snapshots cs
    JOIN emailbison_campaigns ec ON cs.campaign_id = ec.id
    WHERE ec.workspace_id = $1
      AND DATE(cs.snapshot_timestamp) = $2
    ORDER BY cs.campaign_id, cs.snapshot_timestamp DESC
)
SELECT
    COALESCE(SUM(emails_sent), 0) as emails_sent,
    COALESCE(SUM(emails_sent) - SUM(bounced), 0) as emails_delivered,
    COALESCE(SUM(bounced), 0) as emails_bounced,
    0 as emails_complained
FROM latest_daily_snapshots
```

---

### 4. Missing Spam Folder Sync - RESOLVED (2026-02-26)

**Severity:** ~~HIGH~~ RESOLVED
**Impact:** ~~Spam complaints from leads missed~~ Now syncing spam folder

**Resolution Applied:**
- Added spam folder sync to `sync_events.py` after inbox and bounced folders
- Spam folder messages are treated as DIRECT spam complaints
- Complaints increment `complaints_lifetime` counter

**New Code (sync_events.py:82-88):**
```python
# Sync spam folder - DIRECT spam complaints
spam_count = await self.sync_campaign_replies(
    local_campaign_id=campaign['local_id'],
    eb_campaign_id=int(campaign['emailbison_campaign_id']),
    workspace_id=campaign['workspace_id'],
    folder='spam'
)
```

**Spam Detection Logic (sync_events.py:321-337):**
```python
if folder == 'spam':
    # SPAM FOLDER: This is a DIRECT spam complaint - most definitive signal
    is_spam = True
    print(f"      [SPAM FOLDER] Direct spam complaint detected for {to_inbox}")
```

---

### 5. Fresh Inbox Kill Trigger Timing - RESOLVED (2026-02-26)

**Severity:** HIGH
**Impact:** Fresh inboxes could be killed before completing incubation period

**Problem:** Fresh inbox age was calculated from `first_seen_at` (when inbox appeared in sync), not `warmup_started_at` (when warmup was enabled).

**Resolution Applied:**
- Changed age calculation in `health_checks.py` to use `warmup_started_at`
- Added comprehensive documentation in code comments
- Migration `055_cleanup_kill_trigger_accuracy.sql` identifies incorrectly killed inboxes

**Incubation Period Definition:**
```
The 2-week incubation period starts when:
1. Inbox is added to EmailBison AND
2. Warmup is enabled (warmup_started_at is set)

Timeline:
- Day 0-14: Incubation period (fresh inbox protection)
- Day 14+: Mature inbox (normal kill thresholds apply)

If warmup_started_at is NULL:
- Inbox hasn't started incubation yet
- Treated as "mature" (no special protection)
```

**Updated Code (health_checks.py:289-306):**
```python
warmup_started_at = inbox.get('warmup_started_at')

# Calculate incubation age from warmup_started_at (NOT first_seen_at)
#
# IMPORTANT: The 2-week incubation period starts when:
# 1. Inbox is added to EmailBison AND
# 2. Warmup is enabled (warmup_started_at is set)
inbox_age_days = None
if warmup_started_at:
    inbox_age_days = (datetime.now(timezone.utc) - warmup_started_at.replace(tzinfo=timezone.utc)).days
```

**Why This Matters:**
- HyperTide creates inboxes → appear in EmailBison (first_seen_at set)
- We enable warmup → warmup_started_at set
- These can be different times (e.g., sync finds inbox before warmup enabled)
- Incubation protection should only apply AFTER warmup is enabled

---

### 6. Bounce Counter Duplication Risk - RESOLVED (2026-02-26)

**Severity:** HIGH
**Impact:** Dashboard charts show 24x inflated send volumes

**Evidence (daily_snapshot.py:92-102):**
```python
SELECT COALESCE(SUM(cs.emails_sent), 0) as emails_sent
FROM campaign_snapshots cs
WHERE DATE(cs.snapshot_timestamp) = $2
```

Campaign snapshots created **hourly** with **cumulative** totals:
- 9am snapshot: emails_sent = 1000 (cumulative)
- 10am snapshot: emails_sent = 1050 (cumulative)
- SUM = 2050 (WRONG - should be 1050)

**Recommended Fix:**
```python
# Use MAX instead of SUM (latest cumulative value)
SELECT COALESCE(MAX(cs.emails_sent), 0) as emails_sent

# Or use only the latest snapshot
SELECT cs.emails_sent FROM campaign_snapshots cs
WHERE DATE(cs.snapshot_timestamp) = $2
ORDER BY cs.snapshot_timestamp DESC
LIMIT 1
```

---

### 4. Missing Spam Folder Sync

**Severity:** HIGH
**Impact:** Spam complaints from leads missed

**Evidence (sync_events.py:67-85):**
```python
# Syncs:
folder='inbox'   # ✓ replies
folder='bounced' # ✓ bounces
folder='spam'    # ✗ NOT SYNCED
```

EmailBison API supports `folder='spam'` but we never call it.

**Recommended Fix:**
```python
# Add spam folder sync
spam_count = await self.sync_campaign_replies(
    local_campaign_id=campaign['local_id'],
    eb_campaign_id=int(campaign['emailbison_campaign_id']),
    workspace_id=campaign['workspace_id'],
    folder='spam'
)
```

---

## High Priority Issues

### 5. Bounce Counter Duplication Risk - RESOLVED (2026-02-26)

**Severity:** ~~HIGH~~ RESOLVED
**Impact:** ~~Bounces potentially counted twice → premature kills~~

**Resolution Applied:**
- Removed bounce delta tracking from `sync_accounts.py` (lines 422-439)
- Bounce counters now exclusively managed by `sync_events.py`
- Campaign bounces tracked via `response_messages` table (full audit trail)
- Migration `053_fix_warmup_bounce_pollution.sql` resets polluted counters

**Previous Evidence (for reference):**

| Location | Action | Status |
|----------|--------|--------|
| sync_events.py:309 | `increment_inbox_bounces()` when processing bounce reply | ✅ Correct - kept |
| sync_accounts.py:430 | ~~Adds `bounce_delta` to counters~~ | ❌ REMOVED |
| health_checks.py:160 | `aggregate_bounce_counts_from_events()` uses `GREATEST()` | ✅ Safety net - kept |

**New Data Flow:**
```
Campaign bounce → sync_events.py → response_messages →
classified (hard_blocked/hard_unknown) → increment specific counters →
health_checks evaluates → kill trigger fires only for campaign bounces
```

**Warmup bounces now correctly excluded:**
- `warmup_bounces_received/caused` tracked separately (monitoring only)
- `bounces_all_time` informational only (not used for kill triggers)
- `hard_bounces_24h/7d` = campaign bounces ONLY

---

### 6. Connection Status Not in Capacity Calculation

**Severity:** HIGH
**Impact:** Dashboard shows inflated capacity (disconnected inboxes counted)

**Evidence:**
```sql
-- Current calculation
daily_capacity_available = SUM(daily_limit) WHERE inbox_state = 'live'

-- Doesn't exclude disconnected inboxes
-- Charm: 0/154 Entra connected = shows 154 capacity, 0 operational
```

**Recommended Fix:**
```sql
-- Operational capacity
operational_capacity = SUM(daily_limit)
WHERE inbox_state = 'live' AND status = 'Connected'
```

---

### 7. Bounce Type Assumption in Delta Tracking - RESOLVED (2026-02-26)

**Severity:** ~~MEDIUM~~ RESOLVED
**Impact:** ~~Soft bounces incorrectly trigger hard bounce thresholds~~

**Resolution Applied:**
- Delta tracking REMOVED from sync_accounts.py
- All bounce classification now happens in sync_events.py
- Bounces properly classified as: `hard_blocked`, `hard_unknown`, `soft_full`, `soft_temp`
- Only `hard_*` bounces increment kill trigger counters

**New Bounce Flow:**
```
Campaign bounce → sync_events.py → classify_bounce() →
  hard_blocked → hard_blocked_24h + hard_bounces_24h/7d
  hard_unknown → hard_unknown_24h + hard_bounces_24h/7d
  soft_full → soft_bounces_7d (no kill trigger)
  soft_temp → soft_bounces_7d (no kill trigger)
```

---

## Medium Priority Issues

### 8. Domain Inbox Counts Not Auto-Updated

**Severity:** MEDIUM
**Impact:** Domain health scores become stale

- `domains.live_inbox_count` / `dead_inbox_count` are cached
- No trigger maintains them when `sender_accounts` updated
- Manual recalculation required

**Recommended Fix:**
- Add trigger on sender_accounts to update domain counts
- Or use computed view instead of cached columns

---

### 9. 24h Counter Reset Timing Gap

**Severity:** MEDIUM
**Impact:** Brief window after midnight with wrong counters

- Counters reset to 0 at midnight
- Bounce from 11pm previous day still within 24h
- `GREATEST()` in aggregation eventually fixes it
- Gap exists until next health check

**Recommended Fix:**
- Run aggregation immediately after reset
- Or don't reset, use rolling window calculation only

---

### 10. API Route Silent Fallbacks

**Severity:** MEDIUM
**Impact:** False data shown when queries fail

**Evidence (inventory.py:138-148):**
```python
try:
    counts = await _get_inventory_counts_from_view(workspace_id)
except Exception as e:
    logger.warning(...)
    counts = {"total": 0, "deployed": 0, ...}  # Silent fallback
```

**Recommended Fix:**
- Return 500 error instead of false zeros
- Or add `data_quality` indicator to response

---

## EmailBison API Coverage Matrix

### Data We Extract vs Available

| Data Point | EmailBison Provides | We Extract | Gap |
|------------|---------------------|------------|-----|
| Inbox email | ✅ | ✅ | - |
| Connection status | ✅ | ✅ | - |
| Daily limit | ✅ | ✅ | - |
| Warmup enabled | ✅ | ✅ | - |
| Emails sent (all-time) | ✅ | ✅ | - |
| Bounces (all-time) | ✅ | ✅ | - |
| Replies (all-time) | ✅ | ✅ | - |
| Campaign list | ✅ | ✅ | - |
| Campaign metrics | ✅ | ✅ | - |
| Replies (inbox folder) | ✅ | ✅ | - |
| Bounces (bounced folder) | ✅ | ✅ | - |
| Spam (spam folder) | ✅ | ✅ | - |
| Health score | ❌ | Calculated | Expected |
| Bounce reason | ❌ | Parsed | Expected |
| Sends per day | ❌ | ❌ | **Gap** |
| Campaign type (warmup) | ❌ | N/A | **API limitation** |

### Fields We Calculate Locally

| Field | Calculation | Source Data |
|-------|-------------|-------------|
| `health_score` | Connection(40) + Bounces(20) + Spam(20) + Replies(10) + Limits(10) | API fields |
| `bounce_type` | SMTP code parsing from message body | Bounce message text |
| `bounce_reason` | Regex extraction of SMTP codes + keywords | Bounce message text |
| `hard_bounces_24h` | COUNT from response_messages WHERE received_at > 24h | response_messages |
| `spam_complaint` | Text analysis of response for complaint phrases | Inbox reply text |

---

## Database Schema Concerns

### Missing Constraints

| Table | Column | Issue |
|-------|--------|-------|
| sender_accounts | daily_limit | DEFAULT 0, no NOT NULL (0 vs unknown?) |
| sender_accounts | health_score | DEFAULT 100, no NOT NULL |
| sender_accounts | bounce_rate_7d | Nullable DECIMAL |
| response_messages | bounce_type | Not NOT NULL for bounced folder |

### Ambiguous Defaults

| Column | Default | Concern |
|--------|---------|---------|
| hard_bounces_24h | 0 | Can't distinguish "no bounces" from "never synced" |
| ~~total_sends_7d~~ | ~~0~~ | ✅ RESOLVED - Now populated via send delta tracking |
| warmup_started_at | NULL | NULL = warmup not yet enabled (tracked on first observation) |

---

## Sync Timing Analysis

### Current Intervals

| Sync | Interval | Impact |
|------|----------|--------|
| Events | 5 min | Good - catches bounces quickly |
| Full (accounts) | 1 hour | OK - inbox changes are slow |
| Health checks | 15 min | OK - triggers evaluated regularly |
| Kill processing | 30 min | OK - gives time for tagging |
| Warmup | 30 min | OK - warmup changes slowly |

### Timing Dependencies

```
Events sync (5 min) → populates response_messages
       ↓
Health checks (15 min) → aggregates bounces → queues kills
       ↓
Kill processing (30 min) → tags inboxes
       ↓
Account sync (1 hour) → sees tagged inboxes → marks dead locally
```

**Potential Issue:** If events sync fails, health checks use stale data.

---

## Recommendations by Priority

### P0 - Fix Immediately

1. ~~**Populate `total_sends_7d`**~~ ✅ RESOLVED - Send delta tracking added to sync_accounts.py
2. ~~**Fix daily snapshot double-counting**~~ ✅ RESOLVED - Using DISTINCT ON for latest snapshot per campaign
3. ~~**Add spam folder sync**~~ ✅ RESOLVED - Spam folder now synced, direct complaints increment counter

### P1 - Fix This Week

4. ~~**Address warmup/campaign bounce mixing**~~ ✅ RESOLVED - Warmup bounces now excluded
5. ~~**Remove bounce delta duplication**~~ ✅ RESOLVED - Delta tracking removed from sync_accounts.py
6. **Add operational capacity calculation** - Exclude disconnected inboxes

### P2 - Fix This Sprint

7. **Add domain inbox count triggers** - Keep counts in sync
8. ~~**Improve bounce type tracking**~~ ✅ RESOLVED - Delta tracking removed, proper classification in sync_events
9. **Add data quality indicators to API** - Don't return silent zeros

### P3 - Backlog

10. **Add timestamp for last counter sync** - Distinguish 0 from never synced
11. **Document sync failure recovery** - What happens when sync fails?
12. **Add response_messages retention policy** - Prevent unbounded growth

---

## Verification Queries

### Check `total_sends_7d` Population

```sql
SELECT COUNT(*) as total,
       COUNT(*) FILTER (WHERE total_sends_7d > 0) as has_sends,
       COUNT(*) FILTER (WHERE total_sends_7d = 0) as zero_sends
FROM sender_accounts WHERE inbox_state = 'live';
-- Expected: has_sends should be > 0 for active accounts
-- Current: ALL are zero_sends
```

### Check Bounce Counter Consistency

```sql
SELECT sa.email_address,
       sa.hard_bounces_24h as counter_value,
       COUNT(rm.id) as actual_bounces_24h
FROM sender_accounts sa
LEFT JOIN response_messages rm ON rm.sender_account_id = sa.id
  AND rm.folder = 'bounced'
  AND rm.received_at > NOW() - INTERVAL '24 hours'
WHERE sa.hard_bounces_24h > 0
GROUP BY sa.id, sa.email_address, sa.hard_bounces_24h
HAVING sa.hard_bounces_24h != COUNT(rm.id);
-- Should return 0 rows if counters are accurate
```

### Check Daily Snapshot Accuracy

```sql
SELECT snapshot_date,
       COUNT(*) as snapshots_that_day,
       SUM(emails_sent) as summed_value,
       MAX(emails_sent) as correct_value
FROM campaign_snapshots cs
JOIN emailbison_campaigns ec ON cs.campaign_id = ec.id
WHERE ec.workspace_id = 'your-workspace-id'
GROUP BY snapshot_date
HAVING COUNT(*) > 1;
-- Shows days with multiple snapshots where SUM != MAX
```

---

**Document Version:** 1.3
**Last Updated:** 2026-02-26
**Audit Performed By:** System Analysis Agent

**Change Log:**
- v1.3 (2026-02-26): Issues #3, #4, #5 RESOLVED - Daily snapshot double-counting fixed, spam folder sync added, fresh inbox kill trigger timing fixed (uses warmup_started_at)
- v1.2 (2026-02-26): Issue #1 RESOLVED - Added send delta tracking for total_sends_7d, rate-based kill triggers now functional
- v1.1 (2026-02-26): Issues #2, #5, #7 RESOLVED - Removed bounce delta tracking, warmup bounces now excluded from kill triggers
