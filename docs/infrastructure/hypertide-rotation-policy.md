# Hypertide Domain Rotation Policy & Implications

**Document ID:** HYPERTIDE-ROT-001
**Date:** 2026-02-23
**Source:** Email exchange with Hypertide Support
**Context:** Understanding infrastructure management constraints and rotation strategy

---

## Executive Summary

**Critical Finding:** Hypertide does NOT support individual inbox replacement. When inboxes go bad, we must replace the **entire domain**, not individual inboxes.

**Critical Finding #2:** Domain swaps are **only available for Entra (Microsoft) orders**. Google orders do **not** support domain swaps at this time. A burned Google domain is a permanent capacity and financial loss within that order.

**Impact:** Our rotation system must be **domain-based**, not inbox-based. Entra domain burns are recoverable via swap; Google domain burns are not.

---

## Email Exchange

### Question 1: Replacing Bad Inboxes
**Our Question:**
> When we detect a hard bounce message, we automatically "ice" that inbox in our email sequencer. Would it be possible to swap those bad inboxes for new clean inboxes for the same domain?

**Hypertide Response:**
> We're unable to create or remove individual inboxes within a domain, as inbox provisioning and management are fully automated on our end.
>
> If inboxes are iced due to hard bounces, we do not recommend attempting to replace individual inboxes. If deliverability concerns persist, the appropriate course of action would be to **replace the entire domain** rather than specific inboxes.
>
> As an alternative, you may redistribute sending volume across the remaining active inboxes. By redistribution, we mean keeping the total daily sending volume for the domain the same, but allocating it across fewer active inboxes. If you are seeing deliverability issues at the domain level, we recommend replacing the domain rather than increasing volume per inbox.
>
> For example, if five inboxes were sending two emails per day (10 total emails daily) and you choose not to use those inboxes, that same 10-email daily volume can be reallocated proportionally to the remaining active inboxes.
>
> **You can safely send 3–4 emails per inbox per day.**

---

### Question 2: Replacing Single Domain in Order
**Our Question:**
> When a domain goes bad and is a portion of an order, is this where we would initiate a swap on the order? For example, if a single Entra order with 2 domains, and one of those domains goes bad, do we initiate a swap of the domain for that specific order?

**Hypertide Response:**
> Yes — you can replace a single domain within an order without replacing the entire order.
>
> This can be done directly within your Hypertide account by following these steps:
> 1. Navigate to the Bulk page from the left-hand panel
> 2. Search for the domain you would like to update, or use the "Paste to Select" option to select multiple domains at once
> 3. Once selected, the available actions will appear at the bottom of the page
> 4. Choose the appropriate action and apply the update

---

### Question 3: Custom Domains (BYO)
**Our Question:**
> If we start supplying our own domains, this is somewhat a follow-up to question 1, as inboxes goes bad, can we add new inboxes and remove bad ones, or do we just perform a domain swap on the order?

**Hypertide Response:**
> The same inbox limitation applies whether the domains are purchased through Hypertide or supplied by you — we're unable to create or remove individual inboxes within a domain.
>
> If you begin seeing domain-level deliverability issues, we recommend replacing the entire domain rather than attempting to swap specific inboxes.

---

## Key Constraints

### ❌ What We CANNOT Do:
1. **Cannot add individual inboxes to a domain**
2. **Cannot remove individual inboxes from a domain**
3. **Cannot swap individual inboxes when they go bad**
4. Applies to both Hypertide domains AND customer-supplied domains (BYO)

### ✅ What We CAN Do:
1. **Replace entire domains** within an Entra order (swap)
2. **Redistribute sending volume** across remaining active inboxes on a domain
3. **Safely send 3-4 emails per inbox per day** (increased from typical 2/day)
4. **Swap domains via Hypertide Bulk interface** (Entra only)

---

## Domain Swap Availability by Provider

### Entra (Microsoft) — Swaps Available

When an Entra domain is burned:
1. We supply a **replacement domain** (BYO — we must source and provide the domain)
2. HyperTide disconnects all inboxes on the burned domain
3. HyperTide provisions fresh inboxes on the replacement domain
4. New inboxes enter 21-day incubation/warmup period
5. Domain swap is done via the Hypertide Bulk interface

