# Infrastructure Provisioning SPA - User Guide

**Complete guide for using the Infrastructure Provisioning single-page application.**

---

## Overview

The Infrastructure Provisioning SPA provides a unified view of all client email infrastructure, including:
- Domain inventory and lifecycle status
- Inbox provisioning through HyperTide
- Package capacity tracking
- Health monitoring

**URL:** `http://localhost:3000/infrastructure`

---

## Quick Start

1. Select a client from the dropdown
2. View infrastructure summary (Microsoft Entra + Google Workspace)
3. Use filters to find specific domains
4. Generate new domains with "Generate Domains" button
5. Check prices with "Check X Prices" button
6. Take bulk actions (purchase domains, create HyperTide orders)

---

## Infrastructure Summary Header

The header displays real-time metrics for each provider (Microsoft Entra and Google Workspace).

### Provider Cards

Each provider card shows four key metrics:

#### 1. DOMAINS (Actual / Expected)

| Value | Meaning |
|-------|---------|
| Actual | Total provisioned domains (with at least 1 inbox) |
| Expected | Domains expected based on HyperTide orders placed |

**Calculation:**
```
orderCount = ceil(actualDomains / domainsPerOrder)
expectedDomains = orderCount × domainsPerOrder
```

**Example (Entra):**
- 12 domains ÷ 2 per order = 6 orders
- 6 orders × 2 = 12 expected
- Display: **12/12**

**Health Indicators:**
- "All healthy" - No domains flagged or dead
- "X at risk" - X domains flagged (warning state)
- "X dead" - X domains with all inboxes killed

#### 2. INBOXES (Live / Total)

| Value | Meaning |
|-------|---------|
| Live | Currently active, sending inboxes |
| Total | All inboxes (live + dead) |

**Sub-indicators:**
- Green wifi icon: X live
- Red wifi-off icon: X dead

#### 3. DAILY CAPACITY

Estimated daily sending volume based on live inboxes.

**Calculation:**
```
dailyCapacity = liveInboxes × emailsPerDayPerInbox
```

**Provider Rates:**
| Provider | Emails/Day/Inbox | Rationale |
|----------|------------------|-----------|
| Microsoft Entra | 2.5 | Conservative (2-3 avg) |
| Google Workspace | 17.5 | Higher volume (15-20 avg) |

**Example:**
- Entra: 607 inboxes × 2.5 = **1,518/day**
- Google: 74 inboxes × 17.5 = **1,295/day**

Also shows monthly estimate: `~dailyCapacity × 30`

#### 4. ORDERS (Used / Required)

Tracks HyperTide order utilization against client package.

| Value | Meaning |
|-------|---------|
| Used | Actual HyperTide orders placed (domains ÷ domainsPerOrder) |
| Required | Orders required by client's assigned package |

**Status Indicators:**
- "At capacity" - Orders match package requirements
- "X available" - Room for more orders
- "X over limit" - Exceeded package allocation

**HyperTide Order Configuration:**
| Provider | Domains/Order | Inboxes/Domain | Total Inboxes/Order |
|----------|---------------|----------------|---------------------|
| Entra | 2 | 50 | 100 |
| Google | 5 | 3 | 15 |

### Domain Health Bar

Visual progress bar showing domain health distribution:
- Green: Healthy domains
- Amber: Flagged/at-risk domains
- Red: Dead domains

Percentage shown: `(healthyDomains / actualDomains) × 100`

---

## Client Packages

Packages define the infrastructure requirements for each client.

### Package Templates

| Package | Entra Orders | Google Orders | Total Domains | Total Inboxes |
|---------|--------------|---------------|---------------|---------------|
| **Starter** | 6 | 5 | 37 | 699 |
| **Growth** | 12 | 10 | 74 | 1,398 |

### Package Assignment

Each client is assigned a package which determines:
1. Required HyperTide orders per provider
2. Expected infrastructure capacity
3. "Over limit" warnings when exceeded

**Database Table:** `client_subscriptions`
- `package_template_id` - Links to package template
- `entra_packages` - Required Entra orders
- `google_packages` - Required Google orders

---

## Domain Waterfall Table

The main table displays all domains in a 6-column waterfall layout.

### Columns

| Column | Description |
|--------|-------------|
| **Domain** | Domain name, TLD badge, source indicator |
| **Price & Purchase** | Registrar prices, purchase status |
| **DNS** | Nameserver configuration status |
| **Provider** | Entra or Google assignment |
| **HyperTide** | Inbox provisioning status |
| **Status** | Live/Flagged/Dead with inbox counts |

### Domain Lifecycle Priority

Domains are sorted by lifecycle priority (most actionable first):

| Priority | State | Description |
|----------|-------|-------------|
| 1 | Live (Healthy) | Purchased, inboxes active |
| 2 | Live (Flagged) | At-risk, needs attention |
| 3 | Ready for HyperTide | Purchased, DNS ready, no inboxes |
| 4 | DNS Pending | Purchased, awaiting DNS propagation |
| 5 | Ready to Buy | Has price, not purchased |
| 6 | Not Priced | Domain idea, needs pricing |
| 98 | Deactivated | All inboxes dead |
| 99 | Over Budget | Price > $15 |

### Domain Source Indicators

| Source | Badge | Meaning |
|--------|-------|---------|
| Legacy | Purple "External" | Pre-existing domain, externally purchased |
| Generated | Blue "Generated" | AI-generated domain name |

