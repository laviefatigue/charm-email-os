# API CONSOLIDATION AUDIT - Infrastructure Provisioning
**Audit Date:** 2026-02-25
**Status:** ⚠️ CRITICAL - Multiple Duplicates Found

## EXECUTIVE SUMMARY

After comprehensive audit of 5 route files (8,368 total lines), **significant duplication exists** between the new `infrastructure.py` endpoints and existing endpoints in `domain_sourcing.py` and `inbox_purchasing.py`.

### Key Findings:
- ✅ **Waterfall view endpoints are UNIQUE** - No existing equivalent (valuable addition)
- ⚠️ **4 direct conflicts** - Bulk price check, bulk purchase, nameserver setting, HyperTide orders
- ✅ **Provider assignment is UNIQUE** - Fills gap in workflow
- ⚠️ **Sender names endpoint duplicates client-based lookup** - Different input key

---

## DUPLICATE ENDPOINTS - CONSOLIDATION REQUIRED

### 1. ❌ BULK PRICE CHECK - FULL DUPLICATE

**Existing (MATURE):**
- **Path:** `POST /api/domain-sourcing/check-prices-bulk`
- **File:** `domain_sourcing.py:2803`
- **Request:**
  ```python
  BulkPriceCheckRequest(
      client_id: Optional[UUID] = None,
      domain_ids: Optional[list[UUID]] = None,
      job_id: Optional[UUID] = None
  )
  ```
- **Response:**
  ```python
  BulkPriceCheckResponse(
      results: list[CheckPriceResponse],  # Full pricing details per domain
      checked_count: int,
      available_count: int,
      error_count: int
  )
  ```
- **Features:**
  - Checks BOTH Porkbun AND Dynadot concurrently
  - Updates domains table: `porkbun_price`, `dynadot_price`, `cached_price`, `selected_provider`, `price_checked_at`
  - Supports filtering by client_id OR domain_ids OR job_id
  - Returns detailed per-domain pricing breakdown

**New (STUB):**
- **Path:** `POST /api/infrastructure/bulk-price-check`
- **File:** `infrastructure.py:177`
- **Request:** `BulkActionRequest(domain_ids: List[str])`
- **Response:** `{job_id, total_domains, status, message}`
- **Features:**
  - Placeholder only (TODO comment)
  - Returns job_id but doesn't create actual job

**VERDICT:** ❌ Delete new endpoint, use existing `/domain-sourcing/check-prices-bulk`

---

### 2. ❌ BULK PURCHASE - FULL DUPLICATE

**Existing (MATURE):**
- **Path:** `POST /api/domain-sourcing/purchase-domains`
- **File:** `domain_sourcing.py:2131`
- **Request:**
  ```python
  PurchaseDomainsRequest(domain_ids: list[UUID])
  ```
- **Response:**
  ```python
  PurchaseDomainsResponse(
      purchases: list[PurchaseResult],
      successful_count: int,
      failed_count: int,
      total_cost: float
  )
  ```
- **Features:**
  - Validates balance before purchase
  - Automatically sets DNSimple nameservers at purchase time
  - Updates domains table: `approval_status='purchased'`, `cached_price`, `selected_provider`, `purchased_at`, `registration_date`, `nameservers_updated_at`, `nameserver_status`
  - Has automatic fallback between Porkbun/Dynadot
  - Fetches actual WHOIS registration dates from registrar
  - Calculates 30-day setup availability window

**Also Exists:**
- **Path:** `POST /api/domain-sourcing/purchase/{domain_id}` (single domain)
- **Path:** `POST /api/domain-sourcing/purchase` (bulk with nameserver config)

**New (STUB):**
- **Path:** `POST /api/infrastructure/bulk-purchase`
- **File:** `infrastructure.py:190`
- **Request:** `BulkActionRequest(domain_ids)`, optional `provider` query param
- **Response:** `{job_id, total_domains, status, message}`
- **Features:**
  - Placeholder only (TODO comment)
  - Returns job_id but doesn't create actual job

**VERDICT:** ❌ Delete new endpoint, use existing `/domain-sourcing/purchase-domains`

---

### 3. ⚠️ SET NAMESERVERS - DIFFERENT INPUT TYPES

**Existing:**
- **Path:** `POST /api/domain-sourcing/update-nameservers`
- **File:** `domain_sourcing.py` (multiple endpoints)
- **Request:**
  ```python
  UpdateNameserversRequest(
      domain_names: list[str],  # Takes domain NAMES
      nameservers: list[str]  # Optional, defaults to DNSimple
  )
  ```
