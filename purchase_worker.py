"""
Purchase Worker - Hypertide Inbox Purchase Daemon

Polls the database for pending purchase jobs (worker_mode='worker') and spawns
Claude Code to execute each purchase via browser automation on Hypertide.

The worker runs autonomously - Claude Code has full permission to call MCP tools
(browser + database) without human approval during execution.

Usage:
    # Normal daemon mode (polls for jobs):
    python purchase_worker.py

    # Single job mode (process one job and exit):
    python purchase_worker.py --single-job <JOB_ID>

    # Stop after a specific skill step (for testing):
    python purchase_worker.py --single-job <JOB_ID> --stop-after-step 2

Environment variables:
    POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
    POLL_INTERVAL (default: 10 seconds)
    CLAUDE_ACCOUNT (default: ClaudeCodeMax - which Claude Code profile to use)
    OAUTH_CHECK_INTERVAL (default: 3600 - seconds between OAuth health checks)
    ALERT_WEBHOOK_URL (optional - webhook URL for OAuth expiry alerts)
    JOB_TIMEOUT (default: 600 - seconds before a job times out)
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
CLAUDE_ACCOUNT = os.getenv("CLAUDE_ACCOUNT", "ClaudeCodeMax")
OAUTH_CHECK_INTERVAL = int(os.getenv("OAUTH_CHECK_INTERVAL", "3600"))
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
JOB_TIMEOUT = int(os.getenv("JOB_TIMEOUT", "600"))  # 10 minutes

# Path to this project (for MCP config)
PROJECT_PATH = os.path.dirname(os.path.abspath(__file__))

# Track OAuth state
_last_oauth_check = 0
_oauth_valid = True
_alert_sent = False

# Skill file path
SKILL_FILE = os.path.join(PROJECT_PATH, ".claude", "skills", "execute-purchase.md")


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
    """Send alert via webhook (Discord/Slack compatible)."""
    global _alert_sent

    if not ALERT_WEBHOOK_URL:
        logger.warning(f"ALERT (no webhook configured): {title} - {message}")
        return

    if _alert_sent and level == "error":
        logger.info("Alert already sent, skipping duplicate")
        return

    color_map = {"error": 15158332, "warning": 16776960, "info": 3447003}

    payload = {
        "embeds": [{
            "title": f"🚨 {title}" if level == "error" else f"⚠️ {title}" if level == "warning" else f"ℹ️ {title}",
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
        if level == "error":
            _alert_sent = True
    except URLError as e:
        logger.error(f"Failed to send alert: {e}")


def check_oauth_health(force: bool = False) -> bool:
    """Check if Claude Code OAuth token is valid."""
    global _last_oauth_check, _oauth_valid, _alert_sent

    current_time = time.time()

    if not force and (current_time - _last_oauth_check) < OAUTH_CHECK_INTERVAL:
        return _oauth_valid

    _last_oauth_check = current_time

    logger.info("Checking Claude Code OAuth health...")

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

        if result.returncode != 0 or "401" in output or "OAuth" in output or "authentication" in output.lower():
            logger.error("OAuth token is EXPIRED or INVALID")
            logger.error(f"Output: {output[:500]}")
            _oauth_valid = False

            send_alert(
                "Claude OAuth Token Expired (Purchase Worker)",
                f"The OAuth token for Claude Code has expired.\n\n"
                f"**To fix:**\n"
                f"```\ndocker exec -it charm-purchase-worker bash\nclaude /login\n```\n\n"
                f"Worker will pause until re-authenticated.",
                level="error"
            )
            return False

        logger.info("OAuth token is valid")

        if not _oauth_valid and _alert_sent:
            send_alert(
                "Claude OAuth Token Restored (Purchase Worker)",
                "OAuth has been successfully re-authenticated.\n\nWorker resuming normal operation.",
                level="info"
            )

        _oauth_valid = True
        _alert_sent = False
        return True

    except subprocess.TimeoutExpired:
        logger.warning("OAuth check timed out - assuming valid")
        return _oauth_valid
    except Exception as e:
        logger.error(f"OAuth check failed: {e}")
        return _oauth_valid


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
        ]

        for col_name, col_def in worker_columns:
            try:
                cur.execute(f"""
                    ALTER TABLE inbox_purchase_jobs
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
            UPDATE inbox_purchase_jobs
            SET status = 'failed',
                current_step = 'worker_error',
                completed_at = NOW()
            WHERE id = %s
        """, (job_id,))

        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET errors = COALESCE(errors, ARRAY[]::TEXT[]) || ARRAY[%s]
            WHERE id = %s
        """, (error, job_id))

        conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark job as failed: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def process_job(job: dict, skill_content: str, stop_after_step: int = None):
    """Process a purchase job by spawning Claude Code with browser automation.

    Args:
        job: Job dict with id, client_id, provider_type, domain_names, company_name
        skill_content: Pre-loaded skill instructions to embed in prompt
        stop_after_step: If set, inject a stop instruction after this skill step (1-14).
                         Used for testing to prevent accidental purchases.
    """
    job_id = str(job["id"])
    client_id = str(job["client_id"])
    provider_type = job.get("provider_type", "entra")
    company_name = job.get("company_name", "Unknown")
    domain_names = job.get("domain_names", [])

    logger.info(f"Processing purchase job {job_id} for {company_name} ({provider_type}, {len(domain_names)} domains)")
    if stop_after_step:
        logger.info(f"TEST MODE: Will stop after step {stop_after_step}")

    # Build prompt with embedded skill
    # If stop_after_step is set, place the STOP instruction at the TOP of the prompt
    # so Claude sees it before reading any skill steps. This prevents overshoot.
    stop_preamble = ""
    if stop_after_step:
        stop_preamble = f"""
╔══════════════════════════════════════════════════════════════╗
║  MANDATORY STOP RULE — READ THIS FIRST                      ║
║                                                              ║
║  This is a TEST RUN. You MUST stop after Step {stop_after_step:<2}             ║
║  After completing Step {stop_after_step}, immediately call:               ║
║    fail_job("{job_id}",                           ║
║            "test_stopped_after_step_{stop_after_step}",                   ║
║            "step_{stop_after_step}")                                      ║
║                                                              ║
║  Then STOP. Do NOT execute Step {stop_after_step + 1} or beyond.             ║
║  Do NOT navigate to any new pages after Step {stop_after_step}.              ║
║  Do NOT repeat any previous steps.                           ║
║  Do NOT log in more than once.                               ║
╚══════════════════════════════════════════════════════════════╝

"""

    prompt = f"""{stop_preamble}You are executing a Hypertide inbox purchase order. Follow these instructions exactly:

{skill_content}

---

NOW EXECUTE THE PURCHASE WITH THESE PARAMETERS:
- job_id: {job_id}

Execute all steps starting from Step 1 (Load Job Data).
Call get_purchase_job("{job_id}") first to get all the data you need.
Then follow each step in order through to completion or failure.

IMPORTANT TIMING RULES:
- After clicking any button that triggers a page change, ALWAYS call wait_for_text() to verify the new page loaded before doing anything else.
- NEVER navigate to a URL you are already on. If you are already on the dashboard, do NOT navigate to the signin page again.
- Login to Hypertide exactly ONCE. If you see the dashboard, you are logged in — do not log in again.
"""

    # Also append stop reminder at the end for reinforcement
    if stop_after_step:
        prompt += f"""
REMINDER: This is a TEST RUN. STOP after Step {stop_after_step}. Call fail_job() and STOP immediately.
"""

    cmd = [
        "claude",
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--mcp-config", os.path.join(PROJECT_PATH, "purchase_mcp_config.json"),
    ]

    # Limit max turns to prevent runaway execution.
    # Each skill step uses ~5-15 tool calls (navigate, fill, click, wait, screenshot, log_step, get_page_text).
    # Complex steps (domain entry, bison config) need 15+ calls for form interaction.
    if stop_after_step:
        # For testing: ~15 turns per step + 15 for setup/teardown
        max_turns = (stop_after_step * 15) + 15
        cmd.extend(["--max-turns", str(max_turns)])
    else:
        # Full run: 14 steps * 15 turns = 210, round up to 225
        cmd.extend(["--max-turns", "225"])

    if CLAUDE_ACCOUNT and CLAUDE_ACCOUNT != "default":
        cmd.extend(["--profile", CLAUDE_ACCOUNT])

    try:
        logger.info(f"Spawning Claude Code for job {job_id}...")

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
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Claude Code failed: {error_msg[:500]}")

            # Check for authentication errors
            if "401" in error_msg or "authentication" in error_msg.lower() or "OAuth" in error_msg:
                logger.warning("=" * 60)
                logger.warning("AUTHENTICATION ERROR DETECTED")
                logger.warning("OAuth token may have expired. Re-authenticate with:")
                logger.warning("  docker exec -it charm-purchase-worker bash")
                logger.warning("  claude /login")
                logger.warning("=" * 60)

                check_oauth_health(force=True)

                # Return job to pending for retry after re-auth
                conn = get_db()
                cur = conn.cursor()
                try:
                    cur.execute("""
                        UPDATE inbox_purchase_jobs
                        SET status = 'pending', started_at = NULL,
                            current_step = 'OAuth expired - awaiting re-authentication'
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
                return

            mark_job_failed(job_id, error_msg[:500])
        else:
            logger.info(f"Purchase job {job_id} completed")
            logger.info(f"Claude Code output: {result.stdout[:500] if result.stdout else '(empty)'}")

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out after {JOB_TIMEOUT}s")
        mark_job_failed(job_id, f"Purchase timed out after {JOB_TIMEOUT} seconds")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])


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
        stop_after_step: If set, stop execution after this skill step (1-14)
    """
    logger.info(f"Single job mode: processing {job_id}")
    if stop_after_step:
        logger.info(f"Will stop after step {stop_after_step}")

    # Load skill content
    logger.info("Loading skill content...")
    try:
        skill_content = load_skill_content()
        logger.info(f"Skill loaded ({len(skill_content)} chars)")
    except Exception as e:
        logger.error(f"Failed to load skill: {e}")
        sys.exit(1)

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
    process_job(job, skill_content, stop_after_step=stop_after_step)

    logger.info(f"Single job {job_id} processing complete. Exiting.")


def run_worker():
    """Main worker loop.

    Persistent daemon that polls for pending purchase jobs (worker_mode='worker').
    For each job, spawns a Claude Code subprocess with browser automation
    to execute the Hypertide purchase flow.
    """
    global _oauth_valid

    logger.info("Purchase Worker starting...")
    logger.info(f"Database: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    logger.info(f"Poll interval: {POLL_INTERVAL} seconds")
    logger.info(f"Job timeout: {JOB_TIMEOUT} seconds")
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
        logger.error("Run: docker exec -it charm-purchase-worker bash && claude /login")
        logger.error("Worker will wait for valid OAuth before processing jobs...")
        logger.error("=" * 60)

    logger.info("Worker ready - polling for purchase jobs...")

    while True:
        try:
            # Periodic OAuth health check
            if not check_oauth_health():
                logger.warning("OAuth invalid - pausing job processing for 60 seconds...")
                time.sleep(60)
                continue

            # Get next pending job
            job = get_pending_job()

            if job:
                process_job(job, skill_content)
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
        help="Stop execution after skill step N (1-14). For testing only."
    )
    args = parser.parse_args()

    if args.stop_after_step and not args.single_job:
        parser.error("--stop-after-step requires --single-job")

    if args.single_job:
        run_single_job(args.single_job, args.stop_after_step)
    else:
        run_worker()
