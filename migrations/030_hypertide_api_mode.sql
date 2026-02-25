-- Migration 030: Hypertide API Execution Mode Support
-- Adds api_response column and index for REST API-based inbox purchasing
-- Extends worker_mode to support 'api' value alongside 'worker' and 'slack_only'
--
-- Run: psql -h localhost -p 5433 -U postgres -d postgres -f migrations/030_hypertide_api_mode.sql

BEGIN;

-- Add api_response column for debugging and verification
-- Stores sanitized Hypertide API response (order IDs, inboxes created, etc.)
ALTER TABLE inbox_purchase_jobs
ADD COLUMN IF NOT EXISTS api_response JSONB;

COMMENT ON COLUMN inbox_purchase_jobs.api_response IS 'Sanitized Hypertide API response (order IDs, inbox count, costs)';

-- Create index for API worker polling (mirrors existing worker index)
-- The worker at Hypertide-API/src/hypertide_api/worker.py polls for worker_mode='api'
CREATE INDEX IF NOT EXISTS idx_purchase_jobs_pending_api
ON inbox_purchase_jobs(status, worker_mode)
WHERE status = 'pending' AND worker_mode = 'api';

-- Update comment on worker_mode to document all options
COMMENT ON COLUMN inbox_purchase_jobs.worker_mode IS
    'Job processing mode: background_task/worker (browser automation), api (REST API), slack_only (manual)';

-- Log migration
DO $$
BEGIN
    RAISE NOTICE 'Migration 030 complete: Added api_response column and idx_purchase_jobs_pending_api index';
END $$;

COMMIT;
