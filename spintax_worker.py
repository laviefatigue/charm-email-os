"""
Spintax Processing Worker

Polls the database for pending spintax processing jobs and spawns
Claude Code to apply spintax/liquid syntax to approved campaign sequences.

The worker runs autonomously - Claude Code has full permission to call MCP tools
without human approval during execution. Human review happens on the frontend.

Usage:
    python spintax_worker.py

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    POLL_INTERVAL (default: 5 seconds)
    CLAUDE_ACCOUNT (default: ClaudeCodeMax - which Claude Code profile to use)
    OAUTH_CHECK_INTERVAL (default: 3600 - seconds between OAuth health checks)
    ALERT_WEBHOOK_URL (optional - webhook URL for OAuth expiry alerts)
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

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
CLAUDE_ACCOUNT = os.getenv("CLAUDE_ACCOUNT", "ClaudeCodeMax")
OAUTH_CHECK_INTERVAL = int(os.getenv("OAUTH_CHECK_INTERVAL", "3600"))  # 1 hour default
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")  # Optional webhook for alerts

# Path to this project (for MCP config)
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))

# Track OAuth state
_last_oauth_check = 0
_oauth_valid = True
_alert_sent = False

# Skill file path - skill content is embedded in prompt because -p mode doesn't auto-load skills
SKILL_FILE = os.path.join(PROJECT_PATH, ".claude", "skills", "apply-spintax.md")


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


def send_alert(title: str, message: str, level: str = "error"):
    """Send alert via webhook (Discord/Slack compatible).

    Args:
        title: Alert title
        message: Alert message body
        level: Alert level (error, warning, info)
    """
    global _alert_sent

    if not ALERT_WEBHOOK_URL:
        logger.warning(f"ALERT (no webhook configured): {title} - {message}")
        return

    # Prevent duplicate alerts
    if _alert_sent and level == "error":
        logger.info("Alert already sent, skipping duplicate")
        return

    color_map = {"error": 15158332, "warning": 16776960, "info": 3447003}  # Discord colors

    # Discord webhook format (also works with many Slack webhooks)
    payload = {
        "embeds": [{
            "title": f"{title}" if level == "error" else f"{title}" if level == "warning" else f"{title}",
            "description": message,
            "color": color_map.get(level, 3447003),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Spintax Worker"}
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
        if level == "error":
            _alert_sent = True
    except URLError as e:
        logger.error(f"Failed to send alert: {e}")


def check_oauth_health(force: bool = False) -> bool:
    """Check if Claude Code OAuth token is valid.

    Args:
        force: If True, bypass the interval check and always verify

    Returns:
        True if OAuth is valid, False if expired/invalid
    """
    global _last_oauth_check, _oauth_valid, _alert_sent

    current_time = time.time()

    # Skip check if we checked recently (unless forced)
    if not force and (current_time - _last_oauth_check) < OAUTH_CHECK_INTERVAL:
        return _oauth_valid

    _last_oauth_check = current_time

    logger.info("Checking Claude Code OAuth health...")

    # Build command to test auth - use a simple prompt that requires auth
    cmd = ["claude", "-p", "Say 'OK' and nothing else", "--max-turns", "1"]

    if CLAUDE_ACCOUNT and CLAUDE_ACCOUNT != "default":
        cmd.extend(["--profile", CLAUDE_ACCOUNT])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=PROJECT_PATH
        )

        output = (result.stdout or "") + (result.stderr or "")

        # Check for auth errors
        if result.returncode != 0 or "401" in output or "OAuth" in output or "authentication" in output.lower():
            logger.error("OAuth token is EXPIRED or INVALID")
            logger.error(f"Output: {output[:500]}")
            _oauth_valid = False

            # Send alert
            send_alert(
                "Claude OAuth Token Expired - Spintax Worker",
                f"The OAuth token for Claude Code has expired.\n\n"
                f"**To fix:**\n"
                f"```\ndocker exec -it charm-spintax-worker bash\nclaude /login\n```\n\n"
                f"Or use a long-lived token:\n"
                f"```\nclaude setup-token\n```\n\n"
                f"Worker will pause until re-authenticated.",
                level="error"
            )
            return False

        logger.info("OAuth token is valid")

        # Send recovery notification if we were previously invalid
        if not _oauth_valid and _alert_sent:
            send_alert(
                "Claude OAuth Token Restored - Spintax Worker",
                "OAuth has been successfully re-authenticated.\n\nWorker resuming normal operation.",
                level="info"
            )

        _oauth_valid = True
        _alert_sent = False  # Reset alert flag on success
        return True

    except subprocess.TimeoutExpired:
        logger.warning("OAuth check timed out - assuming valid")
        return _oauth_valid  # Return last known state
    except Exception as e:
        logger.error(f"OAuth check failed: {e}")
        return _oauth_valid


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def ensure_tables():
    """Ensure the spintax processing tables exist."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            -- Spintax processing jobs
            CREATE TABLE IF NOT EXISTS spintax_processing_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                sequence_id UUID NOT NULL,
                client_id UUID NOT NULL,
                status VARCHAR(50) DEFAULT 'pending',
                error_message TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                started_at TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_spintax_jobs_status
                ON spintax_processing_jobs(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_spintax_jobs_sequence
                ON spintax_processing_jobs(sequence_id);
        """)

        # Add spintaxed_sequence_data column if it doesn't exist
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'strategy_suggestions'
                    AND column_name = 'spintaxed_sequence_data'
                ) THEN
                    ALTER TABLE strategy_suggestions
                    ADD COLUMN spintaxed_sequence_data JSONB;
                END IF;
            END $$;
        """)

        conn.commit()
        logger.info("Spintax processing tables ready")
    except Exception as e:
        logger.error(f"Failed to create tables: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def get_pending_job():
    """Get the next pending spintax processing job to process."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get and lock a pending job
        cur.execute("""
            UPDATE spintax_processing_jobs
            SET status = 'processing', started_at = NOW()
            WHERE id = (
                SELECT id FROM spintax_processing_jobs
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, sequence_id, client_id
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
            UPDATE spintax_processing_jobs
            SET status = 'failed', error_message = %s, completed_at = NOW()
            WHERE id = %s
        """, (error, job_id))

        # Also revert sequence status back to 'approved' so user can retry
        cur.execute("""
            UPDATE strategy_suggestions
            SET status = 'approved'
            WHERE id = (
                SELECT sequence_id FROM spintax_processing_jobs WHERE id = %s
            )
        """, (job_id,))

        conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark job as failed: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def process_job(job: dict, skill_content: str):
    """Process a spintax job by spawning Claude Code.

    Args:
        job: Job dict with id, sequence_id, client_id
        skill_content: Pre-loaded skill instructions to embed in prompt
    """
    job_id = str(job["id"])
    sequence_id = str(job["sequence_id"])
    client_id = str(job["client_id"])

    logger.info(f"Processing spintax job {job_id} for sequence {sequence_id}")

    # Build prompt with embedded skill content
    prompt = f"""You are applying spintax and liquid syntax to an approved email sequence. Follow these instructions exactly:

{skill_content}

---

NOW EXECUTE THE TASK WITH THESE PARAMETERS:
- job_id: {job_id}
- sequence_id: {sequence_id}

Execute these steps in order:
1. Call get_sequence_for_spintax with sequence_id="{sequence_id}" to get the approved content
2. Review the 4-email sequence and apply:
   - Spintax patterns to greetings, CTAs, softeners, time references
   - Liquid syntax for time-of-day greeting (Email 1)
   - Liquid syntax for day-based availability (Email 4 CTA if applicable)
3. Call save_spintaxed_sequence with:
   - sequence_id="{sequence_id}"
   - spintaxed_sequence (array of 4 transformed email objects)
4. Call complete_spintax_job with job_id="{job_id}"

IMPORTANT RULES:
- Keep the core value proposition unchanged
- Max 2-3 spintax variations per element
- Preserve all existing {{{{variables}}}}
- Ensure all liquid syntax tags are properly closed
"""

    cmd = [
        "claude",
        "-p", prompt,
        "--dangerously-skip-permissions",  # Allow MCP tool calls without confirmation
        "--mcp-config", os.path.join(PROJECT_PATH, "spintax_mcp_config.json"),
    ]

    # Add profile selection if not using default
    if CLAUDE_ACCOUNT and CLAUDE_ACCOUNT != "default":
        cmd.extend(["--profile", CLAUDE_ACCOUNT])

    try:
        logger.info(f"Running Claude Code for spintax processing")

        # Run Claude Code with full autonomy
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minute timeout
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

            # Check for authentication errors - trigger OAuth check and alert
            if "401" in error_msg or "authentication" in error_msg.lower() or "OAuth" in error_msg:
                logger.warning("=" * 60)
                logger.warning("AUTHENTICATION ERROR DETECTED")
                logger.warning("OAuth token may have expired. Re-authenticate with:")
                logger.warning("  docker exec -it charm-spintax-worker bash")
                logger.warning("  claude /login")
                logger.warning("Or use long-lived token: claude setup-token")
                logger.warning("=" * 60)

                # Force OAuth check which will send alert
                check_oauth_health(force=True)

                # Mark job for retry by setting back to pending (not failed)
                conn = get_db()
                cur = conn.cursor()
                try:
                    cur.execute("""
                        UPDATE spintax_processing_jobs
                        SET status = 'pending', started_at = NULL,
                            error_message = 'OAuth expired - awaiting re-authentication'
                        WHERE id = %s
                    """, (job_id,))
                    conn.commit()
                    logger.info(f"Job {job_id} returned to pending queue for retry after re-auth")
                except Exception as e:
                    logger.error(f"Failed to reset job status: {e}")
                    conn.rollback()
                finally:
                    cur.close()
                    conn.close()
                return  # Don't mark as failed, let it retry

            mark_job_failed(job_id, error_msg[:500])
        else:
            logger.info(f"Spintax job {job_id} completed successfully")
            logger.info(f"Claude Code output: {result.stdout[:500] if result.stdout else '(empty)'}")
            # Job status should be updated by complete_spintax_job tool in MCP

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out")
        mark_job_failed(job_id, "Processing timed out after 3 minutes")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])


def run_worker():
    """Main worker loop.

    This is a persistent daemon that runs forever, polling the database for
    pending spintax processing jobs. For each job, it spawns a Claude Code
    subprocess to apply spintax/liquid syntax to approved sequences.

    OAuth credentials persist via volume mount, and Claude Code can auto-refresh
    access tokens using the refresh token (valid ~30 days).

    OAuth Health Monitoring:
    - Checks OAuth validity on startup (fails fast if expired)
    - Re-checks periodically based on OAUTH_CHECK_INTERVAL
    - Sends webhook alerts when OAuth expires
    - Pauses job processing until re-authenticated
    """
    global _oauth_valid

    logger.info("Spintax Processing Worker starting...")
    logger.info(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    logger.info(f"Poll interval: {POLL_INTERVAL} seconds")
    logger.info(f"OAuth check interval: {OAUTH_CHECK_INTERVAL} seconds")
    logger.info(f"Alert webhook: {'configured' if ALERT_WEBHOOK_URL else 'not configured'}")
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

    # Check OAuth on startup
    logger.info("Verifying Claude Code OAuth...")
    if not check_oauth_health(force=True):
        logger.error("=" * 60)
        logger.error("STARTUP BLOCKED: OAuth token is expired!")
        logger.error("Run: docker exec -it charm-spintax-worker bash && claude /login")
        logger.error("Or use long-lived token: claude setup-token")
        logger.error("Worker will wait for valid OAuth before processing jobs...")
        logger.error("=" * 60)

    logger.info("Worker ready - polling for jobs...")

    while True:
        try:
            # Periodic OAuth health check
            if not check_oauth_health():
                # OAuth invalid - wait and retry check
                logger.warning("OAuth invalid - pausing job processing for 60 seconds...")
                time.sleep(60)
                continue

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
