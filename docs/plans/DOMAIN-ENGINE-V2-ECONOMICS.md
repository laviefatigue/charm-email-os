# Domain Engine V2 - Economics-Driven Design

**Status**: Design Specification
**Created**: 2026-03-07
**Updated**: 2026-03-07
**Purpose**: Define the automated infrastructure management system with integrated economics model

---

## Executive Summary

Domain Engine V2 is an **automated infrastructure maintenance system** that:
- Monitors email sending capacity across client portfolios
- Predicts capacity degradation based on kill trigger velocity
- Automatically rotates domains and promotes Reserve pool
- Projects recovery timelines when Incubating domains graduate
- Reports economics transparently (what it costs to maintain infrastructure)

**Key shift**: From manual decision-making tool → automated system with human oversight.

---

## Domain Pool Terminology

### EmailBison Tags (System-Managed)

The system automatically manages these tags in EmailBison. The team simply uses inboxes tagged `live` for campaigns.

| Tag | Status | Meaning |
|-----|--------|---------|
| `live` | **Live** | Deployed to campaigns, actively sending |
| `reserve` | **Reserve** | Warmed backup, ready to promote when Live burns |
| `incubating` | **Incubating** | New domain in warmup phase, not ready yet |
| *(removed)* | **Burned** | Compromised by spam complaint, retired from rotation |

### Domain Lifecycle Flow

```
New Domain Purchased
        │
        ▼
   INCUBATING ──── warmup phase (7-14 days)
        │
        ▼ warmup complete
     RESERVE ──── warmed, waiting in pool
        │
        ▼ Live domain burns OR capacity needed
      LIVE ──── deployed to campaigns
        │
        ▼ spam complaint fires
     BURNED ──── retired, removed from system
```

### Why This Matters

- **Team simplicity**: Just use inboxes tagged `live` - system handles everything else
- **Automatic failover**: When Live domain burns, Reserve promotes automatically
- **Pipeline visibility**: Incubating shows what's coming online soon

---

## The Capacity Lifecycle

### How Capacity Degrades

```
Week 0: 100% capacity (all Live domains healthy, all inboxes connected)
    │
    ▼ KILL TRIGGERS FIRE
    │
    ├─ Inbox-level kills (81% of all kills):
    │   - fresh_inbox_bounce (63%)  → inbox dies, capacity -1
    │   - hard_bounces_24h (18%)    → inbox dies, capacity -1
    │   └─ Reserve inbox promotes automatically, $0 cost
    │
    └─ Domain-level kills (~12-15% of all kills, rate-based):
        - spam_complaint (rate >1.0%) → domain burned, ALL inboxes lost
        - provider_block (<1%)        → domain burned, ALL inboxes lost
        └─ Reserve domain promotes automatically, $12.50 rotation cost
        └─ Workspace circuit breaker: 3+ domains in 24h = fleet event, monitoring not burn
    │
    ▼
Week 2: 78% capacity (accumulated inbox deaths + 1 domain rotation)
    │
    ▼ INCUBATION PIPELINE
    │
    └─ 3 domains graduating from Incubating → Reserve in 12 days
    │
    ▼
Week 4: 94% capacity (graduated domains promoted to Live, capacity recovered)
```

### The Critical Insight

**99.9% of kills happen in the first 2 weeks of sending.**

This is the "danger zone" - infrastructure is most vulnerable post-warmup. The economics model must account for this burst pattern.

---

## Kill Trigger Economics

### Cost Classification

| Trigger Type | Kill Level | % of Total | Cost | Recovery Mechanism |
|--------------|------------|------------|------|-------------------|
| `fresh_inbox_bounce` | Inbox | 63% | **$0** | Reserve inbox promotes |
| `hard_bounces_24h` | Inbox | 18% | **$0** | Reserve inbox promotes |
| `spam_complaint` | **Domain** (rate-based) | ~12-15% | **$12.50** | Reserve domain promotes |
| `provider_block_*` | **Domain** | <1% | **$12.50** | Reserve domain promotes |

