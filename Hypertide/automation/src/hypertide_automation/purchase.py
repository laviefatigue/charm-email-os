"""
Purchase automation for Hypertide.

Implements the complete order flow:
1. Choose Plan (Entra/Google)
2. Select Quantity
3. Select/Configure Domains
4. Setup Domain Settings
5. Review Order
6. Stripe Checkout
"""

import asyncio
import os
from typing import Optional
from datetime import datetime

import structlog
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from .client import HypertideClient
from .models import (
    OrderRequest,
    OrderResult,
    OrderType,
    SendingTool,
    OrderBundle,
    BundleResult,
    MixedOrderRequest,
    BisonCredentials,
    create_order_bundle,
)
from .exceptions import (
    OrderError,
    PaymentError,
    PaymentTimeoutError,
    DomainUnavailableError,
    ElementNotFoundError,
    SessionExpiredError,
    RetryExhaustedError,
)
from .config import StripeConfig

logger = structlog.get_logger()


class PurchaseAutomation:
    """
    Automates the Hypertide purchase flow.

    This class takes a pre-configured OrderRequest and executes
    the purchase through browser automation.

    Usage:
        async with HypertideClient() as client:
            await client.ensure_authenticated()

            automation = PurchaseAutomation(client)
            result = await automation.execute(order_request)

            if result.success:
                print(f"Order created: {result.order_id}")
    """

    # UI Selectors (updated from Chrome DevTools inspection 2026-02-13)
    # Verified against live app2.hypertide.io
    SELECTORS = {
        # =========== Step 1: Choose Plan (/choose-plan) ===========
        # Note: Both plan buttons have same text "Select Plan - $50/mo"
        # Use first/last or locate by heading proximity
        "entra_plan_heading": "heading:has-text('Hypertide Entra')",
        "google_plan_heading": "heading:has-text('Hypertide Google')",
        "entra_quantity_dropdown": "combobox >> nth=0",  # First combobox
        "google_quantity_dropdown": "combobox >> nth=1",  # Second combobox
        # Buttons - both have same text, use nth selector
        "entra_select_btn": "button:has-text('Select Plan') >> nth=0",
        "google_select_btn": "button:has-text('Select Plan') >> nth=1",

        # =========== Step 2: Select Domains (/select-domains) ===========
        # Domain source selection (click heading to select option)
        "purchase_domains_option": "heading:has-text('Purchase domains')",
        "use_own_domains_option": "heading:has-text('Use my own domains')",

        # BYOD mode - multiline textbox for domains (one per line)
        "domain_input": "textarea, textbox[multiline]",  # Multiline textbox
        "add_domain_btn": "button:has-text('Add Your Domain')",
        "max_domains_indicator": "button:has-text('Max Domains Added')",

        # DNS configuration (BYOD)
        "dns_confirmed_btn": "button:has-text('I have configured DNS')",
        "dns_completed_indicator": "button:has-text('✓ Completed')",

        # Navigation
        "continue_to_settings": "button:has-text('Continue to Domain Settings')",
        "go_back_btn": "button:has-text('Go Back')",

        # =========== Step 3: Setup Domain Settings (/setup-domain-settings) ===========
        # Sub-step 1: Basic Configuration
        # Placeholder: "example.com or https://example.com"
        "forwarding_url_input": "input[placeholder*='example.com']",
        # Placeholder: "example: Acme Corp (letters and numbers only)"
        "company_client_input": "input[placeholder*='Acme Corp']",
        "save_basic_config_btn": "button:has-text('Save Basic Configuration')",

        # Sub-step 2: Email Tool Connection
        "saved_credentials_btn": "button:has-text('Access your saved credentials')",
        # Tool selection - these are StaticText elements, click to select
        "tool_instantly": "text=Instantly",
        "tool_smartlead": "text=Smartlead",
        "tool_bison": "text=Bison",
        "tool_other": "text=Other",

        # Bison credentials - placeholders from actual UI
        "bison_url_input": "input[placeholder*='send.example.com']",
        "bison_username_input": "input[placeholder*='name@example.com']",
        "bison_password_input": "input[placeholder*='Enter your password']",
        "masterinbox_checkbox": "input[type='checkbox']:near(text='Add inboxes to masterinbox.com')",

        # Credential save options
        "save_credentials_btn": "button:has-text('Save Your Credentials For Future Use')",
        "move_on_without_saving": "button:has-text('Move on without saving')",

        # Sub-step 3: Warmup & Tags Setup
        "disable_warmup_checkbox": "input[type='checkbox']:near(text='Disable Warmup')",
        "warmup_limit_input": "input[type='number']:near(text='Warmup Limit')",
        "save_warmup_btn": "button:has-text('Save Warmup & Tags Configuration')",

        # Sub-step 4: Outbound Settings
        "daily_limit_input": "input[type='number']:near(text='Daily Limit')",
        "save_outbound_btn": "button:has-text('Save Outbound Settings')",

        # Sub-step 5: User Configuration
        # Placeholders: "Enter first name", "Enter last name"
        "first_name_input": "input[placeholder*='first name']",
        "last_name_input": "input[placeholder*='last name']",
        "add_user_btn": "button:has-text('+ Add User')",

        # Navigation
        "save_continue_review": "button:has-text('Save & Continue to Review')",
        "continue_to_review": "button:has-text('Continue to Review')",

        # =========== Step 4: Review Order (/review-order) ===========
        "go_back_review_btn": "button:has-text('Go Back')",
        "proceed_checkout": "button:has-text('Proceed to Checkout')",
        "checkout_btn": "button:has-text('Checkout with Stripe')",

        # =========== Step 5: Stripe Checkout ===========
        "stripe_iframe": "iframe[src*='stripe']",
        "stripe_pay_button": "button:has-text('Pay')",

        # Success indicators
        "success_message": "text=Order confirmed",
        "order_id": "[data-order-id], [data-testid='order-id']",
    }

    # Timing constants (milliseconds)
    TIMING = {
        "page_transition": 1000,
        "dropdown_open": 300,
        "form_save": 500,
        "domain_search": 90000,  # Discovery search can take ~1 minute
        "stripe_checkout": 60000,
    }

    def __init__(
        self,
        client: HypertideClient,
        stripe_config: Optional[StripeConfig] = None
    ):
        self.client = client
        self.stripe_config = stripe_config or StripeConfig()
        self.page = client.page

    async def execute(self, request: OrderRequest) -> OrderResult:
        """
        Execute the complete purchase flow.

        Includes:
        - Session validation before starting
        - Login detection during flow (SessionExpiredError)
        - Detailed error logging with screenshots
        - Retry logic inherited from client navigation methods

        Args:
            request: The order configuration

        Returns:
            OrderResult with success status and order details
        """
        logger.info(
            "Starting purchase automation",
            client=request.client_name,
            order_type=request.order_type.value,
            quantity=request.quantity,
        )

        try:
            # Pre-flight: Validate session is ready for purchase
            logger.info("Pre-flight: Validating session")
            await self.client.validate_session_for_purchase()

            # Step 1: Navigate to choose plan (already on page from validation)
            await self._step_choose_plan(request)
            await self._check_session_during_flow("choose_plan")

            # Step 2: Select quantity
            await self._step_select_quantity(request)
            await self._check_session_during_flow("select_quantity")

            # Step 3: Configure domains (if custom)
            await self._step_configure_domains(request)
            await self._check_session_during_flow("configure_domains")

            # Step 4: Setup domain settings (5 sub-steps in 2026 UI)
            await self._step_setup_settings_v2(request)
            await self._check_session_during_flow("setup_settings")

            # Step 5: Review order
            await self._step_review_order(request)
            await self._check_session_during_flow("review_order")

            # Step 6: Capture checkout URL (don't auto-pay)
            checkout_url = await self._step_checkout(request)

            # Success - checkout URL captured for manual payment
            result = OrderResult(
                success=True,
                checkout_url=checkout_url,
                client_name=request.client_name,
                forwarding_domain=request.forwarding_domain,
                order_type=request.order_type,
                quantity=request.quantity,
                total_inboxes=request.expected_inboxes,
                monthly_capacity=request.expected_monthly_capacity,
            )

            if checkout_url:
                logger.info("Checkout URL captured successfully", checkout_url=checkout_url)
            else:
                logger.warning("Checkout completed but no Stripe URL captured")
            return result

        except SessionExpiredError as e:
            logger.error("Session expired during purchase", error=str(e))
            screenshot = await self.client.screenshot_on_error(
                f"session-expired-{request.client_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            return OrderResult(
                success=False,
                client_name=request.client_name,
                forwarding_domain=request.forwarding_domain,
                order_type=request.order_type,
                quantity=request.quantity,
                error_message=f"Session expired: {str(e)}. Re-authentication required.",
                screenshot_path=str(screenshot) if screenshot else None,
            )

        except RetryExhaustedError as e:
            logger.error("Retry exhausted during purchase", error=str(e))
            screenshot = await self.client.screenshot_on_error(
                f"retry-exhausted-{request.client_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )
            return OrderResult(
                success=False,
                client_name=request.client_name,
                forwarding_domain=request.forwarding_domain,
                order_type=request.order_type,
                quantity=request.quantity,
                error_message=f"Operation failed after retries: {str(e.last_error)}",
                screenshot_path=str(screenshot) if screenshot else None,
            )

        except Exception as e:
            logger.error("Purchase failed", error=str(e), error_type=type(e).__name__)

            # Take screenshot for debugging
            screenshot = await self.client.screenshot_on_error(
                f"purchase-{request.client_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            )

            return OrderResult(
                success=False,
                client_name=request.client_name,
                forwarding_domain=request.forwarding_domain,
                order_type=request.order_type,
                quantity=request.quantity,
                error_message=str(e),
                screenshot_path=str(screenshot) if screenshot else None,
            )

    async def _check_session_during_flow(self, step_name: str) -> None:
        """
        Check if session is still valid during the purchase flow.

        Args:
            step_name: Name of the current step (for logging)

        Raises:
            SessionExpiredError: If redirected to login page
        """
        if self.client.is_on_login_page():
            raise SessionExpiredError(
                f"Session expired during purchase flow at step: {step_name}"
            )

    # =========================================================================
    # Step Implementations
    # =========================================================================

    async def _step_choose_plan(self, request: OrderRequest) -> None:
        """Step 1: Navigate and select plan type."""
        logger.info("Step 1: Choosing plan")

        # Check if we're already on choose-plan (from session validation)
        if "/choose-plan" not in self.page.url:
            await self.client.goto_choose_plan()

        # Wait for plan selection page to load
        try:
            # Wait for either plan heading or Select Plan button
            await self.page.wait_for_selector(
                "text=Entra, text=Google, button:has-text('Select')",
                timeout=self.client.config.element_timeout,
            )
        except PlaywrightTimeoutError:
            # Take screenshot for debugging
            logger.warning("Plan page content not found with expected text")
            await self.client.screenshot_on_error("plan-page-debug")

        # Click the "Select Plan" button for the appropriate plan
        # Use JavaScript to find the button within the same card as the plan heading
        # This is more reliable than nth selectors which depend on DOM order
        plan_text = "Hypertide Entra" if request.order_type == OrderType.HYPERTIDE_ENTRA else "Hypertide Google"
        logger.info(f"Selecting {plan_text} plan")

        # Primary approach: JavaScript to find button near the correct heading
        clicked = await self.page.evaluate(f"""
            () => {{
                // Find the heading containing the plan name
                const headings = [...document.querySelectorAll('h1, h2, h3, h4, [role="heading"]')];
                const planHeading = headings.find(h => h.textContent.includes('{plan_text}'));

                if (planHeading) {{
                    // Walk up to find the card/container, then find the Select Plan button within it
                    let container = planHeading.parentElement;
                    for (let i = 0; i < 5 && container; i++) {{
                        const btn = container.querySelector('button');
                        if (btn && btn.textContent.includes('Select')) {{
                            btn.click();
                            return true;
                        }}
                        container = container.parentElement;
                    }}
                }}
                return false;
            }}
        """)

        if not clicked:
            # Fallback: try Playwright selectors
            logger.warning(f"JS click failed, trying Playwright selectors")
            fallback_selectors = [
                f"button:has-text('Select Plan'):near(:text('{plan_text}'))",
                self.SELECTORS["entra_select_btn"] if request.order_type == OrderType.HYPERTIDE_ENTRA else self.SELECTORS["google_select_btn"],
            ]

            for fallback in fallback_selectors:
                try:
                    await self.page.click(fallback, timeout=5000)
                    clicked = True
                    logger.info(f"Clicked via fallback selector: {fallback}")
                    break
                except:
                    continue

            if not clicked:
                raise ElementNotFoundError(f"Could not find Select Plan button for {plan_text}")

        await asyncio.sleep(1)  # Wait for page transition

    async def _step_select_quantity(self, request: OrderRequest) -> None:
        """Step 2: Select order quantity from dropdown."""
        logger.info("Step 2: Selecting quantity", quantity=request.quantity)

        # Build the expected dropdown option text
        if request.order_type == OrderType.HYPERTIDE_ENTRA:
            domains_per_order = 2
            domain_type = "Entra"
        else:
            domains_per_order = 5
            domain_type = "Google"

        total_domains = request.quantity * domains_per_order
        capacity_k = request.quantity * 5

        # Format: "X order(s) - Y Entra/Google Domains, Zk emails/mo"
        if request.quantity == 1:
            option_text = f"1 order - {total_domains} {domain_type} Domains"
        else:
            option_text = f"{request.quantity} orders - {total_domains} {domain_type} Domains"

        # Try to find and click the quantity dropdown
        try:
            # Look for a dropdown/select element
            dropdowns = await self.page.query_selector_all("select, [role='listbox'], [data-testid*='quantity']")

            if dropdowns:
                # Click dropdown to open
                await dropdowns[0].click()
                await asyncio.sleep(0.3)

                # Find and click the option
                await self.page.get_by_text(option_text, exact=False).first.click()
            else:
                # Fallback: look for the option text directly
                # (some UIs show all options visible)
                await self.page.get_by_text(option_text, exact=False).first.click()

        except PlaywrightTimeoutError:
            # If exact match fails, try clicking any element with the quantity number
            logger.warning("Could not find exact quantity option, trying alternative")
            await self.page.get_by_text(f"{request.quantity} order").first.click()

        await asyncio.sleep(0.5)

    async def _step_configure_domains(self, request: OrderRequest) -> None:
        """
        Step 2: Select Domains (BYOD - Bring Your Own Domains).

        Flow:
        1. Click "Use my own domains" option
        2. Enter all domains in multiline textbox (one per line)
        3. Click "Add Your Domain"
        4. Click "I have configured DNS"
        5. Click "Continue to Domain Settings"
        """
        logger.info("Step 2: Configuring domains (BYOD mode)")

        # Wait for page to load
        await asyncio.sleep(1)

        # Click "Use my own domains" option to enable BYOD section
        # This heading click toggles between Purchase and BYOD mode
        try:
            byod_option = self.page.locator("heading:has-text('Use my own domains')")
            if await byod_option.count() > 0:
                # Use force click to ensure it registers
                await byod_option.click(force=True)
                logger.info("Selected BYOD mode")
                await asyncio.sleep(1)
            else:
                logger.info("BYOD option not found, trying alternative")
                # Try clicking text directly
                await self.page.get_by_text("Use my own domains").click()
                await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Could not select BYOD mode: {e}")

        # Get domains from request
        domain_names = []
        if hasattr(request, 'domains') and request.domains:
            domain_names = [d.full_domain for d in request.domains]
        elif hasattr(request, 'domain_names') and request.domain_names:
            domain_names = request.domain_names

        if not domain_names:
            # Use forwarding domain as fallback - need 2 domains for Entra
            if request.forwarding_domain:
                # Generate a second domain name for Entra (requires 2)
                base = request.forwarding_domain.replace('.com', '').replace('.net', '')
                domain_names = [
                    f"get{base}.com",
                    f"try{base}.com",
                ]
            else:
                logger.warning("No domains provided, skipping domain configuration")
                return

        logger.info(f"Adding {len(domain_names)} domains")

        # Find the multiline textbox and fill all domains at once (one per line)
        try:
            # The domain input is a multiline textbox/textarea
            domain_input = self.page.locator("textarea").first
            if not await domain_input.count():
                # Try locator with multiline attribute
                domain_input = self.page.locator("[multiline='true']").first
            if not await domain_input.count():
                # Fallback to any textbox with domain placeholder
                domain_input = self.page.get_by_placeholder("example1.com").first

            # Join domains with newlines
            domains_text = "\n".join(domain_names)
            logger.info(f"Filling domains: {domains_text}")
            await domain_input.fill(domains_text)
            await asyncio.sleep(0.5)

            # Click "Add Your Domain" button using JavaScript to bypass overlays
            logger.info("Clicking Add Your Domain button...")
            await self.page.evaluate("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Add Your Domain') || b.textContent.includes('Add Domain')
                    );
                    if (btn) btn.click();
                }
            """)
            logger.info("Add Your Domain clicked, waiting for DNS section to activate...")
            await asyncio.sleep(3)  # Wait for domains to be validated and section to activate

        except Exception as e:
            logger.warning(f"Failed to add domains: {e}")

        # Wait for DNS section to become active (opacity changes from 0.5 to 1)
        # The section with "I have configured DNS" should no longer have opacity-50
        try:
            # Wait for the button to be clickable (not inside opacity-50 section)
            logger.info("Waiting for DNS confirmation section to activate...")
            await self.page.wait_for_function("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('I have configured DNS')
                    );
                    if (!btn) return false;
                    // Check if parent section has opacity-50 class
                    let el = btn;
                    while (el && el !== document.body) {
                        if (el.classList && el.classList.contains('opacity-50')) {
                            return false;  // Still greyed out
                        }
                        el = el.parentElement;
                    }
                    return true;  // Section is active
                }
            """, timeout=15000)
            logger.info("DNS section is now active")
        except Exception as e:
            logger.warning(f"DNS section activation wait failed: {e}, proceeding with force click")

        # Click "I have configured DNS" button using JavaScript
        try:
            logger.info("Clicking I have configured DNS...")
            await self.page.evaluate("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('I have configured DNS')
                    );
                    if (btn) btn.click();
                }
            """)
            logger.info("DNS confirmed, waiting for Continue section to activate...")
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"DNS confirmation click failed: {e}")

        # Wait for Continue section to become active
        try:
            logger.info("Waiting for Continue section to activate...")
            await self.page.wait_for_function("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Continue to Domain Settings')
                    );
                    if (!btn) return false;
                    let el = btn;
                    while (el && el !== document.body) {
                        if (el.classList && el.classList.contains('opacity-50')) {
                            return false;
                        }
                        el = el.parentElement;
                    }
                    return true;
                }
            """, timeout=10000)
            logger.info("Continue section is now active")
        except Exception as e:
            logger.warning(f"Continue section activation wait failed: {e}, proceeding anyway")

        # Click "Continue to Domain Settings" using JavaScript
        try:
            logger.info("Clicking Continue to Domain Settings...")
            await self.page.evaluate("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Continue to Domain Settings') || b.textContent.includes('Continue')
                    );
                    if (btn) btn.click();
                }
            """)
            await asyncio.sleep(2)
            logger.info("Navigated to domain settings page")
        except Exception as e:
            logger.warning(f"Continue button click failed: {e}")

    async def _step_setup_settings(self, request: OrderRequest) -> None:
        """Step 4: Configure forwarding domain and sending tool."""
        logger.info(
            "Step 4: Setting up domain settings",
            forwarding_domain=request.forwarding_domain,
            sending_tool=request.sending_tool.value,
        )

        # Wait for settings form to appear
        await asyncio.sleep(1)

        # Set forwarding domain
        try:
            forwarding_input = await self.page.wait_for_selector(
                "input[placeholder*='forwarding'], input[name*='forwarding']",
                timeout=10000
            )
            await forwarding_input.fill(request.forwarding_domain)
        except PlaywrightTimeoutError:
            # Try alternative approach
            logger.warning("Forwarding input not found with selector, trying text-based")
            await self.page.get_by_label("Forwarding Domain").fill(request.forwarding_domain)

        # Set sending tool
        try:
            # Look for sending tool dropdown
            tool_dropdown = await self.page.wait_for_selector(
                "select[name*='tool'], [data-testid*='sending-tool']",
                timeout=5000
            )
            await tool_dropdown.click()
            await asyncio.sleep(0.3)
            await self.page.get_by_text(request.sending_tool.value).click()
        except PlaywrightTimeoutError:
            # May already be set or different UI
            logger.warning("Sending tool dropdown not found, may be pre-selected")

        await asyncio.sleep(0.5)

    async def _step_setup_settings_v2(self, request: OrderRequest) -> None:
        """
        Step 3: Setup Domain Settings with 5 sub-steps (2026-02-13 UI).

        This is a wizard-style form - each step must be saved before the next
        section becomes active. Process sequentially with explicit waits.

        Sub-steps:
        1. Basic Configuration (forwarding URL + company name) → Save
        2. Email Tool Connection (Bison credentials) → Move on without saving
        3. Warmup & Tags Setup (use defaults) → Save
        4. Outbound Settings (use defaults) → Save
        5. User Configuration (first/last name) → Add User → Save & Continue
        """
        logger.info(
            "Step 3: Setting up domain settings (5 sub-steps)",
            forwarding_domain=request.forwarding_domain,
            client_name=request.client_name,
        )

        # Wait for page to fully load
        await asyncio.sleep(2)

        # ===== Sub-step 1: Basic Configuration =====
        logger.info("Sub-step 1/5: Basic Configuration")

        # Fill forwarding URL
        try:
            forwarding_input = self.page.get_by_placeholder("example.com").first
            await forwarding_input.clear()
            await forwarding_input.fill(request.forwarding_domain)
            logger.info(f"Filled forwarding URL: {request.forwarding_domain}")
        except Exception as e:
            logger.warning(f"Forwarding URL fill failed: {e}")

        await asyncio.sleep(0.5)

        # Fill company name
        try:
            company_input = self.page.get_by_placeholder("Acme Corp").first
            await company_input.clear()
            await company_input.fill(request.client_name)
            logger.info(f"Filled company name: {request.client_name}")
        except Exception as e:
            logger.warning(f"Company name fill failed: {e}")

        await asyncio.sleep(0.5)

        # Click Save Basic Configuration BUTTON
        try:
            save_btn = self.page.get_by_role("button", name="Save Basic Configuration")
            await save_btn.click()
            logger.info("Clicked Save Basic Configuration")
            await asyncio.sleep(2)  # Wait for section 2 to activate
        except Exception as e:
            logger.warning(f"Save Basic Config failed: {e}")
            try:
                await self.page.locator("button:has-text('Save Basic Configuration')").click(force=True)
                await asyncio.sleep(2)
            except:
                pass

        # ===== Sub-step 2: Email Tool Connection =====
        logger.info("Sub-step 2/5: Email Tool Connection")

        # First, click "Other" option to avoid Instantly validation requirements
        # The UI defaults to "Instantly" which requires credentials
        try:
            logger.info("Selecting 'Other' email tool to skip credential requirements")
            await self.page.evaluate("""
                () => {
                    // Find the "Other" radio button/option and click it
                    const otherOption = [...document.querySelectorAll('label, div, span')].find(
                        el => el.textContent.trim() === 'Other'
                    );
                    if (otherOption) otherOption.click();
                }
            """)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Could not select Other option: {e}")

        # Now click "Move on without saving" with proper mouse event dispatch
        logger.info("Clicking Move on without saving...")
        await self.page.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button')].find(
                    b => b.textContent.includes('Move on without saving')
                );
                if (btn) {
                    // Dispatch proper mouse events
                    btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                }
            }
        """)
        logger.info("Clicked Move on without saving (JS with events)")
        await asyncio.sleep(2)  # Wait for section 3 to activate

        # ===== Sub-step 3: Warmup & Tags Setup =====
        logger.info("Sub-step 3/5: Warmup & Tags Setup (defaults)")

        # Wait for Warmup section to become active, then click save
        try:
            await self.page.wait_for_function("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Save Warmup')
                    );
                    if (!btn) return false;
                    return !btn.disabled;
                }
            """, timeout=10000)
            logger.info("Warmup section is active")
        except:
            logger.warning("Warmup section did not become active, proceeding anyway")

        await self.page.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button')].find(
                    b => b.textContent.includes('Save Warmup')
                );
                if (btn && !btn.disabled) {
                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                }
            }
        """)
        logger.info("Clicked Save Warmup & Tags Configuration (JS)")
        await asyncio.sleep(2)

        # ===== Sub-step 4: Outbound Settings =====
        logger.info("Sub-step 4/5: Outbound Settings (defaults)")

        # Wait for Outbound section to become active, then click save
        try:
            await self.page.wait_for_function("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Save Outbound')
                    );
                    if (!btn) return false;
                    return !btn.disabled;
                }
            """, timeout=10000)
            logger.info("Outbound section is active")
        except:
            logger.warning("Outbound section did not become active, proceeding anyway")

        await self.page.evaluate("""
            () => {
                const btn = [...document.querySelectorAll('button')].find(
                    b => b.textContent.includes('Save Outbound')
                );
                if (btn && !btn.disabled) {
                    btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                }
            }
        """)
        logger.info("Clicked Save Outbound Settings (JS)")
        await asyncio.sleep(2)

        # ===== Sub-step 5: User Configuration =====
        logger.info("Sub-step 5/5: User Configuration")

        # Wait for User Configuration section to become active
        try:
            await self.page.wait_for_function("""
                () => {
                    const addBtn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Add User')
                    );
                    if (!addBtn) return false;
                    return !addBtn.disabled;
                }
            """, timeout=10000)
            logger.info("User Configuration section is active")
        except:
            logger.warning("User Configuration section did not become active, proceeding anyway")

        # Get sender name
        first_name = "Chris"
        last_name = "Booth"
        if hasattr(request, 'sender_names') and request.sender_names:
            if isinstance(request.sender_names, list) and len(request.sender_names) > 0:
                sender = request.sender_names[0]
                first_name = sender.get('firstName', first_name)
                last_name = sender.get('lastName', last_name)

        # Fill first name using Playwright's native fill (triggers React state properly)
        try:
            first_input = self.page.get_by_placeholder("Enter first name")
            await first_input.click()  # Focus the input
            await first_input.fill(first_name)
            logger.info(f"Filled first name: {first_name}")
        except Exception as e:
            logger.warning(f"First name fill failed: {e}")
            # Fallback to type
            try:
                await self.page.locator("input[placeholder*='first name']").first.fill(first_name)
            except:
                pass

        await asyncio.sleep(0.3)

        # Fill last name using Playwright's native fill
        try:
            last_input = self.page.get_by_placeholder("Enter last name")
            await last_input.click()  # Focus the input
            await last_input.fill(last_name)
            logger.info(f"Filled last name: {last_name}")
        except Exception as e:
            logger.warning(f"Last name fill failed: {e}")
            # Fallback to type
            try:
                await self.page.locator("input[placeholder*='last name']").first.fill(last_name)
            except:
                pass

        await asyncio.sleep(0.5)

        # Click Add User button using Playwright native click
        try:
            add_user_btn = self.page.get_by_role("button", name="+ Add User")
            await add_user_btn.click()
            logger.info("Clicked + Add User")
        except Exception as e:
            logger.warning(f"Add User click failed: {e}, trying JS fallback")
            await self.page.evaluate("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Add User')
                    );
                    if (btn) btn.click();
                }
            """)
            logger.info("Clicked + Add User (JS fallback)")

        await asyncio.sleep(1)

        # Wait for user to be added (table should show the user)
        try:
            await self.page.wait_for_function("""
                () => {
                    const text = document.body.innerText;
                    return text.includes('Chris') || !text.includes('No users added yet');
                }
            """, timeout=5000)
            logger.info("User appears to be added")
        except:
            logger.warning("User may not have been added, proceeding anyway")

        # Wait for Save & Continue button to become enabled
        try:
            await self.page.wait_for_function("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Save & Continue')
                    );
                    if (!btn) return false;
                    return !btn.disabled;
                }
            """, timeout=10000)
            logger.info("Save & Continue button is now enabled")
        except:
            logger.warning("Save & Continue did not become enabled, attempting click anyway")

        # Click Save & Continue to Review using Playwright native click
        try:
            save_btn = self.page.get_by_role("button", name="Save & Continue to Review")
            await save_btn.click()
            logger.info("Clicked Save & Continue to Review")
        except Exception as e:
            logger.warning(f"Save & Continue click failed: {e}, trying JS fallback")
            await self.page.evaluate("""
                () => {
                    const btn = [...document.querySelectorAll('button')].find(
                        b => b.textContent.includes('Save & Continue')
                    );
                    if (btn) btn.click();
                }
            """)
            logger.info("Clicked Save & Continue to Review (JS fallback)")

        await asyncio.sleep(2)

        logger.info("Domain settings complete")

    async def _substep_basic_config(self, request: OrderRequest) -> None:
        """Sub-step 1: Basic Configuration - forwarding URL + company name."""
        logger.info("Sub-step 1: Basic Configuration")

        # Wait for form to appear
        await asyncio.sleep(1)

        # Fill forwarding URL - clear first then fill
        try:
            forwarding_input = self.page.locator("input[placeholder*='example.com']").first
            await forwarding_input.clear()
            await forwarding_input.fill(request.forwarding_domain)
        except Exception as e:
            logger.warning(f"Could not fill forwarding URL with selector, trying alternative: {e}")
            await self.page.get_by_placeholder("example.com").first.fill(request.forwarding_domain)

        await asyncio.sleep(0.3)

        # Fill company/client name - clear first then fill
        try:
            company_input = self.page.locator("input[placeholder*='Acme Corp']").first
            await company_input.clear()
            await company_input.fill(request.client_name)
        except Exception as e:
            logger.warning(f"Could not fill company name with selector, trying alternative: {e}")
            await self.page.get_by_placeholder("Acme Corp").first.fill(request.client_name)

        await asyncio.sleep(0.3)

        # Save basic configuration
        await self.page.click(self.SELECTORS["save_basic_config_btn"])
        await asyncio.sleep(1)

    async def _substep_email_tool_connection(self, request: OrderRequest) -> None:
        """
        Sub-step 2: Email Tool Connection.

        The Hypertide UI remembers saved credentials (Bison is pre-selected with saved creds).
        We just need to click "Move on without saving" to continue.

        If no saved credentials exist, we would need to:
        1. Click Bison tool option
        2. Fill Bison URL
        3. Fill username/password
        4. Click "Move on without saving"
        """
        logger.info("Sub-step 2: Email Tool Connection")

        # Wait for section to load
        await asyncio.sleep(0.5)

        # Check if Bison is already selected (saved credentials)
        bison_selected = await self.page.locator("text=Selected Tool:").locator("text=Bison").count() > 0

        if not bison_selected:
            # Need to select Bison and fill credentials
            logger.info("Bison not pre-selected, filling credentials")

            try:
                await self.page.click(self.SELECTORS["tool_bison"])
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Could not click Bison tool: {e}")

            # Fill credentials from ENV
            bison_url = os.getenv("EMAILBISON_API_URL", "https://spellcast.hirecharm.com")
            bison_username = os.getenv("EMAILBISON_USERNAME", "")
            bison_password = os.getenv("EMAILBISON_PASSWORD", "")

            try:
                url_input = self.page.locator("input[placeholder*='send.example.com']").first
                await url_input.clear()
                await url_input.fill(bison_url)
            except Exception as e:
                logger.warning(f"Could not fill Bison URL: {e}")

            try:
                username_input = self.page.locator("input[placeholder*='name@example.com']").first
                await username_input.clear()
                await username_input.fill(bison_username)
            except Exception as e:
                logger.warning(f"Could not fill username: {e}")

            try:
                password_input = self.page.locator("input[placeholder*='Enter your password']").first
                await password_input.clear()
                await password_input.fill(bison_password)
            except Exception as e:
                logger.warning(f"Could not fill password: {e}")

        else:
            logger.info("Bison already selected with saved credentials")

        # ALWAYS skip saving credentials - continue without storing
        try:
            await self.page.click(self.SELECTORS["move_on_without_saving"])
        except Exception as e:
            logger.warning(f"Could not click 'Move on without saving': {e}")
            # Try alternative
            await self.page.get_by_text("Move on without saving").click()

        await asyncio.sleep(1)

    async def _substep_warmup_tags(self) -> None:
        """Sub-step 3: Warmup & Tags Setup - use defaults."""
        logger.info("Sub-step 3: Warmup & Tags Setup (defaults)")

        try:
            await self.page.click(self.SELECTORS["save_warmup_btn"])
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Could not click save warmup button: {e}")
            # Try to find and click any save button in this section
            await self.page.get_by_text("Save Warmup", exact=False).first.click()
            await asyncio.sleep(1)

    async def _substep_outbound_settings(self) -> None:
        """Sub-step 4: Outbound Settings - use defaults."""
        logger.info("Sub-step 4: Outbound Settings (defaults)")

        try:
            await self.page.click(self.SELECTORS["save_outbound_btn"])
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Could not click save outbound button: {e}")
            # Try to find and click any save button in this section
            await self.page.get_by_text("Save Outbound", exact=False).first.click()
            await asyncio.sleep(1)

    async def _substep_user_config(self, request: OrderRequest) -> None:
        """Sub-step 5: User Configuration - first/last name."""
        logger.info("Sub-step 5: User Configuration")

        # Get sender name from request
        first_name = "Chris"  # Default
        last_name = "Booth"   # Default

        # Try to get from inbox_names if available
        if hasattr(request, 'inbox_names') and request.inbox_names:
            first_name = request.inbox_names[0].first_name or first_name
            last_name = request.inbox_names[0].last_name or last_name
        # Or from sender_names JSONB field
        elif hasattr(request, 'sender_names') and request.sender_names:
            if isinstance(request.sender_names, list) and len(request.sender_names) > 0:
                sender = request.sender_names[0]
                first_name = sender.get('firstName', first_name)
                last_name = sender.get('lastName', last_name)

        logger.info(f"Adding user: {first_name} {last_name}")

        # Fill first name - placeholder is "Enter first name"
        try:
            first_input = self.page.locator("input[placeholder*='first name']").first
            await first_input.fill(first_name)
        except Exception as e:
            logger.warning(f"Could not fill first name: {e}")
            await self.page.get_by_placeholder("Enter first name").fill(first_name)

        await asyncio.sleep(0.3)

        # Fill last name - placeholder is "Enter last name"
        try:
            last_input = self.page.locator("input[placeholder*='last name']").first
            await last_input.fill(last_name)
        except Exception as e:
            logger.warning(f"Could not fill last name: {e}")
            await self.page.get_by_placeholder("Enter last name").fill(last_name)

        await asyncio.sleep(0.3)

        # Click Add User button
        try:
            await self.page.click(self.SELECTORS["add_user_btn"])
        except Exception as e:
            logger.warning(f"Could not click Add User: {e}")
            await self.page.get_by_text("+ Add User").click()

        await asyncio.sleep(1)

        # Click Save & Continue to Review
        try:
            await self.page.click(self.SELECTORS["save_continue_review"])
        except Exception as e:
            logger.warning(f"Could not click Save & Continue: {e}")
            await self.page.get_by_text("Save & Continue to Review").click()

        await asyncio.sleep(1)

    async def _capture_checkout_url(self) -> str:
        """
        Capture the Stripe checkout URL instead of completing payment.

        This method clicks the checkout button and waits for the Stripe
        redirect, then returns the checkout URL for manual payment.

        Returns:
            str: The Stripe checkout session URL
        """
        logger.info("Capturing Stripe checkout URL")

        # Click Checkout with Stripe button
        await self.page.click(self.SELECTORS["checkout_btn"])
        await asyncio.sleep(2)

        # Wait for Stripe redirect
        try:
            await self.page.wait_for_url("**/checkout.stripe.com/**", timeout=15000)
            checkout_url = self.page.url
            logger.info(f"Captured checkout URL: {checkout_url[:50]}...")
            return checkout_url
        except PlaywrightTimeoutError:
            # Check if we're already on Stripe
            current_url = self.page.url
            if "checkout.stripe.com" in current_url:
                logger.info(f"Already on Stripe checkout: {current_url[:50]}...")
                return current_url

            # Try to extract from page context
            checkout_url = await self.page.evaluate("""
                () => {
                    const stripeUrl = window.location.href;
                    if (stripeUrl.includes('checkout.stripe.com')) {
                        return stripeUrl;
                    }
                    const iframe = document.querySelector('iframe[src*="stripe"]');
                    if (iframe && iframe.src) {
                        return iframe.src;
                    }
                    return null;
                }
            """)

            if checkout_url:
                logger.info(f"Extracted checkout URL from page: {checkout_url[:50]}...")
                return checkout_url

            # Fallback: return current URL and log warning
            logger.warning(f"Could not capture Stripe URL, returning current: {current_url}")
            return current_url

    async def _step_review_order(self, request: OrderRequest) -> None:
        """Step 5: Review order before checkout."""
        logger.info("Step 5: Reviewing order")

        # Click proceed/continue/next button to advance to review
        proceed_buttons = [
            "button:has-text('Proceed')",
            "button:has-text('Continue')",
            "button:has-text('Next')",
            "button:has-text('Review')",
        ]

        for selector in proceed_buttons:
            btn = await self.page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click()
                break

        # Wait for review page
        await asyncio.sleep(1)

        # Verify order summary matches our request
        page_text = await self.page.content()
        expected_capacity = f"{request.quantity * 5}k" if request.quantity * 5 < 100 else f"{request.quantity * 5000}"

        # Log warning if summary doesn't match (but continue)
        if str(request.quantity) not in page_text:
            logger.warning("Order summary may not match request quantity")

    async def _step_checkout(self, request: OrderRequest) -> str:
        """
        Step 6: Capture Stripe checkout URL.

        Instead of completing payment automatically, we capture the Stripe
        checkout URL so the user can pay manually. Stripe may open in:
        1. Same page redirect
        2. New popup/tab window
        """
        logger.info("Step 6: Capturing checkout URL")

        # Set up popup listener BEFORE clicking (Stripe may open in new tab)
        popup_promise = self.page.wait_for_event('popup', timeout=20000)

        # Click checkout button using Playwright's reliable click method
        try:
            checkout_btn = self.page.get_by_role("button", name="Checkout with Stripe")
            await checkout_btn.click()
            logger.info("Clicked Checkout with Stripe button (native)")
        except Exception as e:
            logger.warning(f"Native click failed: {e}, trying alternatives")
            try:
                # Try by text
                await self.page.get_by_text("Checkout with Stripe").click()
                logger.info("Clicked Checkout via text selector")
            except:
                # JS fallback
                await self.page.evaluate("""
                    () => {
                        const btn = [...document.querySelectorAll('button')].find(
                            b => b.textContent.includes('Checkout')
                        );
                        if (btn) {
                            btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                        }
                    }
                """)
                logger.info("Clicked Checkout via JS dispatch")

        # Try to catch popup first (Stripe opens in new window)
        try:
            popup_page = await popup_promise
            await popup_page.wait_for_load_state('domcontentloaded')
            checkout_url = popup_page.url
            logger.info(f"Captured Stripe URL from popup: {checkout_url}")
            # Close the popup - user will click Slack link to open fresh
            await popup_page.close()
            return checkout_url
        except Exception as popup_error:
            logger.info(f"No popup detected: {popup_error}")

        # Fallback: Check if redirect happened in same page
        try:
            await self.page.wait_for_url("**/checkout.stripe.com/**", timeout=10000)
            checkout_url = self.page.url
            logger.info(f"Captured Stripe checkout URL (redirect): {checkout_url}")
            return checkout_url
        except PlaywrightTimeoutError:
            pass

        # Check if we're on Stripe
        if "stripe.com" in self.page.url:
            checkout_url = self.page.url
            logger.info(f"Already on Stripe: {checkout_url}")
            return checkout_url

        # Not on Stripe - check current URL
        logger.warning(f"Did not capture Stripe URL. Current URL: {self.page.url}")
        return ""

    async def _handle_stripe_checkout(self, request: OrderRequest) -> str:
        """
        Handle Stripe payment.

        If saved payment method exists, should auto-complete.
        Otherwise waits for user to complete payment.
        """
        timeout = self.stripe_config.checkout_timeout

        # Wait for Stripe to load (either iframe or redirect)
        try:
            # Check if we have a Stripe iframe
            stripe_frame = await self.page.wait_for_selector(
                "iframe[src*='stripe']",
                timeout=5000
            )

            if stripe_frame:
                logger.info("Stripe iframe detected")
                # If using saved payment, it may auto-submit
                # Otherwise wait for completion

        except PlaywrightTimeoutError:
            # No iframe - might be Stripe redirect or already completed
            logger.info("No Stripe iframe, checking for redirect or completion")

        # Wait for either:
        # 1. Success/confirmation page
        # 2. Timeout (manual completion needed)
        try:
            # Wait for URL to change to success/confirmation
            await self.page.wait_for_url(
                "**/success**,**/confirmation**,**/dashboard**",
                timeout=timeout
            )

            # Try to extract order ID from confirmation page
            order_id = await self._extract_order_id()
            return order_id

        except PlaywrightTimeoutError:
            # Check if we're on a confirmation page anyway
            if "success" in self.page.url or "confirm" in self.page.url:
                return await self._extract_order_id()

            # Check for payment error
            error_elem = await self.page.query_selector("text=declined, text=failed, text=error")
            if error_elem:
                raise PaymentError("Payment was declined or failed")

            # Timeout without completion
            raise PaymentTimeoutError(
                f"Payment did not complete within {timeout/1000} seconds. "
                "Manual completion may be required."
            )

    async def _extract_order_id(self) -> str:
        """Extract order ID from confirmation page."""
        # Try various methods to get order ID

        # Method 1: Look for data attribute
        order_elem = await self.page.query_selector("[data-order-id], [data-testid='order-id']")
        if order_elem:
            order_id = await order_elem.get_attribute("data-order-id")
            if order_id:
                return order_id

        # Method 2: Look for order ID in text
        # Pattern like "Order #12345" or "Order ID: ABC123"
        text_content = await self.page.content()

        import re
        patterns = [
            r"Order\s*#?\s*(\w+)",
            r"Order\s*ID:?\s*(\w+)",
            r"Confirmation\s*#?\s*(\w+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                return match.group(1)

        # Fallback: generate timestamp-based ID
        return f"HT-{datetime.now().strftime('%Y%m%d%H%M%S')}"


async def purchase_order(request: OrderRequest) -> OrderResult:
    """
    Convenience function to purchase a Hypertide order.

    This handles the full flow including authentication.

    Args:
        request: The order configuration

    Returns:
        OrderResult with success status and order details

    Usage:
        from hypertide_automation import purchase_order, OrderRequest, OrderType

        request = OrderRequest(
            client_name="Acme Corp",
            forwarding_domain="acme.com",
            order_type=OrderType.HYPERTIDE_ENTRA,
            quantity=2,
        )

        result = await purchase_order(request)
        print(f"Success: {result.success}")
    """
    from .client import HypertideClient

    async with HypertideClient() as client:
        await client.ensure_authenticated()

        automation = PurchaseAutomation(client)
        return await automation.execute(request)


# =============================================================================
# BUNDLE PURCHASE AUTOMATION (Mixed Entra + Google Orders)
# =============================================================================

class BundlePurchaseAutomation:
    """
    Automates purchasing of mixed order bundles (Entra + Google).

    Hypertide only allows purchasing ONE order type per checkout flow.
    This class orchestrates multiple sequential purchases for clients
    who need both Entra and Google inboxes.

    Flow:
    1. Calculate optimal order quantities from inbox targets
    2. Execute Entra purchase flow (if needed)
    3. Return to dashboard
    4. Execute Google purchase flow (if needed)
    5. Aggregate results

    Usage:
        async with HypertideClient() as client:
            await client.ensure_authenticated()

            # From MixedOrderRequest (high-level)
            automation = BundlePurchaseAutomation(client)
            result = await automation.execute_mixed(mixed_order_request)

            # Or from pre-built OrderBundle
            result = await automation.execute_bundle(order_bundle)

            if result.success:
                print(f"Total inboxes: {result.total_inboxes}")
                for order_result in result.order_results:
                    print(f"  {order_result.order_type.value}: {order_result.total_inboxes} inboxes")
    """

    def __init__(
        self,
        client: HypertideClient,
        stripe_config: Optional[StripeConfig] = None
    ):
        self.client = client
        self.stripe_config = stripe_config or StripeConfig()
        self.page = client.page
        self._purchase_automation = PurchaseAutomation(client, stripe_config)

    async def execute_mixed(self, request: MixedOrderRequest) -> BundleResult:
        """
        Execute a mixed order request (calculates and executes automatically).

        This is the primary entry point for client onboarding automation.
        Takes a high-level MixedOrderRequest and handles everything:
        - Calculates optimal order quantities
        - Creates OrderBundle
        - Executes sequential purchases
        - Returns aggregated results

        Args:
            request: High-level order with inbox targets

        Returns:
            BundleResult with all order outcomes

        Example:
            request = MixedOrderRequest(
                client_name="Acme Corp",
                forwarding_domain="acme.com",
                inbox_target=InboxTarget(entra_inboxes=500, google_inboxes=100),
                bison_credentials=BisonCredentials(
                    username="user@email.com",
                    password="secret",
                    workspace="Acme"
                )
            )

            result = await automation.execute_mixed(request)
            # Executes: 5 Entra orders (500 inboxes) + 7 Google orders (105 inboxes)
        """
        logger.info(
            "Creating order bundle from mixed request",
            client=request.client_name,
            entra_target=request.inbox_target.entra_inboxes,
            google_target=request.inbox_target.google_inboxes,
        )

        # Convert to bundle
        bundle = create_order_bundle(request)

        logger.info(
            "Order bundle created",
            client=bundle.client_name,
            entra_orders=bundle.breakdown.entra_orders,
            google_orders=bundle.breakdown.google_orders,
            total_inboxes=bundle.breakdown.total_inboxes,
        )

        # Execute the bundle
        return await self.execute_bundle(bundle)

    async def execute_bundle(self, bundle: OrderBundle) -> BundleResult:
        """
        Execute a pre-built OrderBundle (sequential purchases).

        Args:
            bundle: Bundle containing 1-2 OrderRequests

        Returns:
            BundleResult with aggregated outcomes
        """
        logger.info(
            "Starting bundle purchase",
            client=bundle.client_name,
            order_count=bundle.order_count,
            requires_multiple=bundle.requires_multiple_purchases,
        )

        order_results: list[OrderResult] = []
        errors: list[str] = []

        for i, order in enumerate(bundle.orders, 1):
            logger.info(
                f"Executing order {i}/{bundle.order_count}",
                order_type=order.order_type.value,
                quantity=order.quantity,
            )

            try:
                # Execute individual order
                result = await self._purchase_automation.execute(order)
                order_results.append(result)

                if not result.success:
                    errors.append(
                        f"{order.order_type.value}: {result.error_message}"
                    )

                # If more orders to come, return to dashboard
                if i < bundle.order_count and result.success:
                    logger.info("Returning to dashboard for next order")
                    await self.client.goto_dashboard()
                    await asyncio.sleep(2)  # Brief pause between orders

            except Exception as e:
                logger.error(f"Order {i} failed with exception", error=str(e))
                errors.append(f"{order.order_type.value}: {str(e)}")

                # Create failed result
                failed_result = OrderResult(
                    success=False,
                    client_name=order.client_name,
                    forwarding_domain=order.forwarding_domain,
                    order_type=order.order_type,
                    quantity=order.quantity,
                    error_message=str(e),
                )
                order_results.append(failed_result)

        # Aggregate results
        successful_orders = sum(1 for r in order_results if r.success)
        failed_orders = len(order_results) - successful_orders
        total_inboxes = sum(r.total_inboxes for r in order_results if r.success)
        total_capacity = sum(r.monthly_capacity for r in order_results if r.success)

        bundle_result = BundleResult(
            success=(failed_orders == 0),
            client_name=bundle.client_name,
            forwarding_domain=bundle.forwarding_domain,
            order_results=order_results,
            total_orders=len(order_results),
            successful_orders=successful_orders,
            failed_orders=failed_orders,
            total_inboxes=total_inboxes,
            total_monthly_capacity=total_capacity,
            errors=errors,
        )

        logger.info(
            "Bundle purchase completed",
            success=bundle_result.success,
            successful_orders=successful_orders,
            failed_orders=failed_orders,
            total_inboxes=total_inboxes,
        )

        return bundle_result


async def purchase_mixed_order(request: MixedOrderRequest) -> BundleResult:
    """
    Convenience function to purchase a mixed Entra + Google order.

    This is the primary function for client onboarding automation.
    Handles authentication and executes all required purchase flows.

    Args:
        request: MixedOrderRequest with inbox targets

    Returns:
        BundleResult with all order outcomes

    Example:
        from hypertide_automation import (
            purchase_mixed_order,
            MixedOrderRequest,
            InboxTarget,
            BisonCredentials,
            InboxConfig,
        )

        request = MixedOrderRequest(
            client_name="Acme Corp",
            forwarding_domain="acme.com",
            inbox_target=InboxTarget(
                entra_inboxes=500,   # Will create 5 Entra orders
                google_inboxes=100,  # Will create 7 Google orders
            ),
            bison_credentials=BisonCredentials(
                username="user@email.com",
                password="secret",
                workspace="Acme Workspace",
                bison_url="https://spellcast.hirecharm.com"
            ),
            users=[
                InboxConfig(first_name="alex", last_name="morgan"),
                InboxConfig(first_name="jordan", last_name="smith"),
            ]
        )

        result = await purchase_mixed_order(request)

        if result.success:
            print(f"All {result.total_orders} orders completed!")
            print(f"Total inboxes: {result.total_inboxes}")
            print(f"Monthly capacity: {result.total_monthly_capacity} emails/mo")
        else:
            print(f"Some orders failed: {result.errors}")
    """
    from .client import HypertideClient

    async with HypertideClient() as client:
        await client.ensure_authenticated()

        automation = BundlePurchaseAutomation(client)
        return await automation.execute_mixed(request)
