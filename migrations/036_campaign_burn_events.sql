-- Migration 036: Campaign Burn Events Table
-- Enables granular tracking of which kill triggers are burning which campaigns/domains
-- Created: 2026-02-22

-- ============================================================================
-- ADD MISSING KILL TRIGGER TYPES TO ENUM
-- ============================================================================
-- These are used in health_checks.py but weren't in the original enum
DO $$
BEGIN
    -- Add hard_blocked_24h if not exists
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'hard_blocked_24h'
                   AND enumtypid = 'kill_trigger_type'::regtype) THEN
        ALTER TYPE kill_trigger_type ADD VALUE 'hard_blocked_24h';
    END IF;

    -- Add hard_unknown_24h if not exists
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'hard_unknown_24h'
                   AND enumtypid = 'kill_trigger_type'::regtype) THEN
        ALTER TYPE kill_trigger_type ADD VALUE 'hard_unknown_24h';
    END IF;
END $$;

-- ============================================================================
-- CREATE CAMPAIGN BURN EVENTS TABLE
-- ============================================================================
-- Tracks each burn event with full context for analysis
CREATE TABLE IF NOT EXISTS campaign_burn_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Core relationships
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    campaign_id UUID NOT NULL REFERENCES emailbison_campaigns(id),
    inbox_id UUID NOT NULL REFERENCES sender_accounts(id),
    domain_id UUID REFERENCES domains(id),

    -- Kill details
    kill_trigger_type VARCHAR(50) NOT NULL,  -- Using VARCHAR for flexibility with provider_block_gmail etc.
    trigger_value DECIMAL(10,4),             -- Actual metric value that triggered
    trigger_threshold DECIMAL(10,4),         -- Threshold that was exceeded

    -- Context
    campaign_name VARCHAR(255),
    inbox_email VARCHAR(255),
    domain_name VARCHAR(255),

    -- Timestamps
    burned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- UNIQUE CONSTRAINT FOR IDEMPOTENCY
-- ============================================================================
-- Prevents duplicate burn events for same inbox in same campaign
-- (An inbox can only die once per campaign assignment)
CREATE UNIQUE INDEX IF NOT EXISTS idx_burn_events_unique
ON campaign_burn_events(campaign_id, inbox_id);

-- ============================================================================
-- INDEXES FOR COMMON QUERIES
-- ============================================================================

-- Campaign drill-down: "What's burning Campaign X?"
CREATE INDEX IF NOT EXISTS idx_burn_events_campaign_trigger
ON campaign_burn_events(campaign_id, kill_trigger_type);

-- Domain drill-down: "What's burning Domain Y?"
CREATE INDEX IF NOT EXISTS idx_burn_events_domain_trigger
ON campaign_burn_events(domain_id, kill_trigger_type);

-- Workspace overview: "All burns for client Z"
CREATE INDEX IF NOT EXISTS idx_burn_events_workspace
ON campaign_burn_events(workspace_id, burned_at DESC);

-- Time-based queries: "Burns in last 7 days"
CREATE INDEX IF NOT EXISTS idx_burn_events_time
ON campaign_burn_events(burned_at DESC);

-- Trigger analysis: "Which trigger type is most common?"
CREATE INDEX IF NOT EXISTS idx_burn_events_trigger_type
ON campaign_burn_events(kill_trigger_type, burned_at DESC);

-- ============================================================================
-- VIEWS FOR COMMON AGGREGATIONS
-- ============================================================================

-- Campaign burn breakdown by trigger type
CREATE OR REPLACE VIEW campaign_burn_summary AS
SELECT
    campaign_id,
    campaign_name,
    workspace_id,
    kill_trigger_type,
    COUNT(*) as burn_count,
    COUNT(DISTINCT domain_id) as domains_affected,
    MIN(burned_at) as first_burn,
    MAX(burned_at) as last_burn
FROM campaign_burn_events
GROUP BY campaign_id, campaign_name, workspace_id, kill_trigger_type;

-- Domain burn breakdown by trigger type
CREATE OR REPLACE VIEW domain_burn_summary AS
SELECT
    domain_id,
    domain_name,
    workspace_id,
    kill_trigger_type,
    COUNT(*) as burn_count,
    COUNT(DISTINCT campaign_id) as campaigns_affected,
    MIN(burned_at) as first_burn,
    MAX(burned_at) as last_burn
FROM campaign_burn_events
WHERE domain_id IS NOT NULL
GROUP BY domain_id, domain_name, workspace_id, kill_trigger_type;

-- Recent burns (last 7 days) aggregated
CREATE OR REPLACE VIEW recent_burn_summary AS
SELECT
    workspace_id,
    kill_trigger_type,
    COUNT(*) as burn_count_7d,
    COUNT(DISTINCT campaign_id) as campaigns_affected_7d,
    COUNT(DISTINCT domain_id) as domains_affected_7d
FROM campaign_burn_events
WHERE burned_at >= NOW() - INTERVAL '7 days'
GROUP BY workspace_id, kill_trigger_type;

-- ============================================================================
-- BACKFILL FROM EXISTING DEAD INBOXES
-- ============================================================================
-- Populate historical burn events from existing dead inboxes + campaign assignments

INSERT INTO campaign_burn_events (
    workspace_id,
    campaign_id,
    inbox_id,
    domain_id,
    kill_trigger_type,
    campaign_name,
    inbox_email,
    domain_name,
    burned_at,
    created_at
)
SELECT DISTINCT
    sa.workspace_id,
    ci.campaign_id,
    sa.id as inbox_id,
    sa.domain_id,
    COALESCE(sa.kill_trigger::TEXT, 'unknown') as kill_trigger_type,
    ec.campaign_name,
    sa.email_address as inbox_email,
    d.domain_name,
    COALESCE(sa.killed_at, sa.updated_at, NOW()) as burned_at,
    NOW() as created_at
FROM sender_accounts sa
JOIN campaign_inboxes ci ON ci.sender_account_id = sa.id
JOIN emailbison_campaigns ec ON ci.campaign_id = ec.id
LEFT JOIN domains d ON sa.domain_id = d.id
WHERE sa.inbox_state = 'dead'
  AND sa.killed_at IS NOT NULL
ON CONFLICT (campaign_id, inbox_id) DO NOTHING;

-- Log the backfill count
DO $$
DECLARE
    backfill_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO backfill_count FROM campaign_burn_events;
    RAISE NOTICE 'Backfilled % campaign burn events from existing dead inboxes', backfill_count;
END $$;

COMMENT ON TABLE campaign_burn_events IS
'Tracks each inbox death attributed to campaigns for granular trigger analysis.
Enables: "Campaign X burned 5 inboxes - 3 spam_complaint, 2 hard_blocked_24h"';
