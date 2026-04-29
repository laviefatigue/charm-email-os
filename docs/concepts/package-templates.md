---
title: Package Templates
created: 2026-01-22
updated: 2026-04-28
tags: [concept, subscription, infrastructure, overhaul-2026-04-27]
---

# Package Templates

> **2026-04-27 OVERHAUL — package model changed:**
> - CEO directive: **100% Google going forward.** Microsoft Entra is legacy ride-to-death; no new Entra orders.
> - The Starter/Growth packages described below (which mix Entra + Google) are **historical only** — useful for understanding existing client subscriptions but NOT for new client onboarding.
> - The new model is the `workspace_packages` table (migration 097) — see "Post-Overhaul Package Model" section below.

Pre-defined infrastructure packages that determine domain and inbox quotas for clients.

## Overview

Clients subscribe to packages that define:
- Number of Entra orders (2 domains × 52 inboxes each) — **LEGACY ONLY, no new orders**
- Number of Google orders (5 domains × 3 inboxes each) — **CURRENT MODEL**
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

## Post-Overhaul Package Model (workspace_packages, migration 097)

Effective 2026-04-28. Replaces the Starter/Growth model for new client onboarding.

### Reference table

```sql
CREATE TABLE workspace_packages (
    package_id            VARCHAR PRIMARY KEY,
    package_name          VARCHAR NOT NULL,
    monthly_send_volume   INTEGER NOT NULL,
    target_live_count     INTEGER NOT NULL,
    target_reserve_count  INTEGER NOT NULL,
    description           TEXT
);
```

Seeded values:

| `package_id` | Monthly volume | Live target | Reserve target | Order count |
|---|---|---|---|---|
| `50k_google` | 50,000 sends | **150 inboxes** | **30 inboxes** | 10 live orders + 2 reserve orders |
| `100k_google` | 100,000 sends | **300 inboxes** | **60 inboxes** | 20 live orders + 4 reserve orders |

Each Google order = 5 domains × 3 inboxes/domain = 15 inboxes. Volume math: 50,000 sends ÷ 30 days ÷ 11 sends/inbox/day ≈ 150 inboxes.

### Workspace assignment + override

`workspaces` gained these columns (migration 097):

| Column | Type | Purpose |
|---|---|---|
| `package_id` | VARCHAR FK → workspace_packages | Which package this workspace is on. NULL = no proactive promotion (reactive only via kill_processor). |
| `target_live_count_override` | INTEGER NULL | Operator-controlled lower bound. Can ONLY lower the package target (e.g., ramp-up: set override=current_deployed initially, raise as orders come in). Validated by trigger: `override ≤ package.target_live_count`. |
| `pause_pool_transitions` | BOOLEAN DEFAULT FALSE | Emergency stop — when TRUE, the orchestrator skips this workspace entirely (no graduation, no promotion, no kill). Useful during incidents. |
| `package_assigned_at` | TIMESTAMPTZ | When the package was assigned. |

### Effective targets view

```sql
CREATE VIEW workspace_effective_targets AS
SELECT
    w.id AS workspace_id,
    w.workspace_name,
    w.package_id,
    p.target_live_count AS package_live_target,
    COALESCE(w.target_live_count_override, p.target_live_count) AS effective_live_target,
    p.target_reserve_count AS reserve_target,
    w.pause_pool_transitions
FROM workspaces w
LEFT JOIN workspace_packages p ON p.package_id = w.package_id
WHERE w.is_active = TRUE;
```

The orchestrator's `_maintain_pool_thresholds` reads this view to compute deficit (effective_live_target − current_deployed_count), then calls `pool_promotion.pick_promotion_candidates` to fill it.

### Why override only LOWERS

Operator can ramp up gradually (set override=current_deployed initially, raise as orders come in). Override > package makes no semantic sense — package IS the contract. The trigger enforces this.

### Why no active demotion when override is lowered

Established sender reputation matters. Lowering the override only governs **future promotions**; natural attrition (kills) brings the deployed count down over time without disrupting in-flight inboxes.

### Skip paths

The orchestrator skips threshold maintenance entirely when:
- `package_id IS NULL` (workspace opted out — reactive promotion only)
- `pause_pool_transitions = TRUE` (emergency stop)

In both cases, kill-driven cross-domain promotion still runs.

## Related

- [[infrastructure-hub]] - Parent hub
- [[inbox-provisioning]] - How packages are consumed
- [[project-status]] - Phase 6B planning
- [[../adr/adr-006-tagging-kill-overhaul-2026-04-27]] - Architectural decision record for the overhaul
- [[../work-logs/2026-04-27-tagging-kill-overhaul-plan]] - Full overhaul plan + handoff
