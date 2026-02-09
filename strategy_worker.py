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
SKILL_FILE = os.path.join(PROJECT_PATH, ".claude", "skills", "generate-strategy.md")


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
            "title": f"🚨 {title}" if level == "error" else f"⚠️ {title}" if level == "warning" else f"ℹ️ {title}",
            "description": message,
            "color": color_map.get(level, 3447003),
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Strategy Worker"}
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
                "Claude OAuth Token Expired",
                f"The OAuth token for Claude Code has expired.\n\n"
                f"**To fix:**\n"
                f"```\ndocker exec -it charm-strategy-test bash\nclaude /login\n```\n\n"
                f"Worker will pause until re-authenticated.",
                level="error"
            )
            return False

        logger.info("OAuth token is valid ✓")

        # Send recovery notification if we were previously invalid
        if not _oauth_valid and _alert_sent:
            send_alert(
                "Claude OAuth Token Restored",
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
            RETURNING id, client_id, submission_id, generation_round, strategy_id, revision_of, job_type
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


def process_job(job: dict, skill_content: str):
    """Process a strategy generation job by spawning Claude Code.

    Args:
        job: Job dict with id, client_id, submission_id, generation_round, job_type, revision_of, strategy_id
        skill_content: Pre-loaded skill instructions to embed in prompt
    """
    job_id = str(job["id"])
    client_id = str(job["client_id"])
    submission_id = str(job["submission_id"]) if job.get("submission_id") else None
    generation_round = job.get("generation_round", 1)
    job_type = job.get("job_type", "initial")
    revision_of = str(job["revision_of"]) if job.get("revision_of") else None
    strategy_id = str(job["strategy_id"]) if job.get("strategy_id") else None

    logger.info(f"Processing strategy job {job_id} for client {client_id} (round {generation_round}, type={job_type})")

    # Build prompt based on job type
    if job_type == "revision" and revision_of:
        # Revision job - generate 1 revised variant based on user feedback
        prompt = f"""You are revising an email variant based on user feedback. Follow these instructions:

{skill_content}

---

REVISION MODE - Generate 1 revised variant (not 3)

PARAMETERS:
- client_id: {client_id}
- job_id: {job_id}
- original_suggestion_id: {revision_of}"""

        if strategy_id:
            prompt += f"\n- strategy_id: {strategy_id}"

        prompt += f"""

Execute these steps:
1. Call get_client_context with the client_id
2. Call get_revision_context with the original_suggestion_id ({revision_of}) to get:
   - The original email content
   - The user's revision instruction
   - Previous feedback patterns
3. Generate 1 revised email variant that incorporates the user's feedback
4. QA score the revised variant
5. Call save_campaign_variant for the revised variant with:
   - original_suggestion_id="{revision_of}"
   - variant_number=1
   - All other required fields (subject_line, email_body, score, rationale, etc.)
6. Call mark_revision_processed with original_suggestion_id="{revision_of}"
7. Call complete_job with the job_id"""

    else:
        # Initial job - generate 4 distinct campaign sequences as a batch
        prompt = f"""You are executing a cold email strategy generation task. Follow these instructions exactly:

{skill_content}

---

NOW EXECUTE THE TASK WITH THESE PARAMETERS:
- client_id: {client_id}
- job_id: {job_id}"""

        if submission_id:
            prompt += f"\n- submission_id: {submission_id}"

        if strategy_id:
            prompt += f"\n- strategy_id: {strategy_id}"

        prompt += """

Execute all steps:
1. Call get_client_context with the client_id to get:
   - Company info, target customer, ICP
   - Segments and personas (critical for targeting the 4 campaigns)
   - Case studies and ROI results

2. Call get_feedback_summary with the client_id to learn:
   - Which patterns work (approved)
   - Which to avoid (denied)

3. Plan 4 distinct campaign angles using the client's segments/personas:
   - Campaign 1: custom_signal angle targeting primary segment/persona
   - Campaign 2: persona_pain angle targeting secondary persona
   - Campaign 3: case_study angle targeting decision makers
   - Campaign 4: risk_efficiency angle targeting budget holders

4. For EACH of the 4 campaigns, create a complete 4-email sequence:
   - Use a different opener pattern for each campaign
   - Target a different persona/segment for each campaign
   - Vary the value prop lead across campaigns

5. Apply QA checklist to all 16 emails (4 campaigns × 4 emails)

6. Call save_campaign_batch with all 4 campaigns + strategy_considerations:
   - Include campaign_angle, target_persona, target_segment, opener_pattern
   - Include strategy_considerations showing which onboarding inputs influenced each campaign

7. Call complete_job with the job_id"""

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

            # Check for authentication errors - trigger OAuth check and alert
            if "401" in error_msg or "authentication" in error_msg.lower() or "OAuth" in error_msg:
                logger.warning("=" * 60)
                logger.warning("AUTHENTICATION ERROR DETECTED")
                logger.warning("OAuth token may have expired. Re-authenticate with:")
                logger.warning("  docker exec -it charm-strategy-test bash")
                logger.warning("  claude /login")
                logger.warning("=" * 60)

                # Force OAuth check which will send alert
                check_oauth_health(force=True)

                # Mark job for retry by setting back to pending (not failed)
                conn = get_db()
                cur = conn.cursor()
                try:
                    cur.execute("""
                        UPDATE strategy_generation_jobs
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
            logger.info(f"Strategy job {job_id} completed successfully")
            logger.info(f"Claude Code output: {result.stdout[:500] if result.stdout else '(empty)'}")
            # Job status should be updated by complete_job tool in MCP

    except subprocess.TimeoutExpired:
        logger.error(f"Job {job_id} timed out")
        mark_job_failed(job_id, "Generation timed out after 5 minutes")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])


def run_worker():
    """Main worker loop.

    This is a persistent daemon that runs forever, polling the database for
    pending strategy generation jobs. For each job, it spawns a Claude Code
    subprocess to generate email variants.

    OAuth credentials persist via volume mount, and Claude Code can auto-refresh
    access tokens using the refresh token (valid ~30 days).

    OAuth Health Monitoring:
    - Checks OAuth validity on startup (fails fast if expired)
    - Re-checks periodically based on OAUTH_CHECK_INTERVAL
    - Sends webhook alerts when OAuth expires
    - Pauses job processing until re-authenticated
    """
    global _oauth_valid

    logger.info("Strategy Generation Worker starting...")
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
        logger.error("Run: docker exec -it charm-strategy-test bash && claude /login")
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
