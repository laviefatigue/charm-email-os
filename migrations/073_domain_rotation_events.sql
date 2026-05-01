-- Migration 073: Domain Rotation Events & Quarantine Support
-- Created: 2026-03-05
-- Purpose: Track domain-level rotation events for domain-killing triggers
--          and support B-Set quarantine when domain is compromised

-- =============================================================================
-- DOMAIN ROTATION EVENTS TABLE
-- =============================================================================
-- Tracks domain-level events like quarantine, rotation requests, replacements
-- This is separate from inbox_rotation_history which tracks inbox-level changes

CREATE TABLE IF NOT EXISTS domain_rotation_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Core relationships
    domain_id UUID NOT NULL REFERENCES domains(id),
    workspace_id UUID NOT NULL REFERENCES workspaces(id),

    -- Event details
    event_type VARCHAR(50) NOT NULL,
    -- event_types: 'quarantine', 'rotation_requested', 'rotation_completed', 'retired'

    trigger_type VARCHAR(50),
    -- The kill trigger that caused this event (spam_complaint, provider_block_*, etc.)

    trigger_inbox_email VARCHAR(255),
    -- The inbox that triggered the domain event

    -- State tracking
    old_status VARCHAR(50),
    new_status VARCHAR(50),

    -- Impact metrics
    a_set_remaining INTEGER DEFAULT 0,
    b_set_quarantined INTEGER DEFAULT 0,

    -- Context
    notes TEXT,
    metadata JSONB,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_domain_rotation_events_domain
ON domain_rotation_events(domain_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_domain_rotation_events_workspace
ON domain_rotation_events(workspace_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_domain_rotation_events_type
ON domain_rotation_events(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_domain_rotation_events_trigger
ON domain_rotation_events(trigger_type) WHERE trigger_type IS NOT NULL;

-- =============================================================================
-- UPDATE INVENTORY_POOL_STATUS COMMENT
-- =============================================================================
-- Add 'quarantined' to the documented values

COMMENT ON COLUMN sender_accounts.inventory_pool_status IS
'Pool status: deployed (A-Set, in campaigns), reserve (B-Set, ready pool), warning (needs cooldown), quarantined (domain compromised, do not promote)';

-- =============================================================================
-- ADD METADATA COLUMN TO INBOX_ROTATION_HISTORY (if not exists)
-- =============================================================================
-- For storing additional context like domain quarantine details

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'inbox_rotation_history' AND column_name = 'metadata'
    ) THEN
        ALTER TABLE inbox_rotation_history ADD COLUMN metadata JSONB;
    END IF;
END $$;

-- =============================================================================
-- VIEW: Domain Quarantine Status
-- =============================================================================
-- Shows domains with quarantined inboxes for operational review

CREATE OR REPLACE VIEW v_domain_quarantine_status AS
SELECT
    d.id as domain_id,
    d.domain_name,
    d.domain_state,
    w.workspace_name,

    -- Inbox counts by pool status
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.inventory_pool_status = 'deployed') as a_set_live,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.inventory_pool_status = 'reserve') as b_set_live,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.inventory_pool_status = 'quarantined') as quarantined_count,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_count,

    -- Latest quarantine event
    (
        SELECT dre.trigger_type
        FROM domain_rotation_events dre
        WHERE dre.domain_id = d.id AND dre.event_type = 'quarantine'
        ORDER BY dre.created_at DESC LIMIT 1
    ) as quarantine_trigger,

    (
        SELECT dre.created_at
        FROM domain_rotation_events dre
        WHERE dre.domain_id = d.id AND dre.event_type = 'quarantine'
        ORDER BY dre.created_at DESC LIMIT 1
    ) as quarantined_at,

    -- Rotation recommendation
    CASE
        WHEN COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.inventory_pool_status = 'quarantined') > 0
        THEN 'rotate_now'
        WHEN d.domain_state = 'dead' THEN 'rotate_now'
        WHEN d.domain_state = 'flagged' THEN 'consider_rotate'
        ELSE 'healthy'
    END as rotation_recommendation

FROM domains d
JOIN workspaces w ON d.workspace_id = w.id
LEFT JOIN sender_accounts sa ON sa.domain_id = d.id
GROUP BY d.id, d.domain_name, d.domain_state, w.workspace_name
HAVING
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.inventory_pool_status = 'quarantined') > 0
    OR d.domain_state IN ('flagged', 'dead')
ORDER BY
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.inventory_pool_status = 'quarantined') DESC,
    d.domain_name;

COMMENT ON VIEW v_domain_quarantine_status IS
'Shows domains with quarantined B-Set inboxes or flagged/dead state. Use for rotation planning.';

-- =============================================================================
-- BACKFILL: Mark existing spam_complaint domains as needing review
-- =============================================================================
-- Find domains that have had spam complaints and log them

INSERT INTO domain_rotation_events (
    domain_id,
    workspace_id,
    event_type,
    trigger_type,
    trigger_inbox_email,
    old_status,
    new_status,
    notes
)
SELECT DISTINCT
    d.id,
    d.workspace_id,
    'quarantine',
    'spam_complaint',
    sa.email_address,
    'active',
    'needs_review',
    'Backfill: Domain had historical spam complaint. Review for rotation.'
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.kill_trigger = 'spam_complaint'
AND sa.killed_at IS NOT NULL
AND NOT EXISTS (
    SELECT 1 FROM domain_rotation_events dre
    WHERE dre.domain_id = d.id AND dre.event_type = 'quarantine'
)
ON CONFLICT DO NOTHING;

-- =============================================================================
-- ADD QUARANTINED COUNT TO DOMAINS TABLE (for waterfall view)
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'domains' AND column_name = 'quarantined_inbox_count'
    ) THEN
        ALTER TABLE domains ADD COLUMN quarantined_inbox_count INTEGER DEFAULT 0;
    END IF;
END $$;

COMMENT ON COLUMN domains.quarantined_inbox_count IS
'Count of B-Set inboxes quarantined due to domain-killing triggers (spam_complaint, provider_block_*). Do not promote these.';

-- Backfill quarantined count from sender_accounts
UPDATE domains d
SET quarantined_inbox_count = (
    SELECT COUNT(*)
    FROM sender_accounts sa
    WHERE sa.domain_id = d.id
    AND sa.inbox_state = 'live'
    AND sa.inventory_pool_status = 'quarantined'
);

-- =============================================================================
-- FUNCTION: Recalculate quarantined count (called after quarantine events)
-- =============================================================================

CREATE OR REPLACE FUNCTION recalculate_domain_quarantine_count(p_domain_id UUID)
RETURNS void AS $$
BEGIN
    UPDATE domains
    SET quarantined_inbox_count = (
        SELECT COUNT(*)
        FROM sender_accounts
        WHERE domain_id = p_domain_id
        AND inbox_state = 'live'
        AND inventory_pool_status = 'quarantined'
    ),
    updated_at = NOW()
    WHERE id = p_domain_id;
END;
$$ LANGUAGE plpgsql;

-- Log migration
DO $$
DECLARE
    quarantine_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO quarantine_count
    FROM domain_rotation_events
    WHERE event_type = 'quarantine';

    RAISE NOTICE 'Migration 073: Created domain_rotation_events table';
    RAISE NOTICE 'Migration 073: Added quarantined_inbox_count to domains';
    RAISE NOTICE 'Migration 073: % domains flagged for quarantine review', quarantine_count;
END $$;
