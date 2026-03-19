---
title: Kill Triggers
created: 2026-02-12
updated: 2026-03-19
tags: [concept, health, kill-triggers, infrastructure]
---

# Kill Triggers

Automated inbox termination system that protects domain reputation by detecting and removing problematic inboxes.

## Overview

Kill triggers are thresholds that, when breached, automatically queue an inbox for deletion. The system follows the v3 spec philosophy: **protect domains over inboxes** - inboxes are disposable, domains are not.

## Core Philosophy

1. **Kill fast, swap fast, diagnose after** - Don't investigate while reputation degrades
2. **100% backup capacity** - Always have warmed backups ready
3. **1 spam complaint = inbox death** - The inbox is always killed immediately. The *domain* burn decision is rate-based: complaint rate evaluated against thresholds (<0.3% safe, 0.3-1.0% monitoring, >1.0% burn).
4. **Differentiated thresholds** - Spam blocks are worse than bad addresses
5. **Proportional domain response** - Domain complaint rate determines action, not raw inbox count. A 3-inbox Gmail domain and a 50-inbox Microsoft domain are evaluated by the same rate thresholds.

## Kill Trigger Types

### Inbox Kill Triggers

All triggers kill the **inbox** immediately when breached:

| Trigger | Threshold | Priority | Rationale |
|---------|-----------|----------|-----------|
| `spam_complaint` | **>=1** | 0 (Highest) | User reported spam — inbox killed instantly |
| `hard_blocked_24h` | **>=2** | 1 | Spam/policy rejection = active reputation damage |
| `hard_unknown_24h` | **>=3** | 2 | Bad addresses = list quality issue |
| `hard_bounces_24h` | **>=2** | 3 | Combined fallback for unclassified bounces |
| `hard_bounce_rate_7d` | **>2.0%** | 4 | Sustained hard bounce rate (min 100 sends) |
| `bounce_rate_all_7d` | **>5%** | 5 | Total bounce rate threshold |

### Domain Burn Classification

After an inbox is killed, the kill processor decides whether to also **burn the domain** (`pool_status = 'burned'`). This is a two-tier classification:

| Classification | Triggers | Domain Action | Rationale |
|----------------|----------|---------------|-----------|
| **Rate-based domain evaluation** | `spam_complaint` | Complaint rate < 0.3% = safe. 0.3-1.0% = `monitoring` (7-day window). > 1.0% = immediate burn. | Rate-based thresholds scale proportionally across different domain sizes (3-inbox Gmail vs 50-inbox Microsoft) |
| **Inbox-level only** | All other triggers | Never burns domain | Bounces, disconnects, and list-quality issues are inbox-level. Safe to promote B-Set inboxes from the same domain |

**Workspace circuit breaker:** 3+ domains in the same workspace with spam kills within 24h triggers fleet-wide list quality response. Affected domains enter `monitoring` instead of burning, even if rate exceeds 1.0%. Prevents cascade burns from a single bad list.

```python
# From kill_processor.py
DOMAIN_KILLING_TRIGGERS = set()  # Empty — provider_block_* removed (misclassified recipient rejections)

CONDITIONAL_DOMAIN_TRIGGERS = {
    'spam_complaint',  # Rate-based: <0.3% safe, 0.3-1.0% monitoring, >1.0% burn
}

INBOX_KILLING_TRIGGERS = {
    'hard_bounces_24h', 'hard_blocked_24h', 'hard_unknown_24h',
    'hard_bounce_rate_7d', 'bounce_rate_all_7d',
    'disconnected_timeout',
}
```

> **History**: Prior to 2026-03-18, `spam_complaint` was an instant domain burn. Production audit found 32 domains incorrectly burned from single spam complaints (e.g., `fixselery.com` — 51/52 inboxes live, health 91, burned from 1 complaint). Changed to count-based (2+) on 2026-03-18, then to rate-based thresholds on 2026-03-19 for proportional response across domain sizes.

