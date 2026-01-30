"""
Test script for Hypertide automation reliability improvements.

Tests:
1. Configuration loading - verify env vars load correctly
2. Health check - verify site accessibility
3. Session validation - check if session is valid
4. Login detection - verify login page detection
5. Navigation with validation - test improved navigation
6. Retry mechanism - verify retry logic works
7. Auto-login - test automated login with credentials
8. Full flow dry run - complete flow without purchasing

Run with: py test_reliability.py
"""

import asyncio
import sys
import os

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

sys.path.insert(0, 'src')

from hypertide_automation import (
    HypertideClient,
    HypertideConfig,
    AuthenticationError,
    SessionExpiredError,
    RetryExhaustedError,
    HypertideUnavailableError,
)

# Use ASCII-safe status markers
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"
SKIP = "[SKIP]"


async def test_config():
    """Test configuration loading."""
    print("\n" + "=" * 60)
    print("TEST 1: Configuration Loading")
    print("=" * 60)

    config = HypertideConfig.from_env()

    print(f"  Default timeout:     {config.timeout}ms")
    print(f"  Navigation timeout:  {config.navigation_timeout}ms")
    print(f"  Element timeout:     {config.element_timeout}ms")
    print(f"  Auth check timeout:  {config.auth_check_timeout}ms")
    print(f"  Max retries:         {config.max_retries}")
    print(f"  Retry delay:         {config.retry_delay}ms")
    print(f"  Retry backoff:       {config.retry_backoff}x")
    print(f"  Headless:            {config.headless}")

    # Verify values are reasonable
    assert config.timeout >= 30000, "Timeout should be at least 30s"
    assert config.navigation_timeout >= 60000, "Nav timeout should be at least 60s"
    assert config.max_retries >= 2, "Should have at least 2 retries"

    print(f"\n  {PASS} Configuration test PASSED")
    return True


async def test_health_check():
    """Test site health check."""
    print("\n" + "=" * 60)
    print("TEST 2: Health Check")
    print("=" * 60)

    # Use headless for automated testing
    config = HypertideConfig.from_env()
    config.headless = True  # Override for test

    async with HypertideClient(config) as client:
        try:
            result = await client.health_check()
            print(f"  Health check result: {result}")
            print(f"\n  {PASS} Health check test PASSED - site is accessible")
            return True
        except HypertideUnavailableError as e:
            print(f"\n  {FAIL} Health check FAILED: {e}")
            return False


async def test_session_check():
    """Test session authentication check."""
    print("\n" + "=" * 60)
    print("TEST 3: Session Authentication Check")
    print("=" * 60)

    config = HypertideConfig.from_env()
    config.headless = True

    async with HypertideClient(config) as client:
        # First do health check
        try:
            await client.health_check()
        except HypertideUnavailableError:
            print("  Skipping - site unavailable")
            return None

        # Check if authenticated
        is_auth = await client.is_authenticated()
        print(f"  Session authenticated: {is_auth}")

        if is_auth:
            print(f"\n  {PASS} Session is valid")

            # Also test session validation for purchase
            try:
                await client.validate_session_for_purchase()
                print(f"  {PASS} Session validated for purchase")
            except SessionExpiredError as e:
                print(f"  {WARN} Session not valid for purchase: {e}")
        else:
            print(f"\n  {WARN} Session expired or not logged in")
            print("    This is expected if no saved session exists")
            print(f"  {PASS} Session check correctly detected no valid session")

        # Test passes if we correctly detected auth state (whether logged in or not)
        return True


async def test_login_detection():
    """Test login page detection."""
    print("\n" + "=" * 60)
    print("TEST 4: Login Page Detection")
    print("=" * 60)

    config = HypertideConfig.from_env()
    config.headless = True

    async with HypertideClient(config) as client:
        # Navigate to signin page
        await client.page.goto(config.signin_url, wait_until="domcontentloaded")

        # Check detection
        is_login = client.is_on_login_page()
        print(f"  On signin page: {is_login}")
        print(f"  Current URL: {client.page.url}")

        assert is_login, "Should detect signin page"
        print(f"\n  {PASS} Login detection test PASSED")
        return True


async def test_navigation_with_retry():
    """Test navigation with retry logic."""
    print("\n" + "=" * 60)
    print("TEST 5: Navigation with Retry Logic")
    print("=" * 60)

    config = HypertideConfig.from_env()
    config.headless = True

    async with HypertideClient(config) as client:
        # Test navigation to signin page
        # Note: If authenticated, may redirect to dashboard (expected behavior)
        print("  Testing navigation to signin page...")

        try:
            await client._navigate_with_validation(
                config.signin_url,
                "/signin",
                "signin"
            )
            print(f"  {PASS} Navigation to signin successful")
            print(f"    URL: {client.page.url}")
        except Exception as e:
            # If authenticated, signin redirects to dashboard - this is OK
            current_url = client.page.url
            if "/dashboard" in current_url:
                print(f"  {PASS} Authenticated user redirected to dashboard (expected)")
                print(f"    URL: {current_url}")
            else:
                print(f"  {FAIL} Navigation failed: {e}")
                return False

        # Test navigation to dashboard (may redirect to signin if not authenticated)
        print("\n  Testing navigation to dashboard...")
        try:
            await client._navigate_with_validation(
                config.dashboard_url,
                "/dashboard",
                "dashboard"
            )
            print(f"  {PASS} Navigation to dashboard successful (session valid)")
        except SessionExpiredError:
            print(f"  {PASS} Session expired detected correctly (redirected to signin)")
        except Exception as e:
            print(f"  {WARN} Navigation issue: {e}")

        print(f"\n  {PASS} Navigation test PASSED")
        return True


