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

    # UI Selectors (updated from flow map 2025-12-10)
    # Source: D:\BrainOn\Hypertide\automation\docs\purchase-flow-map.yaml
    SELECTORS = {
        # =========== Step 1: Choose Plan ===========
        "entra_plan_card": "text=Hypertide Entra",
        "google_plan_card": "text=Hypertide Google",
        "entra_quantity_dropdown": "combobox[value*='Entra']",
        "google_quantity_dropdown": "combobox[value*='Google']",
        "entra_select_button": "button:has-text('Select Plan'):near(:text('Hypertide Entra'))",
        "google_select_button": "button:has-text('Select Plan'):near(:text('Hypertide Google'))",
        "place_new_order": "text=Place New Order",

        # =========== Step 2: Select Domains ===========
        # Domain source selection
        "purchase_domains_option": "text=Purchase domains",
        "use_own_domains_option": "text=Use my own domains",

        # Purchase mode (domain search)
        "discovery_search_btn": "button:has-text('Discovery Search')",
        "exact_search_btn": "button:has-text('Exact Search')",
        "domain_search_input": "textbox[placeholder*='Search for a domain']",
        "search_domains_btn": "button:has-text('Search Domains')",

        # BYOD mode
        "byod_domain_input": "textbox[placeholder*='example1.com']",
        "add_domain_btn": "button:has-text('Add Your Domain')",
        "max_domains_indicator": "button:has-text('Max Domains Added')",

        # DNS configuration (BYOD)
        "dns_confirmed_btn": "button:has-text('I have configured DNS')",

        # Navigation
        "continue_to_settings": "button:has-text('Continue to Domain Settings')",
        "go_back_btn": "button:has-text('Go Back')",

        # =========== Step 3: Setup Domain Settings ===========
        # Basic configuration
        "forwarding_url_input": "textbox[placeholder*='example.com']",
        "company_client_input": "textbox[placeholder*='Acme Corp']",
        "save_basic_config_btn": "button:has-text('Save Basic Configuration')",

        # Email tool selection
        "saved_credentials_btn": "button:has-text('Saved Credentials')",
        "tool_instantly": "text=Instantly",
        "tool_smartlead": "text=Smartlead",
        "tool_bison": "text=Bison",
        "tool_other": "text=Other",

        # Credentials
        "username_input": "textbox[placeholder='name@example.com']",
        "password_input": "textbox[placeholder='Enter your password']",
        "workspace_selector": "text=Click to select workspace",
        "bison_url_input": "textbox[placeholder*='send.example.com']",

        # User configuration
        "first_name_input": "textbox[placeholder='Enter first name']",
        "last_name_input": "textbox[placeholder='Enter last name']",
        "add_user_btn": "button:has-text('+ Add User')",

        # Navigation
        "save_and_continue_btn": "button:has-text('Save & Continue')",
        "next_btn": "button:has-text('Next')",
        "save_continue_review": "button:has-text('Save & Continue to Review')",
        "continue_to_review": "button:has-text('Continue to Review')",

        # =========== Step 4: Review Order ===========
        "checkout_button": "button:has-text('Checkout')",
        "proceed_checkout": "button:has-text('Proceed to Checkout')",

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
            # Step 1: Navigate to choose plan
            await self._step_choose_plan(request)

            # Step 2: Select quantity
            await self._step_select_quantity(request)

            # Step 3: Configure domains (if custom)
            await self._step_configure_domains(request)

            # Step 4: Setup domain settings
            await self._step_setup_settings(request)

            # Step 5: Review order
            await self._step_review_order(request)

            # Step 6: Complete payment
            order_id = await self._step_checkout(request)

            # Success!
            result = OrderResult(
                success=True,
                order_id=order_id,
                client_name=request.client_name,
                forwarding_domain=request.forwarding_domain,
                order_type=request.order_type,
                quantity=request.quantity,
                total_inboxes=request.expected_inboxes,
                monthly_capacity=request.expected_monthly_capacity,
            )

            logger.info("Purchase completed successfully", order_id=order_id)
            return result

        except Exception as e:
            logger.error("Purchase failed", error=str(e))

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

    # =========================================================================
    # Step Implementations
    # =========================================================================

    async def _step_choose_plan(self, request: OrderRequest) -> None:
        """Step 1: Navigate and select plan type."""
        logger.info("Step 1: Choosing plan")

        await self.client.goto_choose_plan()

        # Click the appropriate plan card
        if request.order_type == OrderType.HYPERTIDE_ENTRA:
            await self.page.click(self.SELECTORS["entra_plan_card"])
        else:
            await self.page.click(self.SELECTORS["google_plan_card"])

        await asyncio.sleep(0.5)  # Wait for selection to register

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
        """Step 3: Configure domains if custom domains provided."""
        if not request.domains:
            logger.info("Step 3: Using Hypertide default domains (skipping)")
            return

        logger.info("Step 3: Configuring custom domains", count=len(request.domains))

        for domain_config in request.domains:
            domain_name = domain_config.full_domain

            # Find domain input and enter domain
            try:
                input_elem = await self.page.wait_for_selector(
                    self.SELECTORS["domain_input"],
                    timeout=5000
                )
                await input_elem.fill(domain_name)

                # Click add button
                add_btn = await self.page.wait_for_selector(
                    self.SELECTORS["add_domain_button"],
                    timeout=5000
                )
                await add_btn.click()

                # Wait for domain to be added (check for success indicator)
                await asyncio.sleep(1)

                # Check if domain was rejected
                error_text = await self.page.query_selector("text=unavailable")
                if error_text:
                    raise DomainUnavailableError(domain_name)

            except PlaywrightTimeoutError:
                logger.warning(
                    "Domain input not found, UI may be different",
                    domain=domain_name
                )

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
        """Step 6: Complete Stripe checkout."""
        logger.info("Step 6: Processing payment")

        # Click checkout button
        checkout_buttons = [
            "button:has-text('Checkout')",
            "button:has-text('Pay')",
            "button:has-text('Complete Order')",
            "button:has-text('Place Order')",
        ]

        for selector in checkout_buttons:
            btn = await self.page.query_selector(selector)
            if btn and await btn.is_visible():
                await btn.click()
                break

        # Handle Stripe checkout
        # This could be embedded iframe or redirect to Stripe
        order_id = await self._handle_stripe_checkout(request)

        return order_id

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
                bison_url="https://send.hirecharm.com"
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
