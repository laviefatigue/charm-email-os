-- ============================================
-- WATERFALL VIEW V2 - Add live/dead inbox counts
-- ============================================
-- Updates v_infrastructure_waterfall to support new 6-column frontend layout

BEGIN;

-- Recreate the view with additional columns
CREATE OR REPLACE VIEW v_infrastructure_waterfall AS
SELECT
    d.id as domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,
    d.created_at as generated_at,
    d.legitimacy_score,

    -- Pricing (Column 2)
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

    -- DNS (Column 3)
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

    -- Provider (Column 4)
    d.infrastructure_type as assigned_provider,

    -- HyperTide (Column 5)
    ipj.id as hypertide_order_job_id,
    ipj.status as hypertide_order_status,
    ipj.current_step as hypertide_current_step,
    ipj.created_at as hypertide_ordered_at,

    -- Status (Column 6) - NEW: Live/Dead inbox counts
    COALESCE(inbox_stats.live_count, 0) as live_inbox_count,
    COALESCE(inbox_stats.dead_count, 0) as dead_inbox_count,
    COALESCE(inbox_stats.total_count, 0) as synced_inbox_count,
    inbox_stats.last_synced_at as last_inbox_synced_at,

    -- Computed current stage (1-9)
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
        MAX(sa.created_at) as last_synced_at
    FROM sender_accounts sa
    WHERE sa.domain_id = d.id
) inbox_stats ON TRUE
WHERE d.is_active = TRUE;

-- Add comment explaining the view
COMMENT ON VIEW v_infrastructure_waterfall IS
  'Waterfall view for infrastructure provisioning SPA. Columns: Domain, Pricing, DNS, Provider, HyperTide, Status';

COMMIT;

-- ============================================
-- CHANGES IN THIS MIGRATION
-- ============================================
-- - Added live_inbox_count: Count of inboxes where inbox_state != 'dead'
-- - Added dead_inbox_count: Count of inboxes where inbox_state = 'dead'
-- - Uses LATERAL join for efficient per-domain inbox aggregation
-- - Maintains backward compatibility (synced_inbox_count still exists)
