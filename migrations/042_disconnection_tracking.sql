-- Migration 042: Disconnection Tracking
-- Adds timestamp tracking for when inboxes become disconnected
-- Enables alerting/notification workflows (Slack, email to HyperTide)

-- Add disconnected_at column to sender_accounts
ALTER TABLE sender_accounts
ADD COLUMN IF NOT EXISTS disconnected_at TIMESTAMPTZ;

-- Add index for efficient querying of disconnected inboxes
CREATE INDEX IF NOT EXISTS idx_sender_accounts_disconnected
ON sender_accounts(disconnected_at)
WHERE disconnected_at IS NOT NULL;

-- Add composite index for workspace + disconnected queries
CREATE INDEX IF NOT EXISTS idx_sender_accounts_workspace_disconnected
ON sender_accounts(workspace_id, disconnected_at)
WHERE disconnected_at IS NOT NULL AND inbox_state = 'live';

-- Comment for documentation
COMMENT ON COLUMN sender_accounts.disconnected_at IS 'Timestamp when inbox was detected as disconnected from EmailBison. NULL if currently connected.';

-- Backfill: Set disconnected_at for currently disconnected inboxes (first seen as disconnected)
-- Uses last_synced_at as best approximation for existing disconnected inboxes
UPDATE sender_accounts
SET disconnected_at = COALESCE(last_synced_at, updated_at, NOW())
WHERE status = 'Not connected'
  AND disconnected_at IS NULL
  AND inbox_state = 'live';

-- View: Currently disconnected inboxes with duration
CREATE OR REPLACE VIEW v_disconnected_inboxes AS
SELECT
    sa.id,
    sa.email_address,
    sa.workspace_id,
    w.workspace_name,
    c.id as client_id,
    c.name as client_name,
    sa.disconnected_at,
    EXTRACT(EPOCH FROM (NOW() - sa.disconnected_at)) / 3600 as hours_disconnected,
    EXTRACT(EPOCH FROM (NOW() - sa.disconnected_at)) / 86400 as days_disconnected,
    d.domain_name,
    sa.esp,
    sa.warmup_started_at,
    sa.inventory_lifecycle_status,
    sa.inventory_pool_status
FROM sender_accounts sa
JOIN workspaces w ON sa.workspace_id = w.id
LEFT JOIN clients c ON c.workspace_id = w.id
LEFT JOIN domains d ON sa.domain_id = d.id
WHERE sa.status = 'Not connected'
  AND sa.inbox_state = 'live'
  AND sa.disconnected_at IS NOT NULL
ORDER BY sa.disconnected_at ASC;  -- Oldest first (needs attention)

-- View: Disconnection summary by client (for alerting)
CREATE OR REPLACE VIEW v_disconnection_summary AS
SELECT
    c.id as client_id,
    c.name as client_name,
    COUNT(*) as disconnected_count,
    MIN(sa.disconnected_at) as oldest_disconnection,
    MAX(sa.disconnected_at) as newest_disconnection,
    COUNT(*) FILTER (WHERE sa.disconnected_at < NOW() - INTERVAL '24 hours') as disconnected_over_24h,
    COUNT(*) FILTER (WHERE sa.disconnected_at < NOW() - INTERVAL '7 days') as disconnected_over_7d,
    ARRAY_AGG(DISTINCT d.domain_name) FILTER (WHERE d.domain_name IS NOT NULL) as affected_domains
FROM sender_accounts sa
JOIN workspaces w ON sa.workspace_id = w.id
LEFT JOIN clients c ON c.workspace_id = w.id
LEFT JOIN domains d ON sa.domain_id = d.id
WHERE sa.status = 'Not connected'
  AND sa.inbox_state = 'live'
  AND sa.disconnected_at IS NOT NULL
GROUP BY c.id, c.name
ORDER BY disconnected_count DESC;
