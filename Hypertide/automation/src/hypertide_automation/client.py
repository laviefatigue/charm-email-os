"""
Hypertide browser client using Playwright.

This client manages browser sessions and provides low-level
interaction with the Hypertide web interface.

Reliability features:
- Retry logic with exponential backoff for navigation
- Session validation before operations
- Login detection during flows (redirect to /signin)
- Health check to verify site accessibility
- Configurable per-operation timeouts
"""

import asyncio
from pathlib import Path
from typing import Optional, Callable, TypeVar
from contextlib import asynccontextmanager
from functools import wraps

import structlog
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    Response,
    TimeoutError as PlaywrightTimeoutError,
)

from .config import HypertideConfig, get_config
from .exceptions import (
    AuthenticationError,
    SessionExpiredError,
    NavigationError,
    ElementNotFoundError,
    HypertideUnavailableError,
    RetryExhaustedError,
)

logger = structlog.get_logger()

T = TypeVar('T')


class HypertideClient:
    """
    Browser automation client for Hypertide.

    Manages Playwright browser lifecycle and provides methods for
    interacting with the Hypertide web interface.

    Usage:
        async with HypertideClient() as client:
            await client.ensure_authenticated()
            # ... perform operations
    """

    def __init__(self, config: Optional[HypertideConfig] = None):
        self.config = config or get_config()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def __aenter__(self) -> "HypertideClient":
        """Start browser session."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up browser session."""
        await self.close()

    async def start(self) -> None:
        """Initialize Playwright and browser."""
        logger.info("Starting Hypertide client")

        self._playwright = await async_playwright().start()

        # Use Chromium for best compatibility
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )

        # Try to load existing session or create new context
        await self._setup_context()

    async def _setup_context(self) -> None:
        """Set up browser context, loading saved session if available."""
        storage_path = self.config.session_storage_path

        if storage_path.exists():
            logger.info("Loading saved session", path=str(storage_path))
            try:
                self._context = await self._browser.new_context(
                    storage_state=str(storage_path)
                )
            except Exception as e:
                logger.warning("Failed to load session, creating new", error=str(e))
                self._context = await self._browser.new_context()
        else:
            logger.info("No saved session, creating new context")
            self._context = await self._browser.new_context()

        # Set default timeout (use element timeout for most interactions)
        self._context.set_default_timeout(self.config.element_timeout)
        self._context.set_default_navigation_timeout(self.config.navigation_timeout)

        # Create main page
        self._page = await self._context.new_page()

    # =========================================================================
    # Retry Logic
    # =========================================================================

    async def _with_retry(
        self,
        operation: str,
        func: Callable,
        max_retries: Optional[int] = None,
    ) -> T:
        """
        Execute an async function with retry logic and exponential backoff.

        Args:
            operation: Name of the operation (for logging)
            func: Async function to execute
            max_retries: Override default max retries

        Returns:
            Result of the function

        Raises:
            RetryExhaustedError: If all retries fail
        """
        retries = max_retries or self.config.max_retries
        delay = self.config.retry_delay / 1000  # Convert to seconds
        last_error: Optional[Exception] = None

        for attempt in range(1, retries + 1):
            try:
                return await func()
            except (PlaywrightTimeoutError, NavigationError, SessionExpiredError) as e:
                last_error = e
                if attempt < retries:
                    logger.warning(
                        f"Retry {attempt}/{retries} for {operation}",
                        error=str(e),
                        next_delay=f"{delay:.1f}s",
                    )
                    await asyncio.sleep(delay)
                    delay *= self.config.retry_backoff  # Exponential backoff
                else:
                    logger.error(f"All {retries} retries exhausted for {operation}")

        raise RetryExhaustedError(operation, retries, last_error)

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> bool:
        """
        Check if Hypertide site is accessible.

        Returns:
            True if site is accessible, raises HypertideUnavailableError otherwise
        """
        logger.info("Checking Hypertide site health")
        try:
            response = await self.page.goto(
                self.config.signin_url,
                wait_until="domcontentloaded",
                timeout=30000,
            )

            if response is None:
                raise HypertideUnavailableError(
                    self.config.signin_url,
                    "No response received"
                )

            if response.status >= 500:
                raise HypertideUnavailableError(
                    self.config.signin_url,
                    f"Server error: {response.status}"
                )

            # Check for expected content on signin page
            # Use separate queries since we can't mix CSS and Playwright text selectors
            signin_indicator = await self.page.query_selector("input[type='email']")
            if not signin_indicator:
                signin_indicator = await self.page.query_selector("button")
            if signin_indicator:
                logger.info("Hypertide site is healthy")
                return True

            logger.warning("Signin page loaded but content unexpected")
            return True  # Page loaded, even if content is different

        except PlaywrightTimeoutError:
            raise HypertideUnavailableError(
                self.config.signin_url,
                "Connection timed out"
            )
        except Exception as e:
            if isinstance(e, HypertideUnavailableError):
                raise
            raise HypertideUnavailableError(
                self.config.signin_url,
                str(e)
            )

    async def save_session(self) -> None:
        """Save current session for reuse."""
        if self._context:
            storage_path = self.config.session_storage_path
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=str(storage_path))
            logger.info("Session saved", path=str(storage_path))

    async def close(self) -> None:
        """Close browser and cleanup."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Hypertide client closed")

    @property
    def page(self) -> Page:
        """Get the current page."""
        if not self._page:
            raise RuntimeError("Client not started. Use 'async with HypertideClient()' or call start()")
        return self._page

    # =========================================================================
    # Authentication
    # =========================================================================

    async def is_authenticated(self) -> bool:
        """
        Check if we have a valid session.

        Uses domcontentloaded instead of networkidle for faster, more reliable checks.
        """
        try:
            # Use shorter timeout for auth check
            timeout = self.config.auth_check_timeout

            response = await self.page.goto(
                self.config.dashboard_url,
                wait_until="domcontentloaded",
                timeout=timeout,
            )

            # Wait a bit for any client-side redirects
            await asyncio.sleep(1)

            current_url = self.page.url

            # If we're still on dashboard, we're authenticated
            if "/dashboard" in current_url:
                # Double-check by looking for dashboard content
                dashboard_content = await self.page.query_selector(
                    "text=Dashboard, text=Orders, text=Place New Order, [data-testid='dashboard']"
                )
                if dashboard_content:
                    logger.info("Session is valid (dashboard content found)")
                    return True

                # URL says dashboard but no content - might still be loading
                logger.info("Session appears valid (on dashboard URL)")
                return True

            # If redirected to signin, session expired
            if "/signin" in current_url or "/login" in current_url:
                logger.info("Session expired, need to re-authenticate")
                return False

            # Unknown state - try to check if logged in by looking for user menu
            user_indicator = await self.page.query_selector(
                "[data-testid='user-menu'], text=Logout, text=Account"
            )
            if user_indicator:
                logger.info("Session valid (user indicator found)")
                return True

            logger.warning(f"Unknown auth state, URL: {current_url}")
            return False

        except PlaywrightTimeoutError:
            logger.error("Auth check timed out - site may be slow or unavailable")
            return False
        except Exception as e:
            logger.error("Auth check failed", error=str(e))
            return False

    async def auto_login(self) -> bool:
        """
        Attempt automated login using configured credentials.

        Returns:
            True if login succeeded, False if credentials not configured

        Raises:
            AuthenticationError: If login fails with provided credentials
        """
        # Check if credentials are configured
        if not self.config.auth_email or not self.config.auth_password:
            logger.info("Auto-login skipped - credentials not configured")
            return False

        logger.info("Attempting automated login", email=self.config.auth_email)

        try:
            # Navigate to signin page
            await self.page.goto(
                self.config.signin_url,
                wait_until="domcontentloaded",
                timeout=self.config.navigation_timeout,
            )

            # Wait for login form to be rendered (React/JS may take time)
            # Wait for either the email input or Sign In button to appear
            logger.debug("Waiting for login form to render...")
            try:
                await self.page.wait_for_selector(
                    'input, button:has-text("Sign In")',
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                raise AuthenticationError("Login form did not render within timeout")

            # Additional wait for form to be fully interactive
            await asyncio.sleep(2)

            # Fill email field - try multiple selectors
            # Hypertide uses placeholder="youremail@server.com"
            email_filled = False
            email_selectors = [
                'input[placeholder*="email"]',  # Matches "youremail@server.com"
                'input[placeholder*="@"]',      # Any placeholder with @ symbol
                'input[type="email"]',
                'input[name="email"]',
                'input[id="email"]',
            ]

            # First, get all inputs and try to find the email one
            all_inputs = await self.page.query_selector_all('input')
            logger.debug(f"Found {len(all_inputs)} input fields on page")

            for selector in email_selectors:
                try:
                    email_input = await self.page.query_selector(selector)
                    if email_input:
                        await email_input.fill(self.config.auth_email)
                        email_filled = True
                        logger.debug(f"Email filled using selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

            # Fallback: try the first text input on the page
            if not email_filled and all_inputs:
                try:
                    # The first input is typically the email field
                    await all_inputs[0].fill(self.config.auth_email)
                    email_filled = True
                    logger.debug("Email filled using first input fallback")
                except Exception as e:
                    logger.debug(f"First input fallback failed: {e}")

            if not email_filled:
                raise AuthenticationError("Could not find email input field")

            # Fill password field - try multiple selectors
            password_filled = False
            password_selectors = [
                'input[type="password"]',
                'input[name="password"]',
                'input[id="password"]',
            ]
            for selector in password_selectors:
                try:
                    password_input = await self.page.query_selector(selector)
                    if password_input:
                        await password_input.fill(self.config.auth_password)
                        password_filled = True
                        logger.debug(f"Password filled using selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Password selector {selector} failed: {e}")
                    continue

            # Fallback: try the second input (or last input) for password
            if not password_filled and len(all_inputs) >= 2:
                try:
                    await all_inputs[1].fill(self.config.auth_password)
                    password_filled = True
                    logger.debug("Password filled using second input fallback")
                except Exception as e:
                    logger.debug(f"Second input fallback failed: {e}")

            if not password_filled:
                raise AuthenticationError("Could not find password input field")

            # Small delay before clicking submit
            await asyncio.sleep(0.5)

            # Click Sign In button - try multiple approaches
            signed_in = False
            button_selectors = [
                'button:has-text("Sign In")',
                'button:has-text("Sign in")',
                'button:has-text("Login")',
                'button[type="submit"]',
                'input[type="submit"]',
            ]
            for selector in button_selectors:
                try:
                    button = await self.page.query_selector(selector)
                    if button:
                        await button.click()
                        signed_in = True
                        logger.debug(f"Sign in clicked using selector: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"Button selector {selector} failed: {e}")
                    continue

            # Fallback: find any button and click it
            if not signed_in:
                try:
                    buttons = await self.page.query_selector_all('button')
                    for btn in buttons:
                        text = await btn.inner_text()
                        if 'sign' in text.lower() or 'log' in text.lower():
                            await btn.click()
                            signed_in = True
                            logger.debug(f"Sign in clicked via text search: {text}")
                            break
                except Exception as e:
                    logger.debug(f"Button fallback failed: {e}")

            if not signed_in:
                raise AuthenticationError("Could not find sign in button")

            # Wait for navigation to dashboard (indicates successful login)
            try:
                await self.page.wait_for_url(
                    "**/dashboard**",
                    timeout=self.config.login_timeout,
                )
                logger.info("Auto-login successful")

                # Save session for future use
                await self.save_session()
                return True

            except PlaywrightTimeoutError:
                # Check if still on signin page - likely wrong credentials
                current_url = self.page.url
                if "/signin" in current_url or "/login" in current_url:
                    # Look for error message
                    error_msg = await self.page.query_selector(
                        '[class*="error"], [class*="alert"], text=Invalid, text=incorrect'
                    )
                    if error_msg:
                        try:
                            error_text = await error_msg.inner_text()
                            raise AuthenticationError(f"Login failed: {error_text}")
                        except Exception:
                            pass
                    raise AuthenticationError(
                        "Login failed - invalid credentials or unexpected error"
                    )
                raise AuthenticationError(f"Login redirect failed, ended up at: {current_url}")

        except AuthenticationError:
            raise
        except Exception as e:
            raise AuthenticationError(f"Auto-login failed: {str(e)}")

    async def ensure_authenticated(self) -> None:
        """
        Ensure we have a valid authenticated session.

        Tries automated login first if credentials are configured,
        then falls back to manual login if needed.
        Includes health check before attempting authentication.
        """
        # First, check if site is accessible
        try:
            await self.health_check()
        except HypertideUnavailableError as e:
            logger.error("Cannot authenticate - site unavailable", error=str(e))
            raise

        if await self.is_authenticated():
            return

        logger.warning("Session not valid - attempting authentication")

        # Try automated login first if credentials are configured
        if self.config.auth_email and self.config.auth_password:
            try:
                if await self.auto_login():
                    return  # Auto-login succeeded
            except AuthenticationError as e:
                logger.warning(f"Auto-login failed: {e}")
                # Fall through to manual login

        # Fall back to manual login
        logger.warning("Falling back to manual login")

        # Navigate to signin
        await self.page.goto(
            self.config.signin_url,
            wait_until="domcontentloaded",
            timeout=self.config.navigation_timeout,
        )

        # Wait for user to complete login (watch for redirect to dashboard)
        print("\n" + "=" * 60)
        print("MANUAL LOGIN REQUIRED")
        print("Please complete the login in the browser window.")
        print("Waiting for authentication...")
        print("=" * 60 + "\n")

        try:
            # Wait for navigation to dashboard (up to 5 minutes for manual login)
            await self.page.wait_for_url("**/dashboard**", timeout=300000)
            logger.info("Login successful")

            # Save session for future use
            await self.save_session()

        except PlaywrightTimeoutError:
            raise AuthenticationError("Login timed out after 5 minutes")

    async def validate_session_for_purchase(self) -> bool:
        """
        Validate that session is ready for a purchase flow.

        This is more thorough than is_authenticated() - it ensures
        the session can actually start a purchase.

        Returns:
            True if session is valid and ready for purchase

        Raises:
            SessionExpiredError: If session is invalid
        """
        logger.info("Validating session for purchase flow")

        # Check basic auth
        if not await self.is_authenticated():
            raise SessionExpiredError("Session is not authenticated")

        # Try to access choose-plan page to verify purchase capability
        try:
            response = await self.page.goto(
                self.config.choose_plan_url,
                wait_until="domcontentloaded",
                timeout=self.config.navigation_timeout,
            )

            # Wait for page to settle
            await asyncio.sleep(1)

            current_url = self.page.url

            # If redirected to signin, session is invalid for purchases
            if "/signin" in current_url or "/login" in current_url:
                raise SessionExpiredError(
                    "Session redirected to login when accessing purchase page"
                )

            # Check we're on choose-plan page
            if "/choose-plan" not in current_url:
                logger.warning(
                    f"Unexpected redirect during session validation: {current_url}"
                )
                # May still be OK if on dashboard
                if "/dashboard" in current_url:
                    return True
                raise SessionExpiredError(f"Unexpected redirect to: {current_url}")

            # Look for plan selection content
            plan_content = await self.page.query_selector(
                "text=Hypertide Entra, text=Hypertide Google, text=Choose, text=Select Plan"
            )
            if plan_content:
                logger.info("Session validated - ready for purchase")
                return True

            logger.warning("On choose-plan URL but content not found")
            return True  # URL is correct, proceed anyway

        except PlaywrightTimeoutError:
            raise SessionExpiredError(
                "Timed out validating session - site may be slow"
            )

    def is_on_login_page(self) -> bool:
        """Check if currently on the login page (session may have expired mid-flow)."""
        url = self.page.url
        return "/signin" in url or "/login" in url

    async def wait_for_manual_login(self, timeout: int = 300000) -> None:
        """Wait for user to complete manual login."""
        await self.page.goto(
            self.config.signin_url,
            wait_until="domcontentloaded",
        )
        await self.page.wait_for_url("**/dashboard**", timeout=timeout)
        await self.save_session()

    # =========================================================================
    # Navigation (with retry logic)
    # =========================================================================

    async def _navigate_with_validation(
        self,
        url: str,
        expected_path: str,
        page_name: str,
    ) -> None:
        """
        Navigate to a URL and validate we arrived at the expected path.

        Uses domcontentloaded instead of networkidle for reliability.
        Checks for session expiration (redirect to /signin) unless we're
        intentionally navigating to the signin page.

        Args:
            url: Full URL to navigate to
            expected_path: Expected path fragment (e.g., "/dashboard")
            page_name: Human-readable page name for logging

        Raises:
            NavigationError: If navigation fails
            SessionExpiredError: If redirected to login page (unexpectedly)
        """
        logger.debug(f"Navigating to {page_name}", url=url)

        response = await self.page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=self.config.navigation_timeout,
        )

        # Wait for any client-side routing to complete
        await asyncio.sleep(1.5)

        current_url = self.page.url

        # Check for session expiration (redirect to login)
        # Only flag as expired if we weren't trying to go to signin
        if self.is_on_login_page() and expected_path != "/signin":
            raise SessionExpiredError(
                f"Session expired while navigating to {page_name}. "
                f"Redirected to: {current_url}"
            )

        # Verify we arrived at expected page
        if expected_path not in current_url:
            raise NavigationError(
                f"Failed to navigate to {page_name}. "
                f"Expected '{expected_path}' in URL, got: {current_url}"
            )

        logger.info(f"Successfully navigated to {page_name}")

    async def goto_dashboard(self) -> None:
        """Navigate to main dashboard with retry logic."""
        async def _nav():
            await self._navigate_with_validation(
                self.config.dashboard_url,
                "/dashboard",
                "dashboard"
            )

        await self._with_retry("navigate to dashboard", _nav)

    async def goto_choose_plan(self) -> None:
        """Navigate to plan selection page with retry logic."""
        async def _nav():
            await self._navigate_with_validation(
                self.config.choose_plan_url,
                "/choose-plan",
                "choose plan"
            )

        await self._with_retry("navigate to choose-plan", _nav)

    async def goto_select_domains(self) -> None:
        """Navigate to domain selection page with retry logic."""
        async def _nav():
            await self._navigate_with_validation(
                f"{self.config.base_url}/select-domains",
                "/select-domains",
                "select domains"
            )

        await self._with_retry("navigate to select-domains", _nav)

    async def goto_setup_domain_settings(self) -> None:
        """Navigate to domain settings page with retry logic."""
        async def _nav():
            await self._navigate_with_validation(
                f"{self.config.base_url}/setup-domain-settings",
                "/setup-domain-settings",
                "setup domain settings"
            )

        await self._with_retry("navigate to setup-domain-settings", _nav)

    async def goto_review_order(self) -> None:
        """Navigate to order review page with retry logic."""
        async def _nav():
            await self._navigate_with_validation(
                f"{self.config.base_url}/review-order",
                "/review-order",
                "review order"
            )

        await self._with_retry("navigate to review-order", _nav)

    async def goto_billing(self) -> None:
        """Navigate to billing page with retry logic."""
        async def _nav():
            await self._navigate_with_validation(
                f"{self.config.base_url}/billing",
                "/billing",
                "billing"
            )

        await self._with_retry("navigate to billing", _nav)

    async def wait_for_page_ready(self, expected_content: str = None) -> None:
        """
        Wait for the current page to be fully loaded and ready.

        Args:
            expected_content: Optional text to wait for on the page
        """
        # Wait for network to settle (but with a reasonable timeout)
        try:
            await self.page.wait_for_load_state("networkidle", timeout=15000)
        except PlaywrightTimeoutError:
            # Network didn't settle, but page may still be usable
            logger.debug("Network idle timeout, proceeding anyway")

        if expected_content:
            try:
                await self.page.wait_for_selector(
                    f"text={expected_content}",
                    timeout=self.config.element_timeout,
                )
            except PlaywrightTimeoutError:
                logger.warning(f"Expected content '{expected_content}' not found")

    # =========================================================================
    # Element Interaction Helpers
    # =========================================================================

    async def click_button(self, text: str) -> None:
        """Click a button by its text content."""
        try:
            button = self.page.get_by_role("button", name=text)
            await button.click()
        except PlaywrightTimeoutError:
            raise ElementNotFoundError(f"button:{text}", self.page.url)

    async def click_text(self, text: str) -> None:
        """Click any element containing specific text."""
        try:
            await self.page.get_by_text(text).click()
        except PlaywrightTimeoutError:
            raise ElementNotFoundError(f"text:{text}", self.page.url)

    async def select_dropdown_option(self, dropdown_selector: str, option_text: str) -> None:
        """Select an option from a dropdown."""
        try:
            # Click to open dropdown
            await self.page.click(dropdown_selector)
            await asyncio.sleep(0.3)  # Wait for dropdown to open

            # Click the option
            await self.page.get_by_text(option_text, exact=False).click()
        except PlaywrightTimeoutError:
            raise ElementNotFoundError(f"dropdown:{dropdown_selector}", self.page.url)

    async def fill_input(self, selector: str, value: str) -> None:
        """Fill an input field."""
        try:
            await self.page.fill(selector, value)
        except PlaywrightTimeoutError:
            raise ElementNotFoundError(selector, self.page.url)

    async def wait_for_text(self, text: str, timeout: Optional[int] = None) -> None:
        """Wait for specific text to appear on page."""
        timeout = timeout or self.config.timeout
        try:
            await self.page.get_by_text(text).wait_for(timeout=timeout)
        except PlaywrightTimeoutError:
            raise ElementNotFoundError(f"text:{text}", self.page.url)

    # =========================================================================
    # Screenshots
    # =========================================================================

    async def take_screenshot(self, name: str) -> Path:
        """Take a screenshot for debugging."""
        screenshot_dir = self.config.screenshot_dir
        screenshot_dir.mkdir(parents=True, exist_ok=True)

        path = screenshot_dir / f"{name}.png"
        await self.page.screenshot(path=str(path), full_page=True)
        logger.info("Screenshot saved", path=str(path))
        return path

    async def screenshot_on_error(self, error_name: str) -> Optional[Path]:
        """Take screenshot when an error occurs."""
        if self.config.screenshot_on_error:
            return await self.take_screenshot(f"error-{error_name}")
        return None


@asynccontextmanager
async def hypertide_session(config: Optional[HypertideConfig] = None):
    """
    Context manager for Hypertide browser session.

    Usage:
        async with hypertide_session() as client:
            await client.ensure_authenticated()
            # ... operations
    """
    client = HypertideClient(config)
    try:
        await client.start()
        yield client
    finally:
        await client.close()
