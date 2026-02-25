---
title: "ADR-005: Differentiated Bounce Thresholds"
created: 2026-02-12
updated: 2026-02-12
tags: [adr, status/accepted, health, kill-triggers, bounces]
status: accepted
---

# ADR-005: Differentiated Bounce Thresholds

## Status

**Accepted** - Implemented 2026-02-12

## Context

The kill trigger system initially treated all hard bounces equally with a single `hard_bounces_24h >= 2` threshold. However, hard bounces have different implications for sender reputation:

| Bounce Type | SMTP Codes | Meaning | Impact |
|-------------|------------|---------|--------|
| `hard_blocked` | 550 5.7.x | Spam/policy rejection | **Sender reputation damage** - ESP thinks we're spam |
| `hard_unknown` | 550 5.1.1 | Bad email address | **List quality issue** - we have bad data |

A spam/policy rejection (`hard_blocked`) is far more serious than a "user unknown" bounce (`hard_unknown`):

- **hard_blocked**: The receiving server rejected us due to reputation/policy. This indicates active damage to sender reputation.
- **hard_unknown**: The email address doesn't exist. This is a list hygiene issue, not a reputation problem.

Treating them equally could:
1. Allow reputation-damaging inboxes to send multiple spam-blocked emails before triggering
2. Kill inboxes too aggressively for minor list quality issues

## Decision

Implement differentiated thresholds with three tiers:

| Trigger | Threshold | Priority | Rationale |
|---------|-----------|----------|-----------|
| `hard_blocked_24h` | **>=1** | Highest | Single spam rejection = immediate concern |
| `hard_unknown_24h` | **>=3** | Medium | Need pattern, not single event |
| `hard_bounces_24h` | **>=2** | Fallback | Catches unclassified bounces |

### Implementation

1. **Database**: Add `hard_blocked_24h` and `hard_unknown_24h` columns to `sender_accounts`
2. **Sync**: Modify `increment_inbox_bounces()` to track bounce type separately
3. **Health Checks**: Evaluate triggers in priority order, with combined fallback

### Evaluation Logic

```python
# Priority order
1. Check hard_blocked_24h >= 1  → triggers if true
2. Check hard_unknown_24h >= 3  → triggers if true
3. Check hard_bounces_24h >= 2  → triggers ONLY if no specific trigger fired
```

The combined threshold is a **fallback** that catches edge cases where bounce classification failed (e.g., SMTP code not extracted).

## Consequences

### Positive

- **Faster response to reputation damage**: A single spam rejection now triggers kill
- **More tolerant of list quality issues**: 3 bad addresses required, not 2
- **Accurate attribution**: Kill reason shows specific trigger type
- **Configurable**: All thresholds exposed as environment variables

### Negative

- **More complexity**: Three thresholds instead of one
- **Migration required**: New database columns needed
- **Counter tracking**: Three counters to reset daily instead of one

### Neutral

- Combined `hard_bounces_24h` column kept for backwards compatibility
- Existing inboxes start fresh (counters at 0)

## Environment Variables

```bash
KILL_THRESHOLD_HARD_BLOCKED_24H=1   # Spam/policy rejections
KILL_THRESHOLD_HARD_UNKNOWN_24H=3   # Bad addresses
KILL_THRESHOLD_HARD_BOUNCES_24H=2   # Combined fallback
```

## Migration

```sql
-- Migration 025
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS hard_blocked_24h INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS hard_unknown_24h INTEGER DEFAULT 0;
```

## Files Changed

| File | Change |
|------|--------|
| `migrations/025_differentiated_bounce_columns.sql` | Add columns |
| `sync_modules/sync_events.py` | Differentiated increment logic |
| `sync_modules/health_checks.py` | New thresholds and evaluation |

## Related

- [[../concepts/kill-triggers]] - Kill trigger system overview
- [[../features/health-monitoring]] - Health monitoring
- [[../local-development/emailbison-sync-worker]] - Sync worker configuration
