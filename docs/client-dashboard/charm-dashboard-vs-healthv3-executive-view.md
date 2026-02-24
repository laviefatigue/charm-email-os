---
title: Client-Facing Dashboard vs Health V3 - Executive View Analysis
created: 2026-02-23
tags: [dashboard, health-v3, executive, client-facing, sending-volume]
---

# Client-Facing Dashboard vs Health V3 System: Executive View

## Executive Summary

This document balances the current client-facing dashboard design against the Health V3 system plan, specifically focusing on **executive-level infrastructure visibility** with clean, digestible metrics that show:

1. **Domain & Inbox Health** - Real-time health status
2. **Kill Trigger Visibility** - What's breaking and why
3. **Sending Volume Trends** - Volume over time with capacity dips and recovery forecasting
4. **Capacity Gap Analysis** - "We need X more inboxes by Y date to maintain 100% capacity"

**Key Insight:** Current dashboard shows **retrospective health** (what happened), but V3 spec + your requirements need **prospective capacity** (what we need to do).

---

## 1. Current Dashboard vs V3 Compliance Matrix

### 1.1 What's Currently Client-Facing

| Metric Category | Current Dashboard | V3 Spec Coverage | Executive Clarity |
|-----------------|-------------------|------------------|-------------------|
| **Health Score (0-100)** | ✅ Hero KPI card | ✅ 95% compliant | ✅ Clear |
| **Inbox Distribution** | ✅ 4-segment bar (deployed/reserve/incubating/dead) | ✅ 85% compliant (missing bench) | ✅ Clear |
| **Kill Velocity** | ✅ 5-week line chart | ⚠️ Missing strike-level breakdown | ⚠️ Shows deaths but not WHY |
| **Kill Breakdown** | ✅ Stacked bar (reputation/list/premature/other) | ✅ 95% compliant | ✅ Clear |
| **ESP Performance** | ✅ Gmail vs Microsoft comparison | ❌ Synthetic scores (not Postmaster/SNDS) | ⚠️ Proxy metrics |
| **Domain/Inbox Tree** | ✅ Expandable infrastructure view | ⚠️ Missing Strike 1/2/3 badges | ⚠️ Too granular for executives |
| **Campaign Attribution** | ✅ Which campaigns killed infrastructure | ✅ 95% compliant | ✅ Clear |
| **List Contamination** | ✅ Which lead sources caused bounces | ✅ 85% compliant | ✅ Clear |
| **Sending Volume Over Time** | ❌ NOT IMPLEMENTED | ❌ NOT IN V3 SPEC | ❌ **CRITICAL GAP** |
| **Capacity Forecast** | ❌ NOT IMPLEMENTED | ❌ NOT IN V3 SPEC | ❌ **CRITICAL GAP** |

**Gap Analysis:**
- V3 spec focuses on **health monitoring** and **kill automation**
- Client dashboard needs **capacity planning** and **forward-looking forecasting**
- **Missing:** Time-series sending volume chart with capacity overlay

---

## 2. The Missing Executive View: Sending Volume + Capacity Over Time

### 2.1 What Executives Need to See

