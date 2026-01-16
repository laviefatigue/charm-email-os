"""
Strategy Generation Worker - Prefect Flow

Prefect-based worker that processes strategy generation jobs by spawning
Claude Code to generate email campaign variants using the Cold Email Skill v2.0.

Deploy to Prefect server for centralized monitoring and triggering.

Usage:
    # Run locally for testing
    python strategy_worker_prefect.py

    # Deploy to Prefect
    prefect deploy --all

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    CLAUDE_ACCOUNT (default: ClaudeCodeMax - which Claude Code profile to use)
    PREFECT_API_URL (your Prefect server URL)
"""
import os
import subprocess
import logging
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from prefect import flow, task, get_run_logger
from prefect.blocks.system import Secret

# Database configuration - loaded from environment or Prefect blocks
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

CLAUDE_ACCOUNT = os.getenv("CLAUDE_ACCOUNT", "ClaudeCodeMax")
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))

# Docker mode: run Claude Code inside claudebox container
USE_DOCKER = os.getenv("USE_DOCKER", "false").lower() == "true"
CLAUDEBOX_PROJECT = os.getenv("CLAUDEBOX_PROJECT", "charm-email-os")


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


@task(name="ensure-strategy-tables", retries=2, retry_delay_seconds=5)
def ensure_tables():
    """Ensure the strategy generation tables exist."""
    logger = get_run_logger()
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            -- Strategy generation jobs
            CREATE TABLE IF NOT EXISTS strategy_generation_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES clients(id),
                submission_id UUID,
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
        return True
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


@task(name="get-pending-job")
def get_pending_job() -> Optional[dict]:
    """Get the next pending strategy generation job to process."""
    logger = get_run_logger()
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

        if job:
            logger.info(f"Found pending job: {job['id']}")
        else:
            logger.info("No pending jobs found")

        return dict(job) if job else None
    except Exception as e:
        logger.error(f"Failed to get pending job: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


@task(name="get-all-pending-jobs")
def get_all_pending_jobs() -> list[dict]:
    """Get all pending strategy generation jobs."""
    logger = get_run_logger()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        cur.execute("""
            SELECT id, client_id, submission_id, generation_round, created_at
            FROM strategy_generation_jobs
            WHERE status = 'pending'
            ORDER BY created_at ASC
        """)
        jobs = cur.fetchall()
        logger.info(f"Found {len(jobs)} pending jobs")
        return [dict(j) for j in jobs]
    except Exception as e:
        logger.error(f"Failed to get pending jobs: {e}")
        return []
    finally:
        cur.close()
        conn.close()


@task(name="mark-job-processing")
def mark_job_processing(job_id: str) -> bool:
    """Mark a job as processing."""
    logger = get_run_logger()
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE strategy_generation_jobs
            SET status = 'processing', started_at = NOW()
            WHERE id = %s AND status = 'pending'
        """, (job_id,))
        affected = cur.rowcount
        conn.commit()

        if affected > 0:
            logger.info(f"Marked job {job_id} as processing")
            return True
        else:
            logger.warning(f"Job {job_id} not found or already processing")
            return False
    except Exception as e:
        logger.error(f"Failed to mark job processing: {e}")
        conn.rollback()
        return False
    finally:
        cur.close()
        conn.close()


@task(name="mark-job-failed")
def mark_job_failed(job_id: str, error: str):
    """Mark a job as failed."""
    logger = get_run_logger()
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE strategy_generation_jobs
            SET status = 'failed', error_message = %s, completed_at = NOW()
            WHERE id = %s
        """, (error, job_id))
        conn.commit()
        logger.error(f"Marked job {job_id} as failed: {error}")
    except Exception as e:
        logger.error(f"Failed to mark job as failed: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


@task(name="run-claude-code", timeout_seconds=300, retries=1)
def run_claude_code(job_id: str, client_id: str, submission_id: Optional[str], generation_round: int) -> bool:
    """Run Claude Code to generate strategy variants.

    Supports two execution modes:
    - Direct: Run claude CLI directly (local dev or when CLI installed on host)
    - Docker: Run the charm-strategy-ai container (VPS deployment)

    Set USE_DOCKER=true environment variable to use Docker mode.
    """
    logger = get_run_logger()

    logger.info(f"Processing strategy job {job_id} for client {client_id} (round {generation_round})")
    logger.info(f"Execution mode: {'Docker (charm-strategy-ai)' if USE_DOCKER else 'Direct'}")

    if USE_DOCKER:
        # Docker mode: run the purpose-built charm-strategy-ai container
        # Container includes Claude Code CLI, strategy skill, and MCP server
        cmd = [
            "docker", "run", "--rm",
            # Pass database credentials as environment variables
            "-e", f"POSTGRES_HOST={DB_CONFIG['host']}",
            "-e", f"POSTGRES_PORT={DB_CONFIG['port']}",
            "-e", f"POSTGRES_DB={DB_CONFIG['database']}",
            "-e", f"POSTGRES_USER={DB_CONFIG['user']}",
            "-e", f"POSTGRES_PASSWORD={DB_CONFIG['password']}",
            # Mount Claude credentials from host (persisted after initial auth)
            "-v", "/root/.claude:/root/.claude",
            # Container image
            "charm-strategy-ai:latest",
            # Arguments: client_id, job_id, [submission_id]
            client_id,
            job_id,
        ]

        # Add optional submission_id
        if submission_id:
            cmd.append(submission_id)

        # Environment for subprocess (inherit current env)
        env_vars = os.environ.copy()

    else:
        # Direct mode: run claude CLI directly
        prompt = f"/generate-strategy client_id={client_id} job_id={job_id}"
        if submission_id:
            prompt += f" submission_id={submission_id}"

        cmd = [
            "claude",
            "-p", prompt,
            "--dangerously-skip-permissions",
            "--mcp-config", os.path.join(PROJECT_PATH, "strategy_mcp_config.json"),
        ]

        # Add profile selection if not using default
        if CLAUDE_ACCOUNT and CLAUDE_ACCOUNT != "default":
            cmd.extend(["--profile", CLAUDE_ACCOUNT])

        # Environment variables for database connection (passed to MCP server)
        env_vars = {
            **os.environ,
            "POSTGRES_HOST": DB_CONFIG["host"],
            "POSTGRES_PORT": str(DB_CONFIG["port"]),
            "POSTGRES_DB": DB_CONFIG["database"],
            "POSTGRES_USER": DB_CONFIG["user"],
            "POSTGRES_PASSWORD": DB_CONFIG["password"],
        }

    try:
        logger.info(f"Running command: {' '.join(cmd)}")

        # Run Claude Code with full autonomy
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=PROJECT_PATH,
            env=env_vars
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Claude Code failed: {error_msg}")
            mark_job_failed(job_id, error_msg[:500])
            return False
        else:
            logger.info(f"Strategy job {job_id} completed successfully")
            # Log output for debugging
            if result.stdout:
                logger.info(f"Claude output: {result.stdout[:500]}")
            return True

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out")
        mark_job_failed(job_id, "Generation timed out after 5 minutes")
        return False

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])
        return False