**Key economics**: ~85% of maintenance is FREE (Reserve inbox recovery). Rate-based burn logic reduces false positive domain burns compared to the old count-based approach (was 19%, now ~12-15% of kills result in domain rotation). The workspace circuit breaker further reduces unnecessary burns during fleet-wide campaign events.

### Rate-Based Domain Burn Thresholds

Domain burns are now evaluated by **complaint rate**, not inbox kill counts:

| Complaint Rate | Domain State | Action |
|----------------|-------------|--------|
| <0.1% | `live` | Healthy, no action |
| 0.3%+ | `monitoring` | Elevated risk, under observation |
| >1.0% | `burned` | Reserve domain promotes, $12.50 rotation cost |

**Workspace circuit breaker:** If 3+ domains hit monitoring/burn thresholds within 24 hours, the system treats it as a fleet-wide event (bad list, provider crackdown) and places all affected domains in `monitoring` instead of burning. This prevents cascade burns from a single bad campaign.

### Rotation Trigger Cascade

Domain rotation is triggered by either:

1. **Complaint rate burn** (>1.0% complaint rate, confirmed non-fleet-wide)
2. **Accumulated inbox deaths** crossing capacity threshold

```
P1: complaint rate >1.0% on domain     → rotate_now  (rate-based burn)
P2: All inboxes disconnected           → rotate_now  (no capacity left)
P3: complaint rate 0.3%+ on domain     → monitoring  (observation period)
P4: Capacity < 80% (Entra)/<67% (Google) → consider_rotate (threshold breach)
P5: 1 hard block                       → monitor (early warning)
P6: Disconnected with clean history    → monitor (reconnect opportunity)
```

### Recommended Action Logic

| Rotation Status | Recommended Action | Cost Implication |
|-----------------|-------------------|------------------|
| `rotate_now` | Rotate domain | $12.50 immediate |
| `consider_rotate` | Rotate domain | $12.50 pending |
| `monitor` (compromised) | Watch | $12.50 if escalates |
| `monitor` (clean history) | Reconnect | $0 (save the domain) |
| `healthy` | None | $0 |

---

## Reserve Pool Sizing (Per-Client)

### Current Model (Static)

```
All clients: 80% Live / 20% Reserve
```

### Proposed Model (Dynamic)

Reserve pool should scale with client's **kill trigger velocity**.

```
base_reserve = 20%

adjustment_factor = client_kill_rate / industry_avg_kill_rate

reserve_ratio = base_reserve × adjustment_factor
  - Minimum: 15% (low-risk clients, excellent list quality)
  - Maximum: 40% (high-risk clients, poor list quality)
```

### Examples

| Client | Kill Rate | Industry Avg | Adjustment | Reserve Ratio |
|--------|-----------|--------------|------------|---------------|
| Good List Client | 2%/month | 5%/month | 0.4x | 15% (minimum) |
| Average Client | 5%/month | 5%/month | 1.0x | 20% |
| Hello Hero (bad list) | 20%/month | 5%/month | 4.0x | 40% (maximum) |

### Provider-Specific Reserve Pools

**Critical**: Reserve domains must match the provider type being rotated. You cannot substitute a Google Reserve for a burned Entra domain.

```
Reserve Pool (by provider):
├── Entra:  2 domains (100 inboxes, 200 sends/day capacity)
├── Google: 1 domain  (3 inboxes, 60 sends/day capacity)
└── Total:  3 domains

⚠️ ALERT: Need 2 Entra rotations but only 1 Entra in Reserve!
```

**Why provider matters:**

| Provider | Inboxes/Domain | Sends/Day | Capacity Lost on Burn | Warmup Time |
|----------|----------------|-----------|----------------------|-------------|
| Entra | 50 | 100 | High impact | 14 days |
| Google | 3 | 60 | Lower impact | 7 days |

Losing one Entra domain = losing 50 inboxes and 100 sends/day.
Losing one Google domain = losing 3 inboxes and 60 sends/day.

**Same $12.50 rotation cost, but different capacity impact.**

### Incubation Pipeline by Provider

The Incubating pipeline should also be tracked by provider:

