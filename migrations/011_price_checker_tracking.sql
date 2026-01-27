-- Migration 011: Price Checker Tracking
-- Adds column to track when domain prices were last checked

-- Add last_price_check timestamp to domains table
ALTER TABLE domains ADD COLUMN IF NOT EXISTS last_price_check TIMESTAMP WITH TIME ZONE;

-- Index for efficient querying of stale prices
CREATE INDEX IF NOT EXISTS idx_domains_last_price_check ON domains(last_price_check);

-- Comment explaining the column
COMMENT ON COLUMN domains.last_price_check IS 'Timestamp of the last price check by the continuous price checker worker';
