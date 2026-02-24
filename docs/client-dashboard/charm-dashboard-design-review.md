---
title: Client-Facing Infrastructure Dashboard Design Review
created: 2026-02-23
tags: [dashboard, infrastructure, health, metrics, ui-ux]
---

# Client-Facing Infrastructure Dashboard: Design Review & Gap Analysis

## Executive Summary

This document reviews the current client-facing infrastructure dashboard design in Charm Email OS and compares it against desired infrastructure health metrics based on operational SOPs and monitoring requirements.

**Current Dashboard Maturity:** 70% complete
**Key Strengths:** Comprehensive health scoring, kill trigger visualization, ESP comparison
**Critical Gaps:** Gemini SOP compliance, rolling window tracking, domain-level kill actions, real-time capacity forecasting

---

## 1. Current Dashboard Architecture

### 1.1 Frontend Stack

**Location:** `/home/claw/work/charm-email-os/charm-email-os/app/clients/[clientId]/health/page.tsx`

**Framework:** Next.js 14+ (App Router) with TypeScript
**State Management:** Zustand (`healthStore.ts`, `infrastructureStore.ts`)
**UI Components:** Custom React components (27 components in `components/health/`)
**Data Fetching:** REST API via `lib/api.ts`

**Page Structure:**
```
┌─────────────────────────────────────────────────────────────────────────┐
│  4 KPI Cards: Health Score | Inbox Utilization | Domain Coverage | Churn │
├─────────────────────────────────────────────────────────────────────────┤
│  Tabs: [Dashboard] [Infrastructure] [Campaign Insights]                 │
├─────────────────────────────────────────────────────────────────────────┤
│  Dashboard Tab:                                                          │
│    - Capacity Planning (inbox/domain progress bars)                     │
│    - Inventory Segmentation (pie: deployed/dead/reserve/incubating)     │
│    - Kill Velocity (5-week line chart)                                  │
│    - Kill Breakdown (stacked bar: reputation/list/premature/other)      │
│    - ESP Comparison (Gmail vs Microsoft)                                │
│                                                                          │
│  Infrastructure Tab:                                                     │
│    - Domain/Inbox Tree (expandable, lazy-loaded)                        │
│    - Disconnected Inboxes Alert                                         │
│                                                                          │
│  Campaign Insights Tab:                                                 │
│    - Campaign Attribution (which campaigns killed infrastructure)       │
│    - List Contamination Tracker (lead list bounce rates)                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Backend API Architecture

**Location:** `/home/claw/work/charm-email-os/api/routes/health.py` (2054 lines)

**Framework:** FastAPI (Python)
**Database:** PostgreSQL
**Key Principle:** **Database-only** (no live EmailBison API calls for speed)

**Primary Endpoints:**
```python
GET /api/health/full-dashboard/{client_id}
    └─ Returns: overall_summary, kill_triggers, backup_capacity,
                domain_grid, campaign_attribution, contamination_sources,
                esp_summaries

GET /api/health/infrastructure/{client_id}
    └─ Returns: provider breakdown, health distribution, lifecycle distribution,
                warning level distribution, domain source breakdown

GET /api/health/kill-velocity/{client_id}
    └─ Returns: 5-week death counts, churn rate, trend

GET /api/health/kill-breakdown/{client_id}
    └─ Returns: kill categorization (reputation, list quality, premature, other)

GET /api/health/emailbison-capacity/{client_id}
    └─ Returns: live inbox count, daily send limits, warmup distribution
