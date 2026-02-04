#!/usr/bin/env python3
"""
Hypertide Purchase Automation - Deterministic Playwright Script

This script automates the Hypertide inbox purchase flow using direct Playwright calls.
It's faster and more reliable than the Claude + MCP approach because:
- No LLM inference overhead per step
- Deterministic variable insertion
- Direct Playwright API calls (no MCP round-trip)

Usage:
    # Test with a real job from database:
    python hypertide_playwright.py --job-id <JOB_ID>

    # Dry run (stop before checkout):
    python hypertide_playwright.py --job-id <JOB_ID> --dry-run

    # Stop at a specific step:
    python hypertide_playwright.py --job-id <JOB_ID> --stop-after 7

    # Use headless mode:
    python hypertide_playwright.py --job-id <JOB_ID> --headless

    # INTERACTIVE MODE - Test each screen with user confirmation:
    python hypertide_playwright.py --test --dry-run --interactive

    # RUN SINGLE STEP - Test one specific step:
    python hypertide_playwright.py --test --dry-run --step 2

Steps:
    1  - Load Job Data (validate fields)
    2  - Login to Hypertide
    3  - Start New Order (click Place New Order)
    4  - Select Provider Type (Entra/Google/etc)
    5  - Enter Domains (BYOD mode)
    6  - Basic Configuration (forwarding URL)
    7  - Bison Configuration (email tool credentials)
    8  - Warmup Settings
    9  - Outbound Settings (daily limits)
    10 - Sender Names (add user identities)
    11 - Review Order
    12 - Checkout Handoff (capture Stripe URL)

Requirements:
    pip install playwright psycopg2-binary python-dotenv
    playwright install chromium
"""

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Load .env from project root
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent / "Hypertide" / "automation" / ".env")

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

# Database
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "postgres"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# Credentials (from ENV - no defaults, must be set in container)
HYPERTIDE_EMAIL = os.getenv("HYPERTIDE_EMAIL", "")
HYPERTIDE_PASSWORD = os.getenv("HYPERTIDE_PASSWORD", "")
BISON_USERNAME = os.getenv("BISON_USERNAME", "")
BISON_PASSWORD = os.getenv("BISON_PASSWORD", "")
BISON_URL = os.getenv("BISON_URL", "https://spellcast.hirecharm.com")
BISON_API_KEY = os.getenv("EMAILBISON_API_KEY", "")

# Timing (conservative for reliability - avoid rate limiting)
SLOW_MO = 100  # ms between actions (increased to avoid detection)
NAVIGATION_TIMEOUT = 30000  # ms
ELEMENT_TIMEOUT = 10000  # ms
POST_ACTION_WAIT = 0.5  # seconds after each action (increased for stability)


# =============================================================================
# Database Functions
# =============================================================================

def get_db():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def fetch_job(job_id: str) -> Dict[str, Any]:
    """Fetch job data from database, including client info and sender names."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Fetch job with client info joined
        cur.execute("""
            SELECT j.*,
                   array_to_json(j.domain_names) as domain_names_json,
                   c.name as client_name,
                   c.contact_name as client_contact_name,
                   c.onboarding_data as client_onboarding_data
            FROM inbox_purchase_jobs j
            LEFT JOIN clients c ON c.id = j.client_id
            WHERE j.id = %s
        """, (job_id,))
        job = cur.fetchone()

        if not job:
            raise ValueError(f"Job {job_id} not found")

        # Convert to dict
        result = dict(job)
        result["domain_names"] = job.get("domain_names_json") or []

        # Extract sender names from client's onboarding_data
        onboarding_data = job.get("client_onboarding_data")
        if onboarding_data:
            if isinstance(onboarding_data, str):
                onboarding_data = json.loads(onboarding_data)

            # Get the pre-generated sender names (52 variations)
            pre_generated = onboarding_data.get("preGeneratedSenderNames", [])
            if pre_generated:
                # Use the first 10 (Hypertide max) for this order
                result["sender_names"] = pre_generated[:10]
                logger.info(f"Loaded {len(pre_generated)} sender names from client, using first 10")

            # Get forwarding domain from client onboarding if not set in job
            if not result.get("forwarding_domain"):
                result["forwarding_domain"] = onboarding_data.get("primaryDomain", "")

            # Get base sender name (the original identity)
            base_names = onboarding_data.get("baseSenderNames", [])
            if base_names:
                result["base_sender_name"] = base_names[0]  # First base name
                logger.info(f"Base sender name: {base_names[0]}")

        return result
    finally:
        cur.close()
        conn.close()


def update_job_status(job_id: str, status: str, step: str = None):
    """Update job status in database."""
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
                SET status = %s, started_at = COALESCE(started_at, NOW())
                WHERE id = %s
            """, (status, job_id))
        conn.commit()
        logger.info(f"Updated job {job_id}: status={status}, step={step}")
    finally:
        cur.close()
        conn.close()


def log_step(job_id: str, step_name: str, notes: str = "", screenshot_b64: str = None):
    """Log step to database."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            INSERT INTO purchase_job_steps (job_id, step_name, notes, screenshot_base64, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (job_id, step_name, notes, screenshot_b64))
        conn.commit()
        logger.info(f"Logged step: {step_name} - {notes[:50]}...")
    except Exception as e:
        logger.warning(f"Failed to log step (table may not exist): {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


def handoff_checkout(job_id: str, checkout_url: str):
    """Hand off to manual checkout."""
    conn = get_db()
    cur = conn.cursor()

    try:
        # Update job status
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

        conn.commit()
        logger.info(f"Handed off checkout: {checkout_url}")
    finally:
        cur.close()
        conn.close()


def fail_job(job_id: str, error_msg: str, step: str, error_type: str):
    """Mark job as failed."""
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE inbox_purchase_jobs
            SET status = 'failed',
                current_step = %s,
                error_type = %s,
                errors = array_append(COALESCE(errors, '{}'), %s),
                completed_at = NOW()
            WHERE id = %s
        """, (step, error_type, error_msg, job_id))

        # Release domain locks
        cur.execute("""
            UPDATE domains
            SET purchase_job_id = NULL, purchase_job_status = NULL
            WHERE purchase_job_id = %s
        """, (job_id,))

        conn.commit()
        logger.error(f"Job failed: {error_msg}")
    finally:
        cur.close()
        conn.close()


# =============================================================================
# Interactive Testing Mode
# =============================================================================

STEP_DESCRIPTIONS = {
    1: "Load Job Data - Validate job fields from database",
    2: "Login to Hypertide - Enter credentials and reach dashboard",
    3: "Start New Order - Click 'Place New Order' button",
    4: "Select Provider Type - Choose provider (Entra/Google/etc)",
    5: "Enter Domains (BYOD) - Input domain names for the order",
    6: "Basic Configuration - Forwarding URL and initial settings",
    7: "Bison Configuration - Select Bison tool and enter credentials",
    8: "Warmup Settings - Configure email warmup options",
    9: "Outbound Settings - Set daily sending limits",
    10: "Sender Names - Add user/sender identities",
    11: "Review Order - Verify order details before checkout",
    12: "Checkout Handoff - Capture Stripe URL and hand off to user",
}


def interactive_prompt(step_num: int, step_name: str) -> str:
    """
    Prompt user for action after a step completes.
    Returns: 'continue', 'retry', 'quit', or 'skip'
    """
    print("\n" + "=" * 60)
    print(f"STEP {step_num} COMPLETED: {step_name}")
    print("=" * 60)
    print("\nPlease review the browser window and screenshot.")
    print("\nOptions:")
    print("  [c] Continue to next step")
    print("  [r] Retry this step")
    print("  [s] Skip this step (mark as done)")
    print("  [q] Quit")
    print("  [d] Describe what you see (for debugging)")

    while True:
        choice = input("\nYour choice [c/r/s/q/d]: ").strip().lower()
        if choice in ['c', 'continue', '']:
            return 'continue'
        elif choice in ['r', 'retry']:
            return 'retry'
        elif choice in ['s', 'skip']:
            return 'skip'
        elif choice in ['q', 'quit']:
            return 'quit'
        elif choice in ['d', 'describe']:
            desc = input("Describe what you see: ")
            logger.info(f"User observation: {desc}")
            # Continue prompting
        else:
            print("Invalid choice. Please enter c, r, s, q, or d.")


def interactive_step_preview(step_num: int):
    """Show preview of what the next step will do."""
    desc = STEP_DESCRIPTIONS.get(step_num, "Unknown step")
    print("\n" + "-" * 60)
    print(f"NEXT: Step {step_num} - {desc}")
    print("-" * 60)
    input("Press Enter to execute this step...")


# =============================================================================
# Playwright Automation
# =============================================================================

