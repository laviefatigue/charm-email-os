-- Migration 086: Engagement Counters & Inbox Engagement Snapshots
-- Captures positive engagement signals from EmailBison per inbox and rolls up to domain level.
-- Previously we only tracked negative signals (bounces, complaints). This adds opens, unique
-- replies, interested leads, leads contacted, and unsubscribes — enabling ESP performance
-- comparison and data-driven infrastructure allocation.

-- ============================================================================
-- 1. All-time engagement counters on sender_accounts (from /api/sender-emails)
-- ============================================================================
-- These are returned by EB in every sync cycle but were previously dropped.
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS total_opened_count INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS unique_opened_count INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS unique_replied_count INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS total_leads_contacted_count INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS interested_leads_count INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS unsubscribed_count INTEGER DEFAULT 0;

-- 7-day windowed engagement (derived from inbox_engagement_snapshots)
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS opens_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS unique_opens_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS replies_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS interested_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS sent_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS unsubscribed_7d INTEGER DEFAULT 0;
ALTER TABLE sender_accounts ADD COLUMN IF NOT EXISTS engagement_synced_at TIMESTAMPTZ;

-- ============================================================================
-- 2. Domain-level engagement rollup columns
-- ============================================================================
-- All-time
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_opens_all_time BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_unique_opens_all_time BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_unique_replies_all_time BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_leads_contacted_all_time BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_interested_leads_all_time BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_unsubscribes_all_time BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_sends_all_time BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS engagement_rolled_up_at TIMESTAMPTZ;

-- 7-day windowed
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_opens_7d INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_unique_opens_7d INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_replies_7d INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_interested_7d INTEGER DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_sent_7d BIGINT DEFAULT 0;
ALTER TABLE domains ADD COLUMN IF NOT EXISTS domain_unsubscribed_7d INTEGER DEFAULT 0;