- **Response:**
  ```python
  UpdateNameserversResponse(
      results: list[UpdateNameserverResult],
      successful_count: int,
      failed_count: int
  )
  ```
- **Features:**
  - Tries both Porkbun AND Dynadot automatically
  - Updates `nameservers_updated_at` and `selected_provider`
  - Tracks DNS propagation status
  - DNSimple nameservers hardcoded:
    - ns1.dnsimple.com
    - ns2.dnsimple-edge.net
    - ns3.dnsimple.com
    - ns4.dnsimple-edge.org

**Also Exists:**
- `POST /api/domain-sourcing/set-nameservers` (similar)
- `POST /api/domain-sourcing/verify-nameservers` (verification)
- `GET /api/domain-sourcing/nameserver-status/{domain_name}` (status check)

**New:**
- **Path:** `POST /api/infrastructure/set-nameservers`
- **File:** `infrastructure.py:212`
- **Request:** `BulkActionRequest(domain_ids: List[str])`  # Takes domain IDs
- **Response:** `{job_id, total_domains, status}`
- **Features:**
  - Placeholder only (TODO comment)
  - Uses domain_ids instead of domain_names

**VERDICT:** ⚠️ Keep new endpoint BUT make it a wrapper that:
1. Looks up domain_names from domain_ids
2. Delegates to existing `/domain-sourcing/update-nameservers`
3. Provides UUID-based interface for waterfall UI

---

### 4. 🔶 HYPERTIDE ORDER - OVERLAPPING BUT DIFFERENT

**Existing (V1 - LEGACY):**
- **Path:** `POST /api/inbox-purchasing/execute`
- **File:** `inbox_purchasing.py`
- **Request:**
  ```python
  ExecutePurchaseRequest(
      client_id: UUID,
      inbox_target: int,
      entra_domains: list[str],  # Domain NAMES
      google_domains: list[str],
      inbox_names: list[dict],
      bison_credentials: dict
  )
  ```
- **Features:**
  - Flexible domain counts
  - Background task execution
  - No persistent job storage

**Existing (V2 - CURRENT):**
- **Path:** `POST /api/inbox-purchasing/execute-v2`
- **File:** `inbox_purchasing.py`
- **Request:**
  ```python
  ExecutePurchaseV2Request(
      client_id: UUID,
      order_groups: list[OrderGroup],  # {order_type, domain_ids[], sender_name_id}
      override_age_check: bool = False
  )
  ```
- **Response:**
  ```python
  PurchaseJobResponse(
      job_id: str,
      status: str,
      estimated_duration: int
  )
  ```
- **Features:**
  - Enforces FIXED domain counts:
    - Entra: EXACTLY 2 domains = 100 inboxes
    - Google: EXACTLY 5 domains = 15 inboxes
  - Validates domain age (30+ days required)
  - Creates `inbox_purchase_jobs` records
  - Tracks completion status

**Also Exists:**
- `POST /api/inbox-purchasing/execute-v2/preview` - Preview before execution
- `GET /api/inbox-purchasing/status/{job_id}` - Check order status
- `POST /api/inbox-purchasing/jobs/{job_id}/retry` - Retry failed jobs
- `DELETE /api/inbox-purchasing/jobs/{job_id}` - Cancel jobs

**New:**
- **Path:** `POST /api/infrastructure/hypertide-order`
- **File:** `infrastructure.py:295`
- **Request:**
  ```python
  HyperTideOrderRequest(
      client_id: str,
      workspace_id: str,  # NEW FIELD
      order_groups: list[HyperTideOrderGroupRequest],
      forwarding_domain: str,
      bison_workspace: str
  )
  ```
- **Response:**
  ```python
  {
      job_id: str,
      total_orders: int,
      status: str,
      estimated_duration_seconds: int,
      message: str
  }
  ```
- **Features:**
  - Requires BOTH client_id AND workspace_id (better data tracking)
  - Stores full request_data in JSONB for audit trail
  - Calculates entra_orders + google_orders automatically
  - Stores in inbox_purchase_jobs with metadata

**VERDICT:** 🔶 Keep BOTH endpoints:
- **Existing `/inbox-purchasing/execute-v2`**: For backward compatibility, direct inbox provisioning
- **New `/infrastructure/hypertide-order`**: For waterfall UI, includes workspace_id, better audit trail
- **Action Required:** Document difference and migration path

---

### 5. ⚠️ SENDER NAMES - DIFFERENT LOOKUP KEY

