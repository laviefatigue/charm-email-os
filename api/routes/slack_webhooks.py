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
    """Manually trigger an audit message using the centralized slack_audit module.

    This ensures consistency between manual triggers and scheduled audits.
    """
    try:
        # Import here to avoid circular imports
        import sys
        sys.path.insert(0, '/app')
        from sync_modules.slack_audit import send_daily_audit, get_daily_audit_stats

        # Get stats for the response
        stats = await get_daily_audit_stats()

        # Send the actual audit using the centralized module
        result = await send_daily_audit()

        if result["success"]:
            return {
                "success": True,
                "audit_id": result.get("audit_id"),
                "total_kills": stats["kill_stats"]["total_kills"],
                "total_disconnected": stats["disconnected_total"]
            }
        else:
            return result

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
