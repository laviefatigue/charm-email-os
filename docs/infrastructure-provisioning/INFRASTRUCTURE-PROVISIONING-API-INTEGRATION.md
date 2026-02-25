# Infrastructure Provisioning SPA - API Integration Layer

**Date:** 2026-02-25
**Purpose:** Complete API integration specification for Infrastructure Provisioning waterfall SPA

---

## Overview

This document defines the **complete API layer** for the Infrastructure Provisioning SPA, including:

1. **Existing API endpoints** to reuse from `lib/api.ts`
2. **New API endpoints** needed for waterfall operations
3. **Store integration** with `infrastructureStore.ts`
4. **Type definitions** for waterfall-specific data
5. **Hook patterns** for components

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     React Components                             │
│  (WaterfallTable, GeneratedCell, PricedCell, etc.)              │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ↓ useInfrastructureStore()
┌─────────────────────────────────────────────────────────────────┐
│              Infrastructure Store (Zustand)                      │
│  • Client state management (domains, inboxes, loading)           │
│  • Lazy loading tracking (fetchedDomainIds, loadingDomainIds)   │
│  • Optimistic updates                                            │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ↓ api.infrastructure.*
┌─────────────────────────────────────────────────────────────────┐
│                   API Service Layer                              │
│  • Domain operations (list, generate, purchase, approve)         │
│  • Inbox operations (list, generate, approve)                    │
│  • Waterfall operations (bulk actions, status tracking)          │
│  • Job polling (purchase jobs, DNS verification)                 │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    ↓ HTTP/REST
┌─────────────────────────────────────────────────────────────────┐
│              FastAPI Backend + PostgreSQL                        │
│  • /api/domains, /api/inboxes, /api/infrastructure              │
│  • Writes to domains/inboxes tables                              │
│  • Reads from v_infrastructure_waterfall view                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Existing API Endpoints (Already Implemented)

From `/charm-email-os/lib/api.ts`:

### Domain Operations

```typescript
// List domains with pagination
api.domains.list({
  clientId: string,
  pageSize?: number,
  page?: number
}): Promise<PaginatedResponse<Domain>>

// Generate domains using AI
api.domains.generate(
  clientId: string,
  primaryDomain: string,
  count: number
): Promise<{ message: string; domain?: Domain }>

// Approve domain for purchase
api.domains.approve(domainId: string): Promise<Domain>

// Get inboxes for domain (lazy loading)
api.domains.getInboxes(
  domainId: string,
  { pageSize?: number }
): Promise<PaginatedResponse<Inbox>>
```

### Inbox Operations

```typescript
// List inboxes with filters
api.inboxes.list({
  clientId?: string,
  domainId?: string,
  pageSize?: number
}): Promise<PaginatedResponse<Inbox>>

// Generate inboxes for domain
api.inboxes.generate(
  clientId: string,
  domainId: string,
  firstNames: string[],
  count: number
): Promise<{ message: string; inboxes?: Inbox[] }>

// Approve inbox for provisioning
api.inboxes.approve(inboxId: string): Promise<Inbox>
```

### Purchase Jobs (HyperTide Tracking)

```typescript
// Get purchase job status
api.purchaseJobs.get(jobId: string): Promise<{
  id: string;
  status: 'pending' | 'executing' | 'failed' | 'completed';
  current_step: string;
  provider_type: 'entra' | 'google';
  created_at: Date;
  completed_at?: Date;
}>

// Poll job until completed
api.purchaseJobs.poll(
  jobId: string,
  intervalMs?: number,
  timeoutMs?: number
): Promise<PurchaseJob>
```

---

## New API Endpoints (Need to Implement)

### Infrastructure Waterfall Endpoints

#### 1. **Get Waterfall Data**

Fetch complete waterfall view for a client.

**Endpoint:** `GET /api/infrastructure/waterfall/{clientId}`

**Query Params:**
- `view?: 'all' | 'owned' | 'new'` - Filter records
- `stage?: number` - Filter by current stage (1-9)
- `provider?: 'entra' | 'google'` - Filter by infrastructure type

