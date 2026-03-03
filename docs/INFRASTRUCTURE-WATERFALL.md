# Infrastructure Waterfall System

**Last Updated:** 2026-03-03
**Version:** 2.0 (Enhanced Rotation + Lifecycle Stages)

---

## Overview

The Infrastructure Waterfall is the primary domain provisioning and monitoring interface in Charm Email OS. It provides a 6-column view of the complete domain lifecycle from generation through operational status.

## Recent Improvements (March 2026)

### 1. Lifecycle Stage Filter (Migration 060/061)

Replaced the binary "Purchased/Not Purchased" filter with a three-stage lifecycle:

| Stage | Condition | Action Needed |
|-------|-----------|---------------|
| **Not Purchased** | `!isPurchased` | Buy domain from registrar |
| **Ready for HyperTide** | `isPurchased && isReadyForHyperTide && totalInboxCount === 0` | Order HyperTide provisioning |
| **Complete** | `isPurchased && totalInboxCount > 0` | Operational - monitor rotation |

**Why this matters:** Previously, users had to manually scan the table to find domains that were purchased but not yet provisioned. The new "Ready for HyperTide" stage surfaces these actionable domains immediately.

### 2. Enhanced Rotation Recommendations (Migration 062)

Rotation recommendations now factor in **error history** before suggesting reconnection vs rotation:

#### Priority Order:
1. **Spam complaints** → `rotate_now` (domain is burned)
2. **All disconnected** → `rotate_now` (no capacity)
3. **Multiple hard blocks (2+)** → `consider_rotate` (pattern of issues)
4. **Below capacity threshold** → `consider_rotate`
5. **Single hard block** → `monitor` (watch for escalation)
6. **Disconnected with clean history** → `monitor` + `reconnect` action

#### Key Insight
> "Why create more work to reconnect if we will consider rotating the domain anyway?"

If an inbox was disconnected but had spam complaints or hard blocks before disconnection, the system now classifies it for **rotation** rather than reconnection. This prevents wasted effort reconnecting compromised infrastructure.

#### New Fields in View:
- `recommended_action`: `'none' | 'watch' | 'reconnect' | 'rotate'`
- `has_compromised_inboxes`: boolean (spam complaints or hard blocks)
- `burn_breakdown`: JSONB with counts by trigger type
- `inboxes_with_complaints`: integer
- `inboxes_with_blocks`: integer

### 3. Removed STATUS Filter

The Live/Flagged/Dead STATUS filter was removed because:
- **Redundant:** The ROTATION filter provides better, more actionable coverage
- **OODA Principle:** Observe → Orient → Decide → Act - the rotation filter drives action

The STATUS column still displays domain health, but filtering by rotation status is more operationally useful.

---

## Filter Bar Layout

```
┌─────────────────┬───────────┬─────────────┬─────────────┬───────────┐
│ LIFECYCLE STAGE │    TLD    │  PROVIDER   │  ROTATION   │  >$15 (n) │
├─────────────────┼───────────┼─────────────┼─────────────┼───────────┤
│ All Domains     │ All TLDs  │ All         │ All Domains │   [ ]     │
│ Not Purchased   │ .COM      │ Entra       │ Needs       │           │
│ Ready for HT    │ .CO       │ Google      │   Attention │           │
│ Complete        │ .INFO     │             │ Healthy     │           │
└─────────────────┴───────────┴─────────────┴─────────────┴───────────┘
```

---

## Status Cell Visual Indicators

### Rotation Badges (top of cell)
- 🟣 **Monitor** - Soft indigo, watch closely
- 🟠 **Consider Rotate** - Warm amber, action suggested
- 🔴 **Rotate Now** - Rose/red, urgent action (pulses)

### Health Badges
- 🔴 **Compromised** - Red shield, spam complaints or hard blocks
- 🔵 **Reconnect** - Blue plug, clean history, worth reconnecting

### Status Badges
- 🟢 **Live** - Green, all inboxes operational
- 🟠 **Flagged** - Amber, some dead inboxes
- 🟠 **Disconnected** - Orange WiFi icon, all live inboxes disconnected
- 🔴 **Dead** - Red, all inboxes dead

### Inbox Counts
- Connected/Live count with progress bar
- Disconnected warning with days counter
- 21-day auto-kill warning (urgent when ≥18 days)

---

## API Endpoints

### GET `/api/infrastructure/waterfall/client/{client_id}`

Query Parameters:
```
purchase_status: 'all' | 'not_purchased' | 'ready' | 'complete' | 'purchased'
tld: 'com' | 'co' | 'info'
provider: 'entra' | 'google'
rotation_status: 'all' | 'needs_attention' | 'healthy'
show_over_budget: boolean
show_deactivated: boolean
show_needs_reconnection: boolean
```

