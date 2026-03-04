"""
Slack Webhooks - Handle interactive button callbacks from Slack.

This module handles the "Mark as Completed" button clicks from
Hypertide order specification messages.

Slack App Configuration Required:
1. Go to Slack App settings -> Interactivity & Shortcuts
2. Enable Interactivity
3. Set Request URL to: https://your-api.domain.com/api/slack/interactions
"""

from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
import json
import logging
import hmac
import hashlib
import os

from database import execute, fetch_one, fetch_all
import httpx

router = APIRouter()
logger = logging.getLogger(__name__)

# Slack signing secret for verifying requests (optional but recommended)
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")


def verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify that the request came from Slack using signing secret."""
    if not SLACK_SIGNING_SECRET:
        # SECURITY: In production, reject requests without signing secret configured
        # Only skip verification in development mode
        import os
        if os.getenv("DEBUG", "").lower() in ("true", "1"):
            logger.warning("SLACK_SIGNING_SECRET not configured - skipping verification (DEBUG mode)")
            return True
        logger.error("SLACK_SIGNING_SECRET not configured - rejecting request in production")
        return False

    # Check timestamp to prevent replay attacks
    if abs(int(timestamp) - datetime.now().timestamp()) > 60 * 5:
        logger.warning("Slack request timestamp too old")
        return False

    # Build the signature base string
    sig_basestring = f"v0:{timestamp}:{request_body.decode('utf-8')}"

    # Calculate the signature
    my_signature = 'v0=' + hmac.new(
        SLACK_SIGNING_SECRET.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(my_signature, signature)


@router.post("/interactions")
async def handle_slack_interaction(request: Request):
    """
    Handle Slack interactive component callbacks.

    This endpoint receives POST requests when users click interactive
    buttons in Slack messages (like "Mark as Completed").

    Slack sends the payload as form-urlencoded with a 'payload' field
    containing JSON.
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Verify request came from Slack (if signing secret is configured)
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")

        if SLACK_SIGNING_SECRET and not verify_slack_signature(body, timestamp, signature):
            logger.error("Failed to verify Slack request signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse the form data
        form_data = await request.form()
        payload_str = form_data.get("payload", "{}")

        logger.info(f"Slack webhook received - payload length: {len(payload_str)}")

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse Slack payload: {payload_str[:200]}")
            raise HTTPException(status_code=400, detail="Invalid payload")

        logger.info(f"Slack payload parsed - type: {payload.get('type')}")

        # Extract action info
        actions = payload.get("actions", [])
        if not actions:
            logger.warning(f"No actions in Slack payload. Keys: {list(payload.keys())}")
            return JSONResponse(content={"text": "No action specified"})

        action = actions[0]
        action_id = action.get("action_id", "")
        action_value = action.get("value", "")

        logger.info(f"Received Slack action: action_id='{action_id}' value='{action_value}'")

        # Handle "Mark as Completed" button for Hypertide orders
        if action_id == "complete_hypertide_order":
            return await _handle_complete_order(action_value, payload)

        # Handle inbox audit actions
        if action_id == "audit_confirmed":
            return await _handle_audit_confirmed(action_value, payload)

        if action_id == "audit_issues":
            return await _handle_audit_issues(action_value, payload)

        # Unknown action
        logger.warning(f"Unknown Slack action_id: {action_id}")
        return JSONResponse(content={"text": f"Unknown action: {action_id}"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Slack interaction: {e}", exc_info=True)
        return JSONResponse(
            content={"text": f"Error processing request: {str(e)}"},
            status_code=500
        )


async def _handle_complete_order(job_id: str, payload: dict) -> JSONResponse:
    """
    Handle the "Mark as Completed" button click for Hypertide orders.

    Updates the job status to 'completed' and sends a confirmation
    message to Slack.
    """
    logger.info(f"Marking Hypertide order {job_id} as completed")

    try:
        # Validate job_id is a valid UUID
        try:
            job_uuid = UUID(job_id)
        except ValueError:
            return JSONResponse(content={
                "response_type": "ephemeral",
                "text": f":x: Invalid job ID: {job_id}"
            })

        # Check if job exists and get current status
        job = await fetch_one("""
            SELECT id, status, client_id
            FROM inbox_purchase_jobs
            WHERE id = $1
        """, job_uuid)

        if not job:
            return JSONResponse(content={
                "response_type": "ephemeral",
                "text": f":x: Job not found: `{job_id[:8]}...`"
            })

        current_status = job["status"]

        # Only allow completion from certain statuses
        valid_statuses = ["awaiting_manual_order", "pending", "executing"]
        if current_status not in valid_statuses:
            return JSONResponse(content={
                "response_type": "ephemeral",
                "text": f":warning: Job `{job_id[:8]}...` is already {current_status}"
            })

        # Update job status to completed
        await execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'completed',
                completed_at = $2,
                current_step = 'Manually completed via Slack'
            WHERE id = $1
        """, job_uuid, datetime.now(timezone.utc))

        logger.info(f"Hypertide order {job_id} marked as completed via Slack")

        # Get user info from payload
        user_name = payload.get("user", {}).get("name", "Someone")

        # Return success message to channel
        return JSONResponse(content={
            "response_type": "in_channel",
            "replace_original": False,
            "text": f":white_check_mark: Order `{job_id[:8]}...` marked as completed by @{user_name}!"
        })

    except Exception as e:
        logger.error(f"Error completing order {job_id}: {e}", exc_info=True)
        return JSONResponse(content={
            "response_type": "ephemeral",
            "text": f":x: Failed to complete order: {str(e)}"
        })


@router.get("/test")
async def test_slack_webhooks():
    """Test endpoint to verify the Slack webhooks router is working."""
    return {
        "status": "ok",
        "message": "Slack webhooks router is active",
        "signing_secret_configured": bool(SLACK_SIGNING_SECRET)
    }


# ============================================================================
# INBOX AUDIT HANDLERS
# ============================================================================

async def _handle_audit_confirmed(audit_id: str, payload: dict) -> JSONResponse:
    """Handle 'Confirmed - All Correct' button click for inbox audits."""
    user_name = payload.get("user", {}).get("name", "unknown")

    logger.info(f"Audit {audit_id} confirmed by {user_name}")

    # Update audit status
    await execute("""
        UPDATE inbox_audits
        SET
            status = 'confirmed',
            reviewed_by = $1,
            reviewed_at = NOW()
        WHERE id = $2
    """, user_name, int(audit_id))

    # Log to history
    await execute("""
        INSERT INTO inbox_audit_history (audit_id, action, actor, details)
        VALUES ($1, 'confirmed', $2, $3)
    """, int(audit_id), user_name, json.dumps({"source": "slack_button"}))

    # Update the original message
    return JSONResponse(content={
        "response_type": "in_channel",
        "replace_original": True,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":white_check_mark: *Audit Confirmed*\n\nReviewed by @{user_name} at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n\nAudit ID: `{audit_id}`"
                }
            }
        ]
    })


async def _handle_audit_issues(audit_id: str, payload: dict) -> JSONResponse:
    """Handle 'Issues Found' button click - update message with instructions."""
    user_name = payload.get("user", {}).get("name", "unknown")

    logger.info(f"Audit {audit_id} flagged with issues by {user_name}")

    # Update audit status
    await execute("""
        UPDATE inbox_audits
        SET
            status = 'issues_found',
            reviewed_by = $1,
            reviewed_at = NOW()
        WHERE id = $2
    """, user_name, int(audit_id))

    # Log to history
    await execute("""
        INSERT INTO inbox_audit_history (audit_id, action, actor, details)
        VALUES ($1, 'issues_found', $2, $3)
    """, int(audit_id), user_name, json.dumps({"source": "slack_button"}))

    # Get API URL for corrections endpoint
    api_url = os.getenv("PUBLIC_API_URL", "http://charm-api:8000")

    # Update message with correction instructions
    return JSONResponse(content={
        "response_type": "in_channel",
        "replace_original": True,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":warning: *Audit Issues Reported*\n\nFlagged by @{user_name} at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*To submit corrections:*\n\n1. Download the CSV from the original audit message\n2. Add a `correction_type` column with one of:\n   • `wrong_kill` - Inbox shouldn't have been killed\n   • `false_positive` - Trigger was incorrect\n   • `should_restore` - Need to restore this inbox\n3. Add an optional `reason` column\n4. Upload to the corrections endpoint"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Upload corrections:*\n```\ncurl -X POST '{api_url}/api/slack/corrections/{audit_id}' \\\n  -F 'file=@corrections.csv'\n```"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Audit ID: `{audit_id}`"
                    }
                ]
            }
        ]
    })


# ============================================================================
# CORRECTIONS ENDPOINTS
# ============================================================================

import csv
import io
from fastapi import UploadFile, File, Form

@router.post("/corrections/{audit_id}")
async def submit_corrections(
    audit_id: int,
    file: UploadFile = File(...),
):
    """
    Upload a CSV with corrections for incorrectly flagged inboxes.

    CSV format:
    - email_address (required)
    - correction_type (required): wrong_kill, false_positive, should_restore
    - reason (optional): Explanation

    Returns count of corrections processed.
    """
    logger.info(f"Receiving corrections for audit {audit_id}")

    # Verify audit exists
    audit = await fetch_one("SELECT id, status FROM inbox_audits WHERE id = $1", audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

    # Read and parse CSV
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text_content))

    corrections_added = 0
    errors = []

    for i, row in enumerate(reader, start=2):
        email = row.get("email_address", "").strip()
        correction_type = row.get("correction_type", "").strip().lower()
        reason = row.get("reason", "").strip()

        if not email:
            continue

        if correction_type not in ["wrong_kill", "false_positive", "should_restore", "other"]:
            errors.append(f"Row {i}: Invalid correction_type '{correction_type}'")
            continue

        await execute("""
            INSERT INTO inbox_audit_corrections (
                audit_id, email_address, correction_type, reason
            ) VALUES ($1, $2, $3, $4)
        """, audit_id, email, correction_type, reason or None)

        corrections_added += 1

    # Log to history
    await execute("""
        INSERT INTO inbox_audit_history (audit_id, action, actor, details)
        VALUES ($1, 'corrections_uploaded', 'api', $2)
    """, audit_id, json.dumps({
        "corrections_added": corrections_added,
        "errors": errors[:10]
    }))

    logger.info(f"Processed {corrections_added} corrections for audit {audit_id}")

    return {
        "success": True,
        "audit_id": audit_id,
        "corrections_added": corrections_added,
        "errors": errors
    }


@router.get("/corrections/{audit_id}")
async def get_corrections(audit_id: int):
    """Get all corrections for an audit."""
    corrections = await fetch_one("""
        SELECT
            c.id,
            c.email_address,
            c.correction_type,
            c.reason,
            c.resolved,
            c.resolved_by,
            c.resolved_at,
            c.created_at
        FROM inbox_audit_corrections c
        WHERE c.audit_id = $1
        ORDER BY c.created_at DESC
    """, audit_id)

    return {
        "audit_id": audit_id,
        "corrections": corrections or []
    }


@router.post("/corrections/{audit_id}/{correction_id}/resolve")
async def resolve_correction(
    audit_id: int,
    correction_id: int,
    resolved_by: str = Form(...),
    resolution_notes: str = Form(None)
):
    """Mark a correction as resolved."""
    await execute("""
        UPDATE inbox_audit_corrections
        SET
            resolved = TRUE,
            resolved_by = $1,
            resolved_at = NOW(),
            resolution_notes = $2
        WHERE id = $3 AND audit_id = $4
    """, resolved_by, resolution_notes, correction_id, audit_id)

    return {"success": True, "correction_id": correction_id}


@router.post("/trigger-audit")
async def trigger_manual_audit():
    """Manually trigger an audit message (for testing)."""
    SLACK_WEBHOOK_URL = os.getenv("SLACK_AUDIT_WEBHOOK_URL")
    PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://nckgggwww8sggg0kc4wo00o8.187.77.19.81.sslip.io")

    if not SLACK_WEBHOOK_URL:
        return {"success": False, "error": "SLACK_AUDIT_WEBHOOK_URL not configured"}

    try:
        # Get kill stats
        kill_stats = await fetch_all("""
            SELECT kill_trigger, COUNT(*) as count
            FROM sender_accounts
            WHERE killed_at >= NOW() - INTERVAL '24 hours'
            AND kill_trigger IS NOT NULL
            GROUP BY kill_trigger
            ORDER BY count DESC
        """)
        total_kills = sum(row["count"] for row in kill_stats) if kill_stats else 0

        # Get disconnected stats
        new_disconnected = await fetch_one("""
            SELECT COUNT(*) as count FROM sender_accounts
            WHERE status != 'Connected' AND inbox_state = 'live'
            AND updated_at >= NOW() - INTERVAL '24 hours'
        """)
        total_disconnected = await fetch_one("""
            SELECT COUNT(*) as count FROM sender_accounts
            WHERE status != 'Connected' AND inbox_state = 'live'
        """)

        # Top workspaces
        workspace_kills = await fetch_all("""
            SELECT w.workspace_name, COUNT(*) as count
            FROM sender_accounts sa
            JOIN workspaces w ON sa.workspace_id = w.id
            WHERE sa.killed_at >= NOW() - INTERVAL '24 hours'
            AND sa.kill_trigger IS NOT NULL AND w.is_active = TRUE
            GROUP BY w.workspace_name ORDER BY count DESC LIMIT 5
        """)

        # Dead domains (domains where ALL inboxes are gone from EmailBison - need to cancel subscriptions)
        dead_domains = await fetch_one("""
            SELECT COUNT(*) as count FROM (
                SELECT d.id
                FROM domains d
                JOIN workspaces w ON d.workspace_id = w.id
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*) AS total_inboxes,
                        COUNT(*) FILTER (WHERE sa.is_active = TRUE) AS inboxes_in_emailbison
                    FROM sender_accounts sa
                    WHERE sa.domain_id = d.id
                ) inbox_stats ON true
                WHERE w.is_active = TRUE
                AND d.is_active = TRUE
                AND inbox_stats.total_inboxes > 0
                AND inbox_stats.inboxes_in_emailbison = 0
            ) dead
        """)

        # Create audit record
        audit_record = await fetch_one("""
            INSERT INTO inbox_audits (audit_date, status, total_kills, total_disconnected)
            VALUES (CURRENT_DATE, 'pending', $1, $2)
            RETURNING id
        """, total_kills, total_disconnected["count"] if total_disconnected else 0)
        audit_id = str(audit_record["id"])

        # Build message
        today = datetime.now().strftime("%B %d, %Y")
        kill_lines = []
        if kill_stats:
            for row in kill_stats:
                emoji = {
                    "hard_bounces_24h": ":no_entry:",
                    "spam_complaint": ":rotating_light:",
                    "fresh_inbox_bounce": ":seedling:",
                    "disconnected_21d": ":electric_plug:"
                }.get(row["kill_trigger"], ":x:")
                kill_lines.append(f"{emoji} {row['kill_trigger']}: *{row['count']}*")
        kill_text = "\n".join(kill_lines) if kill_lines else "_No new kills_"

        workspace_lines = []
        if workspace_kills:
            for ws in workspace_kills[:3]:
                workspace_lines.append(f"• {ws['workspace_name']}: {ws['count']}")
        workspace_text = "\n".join(workspace_lines) if workspace_lines else "_None_"

        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": f":clipboard: Daily Inbox Audit - {today}", "emoji": True}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Kill Triggers (last 24h):* {total_kills} inboxes\n{kill_text}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Top Workspaces:*\n{workspace_text}"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": f":electric_plug: *Disconnected Inboxes:* {new_disconnected['count'] if new_disconnected else 0} new ({total_disconnected['count'] if total_disconnected else 0} total)"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": f":headstone: *Dead Domains (Cancel Subscriptions):* {dead_domains['count'] if dead_domains else 0} domains"}},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Download reports for review:*"}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": ":inbox_tray: Kill Triggers CSV", "emoji": True}, "url": f"{PUBLIC_API_URL}/api/health/export/kill-triggers", "action_id": "download_kill_triggers"},
                {"type": "button", "text": {"type": "plain_text", "text": ":inbox_tray: Disconnected CSV", "emoji": True}, "url": f"{PUBLIC_API_URL}/api/health/export/disconnected", "action_id": "download_disconnected"},
                {"type": "button", "text": {"type": "plain_text", "text": ":headstone: Dead Domains CSV", "emoji": True}, "url": f"{PUBLIC_API_URL}/api/health/export/dead-domains", "action_id": "download_dead_domains"}
            ]},
            {"type": "divider"},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*After reviewing, confirm the audit:*"}},
            {"type": "actions", "block_id": f"audit_actions_{audit_id}", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": ":white_check_mark: Confirmed - All Correct", "emoji": True}, "style": "primary", "action_id": "audit_confirmed", "value": audit_id},
                {"type": "button", "text": {"type": "plain_text", "text": ":warning: Issues Found", "emoji": True}, "style": "danger", "action_id": "audit_issues", "value": audit_id}
            ]},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": f"Audit ID: `{audit_id}` | Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"}]}
        ])

        # Send to Slack
        async with httpx.AsyncClient() as client:
            response = await client.post(SLACK_WEBHOOK_URL, json={"blocks": blocks}, headers={"Content-Type": "application/json"})

            if response.status_code == 200:
                logger.info(f"Daily audit sent successfully (audit_id={audit_id})")
                return {"success": True, "audit_id": audit_id, "total_kills": total_kills, "total_disconnected": total_disconnected["count"] if total_disconnected else 0}
            else:
                return {"success": False, "error": f"Slack returned {response.status_code}: {response.text}"}

    except Exception as e:
        logger.error(f"Failed to trigger audit: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@router.get("/audits")
async def list_audits(limit: int = 10):
    """List recent audits."""
    audits = await fetch_one("""
        SELECT
            id,
            audit_date,
            status,
            reviewed_by,
            reviewed_at,
            total_kills,
            total_disconnected,
            created_at
        FROM inbox_audits
        ORDER BY created_at DESC
        LIMIT $1
    """, limit)

    return {"audits": audits or []}


@router.get("/audits/{audit_id}")
async def get_audit(audit_id: int):
    """Get audit details including corrections."""
    audit = await fetch_one("SELECT * FROM inbox_audits WHERE id = $1", audit_id)

    if not audit:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

    corrections = await fetch_one(
        "SELECT * FROM inbox_audit_corrections WHERE audit_id = $1",
        audit_id
    )

    history = await fetch_one(
        "SELECT * FROM inbox_audit_history WHERE audit_id = $1 ORDER BY created_at",
        audit_id
    )

    return {
        "audit": dict(audit) if audit else None,
        "corrections": corrections or [],
        "history": history or []
    }
