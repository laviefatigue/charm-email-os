# Clients

Client entity represents organizations using Charm Email OS.

## Overview

Clients are the top-level entity. Each client has:
- Their own [[infrastructure]] (domains, inboxes)
- [[campaigns]] and [[leads]]
- [[health-monitoring]] metrics

## Data Model

```typescript
interface Client {
  id: string;
  name: string;
  domain: string;           // Primary business domain
  logo?: string;
  onboardingComplete: boolean;
  onboardingData?: OnboardingData;
  createdAt: Date;
}
```

## Onboarding Data

Collected during client setup wizard:

```typescript
interface OnboardingData {
  contactFirstNames: string[];  // Names for inbox personas
  primaryDomain: string;        // e.g., "techflow.io"
  industry: string;             // For campaign targeting
  product: string;              // What they sell
  inboxesNeeded: number;        // Desired capacity
  notes?: string;
}
```

## Client Lifecycle

```
1. Create Client
   ↓
2. Onboarding Wizard
   - Enter contact names
   - Set primary domain
   - Choose industry
   - Describe product
   - Set inbox count
   ↓
3. Generate Infrastructure
   - Domain variations created
   - Inbox personas generated
   ↓
4. Approval Workflow
   - Review domains
   - Review inboxes
   ↓
5. Active Operations
   - Strategy/campaigns
   - Lead management
   - Health monitoring
```

## Store: [[clientStore]]

### State
```typescript
{
  clients: Client[];
  selectedClientId: string | null;
}
```

### Key Actions
- `addClient({ name, domain })` - Create new client
- `completeOnboarding(id, data)` - Complete setup wizard
- `selectClient(id)` - Set active client for navigation

## Components

| Component | Location | Purpose |
|-----------|----------|---------|
| [[ClientCard]] | `components/clients/` | List card display |
| [[ClientForm]] | `components/clients/` | Creation form |
| [[OnboardingForm]] | `components/clients/` | Setup wizard |

## Routes

- `/clients` - Client list
- `/clients/[clientId]/*` - Client-specific views

## Onboarding Flow

The [[OnboardingForm]] guides users through setup:

1. **Contact Names** - First names for inbox personas
2. **Domain Setup** - Primary domain for variations
3. **Industry Selection** - From predefined list
4. **Product Description** - What the client offers
5. **Capacity** - How many inboxes needed
6. **Review** - Confirm and generate infrastructure

## Auto-Generation

When onboarding completes:

### Domain Generation
From `techflow.io` generates:
- `mail-techflow.io`
- `go-techflow.io`
- `techflow-mail.io`
- `techflow-app.io`

### Inbox Generation
From names `["Alex", "Sam"]` generates:
- `alex.smith@mail-techflow.io`
- `sam.johnson@mail-techflow.io`

## Related

- [[infrastructure]] - Domains and inboxes
- [[campaigns]] - Client campaigns
- [[health-monitoring]] - Client health

---
Tags: #clients #entities #onboarding
