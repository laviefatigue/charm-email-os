---
title: Inventory Health Dashboard
created: 2026-02-09
updated: 2026-02-09
tags: [component, infrastructure, health, dashboard]
---

# Inventory Health Dashboard

Real-time infrastructure health visualization in the Active Inventory tab.

## Overview

The `InventoryHealthDashboard` component displays live [[emailbison-integration|EmailBison]] metrics combined with local RBL data, giving operators an at-a-glance view of infrastructure health.

## Location

- **File**: `components/inboxes/InventoryHealthDashboard.tsx`
- **Route**: `/clients/[clientId]/inboxes` (Active Inventory tab)

## Visual Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ ≡ Infrastructure Health                      ● EmailBison: Live │
├─────────────────────────────────────────────────────────────────┤
│ ┌────────────┬────────────┬────────────┬────────────┐          │
│ │ 📥 187     │ 📊 30      │ 🏠 77      │ 💚 100     │          │
│ │ Total      │ Connected  │ Domains    │ Health     │          │
│ │ Inboxes    │ 16% rate   │ 69 flagged │ Score      │          │
│ └────────────┴────────────┴────────────┴────────────┘          │
├─────────────────────────────────────────────────────────────────┤
│ Provider Breakdown                                              │
│ ┌─────────────────────────┬─────────────────────────┐          │
│ │ ☁️ Microsoft            │ 📧 Google               │          │
│ │ 154 inboxes            │ 33 inboxes              │          │
│ │ 0% connected           │ 91% connected           │          │
│ │ Avg Health: 52         │ Avg Health: 76          │          │
│ └─────────────────────────┴─────────────────────────┘          │
├─────────────────────────────────────────────────────────────────┤
│ ⚠️ Needs Attention (10 warning)                                 │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ ⚠️ charmclay.com listed on Spamhaus ZRD, URIBL multi      │  │
│ │ ⚠️ revenuewithcharm.co listed on Spamhaus ZRD, URIBL      │  │
│ │ ⚠️ meetcharm.com listed on Spamhaus ZRD, URIBL multi      │  │
│ │ ⚠️ letscharm.co listed on Spamhaus ZRD, URIBL multi       │  │
│ │ ... + 6 more items                                         │  │
│ └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Props

```typescript
interface InventoryHealthDashboardProps {
  health?: InventoryHealth | null;   // Health data from API
  isLoading?: boolean;               // Show loading spinner
  onRefresh?: () => void;            // Refresh button callback
  pendingInboxes?: number;           // Count for pending approval badge
}
```

## Stat Cards

Four metric cards with color-coded status:

| Card | Metric | Color Logic |
|------|--------|-------------|
| Total Inboxes | `totalInboxes` | Blue (neutral) |
| Connected | `connectedInboxes` | Green ≥80%, Orange ≥50%, Red <50% |
| Domains | `totalDomains` | Green if no flagged, Orange if flagged |
| Health Score | `avgHealthScore` | Green ≥80, Orange ≥60, Red <60 |

## Provider Breakdown Cards

Shows Microsoft vs Google infrastructure split:

```tsx
<ProviderCard
  name="Microsoft"
  count={154}
  connected={0}
  connectionRate={0}
  avgHealth={52}
/>
```

Icons:
- Microsoft Entra: `<Cloud />` (blue)
- Google Workspace: `<Mail />` (red)

## Attention Items

Three types of issues displayed:

### Blacklist Warnings

```tsx
<AttentionItem item={{
  type: 'blacklist',
  domain: 'example.com',
  lists: ['Spamhaus ZRD', 'URIBL multi'],
  severity: 'warning'
}} />
```

Display: `⚠️ example.com listed on Spamhaus ZRD, URIBL multi`

### High Bounce Alerts

```tsx
<AttentionItem item={{
  type: 'high_bounce',
  email: 'john@example.com',
  bounceRate: 0.035,
  bounced: 7,
  sent: 200,
  severity: 'critical'
}} />
```

Display: `🔴 john@example.com - 3.5% bounce rate (7/200 sent)`

### Low Health Warnings

```tsx
<AttentionItem item={{
  type: 'low_health',
  email: 'mike@example.com',
  healthScore: 42,
  severity: 'warning'
}} />
```

Display: `⚠️ mike@example.com - Health: 42`

## Loading State

```tsx
if (isLoading) {
  return (
    <Card>
      <CardContent className="py-8">
        <Loader2 className="animate-spin" />
        Loading inventory health from EmailBison...
      </CardContent>
    </Card>
  );
}
```

## Status Indicators

### EmailBison Connection

| State | Display |
|-------|---------|
| Available | `🟢 EmailBison: Live` |
| Unavailable | `🟡 EmailBison: Unavailable` |
| Error | `🟡 {error message}` |

### Pending Approval Badge

When `pendingInboxes > 0`:
```
⚠️ {n} pending approval
```

## Integration

### In Inboxes Page

```tsx
// app/clients/[clientId]/inboxes/page.tsx
import { InventoryHealthDashboard } from '@/components/inboxes';

function InboxesPage() {
  const [inventoryHealth, setInventoryHealth] = useState<InventoryHealth | null>(null);
  const [isLoadingHealth, setIsLoadingHealth] = useState(false);

  useEffect(() => {
    const fetchInventoryHealth = async () => {
      setIsLoadingHealth(true);
      try {
        const health = await healthApi.getInventoryHealth(clientId);
        setInventoryHealth(health);
      } finally {
        setIsLoadingHealth(false);
      }
    };
    fetchInventoryHealth();
  }, [clientId]);

  return (
    <InventoryHealthDashboard
      health={inventoryHealth}
      isLoading={isLoadingHealth}
      onRefresh={() => fetchInventoryHealth()}
      pendingInboxes={pendingCount}
    />
  );
}
```

## Related

- [[emailbison-integration]] - API data source
- [[infrastructure]] - Domain and inbox management
- [[health-monitoring]] - Kill triggers and alerts
- [[components]] - Component index

---
Tags: #component #dashboard #health #infrastructure
