# Infrastructure Provisioning SPA - Complete Implementation Roadmap

**Date:** 2026-02-25
**Purpose:** Step-by-step implementation guide with file checklist and development phases

---

## 📋 Executive Summary

**What:** Waterfall-style infrastructure provisioning SPA for bulk domain/inbox setup
**Timeline:** 4 weeks (17 development days)
**Code Reuse:** 80% from existing codebase
**Database Impact:** 5 new columns, 1 view, 2 constraints

---

## 🗂️ Documentation Index

All design documents are in `/charm-email-os/docs/`:

1. **INFRASTRUCTURE-PROVISIONING-SPA-V2.md** (47KB)
   - Complete waterfall specification with corrected DNS flow
   - 9-stage column definitions
   - HyperTide limitations documented
   - Business logic and requirements

2. **INFRASTRUCTURE-PROVISIONING-MINIMAL-CHANGES.md** (19KB)
   - Database schema analysis
   - Only 5 new fields needed (DNS record booleans)
   - Migration SQL scripts
   - Waterfall view query

3. **INFRASTRUCTURE-PROVISIONING-EXISTING-CODE-ANALYSIS.md** (27KB)
   - 80% reusable component patterns identified
   - ProcurementTab, DomainCandidatesTable, infrastructureStore analysis
   - Polling, selection, lazy loading patterns

4. **INFRASTRUCTURE-PROVISIONING-MODULAR-DESIGN.md** (26KB)
   - Component breakdown (cells, modals, hooks)
   - Single-responsibility architecture
   - File structure and organization

5. **INFRASTRUCTURE-PROVISIONING-API-INTEGRATION.md** (THIS DOCUMENT)
   - Complete API layer specification
   - Store integration with Zustand
   - Hook patterns for components
   - Backend requirements

---

## 🏗️ Phase-by-Phase Implementation

### **Phase 1: Foundation (Week 1 - Days 1-3)**

**Goal:** Database, API, and store layer ready

#### Day 1: Database Schema
- [ ] Run migration script from `MINIMAL-CHANGES.md`
- [ ] Add 5 DNS boolean columns to `domains` table
- [ ] Add constraints to `infrastructure_type` and `nameserver_status`
- [ ] Create `v_infrastructure_waterfall` view
- [ ] Test view with existing data

**Files to modify:**
- `supabase/migrations/YYYYMMDD_add_infrastructure_waterfall.sql`

**SQL Script:**
```sql
-- Copy from INFRASTRUCTURE-PROVISIONING-MINIMAL-CHANGES.md lines 233-351
BEGIN;

-- 1. Add DNS record verification flags
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS spf_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dkim_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dmarc_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS mx_configured BOOLEAN DEFAULT FALSE;

-- 2. Add computed column
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS dns_records_configured BOOLEAN
  GENERATED ALWAYS AS (
    COALESCE(spf_configured, FALSE) AND
    COALESCE(dkim_configured, FALSE) AND
    COALESCE(dmarc_configured, FALSE) AND
    COALESCE(mx_configured, FALSE)
  ) STORED;

-- 3. Add constraints
ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_infrastructure_type_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_infrastructure_type_check
  CHECK (infrastructure_type IS NULL OR infrastructure_type IN ('entra', 'google'));

-- 4. Create waterfall view (see full SQL in MINIMAL-CHANGES.md)
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS ...;

COMMIT;
```

**Testing:**
```sql
-- Verify view works
SELECT domain_id, domain_name, current_stage, owned_by_client
FROM v_infrastructure_waterfall
LIMIT 10;
```

---

#### Day 2: Backend API Endpoints

**Goal:** FastAPI endpoints for waterfall operations

**Files to create:**
- `backend/routers/infrastructure.py` (new file)

**Files to modify:**
- `backend/main.py` (add infrastructure router)

