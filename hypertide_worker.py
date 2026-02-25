#!/usr/bin/env python3
"""
Hypertide Worker - External worker for domain purchases and inbox provisioning.

Processes two job types:
1. domain_purchase_jobs - Purchase domains from Dynadot/Porkbun registrars
2. inbox_purchase_jobs - Provision inboxes via Hypertide browser automation

This worker runs separately from the API, allowing:
- Independent deployment and updates
- Resilient job processing (jobs persist in DB)
- Horizontal scaling (multiple workers can run)

Usage:
    python hypertide_worker.py

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    POLL_INTERVAL (default: 10 seconds)
    WORKER_ID (default: auto-generated hostname-based)
    STALE_JOB_MINUTES (default: 30 - reclaim jobs from crashed workers)
    HYPERTIDE_HEADLESS (default: true)
    PORKBUN_API_KEY, PORKBUN_API_SECRET
    DYNADOT_API_KEY
"""

import os
import sys
import time
import socket
import logging
import json
import httpx
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Add the api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("hypertide_worker")

# =============================================================================
# Configuration
# =============================================================================

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
WORKER_ID = os.getenv("WORKER_ID", f"worker-{socket.gethostname()}")
STALE_JOB_MINUTES = int(os.getenv("STALE_JOB_MINUTES", "30"))
SLACK_ORDERS_WEBHOOK_URL = os.getenv("SLACK_ORDERS_WEBHOOK_URL", "")

# =============================================================================
# Slack Notification Functions
# =============================================================================

def _send_slack_notification(message: dict) -> bool:
    """Send a Slack notification via webhook."""
    if not SLACK_ORDERS_WEBHOOK_URL:
        logger.warning("SLACK_ORDERS_WEBHOOK_URL not configured - skipping notification")
        return False

    try:
        response = httpx.post(
            SLACK_ORDERS_WEBHOOK_URL,
            json=message,
            timeout=10.0
        )
        if response.status_code == 200:
            logger.info("Slack notification sent successfully")
            return True
        else:
            logger.warning(f"Slack notification failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send Slack notification: {e}")
        return False


def _generate_slack_order_started_message(job: dict, client_name: str) -> dict:
    """Generate Slack message for order started notification (blue)."""
    job_id = str(job.get("id", "unknown"))
    provider_type = job.get("provider_type", "unknown")
    domain_names = job.get("domain_names", [])
    orders_total = len(domain_names) // (2 if provider_type == "entra" else 5) or 1
    monthly_cost = orders_total * 50

    provider_emoji = ":office:" if provider_type == "entra" else ":envelope:"

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":rocket: *Hypertide Order Started*"}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Client:* {client_name}\n*Provider:* {provider_emoji} {provider_type.upper()}\n*Domains:* {len(domain_names)}\n*Est. Cost:* ${monthly_cost:.0f}/mo"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Domains:*\n```{chr(10).join(domain_names[:10])}{'...' if len(domain_names) > 10 else ''}```"
            }
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Job ID: `{job_id[:8]}...` | :hourglass_flowing_sand: Worker automation in progress..."}
            ]
        }
    ]

    return {
        "attachments": [{"color": "#3498db", "blocks": blocks}],
        "text": f"Order started for {client_name}"
    }


def _generate_slack_ready_for_payment_message(job: dict, client_name: str, checkout_url: str = None) -> dict:
    """Generate Slack message for order ready for payment (amber)."""
    job_id = str(job.get("id", "unknown"))
    provider_type = job.get("provider_type", "unknown")
    domain_names = job.get("domain_names", [])

    provider_emoji = ":office:" if provider_type == "entra" else ":envelope:"

    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":credit_card: *Hypertide Order Ready for Payment*"}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Client:* {client_name}\n*Provider:* {provider_emoji} {provider_type.upper()}\n*Domains:* {len(domain_names)}"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Domains:*\n```{chr(10).join(domain_names[:5])}{'...' if len(domain_names) > 5 else ''}```"
            }
        }
    ]

    # Add checkout button if URL provided
    if checkout_url:
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": ":credit_card: Pay Now", "emoji": True},
                "style": "primary",
                "url": checkout_url
            }]
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Job ID: `{job_id[:8]}...` | Click to open Stripe checkout"}]
        })
    else:
        # No checkout URL captured - provide manual instructions
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":point_right: *Next step:* Click button below, then click 'Checkout with Stripe' on Hypertide"
            }
        })
        blocks.append({
            "type": "actions",
            "elements": [{
                "type": "button",
                "text": {"type": "plain_text", "text": ":credit_card: Open Hypertide to Pay", "emoji": True},
                "style": "primary",
                "url": "https://app2.hypertide.io/review-order"
            }]
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Job ID: `{job_id[:8]}...` | All setup complete - just pay!"}]
        })

    return {
        "attachments": [{"color": "#f39c12", "blocks": blocks}],
        "text": f"Order ready for payment: {client_name}"
    }


