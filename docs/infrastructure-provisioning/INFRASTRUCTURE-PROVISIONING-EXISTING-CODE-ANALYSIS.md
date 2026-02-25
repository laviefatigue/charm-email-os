# Infrastructure Provisioning SPA - Existing Code Analysis

**Date:** 2026-02-25
**Purpose:** Analyze what's already built and what can be reused for the waterfall-style Infrastructure Provisioning SPA

---

## ✅ EXISTING COMPONENTS (Can Reuse)

### 1. **ProcurementTab.tsx** - Solid Foundation ⭐⭐⭐⭐⭐

**Location:** `charm-email-os/components/inboxes/tabs/ProcurementTab.tsx`

**What It Does:**
- Domain generation with auto-fill package capacity
- Bulk price checking across Porkbun + Dynadot
- Candidate domain management
- Purchased domain tracking
- Inbox provisioning modal

**Reusable Features:**
- ✅ Domain generation API integration (`domainSourcingApi.createGenerationJob`)
- ✅ Polling pattern for background jobs (every 3s with 2min timeout)
- ✅ Auto-trigger bulk price check after generation
- ✅ Accordion UI for domain sections
- ✅ Subscription/package capacity awareness

**Code to Reuse:**
```typescript
// Domain generation with package fill
const job = await domainSourcingApi.createGenerationJob(clientId, 10, true);

// Poll for job completion
const pollInterval = setInterval(async () => {
  const status = await domainSourcingApi.getJobStatus(jobId);
  if (status.status === 'completed') {
    clearInterval(pollInterval);
    await onRefreshDomains();
  }
}, 3000);

// Auto-trigger bulk price check
await domainSourcingApi.checkPricesBulk({ clientId });
```

**What's Missing for Waterfall:**
- ❌ No DNS verification stage
- ❌ No provider assignment (Entra vs Google)
- ❌ No HyperTide order creation
- ❌ No provisioning status tracking
- ❌ No waterfall table layout (uses accordion instead)

---

### 2. **DomainCandidatesTable.tsx** - Table Foundation ⭐⭐⭐⭐

**Location:** `charm-email-os/components/purchasing/DomainCandidatesTable.tsx`

**What It Does:**
- Table display of domain candidates
- Checkbox selection for bulk operations
- Dual-provider pricing (Porkbun + Dynadot)
- Sorting (by status, price, name)
- TLD filtering
- Bulk price checking
- Bulk purchasing

**Reusable Features:**
- ✅ Table structure with checkboxes
- ✅ Bulk selection state management (`Set<string>`)
- ✅ Price hydration from database cache
- ✅ Sorting logic
- ✅ Filter system (TLD filter)
- ✅ Per-domain action states (`Record<string, ActionState>`)
- ✅ Dual-provider price display

**Code to Reuse:**
```typescript
// Selection management
const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());

// Bulk select all
const handleSelectAll = () => {
  if (selectedDomains.size === domains.length) {
    setSelectedDomains(new Set());
  } else {
    setSelectedDomains(new Set(domains.map(d => d.id)));
  }
};

// Per-domain action states
const [actionStates, setActionStates] = useState<Record<string, ActionState>>({});

// Price hydration from DB
useEffect(() => {
  const initialPrices = {};
  domains.forEach((d) => {
    if (d.cachedPrice || d.porkbunPrice || d.dynadotPrice) {
      initialPrices[d.id] = {
        price: d.cachedPrice ? String(d.cachedPrice) : '',
        available: d.porkbunAvailable || d.dynadotAvailable || false,
        porkbun: { available: d.porkbunAvailable, price: d.porkbunPrice },
        dynadot: { available: d.dynadotAvailable, price: d.dynadotPrice },
        bestProvider: d.selectedProvider,
      };
    }
  });
  setPrices(initialPrices);
}, [domains]);

// Sorting
const sortedDomains = useMemo(() => {
  return [...domains].sort((a, b) => {
    if (sortBy === 'price') {
      const priceA = parseFloat(prices[a.id]?.price || '999');
      const priceB = parseFloat(prices[b.id]?.price || '999');
      return priceA - priceB;
    }
    return a.domainName.localeCompare(b.domainName);
  });
}, [domains, sortBy, prices]);
```

**What's Missing for Waterfall:**
- ❌ No multi-stage columns (only shows candidates)
- ❌ No DNS verification column
- ❌ No provider assignment column
- ❌ No HyperTide order column
- ❌ No provisioning/synced columns
- ❌ Vertical layout (not waterfall/horizontal flow)

---

### 3. **infrastructureStore.ts** - State Management ⭐⭐⭐⭐

**Location:** `charm-email-os/lib/stores/infrastructureStore.ts`