**Implementation:**
```python
# backend/routers/infrastructure.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from ..database import get_db
from ..models import InfrastructureWaterfallView

router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])

@router.get("/waterfall/{client_id}")
async def get_waterfall_data(
    client_id: str,
    view: Optional[str] = "all",
    stage: Optional[int] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get complete waterfall view for client"""
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
        "domains": [d.to_dict() for d in domains],
        "total_domains": len(domains),
    }

@router.post("/bulk-price-check")
async def bulk_price_check(
    domain_ids: list[str],
    providers: list[str],
    db: Session = Depends(get_db),
):
    """Check prices for multiple domains"""
    # Implementation: Create background job for bulk price checking
    job_id = create_price_check_job(domain_ids, providers, db)
    return {
        "job_id": job_id,
        "total_domains": len(domain_ids),
        "status": "queued",
    }

# Add remaining endpoints: bulk-purchase, set-nameservers, verify-dns, assign-provider, hypertide-order
```

**Testing:**
```bash
# Test waterfall endpoint
curl http://localhost:8000/api/infrastructure/waterfall/{client_id}

# Test bulk price check
curl -X POST http://localhost:8000/api/infrastructure/bulk-price-check \
  -H "Content-Type: application/json" \
  -d '{"domain_ids": ["..."], "providers": ["porkbun", "dynadot"]}'
```

---

#### Day 3: Frontend API + Store

**Goal:** Extend `infrastructureStore` and `api.ts`

**Files to modify:**
- `charm-email-os/lib/api.ts` (add infrastructureApi section)
- `charm-email-os/lib/types.ts` (add WaterfallDomain type)
- `charm-email-os/lib/stores/infrastructureStore.ts` (extend store)

**Implementation:**

**1. Add to `lib/types.ts`:**
```typescript
// Copy WaterfallDomain interface from API-INTEGRATION.md
export interface WaterfallDomain {
  domainId: string;
  domainName: string;
  clientId: string;
  // ... all 9 stages ...
  currentStage: number;
}

export const WATERFALL_STAGES = [
  { stage: 1, label: 'Generated', shortLabel: 'Gen' },
  { stage: 2, label: 'Priced', shortLabel: 'Price' },
  // ... etc ...
] as const;
```

**2. Add to `lib/api.ts`:**
```typescript
// After domainApi section, add:
export const infrastructureApi = {
  async getWaterfall(
    clientId: string,
    options?: { view?: 'all' | 'owned' | 'new'; stage?: number; provider?: 'entra' | 'google' }
  ): Promise<{ clientId: string; domains: WaterfallDomain[]; totalDomains: number }> {
    const params = new URLSearchParams();
    if (options?.view) params.set('view', options.view);
    if (options?.stage) params.set('stage', options.stage.toString());
    if (options?.provider) params.set('provider', options.provider);

    return fetchApi<{ clientId: string; domains: WaterfallDomain[]; totalDomains: number }>(
      `/api/infrastructure/waterfall/${clientId}?${params.toString()}`
    );
  },

  async bulkPriceCheck(domainIds: string[]): Promise<{ jobId: string; totalDomains: number; status: string }> {
    return fetchApi('/api/infrastructure/bulk-price-check', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds, providers: ['porkbun', 'dynadot'] }),
    });
  },

  // Add remaining methods: bulkPurchase, setNameservers, verifyDNS, assignProvider, createHyperTideOrder
};
```

