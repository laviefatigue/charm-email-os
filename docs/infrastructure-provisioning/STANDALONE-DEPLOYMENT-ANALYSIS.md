# Infrastructure Provisioning SPA - Standalone Deployment Analysis

**Date**: 2026-02-26
**Status**: Ready for extraction with minor fixes
**Target**: Coolify deployment as standalone app

---

## Executive Summary

The `/infrastructure` page is a complete single-page application for managing email infrastructure provisioning. It can be deployed as a standalone app separate from the main Charm Email OS frontend. The backend API and database are already working locally and will be reused.

---

## 1. What the Infrastructure Page Does

### Core Functionality
- **Domain Generation**: AI-powered domain name generation for cold email
- **Price Checking**: Multi-registrar pricing (Porkbun, Dynadot)
- **Domain Purchase**: Bulk purchase with automatic nameserver configuration
- **HyperTide Orders**: Create inbox provisioning orders (Entra/Google)
- **Status Tracking**: Live/Flagged/Dead domain status with connection monitoring

### User Flow
```
Generate Domains → Check Prices → Purchase Domains → DNS Auto-Config → Create HyperTide Order → Monitor Status
```

---

## 2. API Endpoints - Complete Status

### Endpoints Used by Frontend (All Exist ✅)

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/infrastructure/waterfall/client/{id}` | GET | Get domain waterfall data | ✅ Working |
| `/api/infrastructure/waterfall/workspace/{id}` | GET | Alt: by workspace | ✅ Working |
| `/api/infrastructure/bulk-price-check` | POST | Check registrar prices | ✅ Working |
| `/api/infrastructure/bulk-purchase` | POST | Purchase domains | ✅ Working |
| `/api/infrastructure/hypertide-order` | POST | Create HyperTide order | ✅ Working |
| `/api/infrastructure/hypertide-order/test` | POST | Validate order (dry run) | ✅ Working |
| `/api/infrastructure/sender-names/client/{id}` | GET | Get sender names | ✅ Working |
| `/api/infrastructure/generate-domains/simple` | POST | Generate domain names | ✅ Working |
| `/api/infrastructure/verify-dns/{id}` | POST | Verify DNS config | ✅ Working |

### Endpoints Defined in Frontend But NOT Used in UI

| Endpoint | Method | Why Not Needed |
|----------|--------|----------------|
| `/api/infrastructure/set-nameservers` | POST | Auto-set at purchase time |
| `/api/infrastructure/assign-provider` | POST | Auto-set at HyperTide order |

These are vestigial - the workflows handle them automatically.

---

## 3. Automatic Workflows (No Manual Steps Required)

### Domain Purchase Flow
```
User clicks "Purchase"
  → API creates domain_purchase_job
  → hypertide_worker picks up job
  → Registrar API purchases domain
  → Nameservers AUTO-SET to DNSimple ✅
  → DNS status updated to "propagating"
```

### HyperTide Order Flow
```
User clicks "Create Order"
  → API creates inbox_purchase_job
  → Provider (Entra/Google) AUTO-ASSIGNED ✅
  → hypertide_worker processes order
  → Inboxes provisioned in EmailBison
  → Sync worker updates inbox counts
```

### Key Auto-Configurations
| Action | When | Code Location |
|--------|------|---------------|
| Nameservers → DNSimple | At domain purchase | `domain_sourcing.py:2050` |
| Provider assignment | At HyperTide order | `infrastructure.py:1074-1082` |
| DNS record setup | Via DNSimple API | External service |

---

## 4. Data Flow & Sources

### Where Data Comes From

| Data | Source | Table/View |
|------|--------|------------|
| Domain list | PostgreSQL | `domains` table |
| Inbox counts | PostgreSQL | `v_domain_capacity` view |
| Connection status | PostgreSQL | `sender_accounts.status` |
| Package limits | PostgreSQL | `client_subscriptions` |
| Sender names | PostgreSQL | `clients.onboarding_data.baseSenderNames` |
| Prices | External API | Porkbun/Dynadot (live) |

### Key Database Views
- `v_domain_capacity` - Domain-level inbox aggregation
- `v_client_capacity` - Client-level package vs actual
- `v_infrastructure_waterfall` - Combined waterfall data

---

## 5. Frontend Dependencies

### Files Required for Standalone

```
app/
  infrastructure/
    page.tsx                    # Main page (636 lines)

components/
  infrastructure/
    BulkPurchaseModal.tsx       # Purchase confirmation
    HyperTideOrderModal.tsx     # Order creation modal
    InfraFilterBar.tsx          # Filters (purchase, TLD, provider, status)
    InfraSummaryHeader.tsx      # Current Infrastructure cards
    WaterfallTable.tsx          # Main domain table
    cells/
      DomainCell.tsx            # Domain name + TLD badge
      PricingCell.tsx           # Registrar prices
      DNSCell.tsx               # DNS status
      HyperTideCell.tsx         # Provisioning status
      ProviderCell.tsx          # Entra/Google badge
      StatusCell.tsx            # Live/Flagged/Dead + connection
    index.ts

  ui/                           # shadcn/ui components
    button.tsx
    select.tsx
    switch.tsx
    label.tsx
    checkbox.tsx
    badge.tsx
    progress.tsx
    dialog.tsx

lib/
  api.ts                        # API client (needs trimming)
  utils.ts                      # cn() utility
  stores/
    waterfallStore.ts           # Zustand store (415 lines)
  types/
    infrastructure.ts           # TypeScript types (363 lines)
    index.ts                    # Base types (Client, etc.)