def _generate_slack_order_specification(job: dict, client_name: str) -> dict:
    """
    Generate detailed Slack message with all order specifications.

    This message contains everything needed to manually create the Hypertide order.
    """
    job_id = str(job.get("id", "unknown"))
    provider_type = job.get("provider_type", "entra")
    domain_names = job.get("domain_names", [])
    request_data = job.get('request_data', {})

    # Calculate values based on provider type
    is_entra = provider_type == "entra"
    domains_per_order = 2 if is_entra else 5
    inboxes_per_domain = 50 if is_entra else 3
    orders_needed = max(1, (len(domain_names) + domains_per_order - 1) // domains_per_order)
    monthly_cost = orders_needed * 50
    total_inboxes = len(domain_names) * inboxes_per_domain

    provider_emoji = ":office:" if is_entra else ":envelope:"
    plan_name = "Hypertide Entra" if is_entra else "Hypertide Google"

    # Extract configuration from request_data
    forwarding_domain = request_data.get('forwarding_domain', 'N/A')
    if not forwarding_domain or forwarding_domain == 'N/A':
        # Try to derive from first domain
        if domain_names:
            parts = domain_names[0].split('.')
            if len(parts) >= 2:
                forwarding_domain = '.'.join(parts[-2:])

    sender_names = request_data.get('sender_names', [])
    if sender_names and isinstance(sender_names, list) and len(sender_names) > 0:
        first_name = sender_names[0].get('firstName', 'Chris')
        last_name = sender_names[0].get('lastName', 'Booth')
    else:
        first_name = 'Chris'
        last_name = 'Booth'

    # Build domains list for display (limit to 20 for readability)
    domains_display = "\n".join(domain_names[:20])
    if len(domain_names) > 20:
        domains_display += f"\n... and {len(domain_names) - 20} more"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "📋 New Hypertide Order Specification", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Client:* {client_name}\n*Provider:* {provider_emoji} {provider_type.upper()}\n*Domains:* {len(domain_names)} → *{total_inboxes} inboxes*\n*Est. Cost:* ${monthly_cost}/mo"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*STEP 1: Choose Plan*\nSelect: *{plan_name}*\nQuantity: *{orders_needed} order(s)*"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*STEP 2: Select Domains (BYOD)*\n```{domains_display}```"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*STEP 3: Domain Settings*\n• Forwarding URL: `{forwarding_domain}`\n• Company Name: `{client_name}`\n• Email Tool: Bison (use saved creds)\n• Warmup & Outbound: defaults\n• User: `{first_name} {last_name}`"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*STEP 4: Checkout*\nComplete Stripe payment"
            }
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🚀 Open Hypertide", "emoji": True},
                    "url": "https://app2.hypertide.io/choose-plan"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ Mark as Completed", "emoji": True},
                    "style": "primary",
                    "action_id": f"complete_hypertide_order",
                    "value": job_id
                }
            ]
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Job ID: `{job_id[:8]}...` | Click 'Mark as Completed' after Stripe payment"}]
        }
    ]

    return {
        "attachments": [{"color": "#3498db", "blocks": blocks}],
        "text": f"New order specification for {client_name}"
    }


