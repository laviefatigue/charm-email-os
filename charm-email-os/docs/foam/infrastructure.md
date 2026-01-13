# Infrastructure

Email sending infrastructure: [[domains]] and [[inboxes]].

## Overview

Each [[clients|client]] has email infrastructure for outbound campaigns:

```
Client
└── Domains (multiple)
    └── Inboxes (multiple per domain)
```

## Domains

### Data Model

```typescript
type DomainStatus =
  | 'pending_approval'  // Awaiting review
  | 'approved'          // Ready to purchase
  | 'rejected'          // Declined
  | 'purchasing'        // Being acquired
  | 'active'            // Live and sending
  | 'warming';          // In warmup phase

interface Domain {
  id: string;
  clientId: string;
  domain: string;           // e.g., "mail-techflow.io"
  status: DomainStatus;
  healthScore?: number;     // 0-100
  createdAt: Date;
  // Health tracking
  healthState?: 'live' | 'flagged' | 'dead';
  flaggedAt?: Date;
  deadAt?: Date;
}
```

### Domain Lifecycle Phases

Domains progress through phases based on age:

| Phase | Age (days) | Color | Action |
|-------|------------|-------|--------|
| warming | 0-14 | Yellow | Handle with care |
| ramping | 14-30 | Blue | Increasing sends |
| establishing | 30-90 | Green | Building reputation |
| peak | 90-180 | Green | Maximum performance |
| monitoring | 180-240 | Yellow | Prepare replacement |
| rotation | 240+ | Red | Force rotation required |

### Domain Health States

```
Live → Flagged (1 dead inbox) → Dead (≥2 dead inboxes)
```

## Inboxes

### Data Model

```typescript
type InboxStatus =
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'provisioning'
  | 'active'
  | 'warming';

interface Inbox {
  id: string;
  clientId: string;
  domainId: string;
  email: string;            // e.g., "alex.smith@mail-techflow.io"
  firstName: string;
  lastName: string;
  status: InboxStatus;
  warmupProgress?: number;  // 0-100
  dailySendLimit?: number;
  createdAt: Date;
  // Health tracking
  healthState?: 'live' | 'dead';
  killedAt?: Date;
  killReason?: string;
  provider?: 'gmail' | 'microsoft' | 'other';
}
```

### Inbox Health States

```
Live → Dead (permanent, one-way)
```

Inboxes are killed when [[health-monitoring|kill triggers]] are activated.

## Store: [[infrastructureStore]]

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
- `getInboxesByDomain(domainId)`
- `generateInboxesFromOnboarding(...)`

## Components

| Component | Purpose |
|-----------|---------|
| [[DomainCard]] | Domain with status and inboxes |
| [[DomainForm]] | Create new domain |
| [[DomainEditModal]] | Edit domain |
| [[InboxCard]] | Inbox status and health |
| [[InboxForm]] | Create new inbox |
| [[InboxEditModal]] | Edit inbox |
| [[WarmupProgress]] | Warmup progress bar |

## Route

`/clients/[clientId]/inboxes`

## Approval Workflow

1. Domains/inboxes created in `pending_approval` status
2. Admin reviews and approves/rejects
3. Approved items proceed to provisioning
4. Active items enter warmup phase
5. Health monitoring begins

## Auto-Generation

### Domain Variations
From primary domain `techflow.io`:
```
Prefixes: mail-, go-, try-, get-, hello-
Suffixes: -mail, -app, -hq, -team
```

### Inbox Personas
From first names with generated last names:
```
Names: Smith, Johnson, Williams, Brown, Davis
Format: {firstName}.{lastName}@{domain}
```

## Related

- [[clients]] - Parent entity
- [[health-monitoring]] - Health tracking
- [[domains]] - Domain details
- [[inboxes]] - Inbox details

---
Tags: #infrastructure #domains #inboxes