```
Incubating Pipeline:
├── Entra:  45 domains → 3 graduating in 7d, 5 in 14d
├── Google: 52 domains → 2 graduating in 4d, 8 in 12d
└── Total:  97 domains

Projected capacity gain:
├── +7 days:  +300 Entra sends/day, +120 Google sends/day
└── +14 days: +800 Entra sends/day, +600 Google sends/day
```

### Reserve Adequacy Check

```sql
-- How long until reserve is exhausted at current burn rate?
-- Must be calculated PER PROVIDER

entra_reserve_runway = entra_reserve_domains / monthly_entra_domain_kills
google_reserve_runway = google_reserve_domains / monthly_google_domain_kills

-- Adequacy thresholds (per provider):
-- > 3 months: ADEQUATE
-- 1-3 months: LOW (consider purchasing)
-- < 1 month: CRITICAL (urgent purchase needed)

-- Alert conditions:
-- "Need 2 Entra rotations but only 1 Entra reserve" → CRITICAL
-- "3 Entra incubating, graduating in 7d" → recovery timeline
```

### Reserve Status Indicators

| Status | Condition | UI Display |
|--------|-----------|------------|
| `adequate` | Reserve > 3 months runway | Green |
| `low` | Reserve 1-3 months runway | Yellow, "Consider ordering" |
| `critical` | Reserve < 1 month runway | Red, "Order now" |
| `exhausted` | Reserve = 0 for this provider | Red, "No reserve available!" |
| `mismatch` | Need Entra but only Google available | Red, "Wrong provider type" |

---

## Capacity Model by Provider

### Entra (Microsoft)

| Metric | Value |
|--------|-------|
| Inboxes per domain | 50 |
| Sends per inbox per day | 2 |
| Daily capacity per domain | 100 |
| Monthly capacity per domain | 3,000 |
| Rotation threshold | < 40 connected (80%) |

### Google Workspace

| Metric | Value |
|--------|-------|
| Inboxes per domain | 3 |
| Sends per inbox per day | 20 |
| Daily capacity per domain | 60 |
| Monthly capacity per domain | 1,800 |
| Rotation threshold | < 2 connected (67%) |

---

## Time-Based Projections

### The Forward-Looking View

The UI must show not just current state, but **where capacity is going**:

```
TODAY          +7 DAYS         +14 DAYS        +21 DAYS
  │               │               │               │
 78% ─────────── 72% ─────────── 85% ─────────── 94%
  │               │               │               │
  └─ 2 domains   └─ Projected    └─ 3 domains    └─ Full
     at risk        if no action    graduate        recovery
```

### Projection Formula

```
capacity_day_n = current_capacity
                 - (projected_kills × days × daily_kill_rate)
                 + (graduating_domains × domain_capacity)

Where:
- daily_kill_rate = client_30d_kills / 30
- graduating_domains = incubating domains with graduation_date <= day_n
- domain_capacity = inboxes_per_domain × sends_per_inbox
```

### Recovery Events

Track and display upcoming capacity recovery events:

| Event | Domain | Graduation Date | Capacity Gain |
|-------|--------|-----------------|---------------|
| Warmup complete | sparkwithcharm.com | Mar 19 | +60/day |
| Warmup complete | prospectcharm.com | Mar 21 | +60/day |
| Warmup complete | velocitycharm.co | Mar 23 | +60/day |

---

## Economics Reporting

### Per-Client Dashboard Metrics

**Current State:**
- Live capacity: 460 / 2,748 sends/day (17%)
- Domains: 11 Live, 3 rotating, 97 Incubating
- Reserve status (by provider):
  - Entra: 1 domain (LOW - need 2 rotations)
  - Google: 2 domains (ADEQUATE)

**This Week:**
- Inbox kills: 12 (all recovered via Reserve, $0)
- Domain rotations: 1 ($12.50)
- Net maintenance cost: $12.50

**30-Day Projection:**
- Expected rotations: 3-4 domains (2 Entra, 1-2 Google)
- Projected cost: $37.50 - $50.00
- Reserve shortfall: 1 Entra domain needed ($12.50)