**Entra swap is a recovery mechanism** — the order continues at $50/mo with restored capacity after warmup completes.

### Google — No Swaps Available

HyperTide does **not** support domain swaps for Google orders at this time.

When a Google domain is burned:
1. The domain and its 3 inboxes are **permanently lost** within that order
2. We continue paying the same $50/mo for the order
3. There is no mechanism to replace the burned domain
4. If all 5 Google domains in an order burn, the entire $50/mo is wasted
5. Only recourse: cancel the order and place a new one

---

## Economics of Domain Burns

We pay $50/month per order regardless of how many domains are operational. This makes swap availability a critical financial concern.

### Cost Per Domain by Provider

| Metric | Entra Order | Google Order |
|--------|-------------|--------------|
| **Cost** | $50/mo | $50/mo |
| **Domains/order** | 2 | 5 |
| **Cost per domain** | $25/mo | $10/mo |
| **Inboxes/domain** | ~52 | 3 |
| **Cost per inbox** | ~$0.48/mo | ~$3.33/mo |
| **Daily capacity/domain** | ~104 sends | ~60 sends |
| **Swap available?** | Yes | No |

### Financial Impact of a Domain Burn

| Scenario | Entra | Google |
|----------|-------|--------|
| **1 domain burned** | $25/mo idle until swapped (recoverable) | $10/mo wasted permanently |
| **Recovery path** | Supply new domain → swap → 21-day warmup | None within order |
| **Time to recover** | ~21 days (warmup) | Never (must cancel/reorder) |
| **Order at 100% burn** | 2 burns = $50/mo wasted (both swappable) | 5 burns = $50/mo wasted (not recoverable) |

### Why Swap Capability Matters

**Entra:** A domain burn is an **operational event**. Capacity loss is temporary — swap the domain, warmup the new inboxes, capacity restored. The $50/mo subscription continues to deliver value.

**Google:** A domain burn is a **financial leak**. Each burned Google domain is dead weight on the subscription. At $10/mo per domain, burning 3 of 5 domains means 60% of the order cost produces zero value with no fix short of cancellation.

**Implication for kill trigger tuning:** Google domain burns should be treated more conservatively than Entra burns because they are irrecoverable. The rate-based domain burn logic (complaint rate >1.0% to burn, with a monitoring state at 0.3%+) and workspace circuit breaker (3+ domains in 24h = fleet event) are especially important for Google domains where burns are permanent.

---

## Operational Strategies

### Strategy 1: Volume Redistribution (Temporary)
**When:** A few inboxes die on a domain, but domain health is still acceptable

**How:**
- Keep domain active
- Ice bad inboxes in sequencer
- Redistribute volume across remaining healthy inboxes
- Max safe volume: 3-4 emails per inbox per day

**Example:**
- Original: 5 inboxes × 2 emails/day = 10 emails/day total
- After 2 deaths: 3 inboxes × 3.33 emails/day = 10 emails/day total
- Still within safe limits (3-4 emails/inbox/day)