**Response:**
```typescript
interface WaterfallResponse {
  clientId: string;
  clientName: string;
  domains: WaterfallDomain[];
  totalDomains: number;
  stageBreakdown: {
    stage: number;
    count: number;
    label: string;
  }[];
}

interface WaterfallDomain {
  // Core
  domainId: string;
  domainName: string;
  clientId: string;

  // Stage 1: Generated
  generatedAt: Date;
  legitimacyScore?: number;
  domainSource: 'generated' | 'purchased' | 'legacy';

  // Stage 2: Priced
  priceCheckedAt?: Date;
  cachedPrice?: number;
  selectedProvider?: 'porkbun' | 'dynadot';
  porkbunPrice?: number;
  porkbunAvailable?: boolean;
  dynadotPrice?: number;
  dynadotAvailable?: boolean;
  priceStatus: 'not_checked' | 'valid' | 'stale' | 'unavailable';

  // Stage 3: Purchased
  purchasedAt?: Date;
  purchaseJobId?: string;
  purchaseJobStatus?: string;

  // Stage 4: DNS Moved
  nameserversUpdatedAt?: Date;
  currentNameservers?: string[];
  dnsMigrationStatus: 'not_set' | 'propagating' | 'propagated';

  // Stage 5: DNS Verified
  nameserverStatus?: 'pending' | 'verified' | 'failed';
  nameserverVerifiedAt?: Date;
  spfConfigured: boolean;
  dkimConfigured: boolean;
  dmarcConfigured: boolean;
  mxConfigured: boolean;
  dnsRecordsConfigured: boolean;

  // Stage 6: Provider Assigned
  assignedProvider?: 'entra' | 'google';

  // Stage 7: HyperTide Ordered
  hyperTideOrderJobId?: string;
  hyperTideOrderStatus?: string;
  hyperTideCurrentStep?: string;
  hyperTideProvider?: 'entra' | 'google';

  // Stage 8: Provisioned
  provisioningStatus: 'not_started' | 'provisioning' | 'awaiting_sync' | 'synced';

  // Stage 9: Synced
  syncedInboxCount: number;
  expectedInboxCount: number;
  lastInboxSyncedAt?: Date;

  // Current stage (1-9)
  currentStage: number;

  // Ownership
  ownedByClient: boolean;
  deployedToProduction: boolean;
}
```

**Implementation:**
```typescript
// In lib/api.ts
export const infrastructureApi = {
  async getWaterfall(
    clientId: string,
    options?: {
      view?: 'all' | 'owned' | 'new';
      stage?: number;
      provider?: 'entra' | 'google';
    }
  ): Promise<WaterfallResponse> {
    const params = new URLSearchParams();
    if (options?.view) params.set('view', options.view);
    if (options?.stage) params.set('stage', options.stage.toString());
    if (options?.provider) params.set('provider', options.provider);

    return fetchApi<WaterfallResponse>(
      `/api/infrastructure/waterfall/${clientId}?${params.toString()}`
    );
  },
};
```

---

#### 2. **Bulk Price Check**

Check prices for multiple domains at once.

**Endpoint:** `POST /api/infrastructure/bulk-price-check`

**Request:**
```typescript
interface BulkPriceCheckRequest {
  domainIds: string[];
  providers: ('porkbun' | 'dynadot')[];
}
```

**Response:**
```typescript
interface BulkPriceCheckResponse {
  jobId: string;
  totalDomains: number;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  message: string;
}
```

**Implementation:**
```typescript
async bulkPriceCheck(domainIds: string[]): Promise<BulkPriceCheckResponse> {
  return fetchApi<BulkPriceCheckResponse>(
    '/api/infrastructure/bulk-price-check',
    {
      method: 'POST',
      body: JSON.stringify({
        domain_ids: domainIds,
        providers: ['porkbun', 'dynadot'],
      }),
    }
  );
}
```

---

#### 3. **Bulk Purchase**

Purchase multiple domains at once.

**Endpoint:** `POST /api/infrastructure/bulk-purchase`

**Request:**
```typescript
interface BulkPurchaseRequest {
  domainIds: string[];
  provider?: 'porkbun' | 'dynadot'; // Auto-select lowest if not provided
}
```

**Response:**
```typescript
interface BulkPurchaseResponse {
  jobId: string;
  totalDomains: number;
  totalCost: number;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  message: string;
}
```

