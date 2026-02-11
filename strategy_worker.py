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

def get_claude_cmd():
    """Get the full path to the claude command."""
    if sys.platform == "win32":
        npm_bin = os.path.expanduser("~/AppData/Roaming/npm/claude.cmd")
        if os.path.exists(npm_bin):
            return npm_bin
    return "claude"

CLAUDE_CMD = get_claude_cmd()

# Track OAuth state
_last_oauth_check = 0
_oauth_valid = True
_alert_sent = False

# Skill file paths - skills are embedded in prompt because -p mode doesn't auto-load skills
SKILL_FILE = os.path.join(PROJECT_PATH, ".claude", "skills", "generate-strategy-v1.0.md")
SCAFFOLD_SKILL_FILE = os.path.join(PROJECT_PATH, ".claude", "skills", "generate-strategy-scaffold.md")
CAMPAIGN_SKILL_FILE = os.path.join(PROJECT_PATH, ".claude", "skills", "generate-campaign-copy.md")

# Phased generation mode (set via env var, defaults to False for backward compatibility)
PHASED_MODE = os.getenv("STRATEGY_PHASED_MODE", "false").lower() == "true"


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
    cmd = [CLAUDE_CMD, "-p", "Say OK"]

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


# =============================================================================
# PHASED GENERATION FUNCTIONS
# =============================================================================

