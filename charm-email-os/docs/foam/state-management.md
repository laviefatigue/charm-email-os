# State Management

Charm Email OS uses **Zustand** for client-side state management. All stores are located in `lib/stores/`.

## Store Overview

| Store | Purpose | Location |
|-------|---------|----------|
| [[clientStore]] | Client entities | `lib/stores/clientStore.ts` |
| [[infrastructureStore]] | Domains & Inboxes | `lib/stores/infrastructureStore.ts` |
| [[strategyStore]] | Campaign ideas | `lib/stores/strategyStore.ts` |
| [[campaignStore]] | Campaigns & Leads | `lib/stores/campaignStore.ts` |
| [[healthStore]] | Health metrics & alerts | `lib/stores/healthStore.ts` |

## Store Provider

All stores are initialized via `StoreProvider` in the root layout:

```tsx
// components/providers/StoreProvider.tsx
export function StoreProvider({ children }: { children: React.ReactNode }) {
  // Initialize stores with mock data on mount
  return <>{children}</>;
}
```

## clientStore

Manages [[clients]] data.

### State
```typescript
{
  clients: Client[];
  selectedClientId: string | null;
}
```

### Actions
- `setClients(clients)` - Bulk set clients
- `addClient({ name, domain })` - Create new client
- `updateClient(id, data)` - Partial update
- `selectClient(id)` - Set active client
- `completeOnboarding(id, data)` - Mark onboarding complete
- `getClient(id)` - Get by ID
- `getSelectedClient()` - Get currently selected

## infrastructureStore

Manages [[domains]] and [[inboxes]].

### State
```typescript
{
  domains: Domain[];
  inboxes: Inbox[];
}
```

### Domain Actions
- `addDomain({ clientId, domain })`
- `approveDomain(id)` / `rejectDomain(id)`
- `getDomainsByClient(clientId)`
- `generateDomainsFromOnboarding(clientId, onboarding)`

### Inbox Actions
- `addInbox({ clientId, domainId, firstName, lastName, email })`
- `approveInbox(id)` / `rejectInbox(id)`
- `getInboxesByClient(clientId)` / `getInboxesByDomain(domainId)`
- `generateInboxesFromOnboarding(...)`

## strategyStore

Manages [[campaign-ideas]].

### State
```typescript
{
  ideas: CampaignIdea[];
}
```

### Actions
- `generateIdeas(clientId, industry, segment)` - Create AI-generated ideas
- `approveIdea(id)` / `rejectIdea(id)`
- `updateIdea(id, data)`
- `getIdeasByClient(clientId)`
- `getPendingIdeas(clientId)` / `getApprovedIdeas(clientId)`

## campaignStore

Manages [[campaigns]] and [[leads]].

### State
```typescript
{
  campaigns: Campaign[];
  leads: Lead[];
}
```

### Campaign Actions
- `createCampaignFromIdea(idea)` - Convert approved idea to campaign
- `runCampaign(id)` / `pauseCampaign(id)`
- `getCampaignsByClient(clientId)`

### Lead Actions
- `uploadLeads(campaignId, leads)` - Add leads from CSV
- `simulateUploadLeads(campaignId, count)` - Generate mock leads
- `updateLeadStatus(id, status)`
- `getLeadsByCampaign(campaignId)`
- `simulateCampaignProgress(campaignId)` - Demo simulation

## healthStore

Manages [[health-monitoring]] data.

### State
```typescript
{
  inboxMetrics: InboxHealthMetrics[];
  domainMetrics: DomainHealthMetrics[];
  campaignMetrics: CampaignHealthMetrics[];
  killTriggers: KillTrigger[];
  alerts: HealthAlert[];
  backupCapacity: OverallBackupCapacity | null;
  contaminationSources: ListContaminationSource[];
  espSummaries: ESPHealthSummary[];
  overallSummary: OverallHealthSummary | null;
  isLoading: boolean;
  lastRefresh: Date | null;
}
```

### Key Actions
- `killInbox(inboxId, reason)` - Mark inbox as dead
- `flagDomain(domainId)` / `killDomain(domainId)`
- `executeKillTrigger(triggerId)` / `dismissKillTrigger(triggerId)`
- `quarantineCampaign(campaignId, reason)`
- `addAlert(alert)` / `acknowledgeAlert(alertId)`

## Usage Pattern

```tsx
import { useClientStore } from '@/lib/stores/clientStore';

function MyComponent() {
  const { clients, addClient } = useClientStore();

  const handleAdd = () => {
    addClient({ name: 'Acme', domain: 'acme.com' });
  };

  return (/* ... */);
}
```

## Related

- [[architecture]] - Overall system design
- [[data-models]] - Type definitions

---
Tags: #state #zustand #stores
