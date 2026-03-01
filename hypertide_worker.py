#!/usr/bin/env python3
"""
Hypertide Worker - External worker for domain purchases and inbox provisioning.

Processes three job types:
1. domain_purchase_jobs - Purchase domains from Dynadot/Porkbun registrars
2. inbox_purchase_jobs (worker_mode='worker') - Send Slack specification for manual order
3. inbox_purchase_jobs (worker_mode='api') - Automated order via Hypertide REST API

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
    HYPERTIDE_API_KEY - Required for API mode orders
    PORKBUN_API_KEY, PORKBUN_API_SECRET
    DYNADOT_API_KEY
"""

import os
import sys
import time
import socket
import logging
import json
import asyncio
import httpx
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Add the api directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api'))

# Import Hypertide API client (for API mode orders)
try:
    from hypertide_api.client import HypertideAPIClient, HypertideAPIError
    from hypertide_api.models import (
        PlanType,
        BisonCredentials,
        InboxUser,
        SingleOrderRequest,
        PLAN_SPECS,
    )
    from hypertide_api.service import HypertideOrderService
    HYPERTIDE_API_AVAILABLE = True
except ImportError as e:
    HYPERTIDE_API_AVAILABLE = False
    print(f"Warning: hypertide_api package not available: {e}")

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
HYPERTIDE_API_KEY = os.getenv("HYPERTIDE_API_KEY", "")

