-- Migration: 052_add_connection_status_tracking.sql
-- Purpose: Track inbox connection status (Connected vs Not connected) separately from inbox_state
--
-- Context:
--   - inbox_state = 'live' means the inbox hasn't been killed for bad behavior
--   - inbox_state = 'dead' means the inbox was killed (bounces, spam complaints, etc.)
--   - status = connection status from EmailBison ('Connected', 'Not connected', 'Disconnected', 'Disabled')
--
-- A live inbox can be 'Not connected' (needs reconnection via HyperTide)
-- This migration adds tracking to surface disconnected inboxes in the UI

BEGIN;

-- Drop and recreate the view with connection status counts
DROP VIEW IF EXISTS v_infrastructure_waterfall CASCADE;

CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,
    d.created_at as generated_at,
    d.legitimacy_score,
    COALESCE(d.domain_source, 'legacy') as domain_source,

    -- Pricing
    d.price_checked_at,
    d.cached_price,
    d.selected_provider,
    d.porkbun_price,
    d.porkbun_available,
    d.dynadot_price,
    d.dynadot_available,
    CASE
        WHEN d.price_checked_at IS NULL THEN 'not_checked'
        WHEN d.price_checked_at < NOW() - INTERVAL '24 hours' THEN 'stale'
        WHEN d.porkbun_available = FALSE AND d.dynadot_available = FALSE THEN 'unavailable'
        ELSE 'valid'
    END as price_status,

    -- Purchase
    d.purchased_at,
    d.purchase_job_id,

    -- DNS
    d.nameservers_updated_at,
    d.current_nameservers,
    CASE
        WHEN d.nameservers_updated_at IS NULL THEN 'not_set'
        WHEN d.nameservers_updated_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
        ELSE 'propagated'
    END as dns_migration_status,
    d.nameserver_status,
    d.nameserver_verified_at,
    COALESCE(d.spf_configured, FALSE) as spf_configured,
    COALESCE(d.dkim_configured, FALSE) as dkim_configured,
    COALESCE(d.dmarc_configured, FALSE) as dmarc_configured,
    COALESCE(d.mx_configured, FALSE) as mx_configured,
    COALESCE(d.dns_records_configured, FALSE) as dns_records_configured,

    -- Provider
    COALESCE(d.infrastructure_type, inbox_stats.detected_provider) as assigned_provider,
    inbox_stats.detected_provider,

    -- HyperTide order
    ipj.id as hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.created_at as hypertide_ordered_at,

    -- Inbox counts (based on inbox_state, not killed_at)
    COALESCE(inbox_stats.live_count, 0) as live_inbox_count,
    COALESCE(inbox_stats.dead_count, 0) as dead_inbox_count,
    COALESCE(inbox_stats.total_count, 0) as synced_inbox_count,
    inbox_stats.last_synced_at as last_inbox_synced_at,

    -- NEW: Connection status counts (for live inboxes only)
    COALESCE(inbox_stats.connected_count, 0) as connected_inbox_count,
    COALESCE(inbox_stats.disconnected_count, 0) as disconnected_inbox_count,

    -- Stage tracking
    CASE
        WHEN COALESCE(inbox_stats.total_count, 0) > 0 THEN 9  -- Has inboxes
        WHEN ipj.status = 'completed' THEN 8                   -- HyperTide complete
        WHEN ipj.id IS NOT NULL THEN 7                         -- HyperTide in progress
        WHEN d.infrastructure_type IS NOT NULL THEN 6          -- Provider assigned
        WHEN d.nameserver_status = 'verified' THEN 5           -- DNS verified
        WHEN d.nameservers_updated_at IS NOT NULL THEN 4       -- DNS set
        WHEN d.purchased_at IS NOT NULL THEN 3                 -- Purchased
        WHEN d.price_checked_at IS NOT NULL THEN 2             -- Price checked
        ELSE 1                                                  -- Generated
    END as current_stage,

    -- Flags
    d.approval_status = 'owned' as owned_by_client,
    COALESCE(inbox_stats.total_count, 0) > 0 as deployed_to_production

FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE sa.inbox_state <> 'dead' OR sa.inbox_state IS NULL) as live_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_count,
        COUNT(*) as total_count,
        -- Connection status for LIVE inboxes only
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as connected_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')) as disconnected_count,
        MAX(sa.created_at) as last_synced_at,
        CASE
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
            ELSE NULL
        END as detected_provider
    FROM sender_accounts sa
    WHERE sa.domain_id = d.id
) inbox_stats ON TRUE
WHERE d.is_active = TRUE;

-- Add comment
COMMENT ON VIEW v_infrastructure_waterfall IS
'Infrastructure waterfall view with inbox connection status tracking.
connected_inbox_count = live inboxes with status=Connected
disconnected_inbox_count = live inboxes with status=Not connected/Disconnected';

COMMIT;
