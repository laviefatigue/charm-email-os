-- Migration 090: Per-Client Suppression Module
--
-- Implements workspace-scoped domain suppression lists that act as a pre-admission
-- gate before leads enter the EmailBison pipeline.
--
-- Architecture:
--   - One config row per client (client_suppression_configs)
--   - One row per protected domain per client (client_suppression_domains)
--   - Audit log of Clay check calls (suppression_check_log)
--   - New leads table (leads) with suppression tracking columns
--
-- Isolation model:
--   - Every suppression row carries a non-nullable client_id FK
--   - UNIQUE (client_id, domain) makes domain lists fully client-isolated
--   - ON DELETE CASCADE ensures suppression data is removed with the client
--   - The Clay check endpoint resolves client_id from api_token alone —
--     no cross-client lookup is possible
--
-- Security model (matches migration 089 pattern):
--   - api_token stored as plaintext (no application-layer encryption)
--   - Access controlled at API layer: token only exposed on GET /config and on creation
--   - Token is never returned in list endpoints
--   - Column excluded from all views

-- ============================================================================
-- 1. LEADS TABLE
--    Create if it does not already exist. The routes/leads.py already references
--    this table but no prior migration creates it. IF NOT EXISTS makes this safe
--    whether the table was created manually in production or not yet created.
-- ============================================================================

