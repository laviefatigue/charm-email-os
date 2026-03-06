"""
Slack Audit Module - Daily inbox health audit notifications.

Sends daily audit summaries to #inbox-audits channel with:
- Kill trigger summary (domain-killing vs inbox-killing)
- Campaigns to watch (high bounce/burn rates)
- Domains needing rotation (spam complaints, high death rates)
- Client capacity status (informational, rotation is client-driven)
- CSV download buttons for detailed review
"""

import os
import httpx
from datetime import datetime
from typing import Optional
from .database import fetch_all, fetch_one, execute

# Slack configuration
SLACK_WEBHOOK_URL = os.getenv("SLACK_AUDIT_WEBHOOK_URL")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://charm-api:8000")
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "https://api.wizardgrimoire.cloud")

# Domain-killing triggers (entire domain reputation compromised)
DOMAIN_KILLING_TRIGGERS = {'spam_complaint', 'provider_block_google', 'provider_block_microsoft', 'provider_block_yahoo'}


async def get_kill_trigger_stats() -> dict:
    """Get kill trigger statistics for last 24 hours with severity classification."""

    # Kill triggers in last 24h with workspace info
    kill_stats = await fetch_all("""
        SELECT
            sa.kill_trigger::text as trigger_type,
            COUNT(*) as count,
            COUNT(DISTINCT sa.domain_id) as domains_affected,
            array_agg(DISTINCT w.workspace_name) as workspaces
        FROM sender_accounts sa
        JOIN domains d ON sa.domain_id = d.id
        JOIN workspaces w ON d.workspace_id = w.id
        WHERE sa.killed_at >= NOW() - INTERVAL '24 hours'
        AND sa.kill_trigger IS NOT NULL
        GROUP BY sa.kill_trigger
        ORDER BY count DESC
    """)

    # Separate domain-killing from inbox-killing
    domain_killing = []
    inbox_killing = []

    for row in kill_stats:
        trigger = row['trigger_type']
        if trigger in DOMAIN_KILLING_TRIGGERS or trigger.startswith('provider_block_'):
            domain_killing.append(row)
        else:
            inbox_killing.append(row)

    total_kills = sum(row['count'] for row in kill_stats)
    domain_killing_count = sum(row['count'] for row in domain_killing)

    return {
        "total_kills": total_kills,
        "domain_killing_count": domain_killing_count,
        "inbox_killing_count": total_kills - domain_killing_count,
        "domain_killing": domain_killing,
        "inbox_killing": inbox_killing,
        "all_triggers": kill_stats
    }


async def get_campaigns_to_watch() -> list:
    """Get campaigns with concerning bounce/burn metrics."""

    return await fetch_all("""
        SELECT
            ec.campaign_name,
            w.workspace_name,
            ec.inboxes_burned_7d,
            ec.domains_burned_7d,
            ec.campaign_state,
            -- Calculate bounce rate from recent stats
            CASE
                WHEN COALESCE(cs.total_sent, 0) > 0
                THEN ROUND(100.0 * COALESCE(cs.bounced, 0) / cs.total_sent, 1)
                ELSE 0
            END as bounce_rate_pct,
            cs.total_sent,
            cs.bounced
        FROM emailbison_campaigns ec
        JOIN workspaces w ON ec.workspace_id = w.id
        LEFT JOIN LATERAL (
            SELECT
                SUM(sent) as total_sent,
                SUM(bounced) as bounced
            FROM campaign_snapshots
            WHERE campaign_id = ec.id
            AND snapshot_date >= CURRENT_DATE - INTERVAL '7 days'
        ) cs ON true
        WHERE w.is_active = TRUE
        AND (
            ec.inboxes_burned_7d >= 2
            OR ec.domains_burned_7d >= 2
            OR ec.campaign_state = 'quarantined'
            OR (COALESCE(cs.total_sent, 0) > 100 AND COALESCE(cs.bounced, 0)::float / NULLIF(cs.total_sent, 0) > 0.05)
        )
        ORDER BY ec.inboxes_burned_7d DESC, ec.domains_burned_7d DESC
        LIMIT 5
    """)


