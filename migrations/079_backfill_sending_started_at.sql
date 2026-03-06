-- Migration: 079_backfill_sending_started_at.sql
-- Purpose: Backfill sending_started_at from earliest campaign assignment
--
-- sending_started_at = when inbox first started campaign sending (not warmup graduation)
-- Source: campaign_inboxes.assigned_at (earliest assignment per inbox)

-- Backfill from campaign_inboxes
UPDATE sender_accounts sa
SET sending_started_at = earliest.first_campaign_assignment
FROM (
    SELECT
        sender_account_id,
        MIN(assigned_at) as first_campaign_assignment
    FROM campaign_inboxes
    WHERE sender_account_id IS NOT NULL
    AND assigned_at IS NOT NULL
    GROUP BY sender_account_id
) earliest
WHERE sa.id = earliest.sender_account_id
AND sa.sending_started_at IS NULL;

-- Report stats
SELECT
    COUNT(*) as total_inboxes,
    COUNT(sending_started_at) as has_sending_started_at,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND sending_started_at IS NOT NULL) as dead_with_sending_date,
    COUNT(*) FILTER (WHERE kill_trigger = 'spam_complaint' AND sending_started_at IS NOT NULL) as spam_complaints_with_sending_date
FROM sender_accounts;

SELECT 'Migration 079_backfill_sending_started_at complete' AS status;