**What It Does:**
- Zustand store for domains and inboxes
- Lazy loading with tracking (`loadingDomainIds`, `fetchedDomainIds`)
- Client-scoped fetching
- Domain-scoped inbox fetching
- Pagination support (100 per page, safety max 10 pages)

**Reusable Features:**
- ✅ Lazy loading pattern for domain expansion
- ✅ Loading state tracking per domain
- ✅ Client filtering (`getDomainsByClient`)
- ✅ Status filtering (`getApprovedDomainsByClient`)
- ✅ API integration layer
- ✅ Optimistic updates (`updateDomainLocal`)

**Code to Reuse:**
```typescript
// Lazy load inboxes when domain expanded
fetchInboxesForDomainLazy: async (domainId, clientId) => {
  const state = get();
  if (state.fetchedDomainIds.has(domainId) || state.loadingDomainIds.has(domainId)) {
    return; // Skip if already fetched or loading
  }

  set((state) => ({
    loadingDomainIds: new Set([...state.loadingDomainIds, domainId]),
  }));

  const data = await api.domains.getInboxes(domainId, { pageSize: 100 });

  set((state) => {
    const newLoadingIds = new Set(state.loadingDomainIds);
    newLoadingIds.delete(domainId);
    const newFetchedIds = new Set([...state.fetchedDomainIds, domainId]);
    return { loadingDomainIds: newLoadingIds, fetchedDomainIds: newFetchedIds };
  });
};

// Pagination with safety limit
while (hasMore) {
  const data = await api.domains.list({ clientId, pageSize, page });
  allDomains.push(...data.items);
  hasMore = allDomains.length < data.total;
  page++;
  if (page > 10) break; // Safety: max 1000 domains
}
```

**What's Missing for Waterfall:**
- ❌ No waterfall-specific state (stage tracking)
- ❌ No provider assignment state
- ❌ No DNS verification state
- ❌ No HyperTide order state
- ❌ No bulk action coordination

**Recommendation:** Extend this store or create new `useInfrastructureWaterfallStore`

---

### 4. **API Client (lib/api.ts)** - API Integration ⭐⭐⭐⭐⭐

**Existing API Functions:**
```typescript
domainSourcingApi.createGenerationJob(clientId, count, fillPackage);
domainSourcingApi.getJobStatus(jobId);
domainSourcingApi.checkPricesBulk({ clientId });
api.domains.list({ clientId, pageSize, page });
api.domains.approve(domainId);
api.domains.getInboxes(domainId, { pageSize });
```

**What's Missing (Need to Add):**
- ❌ `api.domains.setNameservers({ domainIds, nameservers })`
- ❌ `api.domains.verifyDNS({ domainIds })`
- ❌ `api.domains.assignProvider({ domainIds, provider })`
- ❌ `api.domains.createHypertideOrder({ domainIds, config })`
- ❌ `api.domains.getHypertideOrderStatus(jobId)`

---

## 🔄 PATTERNS TO REUSE

### Pattern 1: Bulk Action with Progress Modal

**From:** `DomainCandidatesTable.tsx`

```typescript
const [isBulkPurchasing, setIsBulkPurchasing] = useState(false);

const handleBulkPurchase = async () => {
  setIsBulkPurchasing(true);
  try {
    const result = await domainSourcingApi.purchaseBulk({
      clientId,
      domainIds: Array.from(selectedDomains),
    });
    toast.success(`Purchased ${result.successCount} domains`);
  } catch (error) {
    toast.error('Bulk purchase failed');
  } finally {
    setIsBulkPurchasing(false);
  }
};
```

**Adapt for Waterfall:**
- Bulk DNS set
- Bulk DNS verification
- Bulk provider assignment
- Bulk HyperTide order

---

### Pattern 2: Job Polling with Timeout

**From:** `ProcurementTab.tsx`

```typescript
const pollInterval = setInterval(async () => {
  try {
    const status = await api.getJobStatus(jobId);
    if (status.status === 'completed') {
      clearInterval(pollInterval);
      onComplete();
    } else if (status.status === 'failed') {
      clearInterval(pollInterval);
      onError(status.errorMessage);
    }
  } catch {
    // Ignore polling errors
  }
}, 3000);

// Safety timeout after 2 minutes
setTimeout(() => {
  clearInterval(pollInterval);
  onTimeout();
}, 120000);
```

**Adapt for Waterfall:**
- DNS verification polling
- HyperTide order polling
- Provisioning status polling

---

### Pattern 3: Per-Item Action States

**From:** `DomainCandidatesTable.tsx`

