# Infrastructure Provisioning SPA - Design Specification V2

**Application Name:** Infrastructure Command Center
**Version:** 2.0 (Updated 2026-02-25)
**Type:** Single Page Application (React + TypeScript)
**Purpose:** Waterfall-style domain-to-inbox provisioning management with correct DNS flow

---

## CRITICAL UPDATES FROM V1

### 1. DNS VERIFICATION MOVES AFTER PURCHASE ✅
**Correct Flow:** Purchase → DNS Verification → HyperTide Order

**Why:** Nameservers must be changed to DNSimple AFTER purchase, not before. We verify the migration is complete before submitting to HyperTide.

### 2. NO HYPERTIDE API EXISTS ⚠️
**Reality:** HyperTide is a web-only platform with NO API

**Implications:**
- All HyperTide operations use Playwright browser automation
- Domain swapping requires emailing support@hypertide.io (100% manual)
- Order tracking limited to what we see in browser
- No programmatic status checks

### 3. DNS NAMESERVER REQUIREMENTS
**Required Nameservers (DNSimple):**
- ns1.dnsimple.com
- ns2.dnsimple-edge.net
- ns3.dnsimple.com
- ns4.dnsimple-edge.org

**NOT Cloudflare** - HyperTide requires DNSimple for BYOD mode

### 4. PROVIDER TYPE TRACKING
**Critical:** Must show which domains are assigned to Entra vs Google

**Display Requirements:**
- Badge on each domain row: 🟦 Entra | 🔴 Google
- Filter by provider type
- Validation before HyperTide order (no mixing providers in same order)

---

## CORRECTED WATERFALL TABLE (9 Columns)

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    INFRASTRUCTURE PROVISIONING WATERFALL                                             │
├──────┬─────────┬────────┬──────────┬─────────┬──────────────┬────────────┬───────────┬──────────────┬─────────────┤
│Select│Generated│ Priced │ Purchased│DNS Moved│ DNS Verified │  Provider  │HyperTide  │ Provisioned  │ Synced to DB│
│[all] │         │        │          │         │              │  Assigned  │  Ordered  │              │             │
│      │[GENERATE│[CHECK  │[PURCHASE │[SET DNS │  [VERIFY DNS │ [ASSIGN    │ [ORDER    │  [POLL       │  [VIEW      │
│      │  BULK]  │ PRICES │  BULK]   │  BULK]  │   BULK]      │  PROVIDER  │  HYPERTIDE│  HYPERTIDE   │  INBOXES    │
│      │         │  BULK] │          │         │              │   BULK]    │   BULK]   │   BULK]      │   BULK]     │
├──────┼─────────┼────────┼──────────┼─────────┼──────────────┼────────────┼───────────┼──────────────┼─────────────┤
│ ☑    │example  │$10.88✓ │Purchased │DNSimple │   Verified   │ 🟦 Entra  │  Order    │ Provisioning │ 100 inboxes │
│      │.com     │(Dynadt)│2/24/26   │✓ Set    │   ✓ SPF      │  Assigned  │  #4521    │    45%       │  synced ✓   │
│      │Owned ✓  │        │          │24h ago  │   ✓ DKIM     │            │  Active   │  ETA: 2h     │             │
│      │         │        │          │         │   ✓ DMARC    │            │           │              │             │
│      │         │        │          │         │   ✓ MX       │            │           │              │             │
├──────┼─────────┼────────┼──────────┼─────────┼──────────────┼────────────┼───────────┼──────────────┼─────────────┤
│ ☐    │growth   │$11.08  │Purchased │⏱Pending │   Waiting    │ 🔴 Google  │     -     │      -       │      -      │
│      │checkout │(Porkbn)│2/25/26   │12h left │   for NS     │  Assigned  │           │              │             │
│      │.com     │        │          │         │   migration  │            │           │              │             │
└──────┴─────────┴────────┴──────────┴─────────┴──────────────┴────────────┴───────────┴──────────────┴─────────────┘
```

---

## CORRECTED PROCESS FLOW

### Stage 1: Generated
**Status:** `domains.approval_status = 'available'`
**Action:** Domain created via AI or pattern generation
**Display:**
- Domain name
- Legitimacy score (0.0-1.0)
- Generation timestamp

**Bulk Action:** [GENERATE BULK]
- Input: Count (how many domains to generate)
- Calculates deficit from package size
- Runs AI domain generator

---

### Stage 2: Priced
**Status:** `domains.price_checked_at IS NOT NULL`
**Action:** Fetch pricing from Porkbun + Dynadot APIs
**Display:**
- Lowest price: "$10.88 (Dynadot) ✓"
- Hover shows both:
  - Porkbun: $11.08
  - Dynadot: $10.88 ✓ (selected)
- Unavailable: "Unavailable" (gray out)
- Stale (>24h): "⏱ Rechecking..."

**Bulk Action:** [CHECK PRICES BULK]
- Parallel API calls to both registrars
- Updates cached_price and selected_provider
- Progress modal shows per-domain status

---

### Stage 3: Purchased
**Status:** `domains.purchased_at IS NOT NULL`
**Action:** Buy domain from selected registrar
**Display:**
- "Purchased ✓"
- Date: "2/24/26"
- Registrar: "Dynadot"
- Cost: "$10.88"

**Bulk Action:** [PURCHASE BULK]
- Validates all domains have valid prices
- Shows total cost summary
- Creates domain_purchase_jobs record
- Triggers purchase worker
- Progress modal with per-domain results

**CRITICAL:** Nameservers are NOT changed yet - still pointing to registrar defaults

---

### Stage 4: DNS Moved
**Status:** `domains.nameserver_set_at IS NOT NULL`
**NEW ACTION:** Change nameservers to DNSimple **AFTER** purchase
**Display:**
- "✓ Set 24h ago" (if complete)
- "⏱ Pending 12h left" (if in progress)
- "❌ Failed" (if registrar API error)

**Nameserver Configuration:**
```
ns1.dnsimple.com
ns2.dnsimple-edge.net
ns3.dnsimple.com
ns4.dnsimple-edge.org
```

**Bulk Action:** [SET DNS BULK]
- Calls registrar API to update nameservers
- Marks `nameserver_set_at = NOW()`
- Estimated propagation: 24-48 hours
- Progress modal shows per-domain status

**Implementation:**
```python
# Dynadot API
POST /api/set_ns2.json
{
  "domain": "example.com",
  "ns1": "ns1.dnsimple.com",
  "ns2": "ns2.dnsimple-edge.net",
  "ns3": "ns3.dnsimple.com",
  "ns4": "ns4.dnsimple-edge.org"
}