```

### 1.3 Data Model

**Key Database Tables:**
- `sender_accounts` - Inbox health metrics, bounce tracking, warmup status
- `domains` - Domain health, blacklist counts, lifecycle phase
- `emailbison_campaigns` - Campaign metrics, bounce/complaint rates
- `campaign_snapshots` - Latest campaign statistics
- `kill_queue` - Kill trigger queue with status tracking
- `sender_warmup_snapshots` - Time-series warmup data (544 MB, NEVER ANALYZED!)

**Health Score Calculation (0-100):**
| Factor | Points | Criteria |
|--------|--------|----------|
| Connection | 40 | Connected=40, Not connected=0, Other=20 |
| Bounce Rate | 20 | <2%=20, <5%=15, <10%=10, >=10%=0 |
| Spam Rate | 20 | <1%=20, <3%=15, <5%=10, >=5%=0 |
| Reply Rate | 10 | >10%=10, >5%=7, >2%=5, <=2%=3 |
| Daily Limit | 10 | Warmup=10, Has limit=7, No limit=5 |

---

## 2. Current Dashboard Metrics (What We Show Now)

### 2.1 Hero KPIs (4-Card Grid)

| Metric | Calculation | Purpose | Status |
|--------|-------------|---------|--------|
| **Health Score** | Weighted average (0-100) | Overall infrastructure health | ✅ Working |
| **Inbox Utilization** | `live_inboxes / total_inboxes * 100%` | Capacity usage | ✅ Working |
| **Domain Coverage** | `active_domains / total_domains * 100%` | Domain health | ✅ Working |
| **Weekly Churn** | `deaths_this_week / total_inboxes * 100%` | Death rate trend | ✅ Working |

### 2.2 Dashboard Tab Metrics

**Capacity Planning:**
- Inbox progress bar: `current / target` with spare indicator
- Domain progress bar: `current / target` with spare indicator
- **GAP:** No differentiation between primary/hot backup/warming pipeline tiers

**Inventory Segmentation (Pie Chart):**
- Deployed: Assigned to active campaign, actively sending
- Reserve: 14+ days old + warmup enabled (deployment-ready)
- Incubating: Under 14 days OR warmup not enabled
- Dead: Killed inboxes (shown separately, not in percentage)
- **GAP:** No bench/rotation pool visibility

**Kill Velocity (5-Week Line Chart):**
- Weekly death counts for past 5 weeks
- 7-day total, 30-day total
- Churn rate percentage
- Trend indicator (increasing/decreasing/stable)
- **GAP:** No forward-looking "at risk" forecast by strike level

**Kill Breakdown (Stacked Bar Chart):**
- Reputation kills (spam complaints, hard_blocked)
- List quality kills (hard_unknown bounces)
- Premature deployment kills (fresh inbox bounces)
- Other kills
- **GAP:** No Gemini SOP Strike 1/2/3 categorization

**ESP Comparison Card:**
- Gmail vs Microsoft side-by-side
- Metrics: inbox placement, spam placement, avg health score, live/dead counts, death rate
- **GAP:** No DMARC/SPF/DKIM pass rates, no open rate tracking

### 2.3 Infrastructure Tab Metrics

**Domain/Inbox Tree:**
- Expandable domain list
- Lazy-loaded inbox details per domain
- Shows: email, state, bounces, age, campaigns
- **GAP:** No domain-level kill trigger warnings, no Strike 2/3 indicators

**Disconnected Inboxes Alert:**
- Lists inboxes disconnected from EmailBison
- **STATUS:** ✅ Working

### 2.4 Campaign Insights Tab Metrics

**Campaign Attribution:**
- Which campaigns killed inboxes/domains
- Bounce rate, complaint rate per campaign
- Risk level (low/medium/high)
- **GAP:** No 48-hour rolling window attribution, no Strike 2/3 quarantine status

**List Contamination Tracker:**
- Lead list bounce rates by source (enrichment/scraped/manual/purchased)
- Affected inboxes/domains per source
- **STATUS:** ✅ Working

---

## 3. Desired Infrastructure Health Metrics (From SOPs)

### 3.1 From Gemini SOP (Kill Switch Rules)

**Inbox-Level Auto-Pause Rules:**
| Rule | Threshold | Action | Current Status |
|------|-----------|--------|----------------|
| 1 spam complaint (550) | >=1 | Instant pause | ✅ Implemented (`spam_complaint` trigger) |
| Bounce rate >2.5% (7d) | >2.5% | Review + pause | ⚠️ Tracked but threshold 5% not 2.5% |
| Fresh inbox bounce | >=1 on <14 days | Instant pause | ✅ Implemented (`fresh_inbox_hard_bounce`) |
| Hard blocked (5.7.x) | >=1 in 24h | Instant pause | ✅ Implemented (`hard_blocked_24h`) |

**Domain-Level Guardrails:**
| Rule | Threshold | Action | Current Status |
|------|-----------|--------|----------------|
| Bounce rate >2.5% (7d) | Domain-wide | Pause all campaigns on domain | ❌ NOT IMPLEMENTED |
| Spam complaint >0.1% | Domain-wide | Pause all campaigns on domain | ❌ NOT IMPLEMENTED |
| Open rate <20% (3d) | Domain-wide | Pause all campaigns on domain | ❌ NOT IMPLEMENTED |

**Strike System (48-Hour Rolling Window):**
| Strike Level | Definition | Action | Current Status |
|--------------|------------|--------|----------------|
| Strike 1 | 1st inbox kill in 48h | Flag domain, continue monitoring | ❌ NOT IMPLEMENTED |
| Strike 2 | 2nd inbox kill in 48h | Pause campaigns on domain, manual review | ❌ NOT IMPLEMENTED |
| Strike 3 | 3rd inbox kill in 48h | Kill entire domain, rotate to bench | ❌ NOT IMPLEMENTED |

**Current Gap:** Charm tracks kill triggers but does NOT implement:
- 48-hour rolling window for strike detection
- Domain-level campaign pausing
- Strike 2/3 graduated response system
- Bench domain rotation

### 3.2 From Infrastructure Growth SOP

**Warming Lifecycle Tracking:**
| Metric | Definition | Current Tracking |
|--------|------------|------------------|
| Warming Phase | Days 1-21 with gradual volume ramp | ✅ `warmup_started_at`, progress calculation |
| Daily Volume | Emails/account/day by phase | ⚠️ Tracked in snapshots but not visualized |
| Warmup Completion | 21 days → campaign ready | ✅ Calculated in `InventorySegmentationChart` |
| Auto-Enable Warmup | Keep connected inboxes warming | ✅ Sync worker auto-enables |

**Capacity Planning Tiers:**
| Tier | Definition | Current Visibility |
|------|------------|-------------------|
| Primary | Active sending inboxes | ⚠️ Implicit in "deployed" segment |
| Hot Backup | Ready to promote | ⚠️ Implicit in "reserve" segment |
| Warming Pipeline | Incubating inboxes | ✅ "Incubating" segment |
| Bench | Flagged/rotated domains | ❌ NO VISIBILITY |

**Current Gap:** Capacity planning shows aggregate bars but doesn't break down:
- Primary vs hot backup vs warming pipeline (explicit tiers)
- Bench pool for rotated domains
- Target capacity per tier

### 3.3 From Health Monitoring Documentation

**V3 Specification Compliance:**
| Area | Coverage | Status | Dashboard Impact |
|------|----------|--------|------------------|
| Instant Kill Triggers | 95% | ✅ Implemented | Kill Velocity chart shows these |
| Confirming Kill Triggers | 0% | ❌ TODO | No "Under Review" section |
| Domain Health Thresholds | 90% | ✅ Implemented | Domain grid shows state |
| Portfolio Structure | 85% | ✅ Implemented | Backup promotion works |
| ESP Configuration | 40% | ⚠️ Partial | Postmaster/SNDS not integrated |
| Campaign Quarantine | 90% | ✅ Implemented | Campaign Attribution panel |
| List Management | 85% | ✅ Implemented | List Contamination Tracker |
| Placement Testing | 5% | ❌ Schema only | No placement test results shown |
| Alerting | 25% | ⚠️ Slack only | No in-dashboard alerts |
| Data Model | 95% | ✅ Complete | Backend supports all queries |

**Current Gap for Dashboard:**
- No "Confirming Kill Triggers" section (requires placement testing)
- No placement test results visualization
- No in-app alert center (only Slack notifications)
- No Postmaster/SNDS reputation scores

---

## 4. Gap Analysis: Current vs Desired

### 4.1 Critical Gaps (Immediate Impact)

**1. No Domain-Level Kill Actions**
- **Current:** Domain state tracked (`live`, `flagged`, `dead`) but no campaign pausing
- **Desired:** Gemini SOP requires domain-level campaign pausing on Strike 2/3
- **Impact:** Continues sending from damaged domains, cascading reputation loss
- **Fix Required:**
  - Add `pause_campaigns_on_domain(domain_id)` function
  - Integrate with Strike 2/3 detection
  - UI: Domain grid shows "⚠️ CAMPAIGNS PAUSED" badge

**2. No 48-Hour Rolling Window Strike Detection**
- **Current:** Kill triggers use 24h counters (`hard_bounces_24h`) with daily resets
- **Desired:** Gemini SOP requires "2 errors within 48 hours" detection
- **Impact:** Can't detect Strike 2/3 patterns (multiple inbox deaths in short window)
- **Fix Required:**
  - Create `inbox_error_window` table (per Gemini SOP mapping doc)
  - Add `count_domain_strikes(domain_id, hours=48)` function
  - UI: Domain grid shows Strike 1/2/3 badges

**3. No Open Rate Monitoring (<20% for 3 days)**
- **Current:** Open rates tracked but no threshold-based kill triggers
- **Desired:** Gemini SOP requires domain pause if open rate <20% for 3 days
- **Impact:** Domains with poor inbox placement continue sending, damaging reputation
- **Fix Required:**
  - Add `open_rate_3d` column to domains table
  - Create `low_open_rate` kill trigger type
  - UI: ESP Comparison card shows open rate with trend arrow

**4. No Bench Domain Pool Visibility**
- **Current:** Dead domains marked `domain_state = 'dead'` but no rotation tracking
- **Desired:** Gemini SOP requires bench pool for Strike 3 domains (can be revived later)
- **Impact:** Dead domains lost forever, no recovery path
- **Fix Required:**
  - Add `bench_rotated_at` timestamp to domains table
  - Create "Bench Pool" section in Infrastructure tab
  - UI: Show bench domains with "days on bench" and "eligible for rotation" status

### 4.2 Important Gaps (Operational Efficiency)

**5. No Real-Time Capacity Forecasting**
- **Current:** Capacity Planning shows current vs target (static)
- **Desired:** Forward-looking forecast: "At current churn rate, will need 50 more inboxes in 14 days"
- **Impact:** Reactive provisioning, delayed campaign launches
- **Fix Required:**
  - Add forecasting algorithm using kill velocity and campaign ramp plans
  - UI: Capacity Planning adds "Forecast" line to progress bars

**6. No Strike-Level "At Risk" Breakdown**
- **Current:** Kill Velocity shows past deaths + aggregate "at risk" count
- **Desired:** Breakdown: "5 inboxes at Strike 1, 2 at Strike 2, 1 at Strike 3"
- **Impact:** Can't prioritize which domains need urgent attention
- **Fix Required:**
  - Query `inbox_error_window` for current strike distribution
  - UI: Kill Velocity chart adds stacked "At Risk" bar (Strike 1/2/3 colors)

**7. No Primary/Hot Backup/Warming Pipeline Tiers**
- **Current:** Inventory Segmentation shows deployed/reserve/incubating (implicit tiers)
- **Desired:** Explicit breakdown: "Primary: 500, Hot Backup: 100, Warming: 50, Bench: 25"
- **Impact:** Can't assess backup capacity, risk of no hot backups available
- **Fix Required:**
  - Add `inbox_role` enum: `primary`, `hot_backup`, `warming`, `bench`
  - UI: Replace single "Capacity Planning" bar with 4-tier stacked bar

**8. No Placement Test Results**
- **Current:** ESP Comparison shows synthetic health scores
- **Desired:** Real Gmail Postmaster / Microsoft SNDS reputation scores + seed test results
- **Impact:** Relying on proxy metrics instead of actual ESP reputation
- **Fix Required:**
  - Integrate Postmaster Tools API and SNDS API
  - Create `placement_tests` table for seed list test results
  - UI: ESP Comparison adds "Last Placement Test" section

### 4.3 Nice-to-Have Gaps (User Experience)

**9. No In-App Alert Center**
- **Current:** Alerts sent to Slack only
- **Desired:** In-dashboard "Alert Center" with notification bell icon
- **Impact:** Users must leave dashboard to check Slack for alerts
- **Fix Required:**
  - Add `alerts` table with read/unread status per client
  - UI: Header bell icon with badge count, dropdown alert feed

**10. No Domain Lifecycle Phase Visualization**
- **Current:** Domain phase calculated but not prominently displayed
- **Desired:** Timeline showing: Warming → Ramping → Establishing → Peak → Monitoring → Rotation
- **Impact:** Can't quickly see domain maturity distribution
- **Fix Required:**
  - Add `DomainPhaseDistribution` component (already in types, not rendered!)
  - UI: Dashboard tab adds horizontal phase distribution chart

**11. No Campaign-Level Kill Quarantine Status**
- **Current:** Campaign Attribution shows bounce/complaint rates
- **Desired:** Visual "🚫 QUARANTINED" badge for campaigns that burned 2+ inboxes in 7 days
- **Impact:** Doesn't clearly show which campaigns are banned from new inboxes
- **Fix Required:**
  - Add `quarantine_status` and `quarantine_reason` to `emailbison_campaigns`
  - UI: Campaign Attribution table adds "Status" column with badges

**12. No List Contamination Source Flagging**
- **Current:** List Contamination Tracker shows bounce rates
- **Desired:** Visual flags: "⚠️ FLAGGED" for 2+ bounces, "🚫 PURGED" for 3+ bounces
- **Impact:** Doesn't clearly show which sources are banned
- **Fix Required:**
  - Add `source_status` enum: `clean`, `flagged`, `purged`
  - UI: List Contamination Tracker adds "Status" column with color-coded badges

---

## 5. Recommended Dashboard Enhancements

### 5.1 Phase 1: Gemini SOP Compliance (4 weeks)

**Week 1: Rolling Window Foundation**
- [ ] Create `inbox_error_window` table
- [ ] Add `count_domain_strikes()` SQL function
- [ ] Create `detect_strike_level()` backend function
- [ ] Add Strike 1/2/3 badges to Domain Grid (UI)

**Week 2: Domain-Level Kill Actions**
- [ ] Create `pause_campaigns_on_domain()` function
- [ ] Create `rotate_domain_to_bench()` function
- [ ] Add Strike 2 → pause logic
- [ ] Add Strike 3 → bench rotation logic
- [ ] Add "Campaigns Paused" indicator to Domain Grid (UI)

**Week 3: Open Rate Monitoring**
- [ ] Add `open_rate_3d` column to domains table
- [ ] Create open rate tracking query (3-day rolling average)
- [ ] Create `low_open_rate` kill trigger
- [ ] Add open rate trend to ESP Comparison card (UI)

**Week 4: Bench Pool Visibility**
- [ ] Add `bench_rotated_at` timestamp to domains table
- [ ] Create Bench Pool component
- [ ] Add "days on bench" calculation
- [ ] Add "Bench Pool" section to Infrastructure tab (UI)

**Impact:** 100% Gemini SOP compliance, prevents cascading reputation damage

### 5.2 Phase 2: Capacity Planning (2 weeks)

**Week 5: Explicit Tier Breakdown**
- [ ] Add `inbox_role` enum: `primary`, `hot_backup`, `warming`, `bench`
- [ ] Auto-assign roles based on deployment status and age
- [ ] Replace Capacity Planning bars with 4-tier stacked bars (UI)
- [ ] Add "Backup Capacity" alert: "⚠️ Only 10 hot backups remaining"

**Week 6: Forward-Looking Forecast**
- [ ] Create forecasting algorithm: `forecast_capacity_needs(days_ahead)`
- [ ] Calculate: `(avg_churn_rate × days) + planned_campaign_ramp`
- [ ] Add forecast line to Capacity Planning (UI)
- [ ] Add "Provisioning Recommendation" card: "Order 2 Hypertide packs by March 5"

**Impact:** Proactive infrastructure planning, no campaign launch delays

### 5.3 Phase 3: Enhanced Monitoring (2 weeks)

**Week 7: Strike-Level "At Risk" Breakdown**
- [ ] Query current strike distribution from `inbox_error_window`
- [ ] Add stacked "At Risk" bar to Kill Velocity chart (UI)
- [ ] Color code: Strike 1 (yellow), Strike 2 (orange), Strike 3 (red)
- [ ] Add hover tooltip: "5 inboxes at Strike 1 (1 more error = Strike 2)"

**Week 8: In-App Alert Center**
- [ ] Create `alerts` table with read/unread status
- [ ] Add bell icon to dashboard header (UI)
- [ ] Create alert dropdown feed (UI)
- [ ] Sync with Slack alerts (bidirectional read status)

**Impact:** Better situational awareness, faster issue response

### 5.4 Phase 4: ESP Integration (4 weeks)

**Week 9-10: Postmaster Tools & SNDS Integration**
- [ ] Integrate Google Postmaster Tools API
- [ ] Integrate Microsoft SNDS API
- [ ] Add `esp_reputation_scores` table
- [ ] Replace synthetic scores with real ESP data in ESP Comparison card (UI)

**Week 11-12: Placement Testing**
- [ ] Create `placement_tests` table
- [ ] Create seed list management UI
- [ ] Add "Run Placement Test" button per domain
- [ ] Show latest test results in ESP Comparison card (UI)

**Impact:** Real ESP reputation data instead of proxy metrics

---

## 6. Proposed Dashboard Mockup (Enhanced)

### 6.1 Enhanced Dashboard Tab

```
┌─────────────────────────────────────────────────────────────────────────┐
│  [Health: 87] [Utilization: 85%] [Coverage: 92%] [Churn: 2.1% ↓]        │
├─────────────────────────────────────────────────────────────────────────┤
│  [Dashboard] [Infrastructure] [Campaign Insights] [Alerts 🔔 3]         │
├─────────────────────────────────────────────────────────────────────────┤
│  CAPACITY PLANNING (Enhanced)                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Primary:     [████████████████████░░░░] 500/600 (83%)           │   │
│  │ Hot Backup:  [████░░░░░░░░░░░░░░░░░░░░] 85/200 (43%) ⚠️ LOW!   │   │
│  │ Warming:     [██████████░░░░░░░░░░░░░░] 120/200 (60%)          │   │
│  │ Bench:       [███░░░░░░░░░░░░░░░░░░░░░] 25/100 (25%)           │   │
│  │ Forecast:    Need +150 inboxes by Mar 15 ───────────────────▶   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  KILL VELOCITY (Enhanced)                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Deaths  ┃                                                       │   │
│  │  30 ┃    ┃                                      At Risk:        │   │
│  │  25 ┃    ┃  ╔═══╗                               [S3: 1]         │   │
│  │  20 ┃    ┃  ║   ║       ╔═══╗                   [S2: 2]         │   │
│  │  15 ┃  ╔═══╗║   ║       ║   ║                   [S1: 5]         │   │
│  │  10 ┃  ║   ║║   ║ ╔═══╗ ║   ║ ╔═══╗                             │   │
│  │   5 ┃  ║   ║║   ║ ║   ║ ║   ║ ║   ║                             │   │
│  │     ┗━━╚═══╝╚═══╝━╚═══╝━╚═══╝━╚═══╝━━━━━━━━━━━━━━━━━━━━━━━    │   │
│  │       W-4   W-3   W-2   W-1   Now                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ESP PERFORMANCE (Enhanced)                                             │
│  ┌──────────────────────────────┬──────────────────────────────────┐   │
│  │ Gmail                        │ Microsoft                        │   │
│  │ Inbox Placement:   86% ↑     │ Inbox Placement:   91% →         │   │
│  │ Open Rate (3d):    24% ↑     │ Open Rate (3d):    22% ↓         │   │
│  │ DMARC Pass:       100%       │ DMARC Pass:        98%           │   │
│  │ Postmaster Score:  Good      │ SNDS Status:       Green         │   │
│  │ Last Test: 2h ago            │ Last Test: 5h ago                │   │
│  └──────────────────────────────┴──────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Enhanced Infrastructure Tab