**Implementation:**
```typescript
async bulkPurchase(
  domainIds: string[],
  provider?: 'porkbun' | 'dynadot'
): Promise<BulkPurchaseResponse> {
  return fetchApi<BulkPurchaseResponse>(
    '/api/infrastructure/bulk-purchase',
    {
      method: 'POST',
      body: JSON.stringify({
        domain_ids: domainIds,
        provider,
      }),
    }
  );
}
```

---

#### 4. **Set DNS Nameservers**

Change nameservers to DNSimple for HyperTide readiness.

**Endpoint:** `POST /api/infrastructure/set-nameservers`

**Request:**
```typescript
interface SetNameserversRequest {
  domainIds: string[];
  nameservers: string[]; // Default: DNSimple nameservers
}
```

**Response:**
```typescript
interface SetNameserversResponse {
  jobId: string;
  totalDomains: number;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  message: string;
}
```

**Implementation:**
```typescript
async setNameservers(domainIds: string[]): Promise<SetNameserversResponse> {
  return fetchApi<SetNameserversResponse>(
    '/api/infrastructure/set-nameservers',
    {
      method: 'POST',
      body: JSON.stringify({
        domain_ids: domainIds,
        nameservers: [
          'ns1.dnsimple.com',
          'ns2.dnsimple-edge.net',
          'ns3.dnsimple.com',
          'ns4.dnsimple-edge.org',
        ],
      }),
    }
  );
}
```

---

#### 5. **Verify DNS Records**

Check if DNS records (SPF, DKIM, DMARC, MX) are configured.

**Endpoint:** `POST /api/infrastructure/verify-dns`

**Request:**
```typescript
interface VerifyDNSRequest {
  domainIds: string[];
}
```

**Response:**
```typescript
interface VerifyDNSResponse {
  results: {
    domainId: string;
    domainName: string;
    spfConfigured: boolean;
    dkimConfigured: boolean;
    dmarcConfigured: boolean;
    mxConfigured: boolean;
    dnsRecordsConfigured: boolean;
  }[];
  allConfigured: number;
  partiallyConfigured: number;
}
```

**Implementation:**
```typescript
async verifyDNS(domainIds: string[]): Promise<VerifyDNSResponse> {
  return fetchApi<VerifyDNSResponse>(
    '/api/infrastructure/verify-dns',
    {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    }
  );
}
```

---

#### 6. **Assign Provider**

Assign Entra or Google infrastructure type.

**Endpoint:** `POST /api/infrastructure/assign-provider`

**Request:**
```typescript
interface AssignProviderRequest {
  domainIds: string[];
  provider: 'entra' | 'google';
}
```

**Response:**
```typescript
interface AssignProviderResponse {
  updated: number;
  domains: {
    domainId: string;
    domainName: string;
    provider: 'entra' | 'google';
  }[];
}
```

**Implementation:**
```typescript
async assignProvider(
  domainIds: string[],
  provider: 'entra' | 'google'
): Promise<AssignProviderResponse> {
  return fetchApi<AssignProviderResponse>(
    '/api/infrastructure/assign-provider',
    {
      method: 'POST',
      body: JSON.stringify({
        domain_ids: domainIds,
        provider,
      }),
    }
  );
}
```

---

#### 7. **Create HyperTide Order**

Submit order to HyperTide (via Playwright automation).

**Endpoint:** `POST /api/infrastructure/hypertide-order`

**Request:**
```typescript
interface HyperTideOrderRequest {
  clientId: string;
  orderGroups: {
    orderType: 'entra' | 'google';
    domainIds: string[];
    senderNameId: string;
  }[];
  forwardingDomain: string;
  bisonWorkspace: string;
}
```

**Response:**
```typescript
interface HyperTideOrderResponse {
  jobId: string;
  totalOrders: number;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  estimatedDurationSeconds: number;
  message: string;
}
```

**Implementation:**
```typescript
async createHyperTideOrder(
  request: HyperTideOrderRequest
): Promise<HyperTideOrderResponse> {
  return fetchApi<HyperTideOrderResponse>(
    '/api/infrastructure/hypertide-order',
    {
      method: 'POST',
      body: JSON.stringify(toSnakeCase(request)),
    }
  );
}
```