def get_pending_phase():
    """Get the next pending phase to process (has priority over new jobs)."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Lock and get a pending phase
        cur.execute("""
            UPDATE strategy_generation_phases
            SET status = 'processing', started_at = NOW()
            WHERE id = (
                SELECT p.id
                FROM strategy_generation_phases p
                JOIN strategy_generation_jobs j ON j.id = p.parent_job_id
                WHERE p.status = 'pending'
                  AND j.status = 'processing'
                ORDER BY
                    CASE p.phase_type WHEN 'scaffold' THEN 0 ELSE 1 END,
                    p.phase_number NULLS FIRST,
                    p.created_at ASC
                LIMIT 1
                FOR UPDATE OF p SKIP LOCKED
            )
            RETURNING id, parent_job_id, phase_type, phase_number, campaign_document_id
        """)
        phase = cur.fetchone()
        conn.commit()
        return phase
    except Exception as e:
        logger.error(f"Failed to get pending phase: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()


def create_phases_for_job(job_id: str):
    """Create the scaffold phase for a new job. Campaign phases created after scaffold completes."""
    conn = get_db()
    cur = conn.cursor()

    try:
        # Create scaffold phase
        cur.execute("""
            INSERT INTO strategy_generation_phases
            (parent_job_id, phase_type, phase_number, status)
            VALUES (%s, 'scaffold', NULL, 'pending')
            ON CONFLICT (parent_job_id, phase_type, phase_number) DO NOTHING
        """, (job_id,))
        conn.commit()
        logger.info(f"Created scaffold phase for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to create phases for job {job_id}: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def create_campaign_phases(job_id: str):
    """Create the 4 campaign copy phases after scaffold completes."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get campaign documents created by scaffold
        cur.execute("""
            SELECT cd.id, cd.campaign_number
            FROM campaign_documents cd
            JOIN strategy_generation_jobs j ON j.cycle_id = cd.cycle_id
            WHERE j.id = %s
            ORDER BY cd.campaign_number
        """, (job_id,))
        campaigns = cur.fetchall()

        if not campaigns:
            logger.warning(f"No campaign documents found for job {job_id}")
            return

        # Create phase for each campaign
        for campaign in campaigns:
            cur.execute("""
                INSERT INTO strategy_generation_phases
                (parent_job_id, phase_type, phase_number, campaign_document_id, status)
                VALUES (%s, 'campaign_copy', %s, %s, 'pending')
                ON CONFLICT (parent_job_id, phase_type, phase_number) DO NOTHING
            """, (job_id, campaign["campaign_number"], campaign["id"]))

        conn.commit()
        logger.info(f"Created {len(campaigns)} campaign phases for job {job_id}")
    except Exception as e:
        logger.error(f"Failed to create campaign phases: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def mark_phase_complete(phase_id: str):
    """Mark a phase as complete."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE strategy_generation_phases
            SET status = 'completed', completed_at = NOW()
            WHERE id = %s
        """, (phase_id,))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark phase complete: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def mark_phase_failed(phase_id: str, error: str):
    """Mark a phase as failed."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE strategy_generation_phases
            SET status = 'failed', error_message = %s, completed_at = NOW()
            WHERE id = %s
        """, (error, phase_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to mark phase failed: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def check_all_phases_complete(job_id: str):
    """Check if all phases for a job are complete. If so, mark job complete."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Count phase statuses
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) as total
            FROM strategy_generation_phases
            WHERE parent_job_id = %s
        """, (job_id,))
        counts = cur.fetchone()

        if not counts or counts["total"] == 0:
            return

        if counts["failed"] > 0:
            # At least one phase failed - mark job failed
            cur.execute("""
                UPDATE strategy_generation_jobs
                SET status = 'failed',
                    error_message = 'One or more phases failed',
                    completed_at = NOW()
                WHERE id = %s
            """, (job_id,))
            conn.commit()
            logger.info(f"Job {job_id} marked failed - {counts['failed']} phase(s) failed")

        elif counts["completed"] == counts["total"]:
            # All phases complete - mark job complete
            cur.execute("""
                UPDATE strategy_generation_jobs
                SET status = 'review', completed_at = NOW()
                WHERE id = %s
            """, (job_id,))
            conn.commit()
            logger.info(f"Job {job_id} completed - all {counts['total']} phases done")

    except Exception as e:
        logger.error(f"Failed to check phase completion: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def process_scaffold_phase(phase: dict, skill_content: str):
    """Process a scaffold phase - creates ICP, variables, campaign stubs."""
    phase_id = str(phase["id"])
    job_id = str(phase["parent_job_id"])

    logger.info(f"Processing SCAFFOLD phase {phase_id} for job {job_id}")

    # Get job info
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT client_id FROM strategy_generation_jobs WHERE id = %s
        """, (job_id,))
        job = cur.fetchone()
        if not job:
            mark_phase_failed(phase_id, f"Job {job_id} not found")
            return
        client_id = str(job["client_id"])
    finally:
        cur.close()
        conn.close()

    # Build prompt for scaffold generation
    prompt = f"""You are creating the Strategy Scaffold - Phase 1 of a 2-phase generation.

{skill_content}

---

PARAMETERS:
- client_id: {client_id}
- job_id: {job_id}

Execute these steps:
1. get_client_context(client_id="{client_id}") - get company info
2. get_feedback_summary(client_id="{client_id}") - learn patterns
3. Create comprehensive ICP mapping (target_icp, 4 pain point categories, 3 objections)
4. Define cycle variables (apply to all 4 campaigns)
5. Plan 4 campaign angles with campaign-specific variables
6. save_cycle_scaffold(job_id="{job_id}", client_id="{client_id}", cycle_config=..., campaigns=...)

DO NOT call complete_job - the worker handles completion automatically.
This phase creates the SCAFFOLD only - no email content. That comes in Phase 2."""

    # Run Claude Code
    success = run_claude_for_phase(job_id, phase_id, prompt)

    if success:
        mark_phase_complete(phase_id)
        # Create campaign phases now that scaffold exists
        create_campaign_phases(job_id)
        logger.info(f"Scaffold phase {phase_id} complete, campaign phases created")
    else:
        mark_phase_failed(phase_id, "Claude Code execution failed")
        check_all_phases_complete(job_id)


def process_campaign_phase(phase: dict, skill_content: str):
    """Process a campaign copy phase - generates emails for one campaign."""
    phase_id = str(phase["id"])
    job_id = str(phase["parent_job_id"])
    campaign_number = phase["phase_number"]

    logger.info(f"Processing CAMPAIGN {campaign_number} phase {phase_id} for job {job_id}")

    # Build prompt for campaign copy generation
    prompt = f"""You are generating email copy for Campaign {campaign_number} - Phase 2 of generation.

{skill_content}

---

PARAMETERS:
- job_id: {job_id}
- campaign_number: {campaign_number}

Execute these steps:
1. get_campaign_context(job_id="{job_id}", campaign_number={campaign_number}) - load scaffold
2. Understand the campaign angle and variables from context
3. Draft 4 email positions with 2-3 variants each
4. Apply 3-pass word count cutting (50-90 words per email)
5. Run QA scoring for this campaign
6. Create strategy notes
7. save_campaign_copy(job_id="{job_id}", campaign_number={campaign_number}, email_positions=..., qa_scoring=..., strategy_notes=...)

DO NOT call complete_job - the worker handles completion automatically.
Generate emails that match the campaign's assigned angle."""

    # Run Claude Code
    success = run_claude_for_phase(job_id, phase_id, prompt)

    if success:
        mark_phase_complete(phase_id)
        logger.info(f"Campaign {campaign_number} phase {phase_id} complete")
    else:
        mark_phase_failed(phase_id, "Claude Code execution failed")

    # Check if all phases are done
    check_all_phases_complete(job_id)


def run_claude_for_phase(job_id: str, phase_id: str, prompt: str) -> bool:
    """Run Claude Code for a phase and return success/failure."""
    # Select MCP config
    if os.getenv("STRATEGY_LOCAL_MODE", "").lower() == "true":
        mcp_config = os.path.join(PROJECT_PATH, "strategy_mcp_config_docker_local.json")
    else:
        mcp_config = os.path.join(PROJECT_PATH, "strategy_mcp_config.json")

    cmd = [
        CLAUDE_CMD,
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--mcp-config", mcp_config,
    ]

    try:
        # Build environment
        subprocess_env = {
            **os.environ,
            "POSTGRES_HOST": DB_CONFIG["host"],
            "POSTGRES_PORT": str(DB_CONFIG["port"]),
            "POSTGRES_DB": DB_CONFIG["database"],
            "POSTGRES_USER": DB_CONFIG["user"],
            "POSTGRES_PASSWORD": DB_CONFIG["password"],
        }

        if os.getenv("STRATEGY_LOCAL_MODE"):
            subprocess_env["STRATEGY_LOCAL_MODE"] = os.getenv("STRATEGY_LOCAL_MODE")
        if os.getenv("STRATEGY_OUTPUT_DIR"):
            subprocess_env["STRATEGY_OUTPUT_DIR"] = os.getenv("STRATEGY_OUTPUT_DIR")

        # Run with 15 minute timeout per phase (scaffold needs more time for MCP calls)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 minutes per phase
            cwd=PROJECT_PATH,
            env=subprocess_env
        )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"Phase {phase_id} failed: {error_msg[:500]}")
            return False

        logger.info(f"Phase {phase_id} completed successfully")
        return True

    except subprocess.TimeoutExpired:
        logger.error(f"Phase {phase_id} timed out after 15 minutes")
        return False
    except Exception as e:
        logger.error(f"Phase {phase_id} error: {e}")
        return False


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
        # Initial job - generate campaign document in stablekernel format
        prompt = f"""You are generating a cold email campaign document. Follow the skill instructions below.

{skill_content}

---

CRITICAL OVERRIDE - READ CAREFULLY:

DO NOT use save_campaign_batch or save_campaign_sequence or save_campaign_variant.
You MUST use save_campaign_document to save a single document with multiple email position variants.

PARAMETERS:
- client_id: {client_id}
- job_id: {job_id}"""

        if submission_id:
            prompt += f"\n- submission_id: {submission_id}"

        if strategy_id:
            prompt += f"\n- strategy_id: {strategy_id}"

        prompt += """

REQUIRED STEPS:
1. get_client_context(client_id) - get company info, personas, segments, case studies
2. get_feedback_summary(client_id) - learn what works and what to avoid
3. Create icp_mapping with:
   - target_icp: role, company_type, company_size
   - pain_points: EXACTLY 4 categories, each with label and 3-4 specific points
   - objections: EXACTLY 3 objections with preemption strategies
4. Create variable_schema with core, high_signal, ai_generated arrays (include sources)
5. Create email_positions array with 4 positions:
   - Position 1: 3 variants (custom_signal, persona_pain, case_study)
   - Position 2: 1-2 variants (creative ideas, threaded)
   - Position 3: 2 variants (whole_offer, results_first)
   - Position 4: 2 variants (redirect, value_bomb)
   - Mark is_recommended=true on best variant per position
6. Create qa_scoring with overall_score, verdict, and 6 dimension breakdowns
7. Create strategy_notes with callouts, data_enrichment, ab_testing arrays
8. save_campaign_document(job_id, document_name, vertical, objective, icp_mapping, variable_schema, email_positions, sequence_summary, qa_scoring, strategy_notes)
9. complete_job(job_id)

The output MUST match the stablekernel HTML format - a single document with ICP mapping, variables, email variants, QA scoring, and strategy notes. Do NOT generate 4 separate campaigns."""

    # Select MCP config based on mode:
    # - LOCAL_MODE: strategy_mcp_config_docker_local.json (hardcoded LOCAL_MODE env vars)
    # - Production: strategy_mcp_config.json (standard Docker paths)
    # Note: strategy_mcp_config_local.json has Windows paths for local Windows dev
    if os.getenv("STRATEGY_LOCAL_MODE", "").lower() == "true":
        mcp_config = os.path.join(PROJECT_PATH, "strategy_mcp_config_docker_local.json")
        logger.info("Using LOCAL_MODE MCP config - output will be saved to local filesystem")
    else:
        mcp_config = os.path.join(PROJECT_PATH, "strategy_mcp_config.json")

    cmd = [
        CLAUDE_CMD,
        "-p", prompt,
        "--dangerously-skip-permissions",  # Allow MCP tool calls without confirmation
        "--mcp-config", mcp_config,
    ]

    try:
        logger.info(f"Running Claude Code: {' '.join(cmd)}")

        # Build environment for Claude Code subprocess
        # This includes database config and local mode settings
        subprocess_env = {
            **os.environ,
            # Pass database config to MCP server
            "POSTGRES_HOST": DB_CONFIG["host"],
            "POSTGRES_PORT": str(DB_CONFIG["port"]),
            "POSTGRES_DB": DB_CONFIG["database"],
            "POSTGRES_USER": DB_CONFIG["user"],
            "POSTGRES_PASSWORD": DB_CONFIG["password"],
        }

        # Pass local mode settings if enabled
        if os.getenv("STRATEGY_LOCAL_MODE"):
            subprocess_env["STRATEGY_LOCAL_MODE"] = os.getenv("STRATEGY_LOCAL_MODE")
        if os.getenv("STRATEGY_OUTPUT_DIR"):
            subprocess_env["STRATEGY_OUTPUT_DIR"] = os.getenv("STRATEGY_OUTPUT_DIR")

        # Run Claude Code with full autonomy
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,  # 15 minute timeout for full 4-campaign cycles
            cwd=PROJECT_PATH,
            env=subprocess_env
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
        mark_job_failed(job_id, "Generation timed out after 15 minutes")

    except Exception as e:
        logger.error(f"Job {job_id} failed with error: {e}")
        mark_job_failed(job_id, str(e)[:500])


