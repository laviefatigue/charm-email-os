# Kill Triggers Reference

Kill triggers determine when an inbox is marked as "dead" and removed from active sending.

## Trigger Types & Thresholds

| Trigger | Threshold | Inbox Severity | Domain Burn? | Description |
|---------|-----------|----------------|--------------|-------------|
| `spam_complaint` | >= 1 | Instant kill | Conditional (2+ inboxes) | Spam complaint kills inbox. Domain burns only when 2+ inboxes on same domain have spam complaints |
| `hard_blocked_24h` | >= 2 | Instant kill | No | Spam/policy rejection in 24h |
| `hard_unknown_24h` | >= 3 | Instant kill | No | Invalid recipient errors in 24h |
| `hard_bounces_24h` | >= 2 | Instant kill | No | Combined hard bounces in 24h |
| `disconnected_timeout` | 21 days | Instant kill | No | Disconnected for 21+ days |
| `hard_bounce_rate_7d` | > 2.0% | Instant kill | No | 7-day hard bounce rate (min 100 sends) |
| `bounce_rate_all_7d` | > 5% | Instant kill | No | 7-day total bounce rate (min 100 sends) |

## Domain Burn Classification

The kill processor uses a two-tier classification to decide domain-level action after an inbox kill:

**Conditional domain burns** (`spam_complaint`):
- 1 spam complaint on 1 of 50 inboxes = inbox-level problem, domain is safe
- 2+ inboxes on the same domain with spam complaints = cross-inbox pattern, domain burns
- Kill processor queries: `SELECT COUNT(*) FROM sender_accounts WHERE domain_id = $1 AND inbox_state = 'dead' AND kill_trigger = 'spam_complaint'`
- If count >= 2, domain burns. Otherwise, normal inbox-level kill + B-Set promotion.

**Inbox-level only** (all other triggers):
- Indicate individual inbox or list quality issues
- B-Set inboxes from the same domain CAN be promoted
- Domain continues operating with reduced capacity

> **History**: Prior to 2026-03-18, `spam_complaint` was an instant domain burn. A production audit found 32 domains incorrectly burned from single spam complaints. Changed to require 2+ cross-inbox pattern.

## Fresh Inbox Age Calculation

> **Note:** The `fresh_inbox_blocked` and `fresh_inbox_unknown` triggers have been removed (redundant with `hard_blocked_24h` and `hard_unknown_24h`). The incubation period is now 21 days. The age calculation below is still used for determining the incubation period.

**Key insight**: "Fresh" means fresh to **sending**, not fresh to warmup.

```python
# Correct: Use sending_started_at
inbox_sending_age = now - sending_started_at

# Wrong: Using warmup_started_at
# inbox_age = now - warmup_started_at  # Don't use this
```

**Why?**
- Warmup takes 2-3 weeks before inbox sends to real leads
- An inbox could be 3 weeks from warmup but 0 days from first campaign send
- The dangerous period is early SENDING, not early warmup

**Source:** `sending_started_at` is set when inbox is first assigned to an active campaign (via `campaign_inboxes.assigned_at`).

## ESP Comparison (Historical Data)

| Metric | Microsoft | Google |
|--------|-----------|--------|
| Total inboxes | 3,936 | 537 |
| Kill rate | 23.2% | 40.2% |
| Top kill trigger (historical) | fresh_inbox_bounce (72%, now removed) | hard_bounces_24h (59%) |
| Spam complaint rate | 4.7% | 3.7% |

**Observations:**
- Google has higher kill rate due to stricter bounce detection
- Microsoft historically killed mostly from fresh_inbox_bounce (now removed; covered by hard_blocked_24h/hard_unknown_24h)
- Google kills mostly from hard_bounces_24h (ongoing bounce accumulation)

## Kill Processing Flow

1. **Health check** runs every 15 minutes (`sync_modules/health_checks.py`)
2. Evaluates each inbox against all thresholds
3. Triggered inboxes added to `kill_queue` table
4. **Kill processor** runs every 30 minutes (`sync_modules/kill_processor.py`)
5. Processes queue: marks inbox dead, handles B-Set rotation, sends Slack alerts

## Related Files

| File | Purpose |
|------|---------|
| `sync_modules/health_checks.py` | Threshold definitions, `evaluate_inbox_health()` |
| `sync_modules/kill_processor.py` | Queue processing, B-Set rotation |
| `migrations/073_domain_rotation_events.sql` | Domain quarantine tracking |
| `api/routes/health.py` | Analysis endpoints |

## Related Decisions

- [FRESH-INBOX-BOUNCE-CALCULATION.md](./decisions/FRESH-INBOX-BOUNCE-CALCULATION.md) - Why we use sending_started_at
