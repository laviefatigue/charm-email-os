# Infrastructure Provisioning SPA - Complete Implementation Plan

**Goal:** Working localhost implementation - "npm run dev" and it works
**Timeline:** 5 days of focused development
**Starting Point:** 73.7% design complete → 100% working code

---

## 🎯 Implementation Strategy

### Phase Breakdown
1. **Day 1:** Fix critical blockers (database, missing tables, API contracts)
2. **Day 2:** Backend API endpoints + job system
3. **Day 3:** Frontend foundation (store, hooks, base components)
4. **Day 4:** All 9 stage cells + modals
5. **Day 5:** Integration testing + polish

---

## DAY 1: Critical Blockers & Foundation (8 hours)

### 1.1 Database Schema Fixes (2 hours)

**Create:** `/supabase/migrations/20260225_infrastructure_waterfall.sql`

```sql
-- ============================================
-- INFRASTRUCTURE WATERFALL MIGRATION
-- ============================================

BEGIN;

-- 1. Add missing tables
-- ============================================

-- sender_names table (CRITICAL - missing from spec)
CREATE TABLE IF NOT EXISTS sender_names (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  first_name VARCHAR(100) NOT NULL,
  last_name VARCHAR(100) NOT NULL,
  full_name VARCHAR(200) GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED,
  email VARCHAR(255),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  is_active BOOLEAN DEFAULT TRUE,
  CONSTRAINT sender_names_workspace_name_unique UNIQUE (workspace_id, first_name, last_name)
);

CREATE INDEX idx_sender_names_workspace ON sender_names(workspace_id) WHERE is_active = TRUE;
CREATE INDEX idx_sender_names_active ON sender_names(is_active, workspace_id);

-- 2. Add DNS tracking fields to domains table
-- ============================================
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS spf_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dkim_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dmarc_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS mx_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dns_records_configured BOOLEAN
    GENERATED ALWAYS AS (
      COALESCE(spf_configured, FALSE) AND
      COALESCE(dkim_configured, FALSE) AND
      COALESCE(dmarc_configured, FALSE) AND
      COALESCE(mx_configured, FALSE)
    ) STORED;

-- 3. Add constraints to existing fields
-- ============================================
ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_infrastructure_type_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_infrastructure_type_check
  CHECK (infrastructure_type IS NULL OR infrastructure_type IN ('entra', 'google'));

ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_nameserver_status_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_nameserver_status_check
  CHECK (nameserver_status IS NULL OR nameserver_status IN ('pending', 'verified', 'failed'));

-- 4. Add missing indexes for performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_domains_waterfall_workspace
  ON domains(workspace_id, approval_status)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_domains_waterfall_stage
  ON domains(workspace_id, purchased_at, nameservers_updated_at, nameserver_status, infrastructure_type)
  WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_domains_provider_dns
  ON domains(infrastructure_type, nameserver_status)
  WHERE is_active = TRUE AND infrastructure_type IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_domains_needs_nameserver
  ON domains(workspace_id)
  WHERE purchased_at IS NOT NULL AND nameservers_updated_at IS NULL AND is_active = TRUE;

-- 5. Enhance inbox_purchase_jobs table
-- ============================================
ALTER TABLE inbox_purchase_jobs
  ADD COLUMN IF NOT EXISTS error_message TEXT,
  ADD COLUMN IF NOT EXISTS error_stack TEXT,
  ADD COLUMN IF NOT EXISTS error_code VARCHAR(50),
  ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_retry_at TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_purchase_jobs_status
  ON inbox_purchase_jobs(status, created_at DESC);

-- 6. Create waterfall view
-- ============================================
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,
    d.created_at as generated_at,
    d.legitimacy_score,

    -- Stage 2: Priced
    d.price_checked_at,
    d.cached_price,
    d.selected_provider,
    d.porkbun_price,
    d.porkbun_available,
    d.dynadot_price,
    d.dynadot_available,
    CASE
        WHEN d.price_checked_at IS NULL THEN 'not_checked'
        WHEN d.price_checked_at < NOW() - INTERVAL '24 hours' THEN 'stale'
        WHEN d.porkbun_available = FALSE AND d.dynadot_available = FALSE THEN 'unavailable'
        ELSE 'valid'
    END as price_status,

    -- Stage 3: Purchased
    d.purchased_at,
    d.purchase_job_id,

    -- Stage 4: DNS Moved
    d.nameservers_updated_at,
    d.current_nameservers,
    CASE
        WHEN d.nameservers_updated_at IS NULL THEN 'not_set'
        WHEN d.nameservers_updated_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
        ELSE 'propagated'
    END as dns_migration_status,

    -- Stage 5: DNS Verified
    d.nameserver_status,
    d.nameserver_verified_at,
    d.spf_configured,
    d.dkim_configured,
    d.dmarc_configured,
    d.mx_configured,
    d.dns_records_configured,

    -- Stage 6: Provider Assigned
    d.infrastructure_type as assigned_provider,

    -- Stage 7-8: HyperTide
    ipj.id as hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.created_at as hypertide_ordered_at,

    -- Stage 9: Synced
    (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id) as synced_inbox_count,
    (SELECT MAX(created_at) FROM sender_accounts sa WHERE sa.domain_id = d.id) as last_inbox_synced_at,

    -- Computed current stage (1-9)
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
    END as current_stage,

    -- Ownership flags
    (d.approval_status = 'owned') as owned_by_client,
    EXISTS(SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id AND sa.is_active = TRUE) as deployed_to_production

FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
WHERE d.is_active = TRUE;

-- Add index on view for filtering
CREATE INDEX IF NOT EXISTS idx_waterfall_view_workspace_stage
  ON domains(workspace_id,
    CASE
        WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = domains.id) THEN 9
        WHEN purchase_job_id IS NOT NULL THEN 7
        WHEN infrastructure_type IS NOT NULL THEN 6
        WHEN nameserver_status = 'verified' THEN 5
        WHEN nameservers_updated_at IS NOT NULL THEN 4
        WHEN purchased_at IS NOT NULL THEN 3
        WHEN price_checked_at IS NOT NULL THEN 2
        ELSE 1
    END)
  WHERE is_active = TRUE;

-- 7. Create domain lifecycle audit log
-- ============================================
CREATE TABLE IF NOT EXISTS domain_lifecycle_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  event_type VARCHAR(50) NOT NULL,
  event_data JSONB DEFAULT '{}'::jsonb,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_lifecycle_events_domain ON domain_lifecycle_events(domain_id, created_at DESC);
CREATE INDEX idx_lifecycle_events_type ON domain_lifecycle_events(event_type, created_at DESC);

COMMIT;
```

