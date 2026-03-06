-- Migration: 081_backfill_kill_triggers_historical.sql
-- Purpose: Backfill kill_trigger and killed_at for dead inboxes using ACTUAL event data
--
-- Data Sources (in priority order for timestamps):
-- 1. campaign_events - actual bounce/spam events with real timestamps
-- 2. health_events - trigger detection events
-- 3. inbox_removal_events - removal tracking with tagged_at
-- 4. kill_trigger_events - trigger detection log
-- 5. kill_queue - processed kills with queued_at/tagged_at
--
-- For trigger type:
-- 1. kill_queue / kill_trigger_events - explicit trigger
-- 2. health_events - has trigger_type
-- 3. campaign_events - infer from event_type (spam/bounce)
-- 4. inbox_removal_events - has kill_trigger
-- 5. Metric inference - last resort

-- Step 0: Report current state BEFORE backfill
SELECT 'BEFORE BACKFILL' as stage,
    COUNT(*) FILTER (WHERE inbox_state = 'dead') as total_dead,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND kill_trigger IS NOT NULL) as has_trigger,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND kill_trigger IS NULL) as missing_trigger,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND killed_at IS NOT NULL) as has_killed_at,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND killed_at IS NULL) as missing_killed_at
FROM sender_accounts;

-- Step 1: Add missing values to kill_trigger_type enum
DO $$
DECLARE
    v_values TEXT[] := ARRAY['hard_blocked_24h', 'hard_unknown_24h', 'disconnected_timeout', 'unknown'];
    v_value TEXT;
BEGIN
    FOREACH v_value IN ARRAY v_values
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_enum
            WHERE enumlabel = v_value
            AND enumtypid = 'kill_trigger_type'::regtype
        ) THEN
            EXECUTE format('ALTER TYPE kill_trigger_type ADD VALUE IF NOT EXISTS %L', v_value);
        END IF;
    END LOOP;
END $$;

-- Step 2: Create temp table with best available data for each dead inbox
CREATE TEMP TABLE dead_inbox_events AS
WITH
-- Earliest spam event per inbox from campaign_events
spam_events AS (
    SELECT DISTINCT ON (sender_account_id)
        sender_account_id as inbox_id,
        event_timestamp,
        'spam_complaint' as inferred_trigger
    FROM campaign_events
    WHERE event_type = 'spam'
      AND sender_account_id IS NOT NULL
    ORDER BY sender_account_id, event_timestamp ASC
),
-- Earliest bounce event per inbox from campaign_events
bounce_events AS (
    SELECT DISTINCT ON (sender_account_id)
        sender_account_id as inbox_id,
        event_timestamp,
        'hard_bounces_24h' as inferred_trigger
    FROM campaign_events
    WHERE event_type = 'bounce'
      AND sender_account_id IS NOT NULL
    ORDER BY sender_account_id, event_timestamp ASC
),
-- Health events with trigger_type
health_trigger_events AS (
    SELECT DISTINCT ON (entity_id)
        entity_id as inbox_id,
        event_timestamp,
        trigger_type::text as trigger
    FROM health_events
    WHERE entity_type = 'inbox'
      AND trigger_type IS NOT NULL
    ORDER BY entity_id, event_timestamp ASC
),
-- Inbox removal events
removal_events AS (
    SELECT DISTINCT ON (sender_account_id)
        sender_account_id as inbox_id,
        tagged_at as event_timestamp,
        kill_trigger as trigger
    FROM inbox_removal_events
    WHERE kill_trigger IS NOT NULL
    ORDER BY sender_account_id, tagged_at ASC
),
-- Kill trigger events
trigger_events AS (
    SELECT DISTINCT ON (inbox_id)
        inbox_id,
        detected_at as event_timestamp,
        trigger_type as trigger
    FROM kill_trigger_events
    WHERE trigger_type IS NOT NULL
    ORDER BY inbox_id, detected_at ASC
),
-- Kill queue records
queue_events AS (
    SELECT DISTINCT ON (inbox_id)
        inbox_id,
        COALESCE(tagged_at, queued_at) as event_timestamp,
        trigger_type as trigger
    FROM kill_queue
    WHERE trigger_type IS NOT NULL
    ORDER BY inbox_id, COALESCE(tagged_at, queued_at) ASC
)
SELECT
    sa.id as inbox_id,
    -- Best trigger type (priority: kill_queue > trigger_events > removal > health > spam_event > bounce_event)
    COALESCE(
        q.trigger,
        te.trigger,
        re.trigger,
        he.trigger,
        se.inferred_trigger,
        be.inferred_trigger
    ) as best_trigger,
    -- Best timestamp (use earliest available from actual events)
    LEAST(
        COALESCE(q.event_timestamp, 'infinity'::timestamp),
        COALESCE(te.event_timestamp, 'infinity'::timestamp),
        COALESCE(re.event_timestamp, 'infinity'::timestamp),
        COALESCE(he.event_timestamp, 'infinity'::timestamp),
        COALESCE(se.event_timestamp, 'infinity'::timestamp),
        COALESCE(be.event_timestamp, 'infinity'::timestamp)
    ) as best_timestamp,
    -- Track which source we used
    CASE
        WHEN q.trigger IS NOT NULL THEN 'kill_queue'
        WHEN te.trigger IS NOT NULL THEN 'trigger_events'
        WHEN re.trigger IS NOT NULL THEN 'removal_events'
        WHEN he.trigger IS NOT NULL THEN 'health_events'
        WHEN se.inferred_trigger IS NOT NULL THEN 'campaign_spam'
        WHEN be.inferred_trigger IS NOT NULL THEN 'campaign_bounce'
        ELSE 'no_source'
    END as trigger_source,
    CASE
        WHEN q.event_timestamp IS NOT NULL THEN 'kill_queue'
        WHEN te.event_timestamp IS NOT NULL THEN 'trigger_events'
        WHEN re.event_timestamp IS NOT NULL THEN 'removal_events'
        WHEN he.event_timestamp IS NOT NULL THEN 'health_events'
        WHEN se.event_timestamp IS NOT NULL THEN 'campaign_spam'
        WHEN be.event_timestamp IS NOT NULL THEN 'campaign_bounce'
        ELSE 'no_source'
    END as timestamp_source,
    -- Metrics for fallback inference
    sa.complaints_lifetime,
    sa.bounces_all_time,
    sa.warmup_started_at,
    sa.sending_started_at
