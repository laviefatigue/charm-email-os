# Database Query Cookbook
## Ready-to-Use Queries for Common Analysis Tasks

**Last Updated:** 2026-02-24

---

## Table of Contents

1. [Performance Analysis](#performance-analysis)
2. [Health Monitoring](#health-monitoring)
3. [Campaign Analytics](#campaign-analytics)
4. [Capacity Planning](#capacity-planning)
5. [Infrastructure Comparison](#infrastructure-comparison)
6. [Troubleshooting Queries](#troubleshooting-queries)

---

## Performance Analysis

### 1. True Burn Rate by ESP

**Purpose:** Calculate accurate burn rate (only counts performance kills)

```sql
SELECT
    esp,
    COUNT(*) as total_inboxes,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned_inboxes,
    COUNT(*) FILTER (WHERE kill_trigger IS NULL AND inbox_state = 'dead') as healthy_disconnected,
    COUNT(*) FILTER (WHERE inbox_state = 'live') as active_inboxes,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate_pct
FROM sender_accounts
WHERE workspace_id = '<your_workspace_uuid>'
  AND esp IN ('microsoft', 'gmail')
GROUP BY esp
ORDER BY burn_rate_pct DESC;
```

**Expected Output:**
```
esp       | total | burned | healthy_disconnected | active | burn_rate_pct
----------|-------|--------|----------------------|--------|---------------
microsoft | 5720  | 524    | 4206                 | 990    | 9.16
gmail     | 625   | 209    | 228                  | 188    | 33.44
```

---

### 2. Volume-Adjusted Burn Rate

**Purpose:** Account for sending volume differences between providers

```sql
SELECT
    esp,
    COUNT(*) as total_inboxes,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    SUM(emails_sent_all_time) as total_emails_sent,
    ROUND(AVG(emails_sent_all_time), 0) as avg_emails_per_inbox,
    -- Burns per million emails sent
    ROUND(
        1000000.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) /
        NULLIF(SUM(emails_sent_all_time), 0),
        2
    ) as burns_per_million_emails,
    -- Average emails sent before burn
    ROUND(
        SUM(emails_sent_all_time) /
        NULLIF(COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL), 0),
        0
    ) as avg_emails_before_burn
FROM sender_accounts
WHERE workspace_id = '<your_workspace_uuid>'
  AND esp IN ('microsoft', 'gmail')
GROUP BY esp;
```

---

### 3. Kill Trigger Breakdown

**Purpose:** See what's actually killing inboxes

```sql
SELECT
    esp,
    kill_trigger,
    COUNT(*) as kill_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY esp), 2) as pct_of_esp_kills,
    ROUND(AVG(emails_sent_all_time), 0) as avg_emails_before_kill,
    ROUND(AVG(hard_bounces_24h), 1) as avg_hard_bounces_24h,
    ROUND(AVG(bounce_rate_7d), 4) as avg_bounce_rate_7d
FROM sender_accounts
WHERE kill_trigger IS NOT NULL
  AND workspace_id = '<your_workspace_uuid>'
  AND esp IN ('microsoft', 'gmail')
GROUP BY esp, kill_trigger
ORDER BY esp, kill_count DESC;
```

---

### 4. Burn Rate by Sending Volume Tier

**Purpose:** Identify at what volume inboxes burn

```sql
WITH volume_tiers AS (
    SELECT
        sa.esp,
        sa.kill_trigger IS NOT NULL as burned,
        CASE
            WHEN sa.emails_sent_all_time = 0 THEN '0 - Never sent'
            WHEN sa.emails_sent_all_time BETWEEN 1 AND 100 THEN '1-100 emails'
            WHEN sa.emails_sent_all_time BETWEEN 101 AND 1000 THEN '101-1K emails'
            WHEN sa.emails_sent_all_time > 1000 THEN '1K+ emails'
        END as volume_tier
    FROM sender_accounts sa
    WHERE sa.workspace_id = '<your_workspace_uuid>'
      AND sa.esp IN ('microsoft', 'gmail')
)
SELECT
    esp,
    volume_tier,
    COUNT(*) as inbox_count,
    COUNT(*) FILTER (WHERE burned) as burned_count,
    ROUND(100.0 * COUNT(*) FILTER (WHERE burned) / COUNT(*), 2) as burn_rate_pct
FROM volume_tiers
GROUP BY esp, volume_tier
ORDER BY esp,
    CASE volume_tier
        WHEN '0 - Never sent' THEN 0
        WHEN '1-100 emails' THEN 1
        WHEN '101-1K emails' THEN 2
        WHEN '1K+ emails' THEN 3
    END;
```

---

### 5. Client-Level Comparison (Dual-Provider Only)

**Purpose:** Compare providers within same client (controls for client quality)

```sql
WITH dual_provider_workspaces AS (
    -- Find workspaces with BOTH Microsoft AND Google
    SELECT workspace_id
    FROM sender_accounts
    WHERE esp IN ('microsoft', 'gmail')
    GROUP BY workspace_id
    HAVING COUNT(DISTINCT esp) = 2
)
SELECT
    w.workspace_name as client,
    sa.esp as provider,
    COUNT(DISTINCT sa.domain_id) as domains,
    COUNT(sa.id) as total_inboxes,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) as burned,
    COUNT(*) FILTER (WHERE sa.kill_trigger IS NULL AND sa.inbox_state = 'dead') as healthy_disconnected,
    COUNT(*) FILTER (WHERE sa.inbox_state = 'live') as live,
    ROUND(100.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) / COUNT(sa.id), 2) as burn_rate,
    SUM(sa.emails_sent_all_time) as total_volume,
    ROUND(
        1000000.0 * COUNT(*) FILTER (WHERE sa.kill_trigger IS NOT NULL) /
        NULLIF(SUM(sa.emails_sent_all_time), 0),
        2
    ) as burns_per_million
FROM sender_accounts sa
JOIN dual_provider_workspaces dpw ON sa.workspace_id = dpw.workspace_id
JOIN workspaces w ON sa.workspace_id = w.id
WHERE sa.esp IN ('microsoft', 'gmail')
GROUP BY w.workspace_name, sa.esp
ORDER BY w.workspace_name, sa.esp;
```

---

## Health Monitoring

### 6. Inboxes in Kill Queue

**Purpose:** See what's about to be killed

```sql
SELECT
    kq.status,
    kq.trigger_type,
    sa.email_address,
    sa.esp,
    d.domain_name,
    kq.trigger_value,
    kq.trigger_threshold,
    kq.queued_at,
    kq.tagged_at,
    kq.scheduled_delete_at,
    (kq.scheduled_delete_at - NOW()) as time_until_delete
FROM kill_queue kq
JOIN sender_accounts sa ON kq.inbox_id = sa.id
JOIN domains d ON sa.domain_id = d.id
WHERE kq.workspace_id = '<your_workspace_uuid>'
  AND kq.status IN ('pending', 'tagged')
ORDER BY kq.queued_at DESC;
```

---

### 7. Recent Kills (Last 7 Days)

**Purpose:** Monitor what's been killed recently

```sql
SELECT
    sa.killed_at,
    sa.email_address,
    sa.esp,
    sa.kill_trigger,
    sa.emails_sent_all_time,
    sa.bounce_rate_7d,
    sa.hard_bounces_24h,
    sa.complaints_lifetime,
    d.domain_name,
    d.domain_state,
    EXTRACT(DAY FROM sa.killed_at - sa.created_at) as inbox_age_days
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.workspace_id = '<your_workspace_uuid>'
  AND sa.killed_at >= NOW() - INTERVAL '7 days'
ORDER BY sa.killed_at DESC;
```

---

### 8. Domain Health Summary

**Purpose:** See which domains are struggling

```sql
SELECT
    d.domain_name,
    d.domain_state,
    d.live_inbox_count,
    d.dead_inbox_count,
    ROUND(100.0 * d.dead_inbox_count / NULLIF(d.live_inbox_count + d.dead_inbox_count, 0), 1) as dead_pct,
    ROUND(d.domain_bounce_rate_7d, 4) as bounce_rate_7d,
    d.domain_sends_7d,
    d.inboxes_with_complaints,
    d.inboxes_with_blocks,
    d.burn_breakdown::jsonb as kills_by_type,
    EXTRACT(DAY FROM NOW() - d.registration_date) as domain_age_days
FROM domains d
WHERE d.workspace_id = '<your_workspace_uuid>'
  AND (d.live_inbox_count + d.dead_inbox_count) > 0
ORDER BY d.domain_bounce_rate_7d DESC NULLS LAST
LIMIT 20;
```

---

### 9. High-Risk Inboxes (Approaching Thresholds)

**Purpose:** Identify inboxes that might trigger soon

```sql
SELECT
    sa.email_address,
    sa.esp,
    d.domain_name,
    sa.hard_bounces_24h,
    sa.hard_blocked_24h,
    sa.hard_unknown_24h,
    sa.bounce_rate_7d,
    sa.complaints_lifetime,
    sa.emails_sent_all_time,
    EXTRACT(DAY FROM NOW() - sa.created_at) as age_days,
    CASE
        WHEN sa.hard_blocked_24h >= 1 THEN 'Will trigger: hard_blocked_24h'
        WHEN sa.hard_unknown_24h >= 2 THEN 'Close to: hard_unknown_24h (threshold: 3)'
        WHEN sa.hard_bounces_24h >= 1 THEN 'Close to: hard_bounces_24h (threshold: 2)'
        WHEN sa.bounce_rate_7d > 0.003 THEN 'Close to: bounce_rate_7d (threshold: 0.005)'
    END as risk_reason
FROM sender_accounts sa
JOIN domains d ON sa.domain_id = d.id
WHERE sa.workspace_id = '<your_workspace_uuid>'
  AND sa.inbox_state = 'live'
  AND (
      sa.hard_blocked_24h >= 1
      OR sa.hard_unknown_24h >= 2
      OR sa.hard_bounces_24h >= 1
      OR sa.bounce_rate_7d > 0.003
  )
ORDER BY
    CASE
        WHEN sa.hard_blocked_24h >= 1 THEN 1
        WHEN sa.hard_unknown_24h >= 2 THEN 2
        WHEN sa.hard_bounces_24h >= 1 THEN 3
        ELSE 4
    END,
    sa.bounce_rate_7d DESC;
```

---

## Campaign Analytics

### 10. Campaign Performance Overview

**Purpose:** See all active campaigns and their metrics

```sql
SELECT
    c.campaign_name,
    c.campaign_status,
    c.emails_sent,
    c.total_leads_contacted,
    c.unique_opens,
    c.unique_replies,
    c.bounced,
    c.spam_complaints,
    ROUND(100.0 * c.unique_opens / NULLIF(c.emails_sent, 0), 2) as open_rate_pct,
    ROUND(100.0 * c.unique_replies / NULLIF(c.emails_sent, 0), 2) as reply_rate_pct,
    ROUND(100.0 * c.bounced / NULLIF(c.emails_sent, 0), 2) as bounce_rate_pct,
    COUNT(DISTINCT ci.sender_account_id) as inboxes_assigned,
    COUNT(DISTINCT ci.sender_account_id) FILTER (WHERE sa.inbox_state = 'live') as inboxes_live,
    COUNT(DISTINCT ci.sender_account_id) FILTER (WHERE sa.kill_trigger IS NOT NULL) as inboxes_burned_in_campaign
FROM emailbison_campaigns c
LEFT JOIN campaign_inboxes ci ON ci.campaign_id = c.id
LEFT JOIN sender_accounts sa ON sa.id = ci.sender_account_id
WHERE c.workspace_id = '<your_workspace_uuid>'
  AND c.is_active = TRUE
GROUP BY c.id, c.campaign_name, c.campaign_status, c.emails_sent, c.total_leads_contacted,
         c.unique_opens, c.unique_replies, c.bounced, c.spam_complaints
ORDER BY c.last_seen_at DESC;
```

---

### 11. Campaign Impact on Infrastructure

**Purpose:** See which campaigns are burning inboxes

```sql
WITH campaign_burns AS (
    SELECT
        c.campaign_name,
        COUNT(DISTINCT ci.sender_account_id) as total_inboxes_used,
        COUNT(DISTINCT ci.sender_account_id) FILTER (WHERE sa.kill_trigger IS NOT NULL) as inboxes_burned,
        ROUND(100.0 * COUNT(DISTINCT ci.sender_account_id) FILTER (WHERE sa.kill_trigger IS NOT NULL) /
              NULLIF(COUNT(DISTINCT ci.sender_account_id), 0), 2) as campaign_burn_rate,
        STRING_AGG(DISTINCT sa.kill_trigger::text, ', ' ORDER BY sa.kill_trigger::text) as kill_triggers_seen,
        c.bounced as campaign_bounces,
        c.spam_complaints as campaign_complaints,
        c.emails_sent
    FROM emailbison_campaigns c
    LEFT JOIN campaign_inboxes ci ON ci.campaign_id = c.id
    LEFT JOIN sender_accounts sa ON sa.id = ci.sender_account_id
    WHERE c.workspace_id = '<your_workspace_uuid>'
      AND c.is_active = TRUE
    GROUP BY c.id, c.campaign_name, c.bounced, c.spam_complaints, c.emails_sent
)
SELECT *
FROM campaign_burns
WHERE inboxes_burned > 0
ORDER BY campaign_burn_rate DESC, inboxes_burned DESC;
```

---

## Capacity Planning

### 12. Current Capacity Summary

**Purpose:** See total available sending capacity

```sql
SELECT
    COUNT(*) FILTER (WHERE inbox_state = 'live') as live_inboxes,
    COUNT(*) FILTER (WHERE inbox_state = 'live' AND inventory_lifecycle_status = 'incubating') as incubating_inboxes,
    SUM(daily_limit) FILTER (WHERE inbox_state = 'live') as total_daily_capacity,
    SUM(daily_limit) FILTER (WHERE inbox_state = 'live' AND inventory_lifecycle_status = 'active') as active_capacity,
    SUM(daily_limit) FILTER (WHERE inbox_state = 'live' AND inventory_lifecycle_status = 'incubating') as incubating_capacity,
    ROUND(AVG(daily_limit) FILTER (WHERE inbox_state = 'live'), 1) as avg_daily_limit_per_inbox,
    -- Breakdown by ESP
    SUM(daily_limit) FILTER (WHERE inbox_state = 'live' AND esp = 'microsoft') as microsoft_capacity,
    SUM(daily_limit) FILTER (WHERE inbox_state = 'live' AND esp = 'gmail') as google_capacity
FROM sender_accounts
WHERE workspace_id = '<your_workspace_uuid>';
```

---

### 13. Daily Volume Trends (Last 90 Days)

**Purpose:** Capacity and utilization over time

```sql
SELECT
    snapshot_date,
    emails_sent,
    daily_capacity_available,
    ROUND(capacity_utilization_pct, 1) as capacity_used_pct,
    live_inboxes,
    incubating_inboxes,
    dead_inboxes,
    kills_that_day,
    CASE
        WHEN capacity_utilization_pct > 90 THEN '🔴 Critical'
        WHEN capacity_utilization_pct > 75 THEN '🟡 High'
        WHEN capacity_utilization_pct > 50 THEN '🟢 Moderate'
        ELSE '⚪ Low'
    END as utilization_status
FROM daily_volume_snapshots
WHERE workspace_id = '<your_workspace_uuid>'
  AND snapshot_date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY snapshot_date DESC;
```

---

### 14. Warmup Pipeline Status

**Purpose:** See what capacity is coming online

```sql
SELECT
    sa.esp,
    COUNT(*) as warming_inboxes,
    ROUND(AVG(EXTRACT(DAY FROM NOW() - sa.warmup_started_at)), 1) as avg_days_warming,
    ROUND(AVG(14 - EXTRACT(DAY FROM NOW() - sa.warmup_started_at)), 1) as avg_days_remaining,
    SUM(sa.daily_limit) as capacity_when_ready,
    MIN(sa.warmup_started_at) as oldest_warmup,
    MAX(sa.warmup_started_at) as newest_warmup
FROM sender_accounts sa
WHERE sa.workspace_id = '<your_workspace_uuid>'
  AND sa.warmup_enabled = TRUE
  AND sa.inbox_state = 'live'
  AND sa.inventory_lifecycle_status = 'incubating'
GROUP BY sa.esp;
```

---

## Infrastructure Comparison

### 15. Side-by-Side ESP Performance

**Purpose:** Compare all metrics between Microsoft and Google

```sql
WITH esp_metrics AS (
    SELECT
        esp,
        COUNT(*) as total_inboxes,
        COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
        COUNT(*) FILTER (WHERE inbox_state = 'live') as live,
        SUM(emails_sent_all_time) as total_volume,
        SUM(daily_limit) FILTER (WHERE inbox_state = 'live') as daily_capacity,
        ROUND(AVG(emails_sent_all_time), 0) as avg_emails_per_inbox,
        ROUND(AVG(daily_limit), 1) as avg_daily_limit,
        ROUND(AVG(bounce_rate_7d) FILTER (WHERE inbox_state = 'live'), 4) as avg_bounce_rate,
        ROUND(AVG(hard_bounces_7d) FILTER (WHERE inbox_state = 'live'), 1) as avg_hard_bounces_7d
    FROM sender_accounts
    WHERE workspace_id = '<your_workspace_uuid>'
      AND esp IN ('microsoft', 'gmail')
    GROUP BY esp
)
SELECT
    'Total Inboxes' as metric,
    MAX(total_inboxes) FILTER (WHERE esp = 'microsoft') as microsoft,
    MAX(total_inboxes) FILTER (WHERE esp = 'gmail') as google
FROM esp_metrics
UNION ALL
SELECT
    'Burned',
    MAX(burned) FILTER (WHERE esp = 'microsoft'),
    MAX(burned) FILTER (WHERE esp = 'gmail')
FROM esp_metrics
UNION ALL
SELECT
    'Burn Rate %',
    ROUND(MAX(burned * 100.0 / total_inboxes) FILTER (WHERE esp = 'microsoft'), 2),
    ROUND(MAX(burned * 100.0 / total_inboxes) FILTER (WHERE esp = 'gmail'), 2)
FROM esp_metrics
UNION ALL
SELECT
    'Live Inboxes',
    MAX(live) FILTER (WHERE esp = 'microsoft'),
    MAX(live) FILTER (WHERE esp = 'gmail')
FROM esp_metrics
UNION ALL
SELECT
    'Total Volume',
    MAX(total_volume) FILTER (WHERE esp = 'microsoft'),
    MAX(total_volume) FILTER (WHERE esp = 'gmail')
FROM esp_metrics
UNION ALL
SELECT
    'Daily Capacity',
    MAX(daily_capacity) FILTER (WHERE esp = 'microsoft'),
    MAX(daily_capacity) FILTER (WHERE esp = 'gmail')
FROM esp_metrics
UNION ALL
SELECT
    'Avg Emails/Inbox',
    MAX(avg_emails_per_inbox) FILTER (WHERE esp = 'microsoft'),
    MAX(avg_emails_per_inbox) FILTER (WHERE esp = 'gmail')
FROM esp_metrics
UNION ALL
SELECT
    'Avg Daily Limit',
    MAX(avg_daily_limit) FILTER (WHERE esp = 'microsoft'),
    MAX(avg_daily_limit) FILTER (WHERE esp = 'gmail')
FROM esp_metrics;
```

---

## Troubleshooting Queries

### 16. Check Sync Status

**Purpose:** See if data is fresh

```sql
SELECT
    module,
    last_run_at,
    NOW() - last_run_at as time_since_sync,
    records_processed,
    records_created,
    records_updated,
    records_failed,
    success,
    error_message
FROM sync_status
ORDER BY last_run_at DESC;
```

---

### 17. Find Duplicate Inboxes

**Purpose:** Detect sync issues

```sql
SELECT
    email_address,
    COUNT(*) as duplicate_count,
    STRING_AGG(workspace_id::text, ', ') as workspace_ids
FROM sender_accounts
GROUP BY email_address
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
```

---

### 18. Bounce Counter Reset Verification

**Purpose:** Confirm daily cleanup is working

```sql
-- Check if any inboxes have stale 24h counters
SELECT
    COUNT(*) as inboxes_with_nonzero_24h_counters,
    MAX(hard_bounces_24h) as max_hard_bounces_24h,
    MAX(hard_blocked_24h) as max_hard_blocked_24h,
    MAX(hard_unknown_24h) as max_hard_unknown_24h
FROM sender_accounts
WHERE hard_bounces_24h > 0
   OR hard_blocked_24h > 0
   OR hard_unknown_24h > 0;

-- If counts are high, check last daily cleanup
SELECT * FROM sync_status WHERE module = 'daily_cleanup';
```

---

### 19. Orphaned Records

**Purpose:** Find data integrity issues

```sql
-- Sender accounts without domains
SELECT sa.id, sa.email_address, sa.domain_id
FROM sender_accounts sa
LEFT JOIN domains d ON sa.domain_id = d.id
WHERE sa.domain_id IS NOT NULL AND d.id IS NULL
LIMIT 10;

-- Domains without workspaces
SELECT d.id, d.domain_name, d.workspace_id
FROM domains d
LEFT JOIN workspaces w ON d.workspace_id = w.id
WHERE d.workspace_id IS NOT NULL AND w.id IS NULL
LIMIT 10;
```

---

### 20. Performance Query - Slow Queries

**Purpose:** Find expensive queries

```sql
SELECT
    query,
    calls,
    total_time,
    mean_time,
    max_time
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat%'
ORDER BY mean_time DESC
LIMIT 10;
```

---

## Tips for Using These Queries

### 1. Replace `<your_workspace_uuid>` with actual UUID

```sql
-- Get your workspace ID
SELECT id, workspace_name FROM workspaces;

-- Then use it in queries
WHERE workspace_id = 'b9abd34a-f16a-4b92-bda0-5af10f8c44bd'
```

### 2. Create Views for Frequently Used Queries

```sql
CREATE VIEW v_burn_rate_summary AS
SELECT
    esp,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) as burned,
    ROUND(100.0 * COUNT(*) FILTER (WHERE kill_trigger IS NOT NULL) / COUNT(*), 2) as burn_rate_pct
FROM sender_accounts
WHERE esp IN ('microsoft', 'gmail')
GROUP BY esp;

-- Then just query:
SELECT * FROM v_burn_rate_summary;
```

### 3. Use CTE for Complex Queries

```sql
-- Break complex queries into readable chunks
WITH step1 AS (
    SELECT ...
),
step2 AS (
    SELECT ... FROM step1 ...
)
SELECT * FROM step2;
```

### 4. Add LIMIT for Exploration

```sql
-- When testing queries, add LIMIT to avoid huge results
SELECT * FROM sender_accounts
WHERE workspace_id = '...'
LIMIT 10;  -- Remove after testing
```

---

**Last Updated:** 2026-02-24
**More Resources:**
- [Database Guide](./DATABASE-GUIDE.md) - Full documentation
- [Data Dictionary](./DATA-DICTIONARY.md) - Field definitions
- [Kill Triggers](./kill-triggers.md) - Trigger reference
