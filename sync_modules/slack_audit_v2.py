"""
slack_audit_v2.py — Daily redesigned inbox-audit Slack message.

Posts ONE message per day at 7 AM Pacific to #inbox-audit. Replaces
slack_audit.py's twice-daily fleet-aggregate flow.

Differences vs the legacy module:
  - Single daily post (vs 6 AM + 1 PM Pacific twice-daily)
  - Per-workspace summary block, sorted alphabetically (vs fleet-aggregate counts)
  - Cumulative metrics (vs last-24h windows)
  - 7 buttons linking to /reports/* operator pages (vs 4 CSV buttons)
  - No 24h/3d/7d notification buckets (per operator direction 2026-05-02)
  - No "Reviewed / Issues Found" buttons (legacy workflow was abandoned —
    72 audits all status='pending', zero ever clicked)

Reads cumulative metrics directly from sender_accounts + the
inbox_audits.audit_data JSONB (Phase 4 cancel-candidate rollup).

Configuration:
  SLACK_AUDIT_WEBHOOK_URL — webhook for #inbox-audit channel (required)
  PUBLIC_REPORTS_URL      — public origin of the reports UI
                            (e.g. https://app.wizardgrimoire.cloud)
                            If unset, button URLs degrade to relative paths.

Plan ref: docs/plans/inbox-audit-overhaul.md (Phase 5 redesign)
"""
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg
import httpx

SLACK_WEBHOOK_URL = os.getenv("SLACK_AUDIT_WEBHOOK_URL")
PUBLIC_REPORTS_URL = (os.getenv("PUBLIC_REPORTS_URL", "") or "").rstrip("/")


async def get_per_workspace_summary(db: asyncpg.Pool) -> List[Dict[str, Any]]:
    """One row per active workspace with cumulative counts for the daily summary."""
    rows = await db.fetch("""
        SELECT
            w.workspace_name,
            COUNT(*) FILTER (
                WHERE sa.status IS DISTINCT FROM 'Connected'
                  AND sa.inbox_state = 'live'
                  AND sa.emailbison_account_id IS NOT NULL
                  AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
                  AND ((sa.esp = 'microsoft'
                        AND sa.disconnected_at IS NOT NULL
                        AND sa.disconnected_at < NOW() - INTERVAL '48 hours')
                       OR (COALESCE(sa.esp, 'other') != 'microsoft'
                           AND sa.disconnected_at IS NOT NULL
                           AND sa.disconnected_at < NOW() - INTERVAL '24 hours'))
            ) AS disconnects,
            COUNT(*) FILTER (
                WHERE sa.kill_trigger IS NOT NULL
                  AND sa.inbox_state = 'dead'
                  AND sa.is_active = TRUE
                  AND sa.emailbison_account_id IS NOT NULL
                  AND (d.pool_status IS NULL OR d.pool_status != 'cancelled')
            ) AS total_kills,
            COUNT(*) FILTER (
                WHERE sa.is_quarantined = TRUE AND sa.is_active = TRUE
            ) AS quarantined,
            COUNT(*) FILTER (
                WHERE sa.inventory_lifecycle_status = 'incubating'
                  AND sa.is_active = TRUE
                  AND COALESCE(sa.warmup_started_at, sa.created_at) < NOW() - INTERVAL '14 days'
            ) AS stuck_incubation
        FROM workspaces w
        LEFT JOIN sender_accounts sa ON sa.workspace_id = w.id
        LEFT JOIN domains d ON sa.domain_id = d.id
        WHERE w.is_active = TRUE
        GROUP BY w.id, w.workspace_name
        HAVING COUNT(sa.id) > 0
        ORDER BY w.workspace_name
    """)
    return [dict(r) for r in rows]


async def get_domain_rollup(db: asyncpg.Pool) -> Dict[str, int]:
    """Domain-level rollups for the operator's "which domains to rotate" view."""
    rotation = await db.fetchrow("""
        SELECT COUNT(*) AS c FROM (
            SELECT d.id
            FROM domains d
            JOIN sender_accounts sa ON sa.domain_id = d.id
            JOIN workspaces w ON d.workspace_id = w.id
            WHERE w.is_active = TRUE AND d.pool_status != 'cancelled'
            GROUP BY d.id
            HAVING COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0
                OR COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') > 0
                OR COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') = COUNT(*)
                OR (COUNT(*) >= 5 AND 100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / COUNT(*) >= 80)
        ) x
    """)
    cancel = await db.fetchrow("""
        WITH la AS (
            SELECT DISTINCT ON (workspace_id) audit_data
            FROM inbox_audits
            WHERE workspace_id IS NOT NULL AND audit_data IS NOT NULL
            ORDER BY workspace_id, audit_date DESC, updated_at DESC
        )
        SELECT COALESCE(SUM(
            (jsonb_path_query_first(la.audit_data->'sections',
                                    '$[*] ? (@.code == "I-9")')
                ->'details'->>'eligible_count')::int
        ), 0) AS c
        FROM la
    """)
    return {
        "rotation": int(rotation["c"] if rotation else 0),
        "cancel_eligible": int(cancel["c"] if cancel else 0),
    }


