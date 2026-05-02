"""
Reports API — fleet-wide CSV-style reports for operator review.

Replaces the daily Slack inbox audit. Each endpoint returns JSON for the
/reports UI tabs. CSV download for the legacy reports (disconnects/kills/
rotation/capacity) reuses the existing /api/health/export/* endpoints.
For the new accuracy-driven reports (cancel-candidates, quarantined,
incubation-stuck) sourced from inbox_audits.audit_data, this module
serves both JSON (default) and CSV (?format=csv).

Conventions:
  - All rows include workspace_name as the first/leftmost column
  - Default sort: workspace_name, then most-recent-event DESC
  - Disconnects use disconnected_at ASC (oldest first = highest priority)
  - All endpoints filter to is_active workspaces and exclude cancelled domains

Plan ref: inbox-audit-overhaul.md (replacing Slack output entirely)
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Response

from database import fetch_all

router = APIRouter()


def _envelope(name: str, rows: list[dict]) -> dict:
    return {
        "report_name": name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": len(rows),
        "rows": rows,
    }


def _csv_response(name: str, columns: list[str], rows: list[dict]) -> Response:
    def esc(v) -> str:
        if v is None:
            return ""
        s = str(v)
        if "," in s or '"' in s or "\n" in s:
            return '"' + s.replace('"', '""') + '"'
        return s

    lines = [",".join(columns)]
    for r in rows:
        lines.append(",".join(esc(r.get(c)) for c in columns))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return Response(
        content="\n".join(lines),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}-{today}.csv"'},
    )


@router.get("/disconnects")
async def report_disconnects(
    attention_only: bool = Query(True, description="Filter to ESP-aware attention thresholds (Microsoft 48h, others 24h)"),
    format: str = Query("json", regex="^(json|csv)$"),
):
    """Live inboxes whose status != Connected, ESP-aware. Sorted by workspace, then disconnected_at ASC (oldest first)."""
    attention_filter = ""
    if attention_only:
        attention_filter = """
        AND (
            (sa.esp = 'microsoft' AND sa.disconnected_at IS NOT NULL AND sa.disconnected_at < NOW() - INTERVAL '48 hours')
            OR (COALESCE(sa.esp, 'other') != 'microsoft' AND sa.disconnected_at IS NOT NULL AND sa.disconnected_at < NOW() - INTERVAL '24 hours')
        )
        """
    rows = await fetch_all(f"""
        SELECT
            w.workspace_name,
            d.domain_name,
            sa.email_address,
            sa.esp,
            sa.status AS connection_status,
            sa.disconnected_at,
            ROUND(EXTRACT(EPOCH FROM (NOW() - sa.disconnected_at)) / 3600, 1) AS hours_disconnected,
            CASE
                WHEN sa.esp = 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '48 hours' THEN TRUE
                WHEN COALESCE(sa.esp, 'other') != 'microsoft' AND sa.disconnected_at < NOW() - INTERVAL '24 hours' THEN TRUE
                ELSE FALSE
            END AS needs_attention,
            sa.inventory_pool_status AS pool_status,
            sa.warmup_enabled,
            sa.daily_limit,
            COALESCE(sa.total_sends_7d, 0) AS total_sends_7d
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.status != 'Connected'
          AND sa.inbox_state = 'live'
          AND sa.emailbison_account_id IS NOT NULL
          AND w.is_active = TRUE
          AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
          {attention_filter}
        ORDER BY w.workspace_name, sa.disconnected_at ASC NULLS LAST
    """)
    if format == "csv":
        return _csv_response("disconnects", [
            "workspace_name", "domain_name", "email_address", "esp", "connection_status",
            "disconnected_at", "hours_disconnected", "needs_attention", "pool_status",
            "warmup_enabled", "daily_limit", "total_sends_7d",
        ], rows)
    return _envelope("disconnects", rows)


@router.get("/kills")
async def report_kills(
    window: str = Query("24h", regex="^(24h|7d|30d)$"),
    format: str = Query("json", regex="^(json|csv)$"),
):
    """Per-inbox kills within window. Sorted by workspace, killed_at DESC."""
    interval = {"24h": "24 hours", "7d": "7 days", "30d": "30 days"}[window]
    rows = await fetch_all(f"""
        SELECT
            w.workspace_name,
            d.domain_name,
            sa.email_address,
            sa.kill_trigger::text AS kill_trigger,
            sa.kill_reason,
            sa.killed_at,
            sa.esp,
            sa.inventory_pool_status AS pool_status_before_kill,
            COALESCE(sa.total_sends_7d, 0) AS total_sends_7d,
            COALESCE(sa.hard_bounces_24h, 0) AS hard_bounces_24h
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.killed_at >= NOW() - INTERVAL '{interval}'
          AND sa.kill_trigger IS NOT NULL
          AND sa.emailbison_account_id IS NOT NULL
          AND w.is_active = TRUE
          AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
        ORDER BY w.workspace_name, sa.killed_at DESC
    """)
    if format == "csv":
        return _csv_response(f"kills-{window}", [
            "workspace_name", "domain_name", "email_address", "kill_trigger",
            "kill_reason", "killed_at", "esp", "pool_status_before_kill",
            "total_sends_7d", "hard_bounces_24h",
        ], rows)
    return _envelope("kills", rows)


@router.get("/rotation")
async def report_rotation(format: str = Query("json", regex="^(json|csv)$")):
    """Domains needing rotation: spam-compromised / provider-blocked / all-dead / high-death-rate."""
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            d.domain_name,
            COUNT(*) AS total_inboxes,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') AS dead_inboxes,
            COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') AS spam_complaints,
            COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') AS provider_blocks,
            ROUND(100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / NULLIF(COUNT(*), 0), 0) AS death_rate_pct,
            CASE
                WHEN COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0 THEN 'spam_compromised'
                WHEN COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') > 0 THEN 'provider_blocked'
                WHEN COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') = COUNT(*) THEN 'all_dead'
                WHEN 100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / NULLIF(COUNT(*), 0) >= 80 THEN 'high_death_rate'
                ELSE 'monitor'
            END AS rotation_reason,
            MAX(sa.killed_at) AS most_recent_kill
        FROM domains d
        JOIN sender_accounts sa ON sa.domain_id = d.id
        JOIN workspaces w ON d.workspace_id = w.id
        WHERE w.is_active = TRUE
          AND d.pool_status != 'cancelled'
        GROUP BY w.workspace_name, d.id, d.domain_name
        HAVING
            COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0
            OR COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') > 0
            OR COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') = COUNT(*)
            OR (COUNT(*) >= 5 AND 100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / COUNT(*) >= 80)
        ORDER BY w.workspace_name, MAX(sa.killed_at) DESC NULLS LAST
    """)
    if format == "csv":
        return _csv_response("rotation", [
            "workspace_name", "domain_name", "total_inboxes", "dead_inboxes",
            "spam_complaints", "provider_blocks", "death_rate_pct",
            "rotation_reason", "most_recent_kill",
        ], rows)
    return _envelope("rotation", rows)