**When to Stop:**
- If domain-level deliverability issues appear
- If too many inboxes die (can't maintain volume safely)
- If RBL listings occur at domain level

---

### Strategy 2: Full Domain Replacement via Swap (Entra Only)
**When:** Entra domain shows deliverability issues or too many inbox deaths
**Availability:** Entra orders only — Google orders do NOT support domain swaps

**How:**
1. Source a replacement domain (BYO — we supply it)
2. Navigate to Hypertide Bulk page
3. Select the burned Entra domain
4. Initiate domain swap with the replacement domain
5. HyperTide disconnects burned domain inboxes and provisions fresh inboxes on replacement
6. Update our database to reflect new domain

**Process:**
- Entire domain replaced (all inboxes together)
- New domain goes through 21-day warmup/incubation
- Old domain retired completely

### Strategy 3: Order Cancellation & Reorder (Google Only)
**When:** Google domain(s) burn and capacity loss is unacceptable

Since Google orders do not support domain swaps, the only recovery path is:
1. Accept the permanent capacity loss within the current order, OR
2. Cancel the degraded order and place a new Google order ($50/mo)
3. New order provisions 5 fresh domains with 15 fresh inboxes
4. All inboxes enter 21-day warmup

**Trade-off:** Cancellation means losing any remaining healthy domains on the old order. Only worth it when the order is sufficiently degraded (e.g., 3+ of 5 domains burned).

---

## Impact on Rotation System

### Current Rotation Logic (Inbox-Based)
**OLD ASSUMPTION:** We can rotate out individual bad inboxes and add new ones.

**REALITY:** We cannot. We must work at the **domain level**.

---

### New Rotation Model (Domain-Based)

#### Phase 1: Within-Domain Rotation (Volume Redistribution)
**Trigger:** Individual inbox deaths detected (hard bounces)

**Action:**
1. Ice bad inbox in sequencer
2. Calculate remaining healthy inboxes
3. Redistribute volume across healthy inboxes (max 3-4 emails/day per inbox)
4. Monitor domain-level health

**Database Updates:**
```sql
-- Mark inbox as dead
UPDATE inboxes SET
  status = 'dead',
  death_reason = 'hard_bounce',
  died_at = NOW()
WHERE inbox_id = <inbox_id>;

-- Recalculate domain capacity
UPDATE domains SET
  active_inbox_count = active_inbox_count - 1,
  daily_capacity = active_inbox_count * 3  -- Conservative: 3 emails/inbox/day
WHERE domain = <domain>;
```

**Capacity Calculation:**
```python
# Conservative capacity calculation
active_inboxes = domain.total_inboxes - domain.dead_inboxes
safe_capacity = active_inboxes * 3  # 3 emails/inbox/day (conservative)
max_capacity = active_inboxes * 4   # 4 emails/inbox/day (aggressive)
```

---

#### Phase 2: Domain-Level Rotation (Full Replacement)
**Trigger:** Domain health degradation

**Indicators:**
1. Multiple inbox deaths (>30% of inboxes dead)
2. Domain appears on RBL
3. Domain-level deliverability issues (high bounce rate)
4. Cannot maintain required sending volume with remaining inboxes

**Action:**
1. Mark domain as "pending_replacement"
2. Initiate domain swap via Hypertide Bulk interface
3. New domain provisioned by Hypertide
4. Update database with new domain
5. Begin warmup process for new domain
6. Retire old domain completely

**Database Updates:**
```sql
-- Mark old domain for retirement
UPDATE domains SET
  status = 'retiring',
  retirement_reason = 'health_degradation',
  retirement_initiated_at = NOW()
WHERE domain = <old_domain>;

-- Create new domain entry
INSERT INTO domains (
  domain,
  client_id,
  provider,
  status,
  phase,
  total_inboxes,
  active_inbox_count,
  created_at
) VALUES (
  <new_domain>,
  <client_id>,
  'hypertide',
  'active',
  'warming',  -- Start in warmup
  <inbox_count>,
  <inbox_count>,
  NOW()
);

-- Transfer inboxes (or create new inbox records)
-- Hypertide will provision new inboxes, we need to sync them
```

---

## Rotation Triggers & Thresholds

### Tier 1: Volume Redistribution (Stay on Domain)
**Conditions:**
- ✅ Inbox deaths < 30% of domain
- ✅ Domain NOT on RBL
- ✅ Can maintain required volume at 3-4 emails/inbox/day
- ✅ No domain-level deliverability issues

**Action:** Ice bad inboxes, redistribute volume

---

### Tier 2: Domain Replacement (Swap Domain)
**Conditions (ANY of):**
- ❌ Inbox deaths ≥ 30% of domain
- ❌ Domain appears on RBL
- ❌ Cannot maintain required volume (too many dead inboxes)
- ❌ Domain-level bounce rate > threshold (e.g., 10%)
- ❌ Complaint rate >1.0% (rate-based domain burn)

**Note on rate-based burns:** Domain burns are now triggered by complaint rate thresholds, not count-based rules (e.g., "2+ inbox kills"). Thresholds: <0.1% = live, 0.3%+ = monitoring, >1.0% = burn. A workspace circuit breaker (3+ domains hit in 24h) prevents cascade burns from fleet-wide campaign events, placing domains in `monitoring` instead.

**Action:** Full domain replacement via Hypertide

---

## Rotation Workflow

### Automated Rotation Decision Tree

```python
def evaluate_domain_rotation(domain):
    """
    Determine if domain needs rotation and what type

    Returns:
        - "healthy": No action needed
        - "redistribute": Ice bad inboxes, redistribute volume
        - "replace": Full domain replacement needed
    """

    # Calculate health metrics
    total_inboxes = domain.total_inboxes
    dead_inboxes = domain.dead_inbox_count
    active_inboxes = total_inboxes - dead_inboxes
    death_rate = dead_inboxes / total_inboxes

    # Check RBL status
    is_blacklisted = domain.latest_blacklist_count > 0

    # Check if we can maintain volume
    required_volume = domain.target_daily_volume
    max_safe_capacity = active_inboxes * 4  # 4 emails/inbox max
    can_maintain_volume = max_safe_capacity >= required_volume

    # Decision logic
    if death_rate >= 0.30:
        return "replace"  # 30%+ inboxes dead

    if is_blacklisted:
        return "replace"  # Domain on RBL

    if not can_maintain_volume:
        return "replace"  # Can't maintain volume

    if domain.bounce_rate_7d > 0.10:
        return "replace"  # >10% bounce rate

    if dead_inboxes > 0:
        return "redistribute"  # Some deaths, but manageable

    return "healthy"  # No action needed
```

---

## Integration with Current System

### Database Schema Considerations

**Domains Table - Add Fields:**
```sql
ALTER TABLE domains ADD COLUMN IF NOT EXISTS rotation_status VARCHAR(50) DEFAULT 'healthy';
-- Values: 'healthy', 'redistributing', 'pending_replacement', 'retiring'

ALTER TABLE domains ADD COLUMN IF NOT EXISTS replacement_requested_at TIMESTAMP;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS replaced_by_domain VARCHAR(255);
ALTER TABLE domains ADD COLUMN IF NOT EXISTS replaces_domain VARCHAR(255);
```

**Rotation Events Table (New):**
```sql
CREATE TABLE IF NOT EXISTS domain_rotation_events (
  id SERIAL PRIMARY KEY,
  domain VARCHAR(255) NOT NULL,
  client_id UUID NOT NULL,
  event_type VARCHAR(50) NOT NULL,  -- 'redistribute', 'replace_requested', 'replace_completed'
  reason TEXT,
  metadata JSONB,
  created_at TIMESTAMP DEFAULT NOW()
);
```

---

### API Endpoints Needed

#### 1. Check Domain Rotation Status
```http
GET /api/rotation/evaluate/{domain}

Response:
{
  "domain": "example.com",
  "rotation_status": "healthy" | "redistribute" | "replace",
  "reason": "30% inbox death rate",
  "metrics": {
    "death_rate": 0.32,
    "active_inboxes": 17,
    "dead_inboxes": 8,
    "can_maintain_volume": false,
    "is_blacklisted": false
  },
  "recommendation": "Initiate domain replacement via Hypertide"
}
```

#### 2. Trigger Domain Replacement
```http
POST /api/rotation/replace/{domain}

Request:
{
  "reason": "high_death_rate",
  "notes": "32% inbox deaths, cannot maintain volume"
}

Response:
{
  "status": "replacement_requested",
  "old_domain": "example.com",
  "next_steps": "Complete replacement via Hypertide Bulk interface",
  "hypertide_instructions": [
    "1. Navigate to Hypertide Bulk page",
    "2. Search for domain: example.com",
    "3. Select domain and choose 'Replace Domain' action",
    "4. Confirm replacement",
    "5. Update system with new domain details"
  ]
}
```

#### 3. Complete Domain Replacement
```http
POST /api/rotation/complete-replacement

Request:
{
  "old_domain": "example.com",
  "new_domain": "newdomain.com",
  "new_inboxes": [...],  // Synced from Hypertide
  "replaced_at": "2026-02-23T21:00:00Z"
}

Response:
{
  "status": "replacement_completed",
  "old_domain_status": "retired",
  "new_domain_status": "warming",
  "new_domain_phase": "warming",
  "warmup_eta": "2026-03-09T00:00:00Z"  // ~2 weeks
}
```

---

## Hypertide Integration Points

### Manual Steps Required (Currently)
1. **Navigate to Hypertide Bulk page**
   - URL: [Hypertide account]/bulk

2. **Search for domain**
   - Use search box or "Paste to Select" for multiple domains

3. **Select domain(s)**
   - Check boxes next to domains needing replacement

4. **Choose action**
   - Actions appear at bottom of page when domain selected
   - Select "Replace Domain" or equivalent action

5. **Confirm replacement**
   - Hypertide provisions new domain automatically
   - New inboxes created automatically

### Potential Automation (Future)
- **Hypertide API integration** (if they offer API)
- Automate domain replacement requests
- Auto-sync new domain details after replacement
- Reduce manual steps to just approval/confirmation

---

## Implications for Client Dashboard

### New Metrics to Display

#### Domain Health Score
```typescript
interface DomainHealth {
  domain: string;
  rotation_status: 'healthy' | 'redistributing' | 'pending_replacement' | 'retiring';
  active_inboxes: number;
  dead_inboxes: number;
  death_rate: number;
  can_maintain_volume: boolean;
  recommendation: string;
}
```

#### Rotation Recommendations
**Dashboard Card: "Domain Rotation Status"**
- ✅ Healthy domains: X domains
- ⚠️ Redistributing volume: Y domains (some inbox deaths)
- 🔴 Needs replacement: Z domains (action required)

**Action Items:**
- "3 domains need replacement" (link to Hypertide)
- "Replace via Hypertide Bulk interface" (instructions)

---

## Capacity Planning Adjustments

### Old Model (Inbox-Based)
```
Total Capacity = Active Inboxes × 2 emails/day
```

### New Model (Domain-Based with Redistribution)
```
Per-Domain Capacity:
- Conservative: Active Inboxes × 3 emails/day
- Aggressive: Active Inboxes × 4 emails/day
- Emergency: Active Inboxes × 4 emails/day (short term only)

Total Capacity = Sum of all domain capacities
```

### Reserve Buffer
```
Recommended Reserve = 20-30% above required volume
Reason: Accounts for inbox deaths before domain replacement
```

**Example:**
- Required volume: 1000 emails/day
- Recommended capacity: 1200-1300 emails/day
- Buffer: 200-300 emails/day handles inbox deaths during redistribution phase

---

## Operational Procedures

### Procedure 1: Daily Health Check
**Frequency:** Daily (automated)

**Steps:**
1. Run rotation evaluation on all domains
2. Identify domains needing redistribution
3. Identify domains needing replacement
4. Generate alert/report for domains needing action
5. Update dashboard with rotation status

**Automation:**
```python
# Daily cron job or scheduled task
def daily_rotation_check():
    domains = get_all_active_domains()

    needs_redistribution = []
    needs_replacement = []

    for domain in domains:
        status = evaluate_domain_rotation(domain)

        if status == "redistribute":
            needs_redistribution.append(domain)
            # Auto-update capacity calculations
            redistribute_volume(domain)

        elif status == "replace":
            needs_replacement.append(domain)
            # Alert operations team
            send_replacement_alert(domain)

    # Update dashboard
    update_rotation_dashboard(needs_redistribution, needs_replacement)
```

---

### Procedure 2: Domain Replacement Workflow
**Trigger:** Domain flagged for replacement

**Steps:**
1. **Automated:**
   - System marks domain as "pending_replacement"
   - Generates replacement request with reason/metrics
   - Sends alert to operations team

2. **Manual (Hypertide):**
   - Operator logs into Hypertide
   - Navigates to Bulk page
   - Selects domain(s) for replacement
   - Confirms replacement action
   - Hypertide provisions new domain + inboxes

3. **Automated:**
   - EmailBison sync worker detects new domain
   - Syncs new domain and inbox details
   - Marks old domain as "retired"
   - Begins warmup tracking for new domain
   - Updates capacity calculations

4. **Monitoring:**
   - Track new domain warmup progress
   - Monitor new domain health
   - Confirm old domain fully retired

---

## Risk Mitigation

### Risk 1: Capacity Gap During Replacement
**Risk:** When replacing domain, new domain needs warmup (1-2 weeks). Capacity drops.

**Mitigation:**
- Maintain 20-30% capacity buffer
- Replace domains proactively (before critical)
- Stagger domain replacements (not all at once)
- Consider pre-warming backup domains

---

### Risk 2: Frequent Domain Replacements
**Risk:** High domain churn rate → costs, operational overhead

**Mitigation:**
- Focus on **prevention:** Better list quality, sending practices
- Analyze root causes of domain deaths
- Improve warmup process
- Monitor and optimize kill triggers

---

### Risk 3: Mass Domain Failure
**Risk:** Multiple domains fail simultaneously (e.g., list quality issue affects all)

**Mitigation:**
- Segment risk: Different domains for different campaigns/lists
- Maintain emergency reserve capacity
- Have rapid replacement procedure
- Monitor leading indicators (bounce rates, spam complaints)

---

## Key Metrics to Track

### Domain-Level Metrics
1. **Death Rate:** Dead inboxes / Total inboxes per domain
2. **Rotation Status:** healthy / redistributing / pending_replacement / retiring
3. **Days Since Last Rotation:** Track domain lifespan
4. **Replacement Frequency:** How often domains need swapping

### Fleet-Level Metrics
1. **Domains Needing Replacement:** Count of domains flagged for replacement
2. **Average Domain Lifespan:** Days from provisioning to retirement
3. **Rotation Rate:** Domains replaced per month
4. **Capacity Utilization:** Actual sends / Available capacity

---

## Recommendations

### Immediate Actions (Week 1)
1. ✅ Document rotation policy (this document)
2. ✅ Update capacity calculation formulas (3-4 emails/inbox/day)
3. ✅ Build domain rotation evaluation logic
4. ✅ Add rotation status to dashboard
5. ✅ Create alerting for domains needing replacement

### Short-Term (Month 1)
1. Implement automated rotation checks (daily cron)
2. Build Hypertide replacement workflow documentation
3. Train operations team on domain replacement process
4. Add capacity buffer tracking (20-30% reserve)
5. Monitor rotation patterns and optimize thresholds

### Long-Term (Quarter 1)
1. Explore Hypertide API for automation (if available)
2. Build predictive rotation (anticipate domain failures)
3. Optimize domain lifespan through better practices
4. Consider pre-warming backup domains
5. Analyze cost/benefit of domain rotation frequency

---

## Summary

### Critical Insights
1. **Cannot rotate individual inboxes** — must work at domain level
2. **Domain swaps are Entra-only** — Google domains cannot be swapped; burns are permanent within the order
3. **We supply replacement domains** — Entra swaps require us to source and provide the new domain (BYO)
4. **Three-tier rotation:** Volume redistribution (temporary) → Domain swap/Entra (recoverable) → Order cancellation/Google (last resort)
5. **Safe sending limits:** 3-4 emails per inbox per day
6. **Capacity planning:** Need 20-30% buffer for inbox deaths
7. **Google burns are financial leaks** — $10/mo per burned Google domain with no recovery path

### Strategic Impact
- Rotation is **domain-based**, not inbox-based
- Entra burns are recoverable operational events; Google burns are permanent financial losses
- Need higher capacity reserves to handle inbox deaths, especially on Google infrastructure
- Domain replacement has warmup lag (~21 days)
- Kill trigger tuning should be more conservative for Google domains given irrecoverable burns
- Focus shifts to **domain health**, not individual inbox health

### Next Steps
1. Update rotation logic in codebase
2. Adjust capacity planning models
3. Build domain replacement workflow
4. Update dashboard to show rotation status
5. Document Hypertide replacement procedure for ops team

---

**Document Version:** 2.0
**Last Updated:** 2026-03-19
**Status:** Active Policy
**Related Documents:**
- DASHBOARD-BETA-001 (Implementation Plan)
- RBL-IMPL-001 (RBL Implementation Guide)