# Default EmailBison credentials (used when workspace doesn't have specific creds)
EMAILBISON_USERNAME = os.getenv("EMAILBISON_USERNAME", "")
EMAILBISON_PASSWORD = os.getenv("EMAILBISON_PASSWORD", "")
EMAILBISON_API_URL = os.getenv("EMAILBISON_API_URL", "https://spellcast.hirecharm.com")

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
    request_data = job.get('request_data') or {}  # Handle NULL from DB

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
            SELECT id, client_id, workspace_id,
                   domain_ids::text[] as domain_ids,
                   domain_names::text[] as domain_names,
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
    """Get next pending inbox purchase job (worker mode only - sends Slack spec)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, client_id, workspace_id, provider_type,
                   domain_ids::text[] as domain_ids,
                   domain_names::text[] as domain_names,
                   request_data, override_age_check, custom_purchase,
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


def get_pending_inbox_purchase_job_api() -> Optional[dict]:
    """Get next pending inbox purchase job (API mode - automated via REST API)."""
    if not HYPERTIDE_API_AVAILABLE:
        return None
    if not HYPERTIDE_API_KEY:
        return None

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, client_id, workspace_id, provider_type,
                   domain_ids::text[] as domain_ids,
                   domain_names::text[] as domain_names,
                   request_data, override_age_check, custom_purchase,
                   retry_count, max_retries
            FROM inbox_purchase_jobs
            WHERE status = 'pending'
            AND worker_mode = 'api'
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
                    current_step = 'Claimed by API worker',
                    worker_id = %s,
                    worker_started_at = NOW(),
                    started_at = COALESCE(started_at, NOW())
                WHERE id = %s
            """, (WORKER_ID, row['id']))
            conn.commit()
            logger.info(f"API job claimed: {row['id']}")
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
    """Process a domain purchase job via registrar APIs.

    IMPORTANT: This function performs FRESH price checks at purchase time to ensure
    we always buy from the cheapest registrar. The registrar field in the job is
    ignored - we compare real-time prices from BOTH registrars for each domain.
    """
    job_id = str(job['id'])
    domain_ids = job['domain_ids']
    domain_names = job.get('domain_names', [])

    logger.info(f"Processing domain purchase job {job_id}: {len(domain_ids)} domains (will check both registrars for best price)")

    # Import services
    from services.porkbun import PorkbunService
    from services.dynadot import DynadotService

    # Initialize BOTH services - we'll check prices from both before deciding
    porkbun_service = PorkbunService()
    dynadot_service = DynadotService()

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

            logger.info(f"  [{i+1}/{len(domain_ids)}] Checking FRESH prices for {domain_name}")

            try:
                # ===== FRESH PRICE CHECK FROM BOTH REGISTRARS =====
                # Check Dynadot first (fast, no rate limits)
                dynadot_result = await dynadot_service.check_availability(domain_name)
                dynadot_price = dynadot_result.price if dynadot_result.available else None
                logger.info(f"    Dynadot: {'$' + str(dynadot_price) if dynadot_price else 'unavailable'}")

                # Check Porkbun (slower due to rate limits)
                # Add delay to respect Porkbun's rate limit (~1 request per 10 seconds)
                await asyncio.sleep(10)
                porkbun_result = await porkbun_service.check_availability(domain_name)
                porkbun_price = porkbun_result.price if porkbun_result.available else None
                logger.info(f"    Porkbun: {'$' + str(porkbun_price) if porkbun_price else 'unavailable'}")

                # ===== SELECT CHEAPEST REGISTRAR =====
                chosen_registrar = None
                chosen_service = None
                chosen_price = None

                if dynadot_price is not None and porkbun_price is not None:
                    # Both available - pick cheapest
                    if porkbun_price < dynadot_price:
                        chosen_registrar = 'porkbun'
                        chosen_service = porkbun_service
                        chosen_price = porkbun_price
                    else:
                        chosen_registrar = 'dynadot'
                        chosen_service = dynadot_service
                        chosen_price = dynadot_price
                elif dynadot_price is not None:
                    chosen_registrar = 'dynadot'
                    chosen_service = dynadot_service
                    chosen_price = dynadot_price
                elif porkbun_price is not None:
                    chosen_registrar = 'porkbun'
                    chosen_service = porkbun_service
                    chosen_price = porkbun_price
                else:
                    # Neither available
                    results.append({
                        "domain_id": str(domain_id),
                        "domain": domain_name,
                        "success": False,
                        "error": "Domain not available at either registrar"
                    })
                    failed_count += 1
                    continue

                logger.info(f"    → Best price: ${chosen_price} via {chosen_registrar}")

                # ===== EXECUTE PURCHASE =====
                # Porkbun requires price parameter, Dynadot does not
                if chosen_registrar == 'porkbun':
                    purchase_result = await chosen_service.purchase(domain_name, price=chosen_price)
                else:
                    purchase_result = await chosen_service.purchase(domain_name)

                if purchase_result.success:
                    results.append({
                        "domain_id": str(domain_id),
                        "domain": domain_name,
                        "success": True,
                        "order_id": purchase_result.order_id,
                        "price": float(chosen_price),
                        "registrar": chosen_registrar
                    })
                    successful_count += 1
                    total_cost += chosen_price

                    # Update domain with ACTUAL registrar and price used
                    cur.execute("""
                        UPDATE domains
                        SET approval_status = 'purchased',
                            purchased_at = NOW(),
                            selected_provider = %s,
                            cached_price = %s,
                            porkbun_price = %s,
                            dynadot_price = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (chosen_registrar, float(chosen_price),
                          float(porkbun_price) if porkbun_price else None,
                          float(dynadot_price) if dynadot_price else None,
                          domain_id))
                    conn.commit()

                    logger.info(f"    ✓ Purchased {domain_name} for ${chosen_price} via {chosen_registrar}")
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
        await porkbun_service.close()
        await dynadot_service.close()

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
# Inbox Purchase Processing (Hypertide API Mode)
# =============================================================================

def _get_bison_credentials_from_workspace(workspace_id: str) -> Optional[dict]:
    """Get EmailBison credentials from workspace settings."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                bison_username,
                bison_password,
                workspace_name as bison_workspace,
                bison_url,
                bison_api_key
            FROM workspaces
            WHERE id = %s
        """, (workspace_id,))
        row = cur.fetchone()
        if row and row.get('bison_username'):
            return dict(row)
        return None
    finally:
        cur.close()
        conn.close()


def _get_workspace_name(workspace_id: str) -> str:
    """Get workspace name from database."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT workspace_name FROM workspaces WHERE id = %s", (workspace_id,))
        row = cur.fetchone()
        return row['workspace_name'] if row else "Unknown"
    finally:
        cur.close()
        conn.close()