FROM sender_accounts sa
LEFT JOIN queue_events q ON q.inbox_id = sa.id
LEFT JOIN trigger_events te ON te.inbox_id = sa.id
LEFT JOIN removal_events re ON re.inbox_id = sa.id
LEFT JOIN health_trigger_events he ON he.inbox_id = sa.id
LEFT JOIN spam_events se ON se.inbox_id = sa.id
LEFT JOIN bounce_events be ON be.inbox_id = sa.id
WHERE sa.inbox_state = 'dead'
  AND (sa.kill_trigger IS NULL OR sa.killed_at IS NULL);

-- Step 3: Report what we found
SELECT
    'DATA SOURCES FOUND' as stage,
    COUNT(*) as total_to_backfill,
    COUNT(*) FILTER (WHERE trigger_source != 'no_source') as has_trigger_source,
    COUNT(*) FILTER (WHERE trigger_source = 'no_source') as no_trigger_source,
    COUNT(*) FILTER (WHERE best_timestamp != 'infinity'::timestamp) as has_timestamp
FROM dead_inbox_events;

SELECT
    trigger_source,
    COUNT(*) as count
FROM dead_inbox_events
GROUP BY trigger_source
ORDER BY count DESC;

SELECT
    timestamp_source,
    COUNT(*) as count
FROM dead_inbox_events
GROUP BY timestamp_source
ORDER BY count DESC;

-- Step 4: Backfill from event data (has actual timestamps)
UPDATE sender_accounts sa
SET
    kill_trigger = COALESCE(sa.kill_trigger, die.best_trigger::kill_trigger_type),
    killed_at = COALESCE(sa.killed_at,
        CASE WHEN die.best_timestamp != 'infinity'::timestamp
             THEN die.best_timestamp
             ELSE NULL
        END
    )
FROM dead_inbox_events die
WHERE sa.id = die.inbox_id
  AND die.best_trigger IS NOT NULL
  AND die.best_timestamp != 'infinity'::timestamp;