# Porkbun API
POST /api/json/v3/dns/editByNameServer
{
  "domain": "example.com",
  "ns": [
    "ns1.dnsimple.com",
    "ns2.dnsimple-edge.net",
    "ns3.dnsimple.com",
    "ns4.dnsimple-edge.org"
  ]
}
```

---

### Stage 5: DNS Verified
**Status:** `domains.nameserver_status = 'verified'`
**Action:** Check DNS propagation + HyperTide DNS records
**Display:**
- "Verified ✓" (all checks passed)
- Expandable checklist:
  - ✓ Nameservers: DNSimple
  - ✓ SPF record configured
  - ✓ DKIM record configured
  - ✓ DMARC record configured
  - ✓ MX records configured
- "⏱ Verifying..." (checking)
- "❌ Failed: [reason]" (error with details)

**Wait Time:** Minimum 24 hours after nameserver change

**Verification Process:**
```python
# 1. Check nameservers
dig +short NS example.com
# Expected output:
# ns1.dnsimple.com.
# ns2.dnsimple-edge.net.
# ns3.dnsimple.com.
# ns4.dnsimple-edge.org.

# 2. Check SPF record
dig +short TXT example.com | grep spf
# Expected: v=spf1 include:_spf.hirecharm.com ~all

# 3. Check DKIM record
dig +short TXT default._domainkey.example.com
# Expected: v=DKIM1; k=rsa; p=[public key]

# 4. Check DMARC record
dig +short TXT _dmarc.example.com
# Expected: v=DMARC1; p=none; rua=mailto:dmarc@example.com

