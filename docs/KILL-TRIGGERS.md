# Kill Triggers Reference

Kill triggers determine when an inbox is marked as "dead" and removed from active sending.

## Trigger Types & Thresholds

| Trigger | Threshold | Severity | Description |
|---------|-----------|----------|-------------|
| `spam_complaint` | >= 1 | Domain-killing | Any spam complaint = instant death |
| `provider_block_*` | >= 1 | Domain-killing | ESP-specific block (gmail/microsoft/yahoo) |
| `hard_blocked_24h` | >= 1 | Inbox-killing | Spam/policy rejection in 24h |
| `hard_unknown_24h` | >= 3 | Inbox-killing | Invalid recipient errors in 24h |
| `hard_bounces_24h` | >= 2 | Inbox-killing | Combined hard bounces in 24h |
| `fresh_inbox_bounce` | >= 1 | Inbox-killing | Any bounce on inbox < 14 days into sending |
| `disconnected_timeout` | 21 days | Inbox-killing | Disconnected for 21+ days |
| `hard_bounce_rate_7d` | > 5% | Inbox-killing | 7-day hard bounce rate (min 20 sends) |
| `bounce_rate_all_7d` | > 10% | Inbox-killing | 7-day total bounce rate (min 20 sends) |

## Domain-Killing vs Inbox-Killing

**Domain-killing triggers** (`spam_complaint`, `provider_block_*`):
- Indicate the entire domain's reputation is compromised
- B-Set inboxes from the same domain should NOT be promoted
- Domain should be flagged for rotation

**Inbox-killing triggers** (all others):
- Indicate individual inbox issues
- B-Set inboxes from the same domain CAN be promoted
- Domain may survive if other inboxes are healthy

## Fresh Inbox Bounce Calculation

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
| Top kill trigger | fresh_inbox_bounce (72%) | hard_bounces_24h (59%) |
| Spam complaint rate | 4.7% | 3.7% |

**Observations:**
- Google has higher kill rate due to stricter bounce detection
- Microsoft kills mostly from fresh_inbox_bounce (new inboxes fail fast)
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
