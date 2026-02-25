---
title: Health Monitoring
created: 2026-02-12
updated: 2026-02-23
tags: [health, monitoring, infrastructure, database, kill-triggers, warmup, capacity]
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

### Dashboard Layout (2026-02-13)

The Health page uses a tabbed layout with executive KPIs:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  [Health Score]  [Inbox Utilization]  [Domain Coverage]  [Weekly Churn] │
├─────────────────────────────────────────────────────────────────────────┤
│  [Dashboard]  [Infrastructure]  [Campaign Insights]                     │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐  ┌────────────────────────────────────┐   │
│  │ Inbox Distribution      │  │ Kill Velocity                       │   │
│  │ Live: 8 / Dead: 102     │  │ This Week: 1 death │ Trend: ↑       │   │
│  │ [████████████] 100%     │  │ [W1][W2][W3][W4][Now]               │   │
│  │ incubating              │  │                                      │   │
│  └─────────────────────────┘  └────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ ESP Performance        Gmail: 86%   │   Microsoft: 88%          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Inventory Segmentation Chart

Shows 4-segment inbox distribution with **dead shown separately**:

| Segment | Color | Definition |
|---------|-------|------------|
| **Deployed** | Green | Assigned to active campaign, actively sending |
| **Reserve** | Blue | 14+ days old + warmup enabled (deployment-ready) |
| **Incubating** | Amber | Under 14 days OR warmup not enabled (still warming) |
| **Dead** | Gray | Killed inboxes (shown separately, not in percentage bar) |

**Key Design Decisions:**
- Dead inboxes are NOT included in the percentage bar (would skew perception)
- Reserve requires BOTH: 14+ days age AND `warmup_enabled = true`
- Death rate shown as "X% of total created" for context

```
LIVE INVENTORY (8 inboxes)
[████████████████████████████████████████] 100% Incubating

DEAD INBOXES (102)                      87.2% of total created
┌─────────────────────────────────────────────────────────────┐
│ 102 killed or flagged                    High - review kill │
└─────────────────────────────────────────────────────────────┘
```

### Kill Velocity Chart

Shows weekly death trends with warning overlay:

- **5-week history**: Bar chart showing deaths per week
- **Current warnings**: Count of inboxes at risk (approaching kill thresholds)
- **Trend indicator**: Increasing / Decreasing / Stable
- **Insights**: Context-aware messages based on death rate and trends

### ESP Performance Card

Side-by-side Gmail vs Microsoft comparison:

| Metric | Source |
|--------|--------|
| Inbox Placement | External API (Google Postmaster / SNDS) when available |
| Avg Health Score | Local calculation (fallback when no external data) |
| Live/Dead Inboxes | Database counts |
| Death Rate | Calculated: dead / (live + dead) |
| Reputation | Derived from health score or external API |

Shows "Postmaster Data Pending" badge when external APIs not integrated.

### Warning Level Distribution

Predictive death forecasting based on proximity to kill thresholds:

| Level | Definition | Visual |
|-------|------------|--------|
| `healthy` | No bounces in 24h/7d | Green |
| `watching` | 1-2 hard bounces in 7d (pattern forming) | Yellow |
| `warning` | 1 hard bounce in 24h (one more = kill) | Orange |
| `critical` | At or above kill threshold (pending kill) | Red |

API returns `warning_distribution` with counts at each level:

```json
{
  "warning_distribution": {
    "healthy": 380,
    "watching": 5,
    "warning": 7,
    "critical": 15,
    "total_at_risk": 27
  }
}
```

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
| `warmup_enabled` | BOOLEAN | Whether warmup is enabled in EmailBison |
| `warmup_started_at` | TIMESTAMP | When warmup was first detected (first_seen_at + 7 days) |
| `warmup_stopped_at` | TIMESTAMP | When warmup was disabled |
| `sending_started_at` | TIMESTAMP | When inbox was first deployed to campaign |

### sender_accounts (all-time metrics)

These columns match the EmailBison UI metrics and are synced from the API:

| Column | Type | Description |
|--------|------|-------------|
| `emails_sent_all_time` | INTEGER | Total emails sent (all time) |
| `replies_all_time` | INTEGER | Total replies received (all time) |
| `bounces_all_time` | INTEGER | Total bounces (all time) |
| `daily_limit` | INTEGER | Daily sending limit |
| `complaints_lifetime` | INTEGER | Total spam complaints (1 = kill trigger) |

**Note**: Rate-based kill triggers are NOT implemented because absolute count thresholds (24h/7d bounces) catch the same problems without requiring `total_sends_7d` tracking.

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

### Backend