### Domain Burn = Total Loss (Domain-Level Reserve Pool)

**A domain burn condemns ALL inboxes on that domain**, not just the ones that triggered the kill. The reserve pool operates at the **domain level** — you cannot split inboxes from the same domain and selectively reserve some.

When a domain burns:
1. `burn_domain_and_promote()` SQL function sets `pool_status = 'burned'`
2. A **reserve domain** (with all its inboxes) is promoted to `pool_status = 'live'`
3. If no reserve domain exists → Slack alert: "URGENT: Order replacement domains via HyperTide"

**Blast radius depends on ESP** (set by vendor HyperTide, not configurable by us):

| ESP | Inboxes/Domain | Inboxes Lost per Burn | Daily Capacity Lost |
|-----|---------------|----------------------|---------------------|
| Gmail | ~3 | ~3 | ~60 sends/day |
| Microsoft | ~50 | ~50 | ~100 sends/day |

This means a Microsoft domain burn destroys ~50 inboxes even if only 2-3 triggered the kill. The other 47-48 healthy inboxes are collateral damage. This is a structural concentration risk inherent to the vendor-provided Microsoft infrastructure shape.

### Differentiated Bounce Thresholds

Not all hard bounces are equal. The system distinguishes:

| Bounce Type | SMTP Codes | Meaning | Urgency |
|-------------|------------|---------|---------|
| `hard_blocked` | 550 5.7.x, or keyword (blocked/spam/blacklist/denied) | Spam/policy rejection | **Critical** - sender reputation damage |
| `hard_unknown` | 550 5.1.x, or keyword (not found/unknown) | Bad email address | Moderate - list quality issue |
| `soft_full` | 552, 452, 5.2.2, 4.2.2 | Mailbox full/over quota | Low - temporary |
| `soft_temp` | 421, 4.7.x, any 4xx | Temporary failure | Low - retry |
| `unknown` | Empty/missing bounce reason | Unclassifiable | None - excluded from kill triggers |

See [[adr-005-differentiated-bounce-thresholds]] for the decision rationale.

## Kill Queue Process

