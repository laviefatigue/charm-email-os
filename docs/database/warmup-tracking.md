# Warmup Lifecycle Tracking

> **2026-04-27 OVERHAUL UPDATE:** Two new columns added by migration 094 (with 096 fix) for continuous-tracking warmup state — `warmup_enabled_since` and `warmup_disabled_at`. These are MAINTAINED BY TRIGGER on every `warmup_enabled` flip, so the values reflect actual TRUE/FALSE transitions in real time, not observation timestamps. The 14 BD graduation timer in `lifecycle_tag_sync._graduate_mature_inboxes` reads `warmup_enabled_since` (NOT `warmup_started_at`) — this means a paused-then-resumed warmup resets the graduation clock, matching operational intent.

## Overview

Every inbox connected to EmailBison SHOULD be warming. The warmup lifecycle tracks this state through observation timestamps and (post-overhaul) trigger-maintained transition timestamps.

## Key Fields in sender_accounts

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `warmup_enabled` | BOOLEAN | EmailBison API | Current warmup status |
| `warmup_started_at` | TIMESTAMP | Local observation | When we first saw `warmup_enabled=TRUE` (observation-based) |
| `warmup_stopped_at` | TIMESTAMP | Local observation | When `warmup_enabled` changed `TRUE→FALSE` (observation-based) |
| `warmup_enabled_since` | TIMESTAMP | **Trigger-maintained (mig 094+096)** | NOW() when warmup_enabled transitions to TRUE; NULL when transitions to FALSE/NULL |
| `warmup_disabled_at` | TIMESTAMP | **Trigger-maintained (mig 094+096)** | NOW() when warmup_enabled transitions to FALSE/NULL; NULL when transitions to TRUE |

## State Machine

```
Connected inbox (EmailBison)
         ↓
warmup_enabled = TRUE (should always be this)
         ↓
warmup_started_at = NOW() (when we first observed)
         ↓
[Warmup active for 30 days]
         ↓
warmup_progress = days_warming / 30 * 100
         ↓
If warmup_enabled = FALSE (BAD EVENT):
    warmup_stopped_at = NOW()
```

## What EmailBison Provides vs What We Track

| Data | From EmailBison? | Notes |
|------|------------------|-------|
| `warmup_enabled` | YES | Boolean from `/warmup/sender-emails` endpoint |
| `warmup_score` | YES | 0-100 health score during warmup |
| `warmup_started_at` | NO | We track when we first observed warmup active |
| `warmup_stopped_at` | NO | We track when warmup stopped |

## Business Rule

**If an inbox is connected to EmailBison, it should ALWAYS be warming.**

`warmup_enabled = FALSE` is a problem state that needs investigation.

## Observation-Based Tracking

The timestamps are **observation-based**, meaning they record when OUR sync detected the change, not when EmailBison actually started/stopped warmup.

**Why observation-based?**
1. EmailBison API does NOT provide actual warmup start/stop timestamps
2. We can only know what we observe during sync cycles
3. Recording observation time is accurate and traceable

## Sync Frequency

| Module | Interval | What It Does |
|--------|----------|--------------|
| `WarmupSyncModule` | 30 minutes | Syncs warmup status, detects state changes |
| `AccountSyncModule` | 1 hour | Also tracks warmup_enabled in upserts |

## Warmup Progress Calculation

```python
# In sync_warmup.py get_warmup_progress()
days_warming = (now - warmup_started_at).days
warmup_progress = min(100, (days_warming / 30) * 100)
```

Standard warmup period is 30 days. Progress reaches 100% after 30 days of warming.

## Graduation Timer (post-overhaul)

`lifecycle_tag_sync._graduate_mature_inboxes` uses `warmup_enabled_since` (NOT `warmup_started_at`) for the 14 business-day graduation gate:

```sql
SELECT COUNT(*)
FROM generate_series(
    warmup_enabled_since::date,
    CURRENT_DATE - INTERVAL '1 day',
    INTERVAL '1 day'
) AS d
WHERE EXTRACT(DOW FROM d) NOT IN (0, 6)  -- Mon-Fri only
>= 14
```

The `warmup_enabled = TRUE` filter ensures paused inboxes don't graduate. If warmup is disabled mid-incubation, the trigger NULLs `warmup_enabled_since`, so the count returns 0 → not eligible until warmup is re-enabled (which re-stamps `warmup_enabled_since`, restarting the timer).

This is the **continuous-enabled** rule: 14 BD must pass with no warmup interruption. Stricter than the old `warmup_started_at + 21 calendar days` rule, but more accurate for the ride-to-graduation contract.

## Database Constraint

```sql
-- Migration 043 added this constraint
CHECK (warmup_stopped_at IS NULL OR warmup_started_at IS NULL
       OR warmup_stopped_at >= warmup_started_at)
```

This ensures `warmup_stopped_at` can never be before `warmup_started_at`.

## Related Code

- `sync_modules/sync_warmup.py` - Main warmup sync logic
- `sync_modules/sync_accounts.py` - Account upsert with warmup tracking
- `api/routes/inboxes.py` - API that exposes warmup status
- `api/models/inbox.py` - Pydantic models for warmup fields
