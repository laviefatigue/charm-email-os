-- Migration 070: Domain Engine V2 Schema
-- Purpose: Support 3-agent pipeline for continuous domain generation
-- Created: 2026-03-05
-- Status: LOCAL DEVELOPMENT ONLY - DO NOT DEPLOY TO PRODUCTION

BEGIN;

-- =====================================================
-- TABLE 1: Client Domain Profiles
-- Output from Agent 1 (Profiler)
-- Stores crawl results and generation patterns per client
-- =====================================================

CREATE TABLE IF NOT EXISTS client_domain_profiles (
    client_id UUID PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
    primary_url TEXT NOT NULL,

    -- Brand identity (extracted from website)
    brand_name TEXT NOT NULL,
    brand_variations JSONB DEFAULT '[]'::jsonb,
    -- Example: ["selery", "slry", "selry"]

    -- Industry context
    industry TEXT,
    keywords JSONB DEFAULT '{"primary": [], "secondary": []}'::jsonb,
    -- Example: {"primary": ["fulfillment", "shipping"], "secondary": ["3pl", "logistics"]}
    target_audience TEXT,
    tone TEXT,

    -- Competitive intel
    competitors JSONB DEFAULT '[]'::jsonb,
    -- Example: ["shipbob", "deliverr", "shipmonk"]

    -- Generation patterns (suggested by profiler)
    suggested_patterns JSONB DEFAULT '{
        "prefixes": [],
        "suffixes": [],
        "blends": [],
        "pure": []
    }'::jsonb,

    -- Constraints
    avoid_words JSONB DEFAULT '[]'::jsonb,
    cold_email_constraints JSONB DEFAULT '{
        "max_length": 15,
        "allowed_chars": "a-z",
        "no_hyphens": true,
        "no_numbers": true
    }'::jsonb,

    -- TLD preferences (configurable per client)
    tld_preferences JSONB DEFAULT '{
        "allowed": [".com", ".co", ".io"],
        "weights": {".com": 1.0, ".co": 0.85, ".io": 0.70}
    }'::jsonb,

    -- Engine state
    engine_enabled BOOLEAN DEFAULT FALSE,
    last_crawled_at TIMESTAMP WITH TIME ZONE,
    last_generation_at TIMESTAMP WITH TIME ZONE,
    crawl_error TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for finding clients with engine enabled
CREATE INDEX IF NOT EXISTS idx_profiles_engine_enabled
    ON client_domain_profiles(engine_enabled)
    WHERE engine_enabled = true;

COMMENT ON TABLE client_domain_profiles IS
    'Domain Engine V2: Client profiles for domain generation. Output from Agent 1 (Profiler).';


-- =====================================================
-- TABLE 2: Domain Candidates
-- Output from Agents 2 (Generator) and 3 (Scorer)
-- Stores generated domain ideas with scoring
-- =====================================================

CREATE TABLE IF NOT EXISTS domain_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    domain_name TEXT NOT NULL,
    tld VARCHAR(10) NOT NULL,

    -- Pricing (mirrors domains table structure for compatibility)
    dynadot_price DECIMAL(10,2),
    dynadot_available BOOLEAN,
    dynadot_checked_at TIMESTAMP WITH TIME ZONE,
    porkbun_price DECIMAL(10,2),
    porkbun_available BOOLEAN,
    porkbun_checked_at TIMESTAMP WITH TIME ZONE,

    -- Generated columns for best price (auto-computed)
    best_price DECIMAL(10,2) GENERATED ALWAYS AS (
        CASE
            WHEN dynadot_price IS NULL AND porkbun_price IS NULL THEN NULL
            WHEN dynadot_price IS NULL THEN porkbun_price
            WHEN porkbun_price IS NULL THEN dynadot_price
            ELSE LEAST(dynadot_price, porkbun_price)
        END
    ) STORED,

    best_registrar VARCHAR(20) GENERATED ALWAYS AS (
        CASE
            WHEN dynadot_price IS NULL AND porkbun_price IS NULL THEN NULL
            WHEN dynadot_price IS NULL THEN 'porkbun'
            WHEN porkbun_price IS NULL THEN 'dynadot'
            WHEN dynadot_price <= porkbun_price THEN 'dynadot'
            ELSE 'porkbun'
        END
    ) STORED,

    -- Scoring from Agent 3 (weights: Brand 35%, TLD 30%, Safety 20%, Length 15%)
    brand_fit_score DECIMAL(3,2),    -- 0.00 - 1.00
    tld_score DECIMAL(3,2),          -- 0.00 - 1.00
    safety_score DECIMAL(3,2),       -- 0.00 - 1.00
    length_score DECIMAL(3,2),       -- 0.00 - 1.00
    composite_score DECIMAL(3,2),    -- Weighted combination

    -- Lifecycle status
    status VARCHAR(20) DEFAULT 'generated' CHECK (
        status IN ('generated', 'scored', 'priced', 'recommended', 'purchased', 'rejected')
    ),
    rejection_reason TEXT,

    -- Audit trail
    generation_batch_id UUID,
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    scored_at TIMESTAMP WITH TIME ZONE,
    priced_at TIMESTAMP WITH TIME ZONE,
    recommended_at TIMESTAMP WITH TIME ZONE,
    purchased_at TIMESTAMP WITH TIME ZONE,

    -- Link to domains table after purchase
    domain_id UUID REFERENCES domains(id) ON DELETE SET NULL,

    -- Constraints
    UNIQUE(client_id, domain_name)
);