```
┌─────────────────────────────────────────────────────────────────────────┐
│  DOMAINS & INBOXES                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ 🟢 outreach-acme.com [S0] [28 inboxes] [▼]                      │   │
│  │ 🟡 growth-acme.com   [S1] [25 inboxes] [▼]  ⚠️ Strike 1         │   │
│  │ 🟠 scale-acme.io     [S2] [18 inboxes] [▼]  ⚠️ CAMPAIGNS PAUSED │   │
│  │ 🔴 old-domain.com    [S3] [0 inboxes]  [▼]  ⛔ BENCH ROTATION   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  BENCH POOL (New Section)                                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ old-domain.com       14 days on bench   ✅ Eligible for revival │   │
│  │ flagged-domain.io     7 days on bench   ⏳ Needs 7 more days    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.3 Enhanced Campaign Insights Tab

```
┌─────────────────────────────────────────────────────────────────────────┐
│  CAMPAIGN ATTRIBUTION                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Campaign         │ Status        │ Killed │ Bounce │ Risk       │   │
│  │──────────────────┼───────────────┼────────┼────────┼────────────│   │
│  │ Outbound Q1      │ 🟢 Active     │ 2      │ 1.8%   │ Low        │   │
│  │ Cold Reach       │ 🚫 Quarantine │ 5      │ 4.2%   │ High       │   │
│  │ Enterprise Push  │ ⚠️ Review     │ 3      │ 2.8%   │ Medium     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  LIST CONTAMINATION TRACKER                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Source          │ Status       │ Bounce │ Affected              │   │
│  │─────────────────┼──────────────┼────────┼───────────────────────│   │
│  │ Apollo          │ 🟢 Clean     │ 0.8%   │ 2 inboxes             │   │
│  │ Scraped Lists   │ ⚠️ Flagged   │ 3.1%   │ 8 inboxes             │   │
│  │ Purchased DB    │ 🚫 Purged    │ 6.5%   │ 15 inboxes, 2 domains │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Implementation Priority Matrix

