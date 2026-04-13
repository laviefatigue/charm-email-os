-- Migration 087: Client kickoff expansion
-- Adds Slack channel and ClickUp tracking to clients table
-- Supports the full client creation kickoff chain:
--   1. Client record + workspace (already exists)
--   2. Slack channel auto-creation per client
--   3. ClickUp project folder (future integration)

-- Slack channel created on client creation
ALTER TABLE clients ADD COLUMN IF NOT EXISTS slack_channel_id VARCHAR(20);

-- ClickUp folder (future integration)
ALTER TABLE clients ADD COLUMN IF NOT EXISTS clickup_folder_id VARCHAR(50);

-- Index for Slack channel lookups
CREATE INDEX IF NOT EXISTS idx_clients_slack_channel
  ON clients(slack_channel_id) WHERE slack_channel_id IS NOT NULL;

COMMENT ON COLUMN clients.slack_channel_id IS 'Slack channel ID auto-created on client creation';
COMMENT ON COLUMN clients.clickup_folder_id IS 'ClickUp folder ID (future integration)';
