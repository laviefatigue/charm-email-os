"""
Purchase Worker - Hypertide Inbox Purchase Daemon

Polls the database for pending purchase jobs (worker_mode='worker') and spawns
hypertide_playwright.py to execute each purchase via browser automation on Hypertide.

Usage:
    # Normal daemon mode (polls for jobs):
    python purchase_worker.py

    # Single job mode (process one job and exit):
    python purchase_worker.py --single-job <JOB_ID>

    # Stop after a specific step (for testing):
    python purchase_worker.py --single-job <JOB_ID> --stop-after-step 4

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    POLL_INTERVAL (default: 10 seconds)
    JOB_TIMEOUT (default: 600 - seconds before a job times out)
    JOB_COOLDOWN (default: 30 - seconds between jobs)
"""
import os
import sys
import time
import subprocess
import logging
import json
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "10"))
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "600"))  # 10 minutes
JOB_COOLDOWN = int(os.getenv("JOB_COOLDOWN", "30"))  # seconds between jobs
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")

# Path to this project (for script location)
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))
PLAYWRIGHT_SCRIPT = os.path.join(PROJECT_PATH, "hypertide_playwright.py")


def send_alert(title: str, message: str, level: str = "error"):
    """Send alert via webhook (Discord/Slack compatible)."""
    if not ALERT_WEBHOOK_URL:
        logger.warning(f"ALERT (no webhook configured): {title} - {message}")
        return

    color_map = {"error": 15158332, "warning": 16776960, "info": 3447003}

    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": color_map.get(level, 3447003),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Purchase Worker"}
        }]
    }

    try:
        req = Request(
            ALERT_WEBHOOK_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        urlopen(req, timeout=10)
        logger.info(f"Alert sent: {title}")
    except URLError as e:
        logger.error(f"Failed to send alert: {e}")


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def ensure_tables():
    """Ensure the purchase jobs tables exist with worker columns."""
    conn = get_db()
    cur = conn.cursor()

    try:
        # Ensure worker columns exist
        worker_columns = [
            ("hypertide_email", "TEXT"),
            ("hypertide_password", "TEXT"),
            ("company_name", "TEXT"),
            ("forwarding_domain", "TEXT"),
            ("bison_username", "TEXT"),
            ("bison_password", "TEXT"),
            ("bison_workspace_name", "TEXT"),
            ("bison_url", "TEXT DEFAULT 'https://spellcast.hirecharm.com'"),
            ("bison_api_key", "TEXT"),
            ("sender_names", "JSONB"),
            ("use_saved_payment", "BOOLEAN DEFAULT TRUE"),
            ("order_count", "INTEGER DEFAULT 1"),
            ("worker_mode", "VARCHAR(20) DEFAULT 'api'"),
            ("hypertide_order_id", "TEXT"),
            ("error_type", "TEXT"),
            ("checkout_url", "TEXT"),
        ]

        for col_name, col_def in worker_columns:
            try:
                cur.execute(f"""
                    ALTER TABLE inbox_purchase_jobs
                    ADD COLUMN IF NOT EXISTS {col_name} {col_def}
                """)
            except Exception:
                pass  # Column already exists

        # Add purchase lock columns to domains table
        domain_lock_columns = [
            ("purchase_job_id", "UUID REFERENCES inbox_purchase_jobs(id)"),
            ("purchase_job_status", "TEXT"),
        ]
        for col_name, col_def in domain_lock_columns:
            try:
                cur.execute(f"""
                    ALTER TABLE domains
                    ADD COLUMN IF NOT EXISTS {col_name} {col_def}
                """)
            except Exception:
                pass  # Column already exists

        # Create partial index for worker polling
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_purchase_jobs_worker_pending
            ON inbox_purchase_jobs(status, worker_mode)
            WHERE status = 'pending' AND worker_mode = 'worker'
        """)

        # Create audit table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS purchase_job_steps (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_id UUID NOT NULL REFERENCES inbox_purchase_jobs(id) ON DELETE CASCADE,
                step_name TEXT NOT NULL,
                screenshot_base64 TEXT,
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_purchase_steps_job
                ON purchase_job_steps(job_id, created_at);
        """)

        conn.commit()
        logger.info("Purchase tables ready")
    except Exception as e:
        logger.error(f"Failed to ensure tables: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def get_pending_job():
    """Get the next pending purchase job to process (worker_mode='worker' only)."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'processing', started_at = NOW()
            WHERE id = (
                SELECT id FROM inbox_purchase_jobs
                WHERE status = 'pending' AND worker_mode = 'worker'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, client_id, provider_type, domain_names, company_name
        """)
        job = cur.fetchone()
        if job:
            # Sync domain lock status so UI shows correct state
            cur.execute("""
                UPDATE domains SET purchase_job_status = 'processing'
                WHERE purchase_job_id = %s
            """, (str(job['id']),))
        conn.commit()
        return job
    except Exception as e:
        logger.error(f"Failed to get pending job: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def cleanup_stale_jobs():
    """On startup, fail any jobs stuck in 'processing'/'executing' from a previous worker run.

    If the worker crashed mid-job, those jobs are stuck forever.
    This recovers them by marking as failed with error_type='stale'.
    """
    logger.info("Checking for stale jobs from previous run...")
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'failed',
                error_type = 'stale',
                current_step = 'worker_crashed',
                completed_at = NOW(),
                errors = COALESCE(errors, ARRAY[]::TEXT[]) ||
                    ARRAY['Worker restarted while job was processing. Last step: ' || COALESCE(current_step, 'unknown')]
            WHERE status IN ('processing', 'executing')
              AND worker_mode = 'worker'
            RETURNING id, current_step
        """)
        stale_jobs = cur.fetchall()

        for job in stale_jobs:
            cur.execute("""
                UPDATE domains SET purchase_job_status = 'failed'
                WHERE purchase_job_id = %s
            """, (str(job['id']),))
            logger.warning(f"Recovered stale job {job['id']} (was at step: {job.get('current_step', 'unknown')})")

        conn.commit()
        if stale_jobs:
            logger.info(f"Cleaned up {len(stale_jobs)} stale job(s) from previous run")
        else:
            logger.info("No stale jobs found")
    except Exception as e:
        logger.error(f"Failed to clean up stale jobs: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def mark_job_failed(job_id: str, error: str, error_type: str = "system"):
    """Mark a job as failed with a categorized error type."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'failed',
                error_type = %s,
                current_step = 'worker_error',
                completed_at = NOW()
            WHERE id = %s
        """, (error_type, job_id))

        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET errors = COALESCE(errors, ARRAY[]::TEXT[]) || ARRAY[%s]
            WHERE id = %s
        """, (error, job_id))

        # Sync domain lock status so UI shows correct state
        cur.execute("""
            UPDATE domains SET purchase_job_status = 'failed'
            WHERE purchase_job_id = %s::uuid
        """, (job_id,))

        conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark job as failed: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def process_job(job: dict, stop_after_step: int = None):
    """Process a purchase job by spawning hypertide_playwright.py.

    Args:
        job: Job dict with id, client_id, provider_type, domain_names, company_name
        stop_after_step: If set, pass --stop-after to the script (1-12).
    """
    job_id = str(job["id"])
    company_name = job.get("company_name", "Unknown")
    provider_type = job.get("provider_type", "entra")
    domain_names = job.get("domain_names", [])

    logger.info(f"Processing job {job_id} for {company_name} ({provider_type}, {len(domain_names)} domains)")
    if stop_after_step:
        logger.info(f"TEST MODE: Will stop after step {stop_after_step}")

    cmd = [
        sys.executable, PLAYWRIGHT_SCRIPT,
        "--job-id", job_id,
    ]

    if stop_after_step:
        cmd.extend(["--stop-after", str(stop_after_step)])

    try:
        logger.info(f"Spawning Playwright script for job {job_id}...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=JOB_TIMEOUT,
            cwd=PROJECT_PATH,
            env={
                **os.environ,
                "POSTGRES_HOST": DB_CONFIG["host"],
                "POSTGRES_PORT": str(DB_CONFIG["port"]),
                "POSTGRES_DB": DB_CONFIG["database"],
                "POSTGRES_USER": DB_CONFIG["user"],
                "POSTGRES_PASSWORD": DB_CONFIG["password"],
            }
        )

        if result.returncode != 0:
            # Guard: check if the script already handled the status transition
            # (e.g., fail_job() or handoff_checkout() was called before exit)
            try:
                guard_conn = get_db()
                guard_cur = guard_conn.cursor(cursor_factory=RealDictCursor)
                guard_cur.execute("SELECT status FROM inbox_purchase_jobs WHERE id = %s", (job_id,))
                current = guard_cur.fetchone()
                guard_cur.close()
                guard_conn.close()

                if current and current['status'] in ('awaiting_checkout', 'failed', 'completed'):
                    logger.info(f"Job {job_id} already at '{current['status']}'. Ignoring non-zero exit.")
                    return
            except Exception as e:
                logger.warning(f"Status guard check failed: {e}")

            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Script failed: {error_msg[:500]}")
            mark_job_failed(job_id, error_msg[:500], "system")
        else:
            logger.info(f"Job {job_id} completed (exit 0)")
            if result.stdout:
                logger.debug(f"Output: {result.stdout[:500]}")

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out after {JOB_TIMEOUT}s")
        mark_job_failed(job_id, f"Purchase timed out after {JOB_TIMEOUT} seconds", "timeout")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500], "system")