```
┌─────────────────────────────────────────────────────────────────┐
│                        KILL QUEUE FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DETECT     Health check finds trigger breach               │
│       ↓        (runs every 15 minutes)                         │
│                                                                 │
│  2. QUEUE      Insert into kill_queue table                    │
│       ↓        Status: 'pending'                               │
│                                                                 │
│  3. TAG        Apply trigger-specific tag in EmailBison        │
│       ↓        Tag: "flagged_{trigger_type}"                   │
│                Examples: flagged_fresh_inbox_bounce,           │
│                          flagged_spam_complaint                │
│                Status: 'flagged'                               │
│                                                                 │
│  4. UPDATE     Mark inbox_state = 'dead' locally               │
│                Inbox excluded from future campaigns            │
│                                                                 │
│  NOTE: Inboxes are NOT deleted from EmailBison.                │
│        They remain tagged for visibility into WHY flagged.     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Tagging System (No Deletion)

Inboxes are tagged with trigger-specific tags for visibility:

| Tag Name | Trigger | Meaning |
|----------|---------|---------|
| `flagged_spam_complaint` | Spam complaint | User reported spam |
| `flagged_hard_blocked_24h` | Hard blocked | Spam/policy rejection |
| `flagged_hard_unknown_24h` | Hard unknown | Bad email addresses |
| `flagged_hard_bounces_24h` | Hard bounces | Combined fallback |

**Why no deletion?**
- Inboxes remain in EmailBison for manual review
- Tags provide visibility into WHY each inbox was flagged
- Can filter by tag in EmailBison to see patterns
- Easier to reverse if false positive (cancel_kill removes tag)

> **Important**: Tags are created on-demand using `get_or_create_tag()`. The kill processor caches tag IDs per workspace per run for efficiency.

## Database Schema

### kill_queue Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `inbox_id` | UUID | FK to sender_accounts |
| `workspace_id` | UUID | FK to workspaces |
| `trigger_type` | VARCHAR | Which trigger fired |
| `trigger_value` | DECIMAL | Actual value at trigger time |
| `trigger_threshold` | DECIMAL | Threshold that was breached |
| `status` | VARCHAR | pending, flagged, failed, cancelled |
| `tagged_at` | TIMESTAMP | When inbox was tagged in EmailBison |
| `tag_name` | VARCHAR | Trigger-specific tag applied (e.g., flagged_fresh_inbox_bounce) |
| `error_message` | TEXT | Error details if failed |
| `created_at` | TIMESTAMP | When queued |

### sender_accounts Bounce Columns

| Column | Type | Description |
|--------|------|-------------|
| `hard_bounces_24h` | INTEGER | Combined hard bounce count (24h) |
| `hard_blocked_24h` | INTEGER | Spam/policy rejections (24h) |
| `hard_unknown_24h` | INTEGER | Bad address bounces (24h) |
| `hard_bounces_7d` | INTEGER | Combined hard bounces (7d rolling) |
| `complaints_lifetime` | INTEGER | Total spam complaints (never decrements) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KILL_THRESHOLD_SPAM` | 1 | Spam complaints to trigger kill |
| `KILL_THRESHOLD_HARD_BLOCKED_24H` | 2 | Spam/policy rejections to trigger |
| `KILL_THRESHOLD_HARD_UNKNOWN_24H` | 3 | Bad addresses to trigger |
| `KILL_THRESHOLD_HARD_BOUNCES_24H` | 2 | Combined fallback threshold |
| `KILL_THRESHOLD_HARD_BOUNCE_RATE` | 0.02 | Hard bounce rate (2.0%) |
| `KILL_THRESHOLD_TOTAL_BOUNCE_RATE` | 0.05 | Total bounce rate (5%) |
| `KILL_THRESHOLD_MIN_SENDS` | 100 | Min sends before rate triggers |
| `KILL_THRESHOLD_FRESH_INBOX_DAYS` | 21 | Days before inbox "not fresh" |

## Evaluation Priority

Kill triggers are evaluated in priority order. Multiple triggers can fire simultaneously:

```python
# Priority order (evaluated top to bottom)
1. spam_complaint      # >= 1 = inbox killed. Domain evaluated by complaint rate thresholds.
2. hard_blocked_24h    # >= 2 = reputation damage (inbox-level only)
3. hard_unknown_24h    # >= 3 = list quality (inbox-level only)
4. hard_bounces_24h    # >= 2 = fallback (only if no specific trigger)
5. hard_bounce_rate_7d # > 2.0% with 100+ sends
6. bounce_rate_all_7d  # > 5%
```

The combined `hard_bounces_24h` fallback only fires if neither `hard_blocked_24h` nor `hard_unknown_24h` triggered. This catches edge cases where bounce classification failed.

### Domain Burn Decision (After Inbox Kill)

After an inbox is killed, the kill processor evaluates whether the trigger warrants burning the entire domain:

```
Inbox killed with trigger_type
    ↓
Is it spam_complaint?
    YES → Calculate domain complaint rate (spam-killed / total inboxes)
           ↓
           Workspace circuit breaker? (3+ domains with spam kills in 24h)
               YES → Domain enters monitoring (fleet-wide list event)
               NO  ↓
           Rate > 1.0%?   → Immediate domain burn. Reserve domain promoted.
           Rate 0.3-1.0%? → Domain enters monitoring (7-day window).
                             Re-evaluate after 7 days: burn if rate >= 1.0%, else flagged.
           Rate < 0.3%?   → Inbox-level only. Domain safe. Promote B-Set inbox.
    NO ↓
Inbox-level kill. Domain continues operating. Promote B-Set inbox.
```

## SMTP Code Classification

Bounces are classified by extracting SMTP codes from message bodies:

