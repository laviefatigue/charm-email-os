# Hypertide Domain Rotation Policy - Impact on Health V3 System

**Document ID:** HYPERTIDE-V3-IMPACT-001
**Date:** 2026-02-23
**Related Docs:** HYPERTIDE-ROT-001, DASHBOARD-BETA-001
**Context:** Analyzing how Hypertide's domain-only rotation affects Health V3 implementation

---

## Executive Summary

**Critical Finding:** Hypertide's inability to add/remove individual inboxes fundamentally changes how we implement Health V3's rotation and capacity management.

**Key Impact Areas:**
1. **Kill Triggers** - Still work at inbox level (tag/flag), but capacity recovery requires domain replacement
2. **Domain Health Thresholds** - More critical now since we can't replace individual inboxes
3. **Portfolio Structure** - Backup promotion still works, but reserve capacity planning changes
4. **Capacity Planning** - Need higher buffers (20-30%) to absorb inbox deaths before domain swap

**V3 Compliance Impact:** Still ~78% compliant, but rotation strategy shifts from inbox-level to domain-level.

---

## Current Health V3 System Overview

### Core Components

#### 1. Inbox Kill Triggers (95% Implemented)
**What It Does:**
- Detects inbox-level issues (spam complaints, bounces, blocks)
- Tags inbox with trigger-specific flag (e.g., `flagged_spam_complaint`)
- Marks inbox as `dead` locally
- **Does NOT delete from EmailBison** (intentional design)

**Kill Triggers:**
| Trigger | Threshold | Status |
|---------|-----------|--------|
| Spam complaint | ≥1 | ✅ DONE |
| Hard blocked (24h) | ≥1 | ✅ DONE |
| Hard unknown (24h) | ≥3 | ✅ DONE |
| Hard bounces (24h) | ≥2 | ✅ DONE |
| Bounce rate (7d) | >0.5% | ✅ DONE |
| Total bounce rate (7d) | >5% | ✅ DONE |
| Fresh inbox bounce | ≥1 (<14 days old) | ✅ DONE |
| Provider block | Per-provider | ✅ DONE |

---

#### 2. Domain Health Thresholds (95% Implemented)
**What It Does:**
- Monitors domain-level health based on inbox deaths
- Transitions domains through lifecycle states
- Flags domains when too many inboxes die

**Thresholds (rate-based):**
| Condition | Action | Status |
|-----------|--------|--------|
| Spam rate <0.1% | Domain → Live | ✅ DONE |
| Spam rate 0.1-0.3% | Domain → Flagged | ✅ DONE |
| Spam rate 0.3-1.0% | Domain → Monitoring (7-day observation window) | ✅ DONE |
| Spam rate >1.0% | Domain → Burn immediately | ✅ DONE |
| >30% unhealthy AND (10+ total OR 2+ unhealthy) | Domain → Dead (capacity safety net) | ✅ DONE |
| 3+ domains with spam kills in 24h (workspace) | Circuit breaker → Monitoring, not burn | ✅ DONE |
| Domain bounce rate >5% | Domain → Flagged | ✅ DONE |
| Blocks across 2+ inboxes | Domain → Flagged | ✅ DONE |

**Note:** Domain burns are no longer instant from inbox death counts. The system uses spam complaint rates to determine severity, with a 7-day monitoring window for borderline cases (0.3-1.0%). This prevents premature burns from isolated inbox events and gives operators time to investigate.

---

#### 3. Portfolio Structure (85% Implemented)
**What It Does:**
- Manages inbox roles: Primary, Hot Backup, Warming
- Tracks pool tiers and capacity
- Auto-promotes backups when primaries die

**Features:**
- Inbox roles tracked in database ✅
- Pool tier tracking ✅
- Backup capacity calculations ✅
- **Backup promotion automation** ✅ (2026-02-21)
- Warming pipeline targets ✅

---

#### 4. Campaign Burn Tracking (95% Implemented)
**What It Does:**
- Links inbox deaths to campaigns
- Quarantines campaigns that burn too many inboxes
- Tracks burn triggers per campaign

**Features:**
- `campaign_burn_events` table ✅
- Burn counters per campaign ✅
- Quarantine triggers (2+ burns in 7d) ✅
- Granular trigger breakdown ✅

