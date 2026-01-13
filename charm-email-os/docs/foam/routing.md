# Routing

Next.js App Router structure in `app/`.

## Route Map

```
/                           → Redirect to /clients
/clients                    → Client list page
/clients/[clientId]         → Client overview (redirects to strategy)
/clients/[clientId]/strategy    → Campaign ideas
/clients/[clientId]/inboxes     → Domains & inboxes
/clients/[clientId]/leads       → Campaign leads
/clients/[clientId]/health      → Health monitoring
```

## Root Layout

`app/layout.tsx` wraps all pages:

```tsx
<html>
  <body>
    <StoreProvider>
      <div className="flex h-screen">
        <Sidebar />
        <main className="flex-1 overflow-hidden">
          {children}
        </main>
      </div>
      <Toaster />
    </StoreProvider>
  </body>
</html>
```

## Page Details

### `/clients` - Client List

**File:** `app/clients/page.tsx`

Displays:
- Grid of [[ClientCard]] components
- [[ClientForm]] for creating new clients
- [[OnboardingForm]] modal for setup

### `/clients/[clientId]` - Client Base

**File:** `app/clients/[clientId]/page.tsx`

Redirects to `/clients/[clientId]/strategy` as default tab.

### `/clients/[clientId]/strategy` - Strategy Tab

**File:** `app/clients/[clientId]/strategy/page.tsx`

Displays:
- [[IdeaCard]] grid for pending ideas
- [[ApprovedCampaignRow]] list
- [[CreateCampaignModal]] workflow

Stores used: `strategyStore`, `campaignStore`

### `/clients/[clientId]/inboxes` - Infrastructure Tab

**File:** `app/clients/[clientId]/inboxes/page.tsx`

Displays:
- [[DomainCard]] list with nested [[InboxCard]]s
- [[DomainForm]] and [[InboxForm]] for creation
- [[ApprovalButtons]] for pending items

Stores used: `infrastructureStore`

### `/clients/[clientId]/leads` - Leads Tab

**File:** `app/clients/[clientId]/leads/page.tsx`

Displays:
- [[CampaignSidebar]] for campaign selection
- [[LeadsTable]] with filtering
- [[UploadModal]] for CSV import
- [[StatsRow]] statistics

Stores used: `campaignStore`

### `/clients/[clientId]/health` - Health Tab

**File:** `app/clients/[clientId]/health/page.tsx`

Displays:
- [[HealthScoreRing]] overall score
- [[DomainHealthGrid]] domain status
- [[KillTriggerMonitor]] active alerts
- [[ESPHealthSummary]] ESP reputation
- [[BackupCapacityGauge]] capacity
- [[CampaignAttributionPanel]] impact

Stores used: `healthStore`

## Navigation Flow

```
┌─────────────────────────────────────┐
│              Sidebar                │
│  ┌──────────────────────────────┐  │
│  │  Clients List (/clients)     │  │
│  │  ├── Client A                │  │
│  │  │   ├── Strategy            │  │
│  │  │   ├── Inboxes             │  │
│  │  │   ├── Leads               │  │
│  │  │   └── Health              │  │
│  │  └── Client B                │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
```

## Tab Navigation

Client pages use [[TabNavigation]] component:

| Tab | Route | Icon |
|-----|-------|------|
| Strategy | `/strategy` | Lightbulb |
| Inboxes | `/inboxes` | Mail |
| Leads | `/leads` | Users |
| Health | `/health` | Activity |

## Related

- [[architecture]] - System structure
- [[components]] - Component details

---
Tags: #routing #navigation #pages