def _get_client_name(client_id: str) -> str:
    """Look up client name from database."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM clients WHERE id = %s", (client_id,))
        row = cur.fetchone()
        return row['name'] if row else "Unknown Client"
    finally:
        cur.close()
        conn.close()


# =============================================================================
# Database Helpers
# =============================================================================

def get_db_connection():
    """Create a database connection."""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def get_pending_domain_purchase_job() -> Optional[dict]:
    """Get next pending domain purchase job."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, client_id, workspace_id, domain_ids, domain_names,
                   registrar, retry_count, max_retries
            FROM domain_purchase_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """)
        row = cur.fetchone()
        if row:
            # Mark as processing
            cur.execute("""
                UPDATE domain_purchase_jobs
                SET status = 'processing',
                    worker_id = %s,
                    worker_started_at = NOW(),
                    started_at = COALESCE(started_at, NOW())
                WHERE id = %s
            """, (WORKER_ID, row['id']))
            conn.commit()
            return dict(row)
        return None
    finally:
        cur.close()
        conn.close()


def get_pending_inbox_purchase_job() -> Optional[dict]:
    """Get next pending inbox purchase job (worker mode only)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, client_id, workspace_id, provider_type, domain_ids,
                   domain_names, request_data, override_age_check, custom_purchase,
                   retry_count, max_retries
            FROM inbox_purchase_jobs
            WHERE status = 'pending'
            AND worker_mode = 'worker'
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """)
        row = cur.fetchone()
        if row:
            # Mark as processing
            cur.execute("""
                UPDATE inbox_purchase_jobs
                SET status = 'executing',
                    worker_id = %s,
                    worker_started_at = NOW(),
                    started_at = COALESCE(started_at, NOW())
                WHERE id = %s
            """, (WORKER_ID, row['id']))
            conn.commit()
            return dict(row)
        return None
    finally:
        cur.close()
        conn.close()


def reclaim_stale_jobs():
    """Reclaim jobs from crashed workers."""
    stale_threshold = datetime.utcnow() - timedelta(minutes=STALE_JOB_MINUTES)
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Reclaim stale domain purchase jobs
        cur.execute("""
            UPDATE domain_purchase_jobs
            SET status = 'pending',
                worker_id = NULL,
                worker_started_at = NULL,
                retry_count = retry_count + 1
            WHERE status = 'processing'
            AND worker_started_at < %s
            AND retry_count < max_retries
            RETURNING id, domain_names
        """, (stale_threshold,))

        reclaimed_domain = cur.fetchall()
        for row in reclaimed_domain:
            logger.warning(f"Reclaimed stale domain purchase job {row['id']}: {row['domain_names']}")

        # Reclaim stale inbox purchase jobs
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'pending',
                worker_id = NULL,
                worker_started_at = NULL,
                retry_count = retry_count + 1
            WHERE status = 'executing'
            AND execution_mode = 'worker'
            AND worker_started_at < %s
            AND retry_count < max_retries
            RETURNING id, domain_names
        """, (stale_threshold,))

        reclaimed_inbox = cur.fetchall()
        for row in reclaimed_inbox:
            logger.warning(f"Reclaimed stale inbox purchase job {row['id']}: {row['domain_names']}")

        conn.commit()

    finally:
        cur.close()
        conn.close()


# =============================================================================
# Domain Purchase Processing
# =============================================================================