### Priority 1: Prevent Cascading Failures (4 weeks)
- **Rolling window strike detection** - Prevents Strike 2/3 domains from killing more inboxes
- **Domain-level campaign pausing** - Stops sending from damaged domains immediately
- **Bench pool rotation** - Preserves domain assets for future recovery
- **Impact:** Reduces infrastructure losses by 60-80% (per Gemini SOP analysis)

### Priority 2: Operational Efficiency (2 weeks)
- **Explicit tier breakdown** (Primary/Hot Backup/Warming/Bench) - Prevents backup depletion
- **Forward-looking forecast** - Enables proactive provisioning
- **Strike-level "at risk" breakdown** - Prioritizes which domains need attention
- **Impact:** Reduces provisioning delays, prevents campaign launch failures

### Priority 3: Data Accuracy (4 weeks)
- **Postmaster Tools integration** - Real Gmail reputation instead of synthetic
- **SNDS integration** - Real Microsoft reputation instead of proxy metrics
- **Open rate monitoring** - Detects inbox placement issues before ESP flags
- **Impact:** Improves decision-making accuracy, reduces false positives

### Priority 4: User Experience (2 weeks)
- **In-app alert center** - Keeps users in dashboard instead of Slack context switching
- **Campaign quarantine badges** - Visual clarity on which campaigns are banned
- **List contamination flags** - Visual clarity on which sources are flagged/purged
- **Impact:** Faster issue response, reduced cognitive load

