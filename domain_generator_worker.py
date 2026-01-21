"""
Domain Generation Worker

Polls the database for pending domain generation jobs and spawns
Claude Code to generate domain suggestions using the Generate Domain Suggestions skill.

The worker runs autonomously - Claude Code has full permission to call MCP tools
without human approval during execution. Human review happens on the frontend.

Usage:
    python domain_generator_worker.py

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

# Skill file path - skill content is embedded in prompt because -p mode doesn't auto-load skills
SKILL_FILE = os.path.join(PROJECT_PATH, ".claude", "skills", "generate-domain-suggestions.md")


def load_skill_content() -> str:
    """Load skill instructions to embed in prompt.

    Claude Code's -p (prompt) mode doesn't auto-load skills from ~/.claude/skills/,
    so we must embed the skill content directly in the prompt.
    """
    try:
        with open(SKILL_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Skill file not found: {SKILL_FILE}")
        raise
    except Exception as e:
        logger.error(f"Failed to load skill file: {e}")
        raise


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def ensure_tables():
    """Ensure the domain generation tables exist."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            -- Domain generation jobs
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
                ON domain_generation_jobs(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_domain_jobs_client
                ON domain_generation_jobs(client_id);
        """)
        conn.commit()
        logger.info("Domain generation tables ready")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def get_pending_job():
    """Get the next pending domain generation job to process."""
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


def process_job(job: dict, skill_content: str):
    """Process a domain generation job by spawning Claude Code.

    Args:
        job: Job dict with id, client_id, count
        skill_content: Pre-loaded skill instructions to embed in prompt
    """
    job_id = str(job["id"])
    client_id = str(job["client_id"])
    count = job.get("count", 10)

    logger.info(f"Processing domain job {job_id} for client {client_id} (count={count})")

    # Build prompt with embedded skill content
    prompt = f"""You are generating domain name suggestions for a client. Follow these instructions exactly:

{skill_content}

---

NOW EXECUTE THE TASK WITH THESE PARAMETERS:
- client_id: {client_id}
- job_id: {job_id}
- count: {count}

IMPORTANT - TLD POLICY:
Only generate domains with these TLDs: .com, .co, .info
Any other TLD (like .io, .ai, .xyz) will be REJECTED by the MCP server.

Execute these steps:
1. Call get_client_context with the client_id to understand:
   - The client's business (name, industry, product)
   - Their primary_domain or domain_pattern (use this as the base for generation)
   - Existing domains (avoid duplicates)
   - Denied domains (avoid similar patterns)
2. Extract the base name from the client's primary_domain (e.g., "selery" from "selery.com")
3. Generate {count} domain suggestions based on that base name:
   - Use prefixes: try, get, use, go, hire, meet, join, with, hey, run
   - Use suffixes: hq, app, hub, team, mail, inbox, send, reach, now, pro
   - Include pure brand variations with different TLDs
4. For each domain suggestion, call save_domain_suggestion with:
   - job_id="{job_id}"
   - domain_name (the full domain with TLD)
   - rationale (why this domain works)
   - legitimacy_score (0.7-1.0)
5. After all suggestions, call complete_job with job_id="{job_id}"
"""

    cmd = [
        "claude",
        "-p", prompt,
        "--dangerously-skip-permissions",  # Allow MCP tool calls without confirmation
        "--mcp-config", os.path.join(PROJECT_PATH, "domain_mcp_config.json"),
    ]

    # Add profile selection if not using default
    if CLAUDE_ACCOUNT and CLAUDE_ACCOUNT != "default":
        cmd.extend(["--profile", CLAUDE_ACCOUNT])

    try:
        logger.info(f"Running Claude Code for domain generation")

        # Run Claude Code with full autonomy
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minute timeout (domain generation is faster)
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

            # Check for authentication errors - may need manual re-auth
            if "401" in error_msg or "authentication" in error_msg.lower() or "OAuth" in error_msg:
                logger.warning("=" * 60)
                logger.warning("AUTHENTICATION ERROR DETECTED")
                logger.warning("OAuth token may have expired. Re-authenticate with:")
                logger.warning("  docker exec -it <container_id> claude /login")
                logger.warning("=" * 60)

            mark_job_failed(job_id, error_msg[:500])
        else:
            logger.info(f"Domain job {job_id} completed successfully")
            logger.info(f"Claude Code output: {result.stdout[:500] if result.stdout else '(empty)'}")
            # Job status should be updated by complete_job tool in MCP

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out")
        mark_job_failed(job_id, "Generation timed out after 3 minutes")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])


def run_worker():
    """Main worker loop.

    This is a persistent daemon that runs forever, polling the database for
    pending domain generation jobs. For each job, it spawns a Claude Code
    subprocess to generate domain suggestions.

    OAuth credentials persist via volume mount, and Claude Code can auto-refresh
    access tokens using the refresh token (valid ~30 days).
    """
    logger.info("Domain Generation Worker starting...")
    logger.info(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    logger.info(f"Poll interval: {POLL_INTERVAL} seconds")
    logger.info(f"Claude account: {CLAUDE_ACCOUNT}")
    logger.info(f"Skill file: {SKILL_FILE}")

    # Load skill content once at startup
    logger.info("Loading skill content...")
    try:
        skill_content = load_skill_content()
        logger.info(f"Skill loaded successfully ({len(skill_content)} chars)")
    except Exception as e:
        logger.error(f"Failed to load skill - cannot start worker: {e}")
        sys.exit(1)

    # Ensure tables exist
    ensure_tables()

    logger.info("Worker ready - polling for jobs...")

    while True:
        try:
            # Get next pending job
            job = get_pending_job()

            if job:
                process_job(job, skill_content)
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