**Run migration:**
```bash
cd /home/claw/charm-email-os
supabase db push
```

---

### 1.2 Create Missing API Type Definitions (1 hour)

**Create:** `/charm-email-os/lib/types/infrastructure.ts`

```typescript
// ============================================
// INFRASTRUCTURE WATERFALL TYPES
// ============================================

export interface WaterfallDomain {
  // Core
  domainId: string;
  domainName: string;
  workspaceId: string;

  // Stage 1: Generated
  generatedAt: Date;
  legitimacyScore?: number;
  approvalStatus: string;

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
  hyperTideOrderStatus?: 'pending' | 'executing' | 'completed' | 'failed';
  hyperTideCurrentStep?: string;
  hyperTideOrderedAt?: Date;

  // Stage 8: Provisioned (computed from job status)
  provisioningStatus: 'not_started' | 'provisioning' | 'awaiting_sync' | 'synced';

  // Stage 9: Synced
  syncedInboxCount: number;
  expectedInboxCount: number;
  lastInboxSyncedAt?: Date;

  // Computed
  currentStage: number; // 1-9
  ownedByClient: boolean;
  deployedToProduction: boolean;
}

export interface WaterfallResponse {
  workspaceId: string;
  domains: WaterfallDomain[];
  totalDomains: number;
  stageBreakdown: {
    stage: number;
    count: number;
    label: string;
  }[];
}

export interface HyperTideOrderRequest {
  workspaceId: string;
  orderGroups: {
    orderType: 'entra' | 'google';
    domainIds: string[];
    senderNameId?: string; // Optional - can be null
  }[];
  forwardingDomain: string;
  bisonWorkspace: string;
}

export interface HyperTideOrderResponse {
  jobId: string;
  totalOrders: number;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  estimatedDurationSeconds: number;
  message: string;
}

export interface SenderName {
  id: string;
  workspaceId: string;
  firstName: string;
  lastName: string;
  fullName: string;
  email?: string;
  isActive: boolean;
}

export const WATERFALL_STAGES = [
  { stage: 1, label: 'Generated', shortLabel: 'Gen', description: 'AI-generated domains ready for pricing' },
  { stage: 2, label: 'Priced', shortLabel: 'Price', description: 'Check prices from registrars' },
  { stage: 3, label: 'Purchased', shortLabel: 'Buy', description: 'Buy domains from registrar' },
  { stage: 4, label: 'DNS Moved', shortLabel: 'NS Set', description: 'Nameservers changed to DNSimple' },
  { stage: 5, label: 'DNS Verified', shortLabel: 'DNS OK', description: 'SPF, DKIM, DMARC, MX configured' },
  { stage: 6, label: 'Provider Assigned', shortLabel: 'Provider', description: 'Entra or Google assigned' },
  { stage: 7, label: 'HyperTide Ordered', shortLabel: 'Ordered', description: 'Inbox provisioning order submitted' },
  { stage: 8, label: 'Provisioned', shortLabel: 'Provision', description: 'Inboxes created by HyperTide' },
  { stage: 9, label: 'Synced', shortLabel: 'Synced', description: 'Inboxes synced to EmailBison' },
] as const;
```