async def get_domains_needing_rotation() -> list:
    """Get domains that need rotation due to reputation damage or high death rates."""

    return await fetch_all("""
        SELECT
            d.domain_name,
            w.workspace_name,
            COUNT(*) as total_inboxes,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead_inboxes,
            COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') as spam_complaints,
            COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') as provider_blocks,
            ROUND(100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / NULLIF(COUNT(*), 0), 0) as death_rate_pct,
            CASE
                WHEN COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0 THEN 'spam_compromised'
                WHEN COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') > 0 THEN 'provider_blocked'
                WHEN COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') = COUNT(*) THEN 'all_dead'
                WHEN 100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / NULLIF(COUNT(*), 0) >= 80 THEN 'high_death_rate'
                ELSE 'monitor'
            END as rotation_reason
        FROM domains d
        JOIN sender_accounts sa ON sa.domain_id = d.id
        JOIN workspaces w ON d.workspace_id = w.id
        WHERE w.is_active = TRUE
        GROUP BY d.id, d.domain_name, w.workspace_name
        HAVING
            COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0
            OR COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') > 0
            OR COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') = COUNT(*)
            OR (COUNT(*) >= 5 AND 100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') / COUNT(*) >= 80)
        ORDER BY
            CASE
                WHEN COUNT(*) FILTER (WHERE sa.kill_trigger = 'spam_complaint') > 0 THEN 1
                WHEN COUNT(*) FILTER (WHERE sa.kill_trigger::text LIKE 'provider_block_%') > 0 THEN 2
                ELSE 3
            END,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') DESC
        LIMIT 10
    """)


async def get_client_capacity_status() -> list:
    """Get client capacity status (informational - rotation is client-driven)."""

    return await fetch_all("""
        SELECT
            w.workspace_name as client_name,
            COUNT(*) as total_inboxes,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') as live_connected,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'dead') as dead,
            COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status != 'Connected') as disconnected,
            ROUND(100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') / NULLIF(COUNT(*), 0), 0) as health_pct,
            COUNT(DISTINCT d.id) FILTER (WHERE sa.kill_trigger = 'spam_complaint') as compromised_domains
        FROM sender_accounts sa
        JOIN domains d ON sa.domain_id = d.id
        JOIN workspaces w ON d.workspace_id = w.id
        WHERE w.is_active = TRUE
        GROUP BY w.id, w.workspace_name
        HAVING COUNT(*) > 0
        ORDER BY
            ROUND(100.0 * COUNT(*) FILTER (WHERE sa.inbox_state = 'live' AND sa.status = 'Connected') / NULLIF(COUNT(*), 0), 0) ASC,
            COUNT(*) DESC
    """)


async def get_daily_audit_stats() -> dict:
    """Get comprehensive audit statistics for the last 24 hours."""

    # Kill trigger stats with severity
    kill_stats = await get_kill_trigger_stats()

    # Campaigns to watch
    campaigns_to_watch = await get_campaigns_to_watch()

    # Domains needing rotation
    domains_needing_rotation = await get_domains_needing_rotation()

    # Client capacity status
    capacity_status = await get_client_capacity_status()

    # Disconnected inboxes (live but not connected - could reconnect)
    disconnected = await fetch_one("""
        SELECT
            COUNT(*) FILTER (WHERE updated_at >= NOW() - INTERVAL '24 hours') as new_24h,
            COUNT(*) as total
        FROM sender_accounts
        WHERE status != 'Connected'
        AND inbox_state = 'live'
    """)

    return {
        "kill_stats": kill_stats,
        "campaigns_to_watch": campaigns_to_watch,
        "domains_needing_rotation": domains_needing_rotation,
        "capacity_status": capacity_status,
        "disconnected_new": disconnected["new_24h"] if disconnected else 0,
        "disconnected_total": disconnected["total"] if disconnected else 0,
        "generated_at": datetime.utcnow().isoformat()
    }