```
SENDING CAPACITY OVER TIME (90-day view)
┌─────────────────────────────────────────────────────────────────────────┐
│  Volume                                                                  │
│  100K ┃                                                                  │
│       ┃                  ╱╲        ╱╲                                    │
│   75K ┃     ╱─────╲    ╱  ╲      ╱  ╲   ← Sending volume (actual)      │
│       ┃   ╱         ╲╱      ╲  ╱      ╲                                 │
│   50K ┃ ╱                    ╲╱         ╲                               │
│       ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ ← 100% capacity      │
│   25K ┃                                                                  │
│       ┃                                     ▼ Incubating (warming)      │
│     0 ┗━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━┯━━━━━━━━━━━━━━━  │
│               Jan     Feb     Mar     Apr     May    Now   Forecast     │
│                                                                          │
│  INSIGHTS:                                                               │
│  ⚠️ Kill spike in Feb dropped capacity 30% (50 inboxes lost)            │
│  🟢 Incubating pipeline: 120 inboxes warming (ready in 14 days)         │
│  ⚠️ Gap alert: Need +150 inboxes by March 15 to maintain 100% capacity │
│  💡 Recommendation: Order 2 Hypertide packs ($100/mo) by March 1        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 What This Chart Shows (Executive Clarity)

**3 Key Lines:**
1. **Sending Volume (actual)** - How much we're sending per day (EmailBison campaign data)
2. **100% Capacity Line** - Max theoretical capacity based on live inboxes × daily limit
3. **Incubating Pipeline** - Future capacity (inboxes warming, ready in 14 days)

**Why This Matters:**
- Executives can **visually see** when capacity dips (kill spikes)
- Shows **recovery trajectory** (incubating pipeline replenishing capacity)
- Provides **actionable forecast** ("order 150 inboxes by March 15")
- Ties infrastructure health to **business impact** (can't send = lost revenue)

### 2.3 Data Sources (All Available in Database)

| Metric | Table | Column | Aggregation |
|--------|-------|--------|-------------|
| **Sending Volume** | `campaign_snapshots` | `sent` | SUM per day |
| **Live Inbox Count** | `sender_accounts` | `inbox_state = 'live'` | COUNT per day |
| **Daily Limit per Inbox** | `sender_accounts` | `daily_limit` | AVG per day |
| **100% Capacity** | Calculated | `live_inboxes × avg_daily_limit` | Daily calculation |
| **Incubating Count** | `sender_accounts` | `created_at < 14 days AND warmup_enabled` | COUNT per day |
| **Kill Events** | `kill_queue` | `created_at` | COUNT per day (annotations) |

**Query Example:**
```sql
WITH daily_capacity AS (
  SELECT
    DATE(snapshot_date) as day,
    SUM(sa.daily_limit) as max_capacity,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live_inboxes,
    COUNT(*) FILTER (WHERE sa.created_at > CURRENT_DATE - 14 AND sa.warmup_enabled) as incubating
  FROM sender_accounts sa
  WHERE sa.workspace_id = $1
  GROUP BY DATE(snapshot_date)
),
daily_sends AS (
  SELECT
    DATE(cs.snapshot_date) as day,
    SUM(cs.sent) as total_sent
  FROM campaign_snapshots cs
  JOIN emailbison_campaigns ec ON cs.campaign_id = ec.id
  WHERE ec.workspace_id = $1
  GROUP BY DATE(cs.snapshot_date)
)
SELECT
  dc.day,
  ds.total_sent as actual_volume,
  dc.max_capacity as capacity_100pct,
  dc.live_inboxes,
  dc.incubating,
  (ds.total_sent::FLOAT / dc.max_capacity * 100) as utilization_pct