class HypertideAutomation:
    """Deterministic Hypertide purchase automation."""

    def __init__(self, page: Page, job_data: Dict[str, Any], dry_run: bool = False):
        self.page = page
        self.job = job_data
        self.job_id = job_data.get("id", "test-job")
        self.dry_run = dry_run
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)

    def screenshot(self, name: str) -> str:
        """Take and save screenshot."""
        path = self.screenshots_dir / f"{name}_{datetime.now().strftime('%H%M%S')}.png"
        self.page.screenshot(path=str(path))
        logger.info(f"Screenshot saved: {path}")
        return str(path)

    def wait(self, seconds: float = POST_ACTION_WAIT):
        """Brief wait for page stability."""
        time.sleep(seconds)

    def wait_for_text(self, text: str, timeout: int = ELEMENT_TIMEOUT):
        """Wait for text to appear on page."""
        try:
            self.page.wait_for_selector(f"text={text}", timeout=timeout)
            logger.info(f"Found text: '{text}'")
            return True
        except PlaywrightTimeout:
            logger.warning(f"Text not found: '{text}'")
            return False

    def click_text(self, text: str):
        """Click element containing text."""
        self.page.get_by_text(text, exact=False).first.click(timeout=ELEMENT_TIMEOUT)
        self.wait()
        logger.info(f"Clicked: '{text}'")

    def fill_input(self, selector: str, value: str):
        """Fill input field."""
        self.page.fill(selector, value, timeout=ELEMENT_TIMEOUT)
        self.wait()
        logger.info(f"Filled {selector}: '{value[:20]}...'")

    # =========================================================================
    # Step Implementations
    # =========================================================================

    def step_1_load_data(self) -> bool:
        """Step 1: Validate job data."""
        logger.info("=" * 60)
        logger.info("STEP 1: Load Job Data")
        logger.info("=" * 60)

        required_fields = ["domain_names", "company_name", "bison_workspace_name"]
        for field in required_fields:
            if not self.job.get(field):
                logger.error(f"Missing required field: {field}")
                return False

        logger.info(f"Job ID: {self.job_id}")
        logger.info(f"Domains: {self.job.get('domain_names')}")
        logger.info(f"Company: {self.job.get('company_name')}")
        logger.info(f"Provider: {self.job.get('provider_type')}")
        logger.info(f"Bison workspace: {self.job.get('bison_workspace_name')}")

        if not self.dry_run:
            update_job_status(self.job_id, "processing", "Loading job data")

        return True

    def step_2_login(self) -> bool:
        """Step 2: Login to Hypertide."""
        logger.info("=" * 60)
        logger.info("STEP 2: Login to Hypertide")
        logger.info("=" * 60)

        # Use job-specific credentials, fallback to env vars for test mode
        hypertide_email = self.job.get("hypertide_email") or HYPERTIDE_EMAIL
        hypertide_password = self.job.get("hypertide_password") or HYPERTIDE_PASSWORD

        logger.info(f"Logging in as: {hypertide_email}")

        self.page.goto("https://app2.hypertide.io/signin", timeout=NAVIGATION_TIMEOUT)
        self.wait(1)

        # Fill login form
        self.fill_input("input[type='email']", hypertide_email)
        self.fill_input("input[type='password']", hypertide_password)

        # Submit
        self.page.click("button[type='submit']")
        self.wait(2)

        # Verify dashboard
        if not self.wait_for_text("Place New Order", timeout=15000):
            self.screenshot("login_failed")
            logger.error("Login failed - dashboard not reached")
            return False

        self.screenshot("step_2_login_success")
        if not self.dry_run:
            log_step(self.job_id, "login_success", "Successfully logged in to Hypertide")

        return True

    def step_3_new_order(self) -> bool:
        """Step 3: Click 'Place New Order'."""
        logger.info("=" * 60)
        logger.info("STEP 3: Start New Order")
        logger.info("=" * 60)

        self.click_text("Place New Order")
        self.wait(1)

        self.screenshot("step_3_new_order")
        if not self.dry_run:
            log_step(self.job_id, "new_order", "Clicked Place New Order")

        return True

    def step_4_select_provider(self) -> bool:
        """Step 4: Select provider type AND order quantity, then click 'Select Plan' button."""
        logger.info("=" * 60)
        logger.info("STEP 4: Select Provider Plan")
        logger.info("=" * 60)

        provider = self.job.get("provider_type", "entra")
        domain_count = len(self.job.get("domain_names", []))

        # Get order count from correct database column based on provider
        if provider == "entra":
            order_count = self.job.get("entra_orders", 1) or 1
        else:
            order_count = self.job.get("google_orders", 1) or 1

        # Validate domain count matches order_count
        domains_per_order = 2 if provider == "entra" else 5
        expected_domains = order_count * domains_per_order
        if domain_count != expected_domains and order_count > 1:
            logger.warning(f"Domain count mismatch: have {domain_count} domains, expected {expected_domains} for {order_count} {provider} orders")

        logger.info(f"Provider: {provider}, Order count: {order_count}, Domains: {domain_count}")
        self.wait(1)

        # The page shows two cards: "Hypertide Entra" and "Hypertide Google"
        # Each has a quantity dropdown and a "Select Plan" button
        # We need to: 1) select order quantity from dropdown, 2) click Select Plan

        # STEP 4a: Select order quantity from dropdown (if more than 1)
        if order_count > 1:
            logger.info(f"4a: Selecting {order_count} orders from dropdown...")

            # Find and click the dropdown within the correct provider card
            dropdown_js = """
                (args) => {
                    const { provider, orderCount } = args;
                    const providerText = provider === 'entra' ? 'Hypertide Entra' : 'Hypertide Google';

                    // Find all card-like containers
                    const containers = document.querySelectorAll('div');
                    for (const container of containers) {
                        // Check if this container has the provider name
                        if (container.innerText && container.innerText.includes(providerText)) {
                            // Look for combobox/dropdown within this container
                            const dropdown = container.querySelector('[role="combobox"], [class*="select"], button[aria-haspopup="listbox"]');
                            if (dropdown) {
                                dropdown.click();
                                return { found: true, clicked: true };
                            }
                        }
                    }

                    // Fallback: try to find any combobox with "order" in nearby text
                    const comboboxes = document.querySelectorAll('[role="combobox"], button[aria-haspopup="listbox"]');
                    const providerIndex = provider === 'entra' ? 0 : 1;
                    if (comboboxes.length > providerIndex) {
                        comboboxes[providerIndex].click();
                        return { found: true, clicked: true, method: 'fallback_index' };
                    }

                    return { found: false, available: comboboxes.length };
                }
            """

            try:
                dropdown_result = self.page.evaluate(dropdown_js, {"provider": provider, "orderCount": order_count})
                logger.info(f"Dropdown click result: {dropdown_result}")
                self.wait(1)  # Wait for listbox to open

                if dropdown_result.get("found"):
                    # Select the option matching order count
                    # Format: "6 orders - 12 Entra Domains, 30k emails/mo" (plural for >1)
                    option_prefix = f"{order_count} order" if order_count == 1 else f"{order_count} orders"

                    select_js = """
                        (optionPrefix) => {
                            // Find all options in the open listbox
                            const options = document.querySelectorAll('[role="option"], [role="listbox"] > div, [data-radix-collection-item]');
                            for (const opt of options) {
                                const text = opt.innerText || opt.textContent || '';
                                if (text.startsWith(optionPrefix)) {
                                    opt.click();
                                    return { selected: true, text: text.substring(0, 60) };
                                }
                            }
                            // Fallback: try matching partial text
                            for (const opt of options) {
                                const text = opt.innerText || opt.textContent || '';
                                if (text.includes(optionPrefix)) {
                                    opt.click();
                                    return { selected: true, text: text.substring(0, 60), method: 'partial' };
                                }
                            }
                            // List available options for debugging
                            const available = Array.from(options).map(o => (o.innerText || '').substring(0, 50)).slice(0, 5);
                            return { selected: false, available };
                        }
                    """

                    option_result = self.page.evaluate(select_js, option_prefix)
                    logger.info(f"Option selection result: {option_result}")
                    self.screenshot("step_4a_order_selected")
                    self.wait(0.5)

                    if not option_result.get("selected"):
                        logger.warning(f"Could not select {order_count} orders option. Available: {option_result.get('available')}")
                else:
                    logger.warning(f"Could not find dropdown. Available comboboxes: {dropdown_result.get('available', 0)}")

            except Exception as e:
                logger.error(f"Error selecting order count: {e}")
                # Continue anyway - will use default 1 order

        # STEP 4b: Click Select Plan button for the correct provider
        if provider == "entra":
            # Find the Entra card and click its Select Plan button
            # The Entra card contains "Hypertide Entra" text and has an orange button
            try:
                # Try to click the first "Select Plan" button (Entra is on the left)
                buttons = self.page.locator("button:has-text('Select Plan')").all()
                if len(buttons) >= 1:
                    buttons[0].click(timeout=ELEMENT_TIMEOUT)
                    logger.info("Clicked Select Plan button for Entra")
                else:
                    # Fallback: try text-based click
                    self.click_text("Select Plan")
            except Exception as e:
                logger.error(f"Failed to click Select Plan: {e}")
                return False
        else:
            # For Google, click the second button
            try:
                buttons = self.page.locator("button:has-text('Select Plan')").all()
                if len(buttons) >= 2:
                    buttons[1].click(timeout=ELEMENT_TIMEOUT)
                    logger.info("Clicked Select Plan button for Google")
                else:
                    # Try finding Google-specific button
                    self.page.locator("text=Hypertide Google").locator("..").locator("button:has-text('Select Plan')").click()
            except Exception as e:
                logger.error(f"Failed to click Select Plan for Google: {e}")
                return False

        self.wait(2)
        self.screenshot("step_4_provider_selected")

        # Verify we moved to Select Domains step
        if not self.wait_for_text("Select Domains", timeout=10000):
            # Try looking for domain-related text
            if not self.wait_for_text("domain", timeout=5000):
                logger.warning("May not have navigated to Select Domains page")

        if not self.dry_run:
            if provider == "entra":
                order_count = self.job.get("entra_orders", 1) or 1
            else:
                order_count = self.job.get("google_orders", 1) or 1
            log_step(self.job_id, "select_provider", f"Selected {provider} plan with {order_count} order(s)")

        return True

    def step_5_enter_domains(self) -> bool:
        """Step 5: Select 'Use my own domains' and enter domain names."""
        logger.info("=" * 60)
        logger.info("STEP 5: Enter Domains (BYOD)")
        logger.info("=" * 60)

        domains = self.job.get("domain_names", [])
        if not domains:
            logger.error("No domains to enter")
            return False

        # Step 5a: Click "Use my own domains" option (BYOD)
        logger.info("5a: Selecting 'Use my own domains' option...")
        try:
            self.page.get_by_text("Use my own domains", exact=False).click(timeout=ELEMENT_TIMEOUT)
            logger.info("Clicked 'Use my own domains'")
        except:
            logger.warning("'Use my own domains' not found, trying alternative selectors")
            try:
                # Try clicking the card containing "$0.00"
                self.page.locator("text=$0.00").click(timeout=ELEMENT_TIMEOUT)
            except:
                logger.warning("BYOD option click failed, continuing anyway")

        self.wait(2)
        self.screenshot("step_5a_byod_selected")

        # Step 5b: Wait for Step 2 to expand with domain entry textarea
        logger.info("5b: Waiting for domain entry section to expand...")

        # Wait for the textarea to appear (labeled "Enter domains (one per line)")
        try:
            self.page.wait_for_selector("textarea", timeout=10000)
            logger.info("Domain textarea found")
        except:
            logger.warning("Domain textarea not found, trying to scroll")
            self.page.evaluate("window.scrollBy(0, 300)")
            self.wait(1)

        self.screenshot("step_5b_textarea_visible")

        # Step 5c: Enter all domains in the textarea (one per line)
        logger.info(f"5c: Entering {len(domains)} domains in textarea...")

        # Join domains with newlines
        domains_text = "\n".join(domains)

        try:
            # Find the textarea and fill it
            textarea = self.page.locator("textarea").first
            textarea.fill(domains_text)
            logger.info(f"Filled textarea with domains:\n{domains_text}")
        except Exception as e:
            logger.error(f"Failed to fill domain textarea: {e}")
            self.screenshot("step_5c_textarea_error")
            return False

        self.wait(0.5)
        self.screenshot("step_5c_domains_entered")

        # Step 5d: Click "+ Add Your Domain" button to add the domains
        logger.info("5d: Clicking 'Add Your Domain' button...")
        try:
            add_btn = self.page.locator("button:has-text('Add Your Domain')").first
            add_btn.click(timeout=ELEMENT_TIMEOUT)
            logger.info("Clicked 'Add Your Domain' button")
        except Exception as e:
            logger.warning(f"Could not click 'Add Your Domain': {e}")
            # Try alternative selectors
            try:
                self.page.locator("button:has-text('Add')").first.click(timeout=5000)
            except:
                pass

        self.wait(5)  # Wait longer for domains to be validated and DNS step to appear

        self.screenshot("step_5d_domains_added")

        # Step 5e: Confirm DNS configuration
        # After adding domains, "Step 3) Point your DNS properly" appears
        # We need to click "I have configured DNS" to proceed
        logger.info("5e: Confirming DNS configuration...")

        # Wait for DNS section to fully load and button to be visible
        try:
            self.page.wait_for_selector("button:has-text('I have configured DNS')", timeout=15000)
            logger.info("DNS button is now visible")
        except:
            logger.warning("Waiting for DNS button timed out, trying anyway...")

        # Scroll down to make sure button is visible
        self.page.evaluate("window.scrollBy(0, 300)")
        self.wait(1)

        # Try clicking via JavaScript first (more reliable)
        dns_clicked = self.page.evaluate("""
            () => {
                const btn = Array.from(document.querySelectorAll('button')).find(
                    b => b.innerText?.includes('I have configured DNS')
                );
                if (btn) {
                    btn.scrollIntoView();
                    btn.click();
                    return { clicked: true };
                }
                return { clicked: false };
            }
        """)
        logger.info(f"DNS button JS click: {dns_clicked}")

        if not dns_clicked.get('clicked'):
            try:
                dns_btn = self.page.locator("button:has-text('I have configured DNS')").first
                dns_btn.click(force=True, timeout=5000)
                logger.info("Clicked 'I have configured DNS' via locator")
            except Exception as e:
                logger.warning(f"'I have configured DNS' button not found: {e}")

        self.wait(3)
        self.screenshot("step_5e_dns_confirmed")

        # Step 5f: Click "Continue to Domain Settings" to proceed
        logger.info("5f: Clicking 'Continue to Domain Settings'...")

        # Wait for the button to be enabled
        self.wait(2)

        # Try JavaScript click first
        continue_clicked = self.page.evaluate("""
            () => {
                const btn = Array.from(document.querySelectorAll('button')).find(
                    b => b.innerText?.includes('Continue to Domain Settings')
                );
                if (btn && !btn.disabled) {
                    btn.click();
                    return { clicked: true };
                }
                return { clicked: false, disabled: btn?.disabled };
            }
        """)
        logger.info(f"Continue button JS click: {continue_clicked}")

        if not continue_clicked.get('clicked'):
            try:
                continue_btn = self.page.locator("button:has-text('Continue to Domain Settings')").first
                continue_btn.click(force=True, timeout=10000)
                logger.info("Clicked 'Continue to Domain Settings'")
            except Exception as e:
                logger.warning(f"Continue button click failed: {e}")

        self.wait(3)

        if not self.dry_run:
            log_step(self.job_id, "domains_entered", f"Entered {len(domains)} domains: {domains}")

        return True

    def step_6_basic_config(self) -> bool:
        """Step 6: Fill basic configuration (forwarding domain, company name)."""
        logger.info("=" * 60)
        logger.info("STEP 6: Basic Configuration")
        logger.info("=" * 60)

        # Wait for the config form
        self.wait_for_text("What URL should we forward", timeout=10000)

        forwarding_domain = self.job.get("forwarding_domain", "")
        company_name = self.job.get("company_name", "")

        # Fill forwarding domain
        try:
            self.fill_input("input[placeholder*='example.com']", forwarding_domain)
        except:
            # Fallback: find first text input
            inputs = self.page.locator("input[type='text']").all()
            if len(inputs) >= 1:
                inputs[0].fill(forwarding_domain)

        # Fill company name
        try:
            self.fill_input("input[placeholder*='Acme']", company_name)
        except:
            inputs = self.page.locator("input[type='text']").all()
            if len(inputs) >= 2:
                inputs[1].fill(company_name)

        self.wait(0.5)
        self.screenshot("step_6_basic_config")

        # Save configuration
        try:
            self.click_text("Save Basic Configuration")
        except:
            try:
                self.click_text("Save")
            except:
                self.page.keyboard.press("Enter")

        self.wait(2)

        # Verify Step 2 expanded
        if not self.wait_for_text("Connect Your Email Automation Tool", timeout=10000):
            logger.warning("Step 2 may not have expanded")

        if not self.dry_run:
            log_step(self.job_id, "basic_config",
                    f"Forwarding: {forwarding_domain}, Company: {company_name}")

        return True

    def step_7_bison_config(self) -> bool:
        """Step 7: Configure Bison email tool - SELECT BISON FIRST."""
        logger.info("=" * 60)
        logger.info("STEP 7: Bison Email Tool Configuration")
        logger.info("=" * 60)

        workspace_name = self.job.get("bison_workspace_name", "Charm")

        # STEP 7a: SELECT BISON - This MUST succeed before anything else
        logger.info("7a: SELECTING BISON TOOL...")
        self.screenshot("step_7a_before")

        # Scroll to make sure tool buttons are visible
        self.page.evaluate("window.scrollTo(0, 400)")
        self.wait(0.5)

        # Use JavaScript to click the Bison button by finding the container
        # The buttons are styled divs with text: Instantly | Smartlead | Bison | Other
        bison_selected = self.page.evaluate("""
            () => {
                // Find the "Select your email tool:" label first
                const labels = document.querySelectorAll('*');
                let toolRow = null;

                for (const el of labels) {
                    if (el.textContent?.includes('Select your email tool')) {
                        // The buttons should be nearby
                        toolRow = el.closest('div')?.parentElement || el.parentElement;
                        break;
                    }
                }

                // Find all divs that could be tool buttons
                const allDivs = document.querySelectorAll('div');
                const candidates = [];

                for (const div of allDivs) {
                    const text = div.innerText?.trim();
                    // Look for divs that contain tool names
                    if (text === 'Instantly' || text === 'Smartlead' || text === 'Bison' || text === 'Other') {
                        candidates.push({ el: div, text: text });
                    }
                }

                // Find and click the Bison one
                for (const c of candidates) {
                    if (c.text === 'Bison') {
                        // Click the element and all its parents up to 3 levels
                        c.el.click();
                        if (c.el.parentElement) {
                            c.el.parentElement.click();
                        }
                        return { clicked: true, text: c.text };
                    }
                }

                // Alternative: Find by looking for sibling of Instantly
                const instantlyDiv = Array.from(allDivs).find(d => d.innerText?.trim() === 'Instantly');
                if (instantlyDiv && instantlyDiv.parentElement) {
                    const siblings = instantlyDiv.parentElement.children;
                    for (const sib of siblings) {
                        if (sib.innerText?.trim() === 'Bison') {
                            sib.click();
                            return { clicked: true, method: 'sibling' };
                        }
                    }
                }

                return { clicked: false, candidates: candidates.length };
            }
        """)
        logger.info(f"Bison click attempt 1: {bison_selected}")
        self.wait(2)
        self.screenshot("step_7a_after_click1")

        # CHECK: Did Bison get selected?
        # When Bison is selected, the form shows "Bison URL" field
        page_html = self.page.content()
        if 'placeholder="https://api.emailbison.com"' not in page_html and 'Bison URL' not in page_html:
            logger.warning("Bison may not be selected. Trying force click...")

            # Force click using bounding box
            try:
                bison_text = self.page.get_by_text("Bison", exact=True)
                box = bison_text.bounding_box()
                if box:
                    # Click in the center of the bounding box
                    self.page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                    logger.info(f"Force clicked at Bison coordinates: {box}")
            except Exception as e:
                logger.warning(f"Bounding box click failed: {e}")

            self.wait(2)
            self.screenshot("step_7a_after_force_click")

        # Final verification
        page_text = self.page.inner_text("body")
        if "Bison URL" not in page_text and "https://api.emailbison.com" not in page_text:
            # Check if we at least have Username/Password fields (might work)
            if "Username" in page_text and "Password" in page_text:
                logger.warning("Bison URL field not found but credentials fields exist")
            else:
                logger.error("CRITICAL: Bison selection FAILED!")
                self.screenshot("step_7a_FAILED")
                return False

        logger.info("Bison selected successfully")
        self.screenshot("step_7a_bison_confirmed")

        # Step 7b: Fill Username, Password, Bison URL (IN ORDER)
        # Use job-specific credentials, fallback to env vars for test mode
        bison_username = self.job.get("bison_username") or BISON_USERNAME
        bison_password = self.job.get("bison_password") or BISON_PASSWORD
        bison_url = self.job.get("bison_url") or BISON_URL

        logger.info("7b: Filling Bison credentials...")
        logger.info(f"Using credentials: username={bison_username}, url={bison_url}")

        # 1. Username - placeholder is "name@example.com"
        try:
            username_input = self.page.locator("input[placeholder*='name@example']").first
            username_input.fill(bison_username)
            logger.info(f"Filled Username: {bison_username}")
        except Exception as e:
            logger.warning(f"Username fill by placeholder failed: {e}")
            try:
                # Try first text input in the form
                self.page.locator("input[type='text'], input[type='email']").first.fill(bison_username)
                logger.info(f"Filled Username via first input: {bison_username}")
            except:
                logger.error("Could not fill Username field")

        # 2. Password
        try:
            self.fill_input("input[type='password']", bison_password)
            logger.info("Filled Password")
        except Exception as e:
            logger.error(f"Could not fill Password: {e}")

        # 3. Bison URL - placeholder is "https://send.example.com"
        try:
            url_input = self.page.locator("input[placeholder*='send.example']").first
            url_input.fill(bison_url)
            logger.info(f"Filled Bison URL: {bison_url}")
        except Exception as e:
            logger.warning(f"Bison URL fill by placeholder failed: {e}")
            try:
                # Try by looking for input near "Bison URL" label
                self.page.locator("input").filter(has=self.page.locator("text=Bison URL")).first.fill(bison_url)
                logger.info(f"Filled Bison URL via label: {bison_url}")
            except:
                logger.error("Could not fill Bison URL field")

        self.wait(1)
        self.screenshot("step_7b_credentials_filled")

        # Step 7c: Open workspace selector
        logger.info("7c: Opening workspace selector...")
        try:
            self.click_text("Click to select workspace")
        except:
            try:
                self.click_text("Select workspace")
            except:
                logger.warning("Workspace selector not found")

        self.wait(1)

        # Step 7d: Fill API key and fetch workspaces
        # Use job-specific API key, fallback to env var for test mode
        bison_api_key = self.job.get("bison_api_key") or BISON_API_KEY
        logger.info("7d: Filling API key and fetching workspaces...")
        try:
            self.fill_input("input[placeholder*='API']", bison_api_key)
        except:
            try:
                # Find input near "API Key" label
                api_input = self.page.locator("input").filter(has=self.page.locator("text=API")).first
                api_input.fill(bison_api_key)
            except:
                pass

        # Click Fetch Workspaces
        try:
            self.click_text("Fetch Workspaces")
        except:
            try:
                self.click_text("Fetch")
            except:
                pass

        self.wait(3)  # Wait for API call

        # Step 7e: Select workspace from scrollable modal
        # CRITICAL: Uses JavaScript-only approach to avoid Playwright bug #9073
        # (scroll conflict in modal causes click to never complete)
        logger.info(f"7e: Selecting workspace: {workspace_name}")

        # Wait for modal to appear and stabilize
        self.wait(2)
        self.screenshot("step_7e_modal_before_scroll")

        # PHASE 1: Detect and log modal state
        modal_info = self.page.evaluate("""
            () => {
                // Find all potential modal/dropdown containers
                const containers = [];

                // Look for elements with modal/popup/dropdown classes or roles
                const candidates = document.querySelectorAll(
                    '[class*="modal"], [class*="popup"], [class*="dropdown"], [class*="listbox"], ' +
                    '[class*="menu"], [role="listbox"], [role="dialog"], [role="menu"]'
                );

                for (const el of candidates) {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (rect.width > 50 && rect.height > 50 &&
                        rect.top >= 0 && rect.left >= 0 &&
                        style.display !== 'none' && style.visibility !== 'hidden') {
                        containers.push({
                            tag: el.tagName,
                            className: el.className,
                            role: el.getAttribute('role'),
                            scrollable: el.scrollHeight > el.clientHeight,
                            height: rect.height,
                            scrollHeight: el.scrollHeight,
                            childCount: el.children.length
                        });
                    }
                }

                // Also find any visible scrollable containers
                const allDivs = document.querySelectorAll('div');
                for (const div of allDivs) {
                    const rect = div.getBoundingClientRect();
                    const style = window.getComputedStyle(div);
                    const isScrollable = (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                                        div.scrollHeight > div.clientHeight;

                    if (isScrollable && rect.width > 100 && rect.height > 50 && rect.height < 500) {
                        containers.push({
                            tag: 'div',
                            className: div.className.substring(0, 50),
                            scrollable: true,
                            height: rect.height,
                            scrollHeight: div.scrollHeight,
                            childCount: div.children.length
                        });
                    }
                }

                return { containers: containers.slice(0, 5) };
            }
        """)
        logger.info(f"Modal detection: {modal_info}")

        # PHASE 2: Find and click workspace using JAVASCRIPT ONLY
        # (Avoids Playwright bug #9073 where scroll-click conflicts in modals)
        workspace_found = self.page.evaluate("""
            (workspaceName) => {
                const log = [];

                // Helper: Find the scrollable modal container
                function findScrollableModal() {
                    // Priority 1: Look for role="listbox" or role="menu"
                    const roleContainers = document.querySelectorAll('[role="listbox"], [role="menu"]');
                    for (const c of roleContainers) {
                        const rect = c.getBoundingClientRect();
                        if (rect.height > 50 && rect.width > 50) {
                            log.push('Found by role: ' + c.getAttribute('role'));
                            return c;
                        }
                    }

                    // Priority 2: Find divs with overflow:auto/scroll that are visible
                    const allDivs = document.querySelectorAll('div');
                    for (const div of allDivs) {
                        const style = window.getComputedStyle(div);
                        const rect = div.getBoundingClientRect();
                        const isScrollable = (style.overflowY === 'auto' || style.overflowY === 'scroll') &&
                                            div.scrollHeight > div.clientHeight;
                        const isVisible = rect.height > 50 && rect.height < 500 && rect.width > 100;

                        if (isScrollable && isVisible) {
                            // Check if it contains multiple clickable children (options)
                            const clickableChildren = div.querySelectorAll('div, li, button, [role="option"]');
                            if (clickableChildren.length >= 2) {
                                log.push('Found scrollable div with ' + clickableChildren.length + ' children');
                                return div;
                            }
                        }
                    }

                    // Priority 3: Find by class names
                    const classSelectors = ['[class*="workspace"]', '[class*="dropdown"]', '[class*="select"]', '[class*="menu"]'];
                    for (const sel of classSelectors) {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const rect = el.getBoundingClientRect();
                            if (el.scrollHeight > el.clientHeight && rect.height > 50) {
                                log.push('Found by class: ' + sel);
                                return el;
                            }
                        }
                    }

                    return null;
                }

                // Helper: Find workspace element by text
                function findWorkspaceElement(container) {
                    // Search within the container first
                    const searchArea = container || document.body;
                    const elements = searchArea.querySelectorAll('*');

                    for (const el of elements) {
                        // Get direct text content, not including children
                        const directText = el.childNodes.length > 0 ?
                            Array.from(el.childNodes)
                                .filter(n => n.nodeType === Node.TEXT_NODE)
                                .map(n => n.textContent.trim())
                                .join('') : '';

                        const innerText = el.innerText?.trim();

                        if (directText === workspaceName || innerText === workspaceName) {
                            return el;
                        }
                    }

                    // If not in container, search entire document
                    if (container) {
                        const allElements = document.querySelectorAll('*');
                        for (const el of allElements) {
                            if (el.innerText?.trim() === workspaceName &&
                                el.offsetWidth > 0 && el.offsetHeight > 0) {
                                return el;
                            }
                        }
                    }

                    return null;
                }

                // Helper: Scroll within container to find element
                function scrollToFind(container, targetName) {
                    if (!container) return null;

                    const scrollStep = 100;
                    const maxScrolls = Math.ceil(container.scrollHeight / scrollStep) + 1;

                    // Reset to top
                    container.scrollTop = 0;

                    for (let i = 0; i < maxScrolls; i++) {
                        // Check for element after each scroll
                        const el = findWorkspaceElement(container);
                        if (el) {
                            log.push('Found after scroll step ' + i);
                            return el;
                        }

                        // Scroll down
                        container.scrollTop += scrollStep;

                        // Wait briefly for DOM update (sync check)
                        if (container.scrollTop >= container.scrollHeight - container.clientHeight) {
                            log.push('Reached scroll bottom at step ' + i);
                            break;
                        }
                    }

                    return null;
                }

                // MAIN LOGIC

                // Step 1: Find the modal container
                const modal = findScrollableModal();
                log.push(modal ? 'Modal found' : 'No modal found');

                // Step 2: Try to find workspace directly first (visible without scroll)
                let workspaceEl = findWorkspaceElement(modal);

                // Step 3: If not found, scroll through modal
                if (!workspaceEl && modal) {
                    log.push('Workspace not visible, scrolling...');
                    workspaceEl = scrollToFind(modal, workspaceName);
                }

                // Step 4: If still not found, search entire page
                if (!workspaceEl) {
                    log.push('Searching entire page...');
                    workspaceEl = findWorkspaceElement(null);
                }

                // Step 5: Click if found
                if (workspaceEl) {
                    // Scroll element into view within its container
                    workspaceEl.scrollIntoView({ block: 'center', behavior: 'instant' });

                    // Brief delay for scroll to settle
                    // CRITICAL: Use native JS click to avoid Playwright bug #9073
                    workspaceEl.click();

                    // Also try clicking parent if it's a wrapper element
                    const parent = workspaceEl.parentElement;
                    if (parent && (parent.tagName === 'LI' || parent.getAttribute('role') === 'option' ||
                        parent.className.includes('item') || parent.className.includes('option'))) {
                        parent.click();
                        log.push('Also clicked parent: ' + parent.tagName);
                    }

                    return {
                        found: true,
                        method: 'js_click',
                        text: workspaceEl.innerText?.substring(0, 50),
                        tag: workspaceEl.tagName,
                        log: log
                    };
                }

                // Step 6: List available options for debugging
                const availableOptions = [];
                if (modal) {
                    const items = modal.querySelectorAll('div, li, [role="option"]');
                    for (const item of items) {
                        const text = item.innerText?.trim();
                        if (text && text.length < 50 && text.length > 1) {
                            availableOptions.push(text);
                        }
                    }
                }

                return {
                    found: false,
                    log: log,
                    availableOptions: [...new Set(availableOptions)].slice(0, 10)
                };
            }
        """, workspace_name)

        logger.info(f"Workspace search result: {workspace_found}")

        if not workspace_found.get('found'):
            # Log available options for debugging
            available = workspace_found.get('availableOptions', [])
            if available:
                logger.error(f"Workspace '{workspace_name}' NOT FOUND. Available options: {available}")
            else:
                logger.error(f"Workspace '{workspace_name}' NOT FOUND. No options detected in modal.")

            self.screenshot("step_7e_workspace_not_found")

            # One final fallback: try keyboard navigation
            logger.warning("Attempting keyboard navigation fallback...")
            keyboard_result = self.page.evaluate("""
                (workspaceName) => {
                    // Find any focused element or first option
                    const options = document.querySelectorAll('[role="option"], [class*="option"], [class*="item"]');
                    for (const opt of options) {
                        if (opt.innerText?.trim() === workspaceName) {
                            opt.focus();
                            opt.click();
                            return { found: true, method: 'keyboard_fallback' };
                        }
                    }
                    return { found: false };
                }
            """, workspace_name)

            if not keyboard_result.get('found'):
                if not self.dry_run:
                    fail_job(self.job_id,
                            f"WORKSPACE NOT FOUND: '{workspace_name}' not in dropdown. Available: {available}",
                            "bison_workspace_selection", "config")
                return False
            else:
                logger.info("Keyboard fallback succeeded")

        self.wait(1)
        self.screenshot("step_7e_workspace_selected")

        # VERIFY: Check that workspace was actually selected by reading the form field
        # Wait for modal to close and form to update
        self.wait(1)
        logger.info("Verifying workspace selection in form field...")

        selected_workspace = self.page.evaluate("""
            (expectedName) => {
                const log = [];

                // Method 1: Look for the workspace selector trigger/button that should now show the selected value
                // Common patterns: a div/button that shows "Click to select" or the workspace name
                const selectorTriggers = document.querySelectorAll(
                    '[class*="workspace"], [class*="select"], [class*="dropdown"], ' +
                    'button, [role="combobox"], [role="button"]'
                );

                for (const el of selectorTriggers) {
                    const text = el.innerText?.trim() || el.value || '';
                    // The trigger should now show the workspace name, not "Click to select"
                    if (text === expectedName) {
                        log.push('Found in trigger: ' + el.tagName);
                        return { found: true, value: text, method: 'trigger', log };
                    }
                }

                // Method 2: Look for input fields that might hold the workspace value
                const inputs = document.querySelectorAll('input');
                for (const input of inputs) {
                    if (input.value === expectedName ||
                        input.placeholder?.toLowerCase().includes('workspace')) {
                        if (input.value === expectedName) {
                            log.push('Found in input value');
                            return { found: true, value: input.value, method: 'input', log };
                        }
                    }
                }

                // Method 3: Check various UI framework patterns for selected values
                const valueSelectors = [
                    '[class*="workspace"] [class*="value"]',
                    '[class*="workspace"] [class*="selected"]',
                    '[class*="select"] [class*="single-value"]',  // React-Select
                    '[class*="select"] [class*="value-container"]',
                    '[class*="dropdown"] [class*="value"]',
                    '[data-value]',
                    '[class*="chosen"]'
                ];

                for (const selector of valueSelectors) {
                    const els = document.querySelectorAll(selector);
                    for (const el of els) {
                        const text = el.innerText?.trim() || el.getAttribute('data-value') || '';
                        if (text === expectedName) {
                            log.push('Found via selector: ' + selector);
                            return { found: true, value: text, method: 'selector', selector, log };
                        }
                    }
                }

                // Method 4: Look in the Step 2/Connect Your Email section specifically
                const stepSections = document.querySelectorAll('[class*="step"], [class*="section"], [class*="card"]');
                for (const section of stepSections) {
                    const sectionText = section.innerText || '';
                    // Check if this is the email tool section
                    if (sectionText.includes('Connect Your Email') || sectionText.includes('email tool') ||
                        sectionText.includes('Bison')) {
                        // Look for the workspace name in this section
                        if (sectionText.includes(expectedName)) {
                            // Make sure it's in the workspace field area, not just mentioned
                            if (sectionText.includes('Workspace') && sectionText.includes(expectedName)) {
                                log.push('Found in email tool section');
                                return { found: true, value: expectedName, method: 'section', log };
                            }
                        }
                    }
                }

                // Method 5: Regex search in page text near "Workspace" label
                const allText = document.body.innerText;
                const patterns = [
                    new RegExp('Workspace[:\\\\s]+([A-Za-z0-9\\\\s-]+?)(?:\\\\n|Select|Username|Password|$)', 'i'),
                    new RegExp('Select workspace[:\\\\s]+([A-Za-z0-9\\\\s-]+?)(?:\\\\n|$)', 'i')
                ];

                for (const pattern of patterns) {
                    const match = allText.match(pattern);
                    if (match && match[1] && match[1].trim() === expectedName) {
                        log.push('Found via regex: ' + pattern.source);
                        return { found: true, value: match[1].trim(), method: 'regex', log };
                    }
                }

                // Log what we did find for debugging
                const visibleText = allText.substring(0, 500);
                log.push('Searched entire page, workspace name not confirmed in form field');

                return { found: false, log, pageSnippet: visibleText };
            }
        """, workspace_name)

        logger.info(f"Workspace verification result: {selected_workspace}")

        if not selected_workspace.get('found'):
            # Check if at least the modal closed and we can see the form
            page_text = self.page.inner_text("body")
            if workspace_name in page_text:
                logger.info(f"Workspace '{workspace_name}' found in page text - selection likely succeeded")
            else:
                self.screenshot("step_7e_workspace_verification_failed")
                logger.error(f"WORKSPACE SELECTION FAILED: '{workspace_name}' not found in form field!")
                logger.error("The workspace must appear in the form field after selection.")

                if not self.dry_run:
                    fail_job(self.job_id,
                            f"WORKSPACE NOT SELECTED: '{workspace_name}' not showing in form",
                            "bison_workspace_selection", "config")
                return False

        logger.info(f"✓ Workspace '{workspace_name}' confirmed in form")

        # Step 7f: Click "Move on without saving" to proceed
        logger.info("7f: Clicking 'Move on without saving' to proceed...")

        # Scroll down to make sure the button is visible
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.wait(0.5)

        # Screenshot before clicking to verify button is visible
        self.screenshot("step_7f_before_move_on")

        # Try JavaScript first - scroll to button and click
        move_on_result = self.page.evaluate("""
            () => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText?.includes('Move on without saving'));
                if (btn) {
                    btn.scrollIntoView({ block: 'center' });
                    // Small delay then click
                    btn.click();
                    return { clicked: true, text: btn.innerText };
                }
                // List available buttons for debugging
                const available = buttons.map(b => b.innerText?.trim()).filter(t => t);
                return { clicked: false, available };
            }
        """)
        logger.info(f"Move on button JS result: {move_on_result}")

        if not move_on_result.get('clicked'):
            # Fallback: use Playwright locator with force click
            logger.info("JS click failed, trying Playwright locator...")
            try:
                move_on_btn = self.page.locator("button:has-text('Move on without saving')").first
                move_on_btn.scroll_into_view_if_needed()
                self.wait(0.3)
                move_on_btn.click(force=True, timeout=5000)
                logger.info("Clicked 'Move on without saving' via locator")
            except Exception as e:
                logger.error(f"Could not click 'Move on without saving': {e}")
                # Last resort: try clicking by coordinates
                try:
                    box = self.page.locator("button:has-text('Move on')").first.bounding_box()
                    if box:
                        self.page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        logger.info(f"Clicked 'Move on' button at coordinates: {box}")
                except:
                    pass

        # Wait for the section to collapse
        self.wait(2)
        self.screenshot("step_7f_after_move_on")

        # Verify: Check if Step 2 (Bison) section collapsed and Step 3 (Warmup) is visible
        # The Step 2 header should now have a checkmark
        page_text = self.page.inner_text("body")

        # Check if we can see Step 3 (Warmup) as the next active section
        if "Warmup & Tags" in page_text:
            logger.info("✓ Step 3 (Warmup & Tags) is now visible - Step 2 completed successfully")
        else:
            logger.warning("Step 3 (Warmup & Tags) not visible - checking page state...")
            # Take diagnostic screenshot
            self.screenshot("step_7f_diagnostic")

        if not self.dry_run:
            log_step(self.job_id, "bison_config",
                    f"Bison configured. Workspace: {workspace_name}")

        return True

    def _expand_and_save_section(self, section_text: str, save_button_text: str, section_num: int) -> bool:
        """
        Helper to expand a Hypertide accordion section and click its save button.
        Used by Steps 8, 9, 10 to handle the accordion pattern consistently.
        """
        logger.info(f"Expanding section: {section_text}")

        # STEP 1: Click the accordion header to expand
        # The accordion headers are divs with "Step N) ..." text
        expand_result = self.page.evaluate("""
            (args) => {
                const { sectionText, sectionNum } = args;
                const log = [];

                // Method 1: Find the exact accordion header by step number pattern
                const stepPattern = `Step ${sectionNum})`;
                const allDivs = document.querySelectorAll('div');

                for (const div of allDivs) {
                    const text = div.innerText?.trim();
                    // The accordion header contains "Step N) Section Name" and is clickable
                    if (text && text.startsWith(stepPattern)) {
                        log.push(`Found header: ${text.substring(0, 50)}`);

                        // Check if this is the clickable row (not a container)
                        const rect = div.getBoundingClientRect();
                        if (rect.height > 30 && rect.height < 100 && rect.width > 200) {
                            div.scrollIntoView({ block: 'center' });
                            div.click();
                            log.push('Clicked header div');
                            return { clicked: true, method: 'step_pattern', log };
                        }
                    }
                }

                // Method 2: Find by partial text match
                for (const div of allDivs) {
                    const text = div.innerText?.trim();
                    if (text && text.includes(sectionText) && !text.includes('Save')) {
                        const rect = div.getBoundingClientRect();
                        // Accordion headers are typically 40-80px tall
                        if (rect.height > 30 && rect.height < 100) {
                            div.scrollIntoView({ block: 'center' });
                            div.click();
                            log.push(`Clicked by text match: ${text.substring(0, 40)}`);
                            return { clicked: true, method: 'text_match', log };
                        }
                    }
                }

                // Method 3: Look for clickable card/row that contains the text
                const cards = document.querySelectorAll('[class*="card"], [class*="accordion"], [class*="collapse"]');
                for (const card of cards) {
                    if (card.innerText?.includes(sectionText)) {
                        card.scrollIntoView({ block: 'center' });
                        card.click();
                        log.push('Clicked card element');
                        return { clicked: true, method: 'card', log };
                    }
                }

                return { clicked: false, log };
            }
        """, {"sectionText": section_text, "sectionNum": section_num})

        logger.info(f"Expand result: {expand_result}")
        self.wait(2)  # Wait for accordion animation

        # STEP 2: Verify expansion by looking for the save button
        self.screenshot(f"step_{section_num + 5}_after_expand")

        # Scroll down to reveal save button
        self.page.evaluate("window.scrollBy(0, 300)")
        self.wait(0.5)

        # STEP 3: Click the save button
        logger.info(f"Looking for '{save_button_text}' button...")
        save_clicked = False

        # Try Playwright locator first
        try:
            save_btn = self.page.locator(f"button:has-text('{save_button_text}')").first
            if save_btn.is_visible(timeout=5000):
                save_btn.scroll_into_view_if_needed()
                self.wait(0.3)
                save_btn.click(timeout=5000)
                logger.info(f"Clicked '{save_button_text}' via locator")
                save_clicked = True
        except Exception as e:
            logger.debug(f"Locator failed: {e}")

        # Fallback to JavaScript
        if not save_clicked:
            logger.info("Trying JavaScript to click save button...")
            save_result = self.page.evaluate("""
                (btnText) => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const saveBtn = buttons.find(b => b.innerText?.includes(btnText));
                    if (saveBtn && saveBtn.offsetParent !== null) {
                        saveBtn.scrollIntoView({ block: 'center' });
                        saveBtn.click();
                        return { clicked: true, text: saveBtn.innerText };
                    }
                    // List available buttons for debugging
                    const available = buttons
                        .filter(b => b.offsetParent !== null)
                        .map(b => b.innerText?.trim().substring(0, 40))
                        .filter(t => t);
                    return { clicked: false, available };
                }
            """, save_button_text)
            logger.info(f"JS save result: {save_result}")
            if save_result.get("clicked"):
                save_clicked = True
            else:
                logger.warning(f"Save button not found. Available buttons: {save_result.get('available', [])}")

        self.wait(2)  # Wait for section to collapse and next to expand
        return save_clicked

    def step_8_warmup_settings(self) -> bool:
        """Step 8: Accept default warmup settings (Hypertide Step 3)."""
        logger.info("=" * 60)
        logger.info("STEP 8: Warmup Settings (Step 3 in Hypertide)")
        logger.info("=" * 60)

        self.wait(1)

        # Use the helper to expand and save
        save_clicked = self._expand_and_save_section(
            section_text="Warmup & Tags Setup",
            save_button_text="Save Warmup & Tags Configuration",
            section_num=3
        )

        self.screenshot("step_8_warmup")

        if not save_clicked:
            logger.warning("Could not confirm save button click for Warmup settings")
            # Don't fail - the section might auto-progress

        if not self.dry_run:
            log_step(self.job_id, "warmup_settings", "Saved warmup settings")

        return True

    def step_9_outbound_settings(self) -> bool:
        """Step 9: Accept default outbound settings (Hypertide Step 4)."""
        logger.info("=" * 60)
        logger.info("STEP 9: Outbound Settings (Step 4 in Hypertide)")
        logger.info("=" * 60)

        self.wait(1)

        # Use the helper to expand and save
        save_clicked = self._expand_and_save_section(
            section_text="Outbound Settings",
            save_button_text="Save Outbound Settings",
            section_num=4
        )

        self.screenshot("step_9_outbound")

        if not save_clicked:
            logger.warning("Could not confirm save button click for Outbound settings")
            # Don't fail - the section might auto-progress

        if not self.dry_run:
            log_step(self.job_id, "outbound_settings", "Saved outbound settings")

        return True

    def step_10_sender_names(self) -> bool:
        """Step 10: Configure sender names (Hypertide Step 5) and navigate to Review Order."""
        logger.info("=" * 60)
        logger.info("STEP 10: Sender Names (Step 5 in Hypertide) + Navigate to Review")
        logger.info("=" * 60)

        # FIRST: Expand the User Configuration section (Step 5)
        logger.info("Expanding User Configuration section...")
        expand_result = self.page.evaluate("""
            () => {
                const log = [];
                const allDivs = document.querySelectorAll('div');

                // Find "Step 5) Setup Your User Configuration" accordion header
                for (const div of allDivs) {
                    const text = div.innerText?.trim();
                    if (text && (text.startsWith('Step 5)') || text.includes('User Configuration'))) {
                        const rect = div.getBoundingClientRect();
                        // Accordion headers are typically 40-80px tall
                        if (rect.height > 30 && rect.height < 100 && rect.width > 200) {
                            div.scrollIntoView({ block: 'center' });
                            div.click();
                            log.push(`Clicked: ${text.substring(0, 50)}`);
                            return { clicked: true, log };
                        }
                    }
                }
                return { clicked: false, log };
            }
        """)
        logger.info(f"User Config section expand result: {expand_result}")
        self.wait(2)  # Wait for accordion animation

        # Dismiss any modal overlays
        logger.info("Dismissing any modal overlays...")

        # Method 1: Press Escape multiple times
        for _ in range(3):
            self.page.keyboard.press("Escape")
            self.wait(0.3)

        # Method 2: Click any visible overlay backgrounds
        self.page.evaluate("""
            () => {
                // Find and close any modal overlays
                const overlays = document.querySelectorAll('.fixed.inset-0, [class*="modal"], [class*="overlay"]');
                overlays.forEach(el => {
                    if (el.classList.contains('bg-black') || el.classList.contains('bg-opacity')) {
                        el.click();
                    }
                });

                // Also find and click any close buttons in modals
                const closeButtons = document.querySelectorAll('[class*="modal"] button, [aria-label="Close"]');
                closeButtons.forEach(btn => {
                    const text = btn.innerText?.toLowerCase() || '';
                    if (text.includes('close') || text.includes('cancel') || text.includes('x')) {
                        btn.click();
                    }
                });
            }
        """)
        self.wait(0.5)

        # Method 3: Click outside modal area at the top-left corner
        self.page.mouse.click(10, 10)
        self.wait(0.5)

        # Get base sender name from job data (loaded from client's onboarding_data.baseSenderNames)
        # The 52 name variations (preGeneratedSenderNames) are for internal use only
        # In Hypertide, we just add ONE user with the base sender name
        base_name = self.job.get("base_sender_name", {})

        if not base_name:
            # Fallback to client contact name
            contact_name = self.job.get("client_contact_name", "")
            if contact_name:
                parts = contact_name.split(" ", 1)
                base_name = {
                    "firstName": parts[0],
                    "lastName": parts[1] if len(parts) > 1 else "User"
                }
            else:
                # Default fallback
                base_name = {"firstName": "Chris", "lastName": "Booth"}

        first_name = base_name.get("firstName", "Chris")
        last_name = base_name.get("lastName", "Booth")

        logger.info(f"Will add sender name to Hypertide: {first_name} {last_name}")

        # Step 5 should auto-expand after Step 4 saves
        self.wait(1)

        # Scroll to make sure the User Configuration section is visible
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight - 500)")
        self.wait(0.5)
        self.screenshot("step_10a_before_input")

        # Add the base sender name (ONE user) - USE JAVASCRIPT for React inputs
        logger.info(f"Adding sender: {first_name} {last_name}")

        # Use comprehensive JavaScript approach that works with React
        # This properly triggers React's synthetic event system
        add_result = self.page.evaluate("""
            (args) => {
                const { firstName, lastName } = args;

                // Helper to simulate native input behavior for React
                function simulateNativeInput(input, value) {
                    // Focus the input
                    input.focus();

                    // Clear existing value
                    input.value = '';
                    input.dispatchEvent(new Event('input', { bubbles: true }));

                    // Get the native setter
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;

                    // Set value using native setter
                    nativeInputValueSetter.call(input, value);

                    // Reset the tracker so React sees this as a change
                    const tracker = input._valueTracker;
                    if (tracker) {
                        tracker.setValue('');  // Set to empty so React sees a change
                    }

                    // Fire the input event - this is what React listens for
                    const inputEvent = new Event('input', { bubbles: true });
                    input.dispatchEvent(inputEvent);

                    // Also fire change event
                    const changeEvent = new Event('change', { bubbles: true });
                    input.dispatchEvent(changeEvent);

                    return input.value;
                }

                const firstInput = document.querySelector("input[placeholder*='first name'], input[placeholder*='First']");
                const lastInput = document.querySelector("input[placeholder*='last name'], input[placeholder*='Last']");

                let result = { firstName: null, lastName: null };

                if (firstInput) {
                    result.firstName = simulateNativeInput(firstInput, firstName);
                }

                if (lastInput) {
                    result.lastName = simulateNativeInput(lastInput, lastName);
                    // Blur to trigger any onBlur handlers
                    lastInput.blur();
                }

                return result;
            }
        """, {"firstName": first_name, "lastName": last_name})

        logger.info(f"JavaScript input result: {add_result}")
        self.wait(0.5)

        # Verify the values are actually in the inputs
        verify_result = self.page.evaluate("""
            () => {
                const firstInput = document.querySelector("input[placeholder*='first name'], input[placeholder*='First']");
                const lastInput = document.querySelector("input[placeholder*='last name'], input[placeholder*='Last']");
                return {
                    firstName: firstInput?.value || '',
                    lastName: lastInput?.value || ''
                };
            }
        """)
        logger.info(f"Verified input values: {verify_result}")

        self.screenshot("step_10b_after_input")

        # Click "+ Add User" button using JavaScript (most reliable)
        logger.info("Clicking 'Add User' button...")

        add_clicked = self.page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('button'));
                const addBtn = btns.find(b => b.innerText?.includes('Add User'));
                if (addBtn) {
                    addBtn.scrollIntoView({ block: 'center' });
                    addBtn.click();
                    return { clicked: true, text: addBtn.innerText };
                }
                return { clicked: false };
            }
        """)
        logger.info(f"Add User button click result: {add_clicked}")

        self.wait(1)

        # Verify user was added - check for the user row in the table
        page_text = self.page.inner_text("body")
        user_added = "No users added yet" not in page_text

        if user_added:
            logger.info(f"✓ Added user: {first_name} {last_name}")
        else:
            logger.warning("First attempt failed - trying keyboard input method...")

            # Retry with keyboard input method (type character by character)
            try:
                # Focus first name input
                first_input = self.page.locator("input[placeholder*='first name'], input[placeholder*='First']").first
                first_input.click()
                self.wait(0.2)

                # Select all and delete
                self.page.keyboard.press("Control+a")
                self.page.keyboard.press("Delete")
                self.wait(0.1)

                # Type first name character by character
                self.page.keyboard.type(first_name, delay=50)
                self.wait(0.3)

                # Tab to last name
                self.page.keyboard.press("Tab")
                self.wait(0.2)

                # Type last name
                self.page.keyboard.type(last_name, delay=50)
                self.wait(0.3)

                # Tab out to trigger blur
                self.page.keyboard.press("Tab")
                self.wait(0.5)

                self.screenshot("step_10c_keyboard_input")

                # Click Add User again
                self.page.evaluate("""
                    () => {
                        const btns = Array.from(document.querySelectorAll('button'));
                        const addBtn = btns.find(b => b.innerText?.includes('Add User'));
                        if (addBtn) addBtn.click();
                    }
                """)
                self.wait(1)

                # Check again
                page_text = self.page.inner_text("body")
                if "No users added yet" not in page_text:
                    logger.info(f"✓ Added user (keyboard method): {first_name} {last_name}")
                    user_added = True
                else:
                    logger.error("FAILED to add user after retry")

            except Exception as e:
                logger.error(f"Keyboard input method failed: {e}")

        self.screenshot("step_10_senders")

        # Scroll down to find the Save & Continue button
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.wait(0.5)

        # Click "Save & Continue to Review" - this saves Step 5 AND navigates to Review Order
        logger.info("Looking for 'Save & Continue to Review' button...")
        clicked = False

        # First try the exact button
        try:
            save_btn = self.page.locator("button:has-text('Save & Continue to Review')").first
            if save_btn.is_visible(timeout=5000):
                save_btn.scroll_into_view_if_needed()
                self.wait(0.3)
                save_btn.click(timeout=5000)
                logger.info("Clicked 'Save & Continue to Review'")
                clicked = True
        except Exception as e:
            logger.debug(f"Locator failed: {e}")

        if not clicked:
            # Try JavaScript to find and click
            logger.info("Using JavaScript to find and click the button...")
            result = self.page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find(b => b.innerText?.includes('Save & Continue to Review'));
                    if (btn && btn.offsetParent !== null) {
                        btn.scrollIntoView();
                        btn.click();
                        return { clicked: true, text: btn.innerText };
                    }
                    return { clicked: false };
                }
            """)
            if result.get("clicked"):
                logger.info(f"JavaScript clicked: {result.get('text')}")
                clicked = True

        self.wait(3)

        # Verify we navigated to Review Order page
        current_url = self.page.url
        logger.info(f"After clicking Save & Continue to Review, URL: {current_url}")

        if "review" in current_url.lower():
            logger.info("Successfully navigated to Review Order page!")
        else:
            logger.warning("May not have navigated to Review Order page yet")

        if not self.dry_run:
            log_step(self.job_id, "sender_names",
                    f"Added sender: {first_name} {last_name}")

        return True

    def step_11_review_order(self) -> bool:
        """Step 11: Navigate to Review Order page and proceed to checkout."""
        logger.info("=" * 60)
        logger.info("STEP 11: Navigate to Review Order")
        logger.info("=" * 60)

        # First, scroll to the bottom of the page to find the main navigation button
        logger.info("Scrolling to bottom to find Review Order button...")
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.wait(1)

        self.screenshot("step_11a_bottom_of_settings")

        # Check if we're still on setup-domain-settings
        current_url = self.page.url
        logger.info(f"Current URL: {current_url}")

        # Get all button/link text on the page for debugging
        buttons_text = self.page.evaluate("""
            () => {
                const buttons = document.querySelectorAll('button, a, [role="button"]');
                return Array.from(buttons).map(b => b.innerText?.trim()).filter(t => t && t.length < 50);
            }
        """)
        logger.info(f"Available buttons/links: {buttons_text}")

        # PRIORITY: Try "Save & Continue to Review" first (at the bottom of settings page)
        # This is the button that actually navigates, not the header button
        clicked_review = False

        try:
            save_continue_btn = self.page.locator("button:has-text('Save & Continue to Review')").first
            if save_continue_btn.is_visible(timeout=3000):
                save_continue_btn.scroll_into_view_if_needed()
                self.wait(0.3)
                save_continue_btn.click()
                logger.info("Clicked 'Save & Continue to Review'")
                clicked_review = True
        except:
            pass

        if not clicked_review:
            # Try JavaScript approach for Save & Continue to Review
            logger.info("Trying JavaScript to find Save & Continue to Review...")
            result = self.page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const btn = buttons.find(b => b.innerText?.includes('Save & Continue to Review'));
                    if (btn && btn.offsetParent !== null) {
                        btn.scrollIntoView();
                        btn.click();
                        return { clicked: true, text: btn.innerText };
                    }
                    return { clicked: false };
                }
            """)
            if result.get("clicked"):
                logger.info(f"JavaScript clicked: {result.get('text')}")
                clicked_review = True

        if not clicked_review:
            # Fallback: Try the header "Continue to Review" button
            # (but this might be disabled)
            logger.info("Trying header 'Continue to Review' button...")
            try:
                header_btn = self.page.locator("button:has-text('Continue to Review')").first
                if header_btn.is_enabled(timeout=2000):
                    header_btn.click()
                    logger.info("Clicked header 'Continue to Review'")
                    clicked_review = True
            except:
                pass

        if clicked_review:
            self.wait(3)
            new_url = self.page.url
            logger.info(f"After clicking review button, URL: {new_url}")

        # Wait for Review Order page to load
        self.wait(2)

        # Check if we're now on Review Order page
        current_url = self.page.url
        if "review" in current_url.lower():
            logger.info("Successfully navigated to Review Order page")

        # Now get page text for review
        page_text = self.page.inner_text("body")[:2000]
        logger.info(f"Order review (excerpt): {page_text[:500]}...")

        self.screenshot("step_11b_review_page")

        # Verify "Checkout with Stripe" button is visible (but DON'T click it)
        # Step 12 will click it with listeners set up to capture the Stripe URL
        checkout_btn = self.page.locator("button:has-text('Checkout with Stripe')").first
        if checkout_btn.is_visible(timeout=5000):
            logger.info("Checkout button visible - ready for Step 12")
        else:
            logger.warning("Checkout button not found - Step 12 may fail")

        if not self.dry_run:
            log_step(self.job_id, "review_order", "On Review Order page, ready for checkout")

        return True

    def step_12_checkout_handoff(self) -> bool:
        """Step 12: Capture Stripe URL via multiple detection methods and hand off."""
        logger.info("=" * 60)
        logger.info("STEP 12: Checkout Handoff (Multi-Method Capture)")
        logger.info("=" * 60)

        stripe_url = None
        captured_urls = []
        console_errors = []

        # Method 1: Set up response listener to capture Stripe URLs from API responses
        # This catches: Button click → API POST → Response with {url: "https://checkout.stripe.com/..."}
        def handle_response(response):
            nonlocal captured_urls
            if response.status >= 200 and response.status < 300:
                url = response.url.lower()
                if "stripe" in url or "checkout" in url or "session" in url or "api" in url:
                    try:
                        body = response.json()
                        # Stripe session URL is typically in "url" field
                        for key in ["url", "checkout_url", "redirect_url", "session_url"]:
                            if key in body and isinstance(body[key], str):
                                if "checkout.stripe.com" in body[key]:
                                    logger.info(f"[RESPONSE] Captured Stripe URL: {body[key]}")
                                    captured_urls.append(body[key])
                    except:
                        pass

        # Method 2: Monitor console for errors that explain why button doesn't work
        def handle_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
                logger.warning(f"[CONSOLE ERROR] {msg.text}")

        # Method 3: Inject script to monitor window.location changes
        self.page.evaluate("""
            window._stripeURLs = [];

            // Monitor location.href assignments
            try {
                const origHrefSet = Object.getOwnPropertyDescriptor(Location.prototype, 'href').set;
                Object.defineProperty(Location.prototype, 'href', {
                    set: function(url) {
                        if (url && url.includes('stripe')) {
                            window._stripeURLs.push(url);
                            console.log('[STRIPE REDIRECT]', url);
                        }
                        origHrefSet.call(this, url);
                    }
                });
            } catch(e) {}

            // Monitor window.open calls
            try {
                const origOpen = window.open;
                window.open = function(url, ...args) {
                    if (url && url.includes('stripe')) {
                        window._stripeURLs.push(url);
                        console.log('[STRIPE POPUP]', url);
                    }
                    return origOpen.call(this, url, ...args);
                };
            } catch(e) {}
        """)

        # Attach listeners
        self.page.on("response", handle_response)
        self.page.on("console", handle_console)

        try:
            # Diagnostic: Check if Stripe.js is loaded
            stripe_loaded = self.page.evaluate("typeof Stripe === 'function'")
            logger.info(f"Stripe.js loaded: {stripe_loaded}")

            # Diagnostic: Check button state
            checkout_btn = self.page.locator("button:has-text('Checkout with Stripe')").first
            if checkout_btn.count() > 0:
                is_disabled = checkout_btn.evaluate("el => el.disabled")
                logger.info(f"Button disabled: {is_disabled}")

                if not is_disabled:
                    logger.info("Clicking 'Checkout with Stripe' button...")
                    checkout_btn.click()

                    # Wait for API response or redirect (up to 15 seconds)
                    for i in range(15):
                        # Check captured URLs from response listener
                        if captured_urls:
                            stripe_url = captured_urls[0]
                            logger.info(f"[METHOD 1] Captured from API response: {stripe_url}")
                            break

                        # Check injected script captures
                        js_urls = self.page.evaluate("window._stripeURLs || []")
                        if js_urls:
                            stripe_url = js_urls[0]
                            logger.info(f"[METHOD 3] Captured from JS monitor: {stripe_url}")
                            break

                        # Check if page redirected
                        current_url = self.page.url
                        if "checkout.stripe.com" in current_url:
                            stripe_url = current_url
                            logger.info(f"[METHOD 2] Captured from page redirect: {stripe_url}")
                            break

                        self.wait(1)
                        logger.debug(f"[{i+1}s] Waiting for Stripe URL...")
                else:
                    logger.error("Checkout button is DISABLED - cannot proceed")
            else:
                logger.error("Checkout button not found on page")

        finally:
            # Clean up listeners
            self.page.remove_listener("response", handle_response)
            self.page.remove_listener("console", handle_console)

        self.screenshot("step_12_final_state")

        # Report console errors if no URL captured
        if not stripe_url and console_errors:
            logger.error(f"Console errors detected: {console_errors[:3]}")

        # Hand off if we got a Stripe URL
        if stripe_url and "checkout.stripe.com" in stripe_url:
            logger.info(f"SUCCESS: Got Stripe URL: {stripe_url}")
            if not self.dry_run:
                handoff_checkout(self.job_id, stripe_url)
                log_step(self.job_id, "checkout_handoff", f"Checkout URL: {stripe_url}")
            return True

        # Fallback: Check current page state
        current_url = self.page.url
        logger.error(f"FAILED to capture Stripe URL. Current URL: {current_url}")

        # Debug info
        page_text = self.page.inner_text("body").lower()
        if "setup-domain-settings" in current_url:
            logger.error("Still on Setup Domain Settings - checkout navigation failed")
            buttons = self.page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button:not([disabled])');
                    return Array.from(btns).map(b => ({
                        text: b.innerText?.trim(),
                        visible: b.offsetParent !== null
                    })).filter(b => b.text && b.visible);
                }
            """)
            logger.info(f"Visible buttons: {buttons}")

        return False

    def get_steps(self):
        """Return list of (step_num, step_func, step_name) tuples."""
        return [
            (1, self.step_1_load_data, "Load Job Data"),
            (2, self.step_2_login, "Login to Hypertide"),
            (3, self.step_3_new_order, "Start New Order"),
            (4, self.step_4_select_provider, "Select Provider Type"),
            (5, self.step_5_enter_domains, "Enter Domains (BYOD)"),
            (6, self.step_6_basic_config, "Basic Configuration"),
            (7, self.step_7_bison_config, "Bison Configuration"),
            (8, self.step_8_warmup_settings, "Warmup Settings"),
            (9, self.step_9_outbound_settings, "Outbound Settings"),
            (10, self.step_10_sender_names, "Sender Names"),
            (11, self.step_11_review_order, "Review Order"),
            (12, self.step_12_checkout_handoff, "Checkout Handoff"),
        ]

    def run_single_step(self, step_num: int) -> bool:
        """Run only a single step (for testing)."""
        steps = {s[0]: (s[1], s[2]) for s in self.get_steps()}

        if step_num not in steps:
            logger.error(f"Invalid step number: {step_num}. Valid: 1-12")
            return False

        step_func, step_name = steps[step_num]
        logger.info(f"Running single step: {step_num} - {step_name}")

        try:
            success = step_func()
            if not success:
                logger.error(f"Step {step_num} failed")
                self.screenshot(f"failed_step_{step_num}")
            return success
        except Exception as e:
            logger.exception(f"Step {step_num} raised exception: {e}")
            self.screenshot(f"exception_step_{step_num}")
            return False

    def run_interactive(self, start_step: int = 1, stop_after: int = None) -> bool:
        """Run automation interactively, pausing after each step for user confirmation."""
        steps = self.get_steps()

        print("\n" + "=" * 60)
        print("INTERACTIVE TESTING MODE")
        print("=" * 60)
        print(f"Starting from step {start_step}")
        print("After each step, you'll be asked to verify the screen.")
        print("=" * 60)

        for step_num, step_func, step_name in steps:
            # Skip steps before start_step
            if step_num < start_step:
                continue

            if stop_after and step_num > stop_after:
                logger.info(f"Stopping after step {stop_after} (--stop-after)")
                break

            # Show preview of what this step will do
            interactive_step_preview(step_num)

            # Run step with retry loop
            while True:
                try:
                    success = step_func()

                    if success:
                        self.screenshot(f"interactive_step_{step_num}_success")
                    else:
                        self.screenshot(f"interactive_step_{step_num}_failed")
                        logger.warning(f"Step {step_num} returned False")

                except Exception as e:
                    logger.exception(f"Step {step_num} raised exception: {e}")
                    self.screenshot(f"interactive_step_{step_num}_exception")
                    success = False

                # Prompt user for action
                action = interactive_prompt(step_num, step_name)

                if action == 'continue':
                    if not success:
                        print("WARNING: Step reported failure. Continuing anyway...")
                    break  # Move to next step
                elif action == 'retry':
                    print(f"Retrying step {step_num}...")
                    continue  # Retry the same step
                elif action == 'skip':
                    print(f"Skipping step {step_num}...")
                    break  # Move to next step
                elif action == 'quit':
                    print("Exiting interactive mode.")
                    return False

        logger.info("=" * 60)
        logger.info("INTERACTIVE SESSION COMPLETE")
        logger.info("=" * 60)
        return True

    def run(self, stop_after: int = None, interactive: bool = False, single_step: int = None) -> bool:
        """Run the automation flow."""

        # Single step mode - run just one step
        if single_step:
            return self.run_single_step(single_step)

        # Interactive mode - pause after each step
        if interactive:
            return self.run_interactive(start_step=1, stop_after=stop_after)

        # Normal mode - run all steps
        steps = self.get_steps()

        for step_num, step_func, step_name in steps:
            if stop_after and step_num > stop_after:
                logger.info(f"Stopping after step {stop_after} (--stop-after)")
                break

            try:
                success = step_func()
                if not success:
                    logger.error(f"Step {step_num} failed")
                    self.screenshot(f"failed_step_{step_num}")
                    return False
            except Exception as e:
                logger.exception(f"Step {step_num} raised exception: {e}")
                self.screenshot(f"exception_step_{step_num}")
                if not self.dry_run:
                    fail_job(self.job_id, str(e), f"step_{step_num}", "system")
                return False

        logger.info("=" * 60)
        logger.info("AUTOMATION COMPLETE")
        logger.info("=" * 60)
        return True


