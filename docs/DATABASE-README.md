# Charm Email OS - Database Documentation Index

**Last Updated:** 2026-02-24
**Database:** PostgreSQL (charm-postgres:5432)

---

## Welcome to Charm Email OS Database Documentation

This documentation suite was created to prevent the analysis errors documented in [DATABASE-ANALYSIS-RETROSPECTIVE.md](../secure-openclaw/DATABASE-ANALYSIS-RETROSPECTIVE.md). It provides complete guidance for navigating, querying, and understanding the Charm Email OS database.

---

## Documentation Structure

### 1. [DATABASE-GUIDE.md](./DATABASE-GUIDE.md) - START HERE
**Master navigation guide with architecture and data flow**

Read this first to understand:
- How to connect to the database
- How data flows from EmailBison API → Sync Workers → PostgreSQL
- Core tables and their relationships
- Business logic (kill triggers, domain health state machine)
- Troubleshooting common issues

**Best for:** Getting oriented, understanding the big picture, learning the sync architecture

---

### 2. [DATA-DICTIONARY.md](./DATA-DICTIONARY.md) - REFERENCE
**Complete field-by-field documentation of all tables**

Use this when you need to know:
- What each field means and contains
- Data types, defaults, and constraints
- Business rules and validation logic
- Enum type definitions
- Field naming conventions
- Common query pitfalls

**Best for:** Understanding specific fields, writing queries, avoiding common errors

---

### 3. [QUERY-COOKBOOK.md](./QUERY-COOKBOOK.md) - COPY-PASTE QUERIES
**20 ready-to-use queries for common analysis tasks**

Categories:
- **Performance Analysis** (queries 1-5): Burn rates, volume-adjusted metrics, client comparisons
- **Health Monitoring** (queries 6-9): Active kill triggers, warning states, RBL issues
- **Campaign Analytics** (queries 10-11): Campaign performance, burn tracking
- **Capacity Planning** (queries 12-14): Inventory status, warmup pipeline, daily limits
- **Infrastructure Comparison** (query 15): Microsoft vs Google performance
- **Troubleshooting** (queries 16-20): Disconnection analysis, orphaned records, sync lag

**Best for:** Quick analysis, reports, dashboards, investigations

---

### 4. [ADR-005: Differentiated Bounce Thresholds](./adr/adr-005-differentiated-bounce-thresholds.md)
**Kill trigger threshold documentation**

Technical specification for:
- Why `hard_blocked_24h` (≥1) vs `hard_unknown_24h` (≥3) have different thresholds
- Kill trigger priority evaluation order
- Environment variable configuration
- Migration history

**Best for:** Understanding kill trigger logic, modifying thresholds, debugging health checks

---

## Quick Start

### Connect to Database
```bash
# Development
PGPASSWORD=localdevpassword psql -h charm-postgres -U postgres -d postgres

# Production (requires .env)
PGPASSWORD=$(grep DATABASE_PASSWORD .env | cut -d'=' -f2) \
  psql -h production-host -U postgres -d postgres
```

### Essential Queries

#### 1. Burn Rate (CORRECT Definition)
```sql
-- burn = kill_trigger IS NOT NULL (NOT inbox_state = 'dead')
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    COUNT(*) FILTER (WHERE kill_trigger IS NULL AND inbox_state = 'dead') as healthy_disconnected,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate_pct
FROM sender_accounts;
```

#### 2. Infrastructure Type (CORRECT Source)
```sql
-- Use sender_accounts.esp (NOT domains.infrastructure_type - always NULL)
SELECT esp, COUNT(*) as count
FROM sender_accounts
WHERE esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

#### 3. Dual-Provider Comparison (CORRECT Method)
```sql
-- Only compare within clients that have BOTH providers
WITH dual_provider_workspaces AS (
    SELECT workspace_id
    FROM sender_accounts
    WHERE esp IN ('microsoft', 'gmail')
    GROUP BY workspace_id
    HAVING COUNT(DISTINCT esp) = 2
)
SELECT
    w.workspace_name as client,
    sa.esp,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) as burned,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate
FROM sender_accounts sa
JOIN dual_provider_workspaces dpw ON sa.workspace_id = dpw.workspace_id
JOIN workspaces w ON sa.workspace_id = w.id
WHERE sa.esp IN ('microsoft', 'gmail')
GROUP BY w.workspace_name, sa.esp
ORDER BY w.workspace_name;
```

---

## Critical Concepts

### 1. Burn Rate Definition

**WRONG:** `inbox_state = 'dead'` (includes healthy disconnections)
**CORRECT:** `kill_trigger IS NOT NULL` (only performance-based burns)

**Why this matters:**
- 67-91% of "dead" inboxes are healthy disconnections (supplier changes, cancellations, rotation)
- Only 9-33% of "dead" inboxes actually burned due to performance issues
- Using wrong definition inflates burn rate by 5-8x

### 2. Infrastructure Classification

**WRONG:** `domains.infrastructure_type` (always NULL)
**CORRECT:** `sender_accounts.esp` (ground truth from EmailBison API tags)

**Why this matters:**
- `domains.infrastructure_type` was never populated
- EmailBison API tags are the source of truth
- Using wrong field returns empty results

### 3. Volume-Adjusted Metrics

**WRONG:** Raw burn counts (ignores that some inboxes send 10x more volume)
**CORRECT:** Burns per million emails sent

**Why this matters:**
- Google inboxes send 2.2x more volume per inbox than Microsoft
- Raw burn rate shows 33% vs 9%, but volume-adjusted shows 3,163 vs 1,950 burns/M emails
- Must normalize by volume for fair comparison

---

## Common Pitfalls

### ❌ Don't Count Healthy Disconnections as Burns
```sql
-- WRONG - counts 77% Microsoft, 64% Google
WHERE inbox_state = 'dead'
```
```sql
-- CORRECT - counts 9% Microsoft, 33% Google
WHERE kill_trigger IS NOT NULL
```

### ❌ Don't Use domains.infrastructure_type
```sql
-- WRONG - always returns empty
SELECT infrastructure_type FROM domains WHERE infrastructure_type = 'microsoft'
```
```sql
-- CORRECT - use sender_accounts.esp
SELECT sa.esp FROM sender_accounts sa WHERE sa.esp = 'microsoft'
```

### ❌ Don't Compare Different Clients
```sql
-- WRONG - compares Charm (low burn) to Spout (high burn)
SELECT esp, COUNT(*) FROM sender_accounts GROUP BY esp
```
```sql
-- CORRECT - only compare within dual-provider clients
WITH dual_provider_workspaces AS (...)
SELECT esp FROM sender_accounts WHERE workspace_id IN (...)
```

### ❌ Don't Ignore Sending Volume
```sql
-- WRONG - Google sends 2.2x more per inbox
SELECT COUNT(*) burned FROM sender_accounts WHERE kill_trigger IS NOT NULL
```
```sql
-- CORRECT - normalize by volume
SELECT ROUND(1000000.0 * COUNT(*) / SUM(emails_sent_all_time), 2) as burns_per_million
```

---

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      EMAILBISON API                             │
│                  (spellcast.hirecharm.com)                      │
│                                                                 │
│  - Sender accounts (inboxes)                                   │
│  - Campaigns                                                   │
│  - Campaign events (opens, clicks, bounces, replies)          │
│  - Warmup snapshots                                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS API calls
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              EMAILBISON SYNC WORKER                             │
│           (emailbison_sync_worker.py)                           │
│                                                                 │
│  Orchestrates sync modules:                                    │
│  - sync_accounts.py (every hour)                               │
│  - sync_events.py (every 5 min)                                │
│  - sync_warmup_snapshots.py (daily)                            │
│  - sync_campaigns.py (every 15 min)                            │
│  - health_checks.py (every 15 min)                             │
│  - kill_processor.py (every 30 min)                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ SQL INSERT/UPDATE
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   POSTGRESQL DATABASE                           │
│                  (charm-postgres:5432)                          │
│                                                                 │
│  Core Tables:                                                  │
│  - sender_accounts (6,978 rows) - inbox tracking               │
│  - domains (509 rows) - domain health                          │
│  - emailbison_campaigns (113 rows) - campaign metadata         │
│  - campaign_events (1.1M rows) - email events                  │
│  - kill_queue (3 rows) - 24h kill waiting period               │
│  - daily_volume_snapshots - capacity tracking                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Kill Trigger System

### Active Triggers (4 of 12 defined)

| Trigger | Threshold | % of Burns | Avg Emails Before Kill |
|---------|-----------|------------|------------------------|
| **fresh_inbox_bounce** | ≥1 bounce <14 days | 67.71% | 78 emails |
| **hard_bounces_24h** | ≥2 bounces in 24h | 17.42% | 75 emails |
| **spam_complaint** | ≥1 complaint | 14.68% | 90 emails |
| **hard_blocked_24h** | ≥1 spam rejection | 0.19% | 80 emails |

### Evaluation Priority (health_checks.py)

1. **spam_complaint** (≥1) - HIGHEST PRIORITY
2. **provider_block** (≥1, if esp = gmail/microsoft/yahoo)
3. **hard_blocked_24h** (≥1) - reputation damage
4. **hard_unknown_24h** (≥3) - bad addresses
5. **hard_bounces_24h** (≥2) - combined fallback
6. **hard_bounce_rate_7d** (>0.5%, min 50 sends)
7. **bounce_rate_all_7d** (>5%, min 50 sends)
8. **fresh_inbox_bounce** (any bounce <14 days)

---

## Key Findings from Recent Analysis

### Microsoft vs Google Performance (Dual-Provider Clients Only)

| Metric | Microsoft | Google | Winner |
|--------|-----------|--------|--------|
| **Burn Rate** | 9.16% | 33.44% | Microsoft (-24.28 pp) |
| **Burns per Million Emails** | 1,950 | 3,163 | Microsoft (-38% burns) |
| **Burn Rate (1-100 emails)** | 10.55% | **56.97%** | Microsoft (-46.42 pp) |

**Root Cause:** Google has catastrophic 57% burn rate in first 100 emails sent, while Microsoft only burns 11% in that range.

**Recommendation:** Investigate Google warmup protocol and early-stage failure patterns.

---

## Enum Types Quick Reference

### kill_trigger_type
`spam_complaint`, `hard_bounces_24h`, `consecutive_hard_bounces`, `hard_bounce_rate_7d`, `bounce_rate_all_7d`, `provider_block`, `fresh_inbox_bounce`, `placement_failure`, `spam_folder_rate`, `degrading_trend`, `hard_blocked_24h`, `hard_unknown_24h`

### esp_type
`gmail`, `microsoft`, `yahoo`, `other`

### inbox_state
`live`, `dead`

### domain_state
`live`, `flagged` (1 dead inbox), `dead` (2+ dead inboxes)

### campaign_state
`live`, `quarantined`, `dead`

### inbox_role
`primary`, `hot_backup`, `warming`

---

## Getting Help

### "I need to understand how the database works"
→ Read [DATABASE-GUIDE.md](./DATABASE-GUIDE.md)

### "What does this field mean?"
→ Read [DATA-DICTIONARY.md](./DATA-DICTIONARY.md)

### "I need a query for X"
→ Read [QUERY-COOKBOOK.md](./QUERY-COOKBOOK.md)

### "Why are my results wrong?"
→ Check [Common Pitfalls](#common-pitfalls) section above

### "How do kill triggers work?"
→ Read [ADR-005](./adr/adr-005-differentiated-bounce-thresholds.md)

### "Why was the original analysis so difficult?"
→ Read [DATABASE-ANALYSIS-RETROSPECTIVE.md](../secure-openclaw/DATABASE-ANALYSIS-RETROSPECTIVE.md)

---

## Contributing

When adding new fields or tables:

1. Update [DATA-DICTIONARY.md](./DATA-DICTIONARY.md) with field definitions
2. Add relevant queries to [QUERY-COOKBOOK.md](./QUERY-COOKBOOK.md)
3. Update [DATABASE-GUIDE.md](./DATABASE-GUIDE.md) if data flow changes
4. Document ADRs for kill trigger or threshold changes
5. Add database comments via SQL: `COMMENT ON COLUMN table.field IS 'description'`

---

## Version History

- **v1.0** (2026-02-24) - Initial comprehensive documentation suite
  - Created DATABASE-GUIDE.md (master guide)
  - Created DATA-DICTIONARY.md (field reference)
  - Created QUERY-COOKBOOK.md (20 ready-to-use queries)
  - Documented Microsoft vs Google analysis findings
  - Created DATABASE-ANALYSIS-RETROSPECTIVE.md (lessons learned)

---

**Last Updated:** 2026-02-24
**Maintainer:** Charm Email OS Team