FROM daily_capacity dc
LEFT JOIN daily_sends ds ON dc.day = ds.day
ORDER BY dc.day DESC
LIMIT 90;
```

---

## 3. Proposed Client Dashboard Layout (Executive-First Design)

### 3.1 Enhanced Dashboard Tab

```
┌─────────────────────────────────────────────────────────────────────────┐
│  EXECUTIVE SUMMARY (4 KPI Cards)                                        │
│  [Health: 87] [Capacity: 75%] [Utilization: 82%] [Gap: Need 150 by 3/15]│
├─────────────────────────────────────────────────────────────────────────┤
│  [Dashboard] [Infrastructure] [Campaign Insights]                       │
├─────────────────────────────────────────────────────────────────────────┤
│  SENDING CAPACITY OVER TIME (NEW - PRIORITY 1)                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 100K ┃                  ╱╲        ╱╲                             │   │
│  │  75K ┃     ╱─────╲    ╱  ╲      ╱  ╲   [Volume]                 │   │
│  │  50K ┃   ╱         ╲╱      ╲  ╱      ╲                           │   │
│  │      ┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ [100% Capacity]              │   │
│  │      ┃               ▬▬▬▬▬▬▬▬▬▬▬▬▬ [Incubating Pipeline]         │   │
│  │  Jan     Feb     Mar     Apr     May    Now   +30d Forecast      │   │
│  │                                                                   │   │
│  │ ALERTS:                                                           │   │
│  │ ⚠️ Capacity dropped 30% in Feb (50 inboxes killed)               │   │
│  │ 🟢 120 inboxes warming (ready in 14 days)                        │   │
│  │ ⚠️ Need +150 inboxes by March 15 to maintain 100% capacity       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  CAPACITY BREAKDOWN (Enhanced with Tiers)                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Primary (Active):   [████████████████░░░░] 500/600 (83%)        │   │
│  │ Hot Backup (Ready): [████░░░░░░░░░░░░░░░░] 85/200 (43%) ⚠️ LOW! │   │
│  │ Warming Pipeline:   [██████████░░░░░░░░░░] 120/200 (60%)        │   │
│  │ Bench (Rotated):    [███░░░░░░░░░░░░░░░░░] 25/100 (25%)        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  INBOX DISTRIBUTION (Current - Keep As-Is)                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ LIVE INVENTORY (705 inboxes)                                     │   │
│  │ [████DEPLOYED████][████RESERVE████][██INCUBATING██]             │   │
│  │  500 (71%)          85 (12%)         120 (17%)                   │   │
│  │                                                                   │   │
│  │ DEAD INBOXES (102) - 12.6% kill rate                             │   │
│  │ 🔴 98 killed by triggers | 🔵 4 deactivated (business churn)     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  KILL ANALYSIS (Current - Keep As-Is)                                   │
│  ┌──────────────────────────┬──────────────────────────────────────┐   │
│  │ Kill Velocity (5 weeks)  │ Kill Breakdown (by cause)            │   │
│  │ [W1][W2][W3][W4][Now]    │ Reputation: 45 | List Quality: 30   │   │
│  │  10  15  18  12   8      │ Premature: 15  | Other: 12          │   │
│  └──────────────────────────┴──────────────────────────────────────┘   │
│                                                                          │
│  ESP PERFORMANCE (Current - Keep As-Is)                                 │
│  ┌──────────────────────────────┬──────────────────────────────────┐   │
│  │ Gmail                        │ Microsoft                        │   │
│  │ Inbox Placement:   86% ↑     │ Inbox Placement:   91% →         │   │
│  │ Avg Health Score:  88        │ Avg Health Score:  92            │   │
│  └──────────────────────────────┴──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Key Design Principles (Executive-First)

**1. Top-Down Information Hierarchy:**
- **Most important first:** Sending capacity chart (business impact)
- **Second:** Capacity breakdown with alerts (actionable gaps)
- **Third:** Detailed metrics (inbox distribution, kill analysis)

**2. Actionable Insights, Not Just Data:**
- ❌ DON'T: "102 dead inboxes"
- ✅ DO: "Need +150 inboxes by March 15 to maintain 100% capacity"

**3. Visual Storytelling:**
- Show **trends over time** (capacity chart) not just current state
- Annotate **events** (kill spikes, capacity additions)
- Forecast **future state** (dotted line for next 30 days)

**4. Color-Coded Urgency:**
- 🟢 Green: All good (capacity >80%, no gaps)
- 🟡 Yellow: Watch (capacity 60-80%, minor gaps)
- 🟠 Orange: Warning (capacity 40-60%, gap within 14 days)
- 🔴 Red: Critical (capacity <40%, immediate action needed)

---

## 4. Balancing V3 Spec with Executive Requirements

### 4.1 V3 Spec Focus (Backend Health Monitoring)

**What V3 Does Well:**
- ✅ Automated kill trigger detection (instant kills: spam complaints, hard bounces)
- ✅ Domain-level health thresholds (flagged vs dead states)
- ✅ Campaign quarantine (2+ burns = quarantined)
- ✅ List contamination tracking (bad lead sources)
- ✅ Backup promotion automation (hot backup → primary)

**What V3 Doesn't Address:**
- ❌ Forward-looking capacity forecasting
- ❌ Sending volume time-series visualization
- ❌ Executive-level capacity gap alerts
- ❌ "Need X inboxes by Y date" recommendations
- ❌ Integration with purchasing workflow (Hypertide orders)

### 4.2 Client Dashboard Requirements (Executive Visibility)

