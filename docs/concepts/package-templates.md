---
title: Package Templates
created: 2026-01-22
updated: 2026-01-22
tags: [concept, subscription, infrastructure]
---

# Package Templates

Pre-defined infrastructure packages that determine domain and inbox quotas for clients.

## Overview

Clients subscribe to packages that define:
- Number of Entra orders (2 domains × 52 inboxes each)
- Number of Google orders (5 domains × 3 inboxes each)
- Total domains and inboxes

## Package Definitions

### Starter Package

| Component | Value | Calculation |
|-----------|-------|-------------|
| Entra Orders | 6 | - |
| Entra Domains | 12 | 6 × 2 |
| Entra Inboxes | 624 | 12 × 52 |
| Google Orders | 5 | - |
| Google Domains | 25 | 5 × 5 |
| Google Inboxes | 75 | 25 × 3 |
| **Total Domains** | **37** | 12 + 25 |
| **Total Inboxes** | **699** | 624 + 75 |

### Growth Package

| Component | Value | Calculation |
|-----------|-------|-------------|
| Entra Orders | 12 | - |
| Entra Domains | 24 | 12 × 2 |
| Entra Inboxes | 1,248 | 24 × 52 |
| Google Orders | 10 | - |
| Google Domains | 50 | 10 × 5 |
| Google Inboxes | 150 | 50 × 3 |
| **Total Domains** | **74** | 24 + 50 |
| **Total Inboxes** | **1,398** | 1,248 + 150 |

## Code Definition

```typescript
// InboxPurchaseWizard.tsx
const PACKAGE_TEMPLATES = {
  starter: {
    name: 'Starter Package',
    description: '37 domains, 699 inboxes',
    entraPackages: 6,
    googlePackages: 5,
    entraDomains: 12,
    entraInboxes: 624,
    googleDomains: 25,
    googleInboxes: 75,
    totalDomains: 37,
    totalInboxes: 699,
  },
  growth: {
    name: 'Growth Package',
    description: '74 domains, 1398 inboxes',
    entraPackages: 12,
    googlePackages: 10,
    entraDomains: 24,
    entraInboxes: 1248,
    googleDomains: 50,
    googleInboxes: 150,
    totalDomains: 74,
    totalInboxes: 1398,
  },
};
```

## HyperTide Order Specs

| Provider | Domains/Order | Inboxes/Domain | Inboxes/Order | Cost/Order |
|----------|---------------|----------------|---------------|------------|
| Entra | 2 | 52 | 104 | $50/month |
| Google | 5 | 3 | 15 | $50/month |

## Formulas

```
Entra Domains = entra_packages × 2
Entra Inboxes = entra_packages × 2 × 52
Google Domains = google_packages × 5
Google Inboxes = google_packages × 5 × 3
Total Domains = Entra Domains + Google Domains
Total Inboxes = Entra Inboxes + Google Inboxes
Monthly Cost = (entra_packages + google_packages) × $50
```

## Future: Subscription Table (Phase 6B)

Planned database schema for client subscriptions:

```sql
CREATE TABLE client_subscriptions (
    id UUID PRIMARY KEY,
    client_id UUID REFERENCES clients(id),

    -- Package configuration
    entra_packages INTEGER DEFAULT 6,
    google_packages INTEGER DEFAULT 5,

    -- Quotas (computed)
    entra_quota INTEGER GENERATED ALWAYS AS (entra_packages * 2 * 52),
    google_quota INTEGER GENERATED ALWAYS AS (google_packages * 5 * 3),

    -- Status
    status VARCHAR(20) DEFAULT 'active',
    started_at TIMESTAMP DEFAULT NOW(),

    -- Tracking
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Related

- [[infrastructure-hub]] - Parent hub
- [[inbox-provisioning]] - How packages are consumed
- [[project-status]] - Phase 6B planning