```typescript
const [actionStates, setActionStates] = useState<Record<string, ActionState>>({});

const setDomainState = useCallback((domainId: string, state: ActionState) => {
  setActionStates((prev) => ({ ...prev, [domainId]: state }));
}, []);

// Usage
setDomainState(domainId, { loading: true, error: null });
// ... perform action ...
setDomainState(domainId, { loading: false, error: null });
```

**Adapt for Waterfall:**
- Track DNS verification per domain
- Track HyperTide order per domain
- Track provisioning status per domain

---

### Pattern 4: Lazy Loading with Tracking

**From:** `infrastructureStore.ts`

```typescript
const [loadingDomainIds, setLoadingDomainIds] = useState<Set<string>>(new Set());
const [fetchedDomainIds, setFetchedDomainIds] = useState<Set<string>>(new Set());

const fetchLazy = async (domainId: string) => {
  if (fetchedDomainIds.has(domainId) || loadingDomainIds.has(domainId)) {
    return; // Skip if already fetched or loading
  }

  setLoadingDomainIds(new Set([...loadingDomainIds, domainId]));

  try {
    const data = await fetchData(domainId);
    setFetchedDomainIds(new Set([...fetchedDomainIds, domainId]));
  } finally {
    const newSet = new Set(loadingDomainIds);
    newSet.delete(domainId);
    setLoadingDomainIds(newSet);
  }
};
```

**Adapt for Waterfall:**
- Lazy load inboxes on domain row expansion
- Lazy load DNS verification results
- Lazy load HyperTide order details

---

## 🚀 REUSABLE UI COMPONENTS

### From Existing Codebase:

```typescript
// Already available
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion';
import { Loader2, RefreshCw, Filter, ArrowUpDown } from 'lucide-react';
import { toast } from 'sonner';
```

**All UI primitives ready - just compose into waterfall table!**

---

## ❌ WHAT'S MISSING (Need to Build)

### 1. Waterfall Table Layout
**Current:** Vertical accordion with separate tables
**Needed:** Horizontal waterfall with 9 columns

### 2. DNS Verification Components
**Current:** None
**Needed:**
- DNS status cell (Pending/Migrating/Verified/Failed)
- DNS checklist (SPF/DKIM/DMARC/MX)
- Bulk DNS verification action

### 3. Provider Assignment Components
**Current:** None
**Needed:**
- Provider badge (🟦 Entra | 🔴 Google)
- Provider assignment modal
- Bulk provider assignment action

### 4. HyperTide Order Components
**Current:** `InboxProvisionModal` exists but may need updates
**Needed:**
- Order status tracking
- Progress bar for browser automation
- Manual payment warning
- Order tracking modal

### 5. Provisioning Status Components
**Current:** None
**Needed:**
- Provisioning progress cell
- ETA display
- HyperTide polling (no API, manual check)

### 6. Synced Inboxes Components
**Current:** Inbox lists exist but not in waterfall context
**Needed:**
- Synced count display
- Inbox list modal (reuse existing)
- Force sync button

---

## 📊 ARCHITECTURE RECOMMENDATION

### Option 1: Extend Existing ProcurementTab ⭐⭐⭐

**Pros:**
- Reuse 80% of existing code
- Keep existing accordion structure
- Add waterfall view as new tab/mode

**Cons:**
- Accordion not ideal for waterfall visualization
- Hard to see full pipeline at once

---

### Option 2: New Waterfall Page (RECOMMENDED) ⭐⭐⭐⭐⭐

**Pros:**
- Clean slate for waterfall-specific UX
- Can import all reusable patterns
- Better for power users (ops team)
- Separate from client-facing procurement tab

**Cons:**
- More code duplication (but controlled)

**Implementation:**
```
/app/clients/[clientId]/infrastructure-command-center/page.tsx
├── WaterfallTable.tsx (new)
├── cells/
│   ├── GeneratedCell.tsx (reuse from DomainCandidatesTable)
│   ├── PricedCell.tsx (reuse from DomainCandidatesTable)
│   ├── PurchasedCell.tsx (new)
│   ├── DNSMovedCell.tsx (new)
│   ├── DNSVerifiedCell.tsx (new)
│   ├── ProviderAssignedCell.tsx (new)
│   ├── HyperTideOrderedCell.tsx (new)
│   ├── ProvisionedCell.tsx (new)
│   └── SyncedCell.tsx (new)
├── modals/
│   ├── BulkPriceCheckModal.tsx (adapt from existing)
│   ├── BulkPurchaseModal.tsx (adapt from existing)
│   ├── DNSVerificationModal.tsx (new)
│   ├── ProviderAssignmentModal.tsx (new)
│   ├── HyperTideOrderModal.tsx (adapt InboxProvisionModal)
│   └── OrderTrackingModal.tsx (new)
└── hooks/
    ├── useWaterfallData.ts (new, based on infrastructureStore patterns)
    ├── useBulkActions.ts (new, based on DomainCandidatesTable patterns)
    ├── useSelection.ts (reuse pattern from DomainCandidatesTable)
    └── usePolling.ts (reuse pattern from ProcurementTab)
```