**Total Top-Up Required:**
- Immediate rotations: 3 × $12.50 = $37.50
- Reserve replenishment: 1 Entra × $12.50 = $12.50
- **Total: $50.00**

### Kill Trigger Breakdown Visualization

```
┌─────────────────────────────────────────────────────────────────┐
│ KILL TRIGGER ECONOMICS (last 30 days)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ████████████████████████████████░░░░░░░░░░  63% Fresh Bounce   │
│ FREE - Reserve inbox recovery                                  │
│                                                                 │
│ ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  ~13% Spam Complaint│
│ $12.50/rotation - Domain burned (rate >1.0%, circuit breaker)  │
│                                                                 │
│ █████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  18% Hard Bounces   │
│ FREE - Reserve inbox recovery                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Cost this month: $37.50 (3 domain rotations)
vs theoretical: $144.50 (if every kill required rotation)
SAVINGS: $107.00 via Reserve automation
```

---

## Automation Behaviors

### What the System Does Automatically

| Event | Automatic Action | Human Notification |
|-------|------------------|-------------------|
| Inbox kill (bounce) | Mark dead, promote Reserve inbox | None (logged only) |
| Domain kill (spam) | Mark burned, promote Reserve domain | Slack alert |
| Capacity < 80% | Flag for rotation | Dashboard warning |
| Reserve exhausted (any provider) | Queue purchase recommendation | Slack alert |
| Incubation complete | Graduate to Reserve pool | Dashboard update |
| Inventory < target | Generate domain candidates | Purchase approval needed |

### Tag Management (EmailBison)

The system automatically updates EmailBison tags:

| Event | Tag Change | Affected Inboxes |
|-------|------------|------------------|
| Domain purchased | → `incubating` | All inboxes on domain |
| Warmup complete | `incubating` → `reserve` | All inboxes on domain |
| Domain promoted | `reserve` → `live` | All inboxes on domain |
| Domain burned | Remove all tags | All inboxes retired |

**Team workflow**: Simply use inboxes tagged `live` in campaigns. System handles everything else.

### Human Intervention Points

| Scenario | Required Action |
|----------|-----------------|
| Bulk purchase > $100 | Manual approval |
| New client onboarding | Set package parameters |
| Reserve ratio adjustment | Budget approval |
| Anomaly detected | Investigation |

---

## UI Design Requirements

### Primary View: Capacity Health

**Hero metric**: Current capacity % with trend indicator (↑↓→)

**Provider cards** (side by side):
- Entra: capacity %, Live/Reserve/Incubating counts, recovery timeline
- Google: capacity %, Live/Reserve/Incubating counts, recovery timeline

**Reserve status** (per provider with alerts):
```
Reserve Pool:
├── Entra:  1 domain ⚠️ LOW (need 2 rotations)
├── Google: 2 domains ✓ ADEQUATE
└── Total:  3 domains
```

### Secondary View: Domain Operations Table

**Grouped by severity**:
- Rotate Now (red) - Immediate action needed
- Watch (yellow) - At risk, monitoring
- Healthy (green) - Collapsed by default

**Per-domain columns**:
- Domain name + status badge (BURNED, clean)
- Provider (Entra/Google)
- Inboxes (connected/expected)
- Capacity %
- Issues (spam, hard block, disconnected counts)
- Impact (sends lost per day)
- Action button (Retire, Reconnect, Unwatch)

**Expandable rows**: Show individual inbox breakdown

### Tertiary View: Economics Summary

**Kill trigger bar**: Visual breakdown of 63% free / ~13% paid / 18% free (rate-based burns reduce false positives)

**Cost urgency**:
- "Act now: $37.50 (3 rotations)"
- "If delayed 7 days: $104.00"

**Incubation pipeline** (by provider):
- Entra: 45 incubating, 3 graduating in 7d
- Google: 52 incubating, 2 graduating in 4d
- Projected capacity gain on graduation

### Quaternary View: Activity Log

**Recent automation events**:
- Domain rotations (with cost and provider)
- Reserve promotions (which Reserve → Live)
- Graduations (Incubating → Reserve)
- Purchases