-- Step 5: For remaining with trigger but no timestamp, use metrics-based inference
-- Only if we have NO event data at all
UPDATE sender_accounts sa
SET
    kill_trigger = COALESCE(sa.kill_trigger, die.best_trigger::kill_trigger_type),
    killed_at = COALESCE(sa.killed_at,
        -- Use warmup_started_at + reasonable offset if fresh inbox
        CASE
            WHEN die.warmup_started_at IS NOT NULL
                 AND die.best_trigger IN ('fresh_inbox_bounce', 'hard_bounces_24h')
            THEN die.warmup_started_at + INTERVAL '21 days'  -- Avg warmup + early sending
            ELSE sa.updated_at  -- Last resort
        END
    )
FROM dead_inbox_events die
WHERE sa.id = die.inbox_id
  AND die.best_trigger IS NOT NULL
  AND sa.killed_at IS NULL;

-- Step 6: Infer for remaining with no event data
-- These are truly untracked - use metric inference with conservative timestamps
UPDATE sender_accounts
SET
    kill_trigger = 'spam_complaint'::kill_trigger_type,
    killed_at = COALESCE(killed_at,
        CASE WHEN warmup_started_at IS NOT NULL
             THEN warmup_started_at + INTERVAL '30 days'  -- Conservative estimate
             ELSE updated_at
        END
    )
WHERE inbox_state = 'dead'
  AND kill_trigger IS NULL
  AND complaints_lifetime > 0;

UPDATE sender_accounts
SET
    kill_trigger = 'fresh_inbox_bounce'::kill_trigger_type,
    killed_at = COALESCE(killed_at,
        CASE WHEN sending_started_at IS NOT NULL
             THEN sending_started_at + INTERVAL '7 days'  -- Early sending death
             WHEN warmup_started_at IS NOT NULL
             THEN warmup_started_at + INTERVAL '21 days'
             ELSE updated_at
        END
    )
WHERE inbox_state = 'dead'
  AND kill_trigger IS NULL
  AND bounces_all_time > 0
  AND warmup_started_at IS NOT NULL
  AND (
    sending_started_at IS NULL  -- Never made it to sending
    OR updated_at < sending_started_at + INTERVAL '14 days'  -- Died early in sending
  );

UPDATE sender_accounts
SET
    kill_trigger = 'hard_bounces_24h'::kill_trigger_type,
    killed_at = COALESCE(killed_at,
        CASE WHEN sending_started_at IS NOT NULL
             THEN sending_started_at + INTERVAL '30 days'
             ELSE updated_at
        END
    )
WHERE inbox_state = 'dead'
  AND kill_trigger IS NULL
  AND bounces_all_time > 0;

-- Step 7: Mark remaining as unknown
UPDATE sender_accounts
SET
    kill_trigger = 'unknown'::kill_trigger_type,
    killed_at = COALESCE(killed_at, updated_at)
WHERE inbox_state = 'dead'
  AND kill_trigger IS NULL;

-- Cleanup
DROP TABLE dead_inbox_events;

-- Step 8: Report AFTER backfill
SELECT 'AFTER BACKFILL' as stage,
    COUNT(*) FILTER (WHERE inbox_state = 'dead') as total_dead,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND kill_trigger IS NOT NULL) as has_trigger,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND kill_trigger IS NULL) as missing_trigger,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND killed_at IS NOT NULL) as has_killed_at,
    COUNT(*) FILTER (WHERE inbox_state = 'dead' AND killed_at IS NULL) as missing_killed_at
FROM sender_accounts;

-- Step 9: Breakdown by trigger type
SELECT
    kill_trigger::text as trigger_type,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) as pct
FROM sender_accounts
WHERE inbox_state = 'dead'
GROUP BY kill_trigger
ORDER BY count DESC;

-- Step 10: Workspace breakdown
SELECT
    w.workspace_name,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as total_dead,
    COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') as spam_complaint,
    COUNT(*) FILTER (WHERE sa.kill_trigger = 'fresh_inbox_bounce') as fresh_inbox_bounce,
    COUNT(*) FILTER (WHERE sa.kill_trigger = 'hard_bounces_24h') as hard_bounces_24h,
    COUNT(*) FILTER (WHERE sa.kill_trigger = 'unknown') as unknown_trigger
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
JOIN workspaces w ON d.workspace_id = w.id
WHERE sa.inbox_state = 'dead'
GROUP BY w.workspace_name
ORDER BY total_dead DESC;

SELECT 'Migration 081_backfill_kill_triggers_historical complete' AS status;