**Existing (CLIENT-BASED):**
- **Path:** `GET /api/clients/{client_id}/sender-names-for-provisioning`
- **File:** `clients.py`
- **Request:** `client_id` (path param)
- **Response:**
  ```python
  SenderNamesForProvisioningResponse(
      clientId: str,
      clientName: str,
      forwardingDomain: str,
      emailbisonWorkspaceId: str,
      workspaceId: str,
      senderNames: list[SenderName],
      hypertideConstraints: dict  # Entra: 50 prefixes, Google: 3 prefixes
  )
  ```
- **Features:**
  - Returns client context (name, forwarding domain)
  - Includes EmailBison workspace ID
  - Includes HyperTide order constraints
  - Generates sender name prefixes with counts

**New (WORKSPACE-BASED):**
- **Path:** `GET /api/infrastructure/sender-names/{workspace_id}`
- **File:** `infrastructure.py:410`
- **Request:** `workspace_id` (path param)
- **Response:**
  ```python
  {
      sender_names: list[{
          id: str,
          workspace_id: str,
          first_name: str,
          last_name: str,
          full_name: str,
          email: Optional[str],
          is_active: bool
      }]
  }
  ```
- **Features:**
  - Simpler response (just names)
  - No HyperTide constraints
  - No client context
  - Queries new `sender_names` table

**VERDICT:** ⚠️ Keep BOTH but clarify use cases:
- **Existing `/clients/{client_id}/sender-names-for-provisioning`**: Full provisioning context with constraints
- **New `/infrastructure/sender-names/{workspace_id}`**: Simple name lookup for waterfall UI
- **Action Required:** Add bridge endpoint `/infrastructure/sender-names/client/{client_id}` that looks up workspace_id first

---

## UNIQUE ENDPOINTS - NO CONFLICTS ✅

### 1. ✅ WATERFALL VIEW (UNIQUE - VALUABLE)

**New Endpoints:**
- `GET /api/infrastructure/waterfall/client/{client_id}`
- `GET /api/infrastructure/waterfall/workspace/{workspace_id}`

**Purpose:**
- Monitor complete 9-stage provisioning pipeline
- Single query returns all domain states across workflow
- Reads from `v_infrastructure_waterfall` database view

**Response:**
```python
WaterfallResponse(
    workspace_id: str,
    domains: list[WaterfallDomainResponse],  # See below
    total_domains: int
)
```

**WaterfallDomainResponse includes:**
- Stage 1: Domain generation (domain_name, legitimacy_score, generated_at)
- Stage 2: Pricing (price_checked_at, cached_price, selected_provider, price_status)
- Stage 3: Purchase (purchased_at, purchase_job_id)
- Stage 4: DNS moved (nameservers_updated_at, dns_migration_status)
- Stage 5: DNS verified (nameserver_status, SPF/DKIM/DMARC/MX flags, dns_records_configured)
- Stage 6: Provider assigned (assigned_provider: entra|google)
- Stage 7: HyperTide ordered (hypertide_order_job_id, hypertide_order_status)
- Stage 9: Synced (synced_inbox_count, last_inbox_synced_at)
- Computed: current_stage (1-9), owned_by_client, deployed_to_production

**Query Options:**
- `view`: 'all' | 'owned' | 'new'
- `stage`: 1-9 (filter by current stage)
- `provider`: 'entra' | 'google'

**VERDICT:** ✅ Excellent addition - no existing equivalent

---

### 2. ✅ VERIFY DNS (BULK) - ENHANCEMENT

**New Endpoint:**
- `POST /api/infrastructure/verify-dns`

**Request:** `BulkActionRequest(domain_ids: List[str])`

**Response:**
```python
{
    results: list[unknown],
    all_configured: int,
    partially_configured: int
}
```

**Existing Related:**
- `POST /api/domain-sourcing/verify-nameservers` - Verifies nameserver propagation only
- No existing bulk DNS record verification

**VERDICT:** ✅ Good addition - fills gap for SPF/DKIM/DMARC/MX verification in bulk

---

### 3. ✅ ASSIGN PROVIDER - UNIQUE

**New Endpoint:**
- `POST /api/infrastructure/assign-provider`

**Request:** `BulkActionRequest(domain_ids)`, `provider` query param (entra|google)

**Response:**
```python
{
    updated: int,
    provider: str
}
```

**Purpose:**
- Sets `infrastructure_type` field in domains table
- Stage 6 of waterfall: assign domains to Entra or Google infrastructure

**Existing Related:**
- No existing endpoint updates `infrastructure_type` field

**VERDICT:** ✅ Fills gap in provisioning workflow