---

## Store Integration (infrastructureStore.ts)

### Extend Existing Store

Add waterfall-specific methods to `useInfrastructureStore`:

```typescript
// In lib/stores/infrastructureStore.ts

interface InfrastructureStore {
  // ... existing fields ...

  // Waterfall data
  waterfallDomains: WaterfallDomain[];
  waterfallView: 'all' | 'owned' | 'new';
  waterfallStageFilter: number | null;
  waterfallProviderFilter: 'entra' | 'google' | null;

  // Selection
  selectedDomainIds: Set<string>;

  // Bulk action tracking
  bulkActionInProgress: boolean;
  bulkActionJobId: string | null;

  // Actions
  fetchWaterfallData: (clientId: string) => Promise<void>;
  setWaterfallView: (view: 'all' | 'owned' | 'new') => void;
  setStageFilter: (stage: number | null) => void;
  setProviderFilter: (provider: 'entra' | 'google' | null) => void;
  selectDomain: (domainId: string) => void;
  selectAll: () => void;
  clearSelection: () => void;

  // Bulk operations
  bulkPriceCheck: (domainIds: string[]) => Promise<void>;
  bulkPurchase: (domainIds: string[], provider?: 'porkbun' | 'dynadot') => Promise<void>;
  bulkSetNameservers: (domainIds: string[]) => Promise<void>;
  bulkVerifyDNS: (domainIds: string[]) => Promise<void>;
  bulkAssignProvider: (domainIds: string[], provider: 'entra' | 'google') => Promise<void>;
  createHyperTideOrder: (request: HyperTideOrderRequest) => Promise<void>;
}
```

### Implementation Example

```typescript
export const useInfrastructureStore = create<InfrastructureStore>((set, get) => ({
  // ... existing state ...

  waterfallDomains: [],
  waterfallView: 'all',
  waterfallStageFilter: null,
  waterfallProviderFilter: null,
  selectedDomainIds: new Set(),
  bulkActionInProgress: false,
  bulkActionJobId: null,

  fetchWaterfallData: async (clientId) => {
    set({ isLoading: true, error: null });
    try {
      const { view, waterfallStageFilter, waterfallProviderFilter } = get();
      const response = await infrastructureApi.getWaterfall(clientId, {
        view,
        stage: waterfallStageFilter ?? undefined,
        provider: waterfallProviderFilter ?? undefined,
      });
      set({
        waterfallDomains: response.domains,
        isLoading: false
      });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  setWaterfallView: (view) => {
    set({ waterfallView: view });
    // Auto-refresh
    const clientId = get().waterfallDomains[0]?.clientId;
    if (clientId) get().fetchWaterfallData(clientId);
  },

  selectDomain: (domainId) => {
    set((state) => {
      const next = new Set(state.selectedDomainIds);
      if (next.has(domainId)) {
        next.delete(domainId);
      } else {
        next.add(domainId);
      }
      return { selectedDomainIds: next };
    });
  },

  selectAll: () => {
    const allIds = get().waterfallDomains.map(d => d.domainId);
    set({ selectedDomainIds: new Set(allIds) });
  },

  clearSelection: () => {
    set({ selectedDomainIds: new Set() });
  },

  bulkPriceCheck: async (domainIds) => {
    set({ bulkActionInProgress: true, error: null });
    try {
      const response = await infrastructureApi.bulkPriceCheck(domainIds);
      set({ bulkActionJobId: response.jobId });

      // Poll for completion
      await pollJob(response.jobId, async (status) => {
        if (status === 'completed') {
          // Refresh waterfall data
          const clientId = get().waterfallDomains[0]?.clientId;
          if (clientId) await get().fetchWaterfallData(clientId);
        }
      });

      set({ bulkActionInProgress: false, bulkActionJobId: null });
    } catch (error) {
      set({
        error: (error as Error).message,
        bulkActionInProgress: false,
        bulkActionJobId: null,
      });
    }
  },

  bulkPurchase: async (domainIds, provider) => {
    set({ bulkActionInProgress: true, error: null });
    try {
      const response = await infrastructureApi.bulkPurchase(domainIds, provider);
      set({ bulkActionJobId: response.jobId });

      await pollJob(response.jobId, async (status) => {
        if (status === 'completed') {
          const clientId = get().waterfallDomains[0]?.clientId;
          if (clientId) await get().fetchWaterfallData(clientId);
        }
      });

      set({ bulkActionInProgress: false, bulkActionJobId: null });
    } catch (error) {
      set({
        error: (error as Error).message,
        bulkActionInProgress: false,
        bulkActionJobId: null,
      });
    }
  },

  // ... other bulk operations follow same pattern ...
}));

// Helper: Generic job polling
async function pollJob(
  jobId: string,
  onComplete: (status: string) => Promise<void>,
  intervalMs = 3000,
  timeoutMs = 120000
): Promise<void> {
  const startTime = Date.now();

  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const job = await api.purchaseJobs.get(jobId);

        if (job.status === 'completed' || job.status === 'failed') {
          clearInterval(interval);
          await onComplete(job.status);
          resolve();
        }

        // Timeout check
        if (Date.now() - startTime > timeoutMs) {
          clearInterval(interval);
          reject(new Error('Job polling timed out'));
        }
      } catch (error) {
        clearInterval(interval);
        reject(error);
      }
    }, intervalMs);
  });
}
```