# 5. Check MX records
dig +short MX example.com
# Expected: 10 inbound-smtp.us-east-1.amazonaws.com.
```

**Bulk Action:** [VERIFY DNS BULK]
- Runs DNS checks for all selected domains
- Updates `nameserver_status` and `dns_records_configured`
- Shows which specific records are missing
- Retry failed domains with exponential backoff

**CRITICAL:** HyperTide automatically configures SPF/DKIM/DMARC/MX records AFTER domains are added to an order. We're verifying propagation only.

---

### Stage 6: Provider Assigned
**Status:** `domains.assigned_provider IS NOT NULL`
**NEW COLUMN:** Show which provider each domain is assigned to
**Display:**
- 🟦 **Entra** (blue badge) - Microsoft Azure AD
- 🔴 **Google** (red badge) - Google Workspace
- ⚪ **Unassigned** (gray) - Not yet assigned

**Why This Matters:**
- HyperTide orders are provider-specific (can't mix Entra + Google in one order)
- Entra orders: 2 domains required
- Google orders: 5 domains required
- Validation prevents submitting invalid orders

**Bulk Action:** [ASSIGN PROVIDER BULK]
- Modal: "Assign selected domains to: [Entra] [Google]"
- Updates `domains.assigned_provider`
- Shows validation warnings:
  - "⚠ 3 Entra domains selected (need 2 or 4)"
  - "✓ 5 Google domains selected (ready for order)"

**Assignment Rules:**
- Can assign before or after DNS verification
- Recommended: Assign early to track fulfillment per provider
- Can reassign before HyperTide order is created

---

### Stage 7: HyperTide Ordered
**Status:** `domains.hypertide_order_job_id IS NOT NULL`
**Action:** Create HyperTide inbox purchase order (browser automation)
**Display:**
- Order ID: "Order #4521"
- Status badge:
  - 🟡 Pending (queued)
  - 🔵 Executing (browser automation running)
  - 🟢 Completed (order submitted)
  - 🔴 Failed (error occurred)
- Current step (if executing):
  - "Choosing plan..."
  - "Adding domains (BYOD)..."
  - "Configuring settings..."
  - "⏱ Awaiting payment"
  - "Submitting order..."
- Progress bar: "45%"

**Bulk Action:** [ORDER HYPERTIDE BULK]
- **Validation:**
  - All domains must have `nameserver_status = 'verified'`
  - All domains must have same `assigned_provider`
  - Entra: Exactly 2 domains
  - Google: Exactly 5 domains
- **Configuration Modal:**
  ```
  ┌─────────────────────────────────────────┐
  │ Create HyperTide Order                  │
  ├─────────────────────────────────────────┤
  │ Provider: 🟦 Entra                     │
  │ Domains (2):                            │
  │ • example.com                          │
  │ • growthcheckout.com                   │
  │                                         │
  │ Forwarding Domain: [acmecorp.com   ]   │
  │ Company Name:      [Acme Corp      ]   │
  │ EmailBison Workspace: [Acme ▼]         │
  │                                         │
  │ Sender Names (3):                      │
  │ • Chris Booth                          │
  │ • Sarah Johnson                        │
  │ • Mike Chen                            │
  │ [+ Add Name]                           │
  │                                         │
  │ Expected Output:                        │
  │ • 100 inboxes (50 per domain)          │
  │ • $50/month subscription                │
  │                                         │
  │ ⚠ Browser automation required          │
  │ ⚠ Manual payment step                  │
  │                                         │
  │ [Cancel] [Create Order]                │
  └─────────────────────────────────────────┘
  ```
- Creates `inbox_purchase_jobs` record
- Triggers `hypertide_worker.py` (Playwright automation)

**CRITICAL LIMITATION:** No API exists - all operations use browser automation. Manual payment step requires human intervention.

---

### Stage 8: Provisioned
**Status:** `inbox_purchase_jobs.status = 'completed'` BUT inboxes not yet in database
**Action:** HyperTide provisions inboxes on their end (we don't control timing)
**Display:**
- "⏱ Provisioning..." (HyperTide is working)
- "Checking status..." (we're polling)
- "45% (45/100 inboxes)" (if HyperTide provides progress)
- "ETA: 2 hours" (estimated)
- "100 inboxes provisioned ✓" (complete)

**Wait Time:** 1-4 hours (uncontrollable - depends on HyperTide)

**Bulk Action:** [POLL HYPERTIDE BULK]
- Opens HyperTide dashboard in browser (no API to poll)
- User manually checks status
- Updates `provisioning_completed_at` when user confirms

**CRITICAL:** Since there's no API, we rely on:
1. EmailBison sync detecting new inboxes (next stage)
2. Manual user confirmation from HyperTide dashboard

---

### Stage 9: Synced to DB
**Status:** `sender_accounts` records exist for this domain
**Action:** EmailBison sync worker detects new inboxes
**Display:**
- "100 inboxes synced ✓" (Entra)
- "15 inboxes synced ✓" (Google)
- Breakdown (hover):
  - 95 live, 5 warmup
  - ESP: Microsoft
  - Warmup enabled: Yes
  - Avg health score: 87
- Last sync: "2 min ago"

**Sync Detection:**
```python
# emailbison_sync_worker.py runs every 15 minutes
# Calls: GET /api/v1/sender_accounts
# For each account:
#   - Extract domain from email_address
#   - Link to domains.id via domain_name
#   - INSERT into sender_accounts
```

**Bulk Action:** [VIEW INBOXES BULK]
- Opens inbox management page
- Pre-filters to selected domains
- Shows all synced inboxes

**Cell Actions:**
- Click inbox count → Inbox list modal
- Click "Force Sync" → Trigger immediate sync worker run

---

## CRITICAL BUSINESS RULES (UPDATED)

### 1. DNS Flow is AFTER Purchase ✅
**Order:** Generate → Price → Purchase → **DNS Moved** → **DNS Verified** → Provider Assigned → HyperTide Order

**Why:** We purchase domains with registrar nameservers, THEN migrate to DNSimple AFTER purchase completes.

---

### 2. DNSimple Nameservers REQUIRED ⚠️
**Nameservers:**
```
ns1.dnsimple.com
ns2.dnsimple-edge.net
ns3.dnsimple.com
ns4.dnsimple-edge.org
```

**NOT ALLOWED:**
- Cloudflare nameservers (HyperTide doesn't support)
- Registrar default nameservers (won't work with BYOD mode)
- Any other DNS provider

---

### 3. No HyperTide API - Browser Automation Only ⚠️
**Reality Check:**
- No API for order creation
- No API for status tracking
- No API for domain swapping
- No API for inbox management

**What We Have:**
- Playwright browser automation (`hypertide_worker.py`)
- Manual support emails for domain swaps (`support@hypertide.io`)
- EmailBison API for inbox status (post-provisioning)

**Implications for UI:**
- "Order Status" polling is limited
- "Provisioning" stage requires manual checks
- Progress tracking estimated based on average times
- Clear messaging: "⚠ Manual payment required"

---

### 4. Provider Type Tracking REQUIRED ✅
**Why:** HyperTide orders are provider-specific

**Database Field:**
```sql
ALTER TABLE domains ADD COLUMN assigned_provider VARCHAR(20);
-- Values: 'entra' | 'google' | NULL

