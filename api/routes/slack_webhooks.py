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

from database import execute, fetch_one

router = APIRouter()
logger = logging.getLogger(__name__)

# Slack signing secret for verifying requests (optional but recommended)
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")


def verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify that the request came from Slack using signing secret."""
    if not SLACK_SIGNING_SECRET:
        # If no signing secret configured, skip verification (development mode)
        logger.warning("SLACK_SIGNING_SECRET not configured - skipping signature verification")
        return True

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