# =============================================================================
# Main Entry Point
# =============================================================================

def get_test_job_data(order_count: int = 1) -> Dict[str, Any]:
    """Return test job data for debugging without database.

    Args:
        order_count: Number of orders (1-20). Domains will be generated to match:
                    - Entra: order_count * 2 domains
                    - Google: order_count * 5 domains
    """
    # Generate test domains to match order_count (2 per order for Entra)
    domains_needed = order_count * 2
    base_domains = ["testdomain123abc.com", "testdomain456xyz.com"]

    if domains_needed > len(base_domains):
        # Generate additional test domains
        for i in range(len(base_domains), domains_needed):
            base_domains.append(f"testdomain{i + 1:03d}.com")

    return {
        "id": "test-job-001",
        "hypertide_email": HYPERTIDE_EMAIL,
        "hypertide_password": HYPERTIDE_PASSWORD,
        "provider_type": "entra",
        # Database uses entra_orders/google_orders columns
        "entra_orders": order_count,
        "google_orders": 0,
        "orders_total": order_count,
        # BYOD mode requires domains matching order_count * 2 for Entra
        "domain_names": base_domains[:domains_needed],
        "forwarding_domain": "hirecharm.com",
        "company_name": "Test Company",
        "bison_username": BISON_USERNAME,
        "bison_password": BISON_PASSWORD,
        "bison_workspace_name": "Charm",
        "bison_url": BISON_URL,
        "bison_api_key": BISON_API_KEY,
        # Base sender name (the founder's identity) - used for Hypertide user configuration
        "base_sender_name": {"firstName": "Chris", "lastName": "Booth", "isFounder": True},
        "use_saved_payment": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Hypertide Purchase Automation")
    parser.add_argument("--job-id", help="Job ID to process (or use --test)")
    parser.add_argument("--test", action="store_true", help="Use test data instead of database")
    parser.add_argument("--dry-run", action="store_true", help="Don't update database")
    parser.add_argument("--stop-after", type=int, help="Stop after step N")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode: pause after each step for confirmation")
    parser.add_argument("--step", type=int, help="Run only a specific step (1-12). Use with --interactive to test individual screens.")
    parser.add_argument("--list-steps", action="store_true", help="List all steps and exit")
    parser.add_argument("--pause", action="store_true", help="Keep browser open after completion for inspection (press Enter to close)")
    parser.add_argument("--order-count", type=int, default=1, help="Number of orders for test mode (1-20). Generates matching domains.")

    args = parser.parse_args()

    # List steps and exit
    if args.list_steps:
        print("\nHypertide Purchase Automation Steps:")
        print("=" * 50)
        for num, desc in STEP_DESCRIPTIONS.items():
            print(f"  {num:2d} - {desc}")
        print("\nUsage:")
        print("  --interactive    Run all steps with pause after each")
        print("  --step N         Run only step N")
        print("  --stop-after N   Run steps 1-N then stop")
        sys.exit(0)

    if not args.job_id and not args.test:
        parser.error("Either --job-id or --test is required")

    logger.info("=" * 60)
    logger.info("HYPERTIDE PURCHASE AUTOMATION")
    logger.info("=" * 60)
    logger.info(f"Job ID: {args.job_id or 'TEST MODE'}")
    logger.info(f"Test mode: {args.test}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"Stop after: {args.stop_after}")
    logger.info(f"Headless: {args.headless}")
    logger.info(f"Interactive: {args.interactive}")
    logger.info(f"Single step: {args.step}")
    logger.info(f"Order count: {args.order_count}")

    # Fetch job data
    if args.test:
        job_data = get_test_job_data(order_count=args.order_count)
        logger.info(f"Using TEST data: {job_data.get('company_name')} - {len(job_data.get('domain_names', []))} domains - {args.order_count} order(s)")
    else:
        try:
            job_data = fetch_job(args.job_id)
            logger.info(f"Loaded job: {job_data.get('company_name')} - {job_data.get('domain_names')}")
        except Exception as e:
            logger.error(f"Failed to fetch job: {e}")
            sys.exit(1)

    # Run automation
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=args.headless,
            slow_mo=SLOW_MO,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )

        page = browser.new_page(viewport={"width": 1280, "height": 900})

        try:
            automation = HypertideAutomation(page, job_data, dry_run=args.dry_run)
            success = automation.run(
                stop_after=args.stop_after,
                interactive=args.interactive,
                single_step=args.step
            )

            if success:
                logger.info("Automation completed successfully!")
            else:
                logger.error("Automation failed!")

            # Pause for inspection if requested
            if args.pause:
                print("\n" + "=" * 60)
                print("BROWSER PAUSED FOR INSPECTION")
                print("=" * 60)
                print("The browser will stay open so you can inspect the current state.")
                print("Take screenshots, check the page, etc.")
                input("\nPress Enter to close the browser and exit...")

            sys.exit(0 if success else 1)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
