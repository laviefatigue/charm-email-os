-- Migration: 031_list_segment_tracking.sql
-- Purpose: V3 Section 12 - List Management and Segment Tracking
-- Tracks lead sources and bounce patterns to quarantine bad list segments

-- ============================================================================
-- LIST SEGMENTS TABLE
-- Tracks lead list segments and their bounce metrics
-- ============================================================================

CREATE TABLE IF NOT EXISTS list_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),

    -- Segment identification
    segment_name VARCHAR(255) NOT NULL,
    segment_type VARCHAR(50) DEFAULT 'unknown',  -- 'csv_upload', 'enrichment', 'manual', 'api_sync'
    source_provider VARCHAR(100),                 -- 'apollo', 'zoominfo', 'clearbit', 'manual', etc.
    source_file VARCHAR(500),                     -- Original file name if CSV upload

    -- State tracking (V3 spec)
    segment_state VARCHAR(20) DEFAULT 'active',   -- 'active', 'quarantined', 'purged'
    quarantined_at TIMESTAMP WITH TIME ZONE,
    quarantine_reason TEXT,
    purged_at TIMESTAMP WITH TIME ZONE,

    -- Metrics
    total_leads INTEGER DEFAULT 0,
    bounces_caused INTEGER DEFAULT 0,             -- Total bounces from this segment
    bounces_7d INTEGER DEFAULT 0,                 -- Rolling 7-day bounces
    bounce_rate DECIMAL(5,4) DEFAULT 0,           -- bounces_caused / total_leads
    last_bounce_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(workspace_id, segment_name)
);

CREATE INDEX IF NOT EXISTS idx_list_segments_workspace ON list_segments(workspace_id);
CREATE INDEX IF NOT EXISTS idx_list_segments_state ON list_segments(segment_state);
CREATE INDEX IF NOT EXISTS idx_list_segments_provider ON list_segments(source_provider);
CREATE INDEX IF NOT EXISTS idx_list_segments_quarantine ON list_segments(workspace_id, segment_state)
    WHERE segment_state = 'quarantined';

-- ============================================================================
-- ENRICHMENT PROVIDERS TABLE
-- Tracks bounce patterns by data enrichment provider
-- ============================================================================

CREATE TABLE IF NOT EXISTS enrichment_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),

    -- Provider identification
    provider_name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(50) DEFAULT 'enrichment',  -- 'enrichment', 'list_purchase', 'scraper'

    -- State tracking
    provider_state VARCHAR(20) DEFAULT 'active',  -- 'active', 'flagged', 'blocked'
    flagged_at TIMESTAMP WITH TIME ZONE,
    flag_reason TEXT,

    -- Metrics
    total_leads_from INTEGER DEFAULT 0,
    bounces_caused INTEGER DEFAULT 0,
    bounces_7d INTEGER DEFAULT 0,
    last_bounce_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(workspace_id, provider_name)
);

CREATE INDEX IF NOT EXISTS idx_enrichment_providers_workspace ON enrichment_providers(workspace_id);
CREATE INDEX IF NOT EXISTS idx_enrichment_providers_state ON enrichment_providers(provider_state);

-- ============================================================================
-- ADD SEGMENT TRACKING TO LEADS TABLE
-- Link leads to their source segment for bounce attribution
-- ============================================================================

-- Add segment_id to leads if not exists
ALTER TABLE leads ADD COLUMN IF NOT EXISTS segment_id UUID REFERENCES list_segments(id);
ALTER TABLE leads ADD COLUMN IF NOT EXISTS enrichment_provider VARCHAR(100);

CREATE INDEX IF NOT EXISTS idx_leads_segment ON leads(segment_id);
CREATE INDEX IF NOT EXISTS idx_leads_enrichment_provider ON leads(enrichment_provider);

-- ============================================================================
-- V3 THRESHOLDS (as comments for reference)
-- ============================================================================

-- List segment quarantine thresholds:
--   2+ hard bounces from segment → quarantine segment
--   3+ hard bounces from segment → purge permanently
--   Bounce rate > 3% on list → stop using

-- Enrichment provider flagging:
--   3+ bounces from provider → flag provider for audit

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE list_segments IS 'V3 Section 12: Tracks lead list segments for bounce pattern detection and quarantine';
COMMENT ON COLUMN list_segments.segment_state IS 'active=normal, quarantined=blocked pending review, purged=permanently removed';
COMMENT ON TABLE enrichment_providers IS 'V3 Section 12: Tracks bounce patterns by data enrichment provider';

-- Done!
SELECT 'Migration 031_list_segment_tracking complete' AS status;