Response includes `filter_counts`:
```json
{
  "filter_counts": {
    "notPurchased": 88,
    "ready": 8,
    "complete": 14,
    "purchased": 22,
    "by_rotation": {
      "healthy": 90,
      "monitor": 10,
      "consider_rotate": 5,
      "rotate_now": 6
    },
    "by_action": {
      "rotate": 11,
      "reconnect": 6,
      "watch": 3,
      "none": 90
    },
    "compromised": 2
  }
}
```

---

## Database Schema

### View: `v_infrastructure_waterfall`

Key columns added in migration 062:
```sql
-- Error history indicators
burn_breakdown JSONB,
inboxes_with_complaints INTEGER,
inboxes_with_blocks INTEGER,
has_compromised_inboxes BOOLEAN,

-- Enhanced rotation recommendation
rotation_recommendation VARCHAR,  -- not_applicable, healthy, monitor, consider_rotate, rotate_now
recommended_action VARCHAR        -- none, watch, reconnect, rotate
```

### Rotation Logic (in view):
```sql
CASE
    WHEN total_count = 0 THEN 'not_applicable'
    WHEN inboxes_with_complaints > 0 THEN 'rotate_now'
    WHEN burn_breakdown->>'spam_complaint' > 0 THEN 'rotate_now'
    WHEN connected_count = 0 AND live_count > 0 THEN 'rotate_now'
    WHEN inboxes_with_blocks >= 2 THEN 'consider_rotate'
    WHEN detected_provider = 'entra' AND connected_count < 40 THEN 'consider_rotate'
    WHEN detected_provider = 'google' AND connected_count < 2 THEN 'consider_rotate'
    WHEN inboxes_with_blocks = 1 THEN 'monitor'
    WHEN disconnected_count > 0 THEN 'monitor'
    ELSE 'healthy'
END AS rotation_recommendation
```

---

## Migrations

| Migration | Purpose |
|-----------|---------|
| 060 | Domain fulfillment tracking (expected_inbox_count, max_inboxes_seen) |
| 061 | Rotation recommendations in waterfall view |
| 062 | Enhanced rotation with error history (burn_breakdown, compromised detection) |

---

## Frontend Files

| File | Purpose |
|------|---------|
| `components/infrastructure/InfraFilterBar.tsx` | Filter dropdowns (Lifecycle, TLD, Provider, Rotation) |
| `components/infrastructure/WaterfallTable.tsx` | Main table with sorting |
| `components/infrastructure/cells/StatusCell.tsx` | Status column with rotation badges |
| `lib/stores/waterfallStore.ts` | Zustand store for filter state |
| `lib/types/infrastructure.ts` | TypeScript types |
| `api/routes/infrastructure.py` | FastAPI endpoint |

---

## Workflow Examples

### Finding Domains Ready for HyperTide Order
1. Set **Lifecycle Stage** → "Ready for HyperTide"
2. View shows only domains that are purchased, DNS-verified, but have no inboxes
3. Select domains and click "4 Entra Orders" or "1 Google Order"

### Finding Domains That Need Rotation
1. Set **Rotation** → "Needs Attention"
2. Domains sorted by priority: Monitor → Consider Rotate → Rotate Now
3. Check for **Compromised** badge (red shield) - these should NOT be reconnected
4. Check for **Reconnect** badge (blue plug) - these are worth saving

### Understanding Why Rotation is Recommended
Hover over any rotation badge to see tooltip:
- Capacity percentage
- Connected vs expected count
- Spam complaints count
- Hard blocks count
- Recommended action

---

## Design Philosophy

### OODA Loop Applied
- **Observe:** Waterfall shows all domains with real-time status
- **Orient:** Lifecycle and Rotation filters surface actionable items
- **Decide:** Badges indicate whether to rotate or reconnect
- **Act:** Bulk action buttons enable quick execution

### Minimal Viable Complexity
- Removed redundant STATUS filter
- Combined purchase stages into clear lifecycle
- Error history informs rotation decisions automatically
- Visual badges eliminate need to hover for basic decisions

---

## Related Documentation

- [HYPERTIDE-ORDER-FLOW.md](HYPERTIDE-ORDER-FLOW.md) - HyperTide provisioning workflow
- [DEPLOYMENT-CHECKLIST-DISCONNECTED-LIFECYCLE.md](DEPLOYMENT-CHECKLIST-DISCONNECTED-LIFECYCLE.md) - Disconnection handling
- [CSV-EXPORTS.md](CSV-EXPORTS.md) - Export functionality

---

**Document Version:** 2.0
**Author:** Claude (Charm OS Assistant)
**Status:** Production