---

## RECOMMENDED CONSOLIDATION PLAN

### Phase 1: Immediate Deletions (Remove Stubs)

Delete these stub endpoints from `infrastructure.py`:

1. ❌ **DELETE:** `POST /api/infrastructure/bulk-price-check`
   - **Use instead:** `POST /api/domain-sourcing/check-prices-bulk`

2. ❌ **DELETE:** `POST /api/infrastructure/bulk-purchase`
   - **Use instead:** `POST /api/domain-sourcing/purchase-domains`

### Phase 2: Wrapper Conversions (Keep but Delegate)

Convert these to thin wrappers:

3. ⚠️ **CONVERT TO WRAPPER:** `POST /api/infrastructure/set-nameservers`
   ```python
   async def set_nameservers(request: BulkActionRequest):
       # 1. Lookup domain_names from domain_ids
       domain_names = await get_domain_names_from_ids(request.domain_ids)

       # 2. Delegate to existing endpoint
       from routes.domain_sourcing import update_nameservers
       return await update_nameservers(
           UpdateNameserversRequest(
               domain_names=domain_names,
               nameservers=DNSIMPLE_NAMESERVERS
           )
       )
   ```

### Phase 3: Coexistence (Document Differences)

Keep both but document clearly:

4. 🔶 **KEEP BOTH:** HyperTide Order endpoints
   - **Existing:** `POST /api/inbox-purchasing/execute-v2` (legacy, direct provisioning)
   - **New:** `POST /api/infrastructure/hypertide-order` (waterfall UI, includes workspace_id)
   - **Document:** Migration guide for users

5. ⚠️ **ADD BRIDGE:** Sender Names
   - **Keep:** `GET /api/clients/{client_id}/sender-names-for-provisioning` (full context)
   - **Keep:** `GET /api/infrastructure/sender-names/{workspace_id}` (simple lookup)
   - **Add:** `GET /api/infrastructure/sender-names/client/{client_id}` (bridge endpoint)
   ```python
   async def get_sender_names_by_client(client_id: str):
       workspace_id = await get_workspace_id_from_client(client_id)
       return await get_sender_names(workspace_id)
   ```

### Phase 4: Update Frontend API Client

Update `/charm-email-os/lib/api.ts`:

```typescript
export const infrastructureApi = {
  // Waterfall monitoring (UNIQUE)
  async getWaterfallByClient(clientId: string, options?) { ... },
  async getWaterfallByWorkspace(workspaceId: string, options?) { ... },

  // Bulk operations (DELEGATE TO EXISTING)
  async bulkPriceCheck(domainIds: string[]) {
    // Calls /domain-sourcing/check-prices-bulk
    return domainSourcingApi.checkPricesBulk({ domain_ids: domainIds });
  },

  async bulkPurchase(domainIds: string[], provider?) {
    // Calls /domain-sourcing/purchase-domains
    return domainSourcingApi.purchaseDomains({ domain_ids: domainIds });
  },

  async setNameservers(domainIds: string[]) {
    // Calls wrapper that delegates to /domain-sourcing/update-nameservers
    return fetchApi('/api/infrastructure/set-nameservers', {
      method: 'POST',
      body: JSON.stringify({ domain_ids: domainIds })
    });
  },

  // DNS verification (UNIQUE)
  async verifyDNS(domainIds: string[]) { ... },

  // Provider assignment (UNIQUE)
  async assignProvider(domainIds: string[], provider: 'entra' | 'google') { ... },

  // HyperTide order (NEW VERSION with workspace_id)
  async createHyperTideOrder(request: HyperTideOrderRequest) { ... },

  // Sender names (SIMPLE LOOKUP)
  async getSenderNames(workspaceId: string) { ... },
};
```

---

## DATABASE VIEW CONSOLIDATION

### Existing Domain Data Sources

Multiple queries across different endpoints fetch similar domain data:

1. **domain_sourcing.py** queries:
   ```sql
   SELECT id, domain_name, workspace_id, approval_status,
          porkbun_price, dynadot_price, cached_price, selected_provider,
          price_checked_at, purchased_at, nameservers_updated_at
   FROM domains
   WHERE workspace_id = $1
   ```

2. **domains.py** queries:
   ```sql
   SELECT d.*, COUNT(sa.id) as inbox_count
   FROM domains d
   LEFT JOIN sender_accounts sa ON sa.domain_id = d.id
   WHERE d.workspace_id = $1
   GROUP BY d.id
   ```

