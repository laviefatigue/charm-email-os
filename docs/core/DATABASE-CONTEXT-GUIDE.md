# Charm Email OS - Database Context Guide

**Last Updated:** 2026-02-26
**Purpose:** Comprehensive reference for database schema, state machines, and sync architecture

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Key Tables](#key-tables)
3. [State Machines](#state-machines)
4. [Kill Trigger System](#kill-trigger-system)
5. [Domain Health Model](#domain-health-model)
6. [Capacity Calculations](#capacity-calculations)
7. [Sync Architecture](#sync-architecture)
8. [Migration History](#migration-history)
9. [Views Reference](#views-reference)
10. [Known Issues & Fixes](#known-issues--fixes)
11. [API Field Mappings](#api-field-mappings)

---

## Core Concepts

### The Fundamental Distinction: inbox_state vs status

**CRITICAL:** These are two completely different concepts that are often confused:

| Field | Purpose | Values | Set By |
|-------|---------|--------|--------|
| `inbox_state` | Kill-based lifecycle | `'live'`, `'dead'` | kill_processor.py when triggers fire |
| `status` | OAuth connection | `'Connected'`, `'Not connected'`, `'Disconnected'`, `'Disabled'` | EmailBison API via sync_accounts.py |

**Key Rules:**
- A `'live'` inbox can be `'Not connected'` (OAuth expired but not killed)
- A `'dead'` inbox was killed by a trigger (bounces, spam, timeout)
- Only `'Disabled'` status (explicit user action in EmailBison) causes `inbox_state='dead'` during sync
- `'Not connected'` inboxes stay `'live'` but have 0 operational capacity

### Operational Capacity

**Definition:** The actual sending capacity available right now.

```
Operational Capacity = SUM(daily_limit) WHERE inbox_state='live' AND status='Connected'
```

**NOT:**
```
Total Capacity = SUM(daily_limit) WHERE inbox_state='live'  -- WRONG: includes disconnected
```

### Workspace Hierarchy

```
Workspace (from EmailBison)
    └── Client (business entity)
        └── Subscription (package configuration)
            └── Domains (email domains)
                └── Sender Accounts (inboxes)
                    └── Campaigns (assigned to inboxes)
                        └── Response Messages (bounces, replies, spam)
```

---

## Key Tables

### sender_accounts

The core inbox table. Primary fields:

```sql
-- Identity
id                      UUID PRIMARY KEY
email_address           TEXT UNIQUE
emailbison_account_id   INTEGER          -- External sync ID
workspace_id            UUID             -- Links to workspaces
domain_id               UUID             -- Links to domains

-- State (kill-based)
inbox_state             TEXT             -- 'live' or 'dead'
killed_at               TIMESTAMP        -- When killed (NULL if live)
kill_trigger            kill_trigger_type -- What caused the kill
kill_reason             TEXT             -- Human-readable explanation

-- Connection (OAuth-based)
status                  TEXT             -- 'Connected', 'Not connected', 'Disconnected', 'Disabled'
disconnected_at         TIMESTAMP        -- When OAuth was lost (NULL if connected)

-- Health Metrics (24h counters reset daily at midnight)
hard_bounces_24h        INTEGER DEFAULT 0
hard_blocked_24h        INTEGER DEFAULT 0    -- Spam/policy rejections
hard_unknown_24h        INTEGER DEFAULT 0    -- Bad email addresses
complaints_lifetime     INTEGER DEFAULT 0    -- Never reset (1 = death)

-- Health Metrics (7d rolling - decayed daily by 0.86)
hard_bounces_7d         INTEGER DEFAULT 0
soft_bounces_7d         INTEGER DEFAULT 0
total_sends_7d          INTEGER DEFAULT 0
bounce_rate_7d          DECIMAL(5,4)         -- Computed: bounces / sends

-- Warmup Tracking
warmup_enabled          BOOLEAN
warmup_started_at       TIMESTAMP        -- When warmup first observed (NOT created_at+7d)
warmup_score            INTEGER          -- 0-100 from EmailBison

-- Inventory Management
inventory_lifecycle_status  TEXT         -- 'incubating', 'active', 'dead'
inventory_pool_status       TEXT         -- 'reserve', 'incubating', 'deployed', 'warning'
daily_limit                 INTEGER      -- Max sends per day

-- Provider
esp                     TEXT             -- 'microsoft' (Entra) or 'gmail' (Google)
```

### domains

Domain-level tracking:

```sql
id                      UUID PRIMARY KEY
domain_name             TEXT
workspace_id            UUID

-- State
domain_state            domain_state     -- 'live', 'flagged', 'dead'
is_active               BOOLEAN DEFAULT TRUE

-- Health Aggregates (updated by health_checks.py)
live_inbox_count        INTEGER DEFAULT 0
dead_inbox_count        INTEGER DEFAULT 0
health_percentage       DECIMAL(5,2)
latest_health_score     INTEGER

-- Domain-wide Metrics (from migration 037)
domain_bounce_rate_7d   DECIMAL(5,4)
inboxes_with_complaints INTEGER DEFAULT 0
inboxes_with_blocks     INTEGER DEFAULT 0

-- Source Tracking
domain_source           TEXT             -- 'generated', 'purchased', 'legacy'

-- Infrastructure
infrastructure_type     TEXT             -- 'entra' or 'google'
```

### kill_queue

Pending kill operations:

```sql
id                      UUID PRIMARY KEY
inbox_id                UUID             -- FK to sender_accounts
workspace_id            UUID
status                  TEXT             -- 'pending', 'flagged', 'error'
trigger_type            TEXT             -- What caused the kill
trigger_value           DECIMAL          -- Actual value that exceeded threshold
trigger_threshold       DECIMAL          -- The threshold that was exceeded
created_at              TIMESTAMP
processed_at            TIMESTAMP
error_message           TEXT
```

### response_messages

Bounce and reply tracking (source of truth for bounce counters):

```sql
id                      UUID PRIMARY KEY
sender_account_id       UUID             -- FK to sender_accounts
campaign_id             UUID             -- FK to emailbison_campaigns
folder                  TEXT             -- 'bounced', 'replied', 'spam', 'inbox'
bounce_type             TEXT             -- 'hard_blocked', 'hard_unknown', 'soft_full', etc.
received_at             TIMESTAMP
message_id              TEXT             -- EmailBison message ID
subject                 TEXT
body_preview            TEXT
```

### daily_volume_snapshots

Historical capacity tracking for dashboards:

```sql
workspace_id            UUID
snapshot_date           DATE
emails_sent             INTEGER
emails_delivered        INTEGER
emails_bounced          INTEGER
daily_capacity_available INTEGER         -- CONNECTED inboxes only
live_inboxes            INTEGER
incubating_inboxes      INTEGER
dead_inboxes            INTEGER
capacity_utilization_pct DECIMAL
kills_that_day          INTEGER

PRIMARY KEY (workspace_id, snapshot_date)
```

---

## State Machines

### Inbox State Machine

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                        LIVE                                 │
                    │  (inbox_state='live', status='Connected')                   │
                    │  Operational: YES                                           │
                    └────────────────────────┬────────────────────────────────────┘
                                             │
               OAuth expires (status changes to 'Not connected')
               → disconnected_at = NOW()
                                             │
                                             ▼
                    ┌─────────────────────────────────────────────────────────────┐
                    │                    DISCONNECTED                             │
                    │  (inbox_state='live', status='Not connected')               │
                    │  Operational: NO (0 capacity contribution)                  │
                    │  disconnected_at is set                                     │
                    └────────────────────────┬────────────────────────────────────┘
                                             │
           ┌─────────────────────────────────┼─────────────────────────────────┐
           │                                 │                                 │
    OAuth reconnected              21 days disconnected              Kill trigger fires
    status='Connected'             disconnected_timeout              (bounces, spam, etc.)
    → disconnected_at=NULL                   │                                 │
           │                                 │                                 │
           ▼                                 ▼                                 ▼
    ┌─────────────┐               ┌─────────────────────┐           ┌─────────────────────┐
    │    LIVE     │               │        DEAD         │           │        DEAD         │
    │ (connected) │               │  (timeout kill)     │           │  (trigger kill)     │
    └─────────────┘               │  kill_trigger=      │           │  kill_trigger=      │
                                  │  'disconnected_     │           │  specific trigger   │
                                  │   timeout'          │           │                     │
                                  └─────────────────────┘           └─────────────────────┘
```

### Domain State Machine

```
                              ┌─────────────────────┐
                              │        LIVE         │
                              │  live_inbox_count>0 │
                              │  dead_inbox_count=0 │
                              │  OR all connected   │
                              └──────────┬──────────┘
                                         │
            ┌────────────────────────────┼────────────────────────────┐
            │                            │                            │
     1 inbox dies               All live inboxes            2+ inboxes die
     dead_inbox_count=1         become disconnected         OR >30% unhealthy
            │                   (0 operational capacity)              │
            ▼                            │                            ▼
    ┌───────────────┐                    ▼                    ┌───────────────┐
    │    FLAGGED    │            ┌───────────────┐            │     DEAD      │
    │  Warning state │           │    FLAGGED    │            │  No recovery  │
    │  Accelerate    │           │ all_disconn.  │            │  HyperTide    │
    │  backup warming│           │ 0 operational │            │  order needed │
    └───────────────┘            │ capacity      │            └───────────────┘
                                 └───────────────┘
```

### Inventory Lifecycle Status

```
incubating (0-14 days from warmup_started_at)
    │
    │ warmup_started_at + 14 days
    ▼
active (14+ days, inbox_state='live')
    │
    │ Kill trigger fires
    ▼
dead (inbox_state='dead')
```

### Inventory Pool Status

```
reserve (warmup ready, not yet deployed to campaigns)
    │
    │ Added to campaign (campaigns > 0)
    ▼
incubating (in campaign but < 14 days old)
    │
    │ warmup_started_at + 14 days
    ▼
deployed (active in campaigns, > 14 days)
    │
    │ hard_bounces_24h >= 1 (warning signs)
    ▼
warning (at risk, needs monitoring)
    │
    │ Kill trigger fires
    ▼
NULL (inbox_state='dead', removed from pool)
```

---

## Kill Trigger System

### Trigger Priority (highest to lowest)

| Priority | Trigger | Threshold | Severity | Description |
|----------|---------|-----------|----------|-------------|
| 0 | `spam_complaint` | ≥ 1 | instant | 1 complaint = death, no exceptions |
| 0.5 | `provider_block_{esp}` | ≥ 1 blocked | instant | Gmail/Microsoft/Yahoo block |
| 1 | `hard_blocked_24h` | ≥ 1 | instant | Spam/policy rejection (reputation damage) |
| 2 | `hard_unknown_24h` | ≥ 3 | instant | Bad email addresses (list quality) |
| 3 | `hard_bounces_24h` | ≥ 2 | instant | Combined hard bounces (fallback) |
| 4 | `hard_bounce_rate_7d` | > 0.5% | instant | Rate-based (min 20 sends) |
| 5 | `bounce_rate_all_7d` | > 5% | instant | Total bounce rate (hard + soft) |
| 6 | `fresh_inbox_bounce` | ≥ 1 | instant | Any bounce on inbox < 14 days old |
| 7 | `disconnected_timeout` | ≥ 21 days | instant | OAuth disconnected for 21+ days |

### Bounce Classification

```
HARD BOUNCES (permanent failures, 5xx):
├── hard_blocked: 550 5.7.x (spam/policy rejection)
│   ├── 550 5.7.1 "rejected by policy"
│   ├── 550 5.7.51 "user reported spam" (Microsoft)
│   └── 550 5.7.511 "blocked sender" (Microsoft)
│
├── hard_unknown: 550 5.1.x (invalid address)
│   ├── 550 5.1.1 "user unknown"
│   └── 550 5.1.0 "address rejected"
│
└── hard_other: Unclassified 5xx errors

SOFT BOUNCES (temporary failures, 4xx):
├── soft_full: 452 4.2.2 "mailbox full"
├── soft_temp: 421 4.7.0 "temporary failure"
└── soft_other: Unclassified 4xx errors
```

### Kill Processing Flow

```
1. sync_events.py detects bounce/spam
   ↓
2. Increments bounce counters on sender_accounts
   ↓
3. health_checks.py evaluates thresholds
   ↓
4. If threshold exceeded → INSERT INTO kill_queue
   ↓
5. kill_processor.py processes queue:
   a. Tag inbox in EmailBison: "flagged_{trigger_type}"
   b. UPDATE sender_accounts SET inbox_state='dead', killed_at=NOW()
   c. UPDATE domain counts and state
   d. Log to campaign_burn_events
   e. Promote backup inbox if available
   ↓
6. Mark kill_queue entry as 'flagged'
```

---

## Domain Health Model

### Domain State Determination

```sql
-- Priority order (first match wins):
CASE
    -- 2+ dead inboxes = domain dead
    WHEN dead_inbox_count >= 2 THEN 'dead'

    -- >30% unhealthy = domain dead
    WHEN health_percentage < 70 THEN 'dead'

    -- All live inboxes disconnected = flagged (0 operational capacity)
    WHEN live_inbox_count > 0 AND connected_count = 0 THEN 'flagged'

    -- 1 dead inbox = flagged (warning)
    WHEN dead_inbox_count >= 1 THEN 'flagged'

    -- Otherwise live
    ELSE 'live'
END
```

### Domain-Wide Triggers (not inbox-level)

| Condition | Action |
|-----------|--------|
| `domain_bounce_rate_7d > 5%` | Flag domain for review |
| `inboxes_with_complaints >= 2` | Flag domain (cross-inbox spam pattern) |
| `inboxes_with_blocks >= 2` | Flag domain (cross-inbox block pattern) |
| All live inboxes disconnected | Flag domain (0 operational capacity) |

---

## Capacity Calculations

### Daily Capacity (Operational)

```sql
-- CORRECT: Only connected inboxes
SELECT COALESCE(SUM(daily_limit), 0)
FROM sender_accounts
WHERE workspace_id = $1
  AND inbox_state = 'live'
  AND status = 'Connected';
```

### Expected Capacity (HyperTide Model)

| Provider | Inboxes/Domain | Daily Limit/Inbox | Expected/Domain |
|----------|----------------|-------------------|-----------------|
| Entra | 50 | 2 | 100 emails/day |
| Google | 3 | 20 | 60 emails/day |

### Capacity Utilization

```sql
-- Per workspace
SELECT
    (emails_sent / daily_capacity_available) * 100 as utilization_pct
FROM daily_volume_snapshots
WHERE workspace_id = $1
  AND snapshot_date = CURRENT_DATE - 1;
```

### Viability Status (Domain Level)

| Status | Condition | Meaning |
|--------|-----------|---------|
| `awaiting_provisioning` | 0 total inboxes | Never had inboxes, not in health calculation |
| `deprecated` | 0 live inboxes, had inboxes before | All inboxes killed, domain dead |
| `all_disconnected` | live > 0 AND connected = 0 | Has inboxes but 0 operational capacity |
| `critical` | connected capacity < 40% of expected | Severe capacity loss |
| `warning` | connected capacity < 70% of expected | Moderate capacity loss |
| `healthy` | connected capacity ≥ 70% of expected | Normal operation |

---

## Sync Architecture

### Module Responsibilities

| Module | Schedule | Purpose |
|--------|----------|---------|
| `sync_accounts.py` | 1 hour | Sync inbox data from EmailBison, set disconnected_at |
| `sync_events.py` | 5 min | Sync bounces/replies, increment bounce counters |
| `sync_campaigns.py` | 1 hour | Sync campaign data and assignments |
| `health_checks.py` | 15 min | Evaluate triggers, queue kills, flag domains |
| `kill_processor.py` | 30 min | Process kill queue, tag in EmailBison |
| `daily_snapshot.py` | midnight | Capture capacity snapshot for dashboards |

### Execution Order (Critical)

```
1. sync_events.py     ← Fresh bounce data
2. sync_accounts.py   ← Update inbox states
3. health_checks.py   ← Detect triggers using fresh data
4. kill_processor.py  ← Process triggered kills
5. daily_snapshot.py  ← Capture final state
```

### Counter Management

**24h Counters:**
- Reset to 0 daily at midnight UTC
- Used for instant kill triggers
- Fields: `hard_bounces_24h`, `hard_blocked_24h`, `hard_unknown_24h`

**7d Counters:**
- Decayed daily by 0.86 factor (~14% reduction)
- Approximates rolling 7-day window
- Fields: `hard_bounces_7d`, `soft_bounces_7d`, `total_sends_7d`

**Lifetime Counters:**
- Never reset
- Fields: `complaints_lifetime`, `bounces_all_time`

---

## Migration History

### Core Schema (Pre-2026)
- Basic sender_accounts, domains, campaigns tables
- Simple inbox_state tracking

### 2026-02 Migrations

| Migration | Purpose |
|-----------|---------|
| 032 | Domain source tracking (`domain_source` column) |
| 033 | Backfill `killed_at` for 5528 dead inboxes |
| 034 | Bounce counter reset function |
| 035 | Performance indexes (SPLIT_PART, composites) |
| 036 | Campaign burn events table + views |
| 037 | Domain aggregate metrics (domain-wide bounce rate) |
| 038 | Domain capacity views (HyperTide model) |
| 039 | Client capacity views (package vs actual) |
| 040 | Fix inventory status consistency |
| 041 | Daily volume snapshots table |
| 043 | Fix warmup date violations + constraint |
| 044 | Fix warmup_started_at = first observation |
| 051 | Fix inbox_state for 'Not connected' (was incorrectly marking as dead) |
| 052 | Connection status tracking in waterfall view |
| 056 | Fix domain state consistency (153 domains with 0 inboxes marked live) |
| 057 | Add `disconnected_at` column, 21-day auto-kill |
| 058 | Update capacity views for connection status |

### Key Bug Fixes

**Migration 051 Fix:**
- **Bug:** Old sync code treated `status='Not connected'` as dead
- **Fix:** Only `status='Disabled'` causes `inbox_state='dead'`
- **Impact:** 1938 inboxes were incorrectly marked dead

**Migration 056 Fix:**
- **Bug:** 153 domains marked 'live' with 0 inboxes
- **Fix:** Auto-correct domain_state based on inbox counts

---

## Views Reference

### v_infrastructure_waterfall

Primary view for infrastructure provisioning UI. 44+ columns including:

```sql
SELECT
    domain_id, domain_name, workspace_id,
    -- Pricing
    cached_price, porkbun_price, dynadot_price,
    -- Purchase
    purchased_at, purchase_job_id,
    -- DNS
    nameserver_status, spf_configured, dkim_configured,
    -- Provider
    assigned_provider, detected_provider,
    -- Inbox counts
    live_inbox_count, dead_inbox_count,
    connected_inbox_count, disconnected_inbox_count,  -- NEW in 052
    -- Stage
    current_stage  -- 1-9 progression
FROM v_infrastructure_waterfall;
```

### v_domain_capacity

Domain health and capacity metrics:

```sql
SELECT
    domain_id, domain_name, provider_type,
    -- Counts
    total_inboxes, live_inboxes, dead_inboxes,
    connected_inboxes, disconnected_inboxes,  -- NEW in 058
    -- Capacity
    current_daily_capacity,      -- CONNECTED only (058)
    potential_daily_capacity,    -- If all reconnected (058)
    expected_daily_capacity,     -- HyperTide model
    capacity_utilization_pct,
    connection_ratio_pct,        -- NEW in 058
    -- Status
    viability_status  -- 'healthy', 'warning', 'critical', 'deprecated', 'all_disconnected'
FROM v_domain_capacity;
```

### v_client_capacity

Client package vs actual capacity:

```sql
SELECT
    client_id, client_name,
    -- Targets (from subscription)
    entra_domains_target, entra_inboxes_target,
    -- Actuals
    entra_domains_actual, entra_inboxes_live,
    entra_inboxes_connected, entra_inboxes_disconnected,  -- NEW in 058
    -- Gaps
    entra_inbox_gap,   -- Against CONNECTED (058)
    entra_domain_gap,  -- Excludes all_disconnected (058)
    -- Health
    entra_connection_ratio_pct  -- NEW in 058
FROM v_client_capacity;
```

### v_domains_at_risk

Filtered view of domains needing attention:

```sql
SELECT * FROM v_domain_capacity
WHERE viability_status IN ('warning', 'critical', 'deprecated', 'all_disconnected')
ORDER BY
    CASE viability_status
        WHEN 'deprecated' THEN 1       -- Completely dead
        WHEN 'all_disconnected' THEN 2 -- 0 operational capacity
        WHEN 'critical' THEN 3         -- <40% capacity
        WHEN 'warning' THEN 4          -- <70% capacity
    END;
```

---

## Known Issues & Fixes

### Fixed Issues

| Issue | Migration | Description |
|-------|-----------|-------------|
| Dead inboxes missing killed_at | 033 | Backfilled 5528 records |
| Not connected = dead | 051 | Fixed 1938 inboxes |
| Domains with 0 inboxes marked live | 056 | Fixed 153 domains |
| Capacity includes disconnected | 058 | Now CONNECTED only |

### Potential Issues to Monitor

1. **Ghost Records:** Inboxes in DB that no longer exist in EmailBison
   - Cause: Sync doesn't handle deletions
   - Impact: Inflated counts
   - Fix: Periodic reconciliation script (not yet implemented)

2. **Stale disconnected_at:** If sync misses a reconnection event
   - Impact: Inbox could be killed despite being connected
   - Mitigation: Sync runs hourly, checks current status

3. **Bounce Counter Drift:** If sync_events misses bounces
   - Impact: Triggers may not fire
   - Mitigation: health_checks.py aggregates from response_messages as backup

---

## API Field Mappings

### sender_accounts → Inbox (TypeScript)

| Database | API/TypeScript | Notes |
|----------|----------------|-------|
| `inbox_state` | `inboxState` | 'live' or 'dead' |
| `status` | `espConnectionStatus` | OAuth connection status |
| `disconnected_at` | `disconnectedAt` | When OAuth lost |
| `kill_trigger` | `killReason` (partial) | Trigger type enum |
| `hard_bounces_24h` | `hardBounces24h` | 24h counter |
| `esp` | `espType` | 'microsoft' or 'gmail' |

### domains → Domain (TypeScript)

| Database | API/TypeScript | Notes |
|----------|----------------|-------|
| `domain_state` | `healthState` | 'live', 'flagged', 'dead' |
| `live_inbox_count` | `liveInboxCount` | Live inboxes |
| `dead_inbox_count` | `deadInboxCount` | Dead inboxes |
| (computed) | `connectedInboxCount` | From view |
| (computed) | `disconnectedInboxCount` | From view |

---

## Quick Reference Commands

### Check Current State

```bash
# Inbox state distribution
docker exec charm-postgres psql -U postgres -d postgres -c "
SELECT inbox_state, status, COUNT(*)
FROM sender_accounts
GROUP BY inbox_state, status
ORDER BY inbox_state, status;"

# Domain state distribution
docker exec charm-postgres psql -U postgres -d postgres -c "
SELECT domain_state, COUNT(*) FROM domains GROUP BY domain_state;"

# Viability status distribution
docker exec charm-postgres psql -U postgres -d postgres -c "
SELECT viability_status, COUNT(*), SUM(current_daily_capacity)
FROM v_domain_capacity GROUP BY viability_status;"
```

### Check Kill Queue

```bash
docker exec charm-postgres psql -U postgres -d postgres -c "
SELECT trigger_type, status, COUNT(*)
FROM kill_queue
GROUP BY trigger_type, status
ORDER BY status, trigger_type;"
```

### Check Capacity

```bash
docker exec charm-postgres psql -U postgres -d postgres -c "
SELECT
    w.workspace_name,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live,
    COUNT(*) FILTER (WHERE sa.status = 'Connected') as connected,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead,
    SUM(sa.daily_limit) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as capacity
FROM sender_accounts sa
JOIN workspaces w ON w.id = sa.workspace_id
GROUP BY w.workspace_name;"
```

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `KILL_THRESHOLD_SPAM` | 1 | Spam complaints to trigger kill |
| `KILL_THRESHOLD_HARD_BLOCKED_24H` | 1 | Hard blocked bounces in 24h |
| `KILL_THRESHOLD_HARD_UNKNOWN_24H` | 3 | Hard unknown bounces in 24h |
| `KILL_THRESHOLD_HARD_BOUNCES_24H` | 2 | Combined hard bounces in 24h |
| `KILL_THRESHOLD_HARD_BOUNCE_RATE` | 0.005 | 7-day hard bounce rate (0.5%) |
| `KILL_THRESHOLD_TOTAL_BOUNCE_RATE` | 0.05 | 7-day total bounce rate (5%) |
| `KILL_THRESHOLD_MIN_SENDS` | 20 | Minimum sends for rate calculation |
| `KILL_THRESHOLD_FRESH_INBOX_DAYS` | 14 | Fresh inbox protection period |
| `KILL_THRESHOLD_DISCONNECTED_DAYS` | 21 | Days before disconnected = dead |

---

## Related Documentation

- [DEPLOYMENT-CHECKLIST-DISCONNECTED-LIFECYCLE.md](./DEPLOYMENT-CHECKLIST-DISCONNECTED-LIFECYCLE.md) - Migration checklist
- [CONNECTION-STATUS-TRACKING.md](../infrastructure-provisioning/CONNECTION-STATUS-TRACKING.md) - Connection status details
- [DOMAIN-INBOX-STATUS-DEFINITIONS.md](./DOMAIN-INBOX-STATUS-DEFINITIONS.md) - Status definitions