**3. Extend `lib/stores/infrastructureStore.ts`:**
```typescript
interface InfrastructureStore {
  // Existing fields...
  domains: Domain[];
  inboxes: Inbox[];
  isLoading: boolean;

  // New waterfall fields
  waterfallDomains: WaterfallDomain[];
  waterfallView: 'all' | 'owned' | 'new';
  waterfallStageFilter: number | null;
  selectedDomainIds: Set<string>;
  bulkActionInProgress: boolean;

  // New actions
  fetchWaterfallData: (clientId: string) => Promise<void>;
  setWaterfallView: (view: 'all' | 'owned' | 'new') => void;
  selectDomain: (domainId: string) => void;
  selectAll: () => void;
  bulkPriceCheck: (domainIds: string[]) => Promise<void>;
  bulkPurchase: (domainIds: string[], provider?: 'porkbun' | 'dynadot') => Promise<void>;
  // ... remaining bulk actions
}

export const useInfrastructureStore = create<InfrastructureStore>((set, get) => ({
  // Existing state...
  domains: [],
  inboxes: [],
  isLoading: false,

  // New waterfall state
  waterfallDomains: [],
  waterfallView: 'all',
  waterfallStageFilter: null,
  selectedDomainIds: new Set(),
  bulkActionInProgress: false,

  fetchWaterfallData: async (clientId) => {
    set({ isLoading: true, error: null });
    try {
      const { view, waterfallStageFilter } = get();
      const response = await infrastructureApi.getWaterfall(clientId, {
        view,
        stage: waterfallStageFilter ?? undefined,
      });
      set({ waterfallDomains: response.domains, isLoading: false });
    } catch (error) {
      set({ error: (error as Error).message, isLoading: false });
    }
  },

  // ... implement remaining actions from API-INTEGRATION.md
}));
```

**Testing:**
```typescript
// Test in browser console
const store = useInfrastructureStore.getState();
await store.fetchWaterfallData('client-id-here');
console.log(store.waterfallDomains);
```

---

### **Phase 2: Core Components (Week 2 - Days 4-8)**

**Goal:** Build reusable waterfall components

#### Day 4-5: Base Components

**Files to create:**
- `components/infrastructure/WaterfallTable/WaterfallTable.tsx`
- `components/infrastructure/WaterfallTable/WaterfallHeader.tsx`
- `components/infrastructure/WaterfallTable/WaterfallRow.tsx`
- `components/infrastructure/WaterfallTable/WaterfallCell.tsx`
- `components/infrastructure/WaterfallTable/index.ts`
- `hooks/infrastructure/useWaterfallData.ts`
- `hooks/infrastructure/useSelection.ts`

**Implementation:**

**1. Create `hooks/infrastructure/useWaterfallData.ts`:**
```typescript
// Copy full implementation from API-INTEGRATION.md
import { useEffect } from 'react';
import { useInfrastructureStore } from '@/lib/stores/infrastructureStore';

export function useWaterfallData(clientId: string) {
  const {
    waterfallDomains,
    waterfallView,
    selectedDomainIds,
    isLoading,
    error,
    fetchWaterfallData,
    setWaterfallView,
    selectDomain,
    selectAll,
    clearSelection,
  } = useInfrastructureStore();

  useEffect(() => {
    if (clientId) {
      fetchWaterfallData(clientId);
    }
  }, [clientId, fetchWaterfallData]);

  const getDomainsByStage = (stage: number) => {
    return waterfallDomains.filter(d => d.currentStage === stage);
  };

  return {
    domains: waterfallDomains,
    isLoading,
    error,
    currentView: waterfallView,
    setView: setWaterfallView,
    selectedDomainIds,
    selectDomain,
    selectAll,
    clearSelection,
    getDomainsByStage,
  };
}
```

**2. Create `components/infrastructure/WaterfallTable/WaterfallTable.tsx`:**
```typescript
import { useWaterfallData } from '@/hooks/infrastructure/useWaterfallData';
import { WaterfallHeader } from './WaterfallHeader';
import { WaterfallRow } from './WaterfallRow';
import { WATERFALL_STAGES } from '@/lib/types';

interface WaterfallTableProps {
  clientId: string;
}

export function WaterfallTable({ clientId }: WaterfallTableProps) {
  const { domains, isLoading, getDomainsByStage } = useWaterfallData(clientId);

  if (isLoading) {
    return <div>Loading waterfall data...</div>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-collapse">
        <WaterfallHeader />
        <tbody>
          {domains.map(domain => (
            <WaterfallRow key={domain.domainId} domain={domain} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

**3. Create `components/infrastructure/WaterfallTable/WaterfallHeader.tsx`:**
```typescript
import { WATERFALL_STAGES } from '@/lib/types';
import { useBulkActions } from '@/hooks/infrastructure/useBulkActions';
import { Button } from '@/components/ui/button';