---

## Hook Patterns for Components

### useWaterfallData

Complete waterfall data hook with selection and filtering.

```typescript
// In hooks/infrastructure/useWaterfallData.ts

import { useEffect } from 'react';
import { useInfrastructureStore } from '@/lib/stores/infrastructureStore';

export function useWaterfallData(clientId: string) {
  const {
    waterfallDomains,
    waterfallView,
    waterfallStageFilter,
    waterfallProviderFilter,
    selectedDomainIds,
    isLoading,
    error,
    fetchWaterfallData,
    setWaterfallView,
    setStageFilter,
    setProviderFilter,
    selectDomain,
    selectAll,
    clearSelection,
  } = useInfrastructureStore();

  useEffect(() => {
    if (clientId) {
      fetchWaterfallData(clientId);
    }
  }, [clientId, fetchWaterfallData]);

  // Filter domains by current stage for column display
  const getDomainsByStage = (stage: number) => {
    return waterfallDomains.filter(d => d.currentStage === stage);
  };

  // Get selected domains from current view
  const getSelectedDomains = () => {
    return waterfallDomains.filter(d => selectedDomainIds.has(d.domainId));
  };

  return {
    // Data
    domains: waterfallDomains,
    isLoading,
    error,

    // Filtering
    currentView: waterfallView,
    stageFilter: waterfallStageFilter,
    providerFilter: waterfallProviderFilter,
    setView: setWaterfallView,
    setStageFilter,
    setProviderFilter,

    // Selection
    selectedDomainIds,
    selectDomain,
    selectAll,
    clearSelection,

    // Helpers
    getDomainsByStage,
    getSelectedDomains,
  };
}
```

---

### useBulkActions

Bulk action operations for column headers.