async def create_audit_record() -> str:
    """Create an audit record and return its ID for tracking responses."""
    result = await fetch_one("""
        INSERT INTO inbox_audits (
            audit_date,
            status,
            created_at
        ) VALUES (
            CURRENT_DATE,
            'pending',
            NOW()
        )
        RETURNING id
    """)
    return str(result["id"])


def build_slack_message(stats: dict, audit_id: str) -> dict:
    """Build Slack Block Kit message for audit notification."""

    today = datetime.now().strftime("%B %d, %Y")
    kill_stats = stats["kill_stats"]

    # Build kill trigger section
    kill_lines = []

    # Domain-killing triggers (critical)
    if kill_stats["domain_killing"]:
        kill_lines.append("*:rotating_light: Domain-Killing (reputation compromised):*")
        for t in kill_stats["domain_killing"]:
            workspaces = ", ".join(t["workspaces"][:3]) if t["workspaces"] else "unknown"
            kill_lines.append(f"  • {t['trigger_type']}: *{t['count']}* ({t['domains_affected']} domains) - {workspaces}")

    # Inbox-killing triggers
    if kill_stats["inbox_killing"]:
        kill_lines.append("*:x: Inbox-Killing:*")
        for t in kill_stats["inbox_killing"]:
            kill_lines.append(f"  • {t['trigger_type']}: *{t['count']}*")

    kill_text = "\n".join(kill_lines) if kill_lines else "_No new kills_"

    # Summary line
    summary = f"*{kill_stats['total_kills']} kills* "
    if kill_stats["domain_killing_count"] > 0:
        summary += f"(:rotating_light: {kill_stats['domain_killing_count']} domain-killing)"

    # Build campaigns to watch section
    campaign_lines = []
    for c in stats["campaigns_to_watch"][:3]:
        issues = []
        if c["inboxes_burned_7d"] >= 2:
            issues.append(f"{c['inboxes_burned_7d']} burns")
        if c["domains_burned_7d"] >= 2:
            issues.append(f"{c['domains_burned_7d']} domains")
        if c["bounce_rate_pct"] and c["bounce_rate_pct"] > 5:
            issues.append(f"{c['bounce_rate_pct']}% bounce")
        if c["campaign_state"] == "quarantined":
            issues.append("QUARANTINED")

        issue_text = ", ".join(issues)
        campaign_lines.append(f"• {c['campaign_name'][:30]} ({c['workspace_name']}): {issue_text}")

    campaign_text = "\n".join(campaign_lines) if campaign_lines else "_None_"

    # Build domains needing rotation section
    rotation_lines = []
    for d in stats["domains_needing_rotation"][:5]:
        reason_emoji = {
            "spam_compromised": ":biohazard_sign:",
            "provider_blocked": ":no_entry:",
            "all_dead": ":skull:",
            "high_death_rate": ":warning:"
        }.get(d["rotation_reason"], ":question:")

        rotation_lines.append(
            f"{reason_emoji} {d['domain_name']} ({d['workspace_name']}): "
            f"{d['dead_inboxes']}/{d['total_inboxes']} dead"
        )

    rotation_text = "\n".join(rotation_lines) if rotation_lines else "_None_"

    # Build capacity status section (top 5 lowest health)
    capacity_lines = []
    for c in stats["capacity_status"][:5]:
        if c["health_pct"] is None or c["health_pct"] >= 80:
            continue  # Skip healthy clients
        emoji = ":red_circle:" if c["health_pct"] < 50 else ":large_orange_circle:" if c["health_pct"] < 70 else ":large_yellow_circle:"
        compromised = f" :biohazard_sign:{c['compromised_domains']}" if c["compromised_domains"] else ""
        capacity_lines.append(
            f"{emoji} {c['client_name']}: {c['live_connected']}/{c['total_inboxes']} live "
            f"({c['health_pct']}%){compromised}"
        )

    capacity_text = "\n".join(capacity_lines) if capacity_lines else "_All clients healthy (>80%)_"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":clipboard: Daily Inbox Audit - {today}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Kill Triggers (last 24h):* {summary}\n{kill_text}"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":eyes: *Campaigns to Watch:*\n{campaign_text}"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":recycle: *Domains Needing Rotation:*\n{rotation_text}"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":bar_chart: *Client Capacity Status:*\n{capacity_text}"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":electric_plug: Disconnected (not dead): {stats['disconnected_new']} new, {stats['disconnected_total']} total | _Rotation is client-driven_"
                }
            ]
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Download detailed reports:*"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":skull: Kill Triggers",
                        "emoji": True
                    },
                    "url": f"{PUBLIC_API_URL}/api/health/export/kill-triggers",
                    "action_id": "download_kill_triggers"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":recycle: Rotation",
                        "emoji": True
                    },
                    "url": f"{PUBLIC_API_URL}/api/health/export/rotation-summary",
                    "action_id": "download_rotation"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":electric_plug: Disconnected",
                        "emoji": True
                    },
                    "url": f"{PUBLIC_API_URL}/api/health/export/disconnected",
                    "action_id": "download_disconnected"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":bar_chart: Capacity",
                        "emoji": True
                    },
                    "url": f"{PUBLIC_API_URL}/api/health/export/capacity-gaps",
                    "action_id": "download_capacity"
                }
            ]
        },
        {
            "type": "divider"
        },
        {
            "type": "actions",
            "block_id": f"audit_actions_{audit_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":white_check_mark: Reviewed",
                        "emoji": True
                    },
                    "style": "primary",
                    "action_id": "audit_confirmed",
                    "value": audit_id
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":warning: Issues Found",
                        "emoji": True
                    },
                    "style": "danger",
                    "action_id": "audit_issues",
                    "value": audit_id
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Audit ID: `{audit_id}` | {stats['generated_at'][:19]} UTC"
                }
            ]
        }
    ]

    return {"blocks": blocks}