def load_scaffold_skill() -> str:
    """Load scaffold skill for phased generation."""
    try:
        with open(SCAFFOLD_SKILL_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Scaffold skill file not found: {SCAFFOLD_SKILL_FILE}")
        raise


def load_campaign_skill() -> str:
    """Load campaign copy skill for phased generation."""
    try:
        with open(CAMPAIGN_SKILL_FILE, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Campaign skill file not found: {CAMPAIGN_SKILL_FILE}")
        raise


def run_worker():
    """Main worker loop.

    This is a persistent daemon that runs forever, polling the database for
    pending strategy generation jobs. For each job, it spawns a Claude Code
    subprocess to generate email variants.

    Supports two modes:
    - PHASED_MODE=false (default): Single monolithic generation (v1.0 skill)
    - PHASED_MODE=true: Two-phase generation (scaffold + 4 campaign phases)

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
    logger.info(f"PHASED_MODE: {PHASED_MODE}")

    # Load skill content once at startup
    logger.info("Loading skill content...")
    try:
        if PHASED_MODE:
            logger.info(f"Loading phased skills: {SCAFFOLD_SKILL_FILE}, {CAMPAIGN_SKILL_FILE}")
            scaffold_skill = load_scaffold_skill()
            campaign_skill = load_campaign_skill()
            skill_content = None  # Not used in phased mode
            logger.info(f"Phased skills loaded (scaffold: {len(scaffold_skill)} chars, campaign: {len(campaign_skill)} chars)")
        else:
            logger.info(f"Loading monolithic skill: {SKILL_FILE}")
            skill_content = load_skill_content()
            scaffold_skill = None
            campaign_skill = None
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

            if PHASED_MODE:
                # PHASED MODE: Check for pending phases first (they have priority)
                phase = get_pending_phase()

                if phase:
                    # Process phase based on type
                    if phase["phase_type"] == "scaffold":
                        process_scaffold_phase(phase, scaffold_skill)
                    elif phase["phase_type"] == "campaign_copy":
                        process_campaign_phase(phase, campaign_skill)
                    else:
                        logger.error(f"Unknown phase type: {phase['phase_type']}")
                        mark_phase_failed(str(phase["id"]), f"Unknown phase type: {phase['phase_type']}")
                else:
                    # No pending phases - check for new jobs
                    job = get_pending_job()

                    if job:
                        # Create phases for this job instead of processing directly
                        logger.info(f"New job {job['id']} - creating scaffold phase")
                        create_phases_for_job(str(job["id"]))
                    else:
                        # No work available
                        time.sleep(POLL_INTERVAL)
            else:
                # MONOLITHIC MODE: Original behavior
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