---

## Data Sources

### Production API Endpoints

| Endpoint | Data |
|----------|------|
| `/api/infrastructure/waterfall/client/{id}` | Domain list with rotation recommendations |
| `/api/health/analysis/kill-trigger-lifecycle` | Kill trigger breakdown by type |
| `/api/health/analysis/domain-capacity-impact` | Capacity loss by provider |

### Key Database Views

| View | Purpose |
|------|---------|
| `v_infrastructure_waterfall` | Domain health with rotation recommendation |
| `v_domain_sets` | Live/Reserve/Burned allocation per domain |
| `v_workspace_domain_sets` | Reserve pool summary per workspace |

### Key Database Fields

| Table.Field | Purpose |
|-------------|---------|
| `domains.pool_status` | `live`, `reserve`, `incubating`, `burned` |
| `domains.burn_breakdown` | JSON: `{"spam_complaint": 2, "hard_blocked_24h": 1}` |
| `sender_accounts.inventory_pool_status` | Inbox-level tag (matches domain) |
| `sender_accounts.warmup_started_at` | For calculating graduation date |

### Calculated Metrics (Frontend)

| Metric | Formula |
|--------|---------|
| Reserve runway (per provider) | `provider_reserve_domains / monthly_provider_kills` |
| Projected capacity | `current - (kills × days) + (graduations × capacity)` |
| Top-up cost | `(rotate_now × $12.50) + (consider_rotate × $12.50) + (reserve_gap × $12.50)` |
| Reserve savings | `(inbox_kills_month × $12.50) - (domain_kills_month × $12.50)` |
| Graduation date | `warmup_started_at + warmup_days` (14d Entra, 7d Google) |

---

## Production Data Reference

### Current Infrastructure (All Clients)

- **Total domains**: 391 (254 Google, 135 Microsoft)
- **Total inboxes**: 6,650 (2,658 connected, 3,992 disconnected)
- **Total kills**: 1,156 tracked

### Kill Trigger Distribution

- `fresh_inbox_bounce`: 725 (63%)
- `spam_complaint`: 220 (19%)
- `hard_bounces_24h`: 204 (18%)
- `hard_blocked_24h`: 7 (0.6%)

### Capacity Loss by Provider

| Provider | Current Daily | Lost Daily | Loss % |
|----------|---------------|------------|--------|
| Google | 6,100 | 4,320 | 41.5% |
| Microsoft | 3,524 | 1,840 | 34.3% |

### Example Client: Charm

- 107 total domains (11 active, 97 pipeline)
- 33 inboxes (23 connected)
- 460 daily capacity (all Google)
- Gap: 9 Entra + 14 Google domains needed

---

## Summary

Domain Engine V2 is an **economics-aware, automated infrastructure management system** that:

1. **Monitors** capacity health per client with kill trigger velocity tracking
2. **Predicts** future capacity based on burn rate and incubation pipeline
3. **Automates** domain rotation and Reserve promotion (by provider type)
4. **Reports** maintenance costs and Reserve savings transparently
5. **Recommends** reserve pool sizing based on client-specific risk profile
6. **Projects** recovery timelines showing when Incubating domains graduate
7. **Manages** EmailBison tags automatically (`live`, `reserve`, `incubating`)

The UI should surface this as a **command center dashboard** showing an autonomous system at work, with economics transparency and forward-looking projections.

### Key Terminology

| Term | EmailBison Tag | Meaning |
|------|----------------|---------|
| Live | `live` | Active sending domains |
| Reserve | `reserve` | Warmed backup, ready to promote |
| Incubating | `incubating` | Warming up, not ready yet |
| Burned | *(removed)* | Retired due to spam complaint |

**Team workflow**: Use inboxes tagged `live` in campaigns. System handles all transitions.

---

**Document Version**: 1.1
**Author**: Claude + Elliott
**Last Updated**: 2026-03-07
**Changes**: Updated terminology from A-Set/B-Set to Live/Reserve/Incubating. Added provider-specific reserve pool tracking.