def _btn(label: str, slug: str) -> Dict[str, Any]:
    elem: Dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": label, "emoji": True},
        "action_id": f"open_{slug}",
    }
    if PUBLIC_REPORTS_URL:
        elem["url"] = f"{PUBLIC_REPORTS_URL}/reports/{slug}"
    return elem


def build_message(
    workspace_stats: List[Dict[str, Any]],
    domain_summary: Dict[str, int],
) -> Dict[str, Any]:
    """Build Slack Block Kit payload for the daily audit message."""
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # Per-workspace summary lines.
    lines: List[str] = []
    fleet_clean = True
    for w in workspace_stats:
        bits: List[str] = []
        if w["disconnects"]:
            bits.append(f"{w['disconnects']} disc")
        if w["total_kills"]:
            bits.append(f"{w['total_kills']} kills")
        if w["quarantined"]:
            bits.append(f"{w['quarantined']} quar")
        if w["stuck_incubation"]:
            bits.append(f"{w['stuck_incubation']} stuck")
        if not bits:
            bits.append("_clean_")
        else:
            fleet_clean = False
        lines.append(f"*{w['workspace_name']}* — {', '.join(bits)}")

    workspace_text = "\n".join(lines) if lines else "_no active workspaces_"

    # Domain rollup line.
    domain_text = (
        f":recycle: *{domain_summary['rotation']}* domains flagged for rotation\n"
        f":receipt: *{domain_summary['cancel_eligible']}* domains eligible to cancel"
    )

    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Daily Inbox Audit — {today}",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*By workspace*  (cumulative — disc / kills / quarantined / stuck-incubation)\n\n{workspace_text}",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Domain-level signals*\n{domain_text}",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Open a report (cumulative, sortable by workspace + most recent event):*",
            },
        },
        {
            "type": "actions",
            "elements": [
                _btn(":electric_plug: Disconnects", "disconnects"),
                _btn(":skull: Kills", "kills"),
                _btn(":recycle: Domains to Rotate", "rotation"),
                _btn(":receipt: Cancel Candidates", "cancel-candidates"),
                _btn(":shield: Quarantined", "quarantined"),
                _btn(":hourglass_flowing_sand: Stuck in Incubation", "incubation-stuck"),
                _btn(":bar_chart: Capacity", "capacity"),
            ],
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"_Fleet status: {'clean' if fleet_clean else 'issues found'} ·_ "
                        f"_{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_"
                    ),
                }
            ],
        },
    ]
    return {"blocks": blocks}


async def send_daily_audit(db: asyncpg.Pool) -> Dict[str, Any]:
    """Build and post the daily audit message. Returns a result dict; never raises."""
    if not SLACK_WEBHOOK_URL:
        print("[slack_audit_v2] SLACK_AUDIT_WEBHOOK_URL not set — skipping post")
        return {"success": False, "reason": "webhook_not_configured"}

    try:
        ws_stats = await get_per_workspace_summary(db)
        domain_summary = await get_domain_rollup(db)
    except Exception as exc:
        print(f"[slack_audit_v2] Stats query failed: {exc!r}")
        return {"success": False, "reason": f"stats_query: {exc!r}"}

    message = build_message(ws_stats, domain_summary)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                SLACK_WEBHOOK_URL,
                json=message,
                headers={"Content-Type": "application/json"},
            )
            if r.status_code == 200:
                print(
                    f"[slack_audit_v2] Posted daily audit "
                    f"({len(ws_stats)} workspaces, "
                    f"{domain_summary['rotation']} rotation, "
                    f"{domain_summary['cancel_eligible']} cancel-eligible)"
                )
                return {"success": True, "workspace_count": len(ws_stats)}
            else:
                body = (r.text or "")[:300]
                print(f"[slack_audit_v2] Slack returned {r.status_code}: {body}")
                return {"success": False, "reason": f"slack_{r.status_code}", "body": body}
    except Exception as exc:
        print(f"[slack_audit_v2] Slack POST failed: {exc!r}")
        return {"success": False, "reason": f"http: {exc!r}"}