---

## 🎯 CODE REUSE PLAN

### Phase 1: Foundation (Reuse 90%)
```typescript
// 1. Copy table structure
import { Table, Checkbox, Badge } from existing;

// 2. Copy selection logic
const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());
// ... from DomainCandidatesTable

// 3. Copy polling pattern
const pollInterval = setInterval(...);
// ... from ProcurementTab

// 4. Copy lazy loading
const [loadingDomainIds, fetchedDomainIds] = useState<Set<string>>(new Set());
// ... from infrastructureStore
```

### Phase 2: New Cells (Build 50%, Adapt 50%)
```typescript
// Reuse existing:
- GeneratedCell (from DomainCandidatesTable domain name display)
- PricedCell (from DomainCandidatesTable price display)

// Build new:
- DNSMovedCell (new logic)
- DNSVerifiedCell (new logic)
- ProviderAssignedCell (new logic)
- HyperTideOrderedCell (adapt InboxProvisionModal)
- ProvisionedCell (new logic)
- SyncedCell (new logic)
```

### Phase 3: Bulk Actions (Adapt 80%)
```typescript
// Adapt from DomainCandidatesTable:
const handleBulkAction = async () => {
  setIsLoading(true);
  try {
    await api.bulkAction({ domainIds: Array.from(selectedDomains) });
    toast.success('Success');
  } finally {
    setIsLoading(false);
  }
};
```

---

## 📝 MIGRATION CHECKLIST

### From Existing Code:
- [x] Table structure (DomainCandidatesTable)
- [x] Checkbox selection (DomainCandidatesTable)
- [x] Bulk action pattern (DomainCandidatesTable)
- [x] Polling pattern (ProcurementTab)
- [x] Lazy loading pattern (infrastructureStore)
- [x] Price hydration (DomainCandidatesTable)
- [x] Sorting logic (DomainCandidatesTable)
- [x] Filter system (DomainCandidatesTable TLD filter)

### New Code Needed:
- [ ] 9-column waterfall layout
- [ ] DNS verification cells + modal
- [ ] Provider assignment cells + modal
- [ ] HyperTide order tracking cells + modal
- [ ] Provisioning status cells
- [ ] Synced inboxes cells
- [ ] View switcher (Owned/Candidates/Pipeline/All)
- [ ] Waterfall-specific store (or extend existing)

---

## 💡 KEY INSIGHTS

### 1. **80% of Infrastructure Exists** ✅
The codebase already has:
- Domain management (generation, pricing, purchasing)
- Inbox management (provisioning, listing)
- Bulk actions framework
- Polling/async job patterns
- State management patterns
- UI component library

### 2. **20% is Waterfall-Specific** 🆕
What's missing:
- Multi-stage horizontal layout
- DNS verification workflow
- Provider assignment workflow
- HyperTide order creation (exists but needs updates)
- Provisioning status tracking
- Stage-based filtering/views

### 3. **Reuse Patterns, Not Just Code** 🎯
Focus on reusing:
- Selection pattern (`Set<string>`)
- Polling pattern (interval + timeout)
- Lazy loading pattern (track loaded/loading)
- Bulk action pattern (loading state + toast)
- Per-item state pattern (`Record<id, state>`)

### 4. **Separate Page is Better** 🏗️
Create new `/infrastructure-command-center` page instead of modifying ProcurementTab:
- Cleaner code
- Better UX for waterfall visualization
- Can reference existing components
- Easier to test independently

---

## 🚀 NEXT STEPS

1. **Review existing components** with team
2. **Decide:** Extend ProcurementTab OR create new page (recommend new page)
3. **Extract reusable hooks:**
   - `useSelection.ts` from DomainCandidatesTable
   - `usePolling.ts` from ProcurementTab
   - `useLazyLoading.ts` from infrastructureStore
4. **Build new API endpoints** (DNS verification, provider assignment, etc.)
5. **Build waterfall table** using extracted patterns
6. **Build new cells** for missing stages

**Estimated Development Time:**
- Phase 1 (Reuse existing): 1 week
- Phase 2 (Build new cells): 2 weeks
- Phase 3 (Integration + polish): 1 week
- **Total: 4 weeks** (vs 6 weeks building from scratch)

---

**Conclusion:** We can save 2 weeks by reusing existing patterns and components. Focus on waterfall-specific UX as the differentiator.