```typescript
// In hooks/infrastructure/useBulkActions.ts

import { useInfrastructureStore } from '@/lib/stores/infrastructureStore';
import { toast } from 'sonner';

export function useBulkActions() {
  const {
    selectedDomainIds,
    bulkActionInProgress,
    bulkPriceCheck,
    bulkPurchase,
    bulkSetNameservers,
    bulkVerifyDNS,
    bulkAssignProvider,
    createHyperTideOrder,
    clearSelection,
  } = useInfrastructureStore();

  const handleBulkPriceCheck = async () => {
    if (selectedDomainIds.size === 0) {
      toast.error('No domains selected');
      return;
    }

    try {
      await bulkPriceCheck(Array.from(selectedDomainIds));
      toast.success(`Price check started for ${selectedDomainIds.size} domains`);
      clearSelection();
    } catch (error) {
      toast.error(`Price check failed: ${(error as Error).message}`);
    }
  };

  const handleBulkPurchase = async (provider?: 'porkbun' | 'dynadot') => {
    if (selectedDomainIds.size === 0) {
      toast.error('No domains selected');
      return;
    }

    try {
      await bulkPurchase(Array.from(selectedDomainIds), provider);
      toast.success(`Purchase started for ${selectedDomainIds.size} domains`);
      clearSelection();
    } catch (error) {
      toast.error(`Purchase failed: ${(error as Error).message}`);
    }
  };

  const handleBulkSetNameservers = async () => {
    if (selectedDomainIds.size === 0) {
      toast.error('No domains selected');
      return;
    }

    try {
      await bulkSetNameservers(Array.from(selectedDomainIds));
      toast.success(`Nameservers updated for ${selectedDomainIds.size} domains`);
      clearSelection();
    } catch (error) {
      toast.error(`Nameserver update failed: ${(error as Error).message}`);
    }
  };

  const handleBulkVerifyDNS = async () => {
    if (selectedDomainIds.size === 0) {
      toast.error('No domains selected');
      return;
    }

    try {
      await bulkVerifyDNS(Array.from(selectedDomainIds));
      toast.success(`DNS verification started for ${selectedDomainIds.size} domains`);
      clearSelection();
    } catch (error) {
      toast.error(`DNS verification failed: ${(error as Error).message}`);
    }
  };

  const handleAssignProvider = async (provider: 'entra' | 'google') => {
    if (selectedDomainIds.size === 0) {
      toast.error('No domains selected');
      return;
    }

    try {
      await bulkAssignProvider(Array.from(selectedDomainIds), provider);
      toast.success(`Assigned ${provider} to ${selectedDomainIds.size} domains`);
      clearSelection();
    } catch (error) {
      toast.error(`Provider assignment failed: ${(error as Error).message}`);
    }
  };

  return {
    selectedCount: selectedDomainIds.size,
    isProcessing: bulkActionInProgress,

    // Actions
    handleBulkPriceCheck,
    handleBulkPurchase,
    handleBulkSetNameservers,
    handleBulkVerifyDNS,
    handleAssignProvider,
  };
}
```

---

## Backend Implementation Requirements

### FastAPI Endpoints

```python
# /api/infrastructure/waterfall/{client_id}
@router.get("/infrastructure/waterfall/{client_id}")
async def get_waterfall_data(
    client_id: str,
    view: Optional[str] = "all",
    stage: Optional[int] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Get complete waterfall view for client.
    Reads from v_infrastructure_waterfall view.
    """
    query = db.query(InfrastructureWaterfallView).filter_by(workspace_id=client_id)

    if view == "owned":
        query = query.filter_by(owned_by_client=True)
    elif view == "new":
        query = query.filter_by(owned_by_client=False)

    if stage:
        query = query.filter_by(current_stage=stage)

    if provider:
        query = query.filter_by(assigned_provider=provider)

    domains = query.order_by(
        InfrastructureWaterfallView.owned_by_client.desc(),
        InfrastructureWaterfallView.current_stage.desc(),
    ).all()

    return {
        "client_id": client_id,
        "domains": [to_waterfall_domain(d) for d in domains],
        "total_domains": len(domains),
    }
```

---

## Database View (Already Defined)

From `INFRASTRUCTURE-PROVISIONING-MINIMAL-CHANGES.md`:

```sql
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,
    d.created_at as generated_at,
    d.legitimacy_score,
    d.price_checked_at,
    d.cached_price,
    d.purchased_at,
    d.nameservers_updated_at,
    d.nameserver_status,
    COALESCE(d.spf_configured, FALSE) as spf_configured,
    COALESCE(d.dkim_configured, FALSE) as dkim_configured,
    COALESCE(d.dmarc_configured, FALSE) as dmarc_configured,
    COALESCE(d.mx_configured, FALSE) as mx_configured,
    d.infrastructure_type as assigned_provider,
    ipj.status as hypertide_order_status,
    (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id) as synced_inbox_count,
    CASE
        WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id) THEN 9
        WHEN ipj.status = 'completed' THEN 8
        WHEN ipj.id IS NOT NULL THEN 7
        WHEN d.infrastructure_type IS NOT NULL THEN 6
        WHEN d.nameserver_status = 'verified' THEN 5
        WHEN d.nameservers_updated_at IS NOT NULL THEN 4
        WHEN d.purchased_at IS NOT NULL THEN 3
        WHEN d.price_checked_at IS NOT NULL THEN 2
        ELSE 1
    END as current_stage
FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
WHERE d.is_active = TRUE;
```