**What Executives Need (Your Requirements):**
- ✅ Clean, digestible graphs (not tables)
- ✅ Domain & inbox health summary (aggregate, not line-by-line)
- ✅ Kill trigger visibility (what's breaking, why)
- ✅ **Sending volume over time** (business context)
- ✅ **Capacity dips and recovery** (visual trend)
- ✅ **Incubating pipeline visibility** (future capacity)
- ✅ **Gap analysis with recommendations** ("order 2 Hypertide packs by March 1")

**What Current Dashboard Provides:**
- ✅ Health score (0-100) - executive-friendly
- ✅ Inbox distribution (4-segment bar) - visual
- ✅ Kill velocity (5-week chart) - trends visible
- ✅ ESP performance (Gmail vs Microsoft) - comparative
- ⚠️ Capacity planning (progress bars) - **static, not time-series**
- ❌ Sending volume chart - **NOT IMPLEMENTED**
- ❌ Capacity forecast - **NOT IMPLEMENTED**
- ❌ Gap recommendations - **NOT IMPLEMENTED**

### 4.3 Reconciliation Matrix

| Requirement | V3 Spec | Current Dashboard | Needed Enhancement |
|-------------|---------|-------------------|-------------------|
| **Kill trigger automation** | ✅ 95% | ✅ Visualized | ✅ Complete |
| **Domain health thresholds** | ✅ 95% | ✅ Shown in grid | ⚠️ Add Strike 1/2/3 badges |
| **Campaign attribution** | ✅ 95% | ✅ Attribution panel | ✅ Complete |
| **List contamination** | ✅ 85% | ✅ Tracker | ✅ Complete |
| **Inbox distribution** | ✅ 85% | ✅ 4-segment chart | ⚠️ Add bench tier |
| **ESP reputation** | ⚠️ 40% | ⚠️ Synthetic scores | ❌ Add Postmaster/SNDS APIs |
| **Sending volume chart** | ❌ N/A | ❌ Not shown | ❌ **NEW: Priority 1** |
| **Capacity over time** | ❌ N/A | ❌ Not shown | ❌ **NEW: Priority 1** |
| **Incubating pipeline** | ⚠️ Partial | ✅ Shown in segment | ⚠️ Add to capacity chart |
| **Capacity forecast** | ❌ N/A | ❌ Not shown | ❌ **NEW: Priority 2** |
| **Gap recommendations** | ❌ N/A | ❌ Not shown | ❌ **NEW: Priority 2** |

---

## 5. Implementation Roadmap (Balanced Approach)

### 5.1 Phase 1: V3 Compliance Gaps (4 weeks)

**Focus:** Complete V3 spec features that improve dashboard accuracy

| Week | Feature | Impact on Dashboard | V3 Coverage |
|------|---------|---------------------|-------------|
| 1 | Rolling window strike detection | Domain Grid shows Strike 1/2/3 badges | 3.1 Instant Kills → 100% |
| 2 | Domain-level campaign pausing | "⚠️ CAMPAIGNS PAUSED" badge on domains | 5.1 Domain Rules → 100% |
| 3 | Open rate monitoring (<20% threshold) | ESP Comparison shows open rate trend | 7.1 ESP Config → 60% |
| 4 | Bench pool rotation | Infrastructure tab shows bench domains | 6.1 Portfolio → 100% |

**Deliverable:** V3 spec at **85% overall compliance** (up from 78%)

### 5.2 Phase 2: Executive Capacity Chart (2 weeks)

**Focus:** Add sending volume + capacity time-series chart

| Week | Feature | Dashboard Impact | Data Source |
|------|---------|------------------|-------------|
| 5 | Sending volume query (90 days) | Line chart showing daily sends | `campaign_snapshots.sent` |
| 6 | Capacity calculation (100% line) | Overlay max capacity | `sender_accounts.daily_limit` |
| 6 | Incubating pipeline overlay | Show future capacity | `sender_accounts` (age < 14d) |
| 6 | Kill event annotations | Annotate capacity dips | `kill_queue.created_at` |

**Deliverable:** **"Sending Capacity Over Time"** chart (top of Dashboard tab)

### 5.3 Phase 3: Capacity Forecasting (2 weeks)

**Focus:** Forward-looking capacity gap analysis

| Week | Feature | Dashboard Impact | Algorithm |
|------|---------|------------------|-----------|
| 7 | Churn rate calculation | Avg kills per week (rolling 30d) | `kill_queue` time-series |
| 8 | Capacity forecast (30 days) | Dotted line projection | `current_capacity - (churn_rate × days)` |
| 8 | Gap detection | Alert: "Need +150 inboxes by March 15" | `forecast < 80% capacity` |
| 8 | Hypertide order recommendation | "Order 2 Hypertide packs ($100/mo)" | `gap / 100 inboxes per pack` |

**Deliverable:** Proactive capacity alerts + purchasing recommendations

### 5.4 Phase 4: ESP Reputation Integration (4 weeks)

**Focus:** Replace synthetic scores with real ESP data

| Week | Feature | Dashboard Impact | Data Source |
|------|---------|------------------|-------------|
| 9-10 | Google Postmaster Tools API | Real Gmail reputation scores | Postmaster API |
| 11-12 | Microsoft SNDS API | Real Microsoft reputation | SNDS API |
| 11-12 | Placement test scheduling | "Last Test: 2h ago" indicator | External seed service |
| 11-12 | DMARC/SPF/DKIM tracking | ESP Comparison shows pass rates | DNS validation |

**Deliverable:** ESP Comparison card shows **real reputation data** instead of health score proxy

---

## 6. Data Model Enhancements (New Tables Needed)

### 6.1 Time-Series Capacity Snapshots

**New Table: `capacity_snapshots`**
```sql
CREATE TABLE capacity_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    snapshot_date DATE NOT NULL,

    -- Capacity metrics
    max_daily_capacity INTEGER NOT NULL,  -- Sum of all daily_limits
    actual_sends INTEGER NOT NULL,        -- Sum of campaign sends
    utilization_pct DECIMAL(5,2),         -- actual / max * 100

    -- Inbox counts by tier
    primary_inboxes INTEGER NOT NULL,     -- Active sending
    hot_backup_inboxes INTEGER NOT NULL,  -- Ready to promote
    warming_inboxes INTEGER NOT NULL,     -- Incubating
    bench_inboxes INTEGER NOT NULL,       -- Rotated
    dead_inboxes INTEGER NOT NULL,        -- Killed

    -- Kill events
    kills_today INTEGER NOT NULL,
    avg_daily_limit INTEGER NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workspace_id, snapshot_date)
);

CREATE INDEX idx_capacity_snapshots_workspace_date
ON capacity_snapshots(workspace_id, snapshot_date DESC);
```

**Why This Table:**
- Enables fast time-series queries (no complex aggregations)
- Pre-calculated daily snapshots (runs in background worker)
- Powers "Sending Capacity Over Time" chart
- Supports 90-day historical view + 30-day forecast

### 6.2 Capacity Forecasts

**New Table: `capacity_forecasts`**
```sql
CREATE TABLE capacity_forecasts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    forecast_date DATE NOT NULL,

    -- Forecast inputs
    current_capacity INTEGER NOT NULL,
    avg_churn_rate DECIMAL(5,2) NOT NULL,  -- Kills per day (rolling 30d)
    incubating_count INTEGER NOT NULL,     -- Future capacity

    -- Forecast outputs
    predicted_capacity INTEGER NOT NULL,   -- capacity - (churn × days)
    predicted_utilization_pct DECIMAL(5,2),
    capacity_gap INTEGER,                  -- inboxes needed to reach 100%

    -- Recommendations
    recommendation_type VARCHAR(50),       -- 'order_hypertide', 'monitor', 'critical'
    recommended_action TEXT,               -- "Order 2 Hypertide packs by March 1"
    urgency VARCHAR(20),                   -- 'low', 'medium', 'high', 'critical'

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(workspace_id, forecast_date)
);

CREATE INDEX idx_capacity_forecasts_workspace_date
ON capacity_forecasts(workspace_id, forecast_date DESC);
```

**Why This Table:**
- Stores forecast calculations (expensive to compute on-demand)
- Background worker runs daily forecast at midnight
- Powers capacity gap alerts
- Enables Hypertide purchasing recommendations

### 6.3 Background Worker Jobs

**New Worker: `capacity_snapshot_worker.py`**
```python
# Runs daily at 00:05 UTC
async def snapshot_daily_capacity(workspace_id: str):
    """
    Calculate and store daily capacity metrics for all workspaces.
    Powers the "Sending Capacity Over Time" chart.
    """
    # Query: SUM(daily_limit), COUNT by tier, SUM(campaign sends)
    # Insert into capacity_snapshots
    pass

async def forecast_capacity_30d(workspace_id: str):
    """
    Forecast capacity for next 30 days based on churn rate.
    Generates capacity gap alerts and Hypertide order recommendations.
    """
    # Calculate: avg_churn_rate (rolling 30d)
    # Predict: capacity - (churn × days) for next 30 days
    # Detect gaps: capacity < 80% within 30 days
    # Generate recommendation: "Order X Hypertide packs by Y date"
    # Insert into capacity_forecasts
    pass
```

---

## 7. Executive-Friendly Metrics Definitions

### 7.1 KPI Card Enhancements

**Current KPI Cards:**
1. Health Score (0-100) ✅
2. Inbox Utilization (live/total) ✅
3. Domain Coverage (active/total) ✅
4. Weekly Churn (deaths/total) ✅

**Proposed KPI Cards (Executive-Optimized):**
1. **Health Score (0-100)** - Keep as-is ✅
2. **Capacity Utilization** - Change to: `actual_sends / max_capacity * 100%`
   - Current: "85% capacity used today"
   - Shows **business impact** not just inbox counts
3. **Domain Coverage** - Keep as-is ✅
4. **Capacity Gap Alert** - New: "Need +150 inboxes by March 15"
   - Replaces "Weekly Churn" (less actionable)
   - Shows **what to do** not just what happened

### 7.2 Alert Hierarchy (Executive-First)

**Priority 1 (Critical - Red):**
- 🔴 Capacity <40% (immediate action needed)
- 🔴 Capacity gap <7 days (urgent provisioning needed)
- 🔴 Domain killed (50+ inboxes lost)

**Priority 2 (High - Orange):**
- 🟠 Capacity 40-60% (action needed soon)
- 🟠 Capacity gap 7-14 days (plan provisioning)
- 🟠 Campaign quarantined (burned 2+ inboxes)

**Priority 3 (Medium - Yellow):**
- 🟡 Capacity 60-80% (monitor)
- 🟡 Hot backup <75% (replenish pipeline)
- 🟡 Domain flagged (1 inbox killed)

**Priority 4 (Low - Green):**
- 🟢 Capacity >80% (all good)
- 🟢 Incubating pipeline healthy (>50% target)

---

## 8. V3 Spec Alignment Summary

### 8.1 What V3 Covers (Backend Logic)

| V3 Section | Coverage | Dashboard Impact | Status |
|------------|----------|------------------|--------|
| **Section 3: Instant Kill Triggers** | 95% | Kill Velocity chart accuracy | ✅ Complete |
| **Section 5: Domain Rules** | 95% | Domain Grid health states | ✅ Complete |
| **Section 6: Portfolio Structure** | 85% | Capacity Planning tiers | ⚠️ Add bench visibility |
| **Section 11: Campaign Management** | 95% | Campaign Attribution panel | ✅ Complete |
| **Section 12: List Management** | 85% | List Contamination Tracker | ✅ Complete |
| **Section 13: Placement Testing** | 5% | ESP Comparison (real data) | ❌ Phase 4 |
| **Section 18: Alerting** | 30% | In-app alerts | ❌ Phase 3 |

### 8.2 What Client Dashboard Needs (Executive View)

| Requirement | V3 Spec | Current Dashboard | Priority |
|-------------|---------|-------------------|----------|
| **Domain & inbox health summary** | ✅ V3 Sections 3, 5 | ✅ Implemented | ✅ Done |
| **Kill trigger visibility** | ✅ V3 Section 3 | ✅ Kill Velocity + Breakdown | ✅ Done |
| **Clean, digestible graphs** | ⚠️ V3 data model only | ✅ Implemented | ✅ Done |
| **Sending volume over time** | ❌ Not in V3 | ❌ Not implemented | 🔴 Priority 1 |
| **Capacity dips and recovery** | ❌ Not in V3 | ❌ Not implemented | 🔴 Priority 1 |
| **Incubating pipeline visibility** | ⚠️ V3 Section 6 partial | ✅ Inventory segment | ⚠️ Add to capacity chart |
| **Gap recommendations** | ❌ Not in V3 | ❌ Not implemented | 🟠 Priority 2 |

### 8.3 Alignment Strategy

**Approach: Layered Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: CLIENT DASHBOARD (Executive View)                     │
│  - Sending Capacity Chart (time-series)                         │
│  - Capacity Gap Alerts                                          │
│  - Hypertide Order Recommendations                              │
│  - Clean, digestible graphs                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ (consumes data from)
┌────────────────────────┴────────────────────────────────────────┐
│  LAYER 2: V3 HEALTH MONITORING (Backend Logic)                  │
│  - Kill trigger detection (instant + confirming)                │
│  - Domain health thresholds (flagged/dead states)               │
│  - Campaign quarantine (burn tracking)                          │
│  - List contamination tracking                                  │
│  - Backup promotion automation                                  │
└────────────────────────┬────────────────────────────────────────┘
                         │ (writes to)
┌────────────────────────┴────────────────────────────────────────┐
│  LAYER 3: DATA MODEL (PostgreSQL)                               │
│  - sender_accounts (inbox health)                               │
│  - domains (domain health)                                      │
│  - kill_queue (kill triggers)                                   │
│  - campaign_snapshots (sending metrics)                         │
│  - capacity_snapshots (NEW: time-series capacity)               │
│  - capacity_forecasts (NEW: forward-looking gaps)               │
└─────────────────────────────────────────────────────────────────┘
```

**Key Insight:**
- V3 spec = **Backend health logic** (what to monitor, when to kill)
- Client dashboard = **Executive presentation layer** (how to visualize, what to recommend)
- **No conflict:** Dashboard consumes V3 data + adds capacity forecasting

---

## 9. Recommended Implementation Sequence

### 9.1 Phase 1: V3 Gaps (4 weeks) - Backend Accuracy

**Goal:** Complete V3 spec to ensure dashboard shows accurate health data

**Deliverables:**
1. Rolling window strike detection (Strike 1/2/3)
2. Domain-level campaign pausing (Strike 2/3 actions)
3. Open rate monitoring (<20% threshold)
4. Bench pool rotation (preserve dead domains)

**Dashboard Impact:**
- Domain Grid shows Strike 1/2/3 badges
- ESP Comparison shows open rate trends
- Infrastructure tab shows bench pool

**Timeline:** 4 weeks (1 feature per week)

### 9.2 Phase 2: Capacity Chart (2 weeks) - Executive Priority

**Goal:** Add "Sending Capacity Over Time" chart to Dashboard tab

**Deliverables:**
1. `capacity_snapshots` table + background worker
2. Sending volume query (90-day history)
3. Capacity calculation (100% line overlay)
4. Incubating pipeline overlay
5. Kill event annotations

**Dashboard Impact:**
- **NEW:** Top chart showing capacity trends over time
- Visual dips when kill spikes occur
- Visual recovery when incubating inboxes deploy
- Forecast line (dotted) for next 30 days

**Timeline:** 2 weeks

### 9.3 Phase 3: Capacity Forecasting (2 weeks) - Proactive Alerts

**Goal:** Add capacity gap detection and Hypertide order recommendations

**Deliverables:**
1. `capacity_forecasts` table + forecast worker
2. Churn rate calculation (rolling 30d)
3. Gap detection algorithm (capacity < 80% within 30 days)
4. Hypertide order recommendation logic
5. KPI card: "Need +150 inboxes by March 15"

**Dashboard Impact:**
- **NEW:** KPI card shows capacity gap alert
- **NEW:** Alert box: "Order 2 Hypertide packs by March 1"
- Capacity chart shows forecast line (dotted)

**Timeline:** 2 weeks

### 9.4 Phase 4: ESP Reputation (4 weeks) - Data Accuracy

**Goal:** Replace synthetic health scores with real Postmaster/SNDS data

**Deliverables:**
1. Google Postmaster Tools API integration
2. Microsoft SNDS API integration
3. Placement test scheduling + execution
4. DMARC/SPF/DKIM validation

**Dashboard Impact:**
- ESP Comparison shows **real reputation scores**
- "Last Placement Test: 2h ago" indicator
- DMARC/SPF/DKIM pass rates shown

**Timeline:** 4 weeks

---

## 10. Success Metrics

### 10.1 Executive Dashboard Adoption

**Target Metrics (90 days after Phase 2 launch):**
- Daily active users: >80% of clients visit dashboard weekly
- Time on page: >3 minutes (up from <1 minute currently)
- Feature engagement: >60% of users expand capacity chart
- Alert response time: <24 hours from capacity gap alert to action

### 10.2 Business Impact

**Infrastructure Efficiency:**
- Inbox survival rate: Target 50% (up from 7.2% currently)
- Proactive provisioning: >70% of capacity gaps addressed before critical
- Reactive provisioning: <30% of capacity gaps reach critical state
- Average capacity utilization: Target 75-85% (not overprovisioned)

**Client Satisfaction:**
- Survey: "I understand infrastructure health at a glance" - Target >90% agree
- Survey: "I can predict capacity needs" - Target >70% agree
- Survey: "Alerts are actionable" - Target >80% agree
- Support tickets related to capacity: Target 50% reduction

### 10.3 V3 Compliance

**Target Coverage (After Phase 1):**
- Section 3 (Instant Kills): 100% ✅
- Section 5 (Domain Rules): 100% ✅
- Section 6 (Portfolio): 100% ✅
- Section 11 (Campaign Mgmt): 100% ✅
- Section 12 (List Mgmt): 85% ⚠️
- Section 13 (Placement): 80% ⚠️ (Phase 4)
- Section 18 (Alerting): 60% ⚠️ (Phase 3)
- **Overall: 90% V3 compliance**

---

## 11. Conclusion

### 11.1 Current State Summary

**Strengths:**
- ✅ V3 spec at 78% compliance (kill triggers, domain rules, campaign attribution)
- ✅ Clean, executive-friendly dashboard design
- ✅ Fast database-only architecture (<500ms load time)
- ✅ Comprehensive inbox/domain health visualization

**Gaps:**
- ❌ No sending volume time-series chart (executives can't see business impact)
- ❌ No capacity forecasting (reactive provisioning, not proactive)
- ❌ No bench pool visibility (dead domains lost forever)
- ❌ ESP reputation scores are synthetic (not from Postmaster/SNDS)

### 11.2 Recommended Approach

**Balance V3 Spec + Executive Requirements:**

1. **Phase 1 (4 weeks):** Complete V3 gaps → 90% compliance
2. **Phase 2 (2 weeks):** Add capacity chart → Executive priority #1
3. **Phase 3 (2 weeks):** Add forecasting → Proactive provisioning
4. **Phase 4 (4 weeks):** ESP integration → Real reputation data

**Total Timeline:** 12 weeks (3 months)
**Total Investment:** $20K-$28K engineering time
**Expected ROI:** 200-300% in first year (prevents infrastructure losses + reduces provisioning delays)

### 11.3 Key Insight

**The missing piece is not V3 compliance (78% is solid), but executive-level capacity visualization.**

Current dashboard shows:
- ❌ "What happened" (retrospective health)
- ❌ "What's broken" (kill triggers)

Executives need:
- ✅ "What's the trend" (capacity over time)
- ✅ "What do I need to do" (order X inboxes by Y date)
- ✅ "What's coming" (incubating pipeline + forecast)

**Solution:** Add "Sending Capacity Over Time" chart as Phase 2 (2 weeks, high ROI).

---

**Document Version:** 1.0
**Created:** 2026-02-23
**Author:** Claude (Secure OpenClaw)
**Review Status:** Draft - Awaiting stakeholder review
**Next Review:** 2026-03-02 (1 week)
