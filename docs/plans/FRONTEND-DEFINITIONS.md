# Frontend Definitions - Charm OS Complete V1

> Critical mapping between UI components and production database/API.
> All definitions must be validated against actual schema before implementation.

---

## Table of Contents

1. [Terminology](#terminology)
2. [Client List View](#client-list-view)
3. [Client Detail - Profile Tab](#client-detail---profile-tab)
4. [Client Detail - Health Tab](#client-detail---health-tab)
5. [Client Detail - Infrastructure Tab](#client-detail---infrastructure-tab)
6. [Critical Gaps & Questions](#critical-gaps--questions)

---

## Terminology

### Domain States

| UI Term | DB Column | Values | Definition |
|---------|-----------|--------|------------|
| Live (A-Set) | `domain_pool_status` | `'live'` | Actively sending, assigned to campaigns |
| Reserve (B-Set) | `domain_pool_status` | `'reserve'` | Warmed, ready to replace burned Live domains |
| Incubating | `domain_pool_status` | `'incubating'` | Warming up (7-21 days from `warmup_started_at`) |
| Burned | `domain_pool_status` | `'burned'` | Retired due to domain-killing trigger |

### Inbox States

| UI Term | DB Columns | Condition | Definition |
|---------|------------|-----------|------------|
| Connected | `inbox_state='live'` AND `status='Connected'` | Both conditions | Actively operational |
| Disconnected | `inbox_state='live'` AND `status='Not connected'` | Lost connection | Needs HyperTide reconnection (manual) |
| Dead | `inbox_state='dead'` | Has kill trigger | Killed, cannot reconnect |

### Domain Source

| UI Term | Determination | Definition |
|---------|---------------|------------|
| LEGACY | `domain_source IS NULL` OR `domain_source = 'legacy'` | Provisioned via HyperTide before platform. Rotation requires manual email. |
| PLATFORM | `domain_source = 'generated'` | Created via Domain Engine V2. Rotation can use automated API. |

**CRITICAL**: Verify `domain_source` column exists in `domains` table. If not, infer from:
- Legacy: `hypertide_order_job_id IS NOT NULL` AND domain purchased before platform launch date
- Platform: Domain exists in `domain_candidates` with `status='purchased'`

### Rotation Recommendation

> **Core Principle**: Inboxes roll up to domains. We rotate ENTIRE DOMAINS, not individual inboxes.
> The decision: Is remaining domain capacity worth keeping vs cost of replacement ($12.50 + 21 days warmup)?

**Rotation Priority Cascade:**

| Priority | Trigger Condition | Recommendation | Action |
|----------|-------------------|----------------|--------|
| P1 | `spam_complaint` on domain | `rotate_now` | Domain reputation burned - immediate rotation |
| P2 | All inboxes disconnected | `rotate_now` | Zero capacity - rotation required |
| P3 | 2+ hard blocks on domain | `consider_rotate` | Pattern forming - likely to escalate |
| P4 | **Capacity < threshold** | `consider_rotate` | See threshold model below |
| P5 | 1 hard block | `monitor` | Early warning - watch closely |
| P6 | Disconnected + clean history | `monitor` | Reconnect opportunity (save the domain) |

**Capacity Threshold Model (from DOMAIN-ENGINE-V2-ECONOMICS.md):**

| Provider | Inboxes/Domain | Rotation Threshold | Rationale |
|----------|----------------|-------------------|-----------|
| Entra | 50 | < 40 connected (80%) | Lose 10+ inboxes = 20+ sends/day lost |
| Google | 3 | < 2 connected (67%) | Lose 1+ inbox = 20+ sends/day lost |

**Economics Decision:**
```
IF remaining_capacity_value < replacement_cost THEN rotate

Where:
- remaining_capacity_value = connected_inboxes × sends_per_day × remaining_lifespan_days
- replacement_cost = avg_domain_cost + capacity_lost_during_21d_warmup
- avg_domain_cost = AVG(best_price) from domain_candidates WHERE status='purchased'
```

| UI Term | DB Column | Value | Description |
|---------|-----------|-------|-------------|
| Rotate Now | `rotation_recommendation` | `'rotate_now'` | P1-P2: Domain burned or zero capacity |
| Consider Rotate | `rotation_recommendation` | `'consider_rotate'` | P3-P4: Threshold breach or pattern forming |
| Watch | `rotation_recommendation` | `'monitor'` | P5-P6: Early warning or reconnect candidate |
| Healthy | `rotation_recommendation` | `'healthy'` | Above capacity threshold, no issues |

### Kill Triggers

**Domain Burns (DOMAIN_KILLING_TRIGGERS is now empty):**
```python
DOMAIN_KILLING_TRIGGERS = set()  # Empty — provider_block_* removed (misclassified recipient rejections)
```

**Conditional Domain Burns (burns only with 2+ cross-inbox pattern):**
```python
CONDITIONAL_DOMAIN_TRIGGERS = {
    'spam_complaint',  # 1 inbox = inbox kill ($0); 2+ inboxes = domain burn ($12.50)
}
```

**Inbox-Killing (free, domain preserved):**
```python
INBOX_KILLING_TRIGGERS = {
    'hard_bounces_24h',
    'hard_blocked_24h',
    'hard_unknown_24h',
    'hard_bounce_rate_7d',
    'bounce_rate_all_7d',
    'disconnected_timeout',
}
```

---

## Client List View

### Data Source
- **Table**: `clients` LEFT JOIN `workspaces` ON `clients.workspace_id = workspaces.id`
- **Aggregations**: Subqueries on `domains` and `sender_accounts`

### Fields Mapping

| UI Field | Source | Calculation |
|----------|--------|-------------|
| Client Name | `clients.name` | Direct |
| Workspace Slug | `workspaces.name` | Direct |
| Avatar Initial | `clients.name[0]` | First character |
| Avatar Color | Derived | Hash of client name → gradient |
| Domain Count | `COUNT(domains)` | WHERE `workspace_id` matches AND `is_active = true` |
| Inbox Count | `COUNT(sender_accounts)` | WHERE `workspace_id` matches |
| Health % | Calculated | `connected_inbox_count / live_inbox_count * 100` |
| Package Name | `package_templates.name` | Via `client_subscriptions.package_template_id` |
| Status Badge | Derived | See logic below |

### Status Badge Logic

```python
def get_client_status(client):
    if not client.sync_enabled:  # workspace.is_active = false
        return "Inactive"

    if client.rotate_now_count > 0:
        return "Attention"

    return "Active"
```

### API Endpoint
```
GET /api/clients
Response: ClientList { items: Client[], total: int }
```

---

## Client Detail - Profile Tab

### Basic Information Card

| UI Field | DB Column | Table | Editable |
|----------|-----------|-------|----------|
| Company Name | `name` | `clients` | Yes |
| Contact Name | `contact_name` | `clients` | Yes |
| Contact Email | `contact_email` | `clients` | Yes |
| Website | `website` | `clients` | Yes |
| Industry | `industry` | `clients` | Yes (dropdown from INDUSTRIES list) |
| Domain Pattern | `domain_pattern` | `clients` | Yes |

### Sender Names Card

| UI Field | Source | Notes |
|----------|--------|-------|
| Base Name | `onboarding_data.base_sender_names[0]` | JSONB field |
| Variations | `onboarding_data.pre_generated_sender_names` | Array of {firstName, lastName, emailPrefix} |
| Count | Derived | 52 for Entra, 10 for Google |

### Package Card

| UI Field | Source | Calculation |
|----------|--------|-------------|
| Package Name | `package_templates.name` | Via subscription |
| Domains Used | `current_active_domains` | From `v_subscription_usage` |
| Domains Total | `total_domains` | `client_subscriptions` |
| Domains Remaining | Calculated | `total - used` |
| Inboxes Used | `current_active_inboxes` | From `v_subscription_usage` |
| Inboxes Total | `total_inboxes` | `client_subscriptions` |
| Entra Allocation | `entra_packages * entra_domains_per_package` | From subscription |
| Google Allocation | `google_packages * google_domains_per_package` | From subscription |

### Sync Toggle

| UI State | DB Update | Effect |
|----------|-----------|--------|
| Enabled (green) | `workspaces.is_active = true` | Workspace included in EmailBison sync |
| Disabled (gray) | `workspaces.is_active = false` | Workspace excluded from sync |

### API Endpoints
```
GET /api/clients/{id}
PUT /api/clients/{id}  # Updates profile fields
GET /api/subscriptions/client/{id}  # Package info
PUT /api/subscriptions/client/{id}  # Update package
```

---

## Client Detail - Health Tab

### Summary Stats Row

| Metric | Calculation | Source |
|--------|-------------|--------|
| Overall Health | `connected_count / (connected_count + disconnected_count) * 100` | sender_accounts |
| Daily Capacity | Sum of domain capacities | See capacity formula |
| Connected | `COUNT WHERE inbox_state='live' AND status='Connected'` | sender_accounts |
| Disconnected | `COUNT WHERE inbox_state='live' AND status='Not connected'` | sender_accounts |
| Dead | `COUNT WHERE inbox_state='dead'` | sender_accounts |

### Sending Capacity by Provider (Donut Chart)

**Capacity Formula:** ✅ CONFIRMED
```python
# Source: api/routes/health.py:3440
def calculate_daily_capacity(domain):
    if domain.provider in ('microsoft', 'entra'):
        return domain.live_connected_inbox_count * 2  # 2 sends/day
    elif domain.provider == 'google':
        return domain.live_connected_inbox_count * 20  # 20 sends/day
```

**Note:** Values are fixed, do not vary by warmup age.

| Provider | Domains | Inboxes/Domain | Sends/Day | Total Capacity |
|----------|---------|----------------|-----------|----------------|
| Entra | 24 | 50 | 2 | 2,400 |
| Google | 8 | 3 | 20 | 480 |

### Kill Triggers Pie Chart

**Data Source:**
```sql
SELECT
    kill_trigger,
    COUNT(*) as count
FROM sender_accounts
WHERE workspace_id = $1
  AND killed_at >= NOW() - INTERVAL '30 days'
  AND kill_trigger IS NOT NULL
GROUP BY kill_trigger
ORDER BY count DESC;
```

**Economic Impact (from DELIVERABILITY-ECONOMICS.md):**

| Trigger Type | % of Kills | Cost Impact |
|--------------|------------|-------------|
| `hard_blocked_24h` | ~40% | $0 (B-Set promotes) |
| `hard_unknown_24h` | ~25% | $0 (B-Set promotes) |
| `spam_complaint` | ~19% | Conditional domain rotation |
| `hard_bounces_24h` | ~16% | $0 (B-Set promotes) |

**UI Display:**
```
Kill Triggers (Last 30 Days)
┌────────────────────────────────────┐
│  ██████████░░░░  40% hard_blocked   │
│  ██████░░░░░░░░  25% hard_unknown  │
│  ████░░░░░░░░░░  19% spam_complaint│
│  ███░░░░░░░░░░░  16% hard_bounces  │
├────────────────────────────────────┤
│ Domain-killing: 12 ($150 rotation) │
│ Inbox-killing: 51 ($0, B-Set)      │
└────────────────────────────────────┘
```

**Cost Calculation:**
```python
avg_domain_cost = get_rotation_cost_estimate(client_id)  # Dynamic from purchases
domain_kills = sum(1 for t in triggers if t in CONDITIONAL_DOMAIN_TRIGGERS)  # Only spam_complaint with 2+ cross-inbox
rotation_cost = domain_kills * avg_domain_cost
```

### Domain Health Bar Chart

**Data Source:**
```sql
SELECT
    rotation_recommendation,
    COUNT(*) as count
FROM v_infrastructure_waterfall
WHERE workspace_id = $1
  AND domain_pool_status = 'live'
GROUP BY rotation_recommendation;
```

| Category | rotation_recommendation values |
|----------|-------------------------------|
| Healthy | `'healthy'` |
| Watch | `'monitor'`, `'consider_rotate'` |
| Rotate Now | `'rotate_now'` |

### Inbox Status Bar Chart

**Data Source:**
```sql
SELECT
    CASE
        WHEN inbox_state = 'dead' THEN 'dead'
        WHEN status = 'Connected' THEN 'connected'
        ELSE 'disconnected'
    END as status_category,
    COUNT(*) as count
FROM sender_accounts
WHERE workspace_id = $1
GROUP BY status_category;
```

### Reserve & Runway ✅ CONFIRMED

**Reserve Count:**
```sql
SELECT
    detected_provider,
    COUNT(*) as reserve_count
FROM v_infrastructure_waterfall
WHERE workspace_id = $1
  AND domain_pool_status = 'reserve'
GROUP BY detected_provider;
```

**Runway Calculation (from DELIVERABILITY-ECONOMICS.md):**
```python
def calculate_runway_months(reserve_count, total_inboxes, kill_rate, esp):
    """
    Runway = Reserve domains / Monthly domain burn rate

    Monthly burn rate formula:
    monthly_inbox_kills = total_inboxes × (kill_rate / 3)
    domain_kills = monthly_inbox_kills × domain_kill_percentage
    """
    # Domain kill percentages (from production data)
    DOMAIN_KILL_PCT = {
        'microsoft': 0.30,  # 30% of Entra inbox kills cascade to domain
        'google': 0.07,     # 7% of Google inbox kills cascade to domain
    }

    # Default kill rate if no historical data
    DEFAULT_KILL_RATE = {
        'microsoft': 0.234,  # 23.4% inbox kill rate
        'google': 0.402,     # 40.2% inbox kill rate
    }

    effective_kill_rate = kill_rate or DEFAULT_KILL_RATE.get(esp, 0.30)
    monthly_inbox_kills = total_inboxes * (effective_kill_rate / 3)
    monthly_domain_kills = monthly_inbox_kills * DOMAIN_KILL_PCT.get(esp, 0.20)

    if monthly_domain_kills == 0:
        return float('inf')  # "No burns"

    return reserve_count / monthly_domain_kills
```

**Display Format:**
- `< 1 month`: "Critical" (red)
- `1-2 months`: "Low" (orange)
- `3-6 months`: "Healthy" (green)
- `> 6 months`: "Excellent" (green)

### Action Items

Links to Infrastructure tab sections:
- "2 Domains Need Rotation" → Operations tab, Rotate Now section
- "47 Disconnected Inboxes" → Disconnected tab
- "6 Domains Ready to Purchase" → Pipeline tab, Recommended section

---

## Economic Forecasting Model

> Source: `DELIVERABILITY-ECONOMICS.md`, `DELIVERABILITY-ECONOMICS-INSIGHTS.md`, and `DOMAIN-ENGINE-V2-ECONOMICS.md`

### Domain-Centric Capacity Management

**Core Principle**: The atomic unit of management is the DOMAIN, not the inbox.

```
DOMAIN (unit of rotation)
   │
   ├── Inbox 1 ─── Connected (contributing capacity)
   ├── Inbox 2 ─── Connected (contributing capacity)
   ├── Inbox 3 ─── Disconnected (zero capacity)
   ├── ...
   └── Inbox 50 ─── Dead (killed, zero capacity)
   │
   └── Domain Capacity = SUM(connected_inboxes × sends_per_day)
```

**Why Domain-Level:**
1. Spam complaints burn the DOMAIN reputation (not just one inbox)
2. Provider blocks affect ALL inboxes on the domain
3. Rotation cost is per-domain ($12.50), not per-inbox
4. Reserve pools are domain-level (can't substitute individual inboxes)

**The Rotation Decision:**
```
When domain capacity drops below threshold:
  Entra:  < 40/50 connected (80%) → consider rotation
  Google: < 2/3 connected (67%)   → consider rotation

Cost-benefit analysis:
  Keep degraded domain: X sends/day for remaining lifespan
  Rotate to fresh domain: avg_purchase_price + 21 days warmup, then full capacity

Decision: Rotate when salvage value < replacement cost
         (replacement cost = AVG(best_price) from actual purchases)
```

### Package Templates

| Package | Entra Orders | Google Orders | Total Domains | Total Inboxes | Daily Capacity |
|---------|--------------|---------------|---------------|---------------|----------------|
| Starter | 6 | 5 | 37 | 699 | 2,748 |
| Growth | 12 | 10 | 74 | 1,398 | 5,496 |

### Capacity Formula (CONFIRMED)

```python
# Source: DELIVERABILITY-ECONOMICS-INSIGHTS.md
CAPACITY_PER_DAY = {
    'microsoft': 2,   # 2 emails/inbox/day (Entra)
    'google': 20,     # 20 emails/inbox/day
}

INBOXES_PER_DOMAIN = {
    'microsoft': 52,  # 50-52 per Entra domain
    'google': 3,      # 3 per Google domain
}

def calculate_domain_capacity(esp, connected_inbox_count):
    return connected_inbox_count * CAPACITY_PER_DAY.get(esp, 2)

def calculate_total_capacity(domains):
    return sum(calculate_domain_capacity(d.esp, d.connected_inboxes) for d in domains)
```

### Kill Rate Economics

| Trigger Type | % of All Kills | Domain Impact | Cost |
|--------------|----------------|---------------|------|
| `hard_blocked_24h` | ~40% | Inbox only | $0 (Reserve promotes) |
| `hard_unknown_24h` | ~25% | Inbox only | $0 (Reserve promotes) |
| `spam_complaint` | ~19% | **Conditional domain burn** | ~$X.XX rotation (avg from purchases, only at 2+ cross-inbox) |
| `hard_bounces_24h` | ~16% | Inbox only | $0 (Reserve promotes) |

**Note:** Rotation cost is dynamic based on `AVG(best_price)` from purchased domains, not a fixed value.

### Capacity Degradation Formula (Domain-Level)

**Domain capacity degrades as inboxes die, then domain rotates when threshold breached:**

```python
def calculate_domain_capacity(domain):
    """
    Capacity is sum of connected inboxes × sends per inbox.
    When capacity drops below threshold, flag for rotation.
    """
    SENDS_PER_INBOX = {'microsoft': 2, 'google': 20}
    ROTATION_THRESHOLD = {'microsoft': 0.80, 'google': 0.67}  # 80%, 67%

    capacity = domain.connected_inboxes * SENDS_PER_INBOX[domain.esp]
    max_capacity = domain.expected_inboxes * SENDS_PER_INBOX[domain.esp]
    capacity_pct = capacity / max_capacity

    if capacity_pct < ROTATION_THRESHOLD[domain.esp]:
        return {'status': 'rotate', 'capacity': capacity}
    return {'status': 'healthy', 'capacity': capacity}


def project_portfolio_capacity(domains, kill_rate, months):
    """
    Portfolio capacity = SUM(domain capacities)
    Domain rotation replaces degraded domain with fresh domain (21 day warmup).

    month_n_capacity = current - kills + graduations
    """
    RECOVERY_RATE = 0.70  # Reserve recovers 70% of inbox-level kills

    for month in range(1, months + 1):
        # Inbox-level kills (free recovery via Reserve inbox)
        inbox_kills = sum(d.connected_inboxes for d in domains) * (kill_rate * 0.81 / 3)
        recovered = inbox_kills * RECOVERY_RATE

        # Domain-level kills (requires $12.50 rotation)
        domain_kills = len(domains) * (kill_rate * 0.19 / 3)  # 19% are domain-killing

        # Net capacity change (use actual avg cost, not hardcoded)
        avg_domain_cost = get_rotation_cost_estimate(client_id)
        yield {
            'month': month,
            'inbox_kills': inbox_kills,
            'domain_rotations': domain_kills,
            'rotation_cost': domain_kills * avg_domain_cost,
            'avg_domain_cost': avg_domain_cost,
        }
```

### List Quality Scenarios

| Scenario | Inbox Kill Rate | Domain Kill Rate | 3-Month Capacity |
|----------|-----------------|------------------|------------------|
| Excellent | 10-15% | 2-5% | 85% |
| Good | 20-30% | 5-10% | 72% |
| Poor | 40-50% | 15-25% | 40% |
| Bad | 60-80% | 25-40% | 24% |

### Monthly Cost Projection

```python
def project_monthly_cost(package, kill_rate, client_id, domain_kill_pct=0.20):
    """
    rotation_cost = domain_kills × avg_domain_cost (from actual purchases)
    """
    # Get actual average from purchase history
    avg_domain_cost = get_rotation_cost_estimate(client_id)  # Dynamic, not hardcoded

    SUBSCRIPTION = {
        'starter': 550,
        'growth': 1100,
    }

    monthly_inbox_kills = package.total_inboxes * (kill_rate / 3)
    monthly_domain_kills = monthly_inbox_kills * domain_kill_pct
    rotation_cost = monthly_domain_kills * avg_domain_cost

    return {
        'subscription': SUBSCRIPTION[package.name],
        'rotation_cost': rotation_cost,
        'avg_domain_cost': avg_domain_cost,  # Show the actual average used
        'projected_rotations': monthly_domain_kills,
        'total': SUBSCRIPTION[package.name] + rotation_cost,
    }
```

**UI Display:**
```
Monthly Cost Projection
├── Subscription: $550/mo
├── Rotation budget: ~$45/mo
│   └── Based on: 4 domains × $11.23 avg
└── Total: ~$595/mo
```

### Reserve Pool Management (Provider-Specific)

**Critical**: Reserve domains MUST match provider type. Cannot substitute Google for Entra.

```
Reserve Pool Status:
├── Entra:  2 domains ⚠️ LOW (need 3 rotations pending)
│   └── Capacity: 100 inboxes, 200 sends/day ready
├── Google: 4 domains ✓ ADEQUATE
│   └── Capacity: 12 inboxes, 240 sends/day ready
└── Total Reserve: 6 domains

Incubating Pipeline:
├── Entra:  5 domains → 2 graduating in 7d, 3 in 21d
├── Google: 8 domains → 3 graduating in 4d, 5 in 12d
└── Projected capacity gain: +560 sends/day in 21 days
```

**Reserve Adequacy Thresholds:**

| Status | Runway | UI Display | Action |
|--------|--------|------------|--------|
| Adequate | > 3 months | Green | No action |
| Low | 1-3 months | Yellow | Consider ordering more domains |
| Critical | < 1 month | Red | Order domains immediately |
| Exhausted | 0 reserve | Red flashing | URGENT: No backup available |
| Mismatch | Need Entra, only Google | Red | Wrong provider type available |

### Runway Forecast Widget

**Display in Health Tab:**

```
┌─────────────────────────────────────────────┐
│ 📊 Infrastructure Runway (by Provider)      │
├─────────────────────────────────────────────┤
│ Entra    ████████░░░░  4.2 months          │
│          Reserve: 2 domains | Pending: 3    │
│          ⚠️ Need 1 more Entra domain        │
│                                             │
│ Google   ██████████░░  8.1 months          │
│          Reserve: 4 domains | Pending: 0    │
│          ✓ Adequate                         │
├─────────────────────────────────────────────┤
│ Based on 30-day domain burn rate:           │
│   • Entra: 1.2 domains/month                │
│   • Google: 0.3 domains/month               │
│                                             │
│ Incubating (graduating soon):               │
│   • Entra: +2 in 7d, +3 in 21d              │
│   • Google: +3 in 4d, +5 in 12d             │
└─────────────────────────────────────────────┘
```

### Capacity Threshold Alert

**When to show "Order More Infrastructure" prompt:**

```python
def needs_more_infrastructure(workspace):
    """
    Alert when:
    - Runway < 2 months for either ESP
    - Reserve count < 2 domains for either ESP
    - Capacity < 80% of subscription allocation
    """
    entra_runway = calculate_runway(workspace, 'microsoft')
    google_runway = calculate_runway(workspace, 'google')

    alerts = []

    if entra_runway < 2:
        alerts.append(f"Entra runway critical: {entra_runway:.1f} months")

    if google_runway < 2:
        alerts.append(f"Google runway critical: {google_runway:.1f} months")

    if workspace.entra_reserve_count < 2:
        alerts.append("Entra reserve low: order more domains")

    if workspace.google_reserve_count < 2:
        alerts.append("Google reserve low: order more domains")

    current_capacity = calculate_total_capacity(workspace.live_domains)
    target_capacity = workspace.subscription.daily_capacity_target

    if current_capacity / target_capacity < 0.80:
        alerts.append(f"Capacity at {current_capacity/target_capacity*100:.0f}% of target")

    return alerts
```

### Key Performance Metrics

**Health Tab KPIs (from economic model):**

| Metric | Formula | Good | Warning | Critical |
|--------|---------|------|---------|----------|
| Cost per 1K Delivered | `total_cost / (delivered_emails / 1000)` | <$20 | $20-50 | >$50 |
| Capacity Utilization | `current_capacity / subscription_target` | >80% | 60-80% | <60% |
| Weekly Kill Rate | `inbox_kills_7d / total_inboxes` | <2% | 2-5% | >5% |
| Domain Kill Rate | `domain_kills_30d / total_domains` | <5% | 5-15% | >15% |
| B-Set Coverage | `reserve_inboxes / live_inboxes` | >20% | 10-20% | <10% |

### 12-Week Lifecycle Phases

**Display in timeline visualization:**

| Phase | Weeks | Status | Risk Level | Key Metric |
|-------|-------|--------|------------|------------|
| Warmup | 1-3 | Incubating | None | 0% sending |
| Danger Zone | 4-5 | Post-graduation | **CRITICAL** | 99.9% of kills |
| Stabilization | 5-8 | Kill rate declining | Moderate | Execute rotations |
| Optimized | 9-12 | Steady state | Low | Final capacity |

**Visual indicator:**
```
Week 1  ░░░░░░░░░░ Warmup
Week 2  ░░░░░░░░░░ Warmup
Week 3  ░░░░░░░░░░ Warmup
Week 4  ██████████ DANGER ZONE - Monitor daily
Week 5  ██████████ DANGER ZONE - Expect kills
Week 5  ████████░░ Stabilizing
Week 6  ███████░░░ Stabilizing
Week 7  ██████░░░░ Declining
Week 8  █████░░░░░ Declining
Week 9  ████░░░░░░ Steady state
Week 10 ███░░░░░░░ Steady state
Week 11 ███░░░░░░░ Optimized
Week 12 ███░░░░░░░ Optimized
```

---

## Client Detail - Infrastructure Tab

### Capacity Summary Cards

Same calculation as Health tab, but split by provider.

| Provider | Field | Source |
|----------|-------|--------|
| Entra | Daily Capacity | `live_connected_count * 2` |
| Entra | Live Domains | `domain_pool_status = 'live'` |
| Entra | Watch | `rotation_recommendation IN ('monitor', 'consider_rotate')` |
| Entra | Rotate Now | `rotation_recommendation = 'rotate_now'` |
| Entra | Reserve | `domain_pool_status = 'reserve'` |
| Entra | Incubating | `domain_pool_status = 'incubating'` |
| Entra | Runway | `reserve_count / monthly_burn_rate` |

### Operations Sub-tab

**Data Source:**
```sql
SELECT * FROM v_infrastructure_waterfall
WHERE workspace_id = $1
  AND domain_pool_status = 'live'
ORDER BY
    CASE rotation_recommendation
        WHEN 'rotate_now' THEN 1
        WHEN 'consider_rotate' THEN 2
        WHEN 'monitor' THEN 3
        ELSE 4
    END,
    domain_name;
```

**Table Columns:**

| Column | Source | Notes |
|--------|--------|-------|
| Checkbox | UI state | For bulk selection |
| Domain | `domain_name` | With LEGACY/PLATFORM badge |
| Provider | `detected_provider` | Entra or Google badge |
| Inboxes | `connected_inbox_count / expected_inbox_count` | X/Y format |
| Issues | `burn_breakdown` | IssueChips component |
| Days | Days since issue | From `killed_at` or disconnect date |
| Action | Based on state | Rotate, Reconnect, or Monitor button |

**Action Button Logic (Domain-Level):**
```python
def get_action_button(domain):
    """
    Actions are at DOMAIN level, not inbox level.
    We rotate/salvage entire domains based on economic threshold.
    """
    # P1-P2: Immediate rotation triggers
    if domain.rotation_recommendation == 'rotate_now':
        if domain.has_spam_complaint:
            return "Rotate Domain"  # $12.50 - domain reputation burned
        elif domain.all_disconnected:
            if domain.clean_history:
                return "Reconnect All"  # $0 - domain salvageable
            else:
                return "Rotate Domain"  # $12.50 - had issues before disconnect

    # P3-P4: Threshold breach
    elif domain.rotation_recommendation == 'consider_rotate':
        capacity_pct = domain.connected_inboxes / domain.expected_inboxes
        if domain.esp == 'microsoft' and capacity_pct < 0.80:
            return "Rotate Domain"  # Below 80% Entra threshold
        elif domain.esp == 'google' and capacity_pct < 0.67:
            return "Rotate Domain"  # Below 67% Google threshold
        else:
            return "Monitor"  # Pattern forming but above threshold

    # P5-P6: Early warning / reconnect opportunity
    elif domain.rotation_recommendation == 'monitor':
        if domain.disconnected_count > 0 and domain.clean_history:
            return "Reconnect"  # Save the domain
        return "Monitor"

    return "Healthy"  # No action needed
```

**Key Insight**: The "Rotate Domain" action replaces THE ENTIRE DOMAIN with a Reserve domain, not individual inboxes. Cost is $12.50 regardless of how many inboxes were on the domain.

### Pipeline Sub-tab

**Data Source:**
```sql
SELECT * FROM domain_candidates
WHERE client_id = $1
  AND status IN ('scored', 'priced', 'recommended')
ORDER BY
    CASE status
        WHEN 'recommended' THEN 1
        WHEN 'priced' THEN 2
        WHEN 'scored' THEN 3
    END,
    composite_score DESC;
```

**Table Columns:**

| Column | Source | Notes |
|--------|--------|-------|
| Checkbox | UI state | For bulk purchase |
| Domain | `domain_name` | |
| Score | `composite_score` | 0.00-1.00 with progress bar |
| Breakdown | `brand_fit_score`, `tld_score`, `safety_score`, `length_score` | Mini bars: B/T/S/L |
| Dynadot | `dynadot_price` | With availability |
| Porkbun | `porkbun_price` | With availability |
| Best | `best_price` | Highlighted with registrar |

**Score Weights:**
- Brand Fit: 35%
- TLD: 30%
- Safety: 20%
- Length: 15%

**Purchase Flow:**
1. Select domains (checkbox)
2. Click "Purchase Selected ($X.XX)"
3. Creates job in `hypertide_jobs` table
4. `hypertide_worker.py` processes:
   - Checks FRESH prices from both registrars
   - Purchases from cheapest
   - Updates `domains` table with `purchased_at`, `purchase_price`, `purchase_registrar`

### Purchased Sub-tab

**Data Source:**
```sql
SELECT * FROM v_infrastructure_waterfall
WHERE workspace_id = $1
  AND is_purchased = true
  AND hypertide_status = 'not_ordered'
ORDER BY purchased_at DESC;
```

**Table Columns:**

| Column | Source | Notes |
|--------|--------|-------|
| Checkbox | UI state | For HyperTide order |
| Domain | `domain_name` | |
| Purchased | `purchased_at` | Date + registrar |
| Price | `purchase_price` | |
| DNS | `dns_status` | Ready, Propagating, or Failed |
| Provider | Dropdown | Entra (50) or Google (3) |

**HyperTide Order Flow:**
1. Select domains with DNS Ready
2. Choose provider for each
3. Click "Order HyperTide (X domains)"
4. Creates order in `hypertide_orders` table
5. `hypertide_worker.py` submits to HyperTide API

### Disconnected Sub-tab

**CRITICAL BUSINESS RULE:**
> Only request reconnection for inboxes with **clean history** (no kill triggers).
> Inboxes with kill triggers are DEAD and should NOT be reconnected.
> Reconnection is ALWAYS a manual action (email to HyperTide).

**Data Source - Safe to Reconnect:**
```sql
SELECT email, domain_name
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.workspace_id = $1
  AND sa.inbox_state = 'live'
  AND sa.status = 'Not connected'
  AND sa.kill_trigger IS NULL  -- Clean history
ORDER BY d.domain_name, sa.email;
```

**Data Source - Killed (Do Not Reconnect):**
```sql
SELECT email, domain_name, kill_trigger, killed_at
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.workspace_id = $1
  AND sa.inbox_state = 'live'
  AND sa.status = 'Not connected'
  AND sa.kill_trigger IS NOT NULL  -- Has kill trigger
ORDER BY d.domain_name, sa.email;
```

**Email Template Generation:**
```
To: support@hypertide.com
Subject: Reconnection Request - {client_name} ({clean_count} inboxes)

Hi HyperTide Team,

We noticed the following inboxes are showing as disconnected.
Could you please reconnect them at your earliest convenience?

Workspace: {workspace_name}
Total Inboxes: {clean_count}

---

{domain_name} ({count} inboxes)
{email_list}

---

Thanks,
{client_name} Team
```

### Incubating Sub-tab

**Data Source:**
```sql
SELECT
    domain_name,
    detected_provider,
    live_inbox_count,
    warmup_started_at,
    EXTRACT(DAY FROM NOW() - warmup_started_at) as days_warming,
    domain_pool_status
FROM v_infrastructure_waterfall
WHERE workspace_id = $1
  AND domain_pool_status = 'incubating'
ORDER BY warmup_started_at;
```

**Progress Calculation:**
```python
WARMUP_DAYS = 21  # Full warmup period
progress_pct = min(100, (days_warming / WARMUP_DAYS) * 100)
```

**Target Pool Assignment:**
- Based on 80/20 allocation rule
- 80% of capacity should be Live (A-Set)
- 20% of capacity should be Reserve (B-Set)

### Reserve Sub-tab

**Data Source:**
```sql
SELECT
    domain_name,
    detected_provider,
    live_inbox_count as inbox_count,
    warmup_completed_at as ready_since,
    EXTRACT(DAY FROM NOW() - warmup_completed_at) as days_ready
FROM v_infrastructure_waterfall
WHERE workspace_id = $1
  AND domain_pool_status = 'reserve'
ORDER BY detected_provider, warmup_completed_at;
```

**Pending Rotations Section:**
- Shows domains in "rotate_now" status
- Maps each to a reserve domain that will replace it
- "Draft Rotation Request Email" for Legacy domains

---

## Critical Gaps & Questions

### 1. Domain Source Column ✅ CONFIRMED
**Status:** Column exists with values:
- `'legacy'` - Pre-platform HyperTide provisioned
- `'purchased'` - Bought via Domain Engine V2 (Dynadot/Porkbun)
- `'generated'` - Created by domain candidate generator

**Source:** `api/routes/infrastructure.py` WaterfallDomainResponse

### 2. Sends Per Day Values ✅ CONFIRMED
**Status:** Values are correct, defined in `api/routes/health.py:3440`:
```python
CASE WHEN esp = 'microsoft' THEN dead * 2 ELSE dead * 20 END as daily_capacity_lost
```
- **Entra (Microsoft): 2 sends/inbox/day**
- **Google: 20 sends/inbox/day**

**Domain-level capacity** (`health.py:3404-3407`):
- Microsoft: 100/domain/day (50 inboxes × 2)
- Google: 60/domain/day (3 inboxes × 20)

### 3. Domain Rotation Cost ✅ CONFIRMED (Dynamic)
**Status:** Cost is calculated from **actual purchase prices**, not a fixed value.

**Data Source:**
```sql
-- Average cost from purchased domains
SELECT AVG(best_price) as avg_domain_cost
FROM domain_candidates
WHERE status = 'purchased'
  AND best_price IS NOT NULL;

-- Or from domains table with cached_price
SELECT AVG(cached_price) as avg_domain_cost
FROM domains
WHERE cached_price IS NOT NULL
  AND purchased_at IS NOT NULL;
```

**Cost Fields:**
| Field | Table | Description |
|-------|-------|-------------|
| `best_price` | `domain_candidates` | Cheapest of Dynadot/Porkbun at purchase time |
| `dynadot_price` | `domain_candidates` | Dynadot quoted price |
| `porkbun_price` | `domain_candidates` | Porkbun quoted price |
| `cached_price` | `domains` | Last known purchase price |

**Implementation:**
```python
def get_rotation_cost_estimate(client_id=None):
    """
    Calculate average domain cost from actual purchases.
    Falls back to $12.50 if no purchase history.
    """
    if client_id:
        # Client-specific average
        avg = query("""
            SELECT AVG(dc.best_price)
            FROM domain_candidates dc
            WHERE dc.client_id = $1
              AND dc.status = 'purchased'
              AND dc.best_price IS NOT NULL
        """, client_id)
    else:
        # Global average
        avg = query("""
            SELECT AVG(best_price)
            FROM domain_candidates
            WHERE status = 'purchased'
              AND best_price IS NOT NULL
        """)

    return avg or 12.50  # Fallback if no data
```

**Typical Range:** $8-18 depending on TLD
- `.com`: $10-12
- `.co`: $8-10
- `.io`: $35-50 (avoid for rotation)

**UI Display:**
- Show actual average: "Avg. rotation cost: $11.23 (based on 47 purchases)"
- Use this for cost projections, not hardcoded $12.50

### 4. Monthly Burn Rate Calculation ✅ CONFIRMED
**Formula (from DELIVERABILITY-ECONOMICS.md):**
```python
monthly_inbox_kills = total_inboxes × (kill_rate / 3)
domain_kills = monthly_inbox_kills × domain_kill_percentage

# Domain kill percentages (from production):
# - Entra: 30% of inbox kills cascade to domain
# - Google: 7% of inbox kills cascade to domain
```

**Implementation:**
- **Option A (Historical):** Count domain-killing triggers in last 30 days
- **Option B (Projected):** Use formula above with current inbox count and historical kill rate
- **Recommended:** Use historical if >30 days of data, otherwise use projected

### 5. Warmup Period ✅ CONFIRMED
**Status:** 21 days is standard

**Source:** `sync_modules/lifecycle_tag_sync.py:5`:
```python
# 'incubating' - Inbox in warmup period (< 21 days from warmup_started_at)
```

### 6. 80/20 Allocation Rule ⚠️ NEEDS IMPLEMENTATION
**Status:** Migration exists (`migrations/078_domain_allocation_80_20.sql`) but logic needs review.
- 80% of capacity → Live (A-Set)
- 20% of capacity → Reserve (B-Set)
- Assignment happens when domain completes warmup (21 days)

### 7. HyperTide API for Platform Domains ⚠️ NEEDS CLARIFICATION
**Question:** Do we have API access for automated rotation?
- `hypertide_api/models.py` exists but needs review for rotation endpoints
- If no API: All rotations require manual email to HyperTide

### 8. Disconnect vs Kill Trigger ✅ CONFIRMED
**Status:** `disconnected_timeout` trigger fires after 21 days.

**Source:** `sync_modules/health_checks.py`:
```python
KILL_THRESHOLD_DISCONNECTED_DAYS = 21
```

**Flow:**
1. Inbox disconnects (status='Not connected')
2. 21 days pass with no reconnection
3. Kill processor fires `disconnected_timeout` trigger
4. Inbox state changes to 'dead'

### 9. Sync Toggle Effect ✅ UNDERSTOOD
**Status:** Maps to `workspaces.is_active`:
- EmailBison sync worker skips workspace
- Kill processor skips workspace
- Health checks skip workspace
- Existing campaigns continue (no inbox allocation changes)

### 10. Package Template Updates ⚠️ NEEDS CLARIFICATION
**Question:** When a package is changed:
- Does it affect existing domains/inboxes? (Likely no)
- Is it just a quota change? (Likely yes)
- Does it trigger any provisioning? (Likely no)

---

## API Endpoints Summary

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/clients` | GET | List all clients |
| `/api/clients/{id}` | GET | Get client detail |
| `/api/clients/{id}` | PUT | Update client profile |
| `/api/subscriptions/client/{id}` | GET | Get client subscription |
| `/api/subscriptions/client/{id}` | PUT | Update subscription |
| `/api/infrastructure/waterfall` | GET | Domain waterfall data |
| `/api/infrastructure/bulk-purchase` | POST | Purchase domains |
| `/api/infrastructure/hypertide-order` | POST | Order HyperTide provisioning |
| `/api/domain-candidates` | GET | Pipeline candidates |
| `/api/domain-candidates/generate` | POST | Generate new candidates |

---

## Next Steps

1. **Validate schema** - Run queries against production to confirm column names
2. **Confirm business rules** - Get answers to critical questions
3. **Map existing components** - Identify which React components can be reused
4. **Identify API gaps** - Any new endpoints needed?
5. **Create migration plan** - How to transition from current UI
