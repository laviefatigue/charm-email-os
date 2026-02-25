# Infrastructure Provisioning SPA - Minimal Database Changes

**Date:** 2026-02-25
**Purpose:** Document only the NEW fields needed for Infrastructure Provisioning SPA

---

## ✅ EXISTING FIELDS (Already in Database)

The `domains` table already has **most fields we need**:

### DNS Tracking (Already Exists)
- ✅ `nameservers_updated_at` - When nameservers were changed
- ✅ `nameserver_status` - varchar(20) - Status of nameserver migration
- ✅ `nameserver_verified_at` - When DNS verification completed
- ✅ `current_nameservers` - text[] - Array of current nameservers

### Pricing (Already Exists)
- ✅ `porkbun_price` - Porkbun pricing
- ✅ `porkbun_available` - Availability at Porkbun
- ✅ `dynadot_price` - Dynadot pricing
- ✅ `dynadot_available` - Availability at Dynadot
- ✅ `cached_price` - Lowest price
- ✅ `selected_provider` - Chosen registrar
- ✅ `price_checked_at` - Last price check timestamp

### Purchase (Already Exists)
- ✅ `purchased_at` - Purchase timestamp
- ✅ `purchase_job_id` - FK to inbox_purchase_jobs
- ✅ `purchase_job_status` - Job status text

### Provider/Infrastructure (Already Exists)
- ✅ `provider` - varchar(100) - Provider name
- ✅ `infrastructure_type` - varchar(20) - Infrastructure classification

### Ownership (Already Exists)
- ✅ `approval_status` - varchar(20) - Domain approval status
- ✅ `domain_source` - varchar(20) - generated/purchased/legacy

---

## ❌ MISSING FIELDS (Need to Add)

### 1. DNS Record Verification Flags

**Purpose:** Track which DNS records HyperTide has configured

```sql
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS spf_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dkim_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dmarc_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS mx_configured BOOLEAN DEFAULT FALSE;

-- Computed column for overall DNS readiness
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS dns_records_configured BOOLEAN
  GENERATED ALWAYS AS (
    spf_configured AND dkim_configured AND dmarc_configured AND mx_configured
  ) STORED;
```

**Why Needed:** To show DNS verification checklist in UI
**Alternative:** Could use JSONB field `dns_records` instead of 5 boolean columns

---

### 2. Provider Assignment (Use Existing Field)

**Current:** `infrastructure_type` varchar(20) exists but is always NULL
**Proposed:** Repurpose this field for Entra vs Google assignment

```sql
-- Add check constraint to existing field
ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_infrastructure_type_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_infrastructure_type_check
  CHECK (infrastructure_type IS NULL OR infrastructure_type IN ('entra', 'google'));

-- Add index (already exists: idx_domains_infrastructure)
```

**Why Repurpose:** Field exists but unused (always NULL per database audit)
**Benefit:** No new field needed, just add constraints

---

### 3. Ownership Flags (Use Existing Field)

**Current:** `approval_status` can track ownership
**Values Already Used:** 'pending', 'available', 'purchased', 'active'

**Proposed:** Add new statuses instead of boolean flags

```sql
-- Extend approval_status values
-- 'owned' = owned by client
-- 'deployed' = deployed to production
-- No schema change needed, just use existing field
```

**Alternative (if boolean flags preferred):**
```sql
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS owned_by_client BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS deployed_to_production BOOLEAN DEFAULT FALSE;

CREATE INDEX idx_domains_ownership ON domains(owned_by_client, deployed_to_production);
```

**Recommendation:** Use `approval_status` extension (no new fields)

---

## 📊 COMPLETE WATERFALL QUERY (Using Existing Fields)