CREATE INDEX idx_domains_provider ON domains(assigned_provider);
```

**UI Requirements:**
- Badge on every domain row: 🟦 Entra | 🔴 Google
- Filter dropdown: [All Providers ▼] [Entra Only] [Google Only]
- Validation before HyperTide order:
  - "❌ Cannot mix Entra and Google in one order"
  - "✓ 2 Entra domains selected (ready)"
  - "⚠ 3 Google domains selected (need 5)"

---

### 5. HyperTide Order Domain Count Validation
**Entra:** Exactly 2 domains per order (100 inboxes)
**Google:** Exactly 5 domains per order (15 inboxes)

**Smart Selection:**
- Auto-group validated domains into order-ready batches
- Show warning if incorrect count:
  - "⚠ 3 Entra domains selected - need 2 or 4 (even number)"
  - "✓ 10 Google domains selected - will create 2 orders"

---

### 6. Domain Swap Process (Manual) ⚠️
**When a domain dies (kill_trigger fires on 2+ inboxes):**

**Current Process:**
1. Domain marked `domain_state = 'dead'`
2. Manual email to `support@hypertide.io`:
   ```
   Subject: Domain Swap Request - [Client Name]

   Hi HyperTide Support,

   Please swap the following burned domain:
   - Old domain: burned-domain.com
   - New domain: replacement-domain.com (BYOD)
   - Client: Acme Corp
   - Order ID: #4521 (if available)

   DNS is already configured to DNSimple nameservers.

   Thanks!
   ```
3. HyperTide manually performs swap (1-2 business days)
4. New inboxes provisioned under new domain
5. EmailBison sync detects new inboxes

**Future Enhancement:** Build a "Request Domain Swap" UI that:
- Pre-fills email template
- Tracks swap request status locally
- Sends email via backend API
- Monitors for new inboxes under replacement domain

---

## UPDATED DATABASE SCHEMA

### New Fields for `domains` Table

```sql
-- DNS tracking
ALTER TABLE domains ADD COLUMN IF NOT EXISTS nameserver_set_at TIMESTAMP;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS nameserver_status VARCHAR(20)
  CHECK (nameserver_status IN ('pending', 'migrating', 'verified', 'failed'));

-- Provider assignment
ALTER TABLE domains ADD COLUMN IF NOT EXISTS assigned_provider VARCHAR(20)
  CHECK (assigned_provider IN ('entra', 'google'));

