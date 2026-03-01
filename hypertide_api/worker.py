#!/usr/bin/env python3
"""
Hypertide API Worker

Processes inbox purchase jobs via REST API (not browser automation).

Features:
- Uses Hypertide REST API for order creation
- Comprehensive duplicate detection (DB + pending jobs + API)
- No automatic retries (manual retry via UI/Slack)
- Slack notifications for started/failed/completed
- Database job persistence with row-level locking

Usage:
    python -m hypertide_api.worker

Environment Variables:
    HYPERTIDE_API_KEY           - Hypertide API key (required)
    POSTGRES_HOST/PORT/DB/USER/PASSWORD - Database connection
    SLACK_ORDERS_WEBHOOK_URL    - Slack webhook for notifications
    POLL_INTERVAL               - Seconds between job checks (default: 10)
    WORKER_ID                   - Worker identifier (default: hostname)
"""

import os
import sys
import socket
import logging
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import RealDictCursor, Json

from .client import HypertideAPIClient, HypertideAPIError
from .models import (
    PlanType,
    OrderStatus,
    FailureReason,
    SingleOrderRequest,
    BisonCredentials,
    InboxUser,
    OrderResult,
    PLAN_SPECS,
    group_domains_for_orders,
)
from .service import HypertideOrderService, DuplicateCheckResult
from .notifications import SlackNotifier, create_slack_notifier


# Configure logging with structured format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(funcName)s] %(message)s'
)
logger = logging.getLogger("hypertide_api_worker")


# =============================================================================
# Configuration
# =============================================================================

class WorkerConfig:
    """Worker configuration from environment."""

    def __init__(self):
        # Database
        self.db_host = os.getenv("POSTGRES_HOST", "localhost")
        self.db_port = int(os.getenv("POSTGRES_PORT", "5432"))
        self.db_name = os.getenv("POSTGRES_DB", "postgres")
        self.db_user = os.getenv("POSTGRES_USER", "postgres")
        self.db_password = os.getenv("POSTGRES_PASSWORD", "")

        # Worker
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "10"))
        self.worker_id = os.getenv("WORKER_ID", f"api-worker-{socket.gethostname()}")
        self.stale_job_minutes = int(os.getenv("STALE_JOB_MINUTES", "30"))

        # Hypertide API
        self.hypertide_api_key = os.getenv("HYPERTIDE_API_KEY", "")

        # Slack
        self.slack_webhook_url = os.getenv("SLACK_ORDERS_WEBHOOK_URL", "")

        # App URLs
        self.hypertide_app_url = os.getenv("HYPERTIDE_APP_URL", "https://app2.hypertide.io")
        self.charm_api_url = os.getenv("CHARM_API_URL", "https://api.charmemailos.com")

    @property
    def db_config(self) -> dict:
        return {
            "host": self.db_host,
            "port": self.db_port,
            "database": self.db_name,
            "user": self.db_user,
            "password": self.db_password,
        }

    def validate(self) -> list[str]:
        """Validate required configuration. Returns list of missing items."""
        missing = []
        if not self.hypertide_api_key:
            missing.append("HYPERTIDE_API_KEY")
        if not self.db_password:
            missing.append("POSTGRES_PASSWORD")
        return missing


config = WorkerConfig()


# =============================================================================
# Logging Helpers
# =============================================================================

def log_job(job_id: str, level: str, message: str, **kwargs):
    """Structured logging with job context."""
    extra = " | ".join(f"{k}={v}" for k, v in kwargs.items()) if kwargs else ""
    full_msg = f"[job={job_id[:8]}] {message}"
    if extra:
        full_msg += f" | {extra}"
    getattr(logger, level)(full_msg)


# =============================================================================
# Database Operations
# =============================================================================

def get_db_connection():
    """Create a database connection."""
    return psycopg2.connect(**config.db_config, cursor_factory=RealDictCursor)