@flow(name="process-single-strategy-job", log_prints=True)
def process_single_job(job_id: str, client_id: str, submission_id: Optional[str] = None, generation_round: int = 1):
    """
    Process a single strategy generation job.

    Use this flow to process a specific job by ID (e.g., triggered from API).

    Args:
        job_id: UUID of the job to process
        client_id: UUID of the client
        submission_id: Optional UUID of the onboarding submission
        generation_round: Which generation round this is
    """
    logger = get_run_logger()
    logger.info(f"Starting single job processing: {job_id}")

    # Mark as processing first
    if not mark_job_processing(job_id):
        logger.warning(f"Could not mark job {job_id} as processing - may already be processing")

    # Run Claude Code
    success = run_claude_code(job_id, client_id, submission_id, generation_round)

    return {"job_id": job_id, "success": success}


@flow(name="process-pending-strategy-jobs", log_prints=True)
def process_pending_jobs(max_jobs: int = 10):
    """
    Process all pending strategy generation jobs.

    This flow finds all pending jobs and processes them sequentially.
    Use max_jobs to limit how many are processed in a single run.

    Args:
        max_jobs: Maximum number of jobs to process in this run
    """
    logger = get_run_logger()

    # Ensure tables exist
    ensure_tables()

    # Get pending jobs
    pending = get_all_pending_jobs()

    if not pending:
        logger.info("No pending jobs to process")
        return {"processed": 0, "results": []}

    # Limit to max_jobs
    to_process = pending[:max_jobs]
    logger.info(f"Will process {len(to_process)} of {len(pending)} pending jobs")

    results = []
    for job in to_process:
        job_id = str(job["id"])
        client_id = str(job["client_id"])
        submission_id = str(job["submission_id"]) if job.get("submission_id") else None
        generation_round = job.get("generation_round", 1)

        # Mark as processing
        if mark_job_processing(job_id):
            # Run Claude Code
            success = run_claude_code(job_id, client_id, submission_id, generation_round)
            results.append({"job_id": job_id, "success": success})
        else:
            results.append({"job_id": job_id, "success": False, "reason": "Could not lock job"})

    return {
        "processed": len(results),
        "successful": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
        "results": results
    }


@flow(name="strategy-generation-poll", log_prints=True)
def poll_for_jobs(poll_interval: int = 30, max_iterations: int = 100):
    """
    Continuous polling flow for strategy generation jobs.

    Polls for pending jobs at regular intervals. Use this for scheduled
    continuous processing.

    Args:
        poll_interval: Seconds between polls (default: 30)
        max_iterations: Maximum poll iterations before stopping (default: 100)
    """
    import time

    logger = get_run_logger()
    logger.info(f"Starting poll loop: interval={poll_interval}s, max_iterations={max_iterations}")

    # Ensure tables exist
    ensure_tables()

    total_processed = 0

    for i in range(max_iterations):
        logger.info(f"Poll iteration {i+1}/{max_iterations}")

        # Try to get and process a pending job
        job = get_pending_job()

        if job:
            job_id = str(job["id"])
            client_id = str(job["client_id"])
            submission_id = str(job["submission_id"]) if job.get("submission_id") else None
            generation_round = job.get("generation_round", 1)

            success = run_claude_code(job_id, client_id, submission_id, generation_round)
            total_processed += 1

            if success:
                logger.info(f"Processed job {job_id} successfully")
            else:
                logger.warning(f"Job {job_id} failed")
        else:
            # No jobs, wait before next poll
            logger.info(f"No pending jobs, waiting {poll_interval}s...")
            time.sleep(poll_interval)

    logger.info(f"Poll loop complete. Processed {total_processed} jobs.")
    return {"total_processed": total_processed, "iterations": max_iterations}


# Entry point for local testing
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "poll":
        # Run polling mode
        poll_for_jobs(poll_interval=30, max_iterations=100)
    else:
        # Default: process pending jobs once
        result = process_pending_jobs(max_jobs=10)
        print(f"Result: {result}")