| Code | Extended | Classification | Kill Trigger |
|------|----------|----------------|--------------|
| 550 | 5.1.1 | `hard_unknown` | `hard_unknown_24h` |
| 550 | 5.1.0 | `hard_unknown` | `hard_unknown_24h` |
| 550 | 5.7.1 | `hard_blocked` | `hard_blocked_24h` |
| 550 | 5.7.51 | `hard_blocked` + spam | `spam_complaint` |
| 552 | 5.2.2 | `soft_full` | None |
| 452 | 4.2.2 | `soft_full` | None |
| 421 | 4.7.0 | `soft_temp` | None |

## Daily Counter Reset

**Critical**: 24h counters reset at midnight to prevent accumulation:

- `hard_bounces_24h` → 0
- `hard_blocked_24h` → 0
- `hard_unknown_24h` → 0

Without this reset, legitimate inboxes would eventually trigger thresholds.

See [[../local-development/emailbison-sync-worker]] for the reset implementation.

## Monitoring

### Kill Trigger Monitor (UI)

The Health page shows:

- **Action Required** (red) - Inboxes pending kill
- **Under Review** (yellow) - Confirming triggers (planned)
- **Recent Kills** - Completed deletions

### Verification Queries

```sql
-- Current kill queue status
SELECT status, trigger_type, COUNT(*)
FROM kill_queue
GROUP BY status, trigger_type
ORDER BY COUNT(*) DESC;

-- Inboxes with active triggers
SELECT email_address, hard_blocked_24h, hard_unknown_24h, complaints_lifetime
FROM sender_accounts
WHERE inbox_state = 'live'
AND (hard_blocked_24h >= 2 OR hard_unknown_24h >= 3 OR complaints_lifetime >= 1);

-- Recently flagged by trigger type (with tag names)
SELECT trigger_type, tag_name, COUNT(*), MAX(tagged_at)
FROM kill_queue
WHERE status = 'flagged'
GROUP BY trigger_type, tag_name
ORDER BY COUNT(*) DESC;

-- Flagged inbox breakdown by workspace
SELECT w.workspace_name, kq.trigger_type, kq.tag_name, COUNT(*)
FROM kill_queue kq
JOIN workspaces w ON kq.workspace_id = w.id
WHERE kq.status = 'flagged'
GROUP BY w.workspace_name, kq.trigger_type, kq.tag_name
ORDER BY w.workspace_name, COUNT(*) DESC;
```

## ESP-Specific Kill Profiles

Gmail and Microsoft have fundamentally different infrastructure shapes (set by vendor HyperTide), which creates different risk profiles under the same kill trigger definitions:

| Metric | Gmail | Microsoft |
|--------|-------|-----------|
| **Inboxes per domain** | ~3 | ~50 |
| **Daily limit per inbox** | 20 | 2 |
| **Domain daily capacity** | ~60 sends | ~100 sends |
| **Inbox kill rate** | Higher (fewer inboxes, more volume each) | Lower (many inboxes, less volume each) |
| **Domain burn rate** | Lower (kills spread across many domains) | Higher (kills concentrate on few domains) |
| **Blast radius per burn** | Low (~3 inboxes) | Catastrophic (~50 inboxes) |
| **Rate trigger activation** | ~5 days (100 sends at 20/day) | ~50 days (100 sends at 2/day) |

**Key insight**: Gmail has higher inbox-level attrition but lower domain-level risk. Microsoft has lower inbox-level attrition but dramatically higher domain-level risk due to concentration. Rate-based thresholds handle this proportionally: 1 spam kill on a 50-inbox Microsoft domain = 2% rate (monitoring), while 1 spam kill on a 3-inbox Gmail domain = 33% rate (immediate burn).

**Detection gap for Microsoft**: Absolute-count triggers (`hard_unknown_24h >= 3`) are difficult to hit at 2 sends/day. Rate-based triggers require 100 minimum sends (~50 days at Microsoft volume). This means problematic Microsoft inboxes take longer to detect than Gmail inboxes.

