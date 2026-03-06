# Decision: Fresh Inbox Bounce Uses sending_started_at

**Date:** 2026-03-06
**Status:** Implemented
**Author:** Claude + User

## Context

The `fresh_inbox_bounce` kill trigger fires when an inbox receives a hard bounce within its first 14 days. The question was: 14 days from **what**?

### Previous Implementation

Used `warmup_started_at` - the date when warmup was first enabled on the inbox.

```python
inbox_age_days = (now - warmup_started_at).days
if inbox_age_days < 14 and hard_bounces >= 1:
    trigger('fresh_inbox_bounce')
```

### Problem

1. **Warmup takes 2-3 weeks** before inbox starts sending to real leads
2. An inbox could be 3 weeks from warmup start but 0 days from first campaign send
3. The "fresh inbox" danger period is really about **early sending**, not early warmup
4. Warmup dates may be inaccurate due to backfilling/sync issues

### Evidence

Kill trigger data showed:
```
fresh_inbox_bounce: avg_days_from_warmup=4, avg_days_from_sending=0
```

Kills happen **0 days from sending start** - that's the real dangerous moment.

## Decision

Use `sending_started_at` for the fresh_inbox_bounce calculation.

- `sending_started_at` is set when inbox is first assigned to an active campaign
- This marks when the inbox actually starts sending to real leads
- More reliable than warmup dates for determining "fresh" status

### New Implementation

```python
# sync_modules/health_checks.py
sending_started_at = inbox.get('sending_started_at')
inbox_sending_age_days = None

if sending_started_at:
    inbox_sending_age_days = (now - sending_started_at).days
elif warmup_started_at:
    # Fallback for legacy data
    inbox_sending_age_days = (now - warmup_started_at).days

if inbox_sending_age_days < 14 and hard_bounces >= 1:
    trigger('fresh_inbox_bounce')
```

## Two Separate Concepts

| Concept | Source | Purpose |
|---------|--------|---------|
| **Incubation period** | `warmup_started_at` | Determines Live/Reserve classification |
| **Sending age** | `sending_started_at` | Determines fresh_inbox_bounce eligibility |

## Impact

- Inboxes that warmed for 3 weeks then just started sending are now correctly identified as "fresh"
- More accurate kill trigger attribution
- Historical data unaffected (uses warmup_started_at fallback)

## Related

- Migration `079_backfill_sending_started_at.sql` - backfills from `campaign_inboxes.assigned_at`
- `sync_modules/health_checks.py` - kill trigger evaluation
- `api/routes/health.py` - kill trigger reporting endpoints