### Filter Options

| Filter | Options |
|--------|---------|
| Purchase Status | All / Purchased / Not Purchased |
| TLD | All / .com / .co / .info |
| Provider | All / Entra / Google |
| Status | All / Live / Flagged / Dead |

**Toggle Filters:**
- `>$15` - Show over-budget domains (default: hidden)
- `Deactivated` - Show dead domains (default: hidden)

---

## Status Definitions

### Domain Status

| Status | Meaning | Visual |
|--------|---------|--------|
| **Live** | At least 1 active inbox | Green badge |
| **Flagged** | Warning state, domain at risk | Amber badge |
| **Dead** | All inboxes killed, deprecated | Red badge |

### DNS Status

| Status | Meaning |
|--------|---------|
| **Pending** | Awaiting nameserver update |
| **Propagating** | DNS changes propagating |
| **Ready** | DNS verified, ready for HyperTide |
| **Mismatch** | Nameservers incorrect |
| **Failed** | DNS configuration failed |

### HyperTide Status

| Status | Meaning |
|--------|---------|
| **Not Ordered** | No HyperTide order placed |
| **Ordered** | Order submitted, awaiting processing |
| **Provisioning** | Inboxes being created |
| **Complete** | All inboxes provisioned |
| **Failed** | Provisioning error |

---

## Bulk Actions

### Quick Actions Bar

Located below the filters, shows available bulk actions:

| Button | Description |
|--------|-------------|
| **Generate Domains** | Generate new AI-powered domain names for the client |
| **Check X Prices** | Fetch prices for unpriced domains (two-phase: Dynadot first, then Porkbun) |
| **Select X for Purchase** | Select all purchasable domains (both prices available, under budget) |
| **X Entra Orders** | Create HyperTide orders for Entra-ready domains |
| **X Google Order** | Create HyperTide orders for Google-ready domains |

### Two-Phase Pricing

Domain prices are fetched in two phases for optimal user experience:

1. **Phase 1: Dynadot** (fast, no rate limits)
   - Prices appear immediately
   - Shows "Dynadot: $X.XX"

2. **Phase 2: Porkbun** (rate-limited, 10 seconds per domain)
   - Shows "Porkbun: checking..." with spinner while loading
   - Shows "Waiting for Porkbun price..." indicator

**Important:** The "Buy" button only appears when BOTH registrar prices are available. This ensures the cheapest option is always selected. The cheaper registrar is highlighted with a green checkmark.

### Unsupported TLDs

Some TLDs are not supported by all registrars:
- `.co` - Not available on Porkbun
- `.info` - Limited Porkbun support

These domains will show Dynadot pricing only and cannot be purchased until manually verified.

### Domain Selection

- Checkbox per row for individual selection
- "Select All" checkbox in header for visible domains
- Selection persists across filter changes

### Purchase Flow

1. Select unpurchased domains (under $15 budget)
2. Click "Buy Selected" button
3. Review purchase preview modal
4. Confirm to initiate bulk purchase job

### HyperTide Order Flow

1. Select domains ready for HyperTide
2. Click "Create Order" on provider card
3. Review order preview (domains, inboxes, cost)
4. Confirm to submit order

---

## Troubleshooting

### Metrics Not Updating

1. Click "Refresh" button
2. Check API connection (localhost:8000)
3. Verify Docker containers are running

### Domains Missing

1. Check filter settings
2. Enable ">$15" toggle for over-budget domains
3. Enable "Deactivated" toggle for dead domains

### Package Shows "Over Limit"

Client infrastructure exceeds their assigned package. Options:
1. Upgrade client to larger package (Starter → Growth)
2. Update `client_subscriptions` with correct order counts

---

## Technical Reference

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/infrastructure/waterfall/client/{id}` | Full waterfall data |
| `GET /api/clients` | Client list |
| `POST /api/infrastructure/purchase` | Bulk domain purchase |
| `POST /api/infrastructure/hypertide/order` | Create HyperTide order |
| `POST /api/infrastructure/hypertide-order/test` | Validate HyperTide order (no charge) |
| `POST /api/infrastructure/bulk-price-check` | Two-phase bulk price check |

### Key Files

| File | Purpose |
|------|---------|
| `app/infrastructure/page.tsx` | Main SPA page |
| `components/infrastructure/InfraSummaryHeader.tsx` | Provider metrics cards |
| `components/infrastructure/WaterfallTable.tsx` | Domain table |
| `lib/stores/waterfallStore.ts` | Zustand state management |
| `lib/types/infrastructure.ts` | TypeScript types |

### Database Tables

| Table | Purpose |
|-------|---------|
| `domains` | Domain inventory |
| `sender_accounts` | Inbox records |
| `client_subscriptions` | Package assignments |
| `package_templates` | Starter/Growth definitions |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0 | 2026-02-26 | Two-phase pricing (Dynadot first, Porkbun second) |
| 1.5 | 2026-02-26 | Added Generate Domains button with loading feedback |
| 1.4 | 2026-02-26 | Added Check Prices button with progress indicator |
| 1.3 | 2026-02-25 | Fixed DAILY CAPACITY email rates |
| 1.2 | 2026-02-25 | Fixed ORDERS to use package requirements |
| 1.1 | 2026-02-25 | Fixed DOMAINS to show actual/expected |
| 1.0 | 2026-02-25 | Initial implementation |