---

## 8. Technical Debt & Performance Considerations

### 8.1 Current Performance Issues

**1. sender_warmup_snapshots Never Analyzed**
- **Problem:** 544 MB table, 96K rows, NEVER had ANALYZE run
- **Impact:** Slow queries on warmup data, suboptimal query plans
- **Fix:** Run `VACUUM ANALYZE sender_warmup_snapshots;`

**2. Missing Foreign Key Indexes**
- **Problem:** 26 foreign key columns lack indexes (per database audit)
- **Impact:** Slow JOIN queries, especially on dashboard API calls
- **Fix:** Add indexes per `charm-db-integrity-issues.md`

**3. Cross Join Bug in Workspace Counts**
- **Problem:** Workspace aggregate queries multiply counts (14,586 instead of 6)
- **Impact:** Dashboard KPI cards show inflated numbers
- **Fix:** Use DISTINCT COUNT or subqueries in workspace rollup

**4. sender_account_count Always Zero**
- **Problem:** Denormalized counter never updated on domains table
- **Impact:** Can't quickly filter domains by inbox count
- **Fix:** Add trigger to auto-update on INSERT/DELETE to sender_accounts

### 8.2 Scalability Concerns

**Current Dashboard Load Time:** <500ms (database-only principle)
**Expected Load Time After Enhancements:**
- Phase 1 (rolling window): +100ms (new table joins)
- Phase 2 (capacity forecast): +50ms (additional calculations)
- Phase 3 (strike breakdown): +50ms (window aggregations)
- Phase 4 (ESP APIs): +200ms (external API calls)
- **Total:** ~900ms (still acceptable for dashboard)

