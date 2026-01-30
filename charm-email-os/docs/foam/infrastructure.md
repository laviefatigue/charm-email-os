# Infrastructure

Email sending infrastructure: [[domains]], [[inboxes]], and [[sender-names]].

## Overview

Each [[clients|client]] has email infrastructure for outbound campaigns:

```
Client
├── Sender Names (base names → variations)
└── Domains (multiple)
    └── Inboxes (multiple per domain)
```

## Infrastructure Provisioning Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. DOMAIN DISCOVERY                                             │
│    • Campaign docs submission → extract domain ideas            │
│    • Manual generation via domain sourcing tools                │
│    Status: pending → approved → purchased                       │
├─────────────────────────────────────────────────────────────────┤
│ 2. NAME CONFIGURATION                                           │
│    • Add base names (seeds): "Chris Booth"                      │
│    • Generate variations: chris.booth, c.booth, cbooth...       │
│    • Save approved variations to client profile                 │
│    See: [[sender-names]]                                        │
├─────────────────────────────────────────────────────────────────┤
│ 3. NS VERIFICATION                                              │
│    • Verify nameservers point to DNSimple                       │
│    • Fix NS if needed (24-48hr propagation)                     │
│    See: ns-verification.md                                      │
├─────────────────────────────────────────────────────────────────┤
│ 4. INBOX SETUP                                                  │
│    • Select purchased domains ready for setup                   │
│    • Load configured sender names                               │
│    • Automate Hypertide provisioning                            │
│    Status: purchased → provisioning → active                    │
└─────────────────────────────────────────────────────────────────┘
```

## Domains

### Data Model

```typescript
type DomainStatus =
  | 'pending'           // Generated, awaiting approval
  | 'pending_approval'  // Awaiting review (legacy)
  | 'approved'          // Ready to purchase
  | 'rejected'          // Declined
  | 'purchased'         // Domain bought, needs inbox setup
  | 'propagating'       // NS set, waiting for DNS propagation
  | 'provisioning'      // Inboxes being created in Hypertide
  | 'active'            // Live and sending
  | 'legacy'            // Pre-existing infrastructure (needs audit)
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

## Connection to EmailBison & Lead Refinery

Infrastructure provisioned in Charm OS becomes the sending layer in EmailBison:

```
Charm OS Inbox (provisioned)
    → emailbisonAccountId (sender account in EmailBison)
    → Used by campaigns loaded with [[lead-refinery]] verified leads
    → [[health-monitoring]] tracks bounce rates back from EmailBison
```

When the [[lead-refinery]] pushes verified leads into an EmailBison campaign, those leads are sent from the inboxes provisioned here. Bounce and complaint data flows back through [[health-monitoring]] to trigger domain/inbox kill decisions.

See [[system-integration]] for the full platform data flow.

## Related

- [[clients]] - Parent entity
- [[sender-names]] - Name configuration and variations
- [[health-monitoring]] - Health tracking
- [[domains]] - Domain details
- [[inboxes]] - Inbox details
- [[system-integration]] - Platform-wide integration map
- [[lead-refinery]] - Leads sent through this infrastructure

---
Tags: #infrastructure #domains #inboxes #sender-names