| File | Purpose |
|------|---------|
| `api/routes/health.py` | Infrastructure health endpoint + warning distribution |
| `api/routes/inventory.py` | Inventory counts and inbox listing |
| `api/models/health.py` | Pydantic response models (WarningLevelDistribution) |
| `sync_modules/sync_accounts.py` | Health score calculation |
| `sync_modules/health_checks.py` | Kill trigger detection |
| `migrations/029_inventory_segmentation_fix.sql` | Pool status view fix |

### Frontend Components

| File | Purpose |
|------|---------|
| `components/health/InventorySegmentationChart.tsx` | 4-segment distribution (dead separate) |
| `components/health/KillVelocityChart.tsx` | Weekly death trends + warnings overlay |
| `components/health/ESPComparisonCard.tsx` | Gmail vs Microsoft comparison |
| `components/health/HealthDistributionPieChart.tsx` | Health score pie chart |
| `components/health/InventoryTable.tsx` | Inbox table with filters |
| `lib/types/health.ts` | TypeScript types |
| `lib/types/inventory.ts` | Inventory segment types

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
2. **Queue** - Add to `kill_queue` table with status 'pending'
3. **Tag** - Apply trigger-specific tag in EmailBison (e.g., `flagged_fresh_inbox_bounce`)
4. **Flag** - Update status to 'flagged', mark `inbox_state = 'dead'`

**Note**: Inboxes are NOT deleted from EmailBison. They remain tagged for visibility into WHY they were flagged. This allows manual review in EmailBison by filtering by tag.

### Kill Trigger Monitor (UI)

The Health page shows three sections:

- **Action Required** (red) - Inboxes pending flagging
- **Under Review** (yellow) - Confirming triggers (planned feature)
- **Recently Flagged** - Inboxes tagged and marked as dead (no deletion)

See [[../concepts/kill-triggers]] for complete documentation.

## Differentiated Bounce Thresholds

Not all hard bounces are equal. The system distinguishes between:

- **hard_blocked** (550 5.7.x) - Spam/policy rejection = reputation damage
- **hard_unknown** (550 5.1.1) - Bad email address = list quality issue

This allows more aggressive response to reputation issues while being more tolerant of list quality problems.

See [[../adr/adr-005-differentiated-bounce-thresholds]] for the decision rationale.

## Warmup Tracking

The health system includes warmup lifecycle tracking to ensure inboxes are properly warmed before production use.

### Warmup Lifecycle

```
New Inbox → Connected → Warmup Enabled → Warming (30 days) → Ready for Campaigns
                           ↑                                        ↓
                           └────── Auto-enable if missing ←─────────┘
```

### Key Warmup Metrics

| Field | Description |
|-------|-------------|
| `warmup_enabled` | Current warmup status from EmailBison |
| `warmup_started_at` | Estimated start date (first_seen_at + 7 days buffer) |
| `warmup_stopped_at` | When warmup was disabled (transition detected) |
| Warmup Progress | `min(100, days_since_start / 30 * 100)` |

### 7-Day Buffer

When warmup is first detected as enabled, we estimate `warmup_started_at` as:

```
warmup_started_at = first_seen_at + 7 calendar days (~5 business days)
```

This accounts for inbox setup time before warmup actually starts:
- Domain verification
- DKIM/SPF setup
- Initial configuration

### Auto-Enable Warmup

Per the principle "always try to keep connected inboxes in warming", the sync worker automatically enables warmup for:

- Inboxes with `status = 'Connected'`
- Where `warmup_enabled = false`
- Runs every 30 minutes

### Warmup Snapshots

Time-series warmup data is stored in `sender_warmup_snapshots`:

| Column | Description |
|--------|-------------|
| `warmup_enabled` | Status at snapshot time |
| `warmup_score` | 0-100 score from EmailBison |
| `warmup_emails_sent` | Warmup emails sent |
| `warmup_replies_received` | Warmup replies |
| `warmup_bounces_received_count` | Bounces received during warmup |
| `warmup_emails_saved_from_spam` | Emails rescued from spam |

## V3 Specification Compliance

The Health V3 specification (`Inbox & Domain Health System v3.md`) defines 22 sections of requirements. Current implementation coverage:

| Area | Coverage | Status |
|------|----------|--------|
| Instant Kill Triggers | **95%** | All instant triggers + provider blocking |
| Confirming Kill Triggers | 0% | TODO: Requires placement testing |
| Domain Health Thresholds | **90%** | 1 dead=flagged, 2+=dead, >30% unhealthy=dead |
| Portfolio Structure | **85%** | Roles + backup promotion automation |
| ESP Configuration | 40% | Schema ready; Postmaster/SNDS API integration pending |
| Campaign Quarantine | **90%** | Burn tracking + quarantine triggers |
| List Management | **85%** | Segment quarantine + provider flagging |
| Placement Testing | 5% | Schema only |
| Alerting | 25% | Slack only |
| Data Model | **95%** | All core tables complete |

