"""
MCP Server providing browser automation + database tools for Hypertide purchase execution.

This server gives Claude the ability to:
- Navigate and interact with Hypertide's web UI via Playwright (headless Chromium)
- Read purchase job data from the database
- Log step-by-step audit trail with screenshots
- Mark jobs as completed or failed

Browser lifecycle: Chromium launches on first navigate() call.
Browser closes when the MCP server process exits (end of Claude Code subprocess).

Timing & rate limiting:
- slow_mo=100ms on Playwright launch (paces all browser operations)
- 3s minimum cooldown between navigate() calls
- Navigation deduplication (skip if same URL already loaded)
- 3s post-click wait with load state verification
- All waits logged for debugging
"""
import asyncio
import base64
import json
import os
import time
import traceback
from datetime import datetime
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor, Json
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Database configuration from environment
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

server = Server("purchase-executor")

# Browser state (lazy-initialized on first navigate)
_playwright = None
_browser = None
_page = None

# Rate limiting state
_last_navigate_time = 0.0      # Timestamp of last navigate() call
_current_url = ""              # Currently loaded URL (for deduplication)
NAVIGATE_COOLDOWN_SEC = 3.0    # Minimum seconds between navigate() calls

# Login guard — prevents double login (wastes time + hammers Hypertide)
_login_completed = False       # Set True after successful login (dashboard seen)


def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


async def _ensure_browser():
    """Lazily initialize Playwright browser on first use."""
    global _playwright, _browser, _page

    if _page is not None:
        return _page

    from playwright.async_api import async_playwright

    _playwright = await async_playwright().start()
    # Use headed mode with Xvfb virtual display for reliable SPA rendering.
    # Headless Chromium fails to render some SPAs (like Hypertide).
    # The Dockerfile installs xvfb and the worker launches with DISPLAY=:99.
    _browser = await _playwright.chromium.launch(
        headless=False,
        slow_mo=100,  # 100ms between every Playwright action — prevents hammering
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    )
    _page = await _browser.new_page(viewport={"width": 1280, "height": 900})
    return _page


async def _take_screenshot() -> str:
    """Take a screenshot and return as base64 string."""
    if _page is None:
        return ""
    try:
        screenshot_bytes = await _page.screenshot(full_page=False)
        return base64.b64encode(screenshot_bytes).decode("utf-8")
    except Exception:
        return ""


async def _get_page_info() -> dict:
    """Get current page URL and title."""
    if _page is None:
        return {"url": "", "title": ""}
    try:
        return {"url": _page.url, "title": await _page.title()}
    except Exception:
        return {"url": "", "title": ""}


# =============================================================================
# Tool Definitions
# =============================================================================