async def process_inbox_purchase_job_api(job: dict):
    """
    Process an inbox purchase job via Hypertide REST API.

    This is the automated flow - no manual intervention required.
    Creates the order directly via the Hypertide API.
    """
    job_id = str(job['id'])
    client_id = str(job.get('client_id', ''))
    provider_type = job.get('provider_type', 'entra')
    domain_names = job.get('domain_names', [])
    request_data = job.get('request_data') or {}
    workspace_id = job.get('workspace_id')

    # Get client name for notifications
    client_name = _get_client_name(client_id) if client_id else request_data.get('client_name', 'Unknown')

    logger.info(f"Processing inbox purchase job {job_id} via API for {client_name}")
    logger.info(f"  Provider: {provider_type}, Domains: {len(domain_names)}")
    logger.info(f"  Domains: {', '.join(domain_names)}")

    # Calculate order details for notifications
    inboxes_per_domain = 50 if provider_type == 'entra' else 3
    total_inboxes = len(domain_names) * inboxes_per_domain
    domains_per_order = 2 if provider_type == 'entra' else 5
    order_count = max(1, (len(domain_names) + domains_per_order - 1) // domains_per_order)
    monthly_cost = order_count * 50

    # Send "Order Initiated" Slack notification
    _send_slack_notification({
        "attachments": [{
            "color": "#3498db",  # Blue - order started
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "🚀 HyperTide Order Initiated", "emoji": True}
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Client:* {client_name}\n*Provider:* {provider_type.upper()}\n*Domains:* {len(domain_names)}\n*Expected Inboxes:* {total_inboxes}\n*Est. Cost:* ${monthly_cost}/mo"
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
                    "elements": [{"type": "mrkdwn", "text": f"Job ID: `{job_id[:8]}...` | Processing via Hypertide REST API"}]
                }
            ]
        }],
        "text": f"HyperTide order initiated for {client_name}"
    })

    try:
        # Phase 1: Validate inputs
        update_inbox_purchase_job(job_id, 'executing', current_step='Validating inputs')

        plan = PlanType(provider_type) if provider_type in ('entra', 'google') else PlanType.ENTRA

        # Get Bison credentials from workspace or request_data
        bison_creds = None
        if workspace_id:
            ws_creds = _get_bison_credentials_from_workspace(str(workspace_id))
            if ws_creds and ws_creds.get('bison_username'):
                bison_creds = BisonCredentials(
                    username=ws_creds['bison_username'],
                    password=ws_creds['bison_password'],
                    workspace=ws_creds['bison_workspace'],
                    bison_url=ws_creds.get('bison_url') or "https://spellcast.hirecharm.com",
                    api_key=ws_creds.get('bison_api_key') or "",
                )
                logger.info(f"  Loaded Bison credentials from workspace")

        if not bison_creds:
            # Try request_data first
            bison_creds = BisonCredentials(
                username=request_data.get('bison_username', ''),
                password=request_data.get('bison_password', ''),
                workspace=request_data.get('bison_workspace', ''),
                bison_url=request_data.get('bison_url', EMAILBISON_API_URL),
            )

        # Fallback to environment variables if still missing
        if not bison_creds.username or not bison_creds.password:
            if EMAILBISON_USERNAME and EMAILBISON_PASSWORD:
                # Get workspace name from database
                ws_name = _get_workspace_name(str(workspace_id)) if workspace_id else client_name
                bison_creds = BisonCredentials(
                    username=EMAILBISON_USERNAME,
                    password=EMAILBISON_PASSWORD,
                    workspace=ws_name,
                    bison_url=EMAILBISON_API_URL,
                )
                logger.info(f"  Using default Bison credentials from environment")
            else:
                error_msg = "Missing Bison credentials - cannot create order"
                logger.error(f"  {error_msg}")
                update_inbox_purchase_job(job_id, 'failed', error=error_msg)
                return

        # Phase 2: Build order request
        update_inbox_purchase_job(job_id, 'executing', current_step='Building order request')

        sender_names = request_data.get('sender_names', [])
        users = []
        for sn in sender_names:
            if isinstance(sn, dict) and sn.get('firstName') and sn.get('lastName'):
                users.append(InboxUser(first_name=sn['firstName'], last_name=sn['lastName']))

        # Default to Chris Booth if no sender names provided
        if not users:
            users = [InboxUser(first_name='Chris', last_name='Booth')]

        forwarding_domain = request_data.get('forwarding_domain', '')
        if not forwarding_domain and domain_names:
            parts = domain_names[0].split('.')
            if len(parts) >= 2:
                forwarding_domain = '.'.join(parts[-2:])

        order_request = SingleOrderRequest(
            job_id=UUID(job_id),
            client_id=UUID(client_id),
            client_name=client_name,
            plan=plan,
            domains=domain_names,
            forwarding_domain=forwarding_domain,
            bison_credentials=bison_creds,
            users=users,
        )

        # Phase 3: Create order via Hypertide API
        update_inbox_purchase_job(job_id, 'executing', current_step='Calling Hypertide API')
        logger.info(f"  Creating order via Hypertide API...")

        async with HypertideOrderService(
            api_key=HYPERTIDE_API_KEY,
            check_db_duplicates=False,
            check_pending_jobs=False,
            check_api_duplicates=True,  # Check if domain exists in Hypertide
            verify_orders=True,
        ) as service:
            service._client.job_id = job_id
            result = await service.create_single_order(order_request)

        # Phase 4: Process result
        if result.success:
            logger.info(f"  ✓ Order created successfully!")
            logger.info(f"    Inboxes created: {result.inboxes_created}")
            logger.info(f"    Order IDs: {result.hypertide_order_ids}")

            update_inbox_purchase_job(
                job_id, 'completed',
                current_step='Order created successfully',
                results={
                    'hypertide_order_ids': result.hypertide_order_ids,
                    'inboxes_created': result.inboxes_created,
                    'monthly_cost': result.monthly_cost,
                    'nameservers': result.nameservers,
                    'domains': domain_names,
                }
            )

            # Update domains with infrastructure_type
            conn = get_db_connection()
            try:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE domains
                    SET infrastructure_type = %s,
                        purchase_job_status = 'completed',
                        updated_at = NOW()
                    WHERE domain_name = ANY(%s)
                """, (provider_type, domain_names))
                conn.commit()
            finally:
                cur.close()
                conn.close()

            # Send success Slack notification
            _send_slack_notification({
                "attachments": [{
                    "color": "#36a64f",  # Green
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "✅ HyperTide Order Complete", "emoji": True}
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Client:* {client_name}\n*Provider:* {provider_type.upper()}\n*Domains:* {len(domain_names)}\n*Inboxes Created:* {result.inboxes_created}"
                            }
                        }
                    ]
                }],
                "text": f"HyperTide order completed for {client_name}"
            })

        else:
            error_msg = result.error_message or "Unknown error"
            logger.error(f"  ✗ Order failed: {error_msg}")

            update_inbox_purchase_job(
                job_id, 'failed',
                current_step='Order failed',
                error=error_msg,
            )

            # Send failure Slack notification
            _send_slack_notification({
                "attachments": [{
                    "color": "#ff0000",  # Red
                    "blocks": [
                        {
                            "type": "header",
                            "text": {"type": "plain_text", "text": "❌ HyperTide Order Failed", "emoji": True}
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"*Client:* {client_name}\n*Provider:* {provider_type.upper()}\n*Domains:* {len(domain_names)}\n*Error:* {error_msg}"
                            }
                        }
                    ]
                }],
                "text": f"HyperTide order failed for {client_name}"
            })

    except HypertideAPIError as e:
        error_msg = f"Hypertide API error: {e.message} ({e.error_type.value})"
        logger.error(f"  ✗ {error_msg}")
        update_inbox_purchase_job(job_id, 'failed', error=error_msg)

        _send_slack_notification({
            "attachments": [{
                "color": "#ff0000",
                "blocks": [
                    {"type": "header", "text": {"type": "plain_text", "text": "❌ HyperTide API Error"}},
                    {"type": "section", "text": {"type": "mrkdwn", "text": f"*Client:* {client_name}\n*Error:* {error_msg}"}}
                ]
            }]
        })

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Inbox purchase job {job_id} (API mode) failed with exception: {error_msg}")
        update_inbox_purchase_job(job_id, 'failed', error=error_msg)


# =============================================================================
# Main Worker Loop
# =============================================================================

async def run_worker():
    """Main worker loop."""
    logger.info(f"Hypertide Worker starting (ID: {WORKER_ID})")
    logger.info(f"  Poll interval: {POLL_INTERVAL}s")
    logger.info(f"  Stale job threshold: {STALE_JOB_MINUTES} minutes")
    logger.info(f"  Hypertide API: {'enabled' if HYPERTIDE_API_KEY else 'disabled (no API key)'}")

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

            # Priority 2: Inbox purchase jobs - API mode (automated via REST API)
            job = get_pending_inbox_purchase_job_api()
            if job:
                await process_inbox_purchase_job_api(job)
                continue

            # Priority 3: Inbox purchase jobs - Worker mode (sends Slack spec)
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
