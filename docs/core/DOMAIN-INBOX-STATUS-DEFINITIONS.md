# Domain & Inbox Status Definitions

**Document ID:** CORE-STATUS-001
**Created:** 2026-02-26
**Last Updated:** 2026-03-19

---

## Executive Summary

This document defines all status states for domains and inboxes in Charm Email OS. Understanding these definitions is critical for:
- Accurate capacity calculations
- Proper kill trigger evaluation
- Dashboard reporting integrity

---

## 1. Inbox States

### 1.1 Primary State: `inbox_state`

| State | Meaning | Can Revert? |
|-------|---------|-------------|
| **live** | Inbox is active, not killed | → dead (one-way) |
| **dead** | Inbox was killed for bad behavior | ✗ permanent |

**Key Rule:** Only the kill processor sets `inbox_state = 'dead'`. Connection issues do NOT kill an inbox.

### 1.2 Connection Status: `status`

| Status | Meaning | Can Send? | Action Required |
|--------|---------|-----------|-----------------|
| **Connected** | OAuth valid, inbox operational | ✓ Yes | None |
| **Not connected** | OAuth expired or credentials issue | ✗ No | Reconnect in HyperTide/EmailBison |
| **Disconnected** | Same as "Not connected" | ✗ No | Reconnect in HyperTide/EmailBison |
| **Disabled** | Explicitly disabled in EmailBison | ✗ No | Also sets `inbox_state = 'dead'` |

**Critical Understanding:**
```
inbox_state = "live"  +  status = "Not connected"
→ Inbox is NOT dead, but CANNOT send emails
→ Has 0 operational capacity until reconnected
```

### 1.3 Inventory Lifecycle: `inventory_lifecycle_status`

| Status | Age | Meaning |
|--------|-----|---------|
| **incubating** | < 21 days | In warmup period, fresh inbox |
| **active** | ≥ 21 days | Mature, ready for full deployment |
| **dead** | Any | Killed by kill trigger |

### 1.4 Inventory Pool: `inventory_pool_status`

| Status | Condition | Use |
|--------|-----------|-----|
| **reserve** | ≤0 hard bounces 24h, ≤2 in 7d | Ready for deployment |
| **deployed** | Assigned to active campaign | Currently sending |
| **warning** | ≥1 hard bounce 24h OR ≥3 in 7d | Needs cooldown |

---

## 2. Domain States

### 2.1 Primary State: `domain_state` (Trigger-Aware)

Domain state is determined by **reputation kill count**, not simple dead inbox count. Only reputation kills affect domain state — list-quality and operational kills do not.

| State | Definition | Criteria |
|-------|------------|----------|
| **live** | Fully operational | Complaint rate < 0.1% AND below capacity safety net |
| **flagged** | Warning signal | Complaint rate 0.1% - 0.3% |
| **monitoring** | Under observation (7-day window) | Complaint rate 0.3% - 1.0%, OR workspace circuit breaker active (3+ domains with spam kills in 24h) |
| **dead** | Domain compromised | Complaint rate > 1.0%, OR capacity safety net (> 30% unhealthy AND (10+ inboxes OR 2+ unhealthy)) |

**Complaint rate** = spam-killed inboxes / total inboxes on domain
**Reputation kills** = `spam_complaint`, `hard_blocked_24h`
**Non-reputation kills** (do NOT affect domain state) = `hard_unknown_24h`, `hard_bounces_24h`, `hard_bounce_rate_7d`, `bounce_rate_all_7d`, `disconnected_timeout`

**Monitoring window**: Domains in `monitoring` are re-evaluated after 7 days. If complaint rate drops below 1.0%, domain returns to `flagged`. If rate exceeds 1.0%, domain burns.

### 2.2 Domain State Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│         Calculate domain complaint rate                      │
│  complaint_rate = spam_killed_inboxes / total_inboxes        │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              Workspace circuit breaker?
          (3+ domains with spam kills in 24h)
            YES → MONITORING (fleet-wide event)
            NO  ↓
    ┌─────────────┼──────────────┼──────────────┐
    │ > 1.0%      │ 0.3-1.0%    │ 0.1-0.3%     │ < 0.1%
    ▼             ▼              ▼               ▼