@server.list_tools()
async def list_tools():
    """List available purchase execution tools."""
    return [
        # --- Browser Tools ---
        Tool(
            name="navigate",
            description="Navigate to a URL. Waits for DOM content and interactive elements. Returns screenshot + current URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to navigate to"}
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="screenshot",
            description="Take a screenshot of the current page. Returns base64 image + current URL.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="click",
            description="""Click an element on the page. Supports CSS selectors or text selectors.
            Examples: 'button.submit', 'text=Place New Order', '#next-step', 'text=Entra'.
            Returns screenshot after clicking.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector or text= selector to click"}
                },
                "required": ["selector"]
            }
        ),
        Tool(
            name="fill",
            description="Clear an input field and type a value into it. Returns screenshot after filling.",
            inputSchema={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector for the input field"},
                    "value": {"type": "string", "description": "The value to type into the field"}
                },
                "required": ["selector", "value"]
            }
        ),
        Tool(
            name="select_dropdown",
            description="""Open a dropdown/select and choose an option by its visible text.
            First clicks the trigger element, then clicks the option matching the text.
            Returns screenshot after selection.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "trigger_selector": {"type": "string", "description": "CSS selector for the dropdown trigger element"},
                    "option_text": {"type": "string", "description": "The visible text of the option to select"}
                },
                "required": ["trigger_selector", "option_text"]
            }
        ),
        Tool(
            name="scroll_down",
            description="Scroll the page down by a specified number of pixels. Returns screenshot after scrolling.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pixels": {"type": "integer", "description": "Number of pixels to scroll down (default 500)", "default": 500}
                }
            }
        ),
        Tool(
            name="get_page_text",
            description="Get all visible text content on the current page. Useful for reading form values, error messages, or verifying page state.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="wait_for_text",
            description="Wait for specific text to appear on the page. Returns 'found' or 'not_found'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to wait for"},
                    "timeout_ms": {"type": "integer", "description": "Maximum time to wait in milliseconds (default 10000)", "default": 10000}
                },
                "required": ["text"]
            }
        ),

        # --- Database Tools ---
        Tool(
            name="get_purchase_job",
            description="Get the full purchase job record from the database. Returns all job fields as JSON including credentials, domain info, and configuration.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The purchase job UUID"}
                },
                "required": ["job_id"]
            }
        ),
        Tool(
            name="update_job_status",
            description="Update the status and current step of a purchase job.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The purchase job UUID"},
                    "status": {"type": "string", "description": "New status: 'processing', 'executing', etc."},
                    "step": {"type": "string", "description": "Current step description"}
                },
                "required": ["job_id", "status"]
            }
        ),
        Tool(
            name="log_step",
            description="Log an audit step with optional screenshot. Call this at EVERY step of the purchase flow for traceability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The purchase job UUID"},
                    "step_name": {"type": "string", "description": "Name of the step (e.g., 'login', 'select_plan', 'fill_bison_creds')"},
                    "screenshot_base64": {"type": "string", "description": "Base64 screenshot (optional, auto-captured if omitted)"},
                    "notes": {"type": "string", "description": "Notes about what happened at this step"}
                },
                "required": ["job_id", "step_name"]
            }
        ),
        Tool(
            name="complete_job",
            description="""Mark a purchase job as completed successfully.
            Updates job status, stores the Hypertide order ID, and sets infrastructure_type on the domains.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The purchase job UUID"},
                    "order_id": {"type": "string", "description": "The Hypertide order ID from the confirmation screen"}
                },
                "required": ["job_id", "order_id"]
            }
        ),
        Tool(
            name="fail_job",
            description="Mark a purchase job as failed. Automatically takes a final screenshot for debugging.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The purchase job UUID"},
                    "error": {"type": "string", "description": "Error message describing what went wrong"},
                    "step": {"type": "string", "description": "The step where the failure occurred"},
                    "error_type": {
                        "type": "string",
                        "description": "Failure category: payment, config, auth, timeout, system",
                        "enum": ["payment", "config", "auth", "timeout", "system"],
                        "default": "system"
                    }
                },
                "required": ["job_id", "error"]
            }
        ),
        Tool(
            name="handoff_checkout",
            description="Hand off checkout to user for manual payment. Stores the Stripe URL and sets status to awaiting_checkout. STOP all execution after calling this.",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The purchase job UUID"},
                    "checkout_url": {"type": "string", "description": "Full Stripe checkout URL"}
                },
                "required": ["job_id", "checkout_url"]
            }
        ),
    ]


# =============================================================================
# Tool Handlers
# =============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    global _last_navigate_time, _current_url, _login_completed

    # --- Browser Tools ---

    if name == "navigate":
        url = arguments["url"]
        try:
            page = await _ensure_browser()

            # --- Login guard: REFUSE to navigate to signin after login completed ---
            if _login_completed and "signin" in url.lower():
                screenshot = await _take_screenshot()
                return [TextContent(type="text", text=json.dumps({
                    "status": "blocked",
                    "url": _current_url,
                    "note": "LOGIN GUARD: You are already logged in. "
                            "Navigating back to the signin page is FORBIDDEN. "
                            "Continue from the current page. Do NOT log in again.",
                    "screenshot_base64": screenshot
                }))]

            # --- Deduplication: skip if already on this URL ---
            if _current_url and _current_url.rstrip("/") == url.rstrip("/"):
                screenshot = await _take_screenshot()
                info = await _get_page_info()
                return [TextContent(type="text", text=json.dumps({
                    "status": "ok",
                    "url": info["url"],
                    "title": info["title"],
                    "note": "Already on this page — skipped redundant navigation",
                    "screenshot_base64": screenshot
                }))]

            # --- Rate limiting: enforce cooldown between navigations ---
            now = time.time()
            elapsed = now - _last_navigate_time
            if elapsed < NAVIGATE_COOLDOWN_SEC:
                wait_time = NAVIGATE_COOLDOWN_SEC - elapsed
                await asyncio.sleep(wait_time)

            # Use domcontentloaded - don't wait for network requests to finish.
            # Hypertide's backend API (backend.hypertide.io) is unreachable from Docker,
            # so "load" and "networkidle" hang indefinitely. domcontentloaded fires once
            # the HTML is parsed and React can hydrate, matching the proven pattern
            # from HypertideClient in Hypertide/automation/src/.
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            _last_navigate_time = time.time()
            _current_url = url

            # Wait for meaningful content (form elements, buttons, etc.)
            try:
                await page.wait_for_selector(
                    "input, button, form, [role='main']",
                    timeout=15000
                )
            except Exception:
                pass

            # Brief pause for React hydration
            await asyncio.sleep(2)

            screenshot = await _take_screenshot()
            info = await _get_page_info()

            result = {
                "status": "ok",
                "url": info["url"],
                "title": info["title"],
                "screenshot_base64": screenshot
            }
            return [TextContent(type="text", text=json.dumps(result))]
        except Exception as e:
            screenshot = await _take_screenshot()
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "error": str(e),
                "screenshot_base64": screenshot
            }))]

    elif name == "screenshot":
        screenshot = await _take_screenshot()
        info = await _get_page_info()
        return [TextContent(type="text", text=json.dumps({
            "url": info["url"],
            "title": info["title"],
            "screenshot_base64": screenshot
        }))]

    elif name == "click":
        selector = arguments["selector"]
        try:
            page = await _ensure_browser()
            url_before = page.url

            # Handle text= selectors via Playwright's built-in text matching
            if selector.startswith("text="):
                text = selector[5:]
                await page.get_by_text(text, exact=False).first.click(timeout=10000)
            else:
                await page.click(selector, timeout=10000)

            # Wait for any navigation or animation triggered by the click
            await asyncio.sleep(3)

            # If the URL changed, a navigation happened — wait for DOM and update tracking
            url_after = page.url
            if url_after != url_before:
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                _current_url = url_after

            screenshot = await _take_screenshot()
            info = await _get_page_info()
            return [TextContent(type="text", text=json.dumps({
                "status": "ok",
                "clicked": selector,
                "url": info["url"],
                "navigated": url_after != url_before,
                "screenshot_base64": screenshot
            }))]
        except Exception as e:
            screenshot = await _take_screenshot()
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "error": f"Failed to click '{selector}': {str(e)}",
                "screenshot_base64": screenshot
            }))]

    elif name == "fill":
        selector = arguments["selector"]
        value = arguments["value"]
        try:
            page = await _ensure_browser()
            await page.fill(selector, value, timeout=10000)
            await asyncio.sleep(0.5)
            screenshot = await _take_screenshot()
            info = await _get_page_info()
            return [TextContent(type="text", text=json.dumps({
                "status": "ok",
                "filled": selector,
                "value_length": len(value),
                "url": info["url"],
                "screenshot_base64": screenshot
            }))]
        except Exception as e:
            screenshot = await _take_screenshot()
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "error": f"Failed to fill '{selector}': {str(e)}",
                "screenshot_base64": screenshot
            }))]

    elif name == "select_dropdown":
        trigger_selector = arguments["trigger_selector"]
        option_text = arguments["option_text"]
        try:
            page = await _ensure_browser()

            # Click the dropdown trigger
            await page.click(trigger_selector, timeout=10000)
            await asyncio.sleep(1)

            # Look for the option by text
            option = page.get_by_text(option_text, exact=True)
            count = await option.count()

            if count == 0:
                # Try partial match
                option = page.get_by_text(option_text, exact=False).first
                count = await option.count() if hasattr(option, 'count') else 1

            if count == 0:
                screenshot = await _take_screenshot()
                # Get all visible text to help debug
                text = await page.inner_text("body")
                return [TextContent(type="text", text=json.dumps({
                    "status": "error",
                    "error": f"Option '{option_text}' not found in dropdown",
                    "visible_text_excerpt": text[:2000],
                    "screenshot_base64": screenshot
                }))]

            await option.first.click(timeout=5000)
            await asyncio.sleep(1)
            screenshot = await _take_screenshot()
            info = await _get_page_info()
            return [TextContent(type="text", text=json.dumps({
                "status": "ok",
                "selected": option_text,
                "url": info["url"],
                "screenshot_base64": screenshot
            }))]
        except Exception as e:
            screenshot = await _take_screenshot()
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "error": f"Failed to select '{option_text}': {str(e)}",
                "screenshot_base64": screenshot
            }))]

    elif name == "scroll_down":
        pixels = arguments.get("pixels", 500)
        try:
            page = await _ensure_browser()
            await page.evaluate(f"window.scrollBy(0, {pixels})")
            await asyncio.sleep(0.5)
            screenshot = await _take_screenshot()
            info = await _get_page_info()
            return [TextContent(type="text", text=json.dumps({
                "status": "ok",
                "scrolled_pixels": pixels,
                "url": info["url"],
                "screenshot_base64": screenshot
            }))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "error": str(e)
            }))]

    elif name == "get_page_text":
        try:
            page = await _ensure_browser()
            text = await page.inner_text("body")
            info = await _get_page_info()
            return [TextContent(type="text", text=json.dumps({
                "url": info["url"],
                "title": info["title"],
                "text": text[:10000]  # Limit to 10k chars
            }))]
        except Exception as e:
            return [TextContent(type="text", text=json.dumps({
                "status": "error",
                "error": str(e)
            }))]

    elif name == "wait_for_text":
        text = arguments["text"]
        timeout_ms = arguments.get("timeout_ms", 10000)
        try:
            page = await _ensure_browser()
            await page.get_by_text(text).first.wait_for(state="visible", timeout=timeout_ms)

            # --- Login tracking: mark login as done when dashboard text is found ---
            if "place new order" in text.lower():
                _login_completed = True

            screenshot = await _take_screenshot()
            return [TextContent(type="text", text=json.dumps({
                "status": "found",
                "text": text,
                "screenshot_base64": screenshot
            }))]
        except Exception:
            screenshot = await _take_screenshot()
            return [TextContent(type="text", text=json.dumps({
                "status": "not_found",
                "text": text,
                "waited_ms": timeout_ms,
                "screenshot_base64": screenshot
            }))]

    # --- Database Tools ---

    elif name == "get_purchase_job":
        job_id = arguments["job_id"]
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute("""
                SELECT j.*,
                       array_to_json(j.domain_names) as domain_names_json,
                       array_to_json(j.domain_ids) as domain_ids_json
                FROM inbox_purchase_jobs j
                WHERE j.id = %s
            """, (job_id,))
            job = cur.fetchone()

            if not job:
                return [TextContent(type="text", text=f"Error: Job {job_id} not found")]

            # Convert to serializable dict
            result = {}
            for key, value in job.items():
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                elif hasattr(value, '__str__') and key != 'domain_names' and key != 'domain_ids':
                    result[key] = str(value)
                else:
                    result[key] = value

            # Use JSON arrays for cleaner output
            result["domain_names"] = job.get("domain_names_json") or []
            result["domain_ids"] = job.get("domain_ids_json") or []

            # Remove raw array columns
            result.pop("domain_names_json", None)
            result.pop("domain_ids_json", None)

            # Inject global credentials from ENV (override DB values if set)
            env_credentials = {
                "hypertide_email": os.getenv("HYPERTIDE_EMAIL", ""),
                "hypertide_password": os.getenv("HYPERTIDE_PASSWORD", ""),
                "bison_username": os.getenv("BISON_USERNAME", ""),
                "bison_password": os.getenv("BISON_PASSWORD", ""),
                "bison_url": os.getenv("BISON_URL", "https://spellcast.hirecharm.com"),
                "bison_api_key": os.getenv("EMAILBISON_API_KEY", ""),
            }
            for key, env_value in env_credentials.items():
                if env_value:  # ENV set → use it; else keep DB value (backwards compat)
                    result[key] = env_value

            # Stripe card info from ENV (only if card number is set)
            card_number = os.getenv("STRIPE_CARD_NUMBER", "")
            if card_number:
                result["stripe_card_number"] = card_number
                result["stripe_card_exp"] = os.getenv("STRIPE_CARD_EXP", "")
                result["stripe_card_cvc"] = os.getenv("STRIPE_CARD_CVC", "")
                result["stripe_card_zip"] = os.getenv("STRIPE_CARD_ZIP", "")

            return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

        finally:
            cur.close()
            conn.close()

    elif name == "update_job_status":
        job_id = arguments["job_id"]
        status = arguments["status"]
        step = arguments.get("step")

        conn = get_db()
        cur = conn.cursor()

        try:
            if step:
                cur.execute("""
                    UPDATE inbox_purchase_jobs
                    SET status = %s, current_step = %s,
                        started_at = COALESCE(started_at, NOW())
                    WHERE id = %s
                """, (status, step, job_id))
            else:
                cur.execute("""
                    UPDATE inbox_purchase_jobs
                    SET status = %s,
                        started_at = COALESCE(started_at, NOW())
                    WHERE id = %s
                """, (status, job_id))
            conn.commit()
            return [TextContent(type="text", text=f"Job {job_id} status updated to '{status}'" + (f" at step '{step}'" if step else ""))]
        finally:
            cur.close()
            conn.close()

    elif name == "log_step":
        job_id = arguments["job_id"]
        step_name = arguments["step_name"]
        screenshot_b64 = arguments.get("screenshot_base64")
        notes = arguments.get("notes", "")

        conn = get_db()
        cur = conn.cursor()

        try:
            # --- Step dedup: check DATABASE for existing step (survives process restarts) ---
            cur.execute("""
                SELECT COUNT(*) FROM purchase_job_steps
                WHERE job_id = %s AND step_name = %s
            """, (job_id, step_name))
            existing_count = cur.fetchone()[0]

            if existing_count > 0:
                conn.close()
                return [TextContent(type="text", text=(
                    f"STEP ALREADY LOGGED: '{step_name}' was already recorded for job {job_id}. "
                    f"Each step must be logged exactly once. "
                    f"Do NOT repeat previous steps — continue forward to the next step."
                ))]

            # Auto-capture screenshot if not provided
            if not screenshot_b64:
                screenshot_b64 = await _take_screenshot()

            cur.execute("""
                INSERT INTO purchase_job_steps (job_id, step_name, screenshot_base64, notes)
                VALUES (%s, %s, %s, %s)
            """, (job_id, step_name, screenshot_b64, notes))

            # Also update current_step on the job
            cur.execute("""
                UPDATE inbox_purchase_jobs SET current_step = %s WHERE id = %s
            """, (step_name, job_id))

            conn.commit()
            return [TextContent(type="text", text=f"Logged step '{step_name}' for job {job_id}" + (f" - {notes}" if notes else ""))]
        finally:
            cur.close()
            conn.close()

    elif name == "complete_job":
        job_id = arguments["job_id"]
        order_id = arguments["order_id"]

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Mark job as completed
            cur.execute("""
                UPDATE inbox_purchase_jobs
                SET status = 'completed',
                    hypertide_order_id = %s,
                    current_step = 'completed',
                    completed_at = NOW()
                WHERE id = %s
                RETURNING provider_type, domain_ids, workspace_id
            """, (order_id, job_id))
            job = cur.fetchone()

            if not job:
                conn.rollback()
                return [TextContent(type="text", text=f"Error: Job {job_id} not found")]

            # Update domains with infrastructure_type
            provider_type = job["provider_type"]
            domain_ids = job["domain_ids"]

            if domain_ids and provider_type:
                infra_type = provider_type  # 'entra' or 'google'
                for domain_id in domain_ids:
                    cur.execute("""
                        UPDATE domains
                        SET infrastructure_type = %s, infrastructure_set_at = NOW()
                        WHERE id = %s
                    """, (infra_type, str(domain_id)))

            # Release domain locks — domains are now provisioned
            cur.execute("""
                UPDATE domains
                SET purchase_job_id = NULL, purchase_job_status = NULL
                WHERE purchase_job_id = %s
            """, (job_id,))

            # Log completion step
            screenshot_b64 = await _take_screenshot()
            cur.execute("""
                INSERT INTO purchase_job_steps (job_id, step_name, screenshot_base64, notes)
                VALUES (%s, 'completed', %s, %s)
            """, (job_id, screenshot_b64, f"Order completed successfully. Hypertide order ID: {order_id}"))

            conn.commit()
            return [TextContent(type="text", text=f"Job {job_id} completed! Order ID: {order_id}. Domains updated with infrastructure_type='{provider_type}'.")]

        except Exception as e:
            conn.rollback()
            return [TextContent(type="text", text=f"Error completing job: {str(e)}")]
        finally:
            cur.close()
            conn.close()

    elif name == "fail_job":
        job_id = arguments["job_id"]
        error = arguments["error"]
        step = arguments.get("step", "unknown")
        error_type = arguments.get("error_type", "system")

        # Auto-capture final screenshot
        screenshot_b64 = await _take_screenshot()

        conn = get_db()
        cur = conn.cursor()

        try:
            # Update job status
            cur.execute("""
                UPDATE inbox_purchase_jobs
                SET status = 'failed',
                    error_type = %s,
                    current_step = %s,
                    completed_at = NOW()
                WHERE id = %s
            """, (error_type, step, job_id))

            # Append error to errors array
            cur.execute("""
                UPDATE inbox_purchase_jobs
                SET errors = COALESCE(errors, ARRAY[]::TEXT[]) || ARRAY[%s]
                WHERE id = %s
            """, (error, job_id))

            # Update domain lock status to 'failed' (keep lock so domains stay reserved for retry)
            cur.execute("""
                UPDATE domains SET purchase_job_status = 'failed'
                WHERE purchase_job_id = %s
            """, (job_id,))

            # Log failure step with screenshot
            cur.execute("""
                INSERT INTO purchase_job_steps (job_id, step_name, screenshot_base64, notes)
                VALUES (%s, %s, %s, %s)
            """, (job_id, f"FAILED: {step}", screenshot_b64, error))

            conn.commit()
            return [TextContent(type="text", text=(
                f"Job {job_id} marked as FAILED at step '{step}': {error}\n\n"
                "╔════════════════════════════════════════════╗\n"
                "║  JOB FAILED — STOP ALL EXECUTION NOW.     ║\n"
                "║  Do NOT call any more tools.               ║\n"
                "║  Do NOT navigate to any pages.             ║\n"
                "║  Do NOT attempt to recover or retry.       ║\n"
                "║  Your task is COMPLETE. Output your report.║\n"
                "╚════════════════════════════════════════════╝"
            ))]

        finally:
            cur.close()
            conn.close()

    elif name == "handoff_checkout":
        job_id = arguments["job_id"]
        checkout_url = arguments["checkout_url"]

        # Capture screenshot for audit trail
        screenshot_b64 = await _take_screenshot()

        conn = get_db()
        cur = conn.cursor()

        try:
            # Update job: status → awaiting_checkout, store checkout URL
            cur.execute("""
                UPDATE inbox_purchase_jobs
                SET status = 'awaiting_checkout',
                    checkout_url = %s,
                    current_step = 'awaiting_manual_checkout'
                WHERE id = %s
            """, (checkout_url, job_id))

            # Sync domain lock status
            cur.execute("""
                UPDATE domains SET purchase_job_status = 'awaiting_checkout'
                WHERE purchase_job_id = %s
            """, (job_id,))

            # Log step with screenshot
            cur.execute("""
                INSERT INTO purchase_job_steps (job_id, step_name, screenshot_base64, notes)
                VALUES (%s, 'checkout_handoff', %s, %s)
            """, (job_id, screenshot_b64, f"Checkout handed off to user. URL: {checkout_url}"))

            conn.commit()
            return [TextContent(type="text", text=(
                f"Job {job_id} handed off for manual checkout.\n"
                f"Stripe URL: {checkout_url}\n\n"
                "╔════════════════════════════════════════════════╗\n"
                "║  CHECKOUT HANDED OFF — STOP EXECUTION NOW.     ║\n"
                "║  Do NOT call any more tools.                    ║\n"
                "║  Do NOT navigate to any pages.                  ║\n"
                "║  Do NOT attempt to complete the payment.        ║\n"
                "║  The user will pay manually and confirm.        ║\n"
                "║  Your task is COMPLETE. Output your report.     ║\n"
                "╚════════════════════════════════════════════════╝"
            ))]

        except Exception as e:
            conn.rollback()
            return [TextContent(type="text", text=f"Error handing off checkout: {str(e)}")]
        finally:
            cur.close()
            conn.close()

    else:
        return [TextContent(type="text", text=f"Error: Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