-- ============================================================================
-- 3. Inbox engagement snapshots table (daily time-series per inbox)
-- ============================================================================
-- Follows warmup_snapshots pattern (migration 083). Populated by:
-- - backfill_engagement_90d.py (one-time historical load)
-- - sync_engagement.py daily snapshot job (ongoing)
CREATE TABLE IF NOT EXISTS inbox_engagement_snapshots (
    id BIGSERIAL PRIMARY KEY,
    sender_account_id UUID NOT NULL REFERENCES sender_accounts(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    snapshot_date DATE NOT NULL,
    opens INTEGER DEFAULT 0,
    unique_opens INTEGER DEFAULT 0,
    replies INTEGER DEFAULT 0,
    interested INTEGER DEFAULT 0,
    sent INTEGER DEFAULT 0,
    bounced INTEGER DEFAULT 0,
    unsubscribed INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT inbox_engagement_snapshots_unique UNIQUE (sender_account_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_inbox_engagement_snapshots_account_date
    ON inbox_engagement_snapshots(sender_account_id, snapshot_date);
CREATE INDEX IF NOT EXISTS idx_inbox_engagement_snapshots_workspace_date
    ON inbox_engagement_snapshots(workspace_id, snapshot_date);

-- ============================================================================
-- 4. Domain engagement rollup function
-- ============================================================================
CREATE OR REPLACE FUNCTION rollup_domain_engagement(p_domain_id UUID)
RETURNS VOID AS $$
BEGIN
    UPDATE domains
    SET
        -- All-time counters
        domain_opens_all_time = sub.total_opens,
        domain_unique_opens_all_time = sub.unique_opens,
        domain_unique_replies_all_time = sub.unique_replies,
        domain_leads_contacted_all_time = sub.leads_contacted,
        domain_interested_leads_all_time = sub.interested_leads,
        domain_unsubscribes_all_time = sub.unsubscribes,
        domain_sends_all_time = sub.total_sends,
        -- 7-day windowed
        domain_opens_7d = sub.opens_7d,
        domain_unique_opens_7d = sub.unique_opens_7d,
        domain_replies_7d = sub.replies_7d,
        domain_interested_7d = sub.interested_7d,
        domain_sent_7d = sub.sent_7d,
        domain_unsubscribed_7d = sub.unsubscribed_7d,
        engagement_rolled_up_at = NOW(),
        updated_at = NOW()
    FROM (
        SELECT
            COALESCE(SUM(total_opened_count), 0) AS total_opens,
            COALESCE(SUM(unique_opened_count), 0) AS unique_opens,
            COALESCE(SUM(unique_replied_count), 0) AS unique_replies,
            COALESCE(SUM(total_leads_contacted_count), 0) AS leads_contacted,
            COALESCE(SUM(interested_leads_count), 0) AS interested_leads,
            COALESCE(SUM(unsubscribed_count), 0) AS unsubscribes,
            COALESCE(SUM(emails_sent_all_time), 0) AS total_sends,
            COALESCE(SUM(opens_7d), 0) AS opens_7d,
            COALESCE(SUM(unique_opens_7d), 0) AS unique_opens_7d,
            COALESCE(SUM(replies_7d), 0) AS replies_7d,
            COALESCE(SUM(interested_7d), 0) AS interested_7d,
            COALESCE(SUM(sent_7d), 0) AS sent_7d,
            COALESCE(SUM(unsubscribed_7d), 0) AS unsubscribed_7d
        FROM sender_accounts
        WHERE domain_id = p_domain_id AND is_active = TRUE
    ) sub
    WHERE domains.id = p_domain_id;
END;
$$ LANGUAGE plpgsql;

-- Bulk version for workspace
CREATE OR REPLACE FUNCTION rollup_all_domain_engagement(p_workspace_id UUID)
RETURNS INTEGER AS $$
DECLARE
    v_domain RECORD;
    v_count INTEGER := 0;
BEGIN
    FOR v_domain IN
        SELECT id FROM domains
        WHERE workspace_id = p_workspace_id
          AND is_active = TRUE
          AND pool_status NOT IN ('cancelled', 'unassigned')
    LOOP
        PERFORM rollup_domain_engagement(v_domain.id);
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 5. ESP performance comparison view
-- ============================================================================
CREATE OR REPLACE VIEW v_esp_performance AS
SELECT
    d.workspace_id,
    CASE
        WHEN sa.esp::text = 'microsoft' THEN 'entra'
        WHEN sa.esp::text = 'gmail' THEN 'google'
        ELSE sa.esp::text
    END AS provider,
    COUNT(DISTINCT d.id) AS domain_count,
    COUNT(sa.id) AS inbox_count,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live') AS live_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'dead') AS dead_inboxes,
    COUNT(sa.id) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS operational_inboxes,
    -- Volume
    COALESCE(SUM(sa.emails_sent_all_time), 0) AS total_sent,
    COALESCE(SUM(sa.total_leads_contacted_count), 0) AS leads_contacted,
    -- Positive signals
    COALESCE(SUM(sa.total_opened_count), 0) AS total_opens,
    COALESCE(SUM(sa.unique_opened_count), 0) AS unique_opens,
    COALESCE(SUM(sa.replies_all_time), 0) AS total_replies,
    COALESCE(SUM(sa.unique_replied_count), 0) AS unique_replies,
    COALESCE(SUM(sa.interested_leads_count), 0) AS interested_leads,
    -- Negative signals
    COALESCE(SUM(sa.bounces_all_time), 0) AS total_bounces,
    COALESCE(SUM(sa.complaints_lifetime), 0) AS total_complaints,
    COALESCE(SUM(sa.unsubscribed_count), 0) AS total_unsubscribes,
    -- Rates (safe division)
    CASE WHEN SUM(sa.emails_sent_all_time) > 0
        THEN ROUND(SUM(sa.unique_opened_count)::NUMERIC / SUM(sa.emails_sent_all_time) * 100, 2)
        ELSE 0 END AS open_rate_pct,
    CASE WHEN SUM(sa.emails_sent_all_time) > 0
        THEN ROUND(SUM(sa.unique_replied_count)::NUMERIC / SUM(sa.emails_sent_all_time) * 100, 2)
        ELSE 0 END AS reply_rate_pct,
    CASE WHEN SUM(sa.emails_sent_all_time) > 0
        THEN ROUND(SUM(sa.interested_leads_count)::NUMERIC / SUM(sa.emails_sent_all_time) * 100, 2)
        ELSE 0 END AS interest_rate_pct,
    CASE WHEN SUM(sa.emails_sent_all_time) > 0
        THEN ROUND(SUM(sa.bounces_all_time)::NUMERIC / SUM(sa.emails_sent_all_time) * 100, 2)
        ELSE 0 END AS bounce_rate_pct,
    CASE WHEN SUM(sa.emails_sent_all_time) > 0
        THEN ROUND(SUM(sa.complaints_lifetime)::NUMERIC / SUM(sa.emails_sent_all_time) * 100, 3)
        ELSE 0 END AS complaint_rate_pct
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.is_active = TRUE
GROUP BY d.workspace_id,
    CASE
        WHEN sa.esp::text = 'microsoft' THEN 'entra'
        WHEN sa.esp::text = 'gmail' THEN 'google'
        ELSE sa.esp::text
    END;
