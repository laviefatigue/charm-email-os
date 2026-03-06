-- Migration 072: Add unique constraint on sender_accounts for upsert operations
-- Required for ON CONFLICT (workspace_id, email_address) to work

-- First, remove any duplicates (keep the most recent)
DELETE FROM sender_accounts a
USING sender_accounts b
WHERE a.workspace_id = b.workspace_id
  AND a.email_address = b.email_address
  AND a.id < b.id;

-- Add unique constraint
ALTER TABLE sender_accounts
ADD CONSTRAINT sender_accounts_workspace_email_unique
UNIQUE (workspace_id, email_address);