┌────────┐ ┌────────────┐ ┌──────────┐  ┌────────────────┐
│  DEAD  │ │ MONITORING │ │ FLAGGED  │  │ Capacity check │
│ (burn) │ │ (7-day)    │ └──────────┘  │ >30% unhealthy │
└────────┘ └────────────┘               │ AND (10+ inbox  │
                                        │ OR 2+ unhealthy)│
                                        └────────────────┘
                                              │
                                   ┌──────────┴──────────┐
                                   │ YES                  │ NO
                                   ▼                      ▼
                             ┌─────────┐            ┌─────────┐
                             │  DEAD   │            │  LIVE   │
                             │(safety) │            └─────────┘
                             └─────────┘
```

### 2.3 Domain Burn = Total Loss (Domain-Level Reserve Pool)

**When a domain burns, ALL inboxes on that domain are lost.** The reserve pool operates at the **domain level**, not the inbox level. You cannot split inboxes from the same domain — if the domain is burned, every inbox on it is condemned regardless of individual inbox health.

```
Domain "doselery.com" complaint rate exceeds 1.0%
    ↓
ALL 51 inboxes on doselery.com → condemned (even 46 healthy ones)
    ↓
burn_domain_and_promote() SQL function executes:
  1. Sets burned domain pool_status = 'burned'
  2. Finds oldest reserve domain in same workspace
  3. Promotes reserve domain to pool_status = 'live'
    ↓
If no reserve domain available → Slack alert:
  "URGENT: Order replacement domains via HyperTide"

EXCEPTION: Workspace circuit breaker
  3+ domains in workspace with spam kills in 24h
    → Domains enter monitoring instead of burning
    → Prevents cascade burns from bad list data
```

**Domain burn vs domain state** — these are separate concepts:
- **`domain_state`** (live/flagged/monitoring/dead) — computed by `health_checks.py` based on complaint rate thresholds. Informational.
- **`pool_status = 'burned'`** — set by `kill_processor.py` when complaint rate exceeds 1.0% (or after 7-day monitoring window). **Triggers reserve domain promotion.**

A domain can be `domain_state = 'dead'` (e.g., from capacity safety net) but NOT burned. A domain in `monitoring` (rate 0.3-1.0% or circuit breaker active) is under observation and may recover.

### 2.4 Vendor Constraint: Inbox-per-Domain Ratios

Inbox infrastructure is provisioned by **HyperTide** (vendor). We do not control how many inboxes are allocated per domain:

| ESP | Typical Inboxes/Domain | Daily Limit/Inbox | Domain Daily Capacity |
|-----|----------------------|-------------------|----------------------|
| **Gmail** | ~3 | 20 | ~60 sends/day |
| **Microsoft** | ~50 | 2 | ~100 sends/day |

This creates fundamentally different risk profiles:
- **Gmail**: More domains, fewer inboxes each. A single inbox kill = 33% of the domain. Domain burns lose ~3 inboxes (~60 sends/day).
- **Microsoft**: Fewer domains, many inboxes each. A single inbox kill = 2% of the domain. Domain burns are catastrophic — loses ~50 inboxes (~100 sends/day), most of which were healthy.

This ratio is not configurable by us. Infrastructure planning must account for the vendor-provided shape.

**Concentration risk**: Rate-based thresholds handle domain size differences proportionally. On a 50-inbox Microsoft domain, 1 spam kill = 2% rate (monitoring). On a 3-inbox Gmail domain, 1 spam kill = 33% rate (immediate burn). The 30% unhealthy capacity safety net also triggers more easily on small domains (1 dead out of 3 = 33%).

### 2.5 Connection-Adjusted Domain Health

**Problem:** A domain can be `live` (has live inboxes) but have 0% operational capacity (all disconnected).

| Scenario | domain_state | Operational? |
|----------|--------------|--------------|
| 10 live inboxes, all connected | live | ✓ 100% |
| 10 live inboxes, 5 connected | live | ⚠ 50% |
| 10 live inboxes, 0 connected | live | ✗ 0% |
| 0 live inboxes | dead | ✗ 0% |

**Recommendation:** Dashboard should show "operational capacity" = connected live inboxes.

---

## 3. Kill Triggers

### 3.1 Kill Trigger Priority Order

| Priority | Trigger | Threshold | Type |
|----------|---------|-----------|------|
| 0 | `spam_complaint` | ≥ 1 | Reputation |
| 1 | `hard_blocked_24h` | ≥ 2 | Reputation |
| 2 | `hard_unknown_24h` | ≥ 3 | List Quality |
| 3 | `hard_bounces_24h` | ≥ 2 | Operational |
| 4 | `hard_bounce_rate_7d` | > 2.0% (min 100 sends) | Operational |
| 5 | `bounce_rate_all_7d` | > 5% (min 100 sends) | Operational |

### 3.2 Domain Burn Classification

After an inbox is killed, the kill processor decides whether to also burn the domain:

| Classification | Triggers | Domain Action | Rationale |
|----------------|----------|---------------|-----------|
| **Rate-based domain evaluation** | `spam_complaint` | Rate < 0.3% = safe. 0.3-1.0% = monitoring (7-day). > 1.0% = burn. Circuit breaker overrides to monitoring. | Rate-based thresholds scale proportionally across domain sizes |
| **Inbox-level only** | All other triggers | Never burns domain | Bounces, disconnects, list-quality are inbox-level. Safe to promote B-Set inboxes from same domain |

```
Inbox killed with trigger_type
    ↓