-- Primary index: Score-based prioritization for price checker
-- High scores get checked first (don't waste Porkbun rate limit on low scores)
CREATE INDEX IF NOT EXISTS idx_candidates_score_priority
    ON domain_candidates(composite_score DESC NULLS LAST)
    WHERE status = 'scored';

-- Status-based queries
CREATE INDEX IF NOT EXISTS idx_candidates_status
    ON domain_candidates(status, client_id);

-- Price checking queue (scored but not yet priced)
CREATE INDEX IF NOT EXISTS idx_candidates_price_queue
    ON domain_candidates(composite_score DESC)
    WHERE status = 'scored' AND porkbun_price IS NULL;

-- Finding candidates ready for recommendation
CREATE INDEX IF NOT EXISTS idx_candidates_ready
    ON domain_candidates(client_id, composite_score DESC)
    WHERE status = 'priced' AND best_price <= 15.00;

-- Batch lookup
CREATE INDEX IF NOT EXISTS idx_candidates_batch
    ON domain_candidates(generation_batch_id);

COMMENT ON TABLE domain_candidates IS
    'Domain Engine V2: Generated domain candidates with scoring.
    Status flow: generated → scored → priced → recommended → purchased.
    Score determines price check priority (high scores first).';


-- =====================================================
-- TABLE 3: Generation Batches (Audit Trail)
-- Tracks each generation run for debugging
-- =====================================================

CREATE TABLE IF NOT EXISTS domain_generation_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,

    -- Batch metadata
    profile_version TIMESTAMP WITH TIME ZONE NOT NULL,
    batch_size_requested INTEGER DEFAULT 20,

    -- Counts
    domains_generated INTEGER DEFAULT 0,
    domains_rejected INTEGER DEFAULT 0,  -- Failed validation
    domains_duplicate INTEGER DEFAULT 0, -- Already existed
    domains_scored INTEGER DEFAULT 0,
    domains_priced INTEGER DEFAULT 0,

    -- Timing
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    generation_completed_at TIMESTAMP WITH TIME ZONE,
    scoring_completed_at TIMESTAMP WITH TIME ZONE,
    pricing_completed_at TIMESTAMP WITH TIME ZONE,

    -- Status
    status VARCHAR(20) DEFAULT 'running' CHECK (
        status IN ('running', 'generating', 'scoring', 'pricing', 'completed', 'failed')
    ),
    error_message TEXT,

    -- Model used
    ai_provider VARCHAR(20),  -- 'openai', 'anthropic', 'pattern'
    ai_model VARCHAR(50)      -- 'gpt-4', 'claude-3-opus', etc.
);