ESP reputation in the health dashboard is derived from kill rate per provider:
- <5% kill rate → **High** reputation
- <15% → **Medium**
- <30% → **Low**
- >=30% → **Bad**

## Campaign → Kill Attribution

Kill attribution traces from campaigns to dead inboxes via `response_messages`:

```
Campaign sends email → EmailBison records response → response_messages table
                                                        ↓
                                                   Bounce classified (sync_events.py)
                                                        ↓
                                                   Kill trigger evaluated (health_checks.py)
                                                        ↓
                                                   Inbox killed (kill_processor.py)
                                                        ↓
                                                   Attribution query joins:
                                                   response_messages.campaign_id +
                                                   sender_accounts.inbox_state = 'dead'
```

The attribution query:
```sql
SELECT rm.campaign_id,
       COUNT(DISTINCT rm.sender_account_id) FILTER (WHERE sa.inbox_state = 'dead') as inboxes_killed,
       COUNT(DISTINCT d.id) FILTER (WHERE sa.inbox_state = 'dead') as domains_affected
FROM response_messages rm
JOIN sender_accounts sa ON rm.sender_account_id = sa.id
LEFT JOIN domains d ON sa.domain_id = d.id
WHERE rm.folder = 'bounced'
GROUP BY rm.campaign_id
```

## Domain State from Kill Triggers

The sync worker (`health_checks.py`) maintains `domain_state` based on kill trigger outcomes. **`domain_state` is now trigger-aware** — only reputation kills affect domain state, not list-quality or operational kills:

| Rule | Resulting State | Rationale |
|------|----------------|-----------|
| Complaint rate > 1.0% | `dead` | Severe domain compromise, immediate burn |
| Complaint rate 0.3% - 1.0% | `monitoring` | 7-day observation window, may recover or burn |
| Complaint rate 0.1% - 0.3% | `flagged` | Warning signal, inbox-level issue |
| Complaint rate < 0.1% | `live` | Domain operating normally |
| >30% unhealthy AND (10+ inboxes OR 2+ unhealthy) | `dead` | Capacity safety net |
| All inboxes disconnected | `flagged` | OAuth issues across entire domain |
| Workspace circuit breaker (3+ domains with spam kills in 24h) | `monitoring` | Overrides burn, fleet-wide list event |

Domain state values: `live`, `flagged`, `monitoring`, `dead`

List-quality kills (`hard_unknown_24h`, `hard_bounces_24h`, etc.) and operational kills (`disconnected_timeout`) do NOT change domain state — they are inbox-level issues that do not indicate domain reputation compromise.

**Burned domains** (`pool_status='burned'`) are set by the kill processor when complaint rate exceeds 1.0% (or when a `monitoring` domain exceeds 1.0% after the 7-day window). The workspace circuit breaker overrides this: if 3+ domains in the workspace have spam kills in 24h, domains enter `monitoring` instead of burning.

This is separate from `domain_state` and indicates the domain needs replacement. A domain can be `domain_state = 'dead'` (from capacity safety net) but NOT burned. A domain in `monitoring` is under observation and will be re-evaluated after 7 days.

## Files

| File | Purpose |
|------|---------|
| `sync_modules/health_checks.py` | Kill trigger evaluation + domain state |
| `sync_modules/kill_processor.py` | Kill queue processing + domain burning |
| `sync_modules/sync_events.py` | Bounce classification from EmailBison responses |
| `api/routes/health.py` | Kill trigger monitor + ESP analysis + campaign attribution API |

## Related

- [[../features/health-monitoring]] - Health monitoring overview
- [[adr-005-differentiated-bounce-thresholds]] - Differentiated thresholds decision
- [[../local-development/emailbison-sync-worker]] - Sync worker that runs checks
- [[domain-lifecycle]] - Domain state machine
