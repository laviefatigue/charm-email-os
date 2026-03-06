-- Diagnostic: Kill Trigger Data Quality Analysis
-- Run this BEFORE migration 081 to understand the data gaps

-- 1. Overall state of dead inboxes
SELECT 'DEAD INBOX SUMMARY' as section;
SELECT
    COUNT(*) as total_dead,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as has_trigger,
    COUNT(*) FILTER (WHERE kill_trigger IS NULL) as missing_trigger,
    COUNT(*) FILTER (WHERE killed_at IS NOT NULL) as has_killed_at,
    COUNT(*) FILTER (WHERE killed_at IS NULL) as missing_killed_at,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / NULLIF(COUNT(*), 0), 1) as pct_tracked
FROM sender_accounts
WHERE inbox_state = 'dead';

-- 2. By workspace
SELECT 'BY WORKSPACE' as section;
SELECT
    w.workspace_name,
    COUNT(*) as total_dead,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) as has_trigger,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NULL) as missing_trigger,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) / NULLIF(COUNT(*), 0), 1) as pct_tracked
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
JOIN workspaces w ON d.workspace_id = w.id
WHERE sa.inbox_state = 'dead'
GROUP BY w.workspace_name
ORDER BY missing_trigger DESC;

-- 3. Available data sources for backfill
SELECT 'DATA SOURCES AVAILABLE' as section;

SELECT 'campaign_events (bounce)' as source,
    COUNT(DISTINCT sender_account_id) as inboxes_with_data
FROM campaign_events
WHERE event_type = 'bounce'
  AND sender_account_id IN (
    SELECT id FROM sender_accounts WHERE inbox_state = 'dead' AND kill_trigger IS NULL
  );

SELECT 'campaign_events (spam)' as source,
    COUNT(DISTINCT sender_account_id) as inboxes_with_data
FROM campaign_events
WHERE event_type = 'spam'
  AND sender_account_id IN (
    SELECT id FROM sender_accounts WHERE inbox_state = 'dead' AND kill_trigger IS NULL
  );

SELECT 'health_events' as source,
    COUNT(DISTINCT entity_id) as inboxes_with_data
FROM health_events
WHERE entity_type = 'inbox'
  AND entity_id IN (
    SELECT id FROM sender_accounts WHERE inbox_state = 'dead' AND kill_trigger IS NULL
  );

SELECT 'kill_trigger_events' as source,
    COUNT(DISTINCT inbox_id) as inboxes_with_data
FROM kill_trigger_events
WHERE inbox_id IN (
    SELECT id FROM sender_accounts WHERE inbox_state = 'dead' AND kill_trigger IS NULL
  );

SELECT 'kill_queue' as source,
    COUNT(DISTINCT inbox_id) as inboxes_with_data
FROM kill_queue
WHERE inbox_id IN (
    SELECT id FROM sender_accounts WHERE inbox_state = 'dead' AND kill_trigger IS NULL
  );

SELECT 'inbox_removal_events' as source,
    COUNT(DISTINCT sender_account_id) as inboxes_with_data
FROM inbox_removal_events
WHERE sender_account_id IN (
    SELECT id FROM sender_accounts WHERE inbox_state = 'dead' AND kill_trigger IS NULL
  );

-- 4. Metric-based inference potential
SELECT 'METRIC INFERENCE POTENTIAL' as section;
SELECT
    CASE
        WHEN complaints_lifetime > 0 THEN 'has_complaints'
        WHEN bounces_all_time > 0 THEN 'has_bounces'
        ELSE 'no_metrics'
    END as inference_type,
    COUNT(*) as count
FROM sender_accounts
WHERE inbox_state = 'dead'
  AND kill_trigger IS NULL
GROUP BY 1
ORDER BY count DESC;

-- 5. Sample of untracked deaths
SELECT 'SAMPLE UNTRACKED DEATHS (10)' as section;
SELECT
    sa.id,
    LEFT(sa.email_address, 30) as email,
    w.workspace_name,
    sa.inbox_state,
    sa.complaints_lifetime,
    sa.bounces_all_time,
    sa.warmup_started_at::date as warmup_date,
    sa.updated_at::date as updated_date
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
JOIN workspaces w ON d.workspace_id = w.id
WHERE sa.inbox_state = 'dead'
  AND sa.kill_trigger IS NULL
LIMIT 10;
