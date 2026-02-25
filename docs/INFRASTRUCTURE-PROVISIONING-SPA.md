# Infrastructure Provisioning SPA - Design Specification

**Application Name:** Infrastructure Command Center
**Type:** Single Page Application (React + TypeScript)
**Purpose:** Waterfall-style domain-to-inbox provisioning management
**Target Users:** Infrastructure Team, Operations
**Date:** 2026-02-25

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [User Flow](#user-flow)
3. [Waterfall Table Design](#waterfall-table-design)
4. [Column Definitions](#column-definitions)
5. [Bulk Action System](#bulk-action-system)
6. [Views & Filters](#views--filters)
7. [Database Schema](#database-schema)
8. [API Endpoints](#api-endpoints)
9. [Component Architecture](#component-architecture)
10. [Critical Business Rules](#critical-business-rules)
11. [Implementation Plan](#implementation-plan)

---

## Executive Summary

### The Problem
Currently, infrastructure provisioning requires navigating multiple pages (domains, purchasing, HyperTide automation) with no unified view of the complete pipeline. Users lose track of which domains are stuck in which stage.

### The Solution
A single waterfall-style table where **each column represents a provisioning stage**, records flow left-to-right, and bulk actions apply to selected records in each column.

### Key Features
- ✅ Client selector with workspace filtering
- ✅ Package-aware domain generation (Starter: 37 domains, Growth: 74 domains)
- ✅ Waterfall columns: Generated → Priced → Purchased → HyperTide → Provisioned → Synced
- ✅ Bulk actions per column (bulk price check, bulk purchase, bulk HyperTide order)
- ✅ Smart views: "Owned & Deployed", "New Candidates", "Stuck Pipelines"
- ✅ Sort by ownership status (user's domains at top)
- ✅ HyperTide order validation (2 domains for Entra, 5 for Google)
- ✅ Real-time progress tracking with sync worker integration

---

## User Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. SELECT CLIENT                                                │
│    - Dropdown of all clients with workspace_id                 │
│    - Displays current package (Starter: 37 domains, etc.)      │
│    - Shows fulfillment: "12/37 domains owned"                  │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. SELECT VIEW                                                  │
│    - "Owned & Deployed" (owned_by_client = TRUE)               │
│    - "New Candidates" (generated but not purchased)            │
│    - "Active Pipeline" (purchased but not yet synced)          │
│    - "All Domains" (everything for this client)                │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. WATERFALL TABLE                                              │
│    Each row = 1 domain                                          │
│    Each column = 1 stage in provisioning                        │
│    Checkbox selection for bulk actions                          │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. BULK ACTION BUTTONS (top of each column)                    │
│    - Select domains in that column                             │
│    - Click bulk action button                                   │
│    - Action applies to all selected                            │
│    - Progress modal shows real-time status                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Waterfall Table Design

### Visual Layout

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Client: [Acme Corp ▼]           Package: Starter (37 domains)         Status: 12/37 Owned | 8/37 Deployed  │
│ View: [Owned & Deployed ▼]      Filter: [All Types ▼]  [Search domain...                              ]   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              INFRASTRUCTURE PROVISIONING WATERFALL                                          │
├──────────┬───────────┬──────────┬──────────┬───────────┬────────────┬─────────┬──────────┬─────────────────┤
│ Select   │ Generated │ Priced   │ DNS OK   │ Purchased │ HyperTide  │ Ordered │ Provisioned │ Synced to DB│
│ [  all] │           │          │          │           │ Ready      │         │            │             │
│          │ [GENERATE]│ [CHECK]  │ [VERIFY] │ [PURCHASE]│ [ORDER]    │ [TRACK] │ [POLL]     │ [VIEW]      │
│          │  BULK     │  PRICES  │  DNS     │  BULK     │  HYPERTIDE │  STATUS │  HYPERTIDE │  INBOXES    │
│          │           │  BULK    │  BULK    │           │   BULK     │  BULK   │   BULK     │   BULK      │
├──────────┼───────────┼──────────┼──────────┼───────────┼────────────┼─────────┼──────────────────────────┤
│ ☑        │ example   │ $10.88 ✓│ Verified │ Purchased │ +2 Ready   │ Order   │ Provisioning│ 100 inboxes│
│          │ .com      │ (Dynadot)│ ✓ SPF    │ 2/24/26   │ Entra      │ #4521   │ 45%         │ synced ✓   │
│          │ Owned ✓   │          │ ✓ DKIM   │           │            │ Active  │ ETA: 2h     │            │
│          │ Deployed✓ │          │ ✓ DMARC  │           │            │         │             │            │
├──────────┼───────────┼──────────┼──────────┼───────────┼────────────┼─────────┼──────────────────────────┤
│ ☐        │ growth    │ $11.08   │ Pending  │ Available │ -          │ -       │ -           │ -          │
│          │ checkout  │ (Porkbun)│          │           │            │         │             │            │
│          │ .com      │          │          │           │            │         │             │            │
├──────────┼───────────┼──────────┼──────────┼───────────┼────────────┼─────────┼──────────────────────────┤
│ ☐        │ smart     │ Checking │ -        │ -         │ -          │ -       │ -           │ -          │
│          │ payments  │ ...      │          │           │            │         │             │            │
│          │ .com      │          │          │           │            │         │             │            │
├──────────┼───────────┼──────────┼──────────┼───────────┼────────────┼─────────┼──────────────────────────┤
│ ☐        │ ace       │ -        │ -        │ -         │ -          │ -       │ -           │ -          │
│          │ checkout  │          │          │           │            │         │             │            │
│          │ .com      │          │          │           │            │         │             │            │
└──────────┴───────────┴──────────┴──────────┴───────────┴────────────┴─────────┴──────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Legend:  ✓ Owned by Client   ✓ Deployed to Production   ⏱ In Progress   ⚠ Needs Attention   ❌ Failed      │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Column Definitions

### Column 1: Generated
**Purpose:** Domain name created and ready for price check
**Database Status:** `approval_status = 'available'`
**Display:**
- Domain name (with TLD)
- Generation timestamp
- Legitimacy score (0.0-1.0)
- Owned badge if `owned_by_client = TRUE`
- Deployed badge if domain has active inboxes

**Bulk Actions:**
- `[GENERATE BULK]` - Generate N more domains based on package deficit

**Cell Actions:**
- Click domain → View details modal
- Edit domain name (before purchase only)
- Delete candidate (removes from list)

---

### Column 2: Priced
**Purpose:** Registrar pricing fetched from Porkbun + Dynadot
**Database Status:** `price_checked_at IS NOT NULL AND cached_price IS NOT NULL`
**Display:**
- Lowest price with provider name (e.g., "$10.88 (Dynadot)")
- Both prices shown on hover:
  - Porkbun: $11.08 ✓
  - Dynadot: $10.88 ✓ (selected)
- Unavailable domains: "Unavailable" (gray out row)
- Stale prices (>24h): "⏱ Rechecking..."

**Bulk Actions:**
- `[CHECK PRICES BULK]` - Fetch prices for all selected domains

**Cell Actions:**
- Hover → See both registrar prices
- Click price → Force refresh single price

**Color Coding:**
- Green: < $11
- Yellow: $11-$15
- Red: > $15
- Gray: Unavailable

---

### Column 3: DNS OK
**Purpose:** Nameserver verification and DNS records check
**Database Status:** `nameserver_status = 'verified'`
**Display:**
- Verification status: "Verified ✓" | "Pending" | "Failed ❌"
- DNS record checklist (collapsed by default):
  - ✓ SPF record configured
  - ✓ DKIM record configured
  - ✓ DMARC record configured
  - ✓ MX records configured

**Bulk Actions:**
- `[VERIFY DNS BULK]` - Check nameservers for all selected

**Cell Actions:**
- Click "Pending" → Manual DNS check now
- Click "Failed" → Show error details + retry button
- Expand checklist → See full DNS configuration

**Wait Time:** 24-48 hours for DNS propagation after purchase

---

### Column 4: Purchased
**Purpose:** Domain bought from registrar
**Database Status:** `approval_status = 'purchased'`
**Display:**
- "Purchased ✓" with date (e.g., "2/24/26")
- Registrar used (Porkbun | Dynadot)
- Purchase job ID (clickable to view job details)
- Cost paid

**Bulk Actions:**
- `[PURCHASE BULK]` - Buy all selected domains from chosen registrar
  - Modal: "Purchase 5 domains for $54.40 from Dynadot?" [Confirm] [Cancel]
  - Progress bar shows per-domain purchase status

**Cell Actions:**
- Click date → View purchase receipt
- Click job ID → View full purchase job details

---

### Column 5: HyperTide Ready
**Purpose:** Domain eligible for HyperTide order creation
**Database Status:** `approval_status = 'purchased' AND nameserver_status = 'verified'`
**Display:**
- "+2 Ready Entra" (if 2 domains selected for Entra package)
- "+5 Ready Google" (if 5 domains selected for Google package)
- Validation errors:
  - "⚠ Need 2 domains for Entra order" (if only 1 selected)
  - "⚠ Need 5 domains for Google order" (if < 5 selected)

**Bulk Actions:**
- `[ORDER HYPERTIDE BULK]` - Create HyperTide inbox purchase job
  - Validates domain count (2 for Entra, 5 for Google)
  - Opens order configuration modal:
    - Provider type: [Entra] [Google]
    - Forwarding domain: [client.com]
    - Company name: [Acme Corp]
    - EmailBison workspace: [Acme Workspace ▼]
    - Sender names: [+ Add Name]
  - Creates `inbox_purchase_jobs` record
  - Triggers HyperTide worker

**Cell Actions:**
- Click "+2 Ready" → Pre-select those 2 domains for order
- Click validation warning → Show which domains need to be added

---

### Column 6: Ordered
**Purpose:** HyperTide order created and in progress
**Database Status:** `purchase_job_id IS NOT NULL AND purchase_job_status IN ('pending', 'executing')`
**Display:**
- Order ID: "Order #4521"
- Status badge:
  - 🟡 Pending (yellow)
  - 🔵 Executing (blue)
  - 🟢 Completed (green)
  - 🔴 Failed (red)
- Current step (if executing):
  - "Choosing plan..."
  - "Configuring domains..."
  - "Awaiting payment ⏱"
  - "Processing order..."
- Progress bar (0-100%)

**Bulk Actions:**
- `[TRACK STATUS BULK]` - Refresh status for all selected orders

**Cell Actions:**
- Click order ID → Open order tracking modal (detailed steps)
- Click "Awaiting payment" → Open Stripe checkout URL
- Click "Failed" → View error log + retry button

---

### Column 7: Provisioned
**Purpose:** HyperTide has created inboxes in EmailBison workspace
**Database Status:** `purchase_job_status = 'completed' BUT inboxes not yet synced to database`
**Display:**
- "Provisioning..." with spinner (checking HyperTide)
- Progress: "45% (45/100 inboxes)"
- ETA: "2 hours remaining"
- When complete: "100 inboxes provisioned ✓"

**Bulk Actions:**
- `[POLL HYPERTIDE BULK]` - Check provisioning status for all selected

**Cell Actions:**
- Click "Provisioning" → Open HyperTide dashboard (external link)
- Click progress → Force refresh provisioning status

**Note:** This stage depends on HyperTide's external timing (we don't control)

---

### Column 8: Synced to DB
**Purpose:** Inboxes detected by EmailBison sync worker and stored in database
**Database Status:** `sender_accounts` records exist for this domain
**Display:**
- "100 inboxes synced ✓" (Entra)
- "15 inboxes synced ✓" (Google)
- Inbox breakdown (hover):
  - 95 live, 5 warmup
  - ESP: Microsoft
  - Warmup enabled: Yes
  - Avg health score: 87
- Last sync timestamp: "2 min ago"

**Bulk Actions:**
- `[VIEW INBOXES BULK]` - Navigate to inbox management page with these domains filtered

**Cell Actions:**
- Click inbox count → Open inbox list modal (filterable, sortable)
- Click health score → Navigate to health monitoring page
- Click "Refresh" → Trigger immediate sync worker run (force sync)

---

## Bulk Action System

### Selection System

**Checkbox Behavior:**
- Header checkbox per column: Select all in that column
- Row checkboxes: Select individual domains
- Selection persists across view changes (until cleared)
- Selected count badge: "5 domains selected"

**Smart Selection:**
- "Select all available for pricing" - Selects only domains without prices
- "Select all ready for purchase" - Selects only priced domains
- "Select ready for HyperTide" - Auto-groups into valid HyperTide orders (2/5 domains)

---

### Bulk Action Modals

**Price Check Bulk:**
```
┌─────────────────────────────────────────────┐
│ Checking Prices for 12 Domains             │
├─────────────────────────────────────────────┤
│ Progress: ████████░░ 8/12 (67%)            │
│                                             │
│ ✓ example.com - $10.88 (Dynadot)          │
│ ✓ growthcheckout.com - $11.08 (Porkbun)   │
│ ✓ smartpayments.com - $10.88 (Dynadot)    │
│ ⏱ acecheckout.com - Checking...            │
│ ⏱ tryselery.com - Checking...              │
│ ⏱ seleryhq.com - Checking...               │
│ ⏱ launchpayments.com - Checking...         │
│                                             │
│ [View Details] [Close]                     │
└─────────────────────────────────────────────┘
```

**Purchase Bulk:**
```
┌─────────────────────────────────────────────┐
│ Purchase 5 Domains                          │
├─────────────────────────────────────────────┤
│ Registrar: Dynadot (lowest prices)          │
│                                             │
│ Domains:                                    │
│ • example.com ($10.88)                     │
│ • growthcheckout.com ($10.88)              │
│ • smartpayments.com ($10.88)               │
│ • acecheckout.com ($10.88)                 │
│ • tryselery.com ($11.08 from Porkbun)      │
│                                             │
│ Total Cost: $54.60                          │
│ Estimated Time: 2-3 minutes                 │
│                                             │
│ [Cancel] [Purchase All]                    │
└─────────────────────────────────────────────┘

(After clicking Purchase All)

┌─────────────────────────────────────────────┐
│ Purchasing Domains...                       │
├─────────────────────────────────────────────┤
│ Progress: ███████░░░ 3/5 (60%)             │
│                                             │
│ ✓ example.com - Purchased                  │
│ ✓ growthcheckout.com - Purchased           │
│ ✓ smartpayments.com - Purchased            │
│ ⏱ acecheckout.com - Purchasing...          │
│ ⏱ tryselery.com - Queued                   │
│                                             │
│ [View Purchase Jobs] [Close When Done]     │
└─────────────────────────────────────────────┘
```

**HyperTide Order Bulk:**
```
┌─────────────────────────────────────────────┐
│ Create HyperTide Order                      │
├─────────────────────────────────────────────┤
│ Provider Type:                              │
│ ○ Entra (2 domains selected ✓)             │
│ ○ Google (5 domains needed ⚠)              │
│                                             │
│ Selected Domains (2):                       │
│ • example.com                              │
│ • growthcheckout.com                       │
│                                             │
│ Configuration:                              │
│ Forwarding Domain: [acmecorp.com      ]    │
│ Company Name:      [Acme Corp         ]    │
│ EmailBison Workspace: [Acme ▼]             │
│                                             │
│ Sender Names (3):                          │
│ • Chris Booth                              │
│ • Sarah Johnson                            │
│ • Mike Chen                                │
│ [+ Add Name]                               │
│                                             │
│ Expected Output:                            │
│ • 100 inboxes (50 per domain)              │
│ • $50/month subscription                    │
│ • 5,000 emails/month capacity              │
│                                             │
│ [Cancel] [Create Order]                    │
└─────────────────────────────────────────────┘
```

---

## Views & Filters

### Primary Views

**1. Owned & Deployed (Default)**
- **Filter:** `owned_by_client = TRUE`
- **Sort:** Deployed first, then by domain name
- **Purpose:** See active infrastructure in production
- **Expected Count:** Matches package size when fully provisioned

**2. New Candidates**
- **Filter:** `approval_status = 'available'` (not yet purchased)
- **Sort:** By legitimacy score DESC, then alphabetical
- **Purpose:** Review and purchase newly generated domains
- **Expected Count:** Growing until purchased

**3. Active Pipeline**
- **Filter:** `approval_status IN ('purchased', 'provisioning')` but not yet synced
- **Sort:** By stage (furthest along first), then by created_at
- **Purpose:** Monitor domains in provisioning process
- **Expected Count:** Temporary (shrinks as domains sync)

**4. All Domains**
- **Filter:** None (show everything for this client)
- **Sort:** By stage, then by owned_by_client DESC, then alphabetical
- **Purpose:** Complete visibility for troubleshooting
- **Expected Count:** All domains ever generated for client

### Secondary Filters

**ESP Type Filter:**
- All Types
- Entra (Microsoft) only
- Google only

**Status Filter:**
- All Statuses
- Available (not purchased)
- Purchased (bought but not ordered)
- Ordered (HyperTide in progress)
- Provisioned (inboxes created)
- Synced (in database)
- Failed (errors at any stage)

**Time Range Filter:**
- Last 7 days
- Last 30 days
- Last 90 days
- All time

### Search
- **Input:** Domain name search box
- **Behavior:** Filter domains matching substring (case-insensitive)
- **Example:** "checkout" shows all domains containing "checkout"

---

## Database Schema

### New Table: infrastructure_provisioning_state

**Purpose:** Track complete provisioning state per domain across all stages

```sql
CREATE TABLE infrastructure_provisioning_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain_id UUID NOT NULL REFERENCES domains(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),

    -- Ownership tracking
    owned_by_client BOOLEAN DEFAULT FALSE,
    deployed_to_production BOOLEAN DEFAULT FALSE,

    -- Stage 1: Generation
    generated_at TIMESTAMP,
    legitimacy_score DECIMAL(3,2),
    generation_method VARCHAR(20),  -- 'ai' | 'pattern'

    -- Stage 2: Pricing
    price_checked_at TIMESTAMP,
    porkbun_price DECIMAL(10,2),
    porkbun_available BOOLEAN,
    dynadot_price DECIMAL(10,2),
    dynadot_available BOOLEAN,
    selected_provider VARCHAR(20),  -- 'porkbun' | 'dynadot'
    cached_price DECIMAL(10,2),
    price_stale BOOLEAN GENERATED ALWAYS AS (
        price_checked_at < NOW() - INTERVAL '24 hours'
    ) STORED,

    -- Stage 3: DNS Verification
    nameserver_status VARCHAR(20),  -- 'pending' | 'verified' | 'failed'
    nameserver_verified_at TIMESTAMP,
    dns_records_configured BOOLEAN DEFAULT FALSE,
    spf_configured BOOLEAN DEFAULT FALSE,
    dkim_configured BOOLEAN DEFAULT FALSE,
    dmarc_configured BOOLEAN DEFAULT FALSE,
    mx_configured BOOLEAN DEFAULT FALSE,

    -- Stage 4: Purchase
    purchased_at TIMESTAMP,
    purchase_job_id UUID REFERENCES domain_purchase_jobs(id),
    purchase_cost DECIMAL(10,2),

    -- Stage 5: HyperTide Order
    hypertide_order_job_id UUID REFERENCES inbox_purchase_jobs(id),
    hypertide_order_created_at TIMESTAMP,
    hypertide_order_status VARCHAR(20),  -- 'pending' | 'executing' | 'completed' | 'failed'
    hypertide_current_step TEXT,
    hypertide_progress_pct INTEGER,
    hypertide_order_id TEXT,  -- HyperTide's external order ID

    -- Stage 6: Provisioning (HyperTide side)
    provisioning_started_at TIMESTAMP,
    provisioning_completed_at TIMESTAMP,
    expected_inbox_count INTEGER,
    provisioned_inbox_count INTEGER,
    provisioning_eta TIMESTAMP,

    -- Stage 7: Database Sync
    synced_at TIMESTAMP,
    synced_inbox_count INTEGER,
    last_sync_check_at TIMESTAMP,

    -- Error tracking
    last_error TEXT,
    last_error_at TIMESTAMP,
    retry_count INTEGER DEFAULT 0,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_infra_prov_workspace ON infrastructure_provisioning_state(workspace_id);
CREATE INDEX idx_infra_prov_domain ON infrastructure_provisioning_state(domain_id);
CREATE INDEX idx_infra_prov_owned ON infrastructure_provisioning_state(owned_by_client, deployed_to_production);
CREATE INDEX idx_infra_prov_stage ON infrastructure_provisioning_state(hypertide_order_status, nameserver_status);

-- Updated timestamp trigger
CREATE TRIGGER update_infra_prov_timestamp
BEFORE UPDATE ON infrastructure_provisioning_state
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
```

### Modified Table: domains

**Add ownership tracking:**
```sql
ALTER TABLE domains ADD COLUMN IF NOT EXISTS owned_by_client BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS deployed_to_production BOOLEAN DEFAULT FALSE;
```

### View: v_infrastructure_waterfall

**Purpose:** Denormalized view optimized for waterfall table queries

```sql
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,

    -- Ownership
    COALESCE(ips.owned_by_client, FALSE) as owned,
    COALESCE(ips.deployed_to_production, FALSE) as deployed,

    -- Stage 1: Generated
    COALESCE(ips.generated_at, d.created_at) as generated_at,
    ips.legitimacy_score,

    -- Stage 2: Priced
    ips.price_checked_at,
    ips.cached_price,
    ips.selected_provider,
    ips.price_stale,
    CASE
        WHEN ips.porkbun_available = FALSE AND ips.dynadot_available = FALSE THEN 'unavailable'
        WHEN ips.price_checked_at IS NULL THEN 'not_checked'
        WHEN ips.price_stale = TRUE THEN 'stale'
        ELSE 'valid'
    END as price_status,

    -- Stage 3: DNS
    ips.nameserver_status,
    ips.nameserver_verified_at,
    ips.dns_records_configured,

    -- Stage 4: Purchased
    d.purchased_at,
    ips.purchase_job_id,

    -- Stage 5: HyperTide Ready
    CASE
        WHEN d.approval_status = 'purchased' AND ips.nameserver_status = 'verified'
        THEN TRUE
        ELSE FALSE
    END as hypertide_ready,

    -- Stage 6: Ordered
    ips.hypertide_order_job_id,
    ips.hypertide_order_status,
    ips.hypertide_current_step,
    ips.hypertide_progress_pct,

    -- Stage 7: Provisioned
    ips.provisioning_completed_at,
    ips.expected_inbox_count,
    ips.provisioned_inbox_count,
    CASE
        WHEN ips.provisioned_inbox_count >= ips.expected_inbox_count THEN 'complete'
        WHEN ips.provisioning_started_at IS NOT NULL THEN 'in_progress'
        ELSE 'pending'
    END as provisioning_status,

    -- Stage 8: Synced
    ips.synced_at,
    ips.synced_inbox_count,
    (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id) as db_inbox_count,
    CASE
        WHEN ips.synced_inbox_count >= ips.expected_inbox_count THEN 'complete'
        WHEN ips.synced_at IS NOT NULL THEN 'partial'
        ELSE 'pending'
    END as sync_status,

    -- Current stage (for sorting/filtering)
    CASE
        WHEN ips.synced_at IS NOT NULL THEN 8
        WHEN ips.provisioning_completed_at IS NOT NULL THEN 7
        WHEN ips.hypertide_order_status IN ('executing', 'pending') THEN 6
        WHEN d.approval_status = 'purchased' AND ips.nameserver_status = 'verified' THEN 5
        WHEN d.purchased_at IS NOT NULL THEN 4
        WHEN ips.nameserver_status = 'verified' THEN 3
        WHEN ips.price_checked_at IS NOT NULL THEN 2
        ELSE 1
    END as current_stage,

    -- Error tracking
    ips.last_error,
    ips.last_error_at

FROM domains d
LEFT JOIN infrastructure_provisioning_state ips ON ips.domain_id = d.id
WHERE d.is_active = TRUE;
```

---

## API Endpoints

### GET /api/infrastructure/:workspaceId/waterfall

**Purpose:** Fetch all domains for waterfall table

**Query Parameters:**
- `view` - "owned" | "candidates" | "pipeline" | "all" (default: "owned")
- `esp` - "entra" | "google" | null (filter by ESP type)
- `status` - "available" | "purchased" | "ordered" | "provisioned" | "synced" | null
- `search` - domain name substring search
- `sortBy` - "stage" | "name" | "price" | "date" (default: "stage")
- `sortOrder` - "asc" | "desc" (default: "asc")

**Response:**
```json
{
  "workspace": {
    "id": "uuid",
    "name": "Acme Corp",
    "package": "starter",
    "expected_domains": 37,
    "owned_domains": 12,
    "deployed_domains": 8
  },
  "domains": [
    {
      "domain_id": "uuid",
      "domain_name": "example.com",
      "owned": true,
      "deployed": true,
      "current_stage": 8,
      "stages": {
        "generated": {
          "timestamp": "2026-02-24T10:00:00Z",
          "legitimacy_score": 0.95
        },
        "priced": {
          "timestamp": "2026-02-24T10:05:00Z",
          "price": 10.88,
          "provider": "dynadot",
          "status": "valid"
        },
        "dns": {
          "status": "verified",
          "timestamp": "2026-02-25T10:00:00Z",
          "records": {
            "spf": true,
            "dkim": true,
            "dmarc": true,
            "mx": true
          }
        },
        "purchased": {
          "timestamp": "2026-02-24T11:00:00Z",
          "job_id": "uuid",
          "cost": 10.88
        },
        "hypertide_ready": true,
        "ordered": {
          "job_id": "uuid",
          "status": "completed",
          "order_id": "HT-4521",
          "progress": 100
        },
        "provisioned": {
          "status": "complete",
          "expected": 100,
          "provisioned": 100,
          "timestamp": "2026-02-24T14:00:00Z"
        },
        "synced": {
          "status": "complete",
          "inbox_count": 100,
          "timestamp": "2026-02-24T14:30:00Z"
        }
      }
    }
  ],
  "summary": {
    "total": 37,
    "by_stage": {
      "generated": 25,
      "priced": 20,
      "purchased": 15,
      "ordered": 10,
      "provisioned": 8,
      "synced": 12
    }
  }
}
```

---

### POST /api/infrastructure/generate-bulk

**Purpose:** Generate N domains for a workspace

**Body:**
```json
{
  "workspace_id": "uuid",
  "count": 10,
  "method": "ai" | "pattern",
  "package_type": "starter" | "growth"
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "running",
  "expected_count": 10
}
```

---

### POST /api/infrastructure/check-prices-bulk

**Purpose:** Check prices for multiple domains

**Body:**
```json
{
  "domain_ids": ["uuid1", "uuid2", "uuid3"]
}
```

**Response:**
```json
{
  "job_id": "uuid",
  "status": "running",
  "total_domains": 3
}
```

**Poll Status:** `GET /api/infrastructure/price-check/:jobId/status`

---

### POST /api/infrastructure/purchase-bulk

**Purpose:** Purchase multiple domains

**Body:**
```json
{
  "workspace_id": "uuid",
  "domain_ids": ["uuid1", "uuid2"],
  "registrar": "dynadot" | "porkbun" | "auto"
}
```

**Response:**
```json
{
  "purchase_job_id": "uuid",
  "status": "pending",
  "total_cost": 21.76,
  "estimated_duration": "2-3 minutes"
}
```

---

### POST /api/infrastructure/order-hypertide-bulk

**Purpose:** Create HyperTide inbox purchase order

**Body:**
```json
{
  "workspace_id": "uuid",
  "provider_type": "entra" | "google",
  "domain_ids": ["uuid1", "uuid2"],
  "config": {
    "forwarding_domain": "acmecorp.com",
    "company_name": "Acme Corp",
    "bison_workspace_name": "Acme",
    "sender_names": [
      {"firstName": "Chris", "lastName": "Booth"},
      {"firstName": "Sarah", "lastName": "Johnson"}
    ]
  }
}
```

**Validation:**
- Entra: Exactly 2 domains required
- Google: Exactly 5 domains required
- All domains must have `nameserver_status = 'verified'`

**Response:**
```json
{
  "order_job_id": "uuid",
  "status": "pending",
  "expected_inboxes": 100,
  "monthly_cost": 50
}
```

---

### GET /api/infrastructure/order/:jobId/status

**Purpose:** Poll HyperTide order status

**Response:**
```json
{
  "job_id": "uuid",
  "status": "executing",
  "current_step": "Configuring domains...",
  "progress": 45,
  "estimated_completion": "2026-02-24T15:30:00Z",
  "stripe_checkout_url": "https://..." (if status = 'awaiting_payment')
}
```

---

### POST /api/infrastructure/sync-check-bulk

**Purpose:** Force sync check for multiple domains

**Body:**
```json
{
  "domain_ids": ["uuid1", "uuid2"]
}
```

**Response:**
```json
{
  "triggered": true,
  "next_sync_at": "2026-02-24T15:05:00Z"
}
```

---

## Component Architecture

### File Structure

```
/infrastructure-command-center/
├── src/
│   ├── pages/
│   │   └── InfrastructureProvisioningPage.tsx   ← Main page
│   ├── components/
│   │   ├── ClientSelector.tsx                   ← Workspace dropdown
│   │   ├── ViewSelector.tsx                     ← View tabs
│   │   ├── WaterfallTable.tsx                   ← Core table component
│   │   ├── WaterfallHeader.tsx                  ← Column headers with bulk actions
│   │   ├── WaterfallRow.tsx                     ← Single domain row
│   │   ├── cells/
│   │   │   ├── GeneratedCell.tsx                ← Stage 1
│   │   │   ├── PricedCell.tsx                   ← Stage 2
│   │   │   ├── DNSCell.tsx                      ← Stage 3
│   │   │   ├── PurchasedCell.tsx                ← Stage 4
│   │   │   ├── HyperTideReadyCell.tsx           ← Stage 5
│   │   │   ├── OrderedCell.tsx                  ← Stage 6
│   │   │   ├── ProvisionedCell.tsx              ← Stage 7
│   │   │   └── SyncedCell.tsx                   ← Stage 8
│   │   ├── modals/
│   │   │   ├── BulkPriceCheckModal.tsx
│   │   │   ├── BulkPurchaseModal.tsx
│   │   │   ├── HyperTideOrderModal.tsx
│   │   │   ├── OrderTrackingModal.tsx
│   │   │   └── InboxListModal.tsx
│   │   └── PackageSummary.tsx                   ← Package fulfillment status
│   ├── hooks/
│   │   ├── useWaterfallData.ts                  ← Main data fetching hook
│   │   ├── useBulkActions.ts                    ← Bulk action handlers
│   │   ├── useSelection.ts                      ← Checkbox selection state
│   │   └── usePolling.ts                        ← Real-time status polling
│   ├── api/
│   │   └── infrastructure.ts                    ← API client
│   └── types/
│       └── infrastructure.ts                    ← TypeScript types
└── README.md
```

---

### Component: WaterfallTable.tsx

**Responsibilities:**
- Renders full table with 8 stage columns
- Manages selection state (checkboxes)
- Handles sorting
- Real-time updates via polling

**Props:**
```typescript
interface WaterfallTableProps {
  workspaceId: string;
  view: 'owned' | 'candidates' | 'pipeline' | 'all';
  filters: {
    esp?: 'entra' | 'google';
    status?: string;
    search?: string;
  };
  onDomainSelect: (domainIds: string[]) => void;
}
```

**State:**
```typescript
const [selectedDomains, setSelectedDomains] = useState<Set<string>>(new Set());
const [sortBy, setSortBy] = useState<'stage' | 'name' | 'price'>('stage');
const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc');
```

---

### Component: BulkPurchaseModal.tsx

**Purpose:** Handle bulk domain purchases with progress tracking

**State Machine:**
```typescript
type PurchaseState =
  | { type: 'confirming'; domains: Domain[]; totalCost: number }
  | { type: 'purchasing'; progress: number; results: PurchaseResult[] }
  | { type: 'completed'; successful: number; failed: number };
```

**Progress Tracking:**
```typescript
const [purchaseProgress, setPurchaseProgress] = useState({
  total: 0,
  completed: 0,
  successful: 0,
  failed: 0,
  current: null as string | null
});
```

---

### Hook: useWaterfallData.ts

**Purpose:** Fetch and manage waterfall table data with real-time updates

```typescript
export function useWaterfallData(
  workspaceId: string,
  view: ViewType,
  filters: Filters
) {
  const [data, setData] = useState<WaterfallData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch data
  useEffect(() => {
    fetchWaterfallData();
  }, [workspaceId, view, filters]);

  // Poll for updates (every 30s)
  useInterval(() => {
    if (hasActiveJobs(data)) {
      fetchWaterfallData(/* silent refresh */);
    }
  }, 30000);

  const fetchWaterfallData = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const response = await api.getWaterfallData(workspaceId, view, filters);
      setData(response);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return { data, loading, error, refresh: fetchWaterfallData };
}
```

---

## Critical Business Rules

### 1. HyperTide Order Domain Count Validation

**Entra:** MUST be exactly 2 domains per order
**Google:** MUST be exactly 5 domains per order

**Enforcement:**
- UI prevents order creation with incorrect counts
- API validates and returns 400 error if violated
- Bulk action groups domains automatically into valid order sizes

---

### 2. Package Fulfillment Tracking

**Starter Package:**
- Expected: 37 domains (12 Entra + 25 Google)
- UI shows "12/37 owned" progress indicator
- When 37 reached, disable "Generate More" button

**Growth Package:**
- Expected: 74 domains (24 Entra + 50 Google)
- UI shows "24/74 owned" progress indicator

**Database Query:**
```sql
SELECT
  package_type,
  COUNT(*) FILTER (WHERE owned_by_client = TRUE) as owned,
  COUNT(*) as total,
  CASE package_type
    WHEN 'starter' THEN 37
    WHEN 'growth' THEN 74
  END as expected
FROM domains d
JOIN workspaces w ON w.id = d.workspace_id
WHERE d.workspace_id = $1
GROUP BY package_type;
```

---

### 3. Domain Ownership Sorting

**Rule:** Owned domains ALWAYS appear at top of list, regardless of view

**Sort Order:**
1. `owned_by_client DESC` (owned first)
2. `deployed_to_production DESC` (deployed before non-deployed)
3. `current_stage DESC` (furthest along first)
4. `domain_name ASC` (alphabetical)

---

### 4. View Isolation

**Rule:** Switching views does NOT clear selection OR trigger actions

**Behavior:**
- Selected domains persist across view changes
- User can select domains in "Candidates" view
- Switch to "All Domains" view
- Selected domains remain selected
- Bulk action applies only to selected domains

---

### 5. DNS Propagation Wait Time

**Rule:** Nameserver verification not available until 24 hours after purchase

**UI Behavior:**
- "DNS OK" column shows "⏱ Propagating (18h remaining)"
- Bulk DNS check disabled until timer expires
- Manual check shows warning: "DNS may not be propagated yet"

---

### 6. HyperTide Provisioning Timing

**Rule:** We do NOT control when inboxes appear in EmailBison

**UI Handling:**
- "Provisioned" column shows "⏱ Awaiting HyperTide..."
- Estimated time: "1-4 hours"
- Poll every 5 minutes
- Show last check time: "Checked 3 min ago"

---

### 7. Sync Worker Detection

**Rule:** EmailBison sync worker runs every 15 minutes

**UI Behavior:**
- "Synced" column shows next sync time: "Next check in 12 min"
- Manual "Force Sync" button triggers immediate sync
- After force sync, disable button for 5 minutes (cooldown)

---

## Implementation Plan

### Phase 1: Database & API (Week 1)

**Tasks:**
1. Create `infrastructure_provisioning_state` table
2. Create `v_infrastructure_waterfall` view
3. Implement API endpoints:
   - GET /api/infrastructure/:workspaceId/waterfall
   - POST /api/infrastructure/generate-bulk
   - POST /api/infrastructure/check-prices-bulk
   - POST /api/infrastructure/purchase-bulk
   - POST /api/infrastructure/order-hypertide-bulk
   - GET /api/infrastructure/order/:jobId/status
4. Add ownership tracking to existing domains
5. Test with sample data

---

### Phase 2: Core UI Components (Week 2)

**Tasks:**
1. Build WaterfallTable.tsx (core table)
2. Build 8 cell components (one per stage)
3. Build ClientSelector.tsx
4. Build ViewSelector.tsx
5. Implement selection system (checkboxes)
6. Basic styling (Tailwind CSS)

---

### Phase 3: Bulk Actions (Week 3)

**Tasks:**
1. Build BulkPriceCheckModal.tsx
2. Build BulkPurchaseModal.tsx
3. Build HyperTideOrderModal.tsx
4. Implement progress tracking system
5. Connect to API endpoints
6. Error handling and retries

---

### Phase 4: Real-Time Updates (Week 4)

**Tasks:**
1. Implement usePolling hook
2. Add WebSocket support (optional)
3. Build OrderTrackingModal.tsx
4. Add "Force Sync" functionality
5. Optimize polling intervals based on stage

---

### Phase 5: Views & Filters (Week 5)

**Tasks:**
1. Implement view switching logic
2. Add ESP filter dropdown
3. Add status filter dropdown
4. Add domain search
5. Implement sorting controls
6. Test all filter combinations

---

### Phase 6: Polish & Testing (Week 6)

**Tasks:**
1. Add loading skeletons
2. Add empty states
3. Mobile responsiveness
4. Error boundary components
5. Integration testing
6. Performance optimization (virtualization for 100+ rows)
7. Documentation

---

## Success Metrics

### User Efficiency
- **Time to provision 37 domains:** < 30 minutes (vs 2+ hours manual)
- **Clicks to create HyperTide order:** 5 clicks (vs 20+ clicks)
- **Domain generation to sync:** < 4 hours (with HyperTide delay)

### System Reliability
- **Price check success rate:** > 95%
- **Purchase success rate:** > 99%
- **HyperTide order creation success:** > 95%
- **Sync detection latency:** < 15 minutes

### User Satisfaction
- **"Can see entire pipeline at once"** - No more switching between 5 pages
- **"Bulk actions save huge time"** - Select 10 domains, click once
- **"Always know what's stuck"** - Visual indicators for errors

---

## Future Enhancements

### Phase 2 Features
- **Drag-and-drop domain ordering** (arrange before HyperTide order)
- **Automated retry logic** (retry failed purchases automatically)
- **Email notifications** (when HyperTide order completes)
- **Domain swap integration** (when domains die, request swap)
- **Cost tracking** (total spend per client)
- **Forecasting** (predict when domains will be fully provisioned)

### Advanced Features
- **Kanban view** (alternative to waterfall table)
- **Gantt chart** (timeline view of provisioning)
- **Capacity planning** (suggest when to order more inboxes)
- **A/B testing** (compare Entra vs Google performance per client)

---

**End of Specification**

**Next Steps:**
1. Review this spec with team
2. Create database migration for `infrastructure_provisioning_state` table
3. Build API endpoints
4. Start Phase 1 implementation

**Questions for Product/Business:**
1. Confirm package sizes (Starter: 37, Growth: 74)
2. Confirm HyperTide order requirements (2 for Entra, 5 for Google)
3. Confirm monthly cost ($50 per order)
4. Any additional stages or columns needed?
5. Access control (who can purchase domains?)

**Technical Dependencies:**
- PostgreSQL database with UUID support
- React 18+ with TypeScript
- Tailwind CSS for styling
- React Query or SWR for data fetching
- Zustand or Redux for global state (selection)
- Date-fns for timestamp formatting