def update_domain_purchase_job(job_id: str, status: str, current_domain: str = None,
                               results: dict = None, error: str = None,
                               successful_count: int = None, failed_count: int = None,
                               total_cost: Decimal = None):
    """Update domain purchase job status."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        updates = ["status = %s"]
        params = [status]

        if current_domain:
            updates.append("current_domain = %s")
            params.append(current_domain)

        if results is not None:
            updates.append("results = %s")
            params.append(Json(results))

        if error:
            updates.append("error_message = %s")
            params.append(error)
            updates.append("errors = COALESCE(errors, '{}') || %s::text[]")
            params.append([error])

        if successful_count is not None:
            updates.append("successful_count = %s")
            params.append(successful_count)

        if failed_count is not None:
            updates.append("failed_count = %s")
            params.append(failed_count)

        if total_cost is not None:
            updates.append("total_cost = %s")
            params.append(float(total_cost))

        if status == 'completed' or status == 'failed':
            updates.append("completed_at = NOW()")

        params.append(job_id)

        cur.execute(f"""
            UPDATE domain_purchase_jobs
            SET {', '.join(updates)}
            WHERE id = %s
        """, params)

        conn.commit()

    finally:
        cur.close()
        conn.close()


async def process_domain_purchase_job(job: dict):
    """Process a domain purchase job via registrar APIs."""
    job_id = str(job['id'])
    registrar = job['registrar']
    domain_ids = job['domain_ids']
    domain_names = job.get('domain_names', [])

    logger.info(f"Processing domain purchase job {job_id}: {len(domain_ids)} domains via {registrar}")

    # Import services
    from services.porkbun import PorkbunService
    from services.dynadot import DynadotService

    # Select service based on registrar
    if registrar == 'dynadot':
        service = DynadotService()
    else:
        service = PorkbunService()

    results = []
    successful_count = 0
    failed_count = 0
    total_cost = Decimal("0")

    try:
        conn = get_db_connection()
        cur = conn.cursor()

        for i, domain_id in enumerate(domain_ids):
            # Get domain info
            cur.execute("SELECT domain_name FROM domains WHERE id = %s", (domain_id,))
            domain_row = cur.fetchone()
            if not domain_row:
                results.append({
                    "domain_id": str(domain_id),
                    "domain": None,
                    "success": False,
                    "error": "Domain not found in database"
                })
                failed_count += 1
                continue

            domain_name = domain_row['domain_name']
            update_domain_purchase_job(job_id, 'processing', current_domain=domain_name)

            logger.info(f"  [{i+1}/{len(domain_ids)}] Purchasing {domain_name} via {registrar}")

            try:
                # Check availability first
                if registrar == 'dynadot':
                    avail = await service.check_availability(domain_name)
                else:
                    avail = await service.check(domain_name)

                if not avail.available:
                    results.append({
                        "domain_id": str(domain_id),
                        "domain": domain_name,
                        "success": False,
                        "error": "Domain no longer available"
                    })
                    failed_count += 1
                    continue

                # Purchase domain
                purchase_result = await service.purchase(domain_name)

                if purchase_result.success:
                    results.append({
                        "domain_id": str(domain_id),
                        "domain": domain_name,
                        "success": True,
                        "order_id": purchase_result.order_id,
                        "price": float(avail.price) if avail.price else None
                    })
                    successful_count += 1
                    if avail.price:
                        total_cost += avail.price

                    # Update domain status
                    cur.execute("""
                        UPDATE domains
                        SET approval_status = 'purchased',
                            purchased_at = NOW(),
                            updated_at = NOW()
                        WHERE id = %s
                    """, (domain_id,))
                    conn.commit()

                    logger.info(f"    ✓ Purchased {domain_name}")
                else:
                    results.append({
                        "domain_id": str(domain_id),
                        "domain": domain_name,
                        "success": False,
                        "error": purchase_result.error or "Purchase failed"
                    })
                    failed_count += 1
                    logger.warning(f"    ✗ Failed to purchase {domain_name}: {purchase_result.error}")

            except Exception as e:
                results.append({
                    "domain_id": str(domain_id),
                    "domain": domain_name,
                    "success": False,
                    "error": str(e)
                })
                failed_count += 1
                logger.error(f"    ✗ Error purchasing {domain_name}: {e}")

        cur.close()
        conn.close()
        await service.close()

        # Update job as completed
        final_status = 'completed' if failed_count == 0 else ('failed' if successful_count == 0 else 'completed')
        update_domain_purchase_job(
            job_id, final_status,
            results=results,
            successful_count=successful_count,
            failed_count=failed_count,
            total_cost=total_cost
        )

        logger.info(f"Domain purchase job {job_id} completed: {successful_count} success, {failed_count} failed")

    except Exception as e:
        logger.error(f"Domain purchase job {job_id} failed: {e}")
        update_domain_purchase_job(job_id, 'failed', error=str(e))


# =============================================================================
# Inbox Purchase Processing (Hypertide)
# =============================================================================

def _import_hypertide_modules():
    """Import HyperTide modules with error handling."""
    try:
        # Add Hypertide to path
        hypertide_path = os.path.join(os.path.dirname(__file__), "Hypertide", "automation", "src")
        if hypertide_path not in sys.path:
            sys.path.insert(0, hypertide_path)

        from hypertide_automation.models import (
            InboxTarget,
            InboxConfig,
            MixedOrderRequest,
            BisonCredentials,
            OrderType,
            OrderRequest,
            SendingTool,
            DomainConfig,
            calculate_optimal_orders,
            create_order_bundle,
        )
        from hypertide_automation.purchase import (
            purchase_mixed_order,
            BundlePurchaseAutomation,
            PurchaseAutomation,
        )
        from hypertide_automation.client import HypertideClient

        return {
            "InboxTarget": InboxTarget,
            "InboxConfig": InboxConfig,
            "MixedOrderRequest": MixedOrderRequest,
            "BisonCredentials": BisonCredentials,
            "OrderType": OrderType,
            "DomainConfig": DomainConfig,
            "OrderRequest": OrderRequest,
            "SendingTool": SendingTool,
            "calculate_optimal_orders": calculate_optimal_orders,
            "create_order_bundle": create_order_bundle,
            "purchase_mixed_order": purchase_mixed_order,
            "BundlePurchaseAutomation": BundlePurchaseAutomation,
            "PurchaseAutomation": PurchaseAutomation,
            "HypertideClient": HypertideClient,
        }
    except ImportError as e:
        logger.warning(f"HyperTide modules not available: {e}")
        return None


def update_inbox_purchase_job(job_id: str, status: str, current_step: str = None,
                              results: dict = None, error: str = None):
    """Update inbox purchase job status."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        updates = ["status = %s"]
        params = [status]

        if current_step:
            updates.append("current_step = %s")
            params.append(current_step)

        if results is not None:
            updates.append("results = %s")
            params.append(Json(results))

        if error:
            updates.append("errors = COALESCE(errors, '{}') || %s::text[]")
            params.append([error])

        if status == 'completed' or status == 'failed':
            updates.append("completed_at = NOW()")

        params.append(job_id)

        cur.execute(f"""
            UPDATE inbox_purchase_jobs
            SET {', '.join(updates)}
            WHERE id = %s
        """, params)

        conn.commit()

    finally:
        cur.close()
        conn.close()