Is it spam_complaint?
    YES → Calculate complaint rate (spam-killed / total inboxes)
           ↓
           Workspace circuit breaker? (3+ domains with spam kills in 24h)
               YES → Domain enters monitoring (fleet-wide list event)
               NO  ↓
           Rate > 1.0%?   → DOMAIN BURN. All inboxes condemned. Reserve domain promoted.
           Rate 0.3-1.0%? → Domain enters monitoring. Re-evaluate after 7 days.
           Rate < 0.3%?   → Inbox-level only. Domain safe. Promote B-Set inbox.
    NO ↓
Inbox-level kill. Domain continues operating. Promote B-Set inbox.
```

### 3.3 Kill Trigger Flow

```
Bounce/Complaint detected
       ↓
sync_events.py → response_messages
       ↓
health_checks.py → evaluate triggers
       ↓
Kill trigger fires → kill_queue
       ↓
kill_processor.py → tag in EmailBison
       ↓
inbox_state = 'dead' (locally)
       ↓
Domain-level evaluation:
  - Reputation kill? → Check cross-inbox pattern → Possibly burn domain
  - Update domain_state based on trigger-aware rules
```

### 3.4 Tag-Only Policy

**Critical:** Inboxes are TAGGED but NEVER DELETED from EmailBison.
- Tag format: `flagged_{trigger_type}`
- Examples: `flagged_spam_complaint`, `flagged_hard_blocked_24h`
- Purpose: Audit trail, visibility into kill reasons

---

## 4. Operational Capacity

### 4.1 Definition

**Operational Capacity** = Inboxes that CAN actually send emails

```sql
-- TRUE operational capacity
SELECT COUNT(*)
FROM sender_accounts
WHERE inbox_state = 'live'
  AND status = 'Connected'
```

### 4.2 Capacity Matrix

| inbox_state | status | Operational? | Counted in Capacity? |
|-------------|--------|--------------|---------------------|
| live | Connected | ✓ Yes | ✓ Should be |
| live | Not connected | ✗ No | ✗ Should NOT be |
| live | Disabled | ✗ No | ✗ Should NOT be |
| dead | Connected | ✗ No (killed) | ✗ No |
| dead | Not connected | ✗ No | ✗ No |

---

## 5. Incubation Period

### 5.1 Definition

The **21-day incubation period** starts when warmup is enabled (`warmup_started_at`).

```
Timeline:
Day 0: Inbox added to EmailBison (first_seen_at)
Day 0-N: Warmup enabled (warmup_started_at) ← INCUBATION STARTS
Day 0-21 from warmup: Incubating — standard kill triggers apply
Day 21+: Mature inbox, rate-based triggers now have enough volume
```

### 5.2 Incubation and Kill Trigger Coverage

During incubation, fresh inboxes are protected by the same triggers as mature inboxes. There are no special fresh-inbox triggers — the absolute-count triggers (`hard_blocked_24h >= 2`, `hard_unknown_24h >= 3`, `spam_complaint >= 1`) provide protection regardless of age.

**Note on low-volume ESPs**: Rate-based triggers (`hard_bounce_rate_7d > 2%`, `bounce_rate_all_7d > 5%`) require a minimum of 100 sends. At 2 sends/day (Microsoft), this threshold is not reached until ~day 50. Absolute-count triggers are the primary safety net for low-volume inboxes during incubation.

### 5.3 Age Calculation

```python
# CORRECT: Use warmup_started_at
inbox_age_days = (now - warmup_started_at).days

