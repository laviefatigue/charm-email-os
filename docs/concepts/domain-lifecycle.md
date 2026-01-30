---
title: Domain Lifecycle
created: 2026-01-22
updated: 2026-01-30
tags: [concept, domain, infrastructure]
---

# Domain Lifecycle

Domains transition through a defined status flow from generation to active use.

## Status Values

| Status | Description | UI Tab |
|--------|-------------|--------|
| `pending` | Generated, awaiting approval | Purchase New |
| `pending_approval` | Legacy alias for pending | Purchase New |
| `approved` | Approved, ready to purchase | Purchase New |
| `rejected` | Denied by user | Purchase New |
| `purchasing` | Purchase in progress | Purchase New |
| `purchased` | Domain bought, no inboxes yet | Purchase New (Setup Section) |
| `provisioning` | Inboxes being created in HyperTide | Purchase New (Setup Section) |
| `active` | Properly provisioned through new workflow | Current Inventory |
| `legacy` | Pre-existing infrastructure (before 1/22/26) | Current Inventory |
| `warming` | In warmup period (< 2 weeks) | Current Inventory |
| `flagged` | Health issues detected | Current Inventory |
| `dead` | Retired/disabled | Current Inventory |

## Status Flow Diagram

```
     ┌─────────┐
     │ pending │ (AI generates domain suggestions)
     └────┬────┘
          │
     ┌────▼────┐
  ┌──│approved │ (User approves)
  │  └────┬────┘
  │       │
  │  ┌────▼─────┐
  │  │purchased │ (Domain registrar purchase complete)
  │  └────┬─────┘
  │       │
  │  ┌────▼──────────┐
  │  │ provisioning  │ (HyperTide inbox automation running)
  │  └────┬──────────┘
  │       │
  │  ┌────▼────┐
  │  │ active  │ (Inboxes created and uploaded to EmailBison)
  │  └────┬────┘
  │       │
  │  ┌────▼────┐     ┌────────┐
  │  │ warming │────►│ flagged│ (Health issues)
  │  └────┬────┘     └───┬────┘
  │       │              │
  │       ▼              ▼
  │    (2 weeks)     ┌──────┐
  │       │          │ dead │
  │       ▼          └──────┘
  │   ┌───────┐
  │   │active │ (Fully warmed)
  │   └───────┘
  │
  └──►┌────────┐
     │rejected│ (User denies)
     └────────┘
```

## Special Status: Legacy

The `legacy` status was introduced on 2026-01-22 to handle pre-existing domains that:
- Were created before the new workflow was implemented
- Already have inboxes in EmailBison
- Need audit to confirm proper tracking

See [[adr-002-legacy-status]] for the decision rationale.

### Migration Endpoint

```
POST /api/v1/domains/migrate/legacy-domains-with-inboxes
```

Updates domains with existing inboxes from `purchased`/`pending`/`approved`/NULL to `legacy`.

## Tab Filtering Logic

```typescript
// Current Inventory: domains with inboxes in EmailBison
const inventoryDomains = domains.filter(d =>
  ['active', 'legacy', 'warming', 'flagged', 'dead'].includes(d.status)
);

// Purchase New: domains in purchase pipeline
const purchaseDomains = domains.filter(d =>
  ['pending', 'pending_approval', 'approved', 'rejected',
   'purchased', 'provisioning'].includes(d.status)
);

// Setup Section: purchased but needing inbox provisioning
const purchasedNeedingSetup = domains.filter(d =>
  ['purchased', 'provisioning'].includes(d.status)
);
```

## Purchase Job Locking

Independently of the domain status flow, domains can be **locked** to a purchase job via two columns:

| Column | Type | Description |
|--------|------|-------------|
| `purchase_job_id` | UUID | FK to `inbox_purchase_jobs.id`, set when domain is included in a purchase job |
| `purchase_job_status` | VARCHAR | Lock status: `pending`, `processing`, `executing`, or NULL (unlocked) |

### Lock vs Status

Domain locking is **orthogonal** to the domain lifecycle status. A domain with status `purchased` (needs inbox setup) can be:
- **Unlocked** (`purchase_job_id = NULL`) — available for selection
- **Locked** (`purchase_job_id = <job_uuid>`) — included in an active job, cannot be selected for another

### Lock Release

Locks are released (both columns set to NULL) when:
1. The purchase job **completes** successfully
2. The purchase job **fails** and is not retried
3. The purchase job is **cancelled** via `DELETE /api/inbox-purchasing/jobs/{job_id}`

### UI Indicators

In the "Step 2: Setup Inboxes" table:
- Locked domains show an amber **"Queued"** badge
- Their checkboxes are **disabled**
- A summary line shows the count of locked domains

## Type Definitions

### Frontend (TypeScript)
```typescript
// lib/types.ts
export type DomainStatus =
  | 'pending'
  | 'pending_approval'
  | 'approved'
  | 'rejected'
  | 'purchasing'
  | 'purchased'
  | 'provisioning'
  | 'active'
  | 'legacy'
  | 'warming'
  | 'flagged'
  | 'dead';
```

### Backend (Python)
```python
# api/models/domain.py
DomainStatus = Literal[
    "pending",
    "pending_approval",
    "approved",
    "rejected",
    "purchasing",
    "purchased",
    "provisioning",
    "active",
    "legacy",
    "warming",
    "flagged",
    "dead"
]
```

## Related

- [[infrastructure-hub]] - Parent hub
- [[inbox-provisioning]] - How inboxes are created
- [[adr-001-domain-status-lifecycle]] - Original design decision
- [[adr-002-legacy-status]] - Legacy status addition