export function WaterfallHeader() {
  const { selectedCount, handleBulkPriceCheck, handleBulkPurchase } = useBulkActions();

  return (
    <thead>
      <tr>
        <th className="border p-2">
          <input type="checkbox" />
        </th>
        {WATERFALL_STAGES.map(stage => (
          <th key={stage.stage} className="border p-2 min-w-[200px]">
            <div className="flex flex-col gap-2">
              <span className="font-semibold">{stage.label}</span>
              {stage.stage === 2 && (
                <Button
                  size="sm"
                  onClick={handleBulkPriceCheck}
                  disabled={selectedCount === 0}
                >
                  Check Prices ({selectedCount})
                </Button>
              )}
              {stage.stage === 3 && (
                <Button
                  size="sm"
                  onClick={handleBulkPurchase}
                  disabled={selectedCount === 0}
                >
                  Purchase ({selectedCount})
                </Button>
              )}
              {/* Add more bulk action buttons for other stages */}
            </div>
          </th>
        ))}
      </tr>
    </thead>
  );
}
```

**4. Create `components/infrastructure/WaterfallTable/WaterfallRow.tsx`:**
```typescript
import { WaterfallDomain } from '@/lib/types';
import { GeneratedCell } from '../cells/GeneratedCell';
import { PricedCell } from '../cells/PricedCell';
// Import remaining cells...

interface WaterfallRowProps {
  domain: WaterfallDomain;
}

export function WaterfallRow({ domain }: WaterfallRowProps) {
  const { selectDomain, selectedDomainIds } = useWaterfallData(domain.clientId);

  return (
    <tr>
      <td className="border p-2">
        <input
          type="checkbox"
          checked={selectedDomainIds.has(domain.domainId)}
          onChange={() => selectDomain(domain.domainId)}
        />
      </td>
      <td className="border p-2">
        <GeneratedCell domain={domain} />
      </td>
      <td className="border p-2">
        <PricedCell domain={domain} />
      </td>
      {/* Render remaining 7 cells */}
    </tr>
  );
}
```

**Testing:**
- Create test page at `app/test/waterfall/page.tsx`
- Verify table renders with client data
- Test checkbox selection
- Test view filters

---

#### Day 6-8: Stage Cells

**Goal:** Build 9 stage-specific cell components

**Files to create:**
- `components/infrastructure/cells/GeneratedCell/GeneratedCell.tsx`
- `components/infrastructure/cells/GeneratedCell/useGeneratedCell.ts`
- `components/infrastructure/cells/GeneratedCell/index.ts`
- (Repeat for all 9 cells: Priced, Purchased, DNSMoved, DNSVerified, ProviderAssigned, HyperTideOrdered, Provisioned, Synced)

**Example: GeneratedCell:**
```typescript
// components/infrastructure/cells/GeneratedCell/GeneratedCell.tsx
import { WaterfallDomain } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';

interface GeneratedCellProps {
  domain: WaterfallDomain;
}

export function GeneratedCell({ domain }: GeneratedCellProps) {
  if (domain.currentStage < 1) {
    return <div className="text-gray-400">Not generated</div>;
  }

  return (
    <div className="space-y-1">
      <div className="font-medium text-sm">{domain.domainName}</div>

      <div className="flex gap-1 flex-wrap">
        {domain.ownedByClient && (
          <Badge variant="outline" className="text-xs bg-green-50">
            Owned ✓
          </Badge>
        )}
        {domain.deployedToProduction && (
          <Badge variant="outline" className="text-xs bg-blue-50">
            Deployed ✓
          </Badge>
        )}
      </div>

      {domain.legitimacyScore && (
        <div className="text-xs text-gray-500">
          Score: {(domain.legitimacyScore * 100).toFixed(0)}%
        </div>
      )}

      <div className="text-xs text-gray-400">
        {formatDistanceToNow(new Date(domain.generatedAt), { addSuffix: true })}
      </div>
    </div>
  );
}
```

**Example: PricedCell:**
```typescript
// components/infrastructure/cells/PricedCell/PricedCell.tsx
import { WaterfallDomain } from '@/lib/types';
import { Badge } from '@/components/ui/badge';
import { DollarSign } from 'lucide-react';