async def send_daily_audit() -> dict:
    """Send daily audit message to Slack."""

    if not SLACK_WEBHOOK_URL:
        return {"success": False, "error": "SLACK_AUDIT_WEBHOOK_URL not configured"}

    try:
        # Get stats
        stats = await get_daily_audit_stats()

        # Create audit record
        audit_id = await create_audit_record()

        # Build message
        message = build_slack_message(stats, audit_id)

        # Send to Slack
        async with httpx.AsyncClient() as client:
            response = await client.post(
                SLACK_WEBHOOK_URL,
                json=message,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code == 200:
                print(f"[SlackAudit] Daily audit sent successfully (audit_id={audit_id})")
                return {
                    "success": True,
                    "audit_id": audit_id,
                    "stats": stats
                }
            else:
                print(f"[SlackAudit] Failed to send: {response.status_code} - {response.text}")
                return {
                    "success": False,
                    "error": f"Slack returned {response.status_code}: {response.text}"
                }

    except Exception as e:
        print(f"[SlackAudit] Error sending audit: {e}")
        return {"success": False, "error": str(e)}


async def update_audit_status(audit_id: str, status: str, reviewer: str, notes: Optional[str] = None):
    """Update audit record with review status."""
    await execute("""
        UPDATE inbox_audits
        SET
            status = $1,
            reviewed_by = $2,
            reviewed_at = NOW(),
            notes = $3
        WHERE id = $4
    """, status, reviewer, notes, int(audit_id))


async def log_audit_correction(audit_id: str, email_address: str, correction_type: str, reason: str):
    """Log a correction for an incorrectly flagged inbox."""
    await execute("""
        INSERT INTO inbox_audit_corrections (
            audit_id,
            email_address,
            correction_type,
            reason,
            created_at
        ) VALUES ($1, $2, $3, $4, NOW())
    """, int(audit_id), email_address, correction_type, reason)
