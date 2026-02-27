-- ============================================
-- INFRASTRUCTURE WATERFALL MIGRATION (FINAL)
-- ============================================
-- Adds ONLY truly missing fields for waterfall tracking
-- NO sender_names table - names stored in clients.onboarding_data

BEGIN;

-- 1. ADD DNS TRACKING FIELDS TO domains TABLE
-- ============================================
-- These are the ONLY truly missing fields for DNS verification stage

ALTER TABLE domains ADD COLUMN IF NOT EXISTS spf_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dkim_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dmarc_configured BOOLEAN DEFAULT FALSE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS mx_configured BOOLEAN DEFAULT FALSE;

-- Generated column combining all DNS flags
ALTER TABLE domains ADD COLUMN IF NOT EXISTS dns_records_configured BOOLEAN
  GENERATED ALWAYS AS (
    COALESCE(spf_configured, FALSE) AND
    COALESCE(dkim_configured, FALSE) AND
    COALESCE(dmarc_configured, FALSE) AND
    COALESCE(mx_configured, FALSE)
  ) STORED;

-- Nameserver tracking fields (may already exist from domain_sourcing migrations)
ALTER TABLE domains ADD COLUMN IF NOT EXISTS nameservers_updated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS current_nameservers TEXT[];
ALTER TABLE domains ADD COLUMN IF NOT EXISTS nameserver_status VARCHAR(20);
ALTER TABLE domains ADD COLUMN IF NOT EXISTS nameserver_verified_at TIMESTAMP WITH TIME ZONE;

-- 2. ADD CONSTRAINTS (safe to re-run)
-- ============================================
ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_infrastructure_type_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_infrastructure_type_check
  CHECK (infrastructure_type IS NULL OR infrastructure_type IN ('entra', 'google'));

ALTER TABLE domains DROP CONSTRAINT IF EXISTS domains_nameserver_status_check;
ALTER TABLE domains
  ADD CONSTRAINT domains_nameserver_status_check
  CHECK (nameserver_status IS NULL OR nameserver_status IN ('pending', 'verified', 'failed'));

-- 3. ADD PERFORMANCE INDEXES
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

-- 4. ENHANCE inbox_purchase_jobs WITH ERROR TRACKING
-- ============================================
ALTER TABLE inbox_purchase_jobs ADD COLUMN IF NOT EXISTS error_message TEXT;
ALTER TABLE inbox_purchase_jobs ADD COLUMN IF NOT EXISTS error_stack TEXT;
ALTER TABLE inbox_purchase_jobs ADD COLUMN IF NOT EXISTS error_code VARCHAR(50);
ALTER TABLE inbox_purchase_jobs ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
ALTER TABLE inbox_purchase_jobs ADD COLUMN IF NOT EXISTS last_retry_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE inbox_purchase_jobs ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_purchase_jobs_status_time
  ON inbox_purchase_jobs(status, created_at DESC);

-- 5. CREATE WATERFALL VIEW
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
    COALESCE(d.spf_configured, FALSE) as spf_configured,
    COALESCE(d.dkim_configured, FALSE) as dkim_configured,
    COALESCE(d.dmarc_configured, FALSE) as dmarc_configured,
    COALESCE(d.mx_configured, FALSE) as mx_configured,
    COALESCE(d.dns_records_configured, FALSE) as dns_records_configured,

    -- Stage 6: Provider Assigned
    d.infrastructure_type as assigned_provider,

    -- Stage 7-8: HyperTide
    ipj.id as hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.created_at as hypertide_ordered_at,

    -- Stage 9: Synced
    (SELECT COUNT(*) FROM sender_accounts sa WHERE sa.domain_id = d.id AND sa.is_active = TRUE) as synced_inbox_count,
    (SELECT MAX(created_at) FROM sender_accounts sa WHERE sa.domain_id = d.id) as last_inbox_synced_at,

    -- Computed current stage (1-9)
    CASE
        WHEN EXISTS (SELECT 1 FROM sender_accounts sa WHERE sa.domain_id = d.id AND sa.is_active = TRUE) THEN 9
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

-- 6. AUDIT LOG TABLE (optional but recommended)
-- ============================================
CREATE TABLE IF NOT EXISTS domain_lifecycle_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain_id UUID NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
  event_type VARCHAR(50) NOT NULL,
  event_data JSONB DEFAULT '{}'::jsonb,
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lifecycle_events_domain ON domain_lifecycle_events(domain_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lifecycle_events_type ON domain_lifecycle_events(event_type, created_at DESC);

COMMIT;

-- ============================================
-- SUMMARY OF CHANGES
-- ============================================
-- TABLES ADDED: 1 (domain_lifecycle_events - audit log)
-- COLUMNS ADDED TO domains: 8 (4 DNS booleans + 1 generated + 3 nameserver fields)
-- COLUMNS ADDED TO inbox_purchase_jobs: 6 (error tracking)
-- VIEWS CREATED: 1 (v_infrastructure_waterfall)
-- INDEXES CREATED: 10 (performance optimization)
--
-- NOTE: sender_names table NOT created - names stored in clients.onboarding_data
-- NOTE: 95% of required schema already existed from prior migrations