```sql
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,

    -- Stage 1: Generated
    d.created_at as generated_at,
    d.legitimacy_score,
    d.domain_source,

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
    d.purchase_job_status,

    -- Stage 4: DNS Moved (use existing nameservers_updated_at)
    d.nameservers_updated_at,
    d.current_nameservers,
    CASE
        WHEN d.nameservers_updated_at IS NULL THEN 'not_set'
        WHEN d.nameservers_updated_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
        ELSE 'propagated'
    END as dns_migration_status,

    -- Stage 5: DNS Verified (use existing nameserver_status)
    d.nameserver_status,
    d.nameserver_verified_at,
    -- NEW: DNS record flags
    COALESCE(d.spf_configured, FALSE) as spf_configured,
    COALESCE(d.dkim_configured, FALSE) as dkim_configured,
    COALESCE(d.dmarc_configured, FALSE) as dmarc_configured,
    COALESCE(d.mx_configured, FALSE) as mx_configured,
    COALESCE(d.dns_records_configured, FALSE) as dns_records_configured,

    -- Stage 6: Provider Assigned (use existing infrastructure_type)
    d.infrastructure_type as assigned_provider,

    -- Stage 7: HyperTide Ordered (use existing purchase_job_id FK)
    ipj.id as hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.provider_type as hypertide_provider,

    -- Stage 8: Provisioned
    CASE
        WHEN ipj.status = 'completed' AND NOT EXISTS (
            SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id
        ) THEN 'awaiting_sync'
        WHEN ipj.status = 'completed' THEN 'synced'
        WHEN ipj.status IN ('executing', 'pending') THEN 'provisioning'
        ELSE 'not_started'
    END as provisioning_status,

    -- Stage 9: Synced
    (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id) as synced_inbox_count,
    (SELECT MAX(created_at) FROM sender_accounts sa WHERE sa.domain_id = d.id) as last_inbox_synced_at,

    -- Expected inbox count based on provider
    CASE
        WHEN d.infrastructure_type = 'entra' THEN 100
        WHEN d.infrastructure_type = 'google' THEN 15
        ELSE 0
    END as expected_inbox_count,

    -- Current stage (for sorting)
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

    -- Ownership (use approval_status)
    CASE
        WHEN d.approval_status IN ('owned', 'deployed', 'active') THEN TRUE
        ELSE FALSE
    END as owned_by_client,

    CASE
        WHEN d.approval_status = 'deployed' THEN TRUE
        ELSE FALSE
    END as deployed_to_production

FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
WHERE d.is_active = TRUE;
```

---

## 🗄️ MINIMAL MIGRATION SCRIPT

```sql
-- Migration: Add DNS record verification flags only
-- Date: 2026-02-25
-- Purpose: Infrastructure Provisioning SPA

BEGIN;

-- 1. Add DNS record verification flags (ONLY NEW FIELDS NEEDED)
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS spf_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dkim_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS dmarc_configured BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS mx_configured BOOLEAN DEFAULT FALSE;

-- 2. Add computed column for overall DNS readiness
ALTER TABLE domains
  ADD COLUMN IF NOT EXISTS dns_records_configured BOOLEAN
  GENERATED ALWAYS AS (
    COALESCE(spf_configured, FALSE) AND
    COALESCE(dkim_configured, FALSE) AND
    COALESCE(dmarc_configured, FALSE) AND
    COALESCE(mx_configured, FALSE)
  ) STORED;

-- 3. Add check constraint to existing infrastructure_type field
ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_infrastructure_type_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_infrastructure_type_check
  CHECK (infrastructure_type IS NULL OR infrastructure_type IN ('entra', 'google'));

-- 4. Update nameserver_status values (standardize existing field)
ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_nameserver_status_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_nameserver_status_check
  CHECK (nameserver_status IS NULL OR nameserver_status IN ('pending', 'migrating', 'verified', 'failed'));

-- 5. Create waterfall view
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,
    d.created_at as generated_at,
    d.legitimacy_score,
    d.domain_source,
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
    d.purchased_at,
    d.purchase_job_id,
    d.purchase_job_status,
    d.nameservers_updated_at,
    d.current_nameservers,
    CASE
        WHEN d.nameservers_updated_at IS NULL THEN 'not_set'
        WHEN d.nameservers_updated_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
        ELSE 'propagated'
    END as dns_migration_status,
    d.nameserver_status,
    d.nameserver_verified_at,
    COALESCE(d.spf_configured, FALSE) as spf_configured,
    COALESCE(d.dkim_configured, FALSE) as dkim_configured,
    COALESCE(d.dmarc_configured, FALSE) as dmarc_configured,
    COALESCE(d.mx_configured, FALSE) as mx_configured,
    COALESCE(d.dns_records_configured, FALSE) as dns_records_configured,
    d.infrastructure_type as assigned_provider,
    ipj.id as hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.provider_type as hypertide_provider,
    CASE
        WHEN ipj.status = 'completed' AND NOT EXISTS (
            SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id
        ) THEN 'awaiting_sync'
        WHEN ipj.status = 'completed' THEN 'synced'
        WHEN ipj.status IN ('executing', 'pending') THEN 'provisioning'
        ELSE 'not_started'
    END as provisioning_status,
    (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id) as synced_inbox_count,
    (SELECT MAX(created_at) FROM sender_accounts sa WHERE sa.domain_id = d.id) as last_inbox_synced_at,
    CASE
        WHEN d.infrastructure_type = 'entra' THEN 100
        WHEN d.infrastructure_type = 'google' THEN 15
        ELSE 0
    END as expected_inbox_count,
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
    CASE
        WHEN d.approval_status IN ('owned', 'deployed', 'active') THEN TRUE
        ELSE FALSE
    END as owned_by_client,
    CASE
        WHEN d.approval_status = 'deployed' THEN TRUE
        ELSE FALSE
    END as deployed_to_production
FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
WHERE d.is_active = TRUE;

COMMIT;
```

