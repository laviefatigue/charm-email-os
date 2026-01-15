"""
Hypertide browser client using Playwright.

This client manages browser sessions and provides low-level
interaction with the Hypertide web interface.
"""

import asyncio
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

import structlog
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
)

from .config import HypertideConfig, get_config
from .exceptions import (
    AuthenticationError,
    SessionExpiredError,
    NavigationError,
    ElementNotFoundError,
)

logger = structlog.get_logger()


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

        # Set default timeout
        self._context.set_default_timeout(self.config.timeout)

        # Create main page
        self._page = await self._context.new_page()

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
        """Check if we have a valid session."""
        try:
            await self.page.goto(self.config.dashboard_url, wait_until="networkidle")
            current_url = self.page.url

            # If we're still on dashboard, we're authenticated
            if "/dashboard" in current_url:
                logger.info("Session is valid")
                return True

            # If redirected to signin, session expired
            if "/signin" in current_url:
                logger.info("Session expired, need to re-authenticate")
                return False

            return False
        except Exception as e:
            logger.error("Auth check failed", error=str(e))
            return False

    async def ensure_authenticated(self) -> None:
        """
        Ensure we have a valid authenticated session.

        If not authenticated, will wait for manual login.
        """
        if await self.is_authenticated():
            return

        logger.warning("Not authenticated - manual login required")

        # Navigate to signin
        await self.page.goto(self.config.signin_url, wait_until="networkidle")

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

    async def wait_for_manual_login(self, timeout: int = 300000) -> None:
        """Wait for user to complete manual login."""
        await self.page.goto(self.config.signin_url)
        await self.page.wait_for_url("**/dashboard**", timeout=timeout)
        await self.save_session()

    # =========================================================================
    # Navigation
    # =========================================================================

    async def goto_dashboard(self) -> None:
        """Navigate to main dashboard."""
        await self.page.goto(self.config.dashboard_url, wait_until="networkidle")
        if "/dashboard" not in self.page.url:
            raise NavigationError(f"Failed to navigate to dashboard, got {self.page.url}")

    async def goto_choose_plan(self) -> None:
        """Navigate to plan selection page."""
        await self.page.goto(self.config.choose_plan_url, wait_until="networkidle")
        if "/choose-plan" not in self.page.url:
            raise NavigationError(f"Failed to navigate to choose-plan, got {self.page.url}")

    async def goto_billing(self) -> None:
        """Navigate to billing page."""
        await self.page.goto(f"{self.config.base_url}/billing", wait_until="networkidle")

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
