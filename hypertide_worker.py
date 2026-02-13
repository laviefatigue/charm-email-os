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
            AND execution_mode = 'worker'
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
            DomainConfig,
            calculate_optimal_orders,
            create_order_bundle,
        )
        from hypertide_automation.purchase import (
            purchase_mixed_order,
            BundlePurchaseAutomation,
        )
        from hypertide_automation.client import HypertideClient

        return {
            "InboxTarget": InboxTarget,
            "InboxConfig": InboxConfig,
            "MixedOrderRequest": MixedOrderRequest,
            "BisonCredentials": BisonCredentials,
            "OrderType": OrderType,
            "DomainConfig": DomainConfig,
            "calculate_optimal_orders": calculate_optimal_orders,
            "create_order_bundle": create_order_bundle,
            "purchase_mixed_order": purchase_mixed_order,
            "BundlePurchaseAutomation": BundlePurchaseAutomation,
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
    """Process an inbox purchase job via Hypertide."""
    job_id = str(job['id'])
    request_data = job.get('request_data', {})

    logger.info(f"Processing inbox purchase job {job_id}")

    ht = _import_hypertide_modules()
    if not ht:
        update_inbox_purchase_job(job_id, 'failed', error="HyperTide modules not available")
        return

    try:
        update_inbox_purchase_job(job_id, 'executing', current_step="Initializing Hypertide")

        # This is a simplified implementation - the full implementation would
        # mirror the logic in inbox_purchasing.py's _execute_purchase_v2_task
        #
        # For now, we mark it as needing the full implementation

        logger.warning(f"Inbox purchase job {job_id} - full Hypertide integration pending")
        update_inbox_purchase_job(
            job_id, 'failed',
            error="Worker Hypertide integration not yet implemented - use API background tasks"
        )

    except Exception as e:
        logger.error(f"Inbox purchase job {job_id} failed: {e}")
        update_inbox_purchase_job(job_id, 'failed', error=str(e))


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