@router.get("/cancel-candidates")
async def report_cancel_candidates(format: str = Query("json", regex="^(json|csv)$")):
    """Subscription-cancel queue, derived from latest inbox_audits I-9 section per workspace.

    Includes the 14-day reuse-window flag (recency_eligible) so the operator
    can split actionable rows from settling-window rows in the UI.
    """
    rows = await fetch_all("""
        WITH latest_audit AS (
            SELECT DISTINCT ON (workspace_id)
                workspace_id, audit_data, audit_date, updated_at
            FROM inbox_audits
            WHERE workspace_id IS NOT NULL
              AND audit_data IS NOT NULL
            ORDER BY workspace_id, audit_date DESC, updated_at DESC
        ),
        i9 AS (
            SELECT
                la.workspace_id,
                la.audit_date,
                jsonb_path_query(la.audit_data->'sections', '$[*] ? (@.code == "I-9")')->'details' AS details
            FROM latest_audit la
        )
        SELECT
            w.workspace_name,
            i9.audit_date,
            (domain->>'domain_name') AS domain_name,
            (domain->>'domain_id') AS domain_id,
            (domain->>'total_inboxes')::int AS total_inboxes,
            (domain->>'dead_inboxes')::int AS dead_inboxes,
            (domain->>'live_connected')::int AS live_connected,
            (domain->>'live_disconnected')::int AS live_disconnected,
            (domain->>'dead_connected')::int AS dead_connected,
            (domain->>'dead_disconnected')::int AS dead_disconnected,
            (domain->>'most_recent_kill')::timestamptz AS most_recent_kill,
            (domain->>'recency_eligible')::boolean AS recency_eligible
        FROM i9
        JOIN workspaces w ON w.id = i9.workspace_id
        CROSS JOIN LATERAL jsonb_array_elements(i9.details->'domains') AS domain
        ORDER BY w.workspace_name, (domain->>'most_recent_kill')::timestamptz ASC NULLS LAST
    """)
    if format == "csv":
        return _csv_response("cancel-candidates", [
            "workspace_name", "domain_name", "domain_id", "total_inboxes",
            "dead_inboxes", "live_connected", "live_disconnected",
            "dead_connected", "dead_disconnected", "most_recent_kill",
            "recency_eligible", "audit_date",
        ], rows)
    return _envelope("cancel_candidates", rows)