-- DNS record verification
ALTER TABLE domains ADD COLUMN IF NOT EXISTS spf_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dkim_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dmarc_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS mx_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dns_records_configured BOOLEAN
  GENERATED ALWAYS AS (
    spf_configured AND dkim_configured AND dmarc_configured AND mx_configured
  ) STORED;

-- Indexes
CREATE INDEX idx_domains_nameserver_status ON domains(nameserver_status);
CREATE INDEX idx_domains_provider ON domains(assigned_provider);
CREATE INDEX idx_domains_dns_verified ON domains(nameserver_status, dns_records_configured);
```

---

### Updated `infrastructure_provisioning_state` View

```sql
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,

    -- Ownership
    COALESCE(d.owned_by_client, FALSE) as owned,
    COALESCE(d.deployed_to_production, FALSE) as deployed,

    -- Stage 1: Generated
    d.created_at as generated_at,
    d.legitimacy_score,

    -- Stage 2: Priced
    d.price_checked_at,
    d.cached_price,
    d.selected_provider,
    CASE
        WHEN d.price_checked_at IS NULL THEN 'not_checked'
        WHEN d.price_checked_at < NOW() - INTERVAL '24 hours' THEN 'stale'
        WHEN d.porkbun_available = FALSE AND d.dynadot_available = FALSE THEN 'unavailable'
        ELSE 'valid'
    END as price_status,

    -- Stage 3: Purchased
    d.purchased_at,
    d.purchase_job_id,

    -- Stage 4: DNS Moved (NEW)
    d.nameserver_set_at,
    CASE
        WHEN d.nameserver_set_at IS NULL THEN 'not_set'
        WHEN d.nameserver_set_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
        ELSE 'propagated'
    END as dns_migration_status,

    -- Stage 5: DNS Verified (UPDATED)
    d.nameserver_status,
    d.nameserver_verified_at,
    d.dns_records_configured,
    d.spf_configured,
    d.dkim_configured,
    d.dmarc_configured,
    d.mx_configured,

    -- Stage 6: Provider Assigned (NEW)
    d.assigned_provider,

    -- Stage 7: HyperTide Ordered
    d.hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.hypertide_progress_pct,

    -- Stage 8: Provisioned
    ipj.provisioning_completed_at,
    CASE
        WHEN d.assigned_provider = 'entra' THEN 100
        WHEN d.assigned_provider = 'google' THEN 15
        ELSE 0
    END as expected_inbox_count,

    -- Stage 9: Synced
    (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id) as synced_inbox_count,
    (SELECT MAX(created_at) FROM sender_accounts sa WHERE sa.domain_id = d.id) as last_inbox_synced_at,

    -- Current stage (for sorting)
    CASE
        WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id) THEN 9
        WHEN ipj.status = 'completed' THEN 8
        WHEN d.hypertide_order_job_id IS NOT NULL THEN 7
        WHEN d.assigned_provider IS NOT NULL THEN 6
        WHEN d.nameserver_status = 'verified' AND d.dns_records_configured = TRUE THEN 5
        WHEN d.nameserver_set_at IS NOT NULL THEN 4
        WHEN d.purchased_at IS NOT NULL THEN 3
        WHEN d.price_checked_at IS NOT NULL THEN 2
        ELSE 1
    END as current_stage

FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.hypertide_order_job_id
WHERE d.is_active = TRUE;
```

---

## UPDATED API ENDPOINTS

### NEW: POST /api/infrastructure/set-nameservers-bulk

**Purpose:** Change nameservers to DNSimple after purchase

**Body:**
```json
{
  "domain_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Process:**
1. For each domain, call registrar API to update nameservers
2. Update `domains.nameserver_set_at = NOW()`
3. Update `domains.nameserver_status = 'migrating'`
4. Return job ID for progress tracking

**Response:**
```json
{
  "job_id": "uuid",
  "status": "running",
  "domains": [
    {"domain_id": "uuid1", "domain_name": "example.com", "status": "updating"},
    {"domain_id": "uuid2", "domain_name": "growth.com", "status": "queued"}
  ]
}
```

---

### NEW: POST /api/infrastructure/verify-dns-bulk

**Purpose:** Check DNS propagation and HyperTide DNS records

**Body:**
```json
{
  "domain_ids": ["uuid1", "uuid2"]
}
```

**Validation:**
- All domains must have `nameserver_set_at >= 24 hours ago`
- Checks:
  1. Nameservers = DNSimple (dig NS)
  2. SPF record exists (dig TXT)
  3. DKIM record exists (dig TXT default._domainkey)
  4. DMARC record exists (dig TXT _dmarc)
  5. MX records exist (dig MX)

**Response:**
```json
{
  "results": [
    {
      "domain_id": "uuid1",
      "domain_name": "example.com",
      "status": "verified",
      "checks": {
        "nameservers": true,
        "spf": true,
        "dkim": true,
        "dmarc": true,
        "mx": true
      }
    },
    {
      "domain_id": "uuid2",
      "domain_name": "growth.com",
      "status": "failed",
      "checks": {
        "nameservers": true,
        "spf": false,
        "dkim": false,
        "dmarc": false,
        "mx": false
      },
      "error": "DNS records not yet configured by HyperTide"
    }
  ]
}
```

---

### NEW: POST /api/infrastructure/assign-provider-bulk

**Purpose:** Assign domains to Entra or Google provider type

**Body:**
```json
{
  "domain_ids": ["uuid1", "uuid2"],
  "provider": "entra" | "google"
}
```

**Validation:**
- Domains must not be in active HyperTide order
- Updates `domains.assigned_provider`

**Response:**
```json
{
  "updated": 2,
  "validation": {
    "entra_ready_orders": 1,
    "google_ready_orders": 0,
    "warnings": [
      "3 Entra domains total - can create 1 order with 1 domain remaining"
    ]
  }
}
```

---

### UPDATED: POST /api/infrastructure/order-hypertide-bulk

**Additional Validation:**
- All domains must have `nameserver_status = 'verified'`
- All domains must have `dns_records_configured = TRUE`
- All domains must have same `assigned_provider`
- Provider-specific count validation

**Updated Response:**
```json
{
  "order_job_id": "uuid",
  "status": "pending",
  "provider": "entra",
  "domains": ["example.com", "growthcheckout.com"],
  "expected_inboxes": 100,
  "monthly_cost": 50,
  "warnings": [
    "⚠ Browser automation required",
    "⚠ Manual payment step will pause automation",
    "⚠ No API exists - tracking limited"
  ]
}
```

---

## IMPLEMENTATION PRIORITIES

### Phase 1: DNS Flow Fix (Week 1) - CRITICAL ⚠️
1. Add nameserver columns to domains table
2. Build nameserver update endpoint
3. Build DNS verification endpoint
4. Update waterfall table to show DNS columns
5. Test with Dynadot + Porkbun APIs

### Phase 2: Provider Tracking (Week 2)
1. Add assigned_provider column
2. Build provider assignment endpoint
3. Add provider badges to UI
4. Add provider filter
5. Update HyperTide order validation

### Phase 3: HyperTide Reality Check (Week 3)
1. Document "No API" limitations in UI
2. Add manual payment warnings
3. Add "Poll HyperTide" manual button
4. Update progress tracking with realistic estimates
5. Add support email templates for domain swaps

### Phase 4-6: Continue original plan (Weeks 4-6)
- Bulk actions
- Real-time updates
- Polish & testing

---

## KEY TAKEAWAYS

### ✅ What Changed
1. **DNS now comes AFTER purchase** (moved from before)
2. **Added "Provider Assigned" column** to track Entra vs Google
3. **Documented HyperTide limitations** (no API, manual payments)
4. **DNSimple nameservers required** (not Cloudflare)
5. **Added nameserver migration step** (purchase → set NS → verify)

### ⚠️ Critical Constraints
1. **No HyperTide API** - all automation uses Playwright
2. **Manual payment step** - human intervention required
3. **Domain swaps are manual** - email support@hypertide.io
4. **DNS propagation wait** - 24-48 hours after nameserver change
5. **HyperTide provisioning timing** - 1-4 hours (uncontrollable)

### 🎯 Success Metrics
- **DNS migration success rate:** >95% (API reliability)
- **DNS verification within 48h:** >90% (propagation time)
- **HyperTide order creation:** >95% (browser automation reliability)
- **Manual payment completion:** 100% (human step)
- **Inbox sync detection:** <20 minutes after provisioning

---

**End of V2 Specification**

**Next Actions:**
1. Review corrected DNS flow with team
2. Decide: Cloudflare integration (custom solution) vs DNSimple requirement
3. Implement Phase 1 (DNS flow) immediately
4. Update hypertide_worker.py to validate DNS before orders
5. Build domain swap request UI (future enhancement)