**Overall V3 Compliance: ~78%** (updated 2026-02-23)

For detailed gap analysis, see [[v3-compliance-gap-analysis]].

### Implemented Features

1. **Provider-specific blocking** - Gmail/Microsoft/Yahoo blocks trigger `flagged_provider_block_{esp}`
2. **Domain health thresholds** - Auto-transition to flagged/dead based on dead inbox count
3. **Campaign quarantine** - Burns 2+ inboxes in 7 days = quarantine
4. **Backup promotion** - Hot Backup → Primary when Primary dies
5. **List segment tracking** - Quarantine segments with 2+ bounces, purge at 3+
6. **Enrichment provider flagging** - Flag providers with 3+ bounces

### Remaining Gaps

1. **Confirming kill triggers** - Requires placement testing integration
2. **Postmaster/SNDS integration** - Schema ready, API not connected
3. **Placement testing** - No test execution or seed list management
4. **Email/SMS alerting** - Only Slack implemented

## HyperTide Capacity Tracking (2026-02-23)

Database views for tracking domain capacity against HyperTide infrastructure packages.

### Capacity Model

| Provider | Inboxes/Domain | Emails/Day/Inbox | Expected Capacity/Domain |
|----------|----------------|------------------|--------------------------|
| **Entra** | 50 | 2 | 100 emails/day |
| **Google** | 3 | 20 | 60 emails/day |

### Capacity Views

| View | Purpose |
|------|---------|
| `v_domain_capacity` | Per-domain capacity vs expected (utilization %, viability status) |
| `v_workspace_capacity_summary` | Aggregated by workspace + provider type |
| `v_domains_at_risk` | Domains below 70% capacity utilization |
| `v_capacity_validation` | Cross-validates daily_limit against expected HyperTide values |
| `v_client_capacity` | Client packages vs actual with gap analysis |
| `v_hypertide_order_queue` | Actionable HyperTide orders needed to fill gaps |
| `v_inbox_pipeline` | Inbox flow through lifecycle stages |
| `v_workspace_volume` | Raw volume for ALL workspaces (no package required) |

### Viability Status

| Status | Utilization | Description |
|--------|-------------|-------------|
| `healthy` | >70% | Performing well |
| `warning` | 40-70% | Needs attention |
| `critical` | <40% | Significant capacity loss |
| `deprecated` | 0 live | No live inboxes remaining |

### Client Package Tracking

Client packages are stored in `client_subscriptions`:

```sql
SELECT
    entra_packages,          -- Number of Entra HyperTide packages
    entra_domains_per_package,  -- 2 (default)
    entra_inboxes_per_domain,   -- 52 (default)
    google_packages,         -- Number of Google packages
    google_domains_per_package, -- 5 (default)
    google_inboxes_per_domain,  -- 3 (default)
    spare_ratio              -- 0.15 (15% buffer)
FROM client_subscriptions
WHERE status = 'active';
```

### Gap Analysis

The `v_client_capacity` view calculates:

- **Target domains/inboxes** from subscription
- **Actual active** (excluding deprecated)
- **Gap** = target - actual
- **Orders needed** = gap / domains_per_package
- **Pipeline buffer** = incubating + reserve inboxes
- **Buffer ratio** = pipeline / active (should be >= spare_ratio)

Clients without subscriptions show raw volume with NULL for targets (informational, not restrictive).

### Sample Queries

```sql
-- Domains at risk for a workspace
SELECT domain_name, capacity_utilization_pct, viability_status
FROM v_domains_at_risk
WHERE workspace_id = 'your-workspace-id';

-- HyperTide orders needed
SELECT * FROM v_hypertide_order_queue
WHERE orders_needed > 0;

-- Client capacity dashboard
SELECT client_name, entra_domain_gap, google_domain_gap,
       entra_orders_needed, google_orders_needed
FROM v_client_capacity;

-- Raw workspace volume (no package required)
SELECT workspace_name, provider_type, live_inboxes, dead_inboxes,
       incubating_inboxes, active_inboxes
FROM v_workspace_volume;
```

## Related

- [[v3-compliance-gap-analysis]] - Detailed V3 gap analysis
- [[../concepts/kill-triggers]] - Kill trigger system
- [[../adr/adr-005-differentiated-bounce-thresholds]] - Differentiated thresholds ADR
- [[../local-development/emailbison-sync-worker]] - Sync worker documentation
- [[../local-development/environment-variables]] - Environment variables
- [[../database/schema]] - Database schema