def get_job_by_id(job_id: str) -> dict:
    """Get a specific purchase job by ID (regardless of status).

    Used by --single-job mode for testing.
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT id, client_id, provider_type, domain_names, company_name
            FROM inbox_purchase_jobs WHERE id = %s
        """, (job_id,))
        job = cur.fetchone()
        if not job:
            logger.error(f"Job {job_id} not found")
            return None
        return job
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        return None
    finally:
        cur.close()
        conn.close()


def run_single_job(job_id: str, stop_after_step: int = None):
    """Process a single job by ID and exit.

    Used for local testing. Does not poll or loop.

    Args:
        job_id: The UUID of the job to process
        stop_after_step: If set, stop execution after this step (1-12)
    """
    logger.info(f"Single job mode: processing {job_id}")
    if stop_after_step:
        logger.info(f"Will stop after step {stop_after_step}")

    # Ensure tables exist
    ensure_tables()

    # Get the job
    job = get_job_by_id(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in database")
        sys.exit(1)

    logger.info(f"Job found: {job['company_name']} ({job['provider_type']}, {len(job.get('domain_names', []))} domains)")

    # Mark as processing
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'processing', started_at = NOW()
            WHERE id = %s
        """, (job_id,))
        conn.commit()
    finally:
        cur.close()
        conn.close()

    # Process the job
    process_job(job, stop_after_step=stop_after_step)

    logger.info(f"Single job {job_id} processing complete. Exiting.")


def run_worker():
    """Main worker loop.

    Persistent daemon that polls for pending purchase jobs (worker_mode='worker').
    For each job, spawns hypertide_playwright.py to execute the Hypertide purchase flow.
    """
    logger.info("Purchase Worker starting...")
    logger.info(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    logger.info(f"Poll interval: {POLL_INTERVAL} seconds")
    logger.info(f"Job timeout: {JOB_TIMEOUT} seconds")
    logger.info(f"Job cooldown: {JOB_COOLDOWN} seconds")
    logger.info(f"Alert webhook: {'configured' if ALERT_WEBHOOK_URL else 'not configured'}")
    logger.info(f"Playwright script: {PLAYWRIGHT_SCRIPT}")

    # Ensure tables exist
    ensure_tables()

    # Recover any jobs stuck in 'processing' from a previous run
    cleanup_stale_jobs()

    logger.info("Worker ready - polling for purchase jobs...")

    while True:
        try:
            # Get next pending job
            job = get_pending_job()

            if job:
                process_job(job)
                # Cooldown between jobs to avoid hammering Hypertide
                if JOB_COOLDOWN > 0:
                    logger.info(f"Job cooldown: waiting {JOB_COOLDOWN}s before next poll...")
                    time.sleep(JOB_COOLDOWN)
            else:
                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            break

        except Exception as e:
            logger.error(f"Worker error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Purchase Worker - Hypertide Inbox Purchase Daemon"
    )
    parser.add_argument(
        "--single-job",
        type=str,
        metavar="JOB_ID",
        help="Process a single job by UUID and exit (no polling loop)"
    )
    parser.add_argument(
        "--stop-after-step",
        type=int,
        metavar="N",
        help="Stop execution after step N (1-12). For testing only."
    )
    args = parser.parse_args()

    if args.stop_after_step and not args.single_job:
        parser.error("--stop-after-step requires --single-job")

    if args.single_job:
        run_single_job(args.single_job, args.stop_after_step)
    else:
        run_worker()
