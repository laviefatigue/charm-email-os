# Infrastructure Provisioning SPA

**Unified dashboard for managing client email infrastructure: domains, inboxes, and HyperTide orders.**

---

## Status: IMPLEMENTED

The Infrastructure Provisioning SPA is live and operational.

**Access:** `http://localhost:3000/infrastructure`

---

## What It Does

The SPA provides a single view to:
- Monitor domain and inbox health across all clients
- Track HyperTide order utilization against client packages
- Execute bulk domain purchases
- Create HyperTide provisioning orders
- Filter and sort domains by lifecycle stage

---

## Quick Reference

### Provider Metrics

| Metric | Formula | Example |
|--------|---------|---------|
| **DOMAINS** | actual / expected | 12/12 |
| **INBOXES** | live / total | 607/618 |
| **DAILY CAPACITY** | inboxes × rate | 1,518/day |
| **ORDERS** | used / required | 6/6 |

### Email Rates

| Provider | Emails/Day/Inbox |
|----------|------------------|
| Entra | 2.5 |
| Google | 17.5 |

### HyperTide Orders

| Provider | Domains/Order | Inboxes/Domain |
|----------|---------------|----------------|
| Entra | 2 | 50 |
| Google | 5 | 3 |

### Client Packages

| Package | Entra Orders | Google Orders | Total Domains |
|---------|--------------|---------------|---------------|
| Starter | 6 | 5 | 37 |
| Growth | 12 | 10 | 74 |

---

## Documentation

| Document | Purpose |
|----------|---------|
| **[USER-GUIDE.md](USER-GUIDE.md)** | Complete usage guide with all metrics explained |
| [FRONTEND-DESIGN-CLAY.md](FRONTEND-DESIGN-CLAY.md) | Original design specification |
| [API-INTEGRATION.md](INFRASTRUCTURE-PROVISIONING-API-INTEGRATION.md) | API endpoint documentation |
| [MODULAR-DESIGN.md](INFRASTRUCTURE-PROVISIONING-MODULAR-DESIGN.md) | Component architecture |

---

## Key Files

### Frontend

```
charm-email-os/
├── app/infrastructure/
│   └── page.tsx                    # Main SPA page
├── components/infrastructure/
│   ├── InfraSummaryHeader.tsx      # Provider metrics cards
│   ├── WaterfallTable.tsx          # Domain waterfall table
│   ├── WaterfallFilters.tsx        # Filter controls
│   └── cells/
│       ├── DomainCell.tsx          # Domain name + badges
│       ├── PricingCell.tsx         # Price + purchase status
│       ├── DNSCell.tsx             # DNS configuration
│       ├── ProviderCell.tsx        # Entra/Google assignment
│       ├── HyperTideCell.tsx       # Provisioning status
│       └── StatusCell.tsx          # Live/Flagged/Dead
├── lib/
│   ├── stores/waterfallStore.ts    # Zustand state
│   └── types/infrastructure.ts     # TypeScript types
```

### Backend

```
api/routes/
└── infrastructure.py               # Waterfall API endpoints
```

### Database

```sql
-- Key tables
domains                 -- Domain inventory
sender_accounts         -- Inbox records
client_subscriptions    -- Package assignments
package_templates       -- Starter/Growth definitions
```

---

## Running Locally

### With Docker (Recommended)

```bash
cd charm-email-os
docker-compose -f docker-compose.local.yml up -d
```

Access at: `http://localhost:3000/infrastructure`

### Development Mode

```bash
cd charm-email-os/charm-email-os
npm run dev
```

Access at: `http://localhost:3000/infrastructure`

---

## Troubleshooting

### Container not starting
```bash
docker-compose -f docker-compose.local.yml logs charm-frontend
```

### API errors
```bash
curl http://localhost:8000/health
```

### Database connection
```bash
docker exec charm-postgres psql -U postgres -d postgres -c "\dt"
```

---

## Recent Changes

| Date | Change |
|------|--------|
| 2026-02-26 | **Two-phase pricing**: Dynadot loads first (fast), Porkbun second (rate-limited) |
| 2026-02-26 | **Generate Domains** button with loading feedback |
| 2026-02-26 | **Check Prices** button shows progress (X checked, Y available) |
| 2026-02-26 | **Buy button** only appears when BOTH registrar prices available |
| 2026-02-26 | **HyperTide test endpoint** for order validation without charging |
| 2026-02-25 | Fixed DOMAINS metric to show actual/expected based on orders |
| 2026-02-25 | Fixed ORDERS metric to use client package requirements |
| 2026-02-25 | Fixed DAILY CAPACITY to use correct email rates per provider |
| 2026-02-25 | Added lifecycle priority sorting to domain table |

---

## Contact

For issues or questions, check the main project documentation or open an issue.
