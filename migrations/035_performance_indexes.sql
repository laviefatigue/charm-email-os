-- Migration: 035_performance_indexes.sql
-- Purpose: Add performance indexes for domain-inbox joins
-- Related: Option B - Performance First

-- Problem: SPLIT_PART(email_address, '@', 2) = domain_name is expensive
-- Solution: Add functional index on the domain part of email addresses

-- Create functional index on domain part of email address
-- This dramatically speeds up joins between sender_accounts and domains
CREATE INDEX IF NOT EXISTS idx_sender_accounts_email_domain
ON sender_accounts (SPLIT_PART(email_address, '@', 2));

-- Add composite index for common health queries
-- Pattern: WHERE workspace_id = $1 AND inbox_state = 'live' ORDER BY health_score
CREATE INDEX IF NOT EXISTS idx_sender_accounts_workspace_health
ON sender_accounts (workspace_id, inbox_state, health_score DESC)
WHERE is_active = TRUE;

-- Add index for warmup status queries (frequently filtered)
CREATE INDEX IF NOT EXISTS idx_sender_accounts_warmup_status
ON sender_accounts (workspace_id, warmup_enabled, warmup_started_at)
WHERE is_active = TRUE AND inbox_state = 'live';

-- Add index for inventory lifecycle queries
CREATE INDEX IF NOT EXISTS idx_sender_accounts_inventory
ON sender_accounts (workspace_id, inventory_lifecycle_status, inventory_pool_status)
WHERE is_active = TRUE;

-- Domain health composite index
CREATE INDEX IF NOT EXISTS idx_domains_workspace_active
ON domains (workspace_id, status)
WHERE status NOT IN ('rejected', 'denied', 'dead');

-- Analyze tables to update statistics after index creation
ANALYZE sender_accounts;
ANALYZE domains;

SELECT 'Migration 035_performance_indexes complete' AS status;
