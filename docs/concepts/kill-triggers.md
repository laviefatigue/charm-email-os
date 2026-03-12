---
title: Kill Triggers
created: 2026-02-12
updated: 2026-02-12
tags: [concept, health, kill-triggers, infrastructure]
---

# Kill Triggers

Automated inbox termination system that protects domain reputation by detecting and removing problematic inboxes.

## Overview

Kill triggers are thresholds that, when breached, automatically queue an inbox for deletion. The system follows the v3 spec philosophy: **protect domains over inboxes** - inboxes are disposable, domains are not.

## Core Philosophy

1. **Kill fast, swap fast, diagnose after** - Don't investigate while reputation degrades
2. **100% backup capacity** - Always have warmed backups ready
3. **1 spam complaint = death** - No exceptions, no second chances
4. **Differentiated thresholds** - Spam blocks are worse than bad addresses

## Kill Trigger Types

### Instant Kill Triggers

These fire immediately and queue the inbox for deletion:

| Trigger | Threshold | Priority | Rationale |
|---------|-----------|----------|-----------|
| `spam_complaint` | **>=1** | 0 (Highest) | User reported spam = reputation death |
| `hard_blocked_24h` | **>=1** | 1 | Spam/policy rejection = active reputation damage |
| `hard_unknown_24h` | **>=3** | 2 | Bad addresses = list quality issue |
| `hard_bounces_24h` | **>=2** | 3 | Combined fallback for unclassified bounces |
| `hard_bounce_rate_7d` | **>0.5%** | 4 | Sustained hard bounce rate (min 50 sends) |
| `bounce_rate_all_7d` | **>5%** | 5 | Total bounce rate threshold |
| `fresh_inbox_blocked` | **>=1** | 6 | Reputation block on inbox <14 days sending |
| `fresh_inbox_unknown` | **>=3** | 7 | Bad-address bounces on inbox <14 days sending |

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
| `flagged_fresh_inbox_blocked` | Fresh inbox reputation block | Inbox <14 days sending with reputation block |
| `flagged_fresh_inbox_unknown` | Fresh inbox bad addresses | Inbox <14 days sending with 3+ bad-address bounces |
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
| `KILL_THRESHOLD_HARD_BLOCKED_24H` | 1 | Spam/policy rejections to trigger |
| `KILL_THRESHOLD_HARD_UNKNOWN_24H` | 3 | Bad addresses to trigger |
| `KILL_THRESHOLD_HARD_BOUNCES_24H` | 2 | Combined fallback threshold |
| `KILL_THRESHOLD_HARD_BOUNCE_RATE` | 0.005 | Hard bounce rate (0.5%) |
| `KILL_THRESHOLD_TOTAL_BOUNCE_RATE` | 0.05 | Total bounce rate (5%) |
| `KILL_THRESHOLD_MIN_SENDS` | 50 | Min sends before rate triggers |
| `KILL_THRESHOLD_FRESH_INBOX_DAYS` | 14 | Days before inbox "not fresh" |
| `KILL_THRESHOLD_FRESH_BLOCKED` | 1 | Reputation blocks to kill fresh inbox |
| `KILL_THRESHOLD_FRESH_UNKNOWN` | 3 | Bad-address bounces to kill fresh inbox |

## Evaluation Priority

Kill triggers are evaluated in priority order. Multiple triggers can fire simultaneously:

```python
# Priority order (evaluated top to bottom)
1. spam_complaint      # >= 1 = instant death
2. hard_blocked_24h    # >= 1 = reputation damage
3. hard_unknown_24h    # >= 3 = list quality
4. hard_bounces_24h    # >= 2 = fallback (only if no specific trigger)
5. hard_bounce_rate_7d # > 0.5% with 50+ sends
6. bounce_rate_all_7d  # > 5%
7. fresh_inbox_blocked  # Reputation block on inbox <14 days sending
8. fresh_inbox_unknown  # 3+ bad addresses on inbox <14 days sending
```

The combined `hard_bounces_24h` fallback only fires if neither `hard_blocked_24h` nor `hard_unknown_24h` triggered. This catches edge cases where bounce classification failed.

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
AND (hard_blocked_24h >= 1 OR hard_unknown_24h >= 3 OR complaints_lifetime >= 1);

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

## Files

| File | Purpose |
|------|---------|
| `sync_modules/health_checks.py` | Kill trigger evaluation |
| `sync_modules/kill_processor.py` | Kill queue processing |
| `sync_modules/sync_events.py` | Bounce classification |
| `api/routes/health.py` | Kill trigger monitor API |

## Related

- [[../features/health-monitoring]] - Health monitoring overview
- [[adr-005-differentiated-bounce-thresholds]] - Differentiated thresholds decision
- [[../local-development/emailbison-sync-worker]] - Sync worker that runs checks
- [[domain-lifecycle]] - Domain state machine
