-- Migration: 064_user_activity_tracking.sql
-- Description: User and activity tracking tables for audit trail
-- Date: 2026-03-03

-- ============================================================================
-- Users table (auto-populated from Cloudflare Access)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users(last_seen_at);

COMMENT ON TABLE users IS 'Authenticated users from Cloudflare Access Google OAuth (@hirecharm.com)';
COMMENT ON COLUMN users.email IS 'Email from CF-Access-Authenticated-User-Email header';
COMMENT ON COLUMN users.display_name IS 'Derived from email (e.g., elliott@hirecharm.com -> Elliott)';

-- ============================================================================
-- Activity log table for audit trail
-- ============================================================================
CREATE TABLE IF NOT EXISTS activity_log (
    id SERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    user_email VARCHAR(255) NOT NULL,  -- Denormalized for query performance
    action VARCHAR(100) NOT NULL,       -- e.g., 'domain_purchased', 'hypertide_order_created'
    resource_type VARCHAR(50),          -- e.g., 'domain', 'inbox', 'client'
    resource_id VARCHAR(255),           -- UUID or identifier of affected resource
    details JSONB,                      -- Additional context
    ip_address VARCHAR(45),             -- IPv4 or IPv6
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_log_user_email ON activity_log(user_email);
CREATE INDEX IF NOT EXISTS idx_activity_log_user_id ON activity_log(user_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_action ON activity_log(action);
CREATE INDEX IF NOT EXISTS idx_activity_log_resource ON activity_log(resource_type, resource_id);
CREATE INDEX IF NOT EXISTS idx_activity_log_created ON activity_log(created_at DESC);

COMMENT ON TABLE activity_log IS 'Audit trail of user actions for compliance and debugging';
COMMENT ON COLUMN activity_log.action IS 'Action type: domain_purchased, hypertide_order_created, client_updated, etc.';
COMMENT ON COLUMN activity_log.details IS 'JSONB with action-specific context (domain_name, price, etc.)';

-- ============================================================================
-- Trigger to update users.updated_at
-- ============================================================================
CREATE OR REPLACE FUNCTION update_users_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_users_timestamp();