CREATE TABLE IF NOT EXISTS leads (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id         UUID        NOT NULL REFERENCES emailbison_campaigns(id) ON DELETE CASCADE,
    email               VARCHAR(320) NOT NULL,
    first_name          VARCHAR(255),
    last_name           VARCHAR(255),
    company             VARCHAR(255),
    title               VARCHAR(255),
    linkedin_url        TEXT,
    phone               VARCHAR(50),
    website             VARCHAR(500),
    location            VARCHAR(255),
    industry            VARCHAR(100),
    company_size        VARCHAR(50),
    notes               TEXT,
    tags                TEXT[],
    custom_fields       JSONB,
    status              VARCHAR(30)  NOT NULL DEFAULT 'queued',
    source              VARCHAR(50)  NOT NULL DEFAULT 'manual_upload',
    contacted_at        TIMESTAMPTZ,
    enriched_at         TIMESTAMPTZ,
    raw_data            JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Core lookups used by existing routes
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_campaign_email
    ON leads(campaign_id, email);

CREATE INDEX IF NOT EXISTS idx_leads_status
    ON leads(campaign_id, status);

CREATE INDEX IF NOT EXISTS idx_leads_created
    ON leads(campaign_id, created_at DESC);

-- ============================================================================
-- 2. SUPPRESSION COLUMNS ON LEADS
--    Added regardless of whether the table was just created or already existed.
--    IF NOT EXISTS on ALTER TABLE is safe to run multiple times.
-- ============================================================================

-- Company domain for suppression check (separate from email domain — a lead at
-- john@gmail.com working at acme.com needs the acme.com check, not gmail.com)
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS company_domain       VARCHAR(253) DEFAULT NULL;

-- Whether suppression was evaluated for this lead and what the outcome was.
-- NULL  = never evaluated (created before suppression was active, or suppression disabled)
-- 'allowed'     = evaluated, passed — safe to send
-- 'suppressed'  = evaluated, blocked — do not send
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS suppression_status   VARCHAR(20)  DEFAULT NULL;

-- When the suppression verdict was recorded
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS suppressed_at        TIMESTAMPTZ  DEFAULT NULL;

-- Which domain rule triggered the suppression (diagnostic / audit)
ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS suppressed_by_domain VARCHAR(253) DEFAULT NULL;

-- Index: used by retroactive scan (find all leads not yet evaluated)
-- and by campaign stats (count suppressed leads)
CREATE INDEX IF NOT EXISTS idx_leads_suppression
    ON leads(campaign_id, suppression_status)
    WHERE suppression_status IS NOT NULL;

COMMENT ON COLUMN leads.suppression_status IS
    'NULL=not evaluated, allowed=passed check, suppressed=blocked by domain rule';
COMMENT ON COLUMN leads.company_domain IS
    'Apex domain of the lead''s employer — checked against suppression list separately from email domain';
COMMENT ON COLUMN leads.suppressed_by_domain IS
    'The domain entry in client_suppression_domains that triggered the block';

-- ============================================================================
-- 3. CLIENT SUPPRESSION CONFIGS
--    One row per client. Controls whether suppression is active and holds
--    the api_token that Clay uses to identify the client.
-- ============================================================================

CREATE TABLE IF NOT EXISTS client_suppression_configs (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Hard FK to clients table. ON DELETE CASCADE: if the client is deleted,
    -- all suppression data is removed atomically.
    client_id           UUID        NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Denormalized for convenience — avoids a join on every Clay check call.
    -- Set when the config is created; updated if the client is re-linked.
    workspace_id        UUID        REFERENCES workspaces(id) ON DELETE SET NULL,

    -- Master on/off switch. When false, the check endpoint returns suppressed=false
    -- for all calls (transparent passthrough). Clay can be configured before go-live.
    is_enabled          BOOLEAN     NOT NULL DEFAULT FALSE,

    -- 64-char hex token (secrets.token_hex(32)). Stored plaintext.
    -- Identifies the client on every Clay check call.
    -- UNIQUE enforced at DB level — no two clients can share a token.
    api_token           VARCHAR(64) NOT NULL UNIQUE,

    token_created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    token_last_used_at  TIMESTAMPTZ,            -- updated async on each Clay call

    -- Denormalized count of active suppression domain entries.
    -- Updated by the API after every bulk import or single add/delete.
    -- Avoids a COUNT(*) on every stats request.
    domain_count        INTEGER     NOT NULL DEFAULT 0,

    last_import_at      TIMESTAMPTZ,            -- timestamp of last seed list import
    notes               TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Structural guarantee: one config per client, period.
    CONSTRAINT uq_suppression_config_client UNIQUE (client_id)
);

-- Primary lookup for Clay endpoint — runs on every check call.
-- Must be as fast as possible. Covering index on token alone.
CREATE UNIQUE INDEX IF NOT EXISTS idx_suppression_config_token
    ON client_suppression_configs(api_token);

-- Workspace lookup (used when resolving client from EB workspace context)
CREATE INDEX IF NOT EXISTS idx_suppression_config_workspace
    ON client_suppression_configs(workspace_id);

COMMENT ON TABLE client_suppression_configs IS
    'Per-client suppression configuration. api_token is sensitive — never expose in list endpoints.';
COMMENT ON COLUMN client_suppression_configs.api_token IS
    'Plaintext Clay authentication token. Identifies client on every check call. Access-controlled at application layer.';
COMMENT ON COLUMN client_suppression_configs.is_enabled IS
    'When false, check endpoint returns suppressed=false for all calls (safe pre-launch wiring).';
COMMENT ON COLUMN client_suppression_configs.domain_count IS
    'Denormalized count of active entries in client_suppression_domains. Updated on every write.';

-- ============================================================================
-- 4. CLIENT SUPPRESSION DOMAINS
--    The seed list. One row per protected domain per client.
--    All domain values are pre-cleaned (lowercase, no www., no scheme, no path).
-- ============================================================================

CREATE TABLE IF NOT EXISTS client_suppression_domains (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Hard FK. ON DELETE CASCADE: deleting a client removes all their domain entries.
    client_id       UUID        NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Cleaned apex domain. e.g. "acme.com", "bigcorp.co.uk"
    -- Stored lowercase with no scheme, no www., no path, no trailing slash.
    domain          VARCHAR(253) NOT NULL,

    -- Optional parent domain for subsidiary matching.
    -- e.g. umbrella_domain="google.com" covers "mail.google.com", "workspace.google.com"
    -- The check algorithm matches if the lead's domain ends with '.' || umbrella_domain
    umbrella_domain VARCHAR(253),

    -- How this entry was added. Used for audit and UI display.
    added_by        VARCHAR(20) NOT NULL DEFAULT 'manual'
                    CHECK (added_by IN ('manual', 'csv_import', 'api')),

    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Structural guarantee: one entry per domain per client.
    -- Enables safe INSERT ... ON CONFLICT DO NOTHING for bulk imports.
    CONSTRAINT uq_suppression_domain_per_client UNIQUE (client_id, domain)
);

-- Primary hot path: used on every check call.
-- Covers the direct domain match branch: WHERE client_id = $1 AND domain = ANY($2)
CREATE INDEX IF NOT EXISTS idx_suppression_domains_lookup
    ON client_suppression_domains(client_id, domain);

-- Secondary path: umbrella domain match
-- Partial index (only rows with umbrella_domain set) keeps it small.
CREATE INDEX IF NOT EXISTS idx_suppression_domains_umbrella
    ON client_suppression_domains(client_id, umbrella_domain)
    WHERE umbrella_domain IS NOT NULL;

-- Dashboard pagination: ORDER BY created_at DESC with client_id filter
CREATE INDEX IF NOT EXISTS idx_suppression_domains_created
    ON client_suppression_domains(client_id, created_at DESC);

COMMENT ON TABLE client_suppression_domains IS
    'Per-client domain seed list. All domain values pre-cleaned at insert time. UNIQUE (client_id, domain) enforces isolation.';
COMMENT ON COLUMN client_suppression_domains.domain IS
    'Cleaned apex domain. Lowercase, no scheme, no www prefix, no path.';
COMMENT ON COLUMN client_suppression_domains.umbrella_domain IS
    'Parent domain for subsidiary matching. Covers all subdomains ending in this value.';

-- ============================================================================
-- 5. SUPPRESSION CHECK LOG
--    Audit log of Clay endpoint calls. Written asynchronously (fire-and-forget).
--    Not in the hot path. Prune rows older than 90 days in periodic cleanup.
-- ============================================================================

CREATE TABLE IF NOT EXISTS suppression_check_log (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),

    -- FK to clients. ON DELETE CASCADE keeps log clean when client is removed.
    client_id       UUID        NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- The email submitted to the check endpoint
    checked_email   VARCHAR(320),

    -- Domain extracted from checked_email (split on @, lowercase)
    checked_domain  VARCHAR(253),

    -- The verdict returned
    result          VARCHAR(20) NOT NULL
                    CHECK (result IN ('suppressed', 'allowed')),

    -- Which domain rule matched. NULL when result='allowed'.
    matched_domain  VARCHAR(253),

    -- Caller IP for debugging Clay configuration issues
    caller_ip       INET,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dashboard stats: latest N calls for a client
CREATE INDEX IF NOT EXISTS idx_suppression_log_client_created
    ON suppression_check_log(client_id, created_at DESC);

-- Stats queries: count suppressed vs allowed for a client
CREATE INDEX IF NOT EXISTS idx_suppression_log_result
    ON suppression_check_log(client_id, result);

COMMENT ON TABLE suppression_check_log IS
    'Audit log of Clay suppression check calls. Written asynchronously. Prune rows older than 90 days.';