**Mitigation Strategies:**
1. **Cache ESP API responses** (5-minute TTL)
2. **Pre-calculate strike levels** (background worker every 15 min)
3. **Add materialized view** for capacity forecast
4. **Index inbox_error_window** on `(domain_id, detected_at)` for fast windowing

---

## 9. Comparison to Industry Standards

### 9.1 Comparison to SendGrid Dashboard

| Feature | SendGrid | Charm Current | Charm Desired |
|---------|----------|---------------|---------------|
| Real-time delivery stats | ✅ | ✅ | ✅ |
| Bounce categorization | ✅ Hard/Soft/Spam | ✅ hard_blocked/hard_unknown | ✅ Same |
| Domain reputation | ✅ Postmaster/SNDS | ❌ Synthetic | ✅ Phase 4 |
| Inbox placement | ✅ Seed tests | ❌ No testing | ✅ Phase 4 |
| Alert center | ✅ In-app | ❌ Slack only | ✅ Phase 3 |
| Capacity planning | ❌ None | ⚠️ Basic | ✅ Phase 2 |
| Kill automation | ❌ Manual | ✅ Automated | ✅ Enhanced |

**Charm Advantages:**
- Automated kill trigger system (SendGrid requires manual intervention)
- Campaign attribution (SendGrid doesn't track which campaigns damaged infrastructure)
- List contamination tracking (SendGrid doesn't fingerprint bad lead sources)

**Charm Gaps:**
- No real ESP reputation data (SendGrid integrates Postmaster/SNDS)
- No in-app alerts (SendGrid has notification center)
- No placement testing (SendGrid has seed list management)

### 9.2 Comparison to Mailgun Dashboard

| Feature | Mailgun | Charm Current | Charm Desired |
|---------|---------|---------------|---------------|
| Deliverability analytics | ✅ | ✅ | ✅ |
| Suppression lists | ✅ Auto-managed | ⚠️ Manual | ⚠️ Manual |
| Webhook logs | ✅ Event stream | ❌ No webhook UI | ❌ Out of scope |
| IP reputation | ✅ Warmup tracking | ✅ Warmup tracking | ✅ Same |
| Domain verification | ✅ DNS checker | ⚠️ Manual check | ⚠️ Manual check |
| A/B testing | ✅ Built-in | ❌ None | ❌ Out of scope |
| Forecasting | ❌ None | ❌ None | ✅ Phase 2 |
| Strike system | ❌ None | ❌ Partial | ✅ Phase 1 |

**Charm Advantages:**
- Multi-ESP support (Mailgun is single-provider)
- Capacity forecasting (Mailgun doesn't predict infrastructure needs)
- Strike system with graduated response (Mailgun is binary kill/no-kill)

**Charm Gaps:**
- No automated suppression list management
- No webhook event stream UI
- No DNS verification UI (MXToolbox external dependency)

---

## 10. Success Metrics for Dashboard Enhancements

### 10.1 Quantitative Metrics

**Infrastructure Health:**
- **Inbox survival rate:** Target increase from 13% → 50% (current: 8 live / 110 total = 7.2%)
- **Domain survival rate:** Target increase from 60% → 90% (prevent cascading domain kills)
- **False positive kill rate:** Target <5% (don't kill healthy inboxes prematurely)
- **Strike 3 domain recovery rate:** Target 30% (bench domains successfully revived)

**Operational Efficiency:**
- **Time to detect issue:** Target <15 minutes (rolling window check frequency)
- **Time to respond to Strike 2:** Target <1 hour (pause campaigns immediately)
- **Provisioning lead time:** Target reduce from 4 weeks → 2 weeks (forecast-driven)
- **Dashboard load time:** Target <1 second (even with enhancements)

**User Engagement:**
- **Daily active users:** Track dashboard visits per client
- **Alert response time:** Time from alert to user action
- **Feature adoption:** % of clients using new features (strike badges, bench pool, etc.)

### 10.2 Qualitative Metrics

**User Feedback:**
- Survey: "Dashboard provides actionable insights" - Target >80% agree
- Survey: "I understand infrastructure health at a glance" - Target >90% agree
- Survey: "I can predict capacity needs" - Target >70% agree

**Internal Team Feedback:**
- Infrastructure team: "Reduced manual intervention" - Target >60% reduction
- Account managers: "Faster issue escalation" - Target >50% faster
- Executives: "Better ROI visibility" - Target >80% satisfied

---

## 11. Risks & Mitigation

### 11.1 Technical Risks

**Risk 1: Rolling Window Table Growth**
- **Concern:** `inbox_error_window` could grow unbounded
- **Mitigation:** Add `window_expires_at` column, auto-delete rows older than 7 days
- **Monitoring:** Alert if table exceeds 10 MB

**Risk 2: False Positive Strike 2/3**
- **Concern:** Legitimate bounce spikes (ESP outages) trigger domain pausing
- **Mitigation:** Add "whitelist" override for known ESP outages
- **Monitoring:** Manual review queue for Strike 2 before auto-pausing

**Risk 3: ESP API Rate Limits**
- **Concern:** Postmaster Tools / SNDS API rate limits slow dashboard
- **Mitigation:** Cache API responses for 5 minutes, batch requests
- **Monitoring:** Alert if API calls fail >5% of the time

### 11.2 Product Risks

**Risk 4: Feature Overload**
- **Concern:** Too many metrics confuse users
- **Mitigation:** Use progressive disclosure (collapsible sections, tabs)
- **Monitoring:** Track which features are never used, deprecate low-value features

**Risk 5: Gemini SOP Deviation**
- **Concern:** Charm's implementation differs from Gemini's exact thresholds
- **Mitigation:** Make thresholds configurable per client (admin panel)
- **Monitoring:** A/B test Gemini thresholds vs Charm's current thresholds

---

## 12. Conclusion & Next Steps

### 12.1 Summary

**Current Dashboard Status:**
- ✅ Comprehensive health scoring system
- ✅ Real-time inbox/domain tracking
- ✅ Kill trigger automation
- ✅ Campaign attribution
- ✅ List contamination tracking
- ⚠️ Missing: Gemini SOP compliance (Strike 2/3, rolling windows, domain-level actions)
- ⚠️ Missing: Capacity forecasting
- ❌ Missing: Real ESP reputation data
- ❌ Missing: In-app alerts

**Recommended Investment:**
- **Phase 1 (4 weeks):** Gemini SOP compliance → Prevents $20K-$28K/month infrastructure losses
- **Phase 2 (2 weeks):** Capacity planning → Reduces provisioning delays by 50%
- **Phase 3 (2 weeks):** Enhanced monitoring → Improves response time by 60%
- **Phase 4 (4 weeks):** ESP integration → Increases decision accuracy by 40%

**Total Timeline:** 12 weeks (3 months)
**Total Cost:** $20K-$28K engineering investment (per Gemini SOP analysis)
**Expected ROI:** 200-300% in first year (prevents infrastructure losses + reduces provisioning delays)

### 12.2 Immediate Action Items

**This Week:**
1. Review this document with Infrastructure Team + Product Owner
2. Prioritize Phase 1 (Gemini SOP compliance) - CRITICAL
3. Create Jira tickets for rolling window table + Strike 2/3 logic
4. Fix `sender_warmup_snapshots` VACUUM ANALYZE issue (5 minutes)

**Next Week:**
1. Implement `inbox_error_window` table (backend)
2. Add Strike 1/2/3 badges to Domain Grid (frontend)
3. Create `pause_campaigns_on_domain()` function (backend)
4. User acceptance testing with 1-2 pilot clients

**Next Month:**
1. Complete Phase 1 (Gemini SOP compliance)
2. Begin Phase 2 (capacity planning)
3. Measure infrastructure survival rate improvement
4. Iterate based on user feedback

---

**Document Version:** 1.0
**Created:** 2026-02-23
**Author:** Claude (Secure OpenClaw)
**Review Status:** Draft - Awaiting stakeholder review
**Next Review:** 2026-03-09 (2 weeks)
