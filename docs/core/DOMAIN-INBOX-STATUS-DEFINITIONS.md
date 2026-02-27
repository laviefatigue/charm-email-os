# Domain & Inbox Status Definitions

**Document ID:** CORE-STATUS-001
**Created:** 2026-02-26
**Last Updated:** 2026-02-26

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
| **incubating** | < 14 days | In warmup period, fresh inbox |
| **active** | ≥ 14 days | Mature, ready for full deployment |
| **dead** | Any | Killed by kill trigger |

### 1.4 Inventory Pool: `inventory_pool_status`

| Status | Condition | Use |
|--------|-----------|-----|
| **reserve** | ≤0 hard bounces 24h, ≤2 in 7d | Ready for deployment |
| **deployed** | Assigned to active campaign | Currently sending |
| **warning** | ≥1 hard bounce 24h OR ≥3 in 7d | Needs cooldown |

---

## 2. Domain States

### 2.1 Primary State: `domain_state`

| State | Definition | Criteria |
|-------|------------|----------|
| **live** | Fully operational | `live_inbox_count > 0` AND `dead_inbox_count = 0` |
| **flagged** | Needs attention | `live_inbox_count > 0` AND `dead_inbox_count > 0` |
| **dead** | No operational capacity | `live_inbox_count = 0` |

### 2.2 Domain State Decision Tree

```
┌─────────────────────────────────────────────────────────────┐
│                   live_inbox_count = 0?                     │
└─────────────────────────────────────────────────────────────┘
                          │
           ┌──────────────┴──────────────┐
           │ YES                         │ NO
           ▼                             ▼
     ┌─────────┐              ┌───────────────────────────┐
     │  DEAD   │              │  dead_inbox_count > 0?    │
     └─────────┘              └───────────────────────────┘
                                          │
                           ┌──────────────┴──────────────┐
                           │ YES                         │ NO
                           ▼                             ▼
                     ┌──────────┐                  ┌─────────┐
                     │ FLAGGED  │                  │  LIVE   │
                     └──────────┘                  └─────────┘
```

### 2.3 Connection-Adjusted Domain Health

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

| Priority | Trigger | Threshold | Severity |
|----------|---------|-----------|----------|
| 1 | `spam_complaint` | ≥ 1 | Instant |
| 2 | `hard_blocked_24h` | ≥ 1 | Instant |
| 3 | `hard_unknown_24h` | ≥ 3 | Instant |
| 4 | `hard_bounces_24h` | ≥ 2 | Instant |
| 5 | `hard_bounce_rate_7d` | > 0.5% (min 20 sends) | Instant |
| 6 | `bounce_rate_all_7d` | > 5% (min 20 sends) | Instant |
| 7 | `fresh_inbox_bounce` | ≥ 1 (inbox < 14 days) | Instant |

### 3.2 Kill Trigger Flow

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
Domain counters updated
```

### 3.3 Tag-Only Policy

**Critical:** Inboxes are TAGGED but NEVER DELETED from EmailBison.
- Tag format: `flagged_{trigger_type}`
- Examples: `flagged_fresh_inbox_bounce`, `flagged_spam_complaint`
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

### 4.3 Current Issues (As of 2026-02-26)

| Workspace | Connected Live | Disconnected Live | Operational % |
|-----------|---------------|-------------------|---------------|
| Checkout Components | 0 | 1,866 | 0.0% |
| Peaksave | 3 | 687 | 0.4% |
| Sammy | 46 | 630 | 6.8% |
| Root Access | 0 | 624 | 0.0% |
| EventPanda | 30 | 406 | 6.9% |
| Charm | 23 | 158 | 12.7% |

---

## 5. Incubation Period

### 5.1 Definition

The **2-week incubation period** starts when warmup is enabled (`warmup_started_at`).

```
Timeline:
Day 0: Inbox added to EmailBison (first_seen_at)
Day 0-N: Warmup enabled (warmup_started_at) ← INCUBATION STARTS
Day 0-14 from warmup: Fresh inbox protection
Day 14+: Mature inbox, normal thresholds
```

### 5.2 Fresh Inbox Protection

During incubation:
- `fresh_inbox_bounce` trigger active
- ANY hard bounce = instant kill
- Rationale: Young inboxes haven't built reputation

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
   spam_complaint    hard_bounces     fresh_inbox_bounce
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
                    │    LIVE     │
                    └──────┬──────┘
                           │ 1+ inbox killed
                           ▼
                    ┌─────────────┐
                    │  FLAGGED    │◄─────┐
                    └──────┬──────┘      │ still has live
                           │             │
             all inboxes   │             │
             killed        ▼             │
                    ┌─────────────┐      │
                    │    DEAD     │──────┘ (can revert if inboxes added)
                    └─────────────┘
```

---

## 7. Database Schema Reference

### 7.1 Key Columns

| Table | Column | Type | Values |
|-------|--------|------|--------|
| sender_accounts | inbox_state | VARCHAR | live, dead |
| sender_accounts | status | VARCHAR | Connected, Not connected, Disabled |
| sender_accounts | inventory_lifecycle_status | VARCHAR | incubating, active, dead |
| sender_accounts | inventory_pool_status | VARCHAR | deployed, reserve, warning |
| sender_accounts | kill_trigger | VARCHAR | trigger type that killed it |
| domains | domain_state | ENUM | live, flagged, dead |
| domains | live_inbox_count | INTEGER | Count of live inboxes |
| domains | dead_inbox_count | INTEGER | Count of dead inboxes |

### 7.2 Verification Queries

```sql
-- Check inbox state distribution
SELECT inbox_state, status, COUNT(*)
FROM sender_accounts
GROUP BY 1, 2;

-- Check domain state consistency
SELECT
    domain_state,
    CASE WHEN live_inbox_count = 0 THEN 'no_live' ELSE 'has_live' END,
    COUNT(*)
FROM domains
GROUP BY 1, 2;

-- Find domains with inconsistent state
SELECT id, domain_name, domain_state, live_inbox_count, dead_inbox_count
FROM domains
WHERE (domain_state = 'live' AND live_inbox_count = 0)
   OR (domain_state = 'dead' AND live_inbox_count > 0);
```

---

## 8. Summary: What is "Dead"?

### Inbox is DEAD when:
- Kill trigger fired (spam, bounces, blocked)
- `inbox_state = 'dead'`
- Tagged in EmailBison with `flagged_{reason}`
- **Cannot be revived**

### Domain is DEAD when:
- `live_inbox_count = 0`
- All inboxes have been killed
- No operational capacity
- **Should be rotated/replaced**

### NOT Dead (Common Confusion):
- Inbox with `status = 'Not connected'` → NOT dead, just disconnected
- Domain with all disconnected inboxes → NOT dead, but 0% operational
- Domain marked `dead` but has live inboxes → **BUG, needs fixing**

---

**Document Version:** 1.0
**Maintained By:** System Architecture Team
