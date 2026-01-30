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

There are two onboarding paths:

### In-App Wizard (Quick Setup)

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

### External Onboarding Form (Comprehensive)

See [[onboarding-form]] for the detailed external form at **https://onboard.laviefatigue.com**.

Captures 8 sections of deep client context:
- Company foundation & funding
- Product/service offering
- Market signals & buying triggers
- Customer segments & personas
- Current sales tools
- Messaging voice & proof points
- GTM goals & success metrics

This data feeds into [[campaign-ideas|campaign generation]].

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

## Connection to Lead Refinery

Client onboarding data drives the [[lead-refinery]] pipeline. When a campaign needs leads, ICP criteria extracted from onboarding flow into the DuckDB query:

| Onboarding Field | Lead Refinery Use |
|-----------------|-------------------|
| Industry | DuckDB `WHERE industry MATCHES` filter |
| Target titles (from personas) | DuckDB title matching |
| Company size | DuckDB `WHERE company_size >=` filter |
| Geography (from personas) | DuckDB location filter |
| Buying signals | Lead prioritization scoring |

Each client's campaigns consume leads from the shared 75.4M reservoir, tracked by `client_contract_id` in DuckDB to prevent cross-client lead recycling.

See [[system-integration]] for the full platform data flow.

## Related

- [[onboarding-form]] - External comprehensive onboarding form
- [[infrastructure]] - Domains and inboxes
- [[campaigns]] - Client campaigns
- [[campaign-ideas]] - AI-generated campaign ideas
- [[health-monitoring]] - Client health
- [[system-integration]] - Platform-wide integration map
- [[lead-refinery]] - Lead verification pipeline driven by client ICP

---
Tags: #clients #entities #onboarding