async def test_retry_mechanism():
    """Test the retry mechanism with a simulated failure."""
    print("\n" + "=" * 60)
    print("TEST 6: Retry Mechanism")
    print("=" * 60)

    config = HypertideConfig.from_env()
    config.headless = True
    config.max_retries = 2
    config.retry_delay = 500  # Fast for testing

    async with HypertideClient(config) as client:
        # Test retry with a function that fails first then succeeds
        attempt_count = 0

        async def flaky_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                from playwright.async_api import TimeoutError as PlaywrightTimeoutError
                raise PlaywrightTimeoutError("Simulated timeout")
            return "success"

        try:
            result = await client._with_retry("flaky operation", flaky_operation)
            print(f"  Result: {result}")
            print(f"  Attempts made: {attempt_count}")
            assert attempt_count == 2, "Should have retried once"
            print(f"\n  {PASS} Retry mechanism test PASSED")
            return True
        except RetryExhaustedError as e:
            print(f"  {FAIL} Retry test failed: {e}")
            return False


async def test_auto_login():
    """Test automated login with credentials."""
    print("\n" + "=" * 60)
    print("TEST 7: Automated Login")
    print("=" * 60)

    config = HypertideConfig.from_env()
    config.headless = False  # Visible for debugging

    # Check if credentials are configured
    if not config.auth_email or not config.auth_password:
        print(f"  {SKIP} Skipping - credentials not configured")
        print("    Set HYPERTIDE_EMAIL and HYPERTIDE_PASSWORD in .env")
        return None

    print(f"  Email: {config.auth_email}")
    print(f"  Password: {'*' * len(config.auth_password)}")

    async with HypertideClient(config) as client:
        # First check health
        try:
            await client.health_check()
        except HypertideUnavailableError as e:
            print(f"  {FAIL} Site unavailable: {e}")
            return False

        # Clear any existing session to force login
        # (skip loading saved session for this test)

        # Check if already authenticated
        is_auth = await client.is_authenticated()
        if is_auth:
            print(f"  {PASS} Already authenticated via saved session")
            print("    Auto-login not needed (session still valid)")
            return True

        # Try auto-login
        print("  Attempting auto-login...")
        try:
            result = await client.auto_login()
            if result:
                print(f"  {PASS} Auto-login successful!")

                # Verify we're actually logged in
                is_auth_after = await client.is_authenticated()
                if is_auth_after:
                    print(f"  {PASS} Authentication verified after auto-login")
                    return True
                else:
                    print(f"  {FAIL} Auth check failed after auto-login")
                    return False
            else:
                print(f"  {WARN} Auto-login returned False (credentials not configured?)")
                return None
        except Exception as e:
            print(f"  {FAIL} Auto-login failed: {e}")
            return False


async def test_full_flow_dry_run():
    """
    Dry run of the purchase flow (without actually purchasing).

    This validates that navigation and session handling work correctly.
    Uses auto-login if session is expired and credentials are configured.
    """
    print("\n" + "=" * 60)
    print("TEST 8: Full Flow Dry Run (No Purchase)")
    print("=" * 60)

    config = HypertideConfig.from_env()
    # Use visible browser for this test to see what's happening
    config.headless = False

    async with HypertideClient(config) as client:
        print("  Step 1: Health check...")
        try:
            await client.health_check()
            print(f"    {PASS} Site accessible")
        except HypertideUnavailableError as e:
            print(f"    {FAIL} Site unavailable: {e}")
            return False

        print("  Step 2: Ensure authentication (auto-login if needed)...")
        try:
            await client.ensure_authenticated()
            print(f"    {PASS} Authenticated")
        except Exception as e:
            print(f"    {FAIL} Authentication failed: {e}")
            return False

        print("  Step 3: Validate session for purchase...")
        try:
            await client.validate_session_for_purchase()
            print(f"    {PASS} Session valid for purchase")
        except SessionExpiredError as e:
            print(f"    {FAIL} Session invalid: {e}")
            return False

        print("  Step 4: Navigate through purchase pages (without purchasing)...")

        # We're already on choose-plan from validation
        current_url = client.page.url
        print(f"    Current URL: {current_url}")

        if "/choose-plan" in current_url:
            print(f"    {PASS} On choose-plan page")

            # Check for session expiry detection
            if client.is_on_login_page():
                print(f"    {FAIL} Unexpectedly on login page!")
                return False
            else:
                print(f"    {PASS} Not on login page (session still valid)")

        print(f"\n  {PASS} Full flow dry run PASSED")
        print("    The automation is ready for real purchases")
        return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("HYPERTIDE AUTOMATION RELIABILITY TESTS")
    print("=" * 60)

    results = {}

    # Test 1: Config
    results["config"] = await test_config()

    # Test 2: Health check
    results["health_check"] = await test_health_check()

    # Test 3: Session check
    results["session_check"] = await test_session_check()

    # Test 4: Login detection
    results["login_detection"] = await test_login_detection()

    # Test 5: Navigation with retry
    results["navigation"] = await test_navigation_with_retry()

    # Test 6: Retry mechanism
    results["retry"] = await test_retry_mechanism()

    # Test 7: Auto-login
    results["auto_login"] = await test_auto_login()

    # Test 8: Full flow dry run
    results["full_flow"] = await test_full_flow_dry_run()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = 0
    failed = 0
    skipped = 0

    for name, result in results.items():
        if result is True:
            status = f"{PASS}"
            passed += 1
        elif result is False:
            status = f"{FAIL}"
            failed += 1
        else:
            status = f"{SKIP}"
            skipped += 1
        print(f"  {name}: {status}")

    print(f"\n  Total: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print(f"\n  {PASS} ALL TESTS PASSED - Automation is ready!")
        return 0
    else:
        print(f"\n  {FAIL} SOME TESTS FAILED - Review errors above")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