**Update:** `/charm-email-os/lib/types/index.ts`

```typescript
// Add to exports
export * from './infrastructure';
```

---

### 1.3 Stub Backend API Endpoints (2 hours)

**Create:** `/backend/routers/infrastructure.py`

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import uuid

from ..database import get_db
from ..auth import get_current_user

router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])

# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class WaterfallDomainResponse(BaseModel):
    domain_id: str
    domain_name: str
    workspace_id: str
    generated_at: datetime
    legitimacy_score: Optional[float]

    # Stage 2
    price_checked_at: Optional[datetime]
    cached_price: Optional[float]
    selected_provider: Optional[str]
    price_status: str

    # Stage 3
    purchased_at: Optional[datetime]
    purchase_job_id: Optional[str]

    # Stage 4
    nameservers_updated_at: Optional[datetime]
    dns_migration_status: str

    # Stage 5
    nameserver_status: Optional[str]
    spf_configured: bool
    dkim_configured: bool
    dmarc_configured: bool
    mx_configured: bool
    dns_records_configured: bool

    # Stage 6
    assigned_provider: Optional[str]

    # Stage 7
    hypertide_order_job_id: Optional[str]
    hypertide_order_status: Optional[str]

    # Stage 9
    synced_inbox_count: int
    current_stage: int
    owned_by_client: bool

class WaterfallResponse(BaseModel):
    workspace_id: str
    domains: List[WaterfallDomainResponse]
    total_domains: int

class BulkActionRequest(BaseModel):
    domain_ids: List[str]

class HyperTideOrderGroupRequest(BaseModel):
    order_type: str  # 'entra' | 'google'
    domain_ids: List[str]
    sender_name_id: Optional[str] = None

class HyperTideOrderRequest(BaseModel):
    workspace_id: str
    order_groups: List[HyperTideOrderGroupRequest]
    forwarding_domain: str
    bison_workspace: str

# ============================================
# ENDPOINTS
# ============================================

