"""
Domain Generation Worker

Polls the database for pending domain generation jobs and spawns
Claude Code to generate suggestions using the domain MCP server.

Usage:
    python domain_worker.py

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    POLL_INTERVAL (default: 5 seconds)
"""
import os
import sys
import time
import subprocess
import logging
from datetime import datetime
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

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))

# Path to this project (for MCP config)
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def ensure_jobs_table():
    """Ensure the domain_generation_jobs table exists."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS domain_generation_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES clients(id),
                count INTEGER DEFAULT 10,
                status VARCHAR(50) DEFAULT 'pending',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_domain_jobs_status
                ON domain_generation_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_domain_jobs_client
                ON domain_generation_jobs(client_id);
        """)
        conn.commit()
        logger.info("Domain generation jobs table ready")
    except Exception as e:
        logger.error(f"Failed to create jobs table: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def get_pending_job():
    """Get the next pending job to process."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get and lock a pending job
        cur.execute("""
            UPDATE domain_generation_jobs
            SET status = 'processing', started_at = NOW()
            WHERE id = (
                SELECT id FROM domain_generation_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, client_id, count
        """)
        job = cur.fetchone()
        conn.commit()
        return job
    except Exception as e:
        logger.error(f"Failed to get pending job: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def mark_job_failed(job_id: str, error: str):
    """Mark a job as failed."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE domain_generation_jobs
            SET status = 'failed', error_message = %s, completed_at = NOW()
            WHERE id = %s
        """, (error, job_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark job as failed: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def process_job(job: dict):
    """Process a domain generation job by spawning Claude Code."""
    job_id = str(job["id"])
    client_id = str(job["client_id"])
    count = job.get("count", 10)

    logger.info(f"Processing job {job_id} for client {client_id} (count={count})")

    # Build the Claude Code command
    # The skill will be loaded and executed with the parameters
    prompt = f"/generate-domain-suggestions client_id={client_id} job_id={job_id} count={count}"

    cmd = [
        "claude",
        "-p", prompt,
        "--dangerously-skip-permissions",  # Allow MCP tool calls
        "--mcp-config", os.path.join(PROJECT_PATH, "mcp_config.json"),
    ]

    try:
        logger.info(f"Running Claude Code: {' '.join(cmd)}")

        # Run Claude Code
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
            cwd=PROJECT_PATH,
            env={
                **os.environ,
                # Pass database config to MCP server
                "POSTGRES_HOST": DB_CONFIG["host"],
                "POSTGRES_PORT": str(DB_CONFIG["port"]),
                "POSTGRES_DB": DB_CONFIG["database"],
                "POSTGRES_USER": DB_CONFIG["user"],
                "POSTGRES_PASSWORD": DB_CONFIG["password"],
            }
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Claude Code failed: {error_msg}")
            mark_job_failed(job_id, error_msg[:500])
        else:
            logger.info(f"Job {job_id} completed successfully")
            # Job status should be updated by complete_job tool in MCP

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out")
        mark_job_failed(job_id, "Generation timed out after 5 minutes")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])


def run_worker():
    """Main worker loop."""
    logger.info("Domain Generation Worker starting...")
    logger.info(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    logger.info(f"Poll interval: {POLL_INTERVAL} seconds")

    # Ensure tables exist
    ensure_jobs_table()

    while True:
        try:
            # Get next pending job
            job = get_pending_job()

            if job:
                process_job(job)
            else:
                # No pending jobs, wait before polling again
                time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            break

        except Exception as e:
            logger.error(f"Worker error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run_worker()