---

## 📝 SUMMARY: What We're Actually Adding

### New Fields (5 total):
1. `spf_configured` - BOOLEAN
2. `dkim_configured` - BOOLEAN
3. `dmarc_configured` - BOOLEAN
4. `mx_configured` - BOOLEAN
5. `dns_records_configured` - BOOLEAN (computed)

### Repurposed Fields (2 total):
1. `infrastructure_type` - Add constraint for 'entra'/'google' (was always NULL)
2. `approval_status` - Extend values for 'owned'/'deployed' (already used)

### New Constraints (2 total):
1. `domains_infrastructure_type_check` - Validate provider values
2. `domains_nameserver_status_check` - Validate DNS status values

### Total Schema Impact:
- **5 new columns** (all small BOOLEANs)
- **0 new tables**
- **0 new indexes** (reuse existing)
- **1 new view** (v_infrastructure_waterfall)

---

## ✅ RECOMMENDATIONS

1. **Use existing fields wherever possible** ✅
   - `nameservers_updated_at` instead of new `nameserver_set_at`
   - `infrastructure_type` instead of new `assigned_provider`
   - `approval_status` instead of new `owned_by_client` boolean

2. **Only add DNS record flags** ✅
   - 5 boolean columns for SPF/DKIM/DMARC/MX verification
   - Computed column for overall readiness

3. **Add constraints to existing fields** ✅
   - Standardize `nameserver_status` values
   - Validate `infrastructure_type` values

4. **Create view for waterfall queries** ✅
   - `v_infrastructure_waterfall` joins domains + inbox_purchase_jobs
   - Computes all stage statuses
   - No data duplication

---

## 🚫 WHAT WE'RE NOT ADDING

### ❌ No new `infrastructure_provisioning_state` table
**Why:** Would duplicate 90% of data already in `domains` table

### ❌ No new `owned_by_client` boolean
**Why:** Can use `approval_status` values ('owned', 'deployed')

### ❌ No new `assigned_provider` field
**Why:** Repurpose existing `infrastructure_type` (currently unused)

### ❌ No new `nameserver_set_at` field
**Why:** Already have `nameservers_updated_at`

### ❌ No new indexes on domains table
**Why:** Already have 23 indexes including:
- `idx_domains_infrastructure` (for provider filtering)
- `idx_domains_approval_status` (for ownership)
- `idx_domains_workspace` (for client filtering)

---

**Total Impact:** 5 new columns, 2 new constraints, 1 new view

**Minimal, focused, uses existing schema intelligently.**