```

### External Dependencies (package.json)
```json
{
  "dependencies": {
    "next": "^16.1.1",
    "react": "^19.0.0",
    "zustand": "^5.0.0",
    "lucide-react": "^0.460.0",
    "date-fns": "^4.1.0",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.0",
    "tailwind-merge": "^2.5.0",
    "@radix-ui/react-select": "^2.1.0",
    "@radix-ui/react-switch": "^1.1.0",
    "@radix-ui/react-dialog": "^1.1.0",
    "@radix-ui/react-checkbox": "^1.1.0",
    "@radix-ui/react-label": "^2.1.0"
  }
}
```

---

## 6. Current Infrastructure Metrics Fix (Completed)

### Problem Solved
The "Current Infrastructure" summary was counting inboxes from ALL domains including dead ones.

### Fix Applied
Modified `api/routes/infrastructure.py` → `get_client_infra_summary()`:
- Now filters by domain status (`live`, `flagged` only)
- Dead domains excluded from inbox counts
- Daily capacity only counts connected inboxes from live domains

### Before/After (Charm Entra)
| Metric | Before | After |
|--------|--------|-------|
| Inboxes | 0/149 | 0/51 |
| Disconnected | 149 | 51 |
| Dead | 5 | 0 |

---

## 7. Gaps & Considerations

### Not Blocking Deployment

| Gap | Impact | Workaround |
|-----|--------|------------|
| No package assignment UI | Can't set client packages | Use API directly or seed DB |
| No sender names UI | Can't configure names | Set in `clients.onboarding_data` |
| No HyperTide domain sourcing | Must use own domains | Use domain generator (works) |

### Requires Configuration (Per Client)

1. **Package Assignment**: Set in `client_subscriptions` table
   ```sql
   INSERT INTO client_subscriptions (client_id, entra_packages, google_packages, ...)
   ```

2. **Sender Names**: Set in `clients.onboarding_data`
   ```json
   {
     "baseSenderNames": [
       {"firstName": "Alex", "lastName": "Morgan"},
       {"firstName": "Jordan", "lastName": "Smith"}
     ],
     "primaryDomain": "client.com"
   }
   ```

### TypeScript Build Error (Needs Fix)

Location: `lib/api.ts:937`
```typescript
// Current (broken):
generatedDomains: response.generated.map(d => ({
  domainName: d.domain_name,
  legitimacyScore: d.legitimacy_score,
  rationale: 'Pattern-based generation',
})),

// Missing fields: id, baseName, tld
```

Fix required before deployment.

---

## 8. Deployment Options

### Option A: Extract as New Standalone App
- Create fresh Next.js project
- Copy only required files (listed above)
- Clean, minimal deployment
- **Effort**: ~1 hour

### Option B: Deploy Full Frontend, Route Only
- Deploy existing charm-email-os container
- Configure Coolify to only expose `/infrastructure`
- Fix TypeScript error first
- **Effort**: ~10 minutes + fix

### Recommended: Option A
Cleaner separation, no unused code, easier maintenance.

---

## 9. Coolify Deployment Config

### Environment Variables Required

```env
# API Connection
NEXT_PUBLIC_API_URL=https://charm-api.your-domain.com

# Optional
NODE_ENV=production
```

### Dockerfile (exists at charm-email-os/Dockerfile)
- Multi-stage build
- Node 20 Alpine base
- Standalone output mode
- Health check included

### API Requirements
The API container needs:
```env
POSTGRES_HOST=your-postgres-host
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
POSTGRES_DB=postgres
```

---

## 10. Testing Checklist

Before deployment, verify:

- [ ] API health check passes
- [ ] `/infrastructure` loads without errors
- [ ] Client dropdown populates
- [ ] Waterfall table loads data
- [ ] Current Infrastructure shows correct metrics
- [ ] "Generate Domains" button works
- [ ] "Check Prices" button works
- [ ] Bulk purchase modal opens
- [ ] HyperTide order modal opens
- [ ] Filters work (purchase status, TLD, provider, status)
- [ ] "Needs Reconnection" filter works

---

## 11. Files Modified in This Session

### API Changes
- `api/routes/infrastructure.py` - Fixed Current Infrastructure metrics to exclude dead domains

### Frontend Changes (Committed)
- `charm-email-os/app/infrastructure/page.tsx`
- `charm-email-os/components/infrastructure/*` (all files)
- `charm-email-os/lib/stores/waterfallStore.ts`
- `charm-email-os/lib/types/infrastructure.ts`

### Git Status
- Committed as: `fix: Current Infrastructure metrics now show live domains only`
- Branch: `master` (20 commits ahead of origin)
- Not yet pushed to remote

---

## 12. Next Steps

1. **Fix TypeScript error** in `lib/api.ts:937`
2. **Choose deployment option** (A or B)
3. **Push to origin** for CI/CD
4. **Configure Coolify** with API URL
5. **Test end-to-end** in production

---

## Appendix: Key Code Locations

| Component | File | Lines |
|-----------|------|-------|
| Main Page | `app/infrastructure/page.tsx` | 636 |
| Zustand Store | `lib/stores/waterfallStore.ts` | 415 |
| Types | `lib/types/infrastructure.ts` | 363 |
| API Summary | `api/routes/infrastructure.py:438-663` | get_client_infra_summary |
| Waterfall Query | `api/routes/infrastructure.py:686-870` | get_waterfall_by_client |
| HyperTide Order | `api/routes/infrastructure.py:1020-1102` | create_hypertide_order |
| Domain Purchase | `api/routes/infrastructure.py:920-1018` | bulk_purchase |