# WRONG: Do NOT use first_seen_at
# inbox_age_days = (now - first_seen_at).days  # ← INCORRECT
```

---

## 6. State Transitions

### 6.1 Inbox State Transitions

```
                    ┌─────────────┐
                    │    LIVE     │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
   spam_complaint    hard_blocked      hard_unknown
   hard_bounces      bounce_rate       disconnected
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    DEAD     │ (permanent)
                    └─────────────┘
```

### 6.2 Domain State Transitions

```
                    ┌─────────────┐
                    │    LIVE     │  (complaint rate < 0.1%)
                    └──────┬──────┘
                           │ rate 0.1-0.3%
                           ▼
                    ┌─────────────┐
                    │  FLAGGED    │
                    └──────┬──────┘
                           │ rate 0.3-1.0%
                           │ OR circuit breaker (3+ domains in 24h)
                           ▼
                    ┌─────────────┐
                    │ MONITORING  │  (7-day observation window)
                    └──────┬──────┘
                           │ rate > 1.0% (after window)
                           │ OR capacity safety net
                           ▼
                    ┌─────────────┐
                    │    DEAD     │
                    └──────┬──────┘
                           │ rate > 1.0% confirmed
                           ▼
                    ┌─────────────┐
                    │   BURNED    │ (pool_status, triggers reserve promotion)
                    └─────────────┘

Note: MONITORING can revert to FLAGGED if rate drops below 1.0% after 7 days.
List-quality kills (hard_unknown, hard_bounces, etc.)
do NOT advance domain state. Only reputation kills count.
```

---

## 7. Database Schema Reference

### 7.1 Key Columns

| Table | Column | Type | Values |
|-------|--------|------|--------|
| sender_accounts | inbox_state | ENUM | live, dead |
| sender_accounts | status | VARCHAR | Connected, Not connected, Disabled |
| sender_accounts | inventory_lifecycle_status | VARCHAR | incubating, active, dead |
| sender_accounts | inventory_pool_status | VARCHAR | deployed, reserve, warning |
| sender_accounts | kill_trigger | ENUM | trigger type that killed it |
| sender_accounts | killed_at | TIMESTAMP | when inbox was killed |
| domains | domain_state | ENUM | live, flagged, monitoring, dead |
| domains | pool_status | ENUM | live, reserve, burned, cancelled |
| domains | health_percentage | NUMERIC | % of live inboxes on domain |

### 7.2 Verification Queries

```sql
-- Check inbox state distribution
SELECT inbox_state, status, COUNT(*)
FROM sender_accounts
GROUP BY 1, 2;

-- Domain state with reputation kill count
SELECT
    d.domain_name,
    d.domain_state,
    d.pool_status,
    COUNT(*) as total_inboxes,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead' AND (
        sa.kill_trigger::text IN ('spam_complaint', 'hard_blocked_24h')
        OR sa.kill_trigger::text LIKE 'provider_block_%'
    )) as reputation_dead
FROM domains d
JOIN sender_accounts sa ON sa.domain_id = d.id
WHERE sa.is_active = TRUE
GROUP BY d.domain_name, d.domain_state, d.pool_status
ORDER BY reputation_dead DESC;
```

---

## 8. Summary: What is "Dead"?

### Inbox is DEAD when:
- Kill trigger fired (spam, bounces, blocked)
- `inbox_state = 'dead'`
- Tagged in EmailBison with `flagged_{reason}`
- **Cannot be revived**

### Domain is MONITORING when:
- Complaint rate 0.3% - 1.0% (7-day observation window), OR
- Workspace circuit breaker active (3+ domains with spam kills in 24h)
- **Under observation, may recover to flagged or escalate to dead/burned**

### Domain is DEAD when:
- Complaint rate > 1.0%, OR
- > 30% unhealthy AND (10+ inboxes OR 2+ unhealthy) (capacity safety net)
- **Should be rotated/replaced**

### Domain is BURNED when:
- Complaint rate exceeded 1.0% (or exceeded after monitoring window)
- `pool_status = 'burned'`
- **ALL inboxes on domain are condemned** (even healthy ones)
- Reserve domain auto-promoted. If no reserve: order from HyperTide.

### NOT Dead (Common Confusion):
- Inbox with `status = 'Not connected'` → NOT dead, just disconnected
- Domain with all disconnected inboxes → NOT dead, but 0% operational
- Domain with only list-quality kills → domain_state stays `live` (kills don't affect domain reputation)

---

**Document Version:** 2.0
**Last Updated:** 2026-03-19
**Maintained By:** System Architecture Team
