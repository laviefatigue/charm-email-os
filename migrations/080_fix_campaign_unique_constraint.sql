-- Migration: 080_fix_campaign_unique_constraint.sql
-- Purpose: Add missing UNIQUE constraint for campaign upserts
-- Issue: Campaign sync failing with "no unique or exclusion constraint matching ON CONFLICT"
--
-- The upsert_campaign function uses:
--   ON CONFLICT (workspace_id, emailbison_campaign_id) DO UPDATE SET ...
-- But this constraint was never created, causing all campaign syncs to fail.

-- Add the missing unique constraint
-- Using IF NOT EXISTS pattern with DO block for idempotency
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'emailbison_campaigns_workspace_campaign_unique'
    ) THEN
        ALTER TABLE emailbison_campaigns
        ADD CONSTRAINT emailbison_campaigns_workspace_campaign_unique
        UNIQUE (workspace_id, emailbison_campaign_id);
    END IF;
END $$;

-- Also add an index for faster lookups during sync
CREATE INDEX IF NOT EXISTS idx_emailbison_campaigns_workspace_ebid
ON emailbison_campaigns(workspace_id, emailbison_campaign_id);

COMMENT ON CONSTRAINT emailbison_campaigns_workspace_campaign_unique ON emailbison_campaigns IS
'Required for ON CONFLICT upsert in campaign sync - see sync_modules/sync_campaigns.py';
