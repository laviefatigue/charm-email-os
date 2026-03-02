-- Migration: 063_inbox_audit_tables.sql
-- Description: Tables for Slack-based inbox audit workflow
-- Date: 2026-03-02

-- Audit records - one per daily audit sent to Slack
CREATE TABLE IF NOT EXISTS inbox_audits (
    id SERIAL PRIMARY KEY,
    audit_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, confirmed, issues_found
    reviewed_by VARCHAR(255),  -- Slack user who reviewed
    reviewed_at TIMESTAMPTZ,
    notes TEXT,

    -- Stats snapshot at time of audit
    total_kills INTEGER,
    total_disconnected INTEGER,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_status CHECK (status IN ('pending', 'confirmed', 'issues_found'))
);

-- Index for finding pending audits
CREATE INDEX IF NOT EXISTS idx_inbox_audits_status ON inbox_audits(status);
CREATE INDEX IF NOT EXISTS idx_inbox_audits_date ON inbox_audits(audit_date);

-- Corrections submitted when issues are found
CREATE TABLE IF NOT EXISTS inbox_audit_corrections (
    id SERIAL PRIMARY KEY,
    audit_id INTEGER NOT NULL REFERENCES inbox_audits(id),
    email_address VARCHAR(255) NOT NULL,
    correction_type VARCHAR(50) NOT NULL,  -- wrong_kill, false_positive, should_restore
    reason TEXT,

    -- Resolution tracking
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by VARCHAR(255),
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT valid_correction_type CHECK (
        correction_type IN ('wrong_kill', 'false_positive', 'should_restore', 'other')
    )
);

-- Index for finding unresolved corrections
CREATE INDEX IF NOT EXISTS idx_audit_corrections_unresolved
    ON inbox_audit_corrections(resolved) WHERE resolved = FALSE;
CREATE INDEX IF NOT EXISTS idx_audit_corrections_audit
    ON inbox_audit_corrections(audit_id);

-- Track audit history for reporting
CREATE TABLE IF NOT EXISTS inbox_audit_history (
    id SERIAL PRIMARY KEY,
    audit_id INTEGER NOT NULL REFERENCES inbox_audits(id),
    action VARCHAR(50) NOT NULL,  -- created, sent, confirmed, issues_reported, correction_added
    actor VARCHAR(255),  -- Slack user or 'system'
    details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_history_audit ON inbox_audit_history(audit_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_inbox_audit_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for updated_at
DROP TRIGGER IF EXISTS inbox_audits_updated_at ON inbox_audits;
CREATE TRIGGER inbox_audits_updated_at
    BEFORE UPDATE ON inbox_audits
    FOR EACH ROW
    EXECUTE FUNCTION update_inbox_audit_timestamp();

-- Comment for documentation
COMMENT ON TABLE inbox_audits IS 'Daily inbox health audits sent to Slack for team review';
COMMENT ON TABLE inbox_audit_corrections IS 'Corrections submitted when audit reveals incorrectly flagged inboxes';
COMMENT ON TABLE inbox_audit_history IS 'Audit trail for all audit-related actions';
