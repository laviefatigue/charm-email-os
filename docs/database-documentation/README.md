# Database Documentation Suite

**Location:** `/docs/database-documentation/`
**Created:** 2026-02-24/25
**Purpose:** Comprehensive database reference to prevent analysis errors

---

## 📚 Documentation Files

### 1. [DATABASE-README.md](./DATABASE-README.md) - START HERE
**Master index and navigation guide**

Quick reference for:
- Essential queries (burn rate, infrastructure, dual-provider comparison)
- Critical concepts (burn rate definition, volume-adjusted metrics)
- Common pitfalls and how to avoid them
- Which doc to read for what question

**Use when:** You need to get oriented or find the right documentation quickly.

---

### 2. [DATABASE-GUIDE.md](./DATABASE-GUIDE.md) - ARCHITECTURE
**Complete data flow and system architecture**

Covers:
- Database connection details
- Data flow: EmailBison API → Sync Workers → PostgreSQL
- Core tables reference (sender_accounts, domains, campaigns)
- Business logic (kill triggers, domain health state machine)
- Troubleshooting guide

**Use when:** You need to understand how data flows through the system.

---

### 3. [DATA-DICTIONARY.md](./DATA-DICTIONARY.md) - FIELD REFERENCE
**Field-by-field documentation for all core tables**

Contains:
- 5 core tables fully documented (sender_accounts, domains, emailbison_campaigns, workspaces, kill_queue)
- 6 enum types with all values
- Field descriptions, data types, business rules, thresholds
- Common pitfalls section (7 wrong vs correct query examples)
- Field naming conventions

**Use when:** You need to know what a specific field means or how to query it correctly.

---

### 4. [QUERY-COOKBOOK.md](./QUERY-COOKBOOK.md) - COPY-PASTE QUERIES
**20 ready-to-use queries across 6 categories**

Categories:
- Performance Analysis (queries 1-5)
- Health Monitoring (queries 6-9)
- Campaign Analytics (queries 10-11)
- Capacity Planning (queries 12-14)
- Infrastructure Comparison (query 15)
- Troubleshooting (queries 16-20)

**Use when:** You need a query for a specific analysis task.

---

### 5. [COMPREHENSIVE-SYSTEM-AUDIT.md](./COMPREHENSIVE-SYSTEM-AUDIT.md) - AUDIT REPORT
**Full system audit with deployment readiness assessment**

Includes:
- Database integrity audit (score: 6.5/10)
- API design audit (score: 5/10)
- Sync modularity audit (score: 7/10)
- Safety verification (NO DELETION policy confirmed)
- Critical finding: Warmup vs campaign response handling (score: 2/10)
- P0 blockers before deployment
- Complete recommendations with priority levels

**Use when:** You need to understand system health, deployment readiness, or prioritize fixes.

---

## 🎯 Quick Reference

### Essential Queries

#### Correct Burn Rate
```sql
-- CORRECT: kill_trigger IS NOT NULL (NOT inbox_state='dead')
SELECT
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate_pct
FROM sender_accounts;
```

#### Infrastructure Classification
```sql
-- CORRECT: Use sender_accounts.esp (NOT domains.infrastructure_type - always NULL)
SELECT esp, COUNT(*) as count
FROM sender_accounts
WHERE esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

#### Dual-Provider Comparison
```sql
-- CORRECT: Only compare within clients that have BOTH providers
WITH dual_provider_workspaces AS (
    SELECT workspace_id
    FROM sender_accounts
    WHERE esp IN ('microsoft', 'gmail')
    GROUP BY workspace_id
    HAVING COUNT(DISTINCT esp) = 2
)
SELECT
    sa.esp,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) as burned,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate
FROM sender_accounts sa
WHERE workspace_id IN (SELECT workspace_id FROM dual_provider_workspaces)
  AND esp IN ('microsoft', 'gmail')
GROUP BY sa.esp;
```

---

## ⚠️ Critical Distinctions

### Burn Rate Definition
- **WRONG:** `inbox_state = 'dead'` (includes healthy disconnections)
- **CORRECT:** `kill_trigger IS NOT NULL` (only performance-based burns)

### Infrastructure Source
- **WRONG:** `domains.infrastructure_type` (always NULL)
- **CORRECT:** `sender_accounts.esp` (ground truth from EmailBison API)

### Volume Adjustment
- **WRONG:** Raw burn counts (ignores sending volume differences)
- **CORRECT:** Burns per million emails sent

---

## 📊 Key Findings

### Microsoft vs Google Performance (Dual-Provider Clients)
| Metric | Microsoft | Google | Winner |
|--------|-----------|--------|--------|
| Burn Rate | 9.16% | 33.44% | Microsoft (-24.28pp) |
| Burns/Million | 1,950 | 3,163 | Microsoft (-38%) |
| Early Burn (<100 emails) | 10.55% | 56.97% | Microsoft (-46.42pp) |

**Root Cause:** Google has catastrophic 57% burn rate in first 100 emails (warmup phase).

---

## 🚀 Deployment Readiness

### P0 Blockers (Fix Before Production)
1. ❌ Warmup vs campaign response handling NOT IMPLEMENTED
2. ❌ 501 warmup date violations (warmup_stopped_at < warmup_started_at)
3. ❌ No API authentication on HTTP endpoints
4. ❌ Command injection vulnerability in Signal adapter

**Estimated fix time:** 8-10 hours

### System Scores
- Database Integrity: 6.5/10
- API Design: 5/10
- Sync Modularity: 7/10
- Safety (No Deletion): 9/10 ✅
- Warmup vs Campaign: 2/10 ❌

---

## 🔗 Related Documentation

- [ADR-005: Differentiated Bounce Thresholds](../adr/adr-005-differentiated-bounce-thresholds.md)
- [Health Monitoring Feature](../features/health-monitoring.md)
- [Database Schema Reference](../database/schema.md)
- [Kill Triggers Concept](../concepts/kill-triggers.md)

---

## 📝 How This Was Created

This documentation suite was created in response to analysis errors during the Microsoft vs Google infrastructure comparison. The original analysis required 7 corrections due to:
1. Wrong burn rate definition
2. Missing volume context
3. Wrong infrastructure data source
4. Ignored business model
5. Didn't control for client variable
6. Fabricated financial projections
7. Lack of data dictionary

**See:** [DATABASE-ANALYSIS-RETROSPECTIVE.md](../../secure-openclaw/DATABASE-ANALYSIS-RETROSPECTIVE.md) for complete error analysis.

---

## 💡 Getting Help

| Question | Read This |
|----------|-----------|
| "How does the database work?" | DATABASE-GUIDE.md |
| "What does this field mean?" | DATA-DICTIONARY.md |
| "I need a query for X" | QUERY-COOKBOOK.md |
| "Why are my results wrong?" | DATABASE-README.md → Common Pitfalls |
| "How do kill triggers work?" | ADR-005 + COMPREHENSIVE-SYSTEM-AUDIT.md |
| "Is the system ready to deploy?" | COMPREHENSIVE-SYSTEM-AUDIT.md |

---

**Last Updated:** 2026-02-25
**Maintainer:** Charm Email OS Team
**For Claude Code:** Point to `/docs/database-documentation/` for complete database reference