CREATE INDEX IF NOT EXISTS idx_batches_client
    ON domain_generation_batches(client_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_batches_status
    ON domain_generation_batches(status)
    WHERE status = 'running';

COMMENT ON TABLE domain_generation_batches IS
    'Domain Engine V2: Audit trail for generation runs. Tracks what was generated and when.';


-- =====================================================
-- TABLE 4: Inventory Targets (Per-Client)
-- Configurable targets per TLD
-- =====================================================

CREATE TABLE IF NOT EXISTS domain_inventory_targets (
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    tld VARCHAR(10) NOT NULL,

    -- Targets
    min_candidates INTEGER DEFAULT 50,       -- Keep at least this many candidates
    max_price DECIMAL(10,2) DEFAULT 15.00,   -- Hard cap ($15 = HyperTide max)
    target_price DECIMAL(10,2) DEFAULT 10.00, -- Ideal price

    -- Current state (updated by triggers or scheduled job)
    current_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    PRIMARY KEY (client_id, tld)
);

COMMENT ON TABLE domain_inventory_targets IS
    'Domain Engine V2: Per-client inventory targets. $15 hard cap, $10 target.';


-- =====================================================
-- VIEW: Candidate Summary
-- Quick overview of pipeline status per client
-- =====================================================

CREATE OR REPLACE VIEW v_domain_candidate_summary AS
SELECT
    dc.client_id,
    c.name as client_name,
    cdp.brand_name,
    cdp.engine_enabled,

    -- Counts by status
    COUNT(*) as total_candidates,
    COUNT(*) FILTER (WHERE dc.status = 'generated') as unscored,
    COUNT(*) FILTER (WHERE dc.status = 'scored') as scored_unpriced,
    COUNT(*) FILTER (WHERE dc.status = 'priced') as priced,
    COUNT(*) FILTER (WHERE dc.status = 'priced' AND dc.best_price <= 15.00) as priced_under_cap,
    COUNT(*) FILTER (WHERE dc.status = 'priced' AND dc.best_price <= 10.00) as priced_under_target,
    COUNT(*) FILTER (WHERE dc.status = 'recommended') as recommended,
    COUNT(*) FILTER (WHERE dc.status = 'purchased') as purchased,
    COUNT(*) FILTER (WHERE dc.status = 'rejected') as rejected,

    -- Score stats
    AVG(dc.composite_score) FILTER (WHERE dc.composite_score IS NOT NULL) as avg_score,
    MIN(dc.composite_score) FILTER (WHERE dc.composite_score IS NOT NULL) as min_score,
    MAX(dc.composite_score) FILTER (WHERE dc.composite_score IS NOT NULL) as max_score,

    -- Price stats
    MIN(dc.best_price) FILTER (WHERE dc.best_price IS NOT NULL AND dc.best_price < 999) as min_price,
    AVG(dc.best_price) FILTER (WHERE dc.best_price IS NOT NULL AND dc.best_price < 999) as avg_price,

    -- Timing
    MAX(dc.generated_at) as last_generated_at,
    cdp.last_crawled_at

FROM domain_candidates dc
JOIN clients c ON c.id = dc.client_id
LEFT JOIN client_domain_profiles cdp ON cdp.client_id = dc.client_id
GROUP BY dc.client_id, c.name, cdp.brand_name, cdp.engine_enabled, cdp.last_crawled_at;

COMMENT ON VIEW v_domain_candidate_summary IS
    'Domain Engine V2: Summary of candidate pipeline status per client.';


-- =====================================================
-- VIEW: Price Check Queue
-- Ordered list for price checker worker
-- =====================================================

CREATE OR REPLACE VIEW v_price_check_queue AS
SELECT
    dc.id,
    dc.client_id,
    dc.domain_name,
    dc.tld,
    dc.composite_score,
    dc.status,
    dc.generated_at,
    c.name as client_name
FROM domain_candidates dc
JOIN clients c ON c.id = dc.client_id
WHERE dc.status = 'scored'
  AND dc.porkbun_price IS NULL
ORDER BY dc.composite_score DESC NULLS LAST;

COMMENT ON VIEW v_price_check_queue IS
    'Domain Engine V2: Price check queue ordered by score (high scores first).';


-- =====================================================
-- VIEW: Purchase Recommendations
-- Ready-to-buy candidates under $15 cap
-- =====================================================

CREATE OR REPLACE VIEW v_purchase_recommendations AS
SELECT
    dc.id,
    dc.client_id,
    dc.domain_name,
    dc.tld,
    dc.composite_score,
    dc.brand_fit_score,
    dc.tld_score,
    dc.best_price,
    dc.best_registrar,
    dc.dynadot_price,
    dc.porkbun_price,
    c.name as client_name,
    cdp.brand_name
FROM domain_candidates dc
JOIN clients c ON c.id = dc.client_id
LEFT JOIN client_domain_profiles cdp ON cdp.client_id = dc.client_id
WHERE dc.status = 'priced'
  AND dc.best_price IS NOT NULL
  AND dc.best_price <= 15.00  -- Hard cap
ORDER BY dc.best_price ASC;  -- Cheapest first among qualifying

COMMENT ON VIEW v_purchase_recommendations IS
    'Domain Engine V2: Candidates ready to purchase, sorted by price (cheapest first).';


-- =====================================================
-- FUNCTION: Update inventory counts
-- =====================================================

CREATE OR REPLACE FUNCTION update_inventory_count(p_client_id UUID, p_tld VARCHAR)
RETURNS void AS $$
BEGIN
    INSERT INTO domain_inventory_targets (client_id, tld, current_count)
    VALUES (p_client_id, p_tld, (
        SELECT COUNT(*)
        FROM domain_candidates
        WHERE client_id = p_client_id
          AND tld = p_tld
          AND status IN ('priced', 'recommended')
          AND best_price <= 15.00
    ))
    ON CONFLICT (client_id, tld) DO UPDATE
    SET current_count = EXCLUDED.current_count,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;


-- =====================================================
-- COMMENTS
-- =====================================================

COMMENT ON COLUMN domain_candidates.composite_score IS
    'Weighted score: Brand 35%, TLD 30%, Safety 20%, Length 15%. Used for price check prioritization.';

COMMENT ON COLUMN domain_candidates.best_price IS
    'Auto-computed: LEAST(dynadot_price, porkbun_price). $15 hard cap, $10 target.';

COMMENT ON COLUMN client_domain_profiles.tld_preferences IS
    'Configurable TLD weights. Default: .com=1.0, .co=0.85, .io=0.70. No .info (not supported).';

COMMIT;

-- =====================================================
-- VERIFICATION
-- =====================================================

-- Verify tables created
SELECT 'client_domain_profiles' as table_name, COUNT(*) as rows FROM client_domain_profiles
UNION ALL
SELECT 'domain_candidates', COUNT(*) FROM domain_candidates
UNION ALL
SELECT 'domain_generation_batches', COUNT(*) FROM domain_generation_batches
UNION ALL
SELECT 'domain_inventory_targets', COUNT(*) FROM domain_inventory_targets;