---

## Type Definitions

Add to `lib/types.ts`:

```typescript
// Waterfall-specific domain view
export interface WaterfallDomain {
  // Core
  domainId: string;
  domainName: string;
  clientId: string;

  // Stage 1: Generated
  generatedAt: Date;
  legitimacyScore?: number;
  domainSource: 'generated' | 'purchased' | 'legacy';

  // Stage 2: Priced
  priceCheckedAt?: Date;
  cachedPrice?: number;
  selectedProvider?: 'porkbun' | 'dynadot';
  porkbunPrice?: number;
  porkbunAvailable?: boolean;
  dynadotPrice?: number;
  dynadotAvailable?: boolean;
  priceStatus: 'not_checked' | 'valid' | 'stale' | 'unavailable';

  // Stage 3: Purchased
  purchasedAt?: Date;
  purchaseJobId?: string;
  purchaseJobStatus?: string;

  // Stage 4: DNS Moved
  nameserversUpdatedAt?: Date;
  currentNameservers?: string[];
  dnsMigrationStatus: 'not_set' | 'propagating' | 'propagated';

  // Stage 5: DNS Verified
  nameserverStatus?: 'pending' | 'verified' | 'failed';
  nameserverVerifiedAt?: Date;
  spfConfigured: boolean;
  dkimConfigured: boolean;
  dmarcConfigured: boolean;
  mxConfigured: boolean;
  dnsRecordsConfigured: boolean;

  // Stage 6: Provider Assigned
  assignedProvider?: 'entra' | 'google';

  // Stage 7: HyperTide Ordered
  hyperTideOrderJobId?: string;
  hyperTideOrderStatus?: string;
  hyperTideCurrentStep?: string;

  // Stage 8: Provisioned
  provisioningStatus: 'not_started' | 'provisioning' | 'awaiting_sync' | 'synced';

  // Stage 9: Synced
  syncedInboxCount: number;
  expectedInboxCount: number;
  lastInboxSyncedAt?: Date;

  // Current stage (1-9)
  currentStage: number;

  // Ownership
  ownedByClient: boolean;
  deployedToProduction: boolean;
}

// Stage labels
export const WATERFALL_STAGES = [
  { stage: 1, label: 'Generated', shortLabel: 'Gen' },
  { stage: 2, label: 'Priced', shortLabel: 'Price' },
  { stage: 3, label: 'Purchased', shortLabel: 'Buy' },
  { stage: 4, label: 'DNS Moved', shortLabel: 'NS Set' },
  { stage: 5, label: 'DNS Verified', shortLabel: 'DNS OK' },
  { stage: 6, label: 'Provider Assigned', shortLabel: 'Provider' },
  { stage: 7, label: 'HyperTide Ordered', shortLabel: 'Ordered' },
  { stage: 8, label: 'Provisioned', shortLabel: 'Provision' },
  { stage: 9, label: 'Synced', shortLabel: 'Synced' },
] as const;
```

---

## Summary

### What's Already Implemented (80%)
✅ Domain list/generate/approve endpoints
✅ Inbox list/generate/approve endpoints
✅ Infrastructure store with lazy loading
✅ Selection patterns from existing code
✅ Polling patterns from existing code
✅ Type definitions for Domain/Inbox

### What Needs Implementation (20%)
❌ Waterfall view endpoint (`/api/infrastructure/waterfall/{clientId}`)
❌ Bulk operation endpoints (price check, purchase, DNS, provider)
❌ HyperTide order endpoint
❌ Store extensions for waterfall operations
❌ Waterfall-specific type definitions
❌ Backend database view (`v_infrastructure_waterfall`)

### Development Priority
1. **Database migration** - Add 5 DNS boolean columns + view (1 hour)
2. **Backend API** - Waterfall endpoint + bulk operations (4 hours)
3. **Store integration** - Extend infrastructureStore (2 hours)
4. **Hooks** - useWaterfallData + useBulkActions (2 hours)
5. **Components** - Waterfall table + cells (8 hours)

**Total Estimate:** 17 hours (2-3 days) for complete API layer + integration

---

**All API operations follow existing patterns from `lib/api.ts` and `infrastructureStore.ts`. No new architectural patterns required.**
