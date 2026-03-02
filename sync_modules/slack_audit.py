"""
Slack Audit Module - Daily inbox health audit notifications.

Sends daily audit summaries to #inbox-audits channel with:
- Kill trigger summary (new kills since last audit)
- Disconnected inbox count
- CSV download buttons
- Confirmation/Issues buttons for team review
"""

import os
import json
import httpx
from datetime import datetime, timedelta
from typing import Optional
from .database import fetch_all, fetch_one, execute

# Slack configuration
SLACK_WEBHOOK_URL = os.getenv("SLACK_AUDIT_WEBHOOK_URL")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://charm-api:8000")
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://nckgggwww8sggg0kc4wo00o8.187.77.19.81.sslip.io")


async def get_daily_audit_stats() -> dict:
    """Get audit statistics for the last 24 hours."""

    # Kill triggers in last 24h
    kill_stats = await fetch_all("""
        SELECT
            kill_trigger,
            COUNT(*) as count
        FROM sender_accounts
        WHERE killed_at >= NOW() - INTERVAL '24 hours'
        AND kill_trigger IS NOT NULL
        GROUP BY kill_trigger
        ORDER BY count DESC
    """)

    # Total kills
    total_kills = sum(row["count"] for row in kill_stats)

    # New disconnections in last 24h (live inboxes that became disconnected)
    disconnected_stats = await fetch_one("""
        SELECT COUNT(*) as count
        FROM sender_accounts
        WHERE status != 'Connected'
        AND inbox_state = 'live'
        AND updated_at >= NOW() - INTERVAL '24 hours'
    """)

    # Total disconnected (for context)
    total_disconnected = await fetch_one("""
        SELECT COUNT(*) as count
        FROM sender_accounts
        WHERE status != 'Connected'
        AND inbox_state = 'live'
    """)

    # Workspace breakdown for kills
    workspace_kills = await fetch_all("""
        SELECT
            w.workspace_name,
            COUNT(*) as count
        FROM sender_accounts sa
        JOIN workspaces w ON sa.workspace_id = w.id
        WHERE sa.killed_at >= NOW() - INTERVAL '24 hours'
        AND sa.kill_trigger IS NOT NULL
        AND w.is_active = TRUE
        GROUP BY w.workspace_name
        ORDER BY count DESC
        LIMIT 5
    """)

    return {
        "total_kills": total_kills,
        "kill_breakdown": {row["kill_trigger"]: row["count"] for row in kill_stats},
        "new_disconnected": disconnected_stats["count"] if disconnected_stats else 0,
        "total_disconnected": total_disconnected["count"] if total_disconnected else 0,
        "top_workspaces": workspace_kills,
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

    # Build kill trigger breakdown text
    kill_lines = []
    for trigger, count in stats["kill_breakdown"].items():
        emoji = {
            "hard_bounces_24h": ":no_entry:",
            "spam_complaint": ":rotating_light:",
            "fresh_inbox_bounce": ":seedling:",
            "disconnected_21d": ":electric_plug:"
        }.get(trigger, ":x:")
        kill_lines.append(f"{emoji} {trigger}: *{count}*")

    kill_text = "\n".join(kill_lines) if kill_lines else "_No new kills_"

    # Build workspace breakdown
    workspace_lines = []
    for ws in stats["top_workspaces"][:3]:
        workspace_lines.append(f"• {ws['workspace_name']}: {ws['count']}")
    workspace_text = "\n".join(workspace_lines) if workspace_lines else "_None_"

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
                "text": f"*Kill Triggers (last 24h):* {stats['total_kills']} inboxes\n{kill_text}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Top Workspaces:*\n{workspace_text}"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":electric_plug: *Disconnected Inboxes:* {stats['new_disconnected']} new ({stats['total_disconnected']} total)"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Download reports for review:*"
            }
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":inbox_tray: Kill Triggers CSV",
                        "emoji": True
                    },
                    "url": f"{PUBLIC_API_URL}/api/health/export/kill-triggers",
                    "action_id": "download_kill_triggers"
                },
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":inbox_tray: Disconnected CSV",
                        "emoji": True
                    },
                    "url": f"{PUBLIC_API_URL}/api/health/export/disconnected",
                    "action_id": "download_disconnected"
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
                "text": "*After reviewing, confirm the audit:*"
            }
        },
        {
            "type": "actions",
            "block_id": f"audit_actions_{audit_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": ":white_check_mark: Confirmed - All Correct",
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
                    "text": f"Audit ID: `{audit_id}` | Generated: {stats['generated_at'][:19]} UTC"
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
