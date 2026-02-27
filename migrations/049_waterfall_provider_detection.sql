-- ============================================
-- Migration 049: Add provider detection from inbox ESP + Fix DNS for legacy
-- ============================================
-- 1. Add detected_provider to waterfall view (from sender_accounts.esp)
-- 2. Fix DNS records = true for legacy domains with live inboxes

BEGIN;

-- First, update DNS records for legacy domains with live inboxes
-- If they have working inboxes, DNS must be configured
UPDATE domains d
SET
    spf_configured = TRUE,
    dkim_configured = TRUE,
    dmarc_configured = TRUE,
    mx_configured = TRUE,
    updated_at = NOW()
WHERE d.domain_source = 'legacy'
  AND EXISTS (
    SELECT 1 FROM sender_accounts sa
    WHERE sa.domain_id = d.id
    AND (sa.inbox_state != 'dead' OR sa.inbox_state IS NULL)
  );

-- Drop and recreate view with detected_provider
DROP VIEW IF EXISTS v_infrastructure_waterfall;

CREATE VIEW v_infrastructure_waterfall AS
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

    -- Provider (from infrastructure_type OR detected from inbox ESP)
    COALESCE(d.infrastructure_type, inbox_stats.detected_provider) as assigned_provider,
    inbox_stats.detected_provider as detected_provider,

    -- HyperTide
    ipj.id as hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.created_at as hypertide_ordered_at,

    -- Inbox counts
    COALESCE(inbox_stats.live_count, 0) as live_inbox_count,
    COALESCE(inbox_stats.dead_count, 0) as dead_inbox_count,
    COALESCE(inbox_stats.total_count, 0) as synced_inbox_count,
    inbox_stats.last_synced_at as last_inbox_synced_at,

    -- Computed stage
    CASE
        WHEN COALESCE(inbox_stats.total_count, 0) > 0 THEN 9
        WHEN ipj.status = 'completed' THEN 8
        WHEN ipj.id IS NOT NULL THEN 7
        WHEN d.infrastructure_type IS NOT NULL THEN 6
        WHEN d.nameserver_status = 'verified' THEN 5
        WHEN d.nameservers_updated_at IS NOT NULL THEN 4
        WHEN d.purchased_at IS NOT NULL THEN 3
        WHEN d.price_checked_at IS NOT NULL THEN 2
        ELSE 1
    END as current_stage,

    -- Ownership flags
    (d.approval_status = 'owned') as owned_by_client,
    COALESCE(inbox_stats.total_count, 0) > 0 as deployed_to_production

FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE sa.inbox_state != 'dead' OR sa.inbox_state IS NULL) as live_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_count,
        COUNT(*) as total_count,
        MAX(sa.created_at) as last_synced_at,
        -- Detect provider from ESP: microsoft = entra, gmail = google
        CASE
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
            ELSE NULL
        END as detected_provider
    FROM sender_accounts sa
    WHERE sa.domain_id = d.id
) inbox_stats ON TRUE
WHERE d.is_active = TRUE;

COMMENT ON VIEW v_infrastructure_waterfall IS
  'Waterfall view for infrastructure provisioning. Auto-detects provider from inbox ESP (microsoft=entra, gmail=google).';

COMMIT;

SELECT 'Migration 049: Provider detection + DNS fix complete' AS status;
