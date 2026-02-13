---
title: Health Monitoring
created: 2026-02-12
updated: 2026-02-12
tags: [health, monitoring, infrastructure, database, kill-triggers]
---

# Health Monitoring

Database-driven infrastructure health monitoring for email inboxes and domains, with automated kill trigger detection.

## Overview

The Health page provides real-time visibility into inbox health without making live EmailBison API calls. All data comes from the local database, synced by the [[../local-development/emailbison-sync-worker|EmailBison Sync Worker]].

## Key Principle: Database-Only

**No live EmailBison API calls** on the Health page. This ensures:

- Fast page loads (<500ms)
- Consistent data across refreshes
- Reduced API rate limiting
- Works offline (with stale data)

Data freshness is shown via "Last sync: X minutes ago" indicator.

## Health Score Calculation

Health scores are calculated locally by the sync worker (not returned by EmailBison API):

| Factor | Points | Criteria |
|--------|--------|----------|
| Connection | 40 | Connected=40, Not connected=0, Other=20 |
| Bounce Rate | 20 | <2%=20, <5%=15, <10%=10, >=10%=0 |
| Spam Rate | 20 | <1%=20, <3%=15, <5%=10, >=5%=0 |
| Reply Rate | 10 | >10%=10, >5%=7, >2%=5, <=2%=3 |
| Daily Limit | 10 | Warmup=10, Has limit=7, No limit=5 |

### Health Ranges

| Range | Score | Color | Description |
|-------|-------|-------|-------------|
| Healthy | 80-100 | Green | Performing well |
| Good | 60-80 | Yellow | Minor issues |
| Warning | 40-60 | Orange | Needs attention |
| Critical | 0-40 | Red | Immediate action required |

## Components

### Health Distribution Pie Chart

Visual breakdown of inbox health distribution:

- **Interactive**: Click segment to filter InventoryTable
- **CSS-based**: Uses conic-gradient (no Recharts dependency)
- **Center stat**: Shows total live inboxes
- **Legend**: Health range counts

```
┌─────────────────────────────────┐
│  Health Distribution            │
│  ┌─────────────────────────┐   │
│  │      ╭──────────╮       │   │
│  │     ╱   GREEN    ╲      │   │
│  │    │   (692)      │     │   │
│  │     ╲            ╱      │   │
│  │      ╰──────────╯       │   │
│  └─────────────────────────┘   │
│  ● Healthy: 692                 │
│  ● Good: 0                      │
│  ● Warning: 0                   │
│  ● Critical: 0                  │
└─────────────────────────────────┘
```

### Infrastructure Summary

Key metrics at a glance:

- **Live Inboxes**: Inboxes with health_score (synced from EmailBison)
- **Dead Inboxes**: Inboxes marked as dead or not in EmailBison
- **Avg Health Score**: Weighted average across all live inboxes
- **Clean/Total Domains**: Domain health status
- **Provider Breakdown**: Gmail vs Microsoft distribution

### InventoryTable

Detailed inbox list with filtering:

| Column | Description |
|--------|-------------|
| Email | Inbox email address |
| Domain | Associated domain |
| Pool Status | deployed, warning, reserve |
| Lifecycle | active, incubating, dead |
| Age | Days since creation |
| Bounces | 24h / 7d bounce counts |
| Campaigns | Associated campaign count |

Filters:
- **Health Range**: Filter by health score range (click pie chart)
- **Pool Status**: Filter by inventory pool
- **Lifecycle**: Filter by lifecycle status
- **Search**: Text search by email or domain

## API Endpoints

### GET /api/health/infrastructure/{client_id}

Returns database-only infrastructure health:

```json
{
  "clientId": "uuid",
  "totalInboxes": 1727,
  "liveInboxes": 692,
  "deadInboxes": 1035,
  "avgHealthScore": 93.0,
  "providers": [
    {
      "name": "microsoft",
      "count": 1624,
      "liveCount": 618,
      "deadCount": 1006,
      "avgHealthScore": 93.0
    }
  ],
  "healthDistribution": {
    "healthy": 692,
    "good": 0,
    "warning": 0,
    "critical": 0,
    "total": 692
  },
  "totalDomains": 71,
  "cleanDomains": 71,
  "flaggedDomains": 0,
  "lastSync": "2026-02-12T07:34:48.464098",
  "syncSource": "database"
}
```

