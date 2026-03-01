-- Add domain purchase job_id to waterfall view
-- This allows frontend to show "Purchasing..." state for domain purchases

-- Must drop and recreate to add new columns
DROP VIEW IF EXISTS v_infrastructure_waterfall;

CREATE VIEW v_infrastructure_waterfall AS
SELECT
    d.id AS domain_id,
    d.workspace_id,
    d.domain_name,
    d.approval_status,
    d.created_at AS generated_at,
    d.legitimacy_score,
    COALESCE(d.domain_source, 'legacy') AS domain_source,
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
        WHEN d.porkbun_available = false AND d.dynadot_available = false THEN 'unavailable'
        ELSE 'valid'
    END AS price_status,
    d.purchased_at,
    d.job_id AS domain_purchase_job_id,  -- Domain purchase job (domain_purchase_jobs table)
    d.purchase_job_id,                    -- Inbox purchase job (inbox_purchase_jobs table)
    d.nameservers_updated_at,
    d.current_nameservers,
    CASE
        WHEN d.nameservers_updated_at IS NULL THEN 'not_set'
        WHEN d.nameservers_updated_at > NOW() - INTERVAL '24 hours' THEN 'propagating'
        ELSE 'propagated'
    END AS dns_migration_status,
    d.nameserver_status,
    d.nameserver_verified_at,
    COALESCE(d.spf_configured, false) AS spf_configured,
    COALESCE(d.dkim_configured, false) AS dkim_configured,
    COALESCE(d.dmarc_configured, false) AS dmarc_configured,
    COALESCE(d.mx_configured, false) AS mx_configured,
    COALESCE(d.dns_records_configured, false) AS dns_records_configured,
    COALESCE(d.infrastructure_type, inbox_stats.detected_provider::varchar) AS assigned_provider,
    inbox_stats.detected_provider,
    ipj.id AS hypertide_order_job_id,
    ipj.status AS hypertide_order_status,
    ipj.current_step AS hypertide_current_step,
    ipj.created_at AS hypertide_ordered_at,
    COALESCE(inbox_stats.live_count, 0) AS live_inbox_count,
    COALESCE(inbox_stats.dead_count, 0) AS dead_inbox_count,
    COALESCE(inbox_stats.total_count, 0) AS synced_inbox_count,
    inbox_stats.last_synced_at AS last_inbox_synced_at,
    COALESCE(inbox_stats.connected_count, 0) AS connected_inbox_count,
    COALESCE(inbox_stats.disconnected_count, 0) AS disconnected_inbox_count,
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
    END AS current_stage,
    d.approval_status = 'owned' AS owned_by_client,
    COALESCE(inbox_stats.total_count, 0) > 0 AS deployed_to_production
FROM domains d
LEFT JOIN inbox_purchase_jobs ipj ON ipj.id = d.purchase_job_id
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) FILTER (WHERE sa.inbox_state <> 'dead' OR sa.inbox_state IS NULL) AS live_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') AS dead_count,
        COUNT(*) AS total_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS connected_count,
        COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IN ('Not connected', 'Disconnected')) AS disconnected_count,
        MAX(sa.created_at) AS last_synced_at,
        CASE
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'microsoft') > 0 THEN 'entra'
            WHEN COUNT(*) FILTER (WHERE sa.esp = 'gmail') > 0 THEN 'google'
            ELSE NULL
        END AS detected_provider
    FROM sender_accounts sa
    WHERE sa.domain_id = d.id
) inbox_stats ON true
WHERE d.is_active = true;

COMMENT ON VIEW v_infrastructure_waterfall IS 'Infrastructure waterfall view with domain and inbox purchase job tracking';
