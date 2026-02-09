-- Migration: 013_batch_campaign_generation
-- Created: 2026-02-09
-- Purpose: Support 4-campaign batch generation with cycle tracking, versioning, and strategy considerations

-- ============================================================
-- PART 1: Campaign Cycles Table
-- ============================================================

-- Campaign cycles track 14-day periods of outreach
-- Cycle 1 → Cycle 3 → Cycle 5 (odd cycles evolve together)
-- Cycle 2 → Cycle 4 → Cycle 6 (even cycles evolve together)
CREATE TABLE IF NOT EXISTS campaign_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    strategy_id UUID REFERENCES strategies(id),

    -- Cycle metadata
    cycle_number INTEGER NOT NULL,  -- 1, 2, 3, 4, 5, 6...
    cycle_name VARCHAR(100),  -- e.g., "Pre-Launch", "Cycle 1", "Infra Refresh"

    -- Timing
    start_date DATE,
    end_date DATE,
    duration_days INTEGER DEFAULT 14,

    -- Campaign scaling targets
    target_campaigns INTEGER,  -- Target number of campaigns for this cycle
    actual_campaigns INTEGER DEFAULT 0,

    -- Status
    status VARCHAR(50) DEFAULT 'planned',  -- planned, active, completed

    -- Notes
    notes TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cycles_client ON campaign_cycles(client_id);
CREATE INDEX IF NOT EXISTS idx_cycles_strategy ON campaign_cycles(strategy_id);
CREATE INDEX IF NOT EXISTS idx_cycles_status ON campaign_cycles(status);

-- ============================================================
-- PART 2: Campaign Versioning and Lineage
-- ============================================================

-- Add cycle and version tracking to strategy_suggestions (campaigns)
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS cycle_id UUID REFERENCES campaign_cycles(id);

-- Version within a campaign lineage (v1, v2, v3...)
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS campaign_version INTEGER DEFAULT 1;

-- Links to the previous version of this campaign (for lineage tracking)
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS previous_version_id UUID REFERENCES strategy_suggestions(id);

-- The "family" of campaigns - campaigns that evolve from each other share a lineage_id
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS lineage_id UUID;

-- ============================================================
-- PART 3: Campaign Differentiation (4 angles)
-- ============================================================

-- Campaign angle for differentiation
-- Values: custom_signal, persona_pain, case_study, risk_efficiency
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS campaign_angle VARCHAR(50);

-- Target info to track which persona/segment this campaign targets
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS target_persona VARCHAR(255);

ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS target_segment VARCHAR(255);

-- Track which opener pattern was used (from the 5 Poke the Bear patterns)
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS opener_pattern VARCHAR(50);

-- ============================================================
-- PART 4: Performance Tracking (from EmailBison)
-- ============================================================

-- Add performance metrics columns for monitoring
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS emailbison_campaign_id VARCHAR(100);

ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS performance_metrics JSONB;
-- Structure: {
--   "emails_sent": 0,
--   "opens": 0, "open_rate": 0.0,
--   "replies": 0, "reply_rate": 0.0,
--   "bounces": 0, "bounce_rate": 0.0,
--   "unsubscribes": 0,
--   "last_synced_at": "2026-02-09T..."
-- }

ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS last_performance_sync TIMESTAMP;

-- ============================================================
-- PART 5: Strategy Considerations
-- ============================================================

-- Add strategy considerations to jobs table (tracks which onboarding inputs influenced generation)
ALTER TABLE strategy_generation_jobs
ADD COLUMN IF NOT EXISTS strategy_considerations JSONB;

-- ============================================================
-- PART 6: Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_suggestions_cycle ON strategy_suggestions(cycle_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_lineage ON strategy_suggestions(lineage_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_angle ON strategy_suggestions(campaign_angle);
CREATE INDEX IF NOT EXISTS idx_suggestions_version ON strategy_suggestions(lineage_id, campaign_version);

-- ============================================================
-- COMMENTS
-- ============================================================

COMMENT ON TABLE campaign_cycles IS 'Tracks 14-day campaign cycles. Odd cycles (1,3,5) evolve together, even cycles (2,4,6) evolve together.';

COMMENT ON COLUMN strategy_suggestions.campaign_angle IS 'Campaign angle type: custom_signal (research-led), persona_pain (role-specific), case_study (proof-led), risk_efficiency (savings-led)';

COMMENT ON COLUMN strategy_suggestions.opener_pattern IS 'Poke the Bear pattern: status_pressure, efficiency_leverage, risk_based, binary, redirect';

COMMENT ON COLUMN strategy_suggestions.campaign_version IS 'Version number within a campaign lineage. Increments when copy is regenerated.';

COMMENT ON COLUMN strategy_suggestions.lineage_id IS 'Groups campaigns that evolve from each other. All versions of Campaign A share the same lineage_id.';

COMMENT ON COLUMN strategy_suggestions.performance_metrics IS 'Performance data synced from EmailBison: opens, replies, bounces, etc.';
