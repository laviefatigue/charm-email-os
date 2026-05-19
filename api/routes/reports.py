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
    window: str = Query("all", regex="^(all|24h|7d|30d)$"),
    format: str = Query("json", regex="^(json|csv)$"),
):
    """Per-inbox kills. Default cumulative ('all'); window slices supported.
    Sorted by workspace, killed_at DESC.
    """
    if window == "all":
        time_filter = ""
    else:
        interval = {"24h": "24 hours", "7d": "7 days", "30d": "30 days"}[window]
        time_filter = f"AND sa.killed_at >= NOW() - INTERVAL '{interval}'"
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
        WHERE sa.kill_trigger IS NOT NULL
          AND sa.emailbison_account_id IS NOT NULL
          AND w.is_active = TRUE
          AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
          {time_filter}
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


@router.get("/burn-velocity")
async def report_burn_velocity(
    weeks: int = Query(8, ge=1, le=52),
    format: str = Query("json", regex="^(json|csv)$"),
):
    """Weekly domain-burn counts — operator health signal.

    Surfaces "how many domains are we burning per week" as a tracked
    metric. Operator's stated healthy band is ≤5/week; sustained higher
    counts mean reputation/list-quality work upstream.

    Splits by ESP because Google (3 inboxes/dom) and Microsoft (52/dom)
    have structurally different burn semantics — see
    docs/concepts/esp-aware-data-interpretation.md.
    """
    rows = await fetch_all(
        """
        SELECT
            week_start::date AS week_start,
            esp,
            COUNT(*) AS domains_burned
        FROM (
            SELECT
                date_trunc('week', d.burned_at) AS week_start,
                COALESCE(
                    (SELECT sa.esp::text FROM sender_accounts sa
                     WHERE sa.domain_id = d.id LIMIT 1),
                    'unknown'
                ) AS esp,
                d.id
            FROM domains d
            WHERE d.burned_at IS NOT NULL
              AND d.burned_at > NOW() - ($1::int || ' weeks')::interval
        ) per_domain
        GROUP BY week_start, esp
        ORDER BY week_start DESC, esp
        """,
        weeks,
    )
    if format == "csv":
        return _csv_response("burn-velocity", [
            "week_start", "esp", "domains_burned",
        ], rows)
    return _envelope("burn-velocity", rows)


@router.get("/burned-domain-attachments")
async def report_burned_domain_attachments(
    format: str = Query("json", regex="^(json|csv)$"),
):
    """Active campaigns with senders attached on burned domains.

    The operational drift the EOD reapply daemon's 50%-removal guard
    surfaces but refuses to act on. Per-campaign view:
      - How many of the campaign's attached senders are on burned domains?
      - What pct of attached?
      - Is it over the EOD guard's threshold (would be SKIPPED)?

    These senders don't carry the `live` tag, so EB doesn't actually
    send from them — the attachment is cosmetic, not sending. But it
    keeps EOD's guard tripped on those campaigns. Operator decides:
    retire the campaign, do a one-shot detach, or let attrition handle.
    """
    rows = await fetch_all(
        """
        SELECT
            w.workspace_name,
            ec.emailbison_campaign_id AS campaign_id,
            ec.campaign_name,
            COUNT(DISTINCT ci.sender_account_id) AS attached_total,
            COUNT(DISTINCT ci.sender_account_id)
                FILTER (WHERE d.pool_status = 'burned') AS attached_on_burned,
            ROUND(
                100.0 * COUNT(DISTINCT ci.sender_account_id)
                              FILTER (WHERE d.pool_status = 'burned')
                / NULLIF(COUNT(DISTINCT ci.sender_account_id), 0),
                1
            ) AS burned_pct,
            (
                COUNT(DISTINCT ci.sender_account_id)
                    FILTER (WHERE d.pool_status = 'burned') * 100.0
                / NULLIF(COUNT(DISTINCT ci.sender_account_id), 0)
            ) > 50 AS over_eod_guard,
            COUNT(DISTINCT d.id)
                FILTER (WHERE d.pool_status = 'burned') AS burned_domains_in_campaign
        FROM emailbison_campaigns ec
        JOIN workspaces w ON w.id = ec.workspace_id
        JOIN campaign_inboxes ci ON ci.campaign_id = ec.id
            AND ci.is_active = TRUE
            AND ci.removed_at IS NULL
        JOIN sender_accounts sa ON sa.id = ci.sender_account_id
        LEFT JOIN domains d ON d.id = sa.domain_id
        WHERE w.is_active = TRUE
          AND ec.is_active = TRUE
          AND LOWER(COALESCE(ec.campaign_status, '')) IN ('active', 'queued', 'sending')
        GROUP BY w.workspace_name, ec.emailbison_campaign_id, ec.campaign_name
        HAVING COUNT(DISTINCT ci.sender_account_id)
                   FILTER (WHERE d.pool_status = 'burned') > 0
        ORDER BY burned_pct DESC, w.workspace_name
        """
    )
    if format == "csv":
        return _csv_response("burned-domain-attachments", [
            "workspace_name", "campaign_id", "campaign_name",
            "attached_total", "attached_on_burned", "burned_pct",
            "over_eod_guard", "burned_domains_in_campaign",
        ], rows)
    return _envelope("burned-domain-attachments", rows)