## Database Schema

### sender_accounts (health columns)

| Column | Type | Description |
|--------|------|-------------|
| `health_score` | INTEGER | Calculated 0-100 score |
| `inbox_state` | VARCHAR | live, dead |
| `hard_bounces_24h` | INTEGER | Recent bounce count |
| `hard_bounces_7d` | INTEGER | Weekly bounce count |
| `bounce_rate_7d` | DECIMAL | Bounce rate percentage |
| `warmup_score` | INTEGER | Warmup progress 0-100 |

### Health Distribution Query

```sql
SELECT
    COUNT(*) FILTER (WHERE health_score >= 80) as healthy,
    COUNT(*) FILTER (WHERE health_score >= 60 AND health_score < 80) as good,
    COUNT(*) FILTER (WHERE health_score >= 40 AND health_score < 60) as warning,
    COUNT(*) FILTER (WHERE health_score < 40 OR health_score IS NULL) as critical
FROM sender_accounts
WHERE workspace_id = $1 AND inbox_state = 'live';
```

## Files

| File | Purpose |
|------|---------|
| `api/routes/health.py` | Infrastructure health endpoint |
| `api/models/health.py` | Pydantic response models |
| `components/health/HealthDistributionPieChart.tsx` | Pie chart component |
| `components/health/InventoryTable.tsx` | Inbox table with filters |
| `lib/types/health.ts` | TypeScript types |
| `sync_modules/sync_accounts.py` | Health score calculation |

## Migration from EmailBison API

Previously, the `InventoryHealthDashboard` component made live API calls:

```
Frontend → GET /api/health/inventory/{clientId}
         → EmailBisonService.get_workspace_summary()
         → 3+ API calls to spellcast.hirecharm.com
```

Now, all data comes from database:

```
Frontend → GET /api/health/infrastructure/{clientId}
         → SELECT from sender_accounts, domains
         → No external API calls
```

The `InventoryHealthDashboard` component was removed from `components/inboxes/`.

## Kill Trigger System

The health system includes automated kill detection. When thresholds are breached, inboxes are queued for deletion with a 24-hour safety window.

### Kill Triggers Summary

| Trigger | Threshold | Description |
|---------|-----------|-------------|
| `spam_complaint` | >=1 | Any spam complaint = instant death |
| `hard_blocked_24h` | >=1 | Spam/policy rejection |
| `hard_unknown_24h` | >=3 | Bad email addresses |
| `hard_bounces_24h` | >=2 | Combined fallback |
| `fresh_inbox_hard_bounce` | >=1 | Any bounce on inbox <14 days old |

### Kill Queue Process

1. **Detect** - Health check finds threshold breach (every 15 min)
2. **Queue** - Add to `kill_queue` table
3. **Tag** - Apply `delete_queue` tag in EmailBison
4. **Wait** - 24-hour safety window
5. **Delete** - Remove from EmailBison after 24 hours
6. **Update** - Mark `inbox_state = 'dead'`

### Kill Trigger Monitor (UI)

The Health page shows three sections:

- **Action Required** (red) - Inboxes queued for deletion
- **Under Review** (yellow) - Confirming triggers (planned feature)
- **Recent Kills** - Completed deletions

See [[../concepts/kill-triggers]] for complete documentation.

## Differentiated Bounce Thresholds

Not all hard bounces are equal. The system distinguishes between:

- **hard_blocked** (550 5.7.x) - Spam/policy rejection = reputation damage
- **hard_unknown** (550 5.1.1) - Bad email address = list quality issue

This allows more aggressive response to reputation issues while being more tolerant of list quality problems.

See [[../adr/adr-005-differentiated-bounce-thresholds]] for the decision rationale.

## Related

- [[../concepts/kill-triggers]] - Kill trigger system
- [[../adr/adr-005-differentiated-bounce-thresholds]] - Differentiated thresholds ADR
- [[../local-development/emailbison-sync-worker]] - Sync worker documentation
- [[../local-development/environment-variables]] - Environment variables
- [[../database/schema]] - Database schema
