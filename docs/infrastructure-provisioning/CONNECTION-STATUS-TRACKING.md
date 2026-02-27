# Connection Status Tracking

## Overview

The Infrastructure Provisioning SPA now tracks **connection status** separately from **inbox state**. This provides accurate operational visibility into which inboxes are actually functional vs. those that need reconnection.

## Key Concepts

### Inbox State vs Connection Status

| Field | Source | Values | Meaning |
|-------|--------|--------|---------|
| `inbox_state` | Kill processor | `live`, `dead` | Whether inbox was killed for bad behavior (bounces, spam) |
| `status` | EmailBison API | `Connected`, `Not connected`, `Disconnected`, `Disabled` | Current connection to EmailBison |

### Status Definitions

| Status | Meaning | Action Required |
|--------|---------|-----------------|
| **Connected** | Inbox is active and sending | None |
| **Not connected** | OAuth token expired or credentials issue | Reconnect via HyperTide/EmailBison |
| **Disconnected** | Same as "Not connected" | Reconnect via HyperTide/EmailBison |
| **Disabled** | User explicitly disabled in EmailBison | Manual re-enable |

## Domain Status Calculation

Domain status now factors in connection status:

```python
def calculate_domain_status(live_count, dead_count, connected_count, disconnected_count):
    # Dead: killed inboxes (2+ dead, or no live with dead)
    if dead_count >= 2 or (live_count == 0 and dead_count > 0):
        return 'dead'

    # Flagged: has 1 dead inbox
    if dead_count >= 1:
        return 'flagged'

    # Flagged: has live inboxes but ALL are disconnected (no functional inboxes)
    if live_count > 0 and connected_count == 0 and disconnected_count > 0:
        return 'flagged'

    # Live: has at least one connected inbox
    if connected_count > 0:
        return 'live'

    return 'live'  # Default for domains not yet provisioned
```

### Status Hierarchy

| Status | Condition | Color |
|--------|-----------|-------|
| **dead** | 2+ killed inboxes OR no live with killed | Red |
| **flagged** | 1 killed inbox OR all live inboxes disconnected | Amber |
| **live** | Has at least 1 connected inbox | Green |

## API Response Fields

### Domain Level

```json
{
  "domain_name": "lovecharmgtm.com",
  "domain_status": "flagged",
  "live_inbox_count": 51,
  "dead_inbox_count": 0,
  "connected_inbox_count": 0,
  "disconnected_inbox_count": 51,
  "total_inbox_count": 51
}
```

### Provider Summary

```json
{
  "entra": {
    "inboxes_live": 154,
    "inboxes_dead": 0,
    "inboxes_connected": 0,
    "inboxes_disconnected": 154,
    "daily_capacity": 0
  }
}
```

## UI Display

### Summary Header

| Metric | Before | After |
|--------|--------|-------|
| Inboxes | `154/154 live` | `0/154 connected` |
| Daily Capacity | `385/day` (based on live) | `0/day` (based on connected) |
| Health Bar | `100% healthy` | `0% operational` |

### Status Cell

Shows operational capacity per domain:
- **Connected count** / live count (e.g., "0/51 connected")
- **Disconnected warning** with count
- **Progress bar** showing operational percentage (red when 0%)

## Database Schema

### View: v_infrastructure_waterfall

Added columns:
- `connected_inbox_count` - Live inboxes with status='Connected'
- `disconnected_inbox_count` - Live inboxes with status IN ('Not connected', 'Disconnected')

### Sender Accounts Table

Key columns for tracking:
- `inbox_state` - 'live' or 'dead' (set by kill processor)
- `status` - Connection status from EmailBison
- `killed_at` - When inbox was killed (NULL if alive)

## Migrations

| Migration | Purpose |
|-----------|---------|
| `051_fix_inbox_state_not_connected.sql` | Fixed 1,938 inboxes incorrectly marked as dead |
| `052_add_connection_status_tracking.sql` | Added connection counts to waterfall view |

## Sync Behavior

### sync_accounts.py

```python
# Only 'Disabled' sets inbox_state='dead'
inbox_state = 'dead' if status == 'Disabled' else 'live'
```

Previous bug treated 'Not connected' as dead, which was incorrect.

## Current State (Charm)

| Provider | Connected | Disconnected | Dead | Operational |
|----------|-----------|--------------|------|-------------|
| Entra | 0 | 154 | 0 | 0% |
| Google | 23 | 9 | 1 | 72% |

## Reconnection Flow

When inboxes show as "disconnected":

1. **Identify** - Filter by provider in Infrastructure page
2. **Export** - Use "Export disconnected accounts" in EmailBison
3. **Reconnect** - Use HyperTide reconnection flow
4. **Verify** - Status will update on next sync (hourly)

## Files Modified

| File | Changes |
|------|---------|
| `api/routes/infrastructure.py` | Added connection counts to summary, updated domain status calculation |
| `sync_modules/sync_accounts.py` | Fixed inbox_state logic (only 'Disabled' = dead) |
| `charm-email-os/lib/types/infrastructure.ts` | Added connection count fields |
| `charm-email-os/components/infrastructure/InfraSummaryHeader.tsx` | Shows connected/live, operational capacity |
| `charm-email-os/components/infrastructure/cells/StatusCell.tsx` | Shows connection status per domain |