interface PricedCellProps {
  domain: WaterfallDomain;
}

export function PricedCell({ domain }: PricedCellProps) {
  if (domain.currentStage < 2) {
    return <div className="text-gray-400">Not priced</div>;
  }

  const getPriceStatusColor = () => {
    switch (domain.priceStatus) {
      case 'valid': return 'bg-green-100 text-green-800';
      case 'stale': return 'bg-yellow-100 text-yellow-800';
      case 'unavailable': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  return (
    <div className="space-y-2">
      {domain.cachedPrice && (
        <div className="flex items-center gap-1">
          <DollarSign className="w-4 h-4 text-green-600" />
          <span className="font-medium">${domain.cachedPrice.toFixed(2)}</span>
          {domain.selectedProvider && (
            <Badge variant="outline" className="text-xs">
              {domain.selectedProvider}
            </Badge>
          )}
        </div>
      )}

      <Badge className={`text-xs ${getPriceStatusColor()}`}>
        {domain.priceStatus.replace('_', ' ')}
      </Badge>

      {domain.priceStatus === 'stale' && (
        <div className="text-xs text-yellow-600">
          Price check needed
        </div>
      )}
    </div>
  );
}
```

**Repeat for remaining 7 cells** using patterns from `MODULAR-DESIGN.md`.

**Testing:**
- Test each cell renders correctly for different data states
- Test empty states (currentStage < required stage)
- Test badges and status colors
- Test action buttons within cells

---

### **Phase 3: Modals & Bulk Actions (Week 3 - Days 9-13)**

**Goal:** Build bulk action modals and integrate with store

#### Day 9-10: Bulk Action Hook

**File to create:**
- `hooks/infrastructure/useBulkActions.ts`

**Implementation:**
```typescript
// Copy full implementation from API-INTEGRATION.md
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

  // Implement remaining bulk action handlers...

  return {
    selectedCount: selectedDomainIds.size,
    isProcessing: bulkActionInProgress,
    handleBulkPriceCheck,
    handleBulkPurchase,
    handleBulkSetNameservers,
    handleBulkVerifyDNS,
    handleAssignProvider,
  };
}
```

---

#### Day 11-13: Bulk Action Modals

**Files to create:**
- `components/infrastructure/modals/BulkPriceCheckModal.tsx`
- `components/infrastructure/modals/BulkPurchaseModal.tsx`
- `components/infrastructure/modals/BulkDNSSetModal.tsx`
- `components/infrastructure/modals/DNSVerificationModal.tsx`
- `components/infrastructure/modals/ProviderAssignmentModal.tsx`
- `components/infrastructure/modals/HyperTideOrderModal.tsx`

**Example: BulkPurchaseModal:**
```typescript
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useState } from 'react';
import { WaterfallDomain } from '@/lib/types';

interface BulkPurchaseModalProps {
  domains: WaterfallDomain[];
  onClose: () => void;
  onConfirm: (provider?: 'porkbun' | 'dynadot') => Promise<void>;
}

