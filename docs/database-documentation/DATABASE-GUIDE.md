# Charm Email OS Database Guide
## Complete Guide to Database Navigation, Queries, and Data Flow

**Last Updated:** 2026-02-24
**Version:** 1.0

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Database Overview](#database-overview)
3. [Data Flow Architecture](#data-flow-architecture)
4. [Core Tables Reference](#core-tables-reference)
5. [Common Queries](#common-queries)
6. [Data Dictionary](#data-dictionary)
7. [Business Logic](#business-logic)
8. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Connecting to the Database

```bash
# Local Development
PGPASSWORD=localdevpassword psql -h charm-postgres -U postgres -d postgres

# Production (use credentials from .env)
PGPASSWORD=$POSTGRES_PASSWORD psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB
```

### Essential First Queries

```sql
-- See all workspaces (clients)
SELECT id, workspace_name, sender_account_count FROM workspaces;

-- Check inbox distribution
SELECT esp, inbox_state, COUNT(*) FROM sender_accounts GROUP BY esp, inbox_state;

-- Calculate true burn rate (CRITICAL: Only count kill_trigger IS NOT NULL)
SELECT
    esp,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate_pct
FROM sender_accounts
WHERE esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

### Important Concepts

**❗ CRITICAL DISTINCTIONS:**

| Concept | Wrong Assumption | Correct Understanding |
|---------|------------------|----------------------|
| **Burn Rate** | `inbox_state='dead'` = burned | `kill_trigger IS NOT NULL` = burned |
| **Dead Inbox** | Always means performance failure | Could be healthy disconnection (rotation/subscription) |
| **Infrastructure Type** | `domains.infrastructure_type` | `sender_accounts.esp` field |
| **All-Time Metrics** | Updated in real-time | Synced from EmailBison hourly |

---

## Database Overview

### Database Size & Scale

| Table | Approximate Rows | Update Frequency | Purpose |
|-------|-----------------|------------------|---------|
| `sender_warmup_snapshots` | 46,308 | Every 30 min | Warmup progress tracking |
| `campaign_inboxes` | 20,432 | Hourly | Campaign-inbox assignments |
| `response_messages` | 7,547 | Every 5 min | Reply content storage |
| `sender_accounts` | 6,978 | Hourly | **PRIMARY** inbox table |
| `domains` | 509 | Hourly | Domain health tracking |
| `campaign_events` | 547 | Every 5 min | Email event log |
| `emailbison_campaigns` | 113 | Hourly | Campaign metadata |
| `workspaces` | 16 | Manual | Client accounts |

### Key Enum Types

```sql
-- Inbox lifecycle
'inbox_state': 'live' | 'dead'

-- Email service providers
'esp_type': 'gmail' | 'microsoft' | 'yahoo' | 'other'

-- Kill trigger types (12 defined, 4 actually fire)
'kill_trigger_type':
    'spam_complaint'           -- ✅ Fires (14.68% of kills)
    'hard_bounces_24h'         -- ✅ Fires (17.42% of kills)
    'hard_blocked_24h'         -- ✅ Fires (0.19% of kills)
    'fresh_inbox_bounce'       -- ✅ Fires (67.71% of kills)
    'consecutive_hard_bounces' -- ❌ Never fires
    'hard_bounce_rate_7d'      -- ❌ Never fires
    'bounce_rate_all_7d'       -- ❌ Never fires
    'provider_block'           -- ❌ Never fires
    'placement_failure'        -- ❌ Never fires
    'spam_folder_rate'         -- ❌ Never fires
    'degrading_trend'          -- ❌ Never fires
    'hard_unknown_24h'         -- ❌ Never fires

-- Domain lifecycle
'domain_state': 'live' | 'flagged' | 'dead'

-- Campaign status
'campaign_state': 'live' | 'quarantined' | 'dead'
```

---

## Data Flow Architecture

### External Data Sources

```
┌─────────────────────────────────────────────────────────────┐
│ EmailBison API (spellcast.hirecharm.com)                   │
│ - Sender accounts (inboxes)                                │
│ - Campaigns (outbound sequences)                            │
│ - Events (emails sent/opened/replied/bounced)              │
│ - Warmup status                                            │
│ - Reply messages                                            │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ emailbison_sync_worker.py (Main Orchestrator)              │
│ Location: /home/claw/charm-email-os/emailbison_sync_worker.py │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Sync Modules (/home/claw/charm-email-os/sync_modules/)     │
├─────────────────────────────────────────────────────────────┤
│ • sync_accounts.py     → sender_accounts, domains           │
│ • sync_campaigns.py    → emailbison_campaigns, snapshots    │
│ • sync_events.py       → campaign_events, response_messages │
│ • sync_warmup.py       → sender_warmup_snapshots            │
│ • health_checks.py     → kill_queue, domain health          │
│ • kill_processor.py    → Tags in EmailBison, marks dead     │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ PostgreSQL Database (charm-postgres:5432)                   │
│ 91 tables, 6 enums, multiple views                         │
└─────────────────────────────────────────────────────────────┘
```

### Sync Schedule

| Module | Frequency | Purpose | Tables Updated |
|--------|-----------|---------|----------------|
| **Events** | 5 minutes | Email tracking | campaign_events, response_messages |
| **OAuth Queue** | 5 minutes | OAuth token sync | oauth_sync_queue |
| **Health Checks** | 15 minutes | Kill trigger evaluation | kill_queue, domains |
| **Kill Processor** | 30 minutes | Tag & mark dead | sender_accounts, kill_queue |
| **Warmup Sync** | 30 minutes | Warmup progress | sender_warmup_snapshots |
| **Accounts** | 60 minutes | Inbox sync | sender_accounts, domains |
| **Campaigns** | 60 minutes | Campaign metrics | emailbison_campaigns, snapshots |
| **Daily Cleanup** | Midnight | Counter reset | sender_accounts (bounce counters) |

### Data Freshness

```sql
-- Check when data was last synced
SELECT
    module,
    last_run_at,
    NOW() - last_run_at as time_since_sync,
    records_processed,
    records_created,
    records_updated,
    records_failed
FROM sync_status
ORDER BY last_run_at DESC;
```

---

## Core Tables Reference

### 1. `sender_accounts` (Primary Inbox Table)

**Purpose:** Tracks all email inboxes synced from EmailBison

**Key Relationships:**
- Belongs to: `workspaces` (via `workspace_id`)
- Belongs to: `domains` (via `domain_id`)
- Has many: `campaign_inboxes` (M:M with campaigns)
- Has many: `sender_warmup_snapshots` (time-series)
- May have one: `kill_queue` entry (if triggered)

**Critical Columns:**

| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| `id` | UUID | Primary key | Generated locally |
| `workspace_id` | UUID | Client owner | EmailBison workspace mapping |
| `email_address` | VARCHAR | Full email address | EmailBison API |
| `emailbison_account_id` | TEXT | External sync ID | EmailBison API |
| `inbox_state` | ENUM | Connection status | Derived from EmailBison status |
| `esp` | ENUM | Infrastructure type | EmailBison tags or provider field |
| `kill_trigger` | ENUM | Why inbox was killed | Health check evaluation |
| `killed_at` | TIMESTAMP | When auto-killed | Kill processor |
| `disconnected_at` | TIMESTAMP | When EmailBison disconnected | Account sync |
| `emails_sent_all_time` | INTEGER | Lifetime sends | EmailBison API |
| `bounce_rate_7d` | DECIMAL | 7-day bounce rate | Calculated locally |
| `hard_bounces_24h` | INTEGER | Last 24h hard bounces | Event sync (reset daily) |
| `hard_blocked_24h` | INTEGER | Spam rejections 24h | Event sync (reset daily) |
| `hard_unknown_24h` | INTEGER | Bad addresses 24h | Event sync (reset daily) |

**State Flow:**

```
NEW INBOX PROVISIONED
         ↓
   inbox_state='live'
   kill_trigger=NULL
   killed_at=NULL
         ↓
   (Sending emails...)
         ↓
┌─────────────────────┐
│ Performance Issue?  │
├─────────────────────┤
│ YES → KILL TRIGGER  │
│  ↓                  │
│ kill_trigger='...'  │
│ killed_at=NOW()     │
│ inbox_state='dead'  │
│                     │
│ NO → HEALTHY UNTIL  │
│ DISCONNECTION       │
│  ↓                  │
│ kill_trigger=NULL   │
│ disconnected_at=NOW │
│ inbox_state='dead'  │
└─────────────────────┘
```

**CRITICAL DISTINCTION:**

```sql
-- BURNED inbox (performance kill)
WHERE kill_trigger IS NOT NULL

-- HEALTHY disconnection (rotation/subscription)
WHERE kill_trigger IS NULL AND inbox_state = 'dead'

-- NEVER use inbox_state='dead' alone for burn rate!
```

### 2. `domains`

**Purpose:** Domain-level health tracking and aggregation

**Key Relationships:**
- Belongs to: `workspaces` (via `workspace_id`)
- Has many: `sender_accounts`

**Critical Columns:**

| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| `domain_name` | VARCHAR | Unique domain | UNIQUE constraint (global) |
| `domain_state` | ENUM | Health status | Health check evaluation |
| `infrastructure_type` | VARCHAR | Entra vs Google | **⚠️ NOT POPULATED - Use sender_accounts.esp instead** |
| `live_inbox_count` | INTEGER | Active inboxes | Calculated from sender_accounts |
| `dead_inbox_count` | INTEGER | Dead inboxes | Calculated from sender_accounts |
| `domain_bounce_rate_7d` | DECIMAL | Domain-wide bounce rate | Aggregated from inboxes |
| `burn_breakdown` | JSONB | Count by kill trigger | Aggregated kill_trigger counts |

**Domain State Transitions:**

```
live → flagged (1 dead inbox)
     → dead (≥2 dead inboxes OR >30% unhealthy)
```

**⚠️ KNOWN ISSUE:** `infrastructure_type` column exists but is always NULL. Use `sender_accounts.esp` instead.

### 3. `emailbison_campaigns`

**Purpose:** Campaign metadata from EmailBison

**Key Relationships:**
- Belongs to: `workspaces`
- Has many: `campaign_snapshots` (hourly metrics)
- Has many: `campaign_inboxes` (M:M with sender_accounts)
- Has many: `campaign_events` (email events)

**Critical Columns:**

| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| `emailbison_campaign_id` | TEXT | External campaign ID | EmailBison API |
| `campaign_name` | VARCHAR | Campaign name | EmailBison API |
| `campaign_status` | VARCHAR | active/paused/completed | EmailBison API |
| `emails_sent` | INTEGER | Total sends | EmailBison API |
| `total_leads` | INTEGER | Total prospects | EmailBison API |

### 4. `kill_queue`

**Purpose:** 24-hour waiting period before killing inboxes (allows manual intervention)

**Key Relationships:**
- References: `sender_accounts` (via `inbox_id`)
- References: `workspaces` (via `workspace_id`)

**Status Flow:**

```
Health Check Triggers
         ↓
   status='pending'
   queued_at=NOW()
         ↓
Kill Processor Tags in EmailBison
         ↓
   status='tagged'
   tagged_at=NOW()
   tag_name='delete_queue_YYMMDD'
   scheduled_delete_at=tagged_at + 24hrs
         ↓
   (Wait 24 hours for review)
         ↓
Kill Processor Marks Dead
         ↓
   status='deleted'
   deleted_at=NOW()
   sender_accounts.inbox_state='dead'
   sender_accounts.killed_at=NOW()
   sender_accounts.kill_trigger=type
```

### 5. `daily_volume_snapshots`

**Purpose:** Daily capacity tracking for time-series charts (added in migration 041)

**Key Columns:**

| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| `snapshot_date` | DATE | Date of snapshot | Yesterday's date |
| `emails_sent` | INTEGER | Total emails sent | EmailBison campaigns |
| `daily_capacity_available` | INTEGER | Total sending capacity | SUM(sender_accounts.daily_limit WHERE live) |
| `capacity_utilization_pct` | DECIMAL | % of capacity used | (sent / capacity) * 100 |
| `kills_that_day` | INTEGER | Inboxes killed | Count of killed_at on that date |

---

## Common Queries

### Burn Rate Analysis

#### ✅ CORRECT: True Burn Rate (kill_trigger IS NOT NULL)

```sql
-- Burn rate by ESP
SELECT
    esp,
    COUNT(*) as total_inboxes,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    COUNT(*) FILTER (WHERE kill_trigger IS NULL AND inbox_state = 'dead') as healthy_disconnected,
    COUNT(*) FILTER (WHERE inbox_state = 'live') as active,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate_pct
FROM sender_accounts
WHERE workspace_id = '<workspace_uuid>'
  AND esp IN ('microsoft', 'gmail')
GROUP BY esp
ORDER BY burn_rate_pct DESC;
```

#### ❌ WRONG: Using inbox_state='dead'

```sql
-- DON'T DO THIS - includes healthy disconnections!
SELECT
    esp,
    COUNT(*) FILTER (WHERE inbox_state = 'dead') / COUNT(*) as burn_rate  -- WRONG!
FROM sender_accounts
GROUP BY esp;
```

### Volume-Adjusted Burn Rate

```sql
-- Burns per million emails sent (accounts for sending volume differences)
SELECT
    esp,
    COUNT(*) as total_inboxes,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    SUM(emails_sent_all_time) as total_volume,
    ROUND(
        1000000.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) /
        NULLIF(SUM(emails_sent_all_time), 0),
        2
    ) as burns_per_million_emails
FROM sender_accounts
WHERE workspace_id = '<workspace_uuid>'
  AND esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

### Kill Trigger Breakdown

```sql
-- What's killing inboxes?
SELECT
    esp,
    kill_trigger,
    COUNT(*) as kill_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY esp), 2) as pct_of_provider_kills,
    ROUND(AVG(emails_sent_all_time), 0) as avg_emails_before_kill
FROM sender_accounts
WHERE kill_trigger IS NOT NULL
  AND esp IN ('microsoft', 'gmail')
GROUP BY esp, kill_trigger
ORDER BY esp, kill_count DESC;
```

### Client Comparison (Dual-Provider Only)

```sql
-- Only compare clients with BOTH Microsoft AND Google
WITH dual_provider_workspaces AS (
    SELECT workspace_id
    FROM sender_accounts
    WHERE esp IN ('microsoft', 'gmail')
    GROUP BY workspace_id
    HAVING COUNT(DISTINCT esp) = 2
)
SELECT
    w.workspace_name as client,
    sa.esp as provider,
    COUNT(sa.id) as total_inboxes,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) as burned,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NULL AND sa.inbox_state = 'dead') as healthy_disconnected,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) / COUNT(sa.id), 2) as burn_rate,
    SUM(sa.emails_sent_all_time) as total_volume
FROM sender_accounts sa
JOIN dual_provider_workspaces dpw ON sa.workspace_id = dpw.workspace_id
JOIN workspaces w ON sa.workspace_id = w.id
WHERE sa.esp IN ('microsoft', 'gmail')
GROUP BY w.workspace_name, sa.esp
ORDER BY w.workspace_name, sa.esp;
```

### Domain Health Summary

```sql
-- Domains ranked by health
SELECT
    d.domain_name,
    d.domain_state,
    d.live_inbox_count,
    d.dead_inbox_count,
    ROUND(d.domain_bounce_rate_7d, 4) as bounce_rate_7d,
    d.burn_breakdown::jsonb as kill_breakdown
FROM domains d
WHERE d.workspace_id = '<workspace_uuid>'
  AND d.sender_account_count > 0
ORDER BY d.domain_bounce_rate_7d DESC NULLS LAST
LIMIT 20;
```

### Daily Capacity Trends

```sql
-- Last 90 days of sending capacity
SELECT
    snapshot_date,
    emails_sent,
    daily_capacity_available,
    ROUND(capacity_utilization_pct, 1) as capacity_used_pct,
    live_inboxes,
    incubating_inboxes,
    kills_that_day
FROM daily_volume_snapshots
WHERE workspace_id = '<workspace_uuid>'
  AND snapshot_date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY snapshot_date DESC;
```

### Active Campaigns

```sql
-- Current campaign performance
SELECT
    c.campaign_name,
    c.campaign_status,
    c.emails_sent,
    c.total_leads_contacted,
    ROUND(100.0 * c.unique_replies / NULLIF(c.emails_sent, 0), 2) as reply_rate_pct,
    ROUND(100.0 * c.bounced / NULLIF(c.emails_sent, 0), 2) as bounce_rate_pct,
    c.spam_complaints,
    COUNT(ci.sender_account_id) as inboxes_assigned
FROM emailbison_campaigns c
LEFT JOIN campaign_inboxes ci ON ci.campaign_id = c.id
WHERE c.workspace_id = '<workspace_uuid>'
  AND c.is_active = TRUE
GROUP BY c.id, c.campaign_name, c.campaign_status, c.emails_sent, c.total_leads_contacted,
         c.unique_replies, c.bounced, c.spam_complaints
ORDER BY c.last_seen_at DESC;
```

### Recent Kills

```sql
-- Inboxes killed in last 7 days
SELECT
    sa.email_address,
    sa.esp,
    sa.kill_trigger,
    sa.killed_at,
    sa.emails_sent_all_time,
    sa.bounce_rate_7d,
    d.domain_name
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.workspace_id = '<workspace_uuid>'
  AND sa.killed_at >= NOW() - INTERVAL '7 days'
ORDER BY sa.killed_at DESC;
```

### Warmup Pipeline

```sql
-- Inboxes currently warming up
SELECT
    sa.email_address,
    sa.esp,
    sa.warmup_started_at,
    EXTRACT(DAY FROM NOW() - sa.warmup_started_at) as days_warming,
    14 - EXTRACT(DAY FROM NOW() - sa.warmup_started_at) as days_remaining,
    sa.emails_sent_all_time as warmup_emails_sent,
    d.domain_name
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.workspace_id = '<workspace_uuid>'
  AND sa.warmup_enabled = TRUE
  AND sa.inbox_state = 'live'
ORDER BY sa.warmup_started_at DESC;
```

---

## Data Dictionary

### Critical Field Clarifications

#### `sender_accounts.inbox_state` vs `kill_trigger`

| Field | Values | Business Meaning | Use For |
|-------|--------|------------------|---------|
| `inbox_state` | `live`, `dead` | Connection status to EmailBison | Filtering active inboxes |
| `kill_trigger` | `NULL`, kill_trigger_type | Performance termination reason | **Burn rate calculation** |

**❗ CRITICAL:**
- `inbox_state='dead'` does NOT mean "burned"
- `kill_trigger IS NOT NULL` = burned (performance issue)
- `kill_trigger IS NULL AND inbox_state='dead'` = healthy disconnection (rotation/subscription)

**Example:**
```sql
-- Microsoft has 4,206 inboxes marked dead but NOT burned
SELECT COUNT(*)
FROM sender_accounts
WHERE esp = 'microsoft'
  AND inbox_state = 'dead'
  AND kill_trigger IS NULL;  -- These were HEALTHY when disconnected
```

#### `sender_accounts.esp` vs `domains.infrastructure_type`

| Field | Status | Use For |
|-------|--------|---------|
| `sender_accounts.esp` | ✅ **POPULATED** | Infrastructure performance analysis |
| `domains.infrastructure_type` | ❌ **ALWAYS NULL** | Do not use |

**Why?**
- Inboxes provisioned via Hypertide (external supplier), not through internal purchase system
- `esp` field synced from EmailBison API tags
- `infrastructure_type` column exists for future use but never populated

#### Bounce Counter Fields (Reset Daily at Midnight)

| Field | Meaning | Reset Schedule | Threshold |
|-------|---------|----------------|-----------|
| `hard_bounces_24h` | All hard bounces in last 24h | Daily at midnight | ≥2 |
| `hard_blocked_24h` | Spam/policy rejections (5.7.x) | Daily at midnight | ≥1 |
| `hard_unknown_24h` | Bad addresses (5.1.x) | Daily at midnight | ≥3 |

**Why Reset?**
Without daily reset, counters would accumulate forever and kill legitimate inboxes.

#### Date Field Meanings

| Field | Meaning | Set By | Nullable |
|-------|---------|--------|----------|
| `created_at` | When record first created locally | Database insert | No |
| `first_seen_at` | When first appeared in EmailBison | Account sync | No |
| `last_seen_at` | Last sync from EmailBison | Account sync | No |
| `warmup_started_at` | When warmup began | EmailBison API | Yes |
| `sending_started_at` | When moved to outbound sending | EmailBison API | Yes |
| `killed_at` | When auto-killed by system | Kill processor | Yes |
| `disconnected_at` | When EmailBison status changed to "Not connected" | Account sync | Yes |

**CRITICAL DISTINCTION:**
- `killed_at IS NOT NULL` = System killed (performance issue)
- `killed_at IS NULL` but `disconnected_at IS NOT NULL` = Disconnected without kill

---

## Business Logic

### Kill Trigger Evaluation (Every 15 Minutes)

**Location:** `/home/claw/charm-email-os/sync_modules/health_checks.py`

**Evaluation Priority (Lines 236-323):**

1. **Spam Complaints** (≥1) → Instant kill
2. **Provider Block** (hard_blocked_24h ≥1 AND esp IN gmail/microsoft/yahoo) → Instant kill
3. **Hard Blocked** (hard_blocked_24h ≥1) → Reputation damage
4. **Hard Unknown** (hard_unknown_24h ≥3) → List quality
5. **Combined Hard Bounces** (hard_bounces_24h ≥2) → Fallback
6. **Hard Bounce Rate 7d** (>0.5%, min 50 sends) → Sustained issue
7. **Total Bounce Rate 7d** (>5%, min 50 sends) → General deliverability
8. **Fresh Inbox Bounce** (any bounce on inbox <14 days) → Warmup failure

**Kill Queue Flow:**

```
Health Check Detects Issue
         ↓
INSERT INTO kill_queue (status='pending')
         ↓
   (Wait for kill processor - every 30 min)
         ↓
Tag in EmailBison with 'delete_queue_YYMMDD'
UPDATE kill_queue SET status='tagged', scheduled_delete_at=+24hrs
         ↓
   (Wait 24 hours for manual review)
         ↓
UPDATE sender_accounts SET inbox_state='dead', killed_at=NOW(), kill_trigger=type
UPDATE kill_queue SET status='deleted'
```

### Domain Health State Machine

**Location:** `/home/claw/charm-email-os/sync_modules/health_checks.py` (Lines 440-468)

```
live → flagged (1 dead inbox)
     → dead (≥2 dead inboxes OR >30% inboxes unhealthy)
```

**Calculation:**
```python
dead_count = COUNT(sender_accounts WHERE inbox_state='dead')
total_count = COUNT(sender_accounts)
unhealthy_pct = dead_count / total_count

if dead_count >= 2 OR unhealthy_pct > 0.30:
    domain_state = 'dead'
elif dead_count == 1:
    domain_state = 'flagged'
else:
    domain_state = 'live'
```

---

## Troubleshooting

### "Why is burn rate so high?"

**Check:**
1. Are you using `kill_trigger IS NOT NULL` or `inbox_state='dead'`?
   - Wrong: `WHERE inbox_state='dead'` (includes healthy disconnections)
   - Correct: `WHERE kill_trigger IS NOT NULL` (only performance kills)

2. Are you comparing clients with different providers?
   - Only compare within same client (dual-provider analysis)
   - Client quality (copy, targeting) affects burn rate

3. Are you accounting for sending volume?
   - Calculate burns per million emails sent
   - Higher volume = more exposure to spam filters

### "Where is infrastructure_type data?"

**Answer:** Use `sender_accounts.esp` field, not `domains.infrastructure_type`

```sql
-- ✅ CORRECT
SELECT esp, COUNT(*) FROM sender_accounts GROUP BY esp;

-- ❌ WRONG (always NULL)
SELECT infrastructure_type FROM domains;
```

### "Why are counters not resetting?"

**Check:**
- Daily cleanup runs at midnight (see `sync_status` table)
- If bounce counters keep growing, check if cleanup is failing

```sql
-- Check last cleanup
SELECT * FROM sync_status WHERE module = 'daily_cleanup';

-- Manually reset if needed (emergency only)
UPDATE sender_accounts SET
    hard_bounces_24h = 0,
    hard_blocked_24h = 0,
    hard_unknown_24h = 0
WHERE hard_bounces_24h > 0;
```

### "Data seems stale"

**Check sync status:**
```sql
SELECT
    module,
    last_run_at,
    NOW() - last_run_at as time_since_sync,
    records_processed,
    records_failed,
    success
FROM sync_status
ORDER BY last_run_at DESC;
```

**Expected sync intervals:**
- Events: <5 minutes
- Accounts: <60 minutes
- Health checks: <15 minutes

If stale, check `emailbison_sync_worker.py` is running:
```bash
ps aux | grep emailbison_sync_worker
```

---

## Related Documentation

- [Kill Trigger Reference](./kill-triggers.md) - Detailed trigger definitions
- [ADR-005: Differentiated Bounce Thresholds](../adr/adr-005-differentiated-bounce-thresholds.md)
- [Schema Migrations](../migrations/) - All schema changes
- [Sync Module Code](../sync_modules/) - Data sync implementations

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│ BURN RATE CALCULATION                                       │
├─────────────────────────────────────────────────────────────┤
│ ✅ CORRECT:                                                 │
│   COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL)         │
│                                                             │
│ ❌ WRONG:                                                   │
│   COUNT(*) FILTER (WHERE inbox_state='dead')               │
│                                                             │
│ REASON: inbox_state='dead' includes healthy disconnections │
│         (rotation, subscription cancellation)               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ INFRASTRUCTURE TYPE                                         │
├─────────────────────────────────────────────────────────────┤
│ ✅ USE: sender_accounts.esp                                 │
│ ❌ DON'T USE: domains.infrastructure_type (always NULL)     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ KILL TRIGGERS THAT ACTUALLY FIRE                           │
├─────────────────────────────────────────────────────────────┤
│ 1. fresh_inbox_bounce    (67.71% of kills)                 │
│ 2. hard_bounces_24h      (17.42% of kills)                 │
│ 3. spam_complaint        (14.68% of kills)                 │
│ 4. hard_blocked_24h      ( 0.19% of kills)                 │
│                                                             │
│ (8 other triggers defined but never fire)                  │
└─────────────────────────────────────────────────────────────┘
```

---

**Last Updated:** 2026-02-24
**Maintainer:** Engineering Team
**Questions?** Check [DATABASE-ANALYSIS-RETROSPECTIVE.md](../../secure-openclaw/DATABASE-ANALYSIS-RETROSPECTIVE.md) for common pitfalls and lessons learned.
