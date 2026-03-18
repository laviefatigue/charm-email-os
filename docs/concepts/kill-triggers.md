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
3. **1 spam complaint = inbox death** - The inbox is always killed immediately. The *domain* only burns when 2+ inboxes on the same domain have spam complaints (cross-inbox pattern).
4. **Differentiated thresholds** - Spam blocks are worse than bad addresses
5. **Proportional domain response** - 1 bad inbox out of 50 is an inbox problem, not a domain problem. Domain burns require evidence of domain-level compromise.

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

| Classification | Triggers | Domain Burn Rule | Rationale |
|----------------|----------|------------------|-----------|
| **Conditional domain burn** | `spam_complaint` | Burns only when **2+ inboxes** on the same domain have the same trigger | 1 spam complaint on 1 of 50 inboxes is an inbox problem, not domain compromise. Cross-inbox pattern = domain reputation issue |
| **Inbox-level only** | All other triggers | Never burns domain | Bounces, disconnects, and list-quality issues are inbox-level. Safe to promote B-Set inboxes from the same domain |

```python
# From kill_processor.py
DOMAIN_KILLING_TRIGGERS = set()  # Empty — provider_block_* removed (misclassified recipient rejections)

CONDITIONAL_DOMAIN_TRIGGERS = {
    'spam_complaint',  # 1 inbox = inbox kill; 2+ inboxes = domain burn
}

INBOX_KILLING_TRIGGERS = {
    'hard_bounces_24h', 'hard_blocked_24h', 'hard_unknown_24h',
    'hard_bounce_rate_7d', 'bounce_rate_all_7d',
    'disconnected_timeout',
}
```

> **History**: Prior to 2026-03-18, `spam_complaint` was an instant domain burn. Production audit found 32 domains incorrectly burned from single spam complaints (e.g., `fixselery.com` — 51/52 inboxes live, health 91, burned from 1 complaint). Changed to require cross-inbox pattern confirmation.

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
1. spam_complaint      # >= 1 = inbox killed. Domain burned only if 2+ inboxes affected.
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
    YES → Count dead inboxes on same domain with same trigger.
           2+ inboxes? → Domain burn (cross-inbox pattern confirmed).
           1 inbox?    → Inbox-level only. Domain safe. Promote B-Set inbox.
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

Different ESPs exhibit different kill patterns based on their enforcement behavior:

| Provider | Typical Kill Rate | Top Triggers | Pattern |
|----------|------------------|--------------|---------|
| **Microsoft** | ~25% | `hard_unknown`, `hard_blocked` | High volume of unknown-user bounces; aggressive blocking for policy violations |
| **Gmail** | ~45% | `hard_bounces`, `hard_blocked` | Higher kill rate due to stricter spam filtering; more bounce-based kills |
| **Other** | Varies | Mixed | Depends on provider infrastructure |

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
| 2+ reputation kills (spam_complaint, hard_blocked_24h) | `dead` | Reputation-impacting kills = domain compromised |
| >30% unhealthy inboxes | `dead` | Capacity safety net — widespread health degradation |
| 1 reputation kill | `flagged` | Warning signal, may recover |
| All inboxes disconnected | `flagged` | OAuth issues across entire domain |
| Otherwise | `live` | Domain operating normally |

List-quality kills (`hard_unknown_24h`, `hard_bounces_24h`, etc.) and operational kills (`disconnected_timeout`) do NOT change domain state — they are inbox-level issues that do not indicate domain reputation compromise.

**Burned domains** (`pool_status='burned'`) are set by the kill processor when domain-level triggers are confirmed:
- **Spam complaints**: Only after cross-inbox confirmation — 2+ inboxes on the same domain with `kill_trigger = 'spam_complaint'`

This is separate from `domain_state` and indicates the domain needs replacement. A domain can be `domain_state = 'dead'` (many dead inboxes from reputation kills or capacity safety net) but NOT burned — because burning requires confirmed cross-inbox spam complaint pattern.

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
