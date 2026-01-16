"""
Strategy Generation Worker

Polls the database for pending strategy generation jobs and spawns
Claude Code to generate email campaign variants using the Cold Email Skill v2.0.

The worker runs autonomously - Claude Code has full permission to call MCP tools
without human approval during execution. Human review happens on the frontend.

Usage:
    python strategy_worker.py

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    POLL_INTERVAL (default: 5 seconds)
    CLAUDE_ACCOUNT (default: ClaudeCodeMax - which Claude Code profile to use)
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
CLAUDE_ACCOUNT = os.getenv("CLAUDE_ACCOUNT", "ClaudeCodeMax")

# Path to this project (for MCP config)
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def ensure_tables():
    """Ensure the strategy generation tables exist."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            -- Strategy generation jobs
            CREATE TABLE IF NOT EXISTS strategy_generation_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES clients(id),
                submission_id UUID REFERENCES client_onboarding_submissions(id),
                status VARCHAR(50) DEFAULT 'pending',
                generation_round INTEGER DEFAULT 1,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_strategy_jobs_status
                ON strategy_generation_jobs(status);
            CREATE INDEX IF NOT EXISTS idx_strategy_jobs_client
                ON strategy_generation_jobs(client_id);

            -- Strategy suggestions
            CREATE TABLE IF NOT EXISTS strategy_suggestions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
                client_id UUID NOT NULL REFERENCES clients(id),
                variant_number INTEGER NOT NULL,
                subject_line TEXT NOT NULL,
                email_body TEXT NOT NULL,
                score INTEGER,
                rationale TEXT,
                used_variables JSONB,
                missing_variables JSONB,
                campaign_type VARCHAR(50),
                status VARCHAR(50) DEFAULT 'pending',
                human_comment TEXT,
                reviewed_by VARCHAR(255),
                reviewed_at TIMESTAMP,
                generation_round INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_suggestions_job ON strategy_suggestions(job_id);
            CREATE INDEX IF NOT EXISTS idx_suggestions_client ON strategy_suggestions(client_id);
            CREATE INDEX IF NOT EXISTS idx_suggestions_status ON strategy_suggestions(status);

            -- Revision requests
            CREATE TABLE IF NOT EXISTS strategy_revision_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_id UUID NOT NULL REFERENCES strategy_generation_jobs(id),
                client_id UUID NOT NULL REFERENCES clients(id),
                variant_id UUID REFERENCES strategy_suggestions(id),
                instruction TEXT NOT NULL,
                processed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_revision_requests_job ON strategy_revision_requests(job_id);
            CREATE INDEX IF NOT EXISTS idx_revision_requests_client ON strategy_revision_requests(client_id);
        """)
        conn.commit()
        logger.info("Strategy generation tables ready")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def get_pending_job():
    """Get the next pending strategy generation job to process."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get and lock a pending job
        cur.execute("""
            UPDATE strategy_generation_jobs
            SET status = 'processing', started_at = NOW()
            WHERE id = (
                SELECT id FROM strategy_generation_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, client_id, submission_id, generation_round
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
            UPDATE strategy_generation_jobs
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
    """Process a strategy generation job by spawning Claude Code."""
    job_id = str(job["id"])
    client_id = str(job["client_id"])
    submission_id = str(job["submission_id"]) if job.get("submission_id") else None
    generation_round = job.get("generation_round", 1)

    logger.info(f"Processing strategy job {job_id} for client {client_id} (round {generation_round})")

    # Build the Claude Code command
    # The skill will load the Cold Email Skill v2.0 and generate variants
    prompt = f"/generate-strategy client_id={client_id} job_id={job_id}"
    if submission_id:
        prompt += f" submission_id={submission_id}"

    cmd = [
        "claude",
        "-p", prompt,
        "--dangerously-skip-permissions",  # Allow MCP tool calls without confirmation
        "--mcp-config", os.path.join(PROJECT_PATH, "strategy_mcp_config.json"),
    ]

    # Add profile selection if not using default
    if CLAUDE_ACCOUNT and CLAUDE_ACCOUNT != "default":
        cmd.extend(["--profile", CLAUDE_ACCOUNT])

    try:
        logger.info(f"Running Claude Code: {' '.join(cmd)}")

        # Run Claude Code with full autonomy
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
            logger.info(f"Strategy job {job_id} completed successfully")
            # Job status should be updated by complete_job tool in MCP

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out")
        mark_job_failed(job_id, "Generation timed out after 5 minutes")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])


def run_worker():
    """Main worker loop."""
    logger.info("Strategy Generation Worker starting...")
    logger.info(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    logger.info(f"Poll interval: {POLL_INTERVAL} seconds")
    logger.info(f"Claude account: {CLAUDE_ACCOUNT}")

    # Ensure tables exist
    ensure_tables()

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
