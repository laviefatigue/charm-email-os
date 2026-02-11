-- Migration: 017_unified_cycle_schema.sql
-- Purpose: Create unified cycle-campaign hierarchy with variable inheritance
-- Enables: Cycle -> 4 Campaigns -> 4 Emails per campaign structure

-- 1. Cycle-level strategy configuration
CREATE TABLE IF NOT EXISTS cycle_strategy_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_id UUID NOT NULL REFERENCES campaign_cycles(id) ON DELETE CASCADE,

    -- ICP at cycle level (applies to all campaigns in cycle)
    -- Structure: { "target_icp": {...}, "pain_points": [...], "objections": [...] }
    icp_mapping JSONB,

    -- Cycle-level variables (apply to all 4 campaigns)
    -- Structure: [{ "name": "{{competitor}}", "description": "...", "value": "Fiserv" }]
    cycle_variables JSONB,

    -- Strategic context for this cycle
    strategic_focus TEXT,      -- Overall focus/theme for this cycle
    target_outcome TEXT,       -- What we want to achieve this cycle

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(cycle_id)
);

CREATE INDEX IF NOT EXISTS idx_cycle_config_cycle ON cycle_strategy_config(cycle_id);

COMMENT ON TABLE cycle_strategy_config IS 'Cycle-level strategy configuration including ICP and variables';
COMMENT ON COLUMN cycle_strategy_config.icp_mapping IS 'Target ICP, pain points, and objection preemptions for all campaigns in cycle';
COMMENT ON COLUMN cycle_strategy_config.cycle_variables IS 'Variables that apply to all 4 campaigns in this cycle';

-- 2. Add cycle_id to campaign_documents (link documents to cycles)
ALTER TABLE campaign_documents
ADD COLUMN IF NOT EXISTS cycle_id UUID REFERENCES campaign_cycles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_campaign_docs_cycle ON campaign_documents(cycle_id);

-- 3. Add campaign-level variables to campaign_documents
ALTER TABLE campaign_documents
ADD COLUMN IF NOT EXISTS campaign_variables JSONB;

COMMENT ON COLUMN campaign_documents.cycle_id IS 'Links campaign to its parent cycle (1 cycle = 4 campaigns)';
COMMENT ON COLUMN campaign_documents.campaign_variables IS 'Campaign-specific variables (case study, target persona for this angle)';

-- 4. Add cycle_id to strategy_suggestions for backward compatibility
ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS cycle_id UUID REFERENCES campaign_cycles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_suggestions_cycle ON strategy_suggestions(cycle_id);

-- 5. Add campaign_number to track position within cycle (1-4)
ALTER TABLE campaign_documents
ADD COLUMN IF NOT EXISTS campaign_number INTEGER CHECK (campaign_number BETWEEN 1 AND 4);

ALTER TABLE strategy_suggestions
ADD COLUMN IF NOT EXISTS campaign_number INTEGER CHECK (campaign_number BETWEEN 1 AND 4);

COMMENT ON COLUMN campaign_documents.campaign_number IS 'Position within cycle: 1=Custom Signal, 2=Persona Pain, 3=Case Study, 4=Risk/Efficiency';
COMMENT ON COLUMN strategy_suggestions.campaign_number IS 'Position within cycle: 1=Custom Signal, 2=Persona Pain, 3=Case Study, 4=Risk/Efficiency';