---

## Hypertide Constraints Review

### ❌ What Hypertide CANNOT Do:
1. Add individual inboxes to existing domains
2. Remove individual inboxes from domains
3. Swap individual bad inboxes
4. (Applies to both Hypertide domains AND BYO domains)

### ✅ What Hypertide CAN Do:
1. Replace entire domains (all inboxes together)
2. Swap single domain within multi-domain order
3. Provision new domains with fresh inboxes

### Operational Workarounds:
1. **Redistribute volume** across remaining healthy inboxes (3-4 emails/inbox/day max)
2. **Replace domain** via Hypertide Bulk interface when health degrades

---

## Impact Analysis by V3 Component

### 1. Kill Triggers - MINIMAL IMPACT ✅

**Current Behavior:**
- Inbox-level detection and tagging **still works perfectly**
- Kill triggers fire → Inbox tagged → Marked as dead locally
- No deletion from EmailBison (by design)

**Hypertide Impact:**
- ✅ Detection logic unchanged
- ✅ Tagging logic unchanged
- ⚠️ **NEW:** Dead inboxes reduce domain capacity (can't replace individually)
- ⚠️ **NEW:** Multiple dead inboxes → Domain replacement needed

**Required Changes:**
- **NONE** to kill trigger detection
- **ADD:** Domain capacity recalculation after inbox death
- **ADD:** Domain replacement trigger when capacity too low

**Code Location:**
- `sync_modules/health_checks.py` - No changes needed
- `sync_modules/kill_processor.py` - Add domain capacity update

**Example Addition:**
```python
# In kill_processor.py after tagging inbox
def _update_domain_capacity_after_kill(self, inbox):
    """Recalculate domain capacity after inbox death"""
    domain = inbox.domain
    active_inboxes = domain.total_inboxes - domain.dead_inboxes - 1  # -1 for this death

    # Conservative capacity: 3 emails/inbox/day
    new_capacity = active_inboxes * 3

    # Update domain
    domain.active_inbox_count = active_inboxes
    domain.daily_capacity = new_capacity
    domain.capacity_utilization = new_capacity / domain.expected_capacity

    # Check if domain needs replacement
    if domain.capacity_utilization < 0.70:  # <70% capacity
        self._flag_domain_for_replacement(domain, reason="capacity_loss")
```

---

### 2. Domain Health Thresholds - HIGH IMPACT ⚠️

**Current Behavior:**
- Monitors domain health based on dead inbox count
- Flags/pauses domains when thresholds breached
- Calculates unhealthy percentage

**Hypertide Impact:**
- ✅ Domain flagging **more critical now** (can't replace individual inboxes)
- ⚠️ **NEW:** Domain flagging → Must trigger domain replacement workflow
- ⚠️ **NEW:** Need to track "can maintain volume" status
- ⚠️ **NEW:** Domain lifecycle tied to replacement capability

**Required Changes:**
- **ENHANCE:** Add capacity-based domain flagging
- **ADD:** "Pending replacement" domain status
- **ADD:** Domain replacement workflow integration

**New Thresholds (rate-based):**
| Condition | Old Action | New Action |
|-----------|------------|------------|
| Spam rate <0.1% | Live | Live (no change) |
| Spam rate 0.1-0.3% | N/A | Flagged + Monitor capacity |
| Spam rate 0.3-1.0% | N/A | **Monitoring** (7-day observation window before burn decision) |
| Spam rate >1.0% | N/A | **Burn immediately** |
| >30% unhealthy (size-aware) | Pause | Dead only if 10+ total inboxes OR 2+ unhealthy (safety net) |
| 3+ domains spam-killed in 24h | N/A | **Workspace circuit breaker** → Monitoring, not burn |
| Capacity <70% | N/A | **Flag for replacement** |
| Capacity <40% | N/A | **Critical - Replace immediately** |

**Code Changes:**
```python
# In health_checks.py - Add capacity checks
def _check_domain_capacity_thresholds(self, domain):
    """Check if domain can maintain required volume"""
    active_inboxes = domain.total_inboxes - domain.dead_inboxes
    death_rate = domain.dead_inboxes / domain.total_inboxes

    # Calculate if we can maintain volume
    max_safe_capacity = active_inboxes * 4  # 4 emails/inbox/day max
    required_volume = domain.target_daily_volume
    can_maintain_volume = max_safe_capacity >= required_volume

    capacity_utilization = active_inboxes / domain.total_inboxes

    # Replacement triggers
    if death_rate >= 0.30:
        return "replace", "30%+ inbox deaths"

    if capacity_utilization < 0.40:
        return "replace", "Critical capacity loss (<40%)"

    if not can_maintain_volume:
        return "replace", "Cannot maintain required volume"

    if capacity_utilization < 0.70:
        return "redistribute", "Moderate capacity loss (70-40%)"

    return "healthy", None
```

**New Domain States:**
```sql
-- Add to domains table
ALTER TABLE domains ADD COLUMN rotation_status VARCHAR(50) DEFAULT 'healthy';
-- Values: 'healthy', 'redistributing', 'pending_replacement', 'retiring', 'retired'

ALTER TABLE domains ADD COLUMN replacement_reason TEXT;
ALTER TABLE domains ADD COLUMN replacement_requested_at TIMESTAMP;
ALTER TABLE domains ADD COLUMN replaced_by_domain VARCHAR(255);
```

---

### 3. Portfolio Structure - MEDIUM IMPACT ⚠️

**Current Behavior:**
- Inbox roles: Primary, Hot Backup, Warming
- Backup promotion when Primary dies
- 100% hot backup capacity target
- 50% warming pipeline target

**Hypertide Impact:**
- ✅ Backup promotion **still works** (role reassignment is local)
- ⚠️ **NEW:** Can't add new warming inboxes to existing domain
- ⚠️ **NEW:** Warming pipeline must come from **new domains**
- ⚠️ **NEW:** Reserve capacity buffer must be higher (20-30%)

**Required Changes:**
- **ADJUST:** Reserve capacity targets (increase from 50% to 70%)
- **ADD:** Warming pipeline must be separate domains
- **ENHANCE:** Backup promotion considers domain health

**Portfolio Math Changes:**

**OLD MODEL (Inbox-based rotation):**
```
Active Inboxes: 100
Hot Backup: 100 (100% of active)
Warming: 50 (50% of active)
Total Pipeline: 150 inboxes

When inbox dies: Replace with 1 warming inbox
```

**NEW MODEL (Domain-based rotation):**
```
Active Inboxes: 100 (across 2 domains @ 50 inboxes each)
Hot Backup: 100 (100% of active, across separate domains)
Warming: 70 (70% of active, must be separate domains!)
Buffer: 30 (30% buffer for inbox deaths before domain swap)
Total Pipeline: 200 inboxes (up from 150)

When inbox dies: Redistribute volume until domain capacity <70%
When domain dies: Replace entire domain (50 inboxes)
```

**Code Changes:**
```python
# In health.py - Update capacity calculations
def _calculate_portfolio_targets(self, client):
    """Calculate portfolio targets with domain-based rotation"""
    active_inboxes = client.active_inbox_count

    # Domain-based rotation requires higher reserves
    targets = {
        "hot_backup": active_inboxes * 1.0,  # 100% (unchanged)
        "warming": active_inboxes * 0.7,     # 70% (up from 50%)
        "buffer": active_inboxes * 0.3,      # 30% buffer (NEW)
        "total_pipeline": active_inboxes * 2.0  # 200% (up from 150%)
    }

    # Buffer absorbs inbox deaths until domain replacement
    # Example: 100 active inboxes
    # - Lose 20 inboxes → Redistribute to remaining 80 (within safe limits)
    # - At 30 deaths → Domain at 70% capacity → Trigger replacement
    # - Buffer ensures we can maintain volume during replacement warmup

    return targets
```

---

### 4. Campaign Burn Tracking - MINIMAL IMPACT ✅

**Current Behavior:**
- Links inbox deaths to campaigns
- Quarantines campaigns burning 2+ inboxes in 7d
- Tracks granular trigger breakdown

**Hypertide Impact:**
- ✅ Burn tracking **unchanged** (still inbox-level)
- ✅ Quarantine triggers **unchanged**
- ⚠️ **ENHANCE:** Add domain impact to burn events

**Required Changes:**
- **ADD:** Domain ID to burn events (already tracked)
- **ADD:** "Inboxes burned per domain" metric
- **ADD:** Campaign quarantine if burns across multiple domains

**Code Enhancement:**
```python
# In kill_processor.py - Enhance burn tracking
def _track_campaign_burn(self, inbox, trigger_type, campaign_id):
    """Track burn event with domain context"""
    # Existing burn tracking
    self._insert_burn_event(inbox, trigger_type, campaign_id)

    # NEW: Check if campaign burning across multiple domains
    recent_burns = self._get_campaign_burns_7d(campaign_id)
    burned_domains = set([burn.domain for burn in recent_burns])

    if len(burned_domains) >= 2:
        # Campaign burning across multiple domains → Serious issue
        self._quarantine_campaign(
            campaign_id,
            reason="burns_across_multiple_domains",
            affected_domains=list(burned_domains)
        )
```

---

### 5. Capacity Planning - HIGH IMPACT ⚠️

**Current System:**
- Uses HyperTide capacity views
- Tracks per-domain and per-client capacity
- Expected capacity: Entra (100 emails/day), Google (60 emails/day)

**Hypertide Impact:**
- ⚠️ **CRITICAL:** Capacity calculations must account for inbox deaths
- ⚠️ **CRITICAL:** Need 20-30% buffer for deaths before replacement
- ⚠️ **NEW:** Warmup lag when replacing domains (1-2 weeks)

**Current Capacity Formula:**
```
Domain Capacity = Total Inboxes × 2 emails/day
```

**NEW Capacity Formula:**
```
Conservative Capacity = Active Inboxes × 3 emails/day
Aggressive Capacity = Active Inboxes × 4 emails/day

Active Inboxes = Total Inboxes - Dead Inboxes

Effective Capacity = Conservative Capacity × 0.85  // 15% safety margin
```

**Required Changes:**

**1. Update Capacity Views:**
```sql
-- Update v_domain_capacity view
CREATE OR REPLACE VIEW v_domain_capacity AS
SELECT
    d.domain,
    d.total_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') as active_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,

    -- OLD: total_inboxes × 2
    -- NEW: active_inboxes × 3 (conservative)
    (COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') * 3) as daily_capacity_conservative,
    (COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') * 4) as daily_capacity_aggressive,

    -- Utilization: active / total
    ROUND(
        COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live')::DECIMAL /
        NULLIF(d.total_inboxes, 0) * 100,
        1
    ) as capacity_utilization_pct,

    -- Expected capacity (from HyperTide specs)
    CASE
        WHEN d.provider = 'microsoft' THEN d.total_inboxes * 2  -- Entra: 50 inboxes × 2 = 100
        WHEN d.provider = 'google' THEN d.total_inboxes * 20    -- Google: 3 inboxes × 20 = 60
    END as expected_capacity,

    -- Viability status
    CASE
        WHEN COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') = 0 THEN 'deprecated'
        WHEN capacity_utilization_pct < 40 THEN 'critical'
        WHEN capacity_utilization_pct < 70 THEN 'warning'
        ELSE 'healthy'
    END as viability_status,

    -- NEW: Rotation recommendation
    CASE
        WHEN capacity_utilization_pct < 40 THEN 'replace_immediately'
        WHEN capacity_utilization_pct < 70 THEN 'consider_replacement'
        WHEN dead_inboxes > 0 THEN 'redistribute_volume'
        ELSE 'no_action'
    END as rotation_recommendation

FROM domains d
LEFT JOIN sender_accounts sa ON sa.domain = d.domain
GROUP BY d.domain, d.total_inboxes, d.provider;
```

**2. Add Replacement Buffer View:**
```sql
CREATE VIEW v_client_rotation_buffer AS
SELECT
    c.client_id,
    c.client_name,

    -- Active capacity
    SUM(dc.active_inboxes) as total_active_inboxes,
    SUM(dc.daily_capacity_conservative) as total_daily_capacity,

    -- Required capacity (target volume)
    c.target_daily_volume,

    -- Buffer calculation
    SUM(dc.daily_capacity_conservative) - c.target_daily_volume as capacity_buffer,
    ROUND(
        (SUM(dc.daily_capacity_conservative) - c.target_daily_volume)::DECIMAL /
        NULLIF(c.target_daily_volume, 0) * 100,
        1
    ) as buffer_percentage,

    -- Buffer status
    CASE
        WHEN buffer_percentage >= 30 THEN 'healthy'       -- 30%+ buffer
        WHEN buffer_percentage >= 20 THEN 'adequate'      -- 20-30% buffer
        WHEN buffer_percentage >= 10 THEN 'low'           -- 10-20% buffer
        ELSE 'critical'                                    -- <10% buffer
    END as buffer_status,

    -- Domains at risk
    COUNT(*) FILTER (WHERE dc.viability_status = 'critical') as domains_critical,
    COUNT(*) FILTER (WHERE dc.viability_status = 'warning') as domains_warning,
    COUNT(*) FILTER (WHERE dc.rotation_recommendation = 'replace_immediately') as domains_needing_replacement

FROM clients c
JOIN v_domain_capacity dc ON dc.client_id = c.client_id
GROUP BY c.client_id, c.client_name, c.target_daily_volume;
```

---

### 6. Rotation Workflows - NEW FEATURE REQUIRED ⚠️

**What's Needed:**
A new workflow system to handle domain replacement, since we can't rotate individual inboxes.

**Workflow States:**
```
healthy → redistributing → pending_replacement → replacing → retired
```

**Rotation Decision Tree:**
```python
def evaluate_domain_rotation(domain):
    """Determine rotation action needed"""
    # Calculate health metrics
    total_inboxes = domain.total_inboxes
    dead_inboxes = domain.dead_inbox_count
    active_inboxes = total_inboxes - dead_inboxes
    death_rate = dead_inboxes / total_inboxes
    capacity_utilization = active_inboxes / total_inboxes

    # Check triggers
    is_blacklisted = domain.latest_blacklist_count > 0
    required_volume = domain.target_daily_volume
    max_safe_capacity = active_inboxes * 4
    can_maintain_volume = max_safe_capacity >= required_volume

    # Decision logic
    if death_rate >= 0.30:
        return {
            "action": "replace",
            "reason": "30%+ inbox deaths",
            "priority": "high"
        }

    if is_blacklisted:
        return {
            "action": "replace",
            "reason": "Domain on RBL",
            "priority": "critical"
        }

    if not can_maintain_volume:
        return {
            "action": "replace",
            "reason": "Cannot maintain required volume",
            "priority": "high"
        }

    if capacity_utilization < 0.40:
        return {
            "action": "replace",
            "reason": "Critical capacity loss",
            "priority": "high"
        }

    if domain.bounce_rate_7d > 0.10:
        return {
            "action": "replace",
            "reason": "Domain bounce rate >10%",
            "priority": "medium"
        }

    if capacity_utilization < 0.70:
        return {
            "action": "redistribute",
            "reason": "Moderate capacity loss",
            "priority": "low"
        }

    if dead_inboxes > 0:
        return {
            "action": "monitor",
            "reason": "Some inbox deaths, within tolerance",
            "priority": "low"
        }

    return {
        "action": "none",
        "reason": "Healthy",
        "priority": None
    }
```

**New Tables Required:**
```sql
CREATE TABLE domain_rotation_events (
    id SERIAL PRIMARY KEY,
    domain VARCHAR(255) NOT NULL,
    client_id UUID NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    -- event_type: 'redistribute', 'replace_requested', 'replace_completed', 'retired'
    reason TEXT,
    old_status VARCHAR(50),
    new_status VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE domain_replacement_queue (
    id SERIAL PRIMARY KEY,
    old_domain VARCHAR(255) NOT NULL,
    client_id UUID NOT NULL,
    replacement_reason TEXT NOT NULL,
    priority VARCHAR(20) NOT NULL,  -- 'critical', 'high', 'medium', 'low'
    status VARCHAR(50) DEFAULT 'pending',
    -- status: 'pending', 'in_progress', 'completed', 'cancelled'
    requested_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    new_domain VARCHAR(255),
    notes TEXT
);
```

---

## Updated V3 Implementation Priority

### Health V3 Compliance With Hypertide Constraints

**Original V3 Compliance:** ~78%
**With Hypertide Adjustments:** ~75% (some features need rework)

**What Stays the Same (No Changes):**
- ✅ Kill trigger detection (inbox-level)
- ✅ Kill trigger tagging
- ✅ Campaign burn tracking
- ✅ Backup promotion automation
- ✅ List segment quarantine
- ✅ Alerting system

**What Needs Enhancement:**
- ⚠️ Domain health thresholds (add capacity checks)
- ⚠️ Portfolio structure (higher reserves)
- ⚠️ Capacity planning (domain-based formulas)

**What's New (Required by Hypertide):**
- 🆕 Domain rotation workflows
- 🆕 Domain replacement queue
- 🆕 Capacity utilization monitoring
- 🆕 Volume redistribution automation

---

## Implementation Roadmap

### Phase 1: Critical Adjustments (Week 1)
**Goal:** Make Health V3 work with domain-only rotation

**Tasks:**
1. ✅ Update capacity calculation formulas (3-4 emails/inbox/day)
2. ✅ Add domain capacity utilization tracking
3. ✅ Enhance domain health thresholds with capacity checks
4. ✅ Create rotation decision logic
5. ✅ Add rotation status to domains table

**Deliverables:**
- Updated capacity views
- Domain rotation decision tree
- Rotation status tracking

**Time Estimate:** 8-12 hours

---

### Phase 2: Workflow Automation (Week 2)
**Goal:** Automate domain rotation workflows

**Tasks:**
1. Create `domain_rotation_events` table
2. Create `domain_replacement_queue` table
3. Build domain evaluation cron job (daily)
4. Add volume redistribution automation
5. Create Hypertide replacement workflow UI

**Deliverables:**
- Rotation event tracking
- Replacement queue system
- Automated daily checks
- Operator workflow documentation

**Time Estimate:** 12-16 hours

---

### Phase 3: Enhanced Monitoring (Week 3-4)
**Goal:** Add visibility and alerting

**Tasks:**
1. Add rotation status to dashboard
2. Create capacity buffer alerts
3. Add domain replacement recommendations to UI
4. Enhance Slack alerts with rotation events
5. Build capacity forecasting

**Deliverables:**
- Dashboard rotation cards
- Proactive alerts
- Replacement recommendations
- Capacity runway predictions

**Time Estimate:** 10-14 hours

---

## Key Metrics to Track

### Domain Health Metrics (NEW)
1. **Capacity Utilization:** Active inboxes / Total inboxes
2. **Death Rate:** Dead inboxes / Total inboxes
3. **Can Maintain Volume:** Boolean (max capacity ≥ required volume)
4. **Rotation Status:** healthy / redistributing / pending_replacement / retiring
5. **Days Until Rotation:** Predicted time until replacement needed

### Portfolio Metrics (UPDATED)
1. **Buffer Percentage:** (Available capacity - Required volume) / Required volume
2. **Domains Needing Replacement:** Count of domains flagged for swap
3. **Average Domain Lifespan:** Days from provisioning to retirement
4. **Rotation Rate:** Domains replaced per month
5. **Warmup Pipeline:** Domains in warming phase (1-2 weeks from deployment)

---

## Risk Assessment

### High Risks

#### Risk 1: Capacity Gap During Replacement
**Impact:** When replacing domain, new domain needs warmup (1-2 weeks). Capacity drops temporarily.

**Likelihood:** High (every domain replacement)

**Mitigation:**
- Maintain 20-30% capacity buffer at all times
- Replace domains proactively (before critical)
- Stagger replacements (don't swap multiple domains simultaneously)
- Consider pre-warming backup domains

**Monitoring:**
- Track buffer percentage daily
- Alert when buffer <20%
- Forecast capacity runway

---

#### Risk 2: Cascading Domain Failures
**Impact:** Multiple domains fail simultaneously (e.g., list quality issue affects all). Can't replace all at once.

**Likelihood:** Medium (depends on list quality practices)

**Mitigation:**
- Segment risk: Different domains for different campaigns/lists
- Maintain emergency reserve capacity (extra domains in warmup)
- Monitor leading indicators (bounce rates, spam complaints)
- Rapid response procedure for mass failures

**Monitoring:**
- Alert when 2+ domains flagged simultaneously
- Track cross-domain failure patterns
- Monitor campaign-level metrics

---

#### Risk 3: Frequent Domain Replacements
**Impact:** High domain churn → increased costs, operational overhead, warmup delays

**Likelihood:** Medium-High (if list quality poor)

**Mitigation:**
- **Prevention focus:** Improve list quality, sending practices
- Analyze root causes of domain deaths
- Optimize kill triggers (balance sensitivity)
- Improve warmup process

**Monitoring:**
- Track domains replaced per month
- Calculate average domain lifespan
- Analyze kill trigger distribution
- Compare to industry benchmarks

---

### Medium Risks

#### Risk 4: Manual Workflow Delays
**Impact:** Domain replacement requires manual Hypertide UI interaction. Delays = capacity loss.

**Likelihood:** Medium

**Mitigation:**
- Document clear replacement procedures
- Train operations team
- Set SLAs for replacement actions (e.g., 24-hour response)
- Explore Hypertide API for automation (future)

**Monitoring:**
- Track time from "pending_replacement" to "completed"
- Alert if replacement pending >24 hours

---

## Summary & Recommendations

### Critical Insights

1. **Health V3 mostly compatible** with Hypertide constraints
   - Kill triggers work perfectly (inbox-level detection)
   - Domain thresholds need capacity enhancements
   - Portfolio structure needs higher reserves

2. **Rotation shifts from inbox-level to domain-level**
   - Can't replace individual inboxes
   - Must redistribute volume or replace entire domain
   - Warmup lag (1-2 weeks) during replacement

3. **Capacity planning is critical**
   - Need 20-30% buffer for inbox deaths
   - Conservative formulas (3-4 emails/inbox/day)
   - Proactive domain replacement to avoid gaps

4. **Higher operational overhead**
   - Manual Hypertide UI interaction required
   - Need clear procedures and training
   - More complex capacity forecasting

---

### Recommended Actions

#### Immediate (This Week)
1. ✅ Update capacity calculation formulas
2. ✅ Add domain rotation status tracking
3. ✅ Enhance domain health thresholds
4. ✅ Build rotation decision logic
5. ✅ Document replacement workflow for ops team

#### Short-Term (Month 1)
1. Create rotation event tables
2. Build automated daily rotation checks
3. Add volume redistribution automation
4. Create replacement queue system
5. Add rotation status to dashboard

#### Long-Term (Quarter 1)
1. Explore Hypertide API for automation
2. Build predictive rotation (anticipate failures)
3. Optimize domain lifespan through better practices
4. Consider pre-warming backup domains
5. Analyze cost/benefit of rotation frequency

---

### Impact on V3 Compliance

**V3 Compliance Scorecard:**

| Section | Pre-Hypertide | Post-Hypertide | Delta | Notes |
|---------|---------------|----------------|-------|-------|
| Kill Triggers | 95% | 95% | 0% | ✅ No change |
| Domain Health | 95% | 90% | -5% | ⚠️ Need capacity checks |
| Portfolio | 85% | 80% | -5% | ⚠️ Higher reserves needed |
| Campaign Mgmt | 95% | 95% | 0% | ✅ No change |
| Capacity Planning | 85% | 75% | -10% | ⚠️ Formulas need updates |
| **Overall** | **78%** | **75%** | **-3%** | ⚠️ Minor adjustments needed |

**Conclusion:** Hypertide constraints require adjustments but don't break Health V3. Core functionality intact, capacity planning needs enhancement.

---

## Related Documents

- **HYPERTIDE-ROT-001:** Hypertide Domain Rotation Policy
- **DASHBOARD-BETA-001:** Client Dashboard Implementation Plan
- **RBL-IMPL-001:** RBL Implementation Guide
- `/charm-email-os/docs/features/health-monitoring.md` - Health V3 System
- `/charm-email-os/docs/features/v3-compliance-gap-analysis.md` - V3 Compliance

---

**Document Version:** 1.0
**Last Updated:** 2026-02-23
**Status:** Analysis Complete
**Next Steps:** Implement Phase 1 capacity adjustments