3. **infrastructure.py** queries:
   ```sql
   SELECT * FROM v_infrastructure_waterfall
   WHERE workspace_id = $1
   ```

### Recommendation: Use v_infrastructure_waterfall as Single Source

The new `v_infrastructure_waterfall` view consolidates all domain data:
- ✅ Includes pricing fields (porkbun, dynadot, cached_price)
- ✅ Includes purchase tracking (purchased_at, purchase_job_id)
- ✅ Includes DNS tracking (nameservers_updated_at, nameserver_status, SPF/DKIM/DMARC/MX)
- ✅ Includes infrastructure (assigned_provider: entra|google)
- ✅ Includes HyperTide status (hypertide_order_job_id, hypertide_order_status)
- ✅ Includes inbox sync (synced_inbox_count)
- ✅ Computes current_stage (1-9) automatically
- ✅ Joins inbox_purchase_jobs automatically

**Action:** Gradually migrate other endpoints to use `v_infrastructure_waterfall` instead of raw `domains` table queries.

---

## MIGRATION CHECKLIST

### Backend Changes
- [ ] Delete `POST /api/infrastructure/bulk-price-check` (use existing)
- [ ] Delete `POST /api/infrastructure/bulk-purchase` (use existing)
- [ ] Convert `POST /api/infrastructure/set-nameservers` to wrapper
- [ ] Add `GET /api/infrastructure/sender-names/client/{client_id}` bridge endpoint
- [ ] Document HyperTide order endpoint differences
- [ ] Add deprecation warnings to V1 inbox-purchasing endpoints

### Frontend Changes
- [ ] Update infrastructureApi to delegate bulk operations
- [ ] Add comments explaining which endpoints are wrappers
- [ ] Create migration guide for users of old endpoints
- [ ] Update TypeScript types to match consolidated responses

### Documentation Changes
- [ ] Create API endpoint comparison table (old vs new)
- [ ] Document waterfall view as canonical data source
- [ ] Add sequence diagrams for each provisioning stage
- [ ] Document when to use `/inbox-purchasing/execute-v2` vs `/infrastructure/hypertide-order`

### Testing Changes
- [ ] Add integration tests for waterfall view filtering
- [ ] Test wrapper delegation works correctly
- [ ] Verify backward compatibility with existing clients
- [ ] Test client_id→workspace_id lookups

---

## COST-BENEFIT ANALYSIS

### Benefits of Consolidation
- ✅ Reduced code duplication (eliminate ~200 lines of stub code)
- ✅ Single source of truth for domain data (v_infrastructure_waterfall)
- ✅ Clearer API boundaries (waterfall UI vs direct provisioning)
- ✅ Better audit trail (workspace_id + client_id tracking)

### Costs of Consolidation
- ⚠️ Breaking changes for internal tools using `/infrastructure/bulk-*` endpoints
- ⚠️ Need to update frontend immediately
- ⚠️ Migration documentation required
- ⚠️ Potential confusion with two HyperTide order endpoints

### Recommendation
**Proceed with consolidation** but:
1. Keep HyperTide order endpoints separate (different use cases)
2. Add bridge endpoints for smooth migration
3. Document clearly in API reference
4. Add deprecation warnings before deleting

---

## FINAL VERDICT TABLE

| Endpoint | File | Status | Action |
|----------|------|--------|--------|
| GET /waterfall/client/{id} | infrastructure.py | ✅ UNIQUE | Keep - valuable addition |
| GET /waterfall/workspace/{id} | infrastructure.py | ✅ UNIQUE | Keep - valuable addition |
| POST /bulk-price-check | infrastructure.py | ❌ DUPLICATE | Delete - use domain_sourcing |
| POST /bulk-purchase | infrastructure.py | ❌ DUPLICATE | Delete - use domain_sourcing |
| POST /set-nameservers | infrastructure.py | ⚠️ DIFFERENT | Keep as wrapper |
| POST /verify-dns | infrastructure.py | ✅ UNIQUE | Keep - fills gap |
| POST /assign-provider | infrastructure.py | ✅ UNIQUE | Keep - fills gap |
| POST /hypertide-order | infrastructure.py | 🔶 OVERLAP | Keep - better audit trail |
| GET /sender-names/{workspace_id} | infrastructure.py | ⚠️ DIFFERENT | Keep + add bridge |

**Summary:**
- ✅ Keep: 6 endpoints (4 unique, 2 overlap-but-better)
- ❌ Delete: 2 endpoints (full duplicates)
- ⚠️ Convert: 1 endpoint (wrapper)
- 🔶 Document: 2 endpoints (coexistence)
