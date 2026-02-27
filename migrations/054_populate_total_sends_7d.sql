-- Migration: 054_populate_total_sends_7d.sql
-- Purpose: Initialize total_sends_7d for existing inboxes
--
-- Background:
--   total_sends_7d was never populated, causing rate-based kill triggers to fail.
--   Rate calculation: bounce_rate = hard_bounces_7d / total_sends_7d
--   With total_sends_7d = 0, the denominator check fails and triggers never fire.
--
-- Approach:
--   Since we don't have historical daily send data, we use heuristics:
--   1. For live inboxes with campaign activity: estimate from daily_limit * 7
--   2. For inboxes in campaigns: use campaign snapshot data if available
--   3. Apply conservative estimates to avoid false positive kills
--
-- After this migration:
--   - sync_accounts.py will track send deltas going forward
--   - health_checks.py daily decay (0.86x) maintains 7-day window
--   - Rate-based kill triggers will start firing correctly

BEGIN;

-- Method 1: Use campaign snapshots to estimate per-inbox sends
-- Sum recent campaign sends and divide by active inboxes in each campaign
WITH campaign_send_rates AS (
    -- Get recent campaign activity (last 7 days)
    SELECT
        ec.id as campaign_id,
        ec.workspace_id,
        -- Get total sends from latest snapshot for each campaign
        COALESCE((
            SELECT emails_sent
            FROM campaign_snapshots cs
            WHERE cs.campaign_id = ec.id
            ORDER BY snapshot_timestamp DESC
            LIMIT 1
        ), 0) as total_campaign_sends,
        -- Count active inboxes in this campaign
        (SELECT COUNT(*) FROM campaign_inboxes ci
         WHERE ci.campaign_id = ec.id AND ci.is_active = TRUE) as inbox_count
    FROM emailbison_campaigns ec
    WHERE ec.campaign_status IN ('active', 'running', 'sending')
),
inbox_send_estimates AS (
    -- Distribute campaign sends across inboxes (simple equal distribution)
    SELECT
        ci.sender_account_id,
        SUM(
            CASE WHEN csr.inbox_count > 0
            THEN csr.total_campaign_sends / csr.inbox_count
            ELSE 0 END
        ) as estimated_sends_7d
    FROM campaign_inboxes ci
    JOIN campaign_send_rates csr ON ci.campaign_id = csr.campaign_id
    WHERE ci.is_active = TRUE
    GROUP BY ci.sender_account_id
)
UPDATE sender_accounts sa
SET
    total_sends_7d = GREATEST(
        COALESCE(sa.total_sends_7d, 0),  -- Keep existing if higher
        COALESCE(ise.estimated_sends_7d, 0)::INTEGER
    ),
    updated_at = NOW()
FROM inbox_send_estimates ise
WHERE sa.id = ise.sender_account_id
  AND sa.inbox_state = 'live';

-- Method 2: For inboxes not in active campaigns, use daily_limit heuristic
-- Conservative: assume 50% utilization over 7 days
UPDATE sender_accounts
SET
    total_sends_7d = GREATEST(
        COALESCE(total_sends_7d, 0),
        -- 50% of daily_limit * 7 days
        (COALESCE(daily_limit, 0) * 7 * 0.5)::INTEGER
    ),
    updated_at = NOW()
WHERE inbox_state = 'live'
  AND total_sends_7d = 0
  AND daily_limit > 0;

-- Method 3: For any remaining live inboxes with all-time sends but no 7d estimate
-- Use a conservative 10% of all-time sends as 7d estimate
UPDATE sender_accounts
SET
    total_sends_7d = GREATEST(
        1,  -- Minimum 1 to avoid division by zero
        (COALESCE(emails_sent_all_time, 0) * 0.1)::INTEGER
    ),
    updated_at = NOW()
WHERE inbox_state = 'live'
  AND total_sends_7d = 0
  AND emails_sent_all_time > 0;

-- Log results
DO $$
DECLARE
    total_updated INTEGER;
    with_sends INTEGER;
    still_zero INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_updated
    FROM sender_accounts WHERE inbox_state = 'live';

    SELECT COUNT(*) INTO with_sends
    FROM sender_accounts WHERE inbox_state = 'live' AND total_sends_7d > 0;

    SELECT COUNT(*) INTO still_zero
    FROM sender_accounts WHERE inbox_state = 'live' AND total_sends_7d = 0;

    RAISE NOTICE 'total_sends_7d population complete:';
    RAISE NOTICE '  Total live inboxes: %', total_updated;
    RAISE NOTICE '  With sends populated: %', with_sends;
    RAISE NOTICE '  Still zero (inactive/new): %', still_zero;
END $$;

COMMIT;

-- Verification query (run after migration):
-- SELECT
--     workspace_id,
--     COUNT(*) as total_live,
--     COUNT(*) FILTER (WHERE total_sends_7d > 0) as has_sends,
--     COUNT(*) FILTER (WHERE total_sends_7d = 0) as zero_sends,
--     AVG(total_sends_7d) as avg_sends_7d
-- FROM sender_accounts
-- WHERE inbox_state = 'live'
-- GROUP BY workspace_id;