async def process_inbox_purchase_job(job: dict):
    """
    Process an inbox purchase job by sending Slack specification.

    NOTE: Browser automation was disabled due to:
    1. Session isolation - order state only exists in headless browser
    2. Stripe bot detection - cannot capture checkout URL
    3. Non-shareable URLs - user's browser has different session

    Flow:
    1. Extract all order variables from job
    2. Generate detailed Slack specification message
    3. Send to Slack with "Open Hypertide" and "Mark Complete" buttons
    4. Set job status to 'awaiting_manual_order'
    5. User manually creates order in Hypertide using the specification
    6. User clicks "Mark as Completed" in Slack → status becomes 'completed'
    """
    job_id = str(job['id'])
    client_id = str(job.get('client_id', ''))
    provider_type = job.get('provider_type', 'entra')
    domain_names = job.get('domain_names', [])
    request_data = job.get('request_data', {})

    # Get client name for notifications
    client_name = _get_client_name(client_id) if client_id else request_data.get('client_name', 'Unknown')

    logger.info(f"Processing inbox purchase job {job_id} for {client_name}")
    logger.info(f"  Provider: {provider_type}, Domains: {len(domain_names)}")
    logger.info(f"  Mode: Slack specification (manual order)")

    try:
        # Generate and send Slack specification message
        slack_msg = _generate_slack_order_specification(job, client_name)
        success = _send_slack_notification(slack_msg)

        if success:
            # Update job to awaiting manual completion
            update_inbox_purchase_job(
                job_id, 'awaiting_manual_order',
                current_step="Slack specification sent - awaiting manual order",
                results={
                    "provider_type": provider_type,
                    "domain_count": len(domain_names),
                    "specification_sent": True,
                }
            )
            logger.info(f"Slack specification sent for job {job_id}")
        else:
            # Slack notification failed - mark job for retry or manual handling
            update_inbox_purchase_job(
                job_id, 'failed',
                current_step="Failed to send Slack specification",
                error="Slack webhook failed - check SLACK_ORDERS_WEBHOOK_URL configuration"
            )
            logger.error(f"Failed to send Slack specification for job {job_id}")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Inbox purchase job {job_id} failed with exception: {error_msg}")
        update_inbox_purchase_job(job_id, 'failed', error=error_msg)


# =============================================================================
# Main Worker Loop
# =============================================================================

import asyncio

async def run_worker():
    """Main worker loop."""
    logger.info(f"Hypertide Worker starting (ID: {WORKER_ID})")
    logger.info(f"  Poll interval: {POLL_INTERVAL}s")
    logger.info(f"  Stale job threshold: {STALE_JOB_MINUTES} minutes")

    last_stale_check = datetime.utcnow()
    stale_check_interval = timedelta(minutes=5)

    while True:
        try:
            # Periodically reclaim stale jobs
            if datetime.utcnow() - last_stale_check > stale_check_interval:
                reclaim_stale_jobs()
                last_stale_check = datetime.utcnow()

            # Priority 1: Domain purchase jobs (faster, API-based)
            job = get_pending_domain_purchase_job()
            if job:
                await process_domain_purchase_job(job)
                continue  # Check for more work immediately

            # Priority 2: Inbox purchase jobs (slower, browser automation)
            job = get_pending_inbox_purchase_job()
            if job:
                await process_inbox_purchase_job(job)
                continue

            # No work found, sleep
            await asyncio.sleep(POLL_INTERVAL)

        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(POLL_INTERVAL)


def main():
    """Entry point."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker shutting down")


if __name__ == "__main__":
    main()