export function BulkPurchaseModal({ domains, onClose, onConfirm }: BulkPurchaseModalProps) {
  const [purchasing, setPurchasing] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<'porkbun' | 'dynadot' | undefined>();

  const totalCost = domains.reduce((sum, d) => sum + (d.cachedPrice || 0), 0);

  const handlePurchase = async () => {
    setPurchasing(true);
    try {
      await onConfirm(selectedProvider);
      onClose();
    } catch (error) {
      // Error handled by useBulkActions
    } finally {
      setPurchasing(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Purchase {domains.length} Domains</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="p-4 bg-blue-50 rounded-lg">
            <div className="text-sm font-medium">Total Cost</div>
            <div className="text-2xl font-bold">${totalCost.toFixed(2)}</div>
          </div>

          <div>
            <label className="text-sm font-medium">Provider</label>
            <select
              className="w-full border rounded p-2"
              value={selectedProvider || ''}
              onChange={(e) => setSelectedProvider(e.target.value as 'porkbun' | 'dynadot')}
            >
              <option value="">Auto-select lowest price</option>
              <option value="porkbun">Porkbun</option>
              <option value="dynadot">Dynadot</option>
            </select>
          </div>

          <div className="max-h-64 overflow-y-auto">
            <table className="w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left">Domain</th>
                  <th className="text-right">Price</th>
                </tr>
              </thead>
              <tbody>
                {domains.map(d => (
                  <tr key={d.domainId}>
                    <td>{d.domainName}</td>
                    <td className="text-right">${d.cachedPrice?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={purchasing}>
            Cancel
          </Button>
          <Button onClick={handlePurchase} disabled={purchasing}>
            {purchasing ? 'Purchasing...' : 'Purchase All'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

**Repeat for remaining 5 modals** using patterns from `MODULAR-DESIGN.md`.

**Testing:**
- Test modal opens with selected domains
- Test provider selection
- Test cost calculations
- Test error handling
- Test loading states during purchase

---

### **Phase 4: Integration & Polish (Week 4 - Days 14-17)**

**Goal:** Final integration, testing, and UX polish

#### Day 14: Main Page Integration

**File to create:**
- `app/(authenticated)/infrastructure/page.tsx`

**Implementation:**
```typescript
'use client';

import { useState } from 'react';
import { WaterfallTable } from '@/components/infrastructure/WaterfallTable';
import { ClientSelector } from '@/components/ui/client-selector';
import { Button } from '@/components/ui/button';
import { useInfrastructureStore } from '@/lib/stores/infrastructureStore';

export default function InfrastructurePage() {
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null);
  const { waterfallView, setWaterfallView } = useInfrastructureStore();

  return (
    <div className="container mx-auto p-6">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Infrastructure Provisioning</h1>

        <div className="flex gap-4">
          {/* View filters */}
          <div className="flex gap-2">
            <Button
              variant={waterfallView === 'all' ? 'default' : 'outline'}
              onClick={() => setWaterfallView('all')}
            >
              All Domains
            </Button>
            <Button
              variant={waterfallView === 'owned' ? 'default' : 'outline'}
              onClick={() => setWaterfallView('owned')}
            >
              Owned
            </Button>
            <Button
              variant={waterfallView === 'new' ? 'default' : 'outline'}
              onClick={() => setWaterfallView('new')}
            >
              New
            </Button>
          </div>

          {/* Client selector */}
          <ClientSelector
            value={selectedClientId}
            onChange={setSelectedClientId}
          />
        </div>
      </div>

      {selectedClientId ? (
        <WaterfallTable clientId={selectedClientId} />
      ) : (
        <div className="text-center text-gray-500 py-12">
          Select a client to view infrastructure
        </div>
      )}
    </div>
  );
}
```

---

#### Day 15: Job Polling & Status Updates

**Goal:** Implement real-time job status polling

**Files to modify:**
- `lib/stores/infrastructureStore.ts` (add polling logic)

**Implementation:**
```typescript
// Add to infrastructureStore.ts

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

// Use in bulk actions
bulkPurchase: async (domainIds, provider) => {
  set({ bulkActionInProgress: true, error: null });
  try {
    const response = await infrastructureApi.bulkPurchase(domainIds, provider);
    set({ bulkActionJobId: response.jobId });

    // Poll until completed
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
```

---

#### Day 16: Testing & Bug Fixes

**Testing Checklist:**

- [ ] **Selection**
  - [ ] Single domain selection
  - [ ] Select all domains
  - [ ] Clear selection
  - [ ] Selection persists across view changes

- [ ] **Bulk Actions**
  - [ ] Bulk price check (2+ domains)
  - [ ] Bulk purchase (2+ domains)
  - [ ] Bulk DNS set (2+ domains)
  - [ ] Bulk DNS verify (2+ domains)
  - [ ] Provider assignment (Entra vs Google)
  - [ ] HyperTide order (grouped domains)

- [ ] **Waterfall Flow**
  - [ ] Domain moves through stages correctly
  - [ ] Stage badges update in real-time
  - [ ] Owned/deployed badges show correctly
  - [ ] Current stage calculation correct

- [ ] **Filters**
  - [ ] View filter (all/owned/new)
  - [ ] Stage filter (1-9)
  - [ ] Provider filter (entra/google)

- [ ] **Error Handling**
  - [ ] API errors show toast notifications
  - [ ] Loading states show during operations
  - [ ] Job timeouts handled gracefully
  - [ ] Network errors handled

---

#### Day 17: UX Polish & Documentation

**UX Improvements:**
- [ ] Add loading skeletons for cells
- [ ] Add empty states for each stage
- [ ] Add tooltips for action buttons
- [ ] Add keyboard shortcuts (Cmd+A for select all)
- [ ] Add export to CSV functionality
- [ ] Add search/filter within table

**Documentation:**
- [ ] Add README to `components/infrastructure/`
- [ ] Document bulk action workflows
- [ ] Create user guide for operations team
- [ ] Add JSDoc comments to all hooks
- [ ] Create troubleshooting guide

---

## 📦 Deployment Checklist

### Pre-Deployment
- [ ] All tests passing
- [ ] Database migration tested on staging
- [ ] Backend API deployed and tested
- [ ] Frontend build successful
- [ ] Environment variables configured

### Deployment Steps
1. [ ] Run database migration on production
2. [ ] Deploy backend API
3. [ ] Deploy frontend
4. [ ] Verify waterfall view loads
5. [ ] Test bulk price check (1 domain)
6. [ ] Monitor logs for errors

### Post-Deployment
- [ ] Train operations team on new UI
- [ ] Monitor error rates
- [ ] Collect user feedback
- [ ] Create runbook for common issues

---

## 🎯 Success Metrics

**Week 1:**
- [ ] Database migration complete
- [ ] Waterfall view returns data
- [ ] Store integration tested

**Week 2:**
- [ ] All 9 stage cells rendering
- [ ] Selection working
- [ ] Filters working

**Week 3:**
- [ ] All bulk actions functional
- [ ] Modals polished
- [ ] Job polling working

**Week 4:**
- [ ] Full integration tested
- [ ] Operations team trained
- [ ] Deployed to production

---

## 📚 Reference Documents

| Document | Purpose | Size |
|----------|---------|------|
| INFRASTRUCTURE-PROVISIONING-SPA-V2.md | Complete spec + corrected DNS flow | 47KB |
| INFRASTRUCTURE-PROVISIONING-MINIMAL-CHANGES.md | Database schema (5 new fields) | 19KB |
| INFRASTRUCTURE-PROVISIONING-EXISTING-CODE-ANALYSIS.md | 80% reusable patterns | 27KB |
| INFRASTRUCTURE-PROVISIONING-MODULAR-DESIGN.md | Component architecture | 26KB |
| INFRASTRUCTURE-PROVISIONING-API-INTEGRATION.md | API layer + store integration | 45KB |

---

## 🚀 Quick Start Commands

```bash
# Phase 1: Database
cd /home/claw/charm-email-os
supabase db push

# Phase 1: Backend
cd backend
uvicorn main:app --reload

# Phase 1: Frontend
cd charm-email-os
npm run dev

# Test waterfall endpoint
curl http://localhost:8000/api/infrastructure/waterfall/{client-id}

# Test frontend page
open http://localhost:3000/infrastructure
```

---

**This roadmap provides complete step-by-step implementation instructions. Follow phases sequentially for a 4-week delivery timeline.**
