-- Migration: 001_add_client_profile_columns.sql
-- Purpose: Add dedicated profile columns to clients table for basic info
-- Date: 2026-01-16

-- Add profile columns
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_name VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS contact_email VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS industry VARCHAR(100);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS domain_pattern VARCHAR(255);

-- Add comment for documentation
COMMENT ON COLUMN clients.contact_name IS 'Primary contact name for the client';
COMMENT ON COLUMN clients.contact_email IS 'Primary contact email for the client';
COMMENT ON COLUMN clients.website IS 'Client website URL';
COMMENT ON COLUMN clients.industry IS 'Client industry (e.g., E-commerce, SaaS)';
COMMENT ON COLUMN clients.domain_pattern IS 'Common domain suffix pattern (e.g., checkoutcomponents.com)';