def get_pending_job() -> Optional[dict]:
    """
    Get next pending inbox purchase job with row-level locking.

    Uses FOR UPDATE SKIP LOCKED to prevent concurrent processing.
    Only gets jobs with worker_mode = 'api'.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get and lock the job atomically
        cur.execute("""
            SELECT id, client_id, workspace_id, provider_type, domain_ids,
                   domain_names, request_data, override_age_check, custom_purchase,
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
            job_id = str(row['id'])
            log_job(job_id, "info", "Claimed job", worker=config.worker_id)

            # Mark as executing with worker info
            cur.execute("""
                UPDATE inbox_purchase_jobs
                SET status = 'executing',
                    current_step = 'Claimed by worker',
                    worker_id = %s,
                    worker_started_at = NOW(),
                    started_at = COALESCE(started_at, NOW())
                WHERE id = %s
            """, (config.worker_id, row['id']))

            # Also update domain statuses
            cur.execute("""
                UPDATE domains
                SET purchase_job_status = 'executing'
                WHERE purchase_job_id = %s
            """, (row['id'],))

            conn.commit()
            return dict(row)

        return None

    except Exception as e:
        logger.error(f"Error getting pending job: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def check_domains_exist_in_db(domains: list[str]) -> list[str]:
    """Check which domains already have infrastructure in database."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT domain_name
            FROM domains
            WHERE domain_name = ANY(%s)
            AND infrastructure_type IS NOT NULL
        """, (domains,))
        return [row['domain_name'] for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()


def check_domains_in_pending_jobs(domains: list[str], exclude_job_id: Optional[str] = None) -> list[str]:
    """Check which domains are in pending or executing jobs (excluding current job)."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        query = """
            SELECT DISTINCT unnest(domain_names) as domain_name
            FROM inbox_purchase_jobs
            WHERE status IN ('pending', 'executing')
            AND domain_names && %s
        """
        params = [domains]

        if exclude_job_id:
            query += " AND id != %s"
            params.append(exclude_job_id)

        cur.execute(query, params)
        found = [row['domain_name'] for row in cur.fetchall() if row['domain_name'] in domains]
        return found
    finally:
        cur.close()
        conn.close()


def update_job_status(
    job_id: str,
    status: str,
    current_step: Optional[str] = None,
    results: Optional[dict] = None,
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    orders_completed: Optional[int] = None,
    total_inboxes: Optional[int] = None,
    api_response: Optional[dict] = None,
):
    """Update inbox purchase job status with full logging."""
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

        if error_type:
            updates.append("error_type = %s")
            params.append(error_type)

        if orders_completed is not None:
            updates.append("orders_completed = %s")
            params.append(orders_completed)

        if total_inboxes is not None:
            updates.append("total_inboxes = %s")
            params.append(total_inboxes)

        # Store full API response for debugging
        if api_response is not None:
            updates.append("api_response = %s")
            params.append(Json(api_response))

        if status in ('completed', 'failed'):
            updates.append("completed_at = NOW()")

        params.append(job_id)

        cur.execute(f"""
            UPDATE inbox_purchase_jobs
            SET {', '.join(updates)}
            WHERE id = %s
        """, params)

        # Update domain status
        cur.execute("""
            UPDATE domains
            SET purchase_job_status = %s
            WHERE purchase_job_id = %s
        """, (status, job_id))

        conn.commit()

        log_job(job_id, "info", f"Status updated to {status}")

    except Exception as e:
        logger.error(f"Error updating job {job_id}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def get_client_name(client_id: str) -> str:
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


def get_bison_credentials_from_db(workspace_id: str) -> Optional[BisonCredentials]:
    """Get EmailBison credentials from workspace settings."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                bison_username,
                bison_password,
                bison_workspace,
                bison_url,
                bison_api_key
            FROM workspaces
            WHERE id = %s
        """, (workspace_id,))
        row = cur.fetchone()
        if row and row.get('bison_username'):
            return BisonCredentials(
                username=row['bison_username'],
                password=row['bison_password'],
                workspace=row['bison_workspace'],
                bison_url=row.get('bison_url') or "https://spellcast.hirecharm.com",
                api_key=row.get('bison_api_key') or "",
            )
        return None
    finally:
        cur.close()
        conn.close()


# =============================================================================
# Job Processing
# =============================================================================

async def process_job(job: dict, slack: SlackNotifier):
    """
    Process an inbox purchase job via API.

    Flow:
    1. Parse and validate job data
    2. Check for duplicates (DB + pending jobs + API)
    3. Send Slack "started" notification
    4. Create order via Hypertide API
    5. Verify order was created
    6. Send Slack "completed" or "failed" notification
    7. Update job status with full details
    """
    job_id = str(job['id'])
    client_id = str(job.get('client_id', ''))
    provider_type = job.get('provider_type', 'entra')
    domain_names = job.get('domain_names', [])
    request_data = job.get('request_data', {})
    workspace_id = job.get('workspace_id')

    # Get client name
    client_name = get_client_name(client_id) if client_id else request_data.get('client_name', 'Unknown')

    log_job(job_id, "info", "Processing job",
            client=client_name,
            provider=provider_type,
            domains=len(domain_names))

    log_job(job_id, "info", f"Domains: {', '.join(domain_names)}")

    try:
        # =====================================================================
        # Phase 1: Validate inputs
        # =====================================================================
        log_job(job_id, "info", "Phase 1: Validating inputs")
        update_job_status(job_id, 'executing', current_step='Validating inputs')

        plan = PlanType(provider_type) if provider_type in ('entra', 'google') else PlanType.ENTRA

        # Get Bison credentials
        bison_creds = None
        if workspace_id:
            bison_creds = get_bison_credentials_from_db(str(workspace_id))
            if bison_creds:
                log_job(job_id, "info", "Loaded Bison credentials from workspace")

        if not bison_creds:
            bison_creds = BisonCredentials(
                username=request_data.get('bison_username', ''),
                password=request_data.get('bison_password', ''),
                workspace=request_data.get('bison_workspace', ''),
                bison_url=request_data.get('bison_url', 'https://spellcast.hirecharm.com'),
            )

        if not bison_creds.username or not bison_creds.password:
            error_msg = "Missing Bison credentials - cannot create order"
            log_job(job_id, "error", error_msg)
            raise ValueError(error_msg)

        # =====================================================================
        # Phase 2: Check for duplicates
        # =====================================================================
        log_job(job_id, "info", "Phase 2: Checking for duplicates")
        update_job_status(job_id, 'executing', current_step='Checking for duplicate domains')

        # Check 1: Domains with existing infrastructure
        db_existing = check_domains_exist_in_db(domain_names)
        if db_existing:
            log_job(job_id, "warning", f"Found {len(db_existing)} domains with existing infrastructure",
                    domains=db_existing)

        # Check 2: Domains in pending/executing jobs
        db_pending = check_domains_in_pending_jobs(domain_names, exclude_job_id=job_id)
        if db_pending:
            log_job(job_id, "warning", f"Found {len(db_pending)} domains in other pending jobs",
                    domains=db_pending)

        # Check 3: Domains in Hypertide API
        api_existing = []
        async with HypertideAPIClient(api_key=config.hypertide_api_key, job_id=job_id) as client:
            remaining = [d for d in domain_names if d not in db_existing and d not in db_pending]
            log_job(job_id, "info", f"Checking {len(remaining)} domains via Hypertide API")

            for domain in remaining:
                try:
                    has_active, _ = await client.check_domain_has_active_order(domain)
                    if has_active:
                        api_existing.append(domain)
                        log_job(job_id, "warning", f"Domain {domain} exists in Hypertide API")
                except HypertideAPIError as e:
                    if e.status_code != 404:
                        log_job(job_id, "error", f"API check failed for {domain}: {e}")

        all_duplicates = list(set(db_existing + db_pending + api_existing))
        if all_duplicates:
            error_msg = f"Duplicate domains found: {', '.join(all_duplicates)}"
            if db_pending:
                error_msg += f" (domains in pending jobs: {', '.join(db_pending)})"

            log_job(job_id, "error", "Order blocked due to duplicates",
                    db_existing=len(db_existing),
                    db_pending=len(db_pending),
                    api_existing=len(api_existing))

            update_job_status(
                job_id, 'failed',
                current_step='Blocked: duplicate domains',
                error=error_msg,
                error_type='domain_conflict',
            )

            # Send failure notification
            await _send_failure_notification(
                slack, job_id, client_name, plan, domain_names, error_msg, "domain_conflict"
            )
            return

        # =====================================================================
        # Phase 3: Send "started" notification
        # =====================================================================
        log_job(job_id, "info", "Phase 3: Sending started notification")
        update_job_status(job_id, 'executing', current_step='Sending started notification')

        await _send_started_notification(slack, job_id, client_name, plan, domain_names)

        # =====================================================================
        # Phase 4: Create order via API
        # =====================================================================
        log_job(job_id, "info", "Phase 4: Creating order via Hypertide API")
        update_job_status(job_id, 'executing', current_step='Calling Hypertide API')

        # Build order request
        sender_names = request_data.get('sender_names', [])
        users = []
        for sn in sender_names:
            if isinstance(sn, dict) and sn.get('firstName') and sn.get('lastName'):
                users.append(InboxUser(first_name=sn['firstName'], last_name=sn['lastName']))

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

        # Execute order
        async with HypertideOrderService(
            api_key=config.hypertide_api_key,
            check_db_duplicates=False,  # Already checked
            check_pending_jobs=False,
            check_api_duplicates=False,
            verify_orders=True,
        ) as service:
            service._client.job_id = job_id
            result = await service.create_single_order(order_request)

        # =====================================================================
        # Phase 5: Process result
        # =====================================================================
        log_job(job_id, "info", "Phase 5: Processing result",
                success=result.success,
                inboxes=result.inboxes_created)

        if result.success:
            update_job_status(
                job_id, 'completed',
                current_step='Order created successfully',
                results={
                    'hypertide_order_ids': result.hypertide_order_ids,
                    'inboxes_created': result.inboxes_created,
                    'monthly_cost': result.monthly_cost,
                    'nameservers': result.nameservers,
                    'domains': domain_names,
                },
                orders_completed=1,
                total_inboxes=result.inboxes_created,
            )

            await _send_completed_notification(
                slack, job_id, client_name, plan, domain_names, result
            )

            log_job(job_id, "info", "Job completed successfully",
                    inboxes=result.inboxes_created,
                    cost=f"${result.monthly_cost}/mo")

        else:
            error_msg = result.error_message or "Unknown error"
            error_type = result.failure_reason.value if result.failure_reason else "unknown"

            update_job_status(
                job_id, 'failed',
                current_step='Order creation failed',
                error=error_msg,
                error_type=error_type,
            )

            await _send_failure_notification(
                slack, job_id, client_name, plan, domain_names, error_msg, error_type
            )

            log_job(job_id, "error", "Job failed",
                    error_type=error_type,
                    error_message=error_msg)

    except Exception as e:
        error_msg = str(e)
        log_job(job_id, "error", f"Job failed with exception: {error_msg}")
        logger.exception(f"[job={job_id[:8]}] Full traceback:")

        update_job_status(
            job_id, 'failed',
            current_step='Processing failed with exception',
            error=error_msg,
            error_type='unknown',
        )

        await _send_failure_notification(
            slack, job_id, client_name,
            PlanType(provider_type) if provider_type in ('entra', 'google') else PlanType.ENTRA,
            domain_names, error_msg, 'unknown'
        )


# =============================================================================
# Slack Notification Helpers
# =============================================================================

async def _send_started_notification(
    slack: SlackNotifier,
    job_id: str,
    client_name: str,
    plan: PlanType,
    domains: list[str],
):
    """Send order started notification to Slack."""
    try:
        # Build minimal request for notification
        request = SingleOrderRequest(
            order_id=UUID(job_id),
            job_id=UUID(job_id),
            client_id=UUID('00000000-0000-0000-0000-000000000000'),
            client_name=client_name,
            plan=plan,
            domains=domains,
            forwarding_domain="",
            bison_credentials=BisonCredentials(username="", password="", workspace=""),
        )
        await slack.notify_order_started(request, client_name)
    except Exception as e:
        log_job(job_id, "warning", f"Failed to send started notification: {e}")


async def _send_completed_notification(
    slack: SlackNotifier,
    job_id: str,
    client_name: str,
    plan: PlanType,
    domains: list[str],
    result: OrderResult,
):
    """Send order completed notification to Slack."""
    try:
        request = SingleOrderRequest(
            order_id=UUID(job_id),
            job_id=UUID(job_id),
            client_id=UUID('00000000-0000-0000-0000-000000000000'),
            client_name=client_name,
            plan=plan,
            domains=domains,
            forwarding_domain="",
            bison_credentials=BisonCredentials(username="", password="", workspace=""),
        )
        await slack.notify_order_completed(request, result, client_name)
    except Exception as e:
        log_job(job_id, "warning", f"Failed to send completed notification: {e}")


async def _send_failure_notification(
    slack: SlackNotifier,
    job_id: str,
    client_name: str,
    plan: PlanType,
    domains: list[str],
    error_message: str,
    error_type: str,
):
    """Send order failed notification to Slack."""
    try:
        request = SingleOrderRequest(
            order_id=UUID(job_id),
            job_id=UUID(job_id),
            client_id=UUID('00000000-0000-0000-0000-000000000000'),
            client_name=client_name,
            plan=plan,
            domains=domains,
            forwarding_domain="",
            bison_credentials=BisonCredentials(username="", password="", workspace=""),
        )

        result = OrderResult(
            order_id=UUID(job_id),
            success=False,
            plan=plan,
            domains=domains,
            error_message=error_message,
            failure_reason=FailureReason(error_type) if error_type in [e.value for e in FailureReason] else FailureReason.UNKNOWN,
        )

        await slack.notify_order_failed(request, result, client_name, job_id=UUID(job_id))
    except Exception as e:
        log_job(job_id, "warning", f"Failed to send failure notification: {e}")


# =============================================================================
# Main Worker Loop
# =============================================================================

async def run_worker():
    """Main worker loop."""
    # Validate configuration
    missing = config.validate()
    if missing:
        logger.error(f"Missing required configuration: {', '.join(missing)}")
        sys.exit(1)

    logger.info(f"Hypertide API Worker starting")
    logger.info(f"  Worker ID: {config.worker_id}")
    logger.info(f"  Poll interval: {config.poll_interval}s")
    logger.info(f"  API endpoint: https://backend.hypertide.io/api/v1")

    # Initialize Slack notifier
    slack = create_slack_notifier(config.slack_webhook_url)
    if slack.enabled:
        logger.info(f"  Slack notifications: enabled")
    else:
        logger.warning(f"  Slack notifications: disabled (no webhook URL)")

    # Test database connection
    try:
        conn = get_db_connection()
        conn.close()
        logger.info(f"  Database: connected to {config.db_host}:{config.db_port}/{config.db_name}")
    except Exception as e:
        logger.error(f"  Database: connection failed - {e}")
        sys.exit(1)

    logger.info("Worker ready, entering main loop")

    while True:
        try:
            # Get next job (with row-level locking)
            job = get_pending_job()

            if job:
                await process_job(job, slack)
            else:
                # No work, sleep
                await asyncio.sleep(config.poll_interval)

        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            logger.exception("Full traceback:")
            await asyncio.sleep(config.poll_interval)


def main():
    """Entry point."""
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker shutting down (SIGINT)")


if __name__ == "__main__":
    main()