@router.get("/quarantined")
async def report_quarantined(format: str = Query("json", regex="^(json|csv)$")):
    """Inboxes quarantined by the cross-workspace integrity firewall (HR-1 lockout)."""
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            d.domain_name,
            sa.email_address,
            sa.is_quarantined,
            sa.quarantine_reason,
            sa.inventory_pool_status,
            sa.inbox_state,
            sa.status AS connection_status,
            sa.created_at,
            sa.updated_at
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.is_quarantined = TRUE
          AND w.is_active = TRUE
        ORDER BY w.workspace_name, sa.updated_at DESC
    """)
    if format == "csv":
        return _csv_response("quarantined", [
            "workspace_name", "domain_name", "email_address", "is_quarantined",
            "quarantine_reason", "inventory_pool_status", "inbox_state",
            "connection_status", "created_at", "updated_at",
        ], rows)
    return _envelope("quarantined", rows)


@router.get("/incubation-stuck")
async def report_incubation_stuck(
    min_calendar_days: int = Query(14, description="Minimum calendar days in incubation to surface"),
    format: str = Query("json", regex="^(json|csv)$"),
):
    """Inboxes stuck in incubation past N calendar days. Source for I-2 review."""
    rows = await fetch_all(f"""
        SELECT
            w.workspace_name,
            d.domain_name,
            sa.email_address,
            sa.inventory_lifecycle_status,
            sa.inventory_pool_status,
            sa.warmup_started_at,
            sa.created_at,
            FLOOR(EXTRACT(EPOCH FROM (NOW() - COALESCE(sa.warmup_started_at, sa.created_at))) / 86400)::int AS calendar_days_in_incubation,
            sa.last_synced_at
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.inventory_lifecycle_status = 'incubating'
          AND sa.is_active = TRUE
          AND w.is_active = TRUE
          AND COALESCE(sa.warmup_started_at, sa.created_at) < NOW() - INTERVAL '{min_calendar_days} days'
        ORDER BY w.workspace_name, COALESCE(sa.warmup_started_at, sa.created_at) ASC
    """)
    if format == "csv":
        return _csv_response("incubation-stuck", [
            "workspace_name", "domain_name", "email_address", "inventory_lifecycle_status",
            "inventory_pool_status", "warmup_started_at", "created_at",
            "calendar_days_in_incubation", "last_synced_at",
        ], rows)
    return _envelope("incubation_stuck", rows)


@router.get("/capacity")
async def report_capacity(format: str = Query("json", regex="^(json|csv)$")):
    """Per-workspace capacity health summary."""
    rows = await fetch_all("""
        SELECT
            w.workspace_name,
            COUNT(*) AS total_inboxes,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') AS live_connected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status IS DISTINCT FROM 'Connected') AS live_disconnected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') AS dead,
            ROUND(100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') / NULLIF(COUNT(*), 0), 0) AS health_pct,
            COUNT(DISTINCT d.id) FILTER (WHERE sa.kill_trigger = 'spam_complaint') AS spam_compromised_domains,
            w.target_live_count_override AS target_live,
            MAX(sa.updated_at) AS most_recent_event
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE sa.emailbison_account_id IS NOT NULL
          AND w.is_active = TRUE
          AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
        GROUP BY w.id, w.workspace_name, w.target_live_count_override
        HAVING COUNT(*) > 0
        ORDER BY w.workspace_name
    """)
    if format == "csv":
        return _csv_response("capacity", [
            "workspace_name", "total_inboxes", "live_connected", "live_disconnected",
            "dead", "health_pct", "spam_compromised_domains", "target_live",
            "most_recent_event",
        ], rows)
    return _envelope("capacity", rows)