@router.get("/hypertide-drift")
async def report_hypertide_drift(
    format: str = Query("json", regex="^(json|csv)$"),
):
    """Hypertide ↔ EmailBison drift visibility.

    Surfaces three kinds of state mismatch the hypertide-worker's daily
    audit detects but doesn't act on (Phase 1 is read-only):

      1. `ht_cancelled_eb_active` — HT subscription cancelled or flagged
         to_be_cancelled, but the domain's inboxes are still active and
         Connected in EB. When HT cancellation completes, DNS/auth dies
         → sends will start failing. Operator needs to coordinate.
      2. `ht_npc_eb_live` — HT subscription in NPC (non-payment /
         cancellation pending), but the domain is still in `pool='live'`
         actively sending. Reputation risk if HT auto-cancels mid-cycle.
      3. `db_only_unlinked` — domain in our DB but no HT record after
         the most recent audit. Either friends-and-family or genuinely
         out-of-band; flagged `is_legacy=TRUE` post-audit.

    All three are derivable from current `domains` columns; this endpoint
    is a live SQL view (no dependency on the audit-log table). The
    `hypertide_last_synced_at` column shows when the audit last
    confirmed the underlying HT state — values older than 48h mean
    the worker is unhealthy and the findings could be stale.
    """
    rows = await fetch_all(
        """
        WITH base AS (
            SELECT
                w.workspace_name,
                d.domain_name,
                d.pool_status,
                d.hypertide_status::text AS ht_status,
                d.hypertide_to_be_cancelled AS ht_to_be_cancelled,
                d.is_legacy,
                d.hypertide_last_synced_at,
                (SELECT COUNT(*) FROM sender_accounts sa
                 WHERE sa.domain_id = d.id AND sa.is_active = TRUE) AS inboxes_total,
                (SELECT COUNT(*) FROM sender_accounts sa
                 WHERE sa.domain_id = d.id AND sa.is_active = TRUE
                   AND sa.status = 'Connected') AS inboxes_connected
            FROM domains d
            LEFT JOIN workspaces w ON w.id = d.workspace_id
            WHERE w.is_active = TRUE
              AND EXISTS (
                  SELECT 1 FROM client_hypertide_subscriptions chs
                  WHERE chs.client_id = w.client_id
              )
              AND d.pool_status IS DISTINCT FROM 'cancelled'
        )
        SELECT
            CASE
                WHEN (ht_status = 'cancelled' OR ht_to_be_cancelled = TRUE)
                     AND inboxes_connected > 0 THEN 'ht_cancelled_eb_active'
                WHEN ht_status = 'NPC' AND pool_status = 'live'
                     THEN 'ht_npc_eb_live'
                WHEN is_legacy = TRUE THEN 'db_only_unlinked'
            END AS drift_type,
            workspace_name,
            domain_name,
            pool_status,
            ht_status,
            ht_to_be_cancelled,
            is_legacy,
            inboxes_total,
            inboxes_connected,
            hypertide_last_synced_at
        FROM base
        WHERE
            ((ht_status = 'cancelled' OR ht_to_be_cancelled = TRUE)
             AND inboxes_connected > 0)
            OR (ht_status = 'NPC' AND pool_status = 'live')
            OR is_legacy = TRUE
        ORDER BY drift_type, workspace_name, domain_name
        """
    )
    if format == "csv":
        return _csv_response("hypertide-drift", [
            "drift_type", "workspace_name", "domain_name", "pool_status",
            "ht_status", "ht_to_be_cancelled", "is_legacy",
            "inboxes_total", "inboxes_connected", "hypertide_last_synced_at",
        ], rows)
    return _envelope("hypertide-drift", rows)