@router.get("/waterfall/{workspace_id}")
async def get_waterfall_data(
    workspace_id: str,
    view: Optional[str] = Query("all", enum=["all", "owned", "new"]),
    stage: Optional[int] = Query(None, ge=1, le=9),
    provider: Optional[str] = Query(None, enum=["entra", "google"]),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get complete waterfall view for workspace.
    Reads from v_infrastructure_waterfall view.
    """
    # Build query
    query = f"""
        SELECT * FROM v_infrastructure_waterfall
        WHERE workspace_id = '{workspace_id}'
    """

    if view == "owned":
        query += " AND owned_by_client = TRUE"
    elif view == "new":
        query += " AND owned_by_client = FALSE"

    if stage:
        query += f" AND current_stage = {stage}"

    if provider:
        query += f" AND assigned_provider = '{provider}'"

    query += " ORDER BY owned_by_client DESC, current_stage DESC, generated_at DESC"

    result = db.execute(query)
    domains = [dict(row) for row in result]

    return {
        "workspace_id": workspace_id,
        "domains": domains,
        "total_domains": len(domains)
    }

@router.post("/bulk-price-check")
async def bulk_price_check(
    request: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Bulk price check for multiple domains.
    Creates background job for parallel API calls.
    """
    job_id = str(uuid.uuid4())

    # TODO: Create background job
    # For now, return immediate response

    return {
        "job_id": job_id,
        "total_domains": len(request.domain_ids),
        "status": "queued",
        "message": f"Price check started for {len(request.domain_ids)} domains"
    }

@router.post("/bulk-purchase")
async def bulk_purchase(
    request: BulkActionRequest,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Bulk purchase multiple domains.
    """
    job_id = str(uuid.uuid4())

    # TODO: Create purchase job

    return {
        "job_id": job_id,
        "total_domains": len(request.domain_ids),
        "status": "queued",
        "message": f"Purchase started for {len(request.domain_ids)} domains"
    }

@router.post("/set-nameservers")
async def set_nameservers(
    request: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Set nameservers to DNSimple for multiple domains.
    """
    job_id = str(uuid.uuid4())

    # TODO: Update nameservers

    return {
        "job_id": job_id,
        "total_domains": len(request.domain_ids),
        "status": "queued"
    }

@router.post("/verify-dns")
async def verify_dns(
    request: BulkActionRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Verify DNS records for multiple domains.
    """
    # TODO: Check SPF, DKIM, DMARC, MX records

    return {
        "results": [],
        "all_configured": 0,
        "partially_configured": 0
    }

@router.post("/assign-provider")
async def assign_provider(
    request: BulkActionRequest,
    provider: str = Query(..., enum=["entra", "google"]),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Assign Entra or Google provider to domains.
    """
    # Update infrastructure_type field
    db.execute(f"""
        UPDATE domains
        SET infrastructure_type = '{provider}',
            updated_at = NOW()
        WHERE id = ANY(ARRAY[{','.join([f"'{d}'" for d in request.domain_ids])}])
    """)
    db.commit()

    return {
        "updated": len(request.domain_ids),
        "provider": provider
    }

@router.post("/hypertide-order")
async def create_hypertide_order(
    request: HyperTideOrderRequest,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Submit HyperTide order with workspace configuration.
    """
    # Validate order groups
    for group in request.order_groups:
        if group.order_type == "entra" and len(group.domain_ids) != 2:
            raise HTTPException(400, "Entra orders require exactly 2 domains")
        if group.order_type == "google" and len(group.domain_ids) > 5:
            raise HTTPException(400, "Google orders support max 5 domains")

    job_id = str(uuid.uuid4())

    # TODO: Create inbox_purchase_job record
    # TODO: Trigger Playwright automation

    return {
        "job_id": job_id,
        "total_orders": len(request.order_groups),
        "status": "pending",
        "estimated_duration_seconds": len(request.order_groups) * 7200,  # 2h per order
        "message": f"HyperTide order submitted: {len(request.order_groups)} orders"
    }

@router.get("/sender-names/{workspace_id}")
async def get_sender_names(
    workspace_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get all sender names for workspace.
    """
    result = db.execute(f"""
        SELECT id, workspace_id, first_name, last_name, full_name, email, is_active
        FROM sender_names
        WHERE workspace_id = '{workspace_id}' AND is_active = TRUE
        ORDER BY full_name
    """)

    return {"sender_names": [dict(row) for row in result]}
```

**Add to main.py:**
```python
from .routers import infrastructure

app.include_router(infrastructure.router)
```

---

### 1.4 Update Frontend API Client (1 hour)

**Update:** `/charm-email-os/lib/api.ts`

```typescript
// Add infrastructure API section
export const infrastructureApi = {
  async getWaterfall(
    workspaceId: string,
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
      `/api/infrastructure/waterfall/${workspaceId}?${params.toString()}`
    );
  },

  async bulkPriceCheck(domainIds: string[]): Promise<{ jobId: string; totalDomains: number; status: string }> {
    return fetchApi('/api/infrastructure/bulk-price-check', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    });
  },

  async bulkPurchase(domainIds: string[], provider?: 'porkbun' | 'dynadot'): Promise<{ jobId: string }> {
    return fetchApi('/api/infrastructure/bulk-purchase', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds, provider }),
    });
  },

  async setNameservers(domainIds: string[]): Promise<{ jobId: string }> {
    return fetchApi('/api/infrastructure/set-nameservers', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    });
  },

  async verifyDNS(domainIds: string[]): Promise<{ results: any[] }> {
    return fetchApi('/api/infrastructure/verify-dns', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    });
  },

  async assignProvider(domainIds: string[], provider: 'entra' | 'google'): Promise<{ updated: number }> {
    return fetchApi(`/api/infrastructure/assign-provider?provider=${provider}`, {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds }),
    });
  },

  async createHyperTideOrder(request: HyperTideOrderRequest): Promise<HyperTideOrderResponse> {
    return fetchApi('/api/infrastructure/hypertide-order', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  },

  async getSenderNames(workspaceId: string): Promise<{ senderNames: SenderName[] }> {
    return fetchApi(`/api/infrastructure/sender-names/${workspaceId}`);
  },
};
```

---

### 1.5 Test Foundation (30 minutes)

```bash
# Start backend
cd /home/claw/charm-email-os/backend
uvicorn main:app --reload

# Start frontend
cd /home/claw/charm-email-os/charm-email-os
npm run dev

# Test API endpoint
curl http://localhost:8000/api/infrastructure/waterfall/test-workspace-id

# Should return: {"workspace_id": "test-workspace-id", "domains": [], "total_domains": 0}
```

**✅ Day 1 Complete Checklist:**
- [ ] Database migration runs without errors
- [ ] New tables created (sender_names, lifecycle_events)
- [ ] DNS fields added to domains table
- [ ] Indexes created
- [ ] Backend starts without import errors
- [ ] `/api/infrastructure/waterfall/{id}` returns 200
- [ ] Frontend compiles without TypeScript errors

---

## DAY 2: Backend API Implementation (8 hours)

### 2.1 Complete All API Endpoints (4 hours)

[Continued in next message due to length...]

**IMPLEMENTATION CONTINUES...**

Would you like me to continue with Days 2-5, or shall we start implementing Day 1 first to ensure the foundation works before proceeding?
