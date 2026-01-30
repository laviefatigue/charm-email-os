"""
Automated Hypertide session establishment with credentials.
"""
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from playwright.async_api import async_playwright
from hypertide_automation.config import HypertideConfig

# Credentials - hardcoded for this session
EMAIL = "chris@hirecharm.com"
PASSWORD = "l$97t73M"

async def establish_session_auto():
    print("=" * 60)
    print("HYPERTIDE AUTOMATED SESSION ESTABLISHMENT")
    print("=" * 60)

    config = HypertideConfig(headless=False, slow_mo=100)

    print(f"Email: {EMAIL}")
    print(f"Session path: {config.session_storage_path}")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=100)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            print("Navigating to signin page...")
            await page.goto("https://app2.hypertide.io/signin", wait_until="networkidle")
            await asyncio.sleep(3)

            # Take initial screenshot
            await page.screenshot(path="signin_before.png")
            print("Initial page screenshot saved")

            # Find and fill email field
            print("Looking for email input...")
            email_input = page.locator('input[placeholder="youremail@server.com"]')
            if await email_input.count() == 0:
                email_input = page.locator('input[type="email"]')
            if await email_input.count() == 0:
                email_input = page.locator('input').first

            print(f"Found {await email_input.count()} email input(s)")
            await email_input.first.click()
            await email_input.first.fill("")  # Clear first
            await asyncio.sleep(0.5)
            await email_input.first.type(EMAIL, delay=50)  # Type slowly
            await asyncio.sleep(1)

            # Find and fill password field
            print("Looking for password input...")
            password_input = page.locator('input[type="password"]')
            print(f"Found {await password_input.count()} password input(s)")
            await password_input.first.click()
            await password_input.first.fill("")  # Clear first
            await asyncio.sleep(0.5)
            await password_input.first.type(PASSWORD, delay=50)  # Type slowly
            await asyncio.sleep(1)

            # Screenshot after filling
            await page.screenshot(path="signin_filled.png")
            print("Filled form screenshot saved")

            # Click the Sign In button
            print("Looking for Sign In button...")
            sign_in_button = page.locator('button:has-text("Sign In")')
            print(f"Found {await sign_in_button.count()} Sign In button(s)")
            await sign_in_button.first.click()

            print("Clicked Sign In, waiting for navigation...")
            await asyncio.sleep(3)

            # Take screenshot after click
            await page.screenshot(path="signin_after_click.png")
            print("Post-click screenshot saved")

            # Check current URL
            current_url = page.url
            print(f"Current URL: {current_url}")

            # Wait for redirect to dashboard
            print("Waiting for dashboard redirect (5 min timeout)...")
            try:
                await page.wait_for_url("**/dashboard**", timeout=300000)
                print("Login successful - reached dashboard!")
            except:
                # Maybe we're on a different success page
                current_url = page.url
                print(f"Final URL: {current_url}")
                await page.screenshot(path="final_page.png")

                if "dashboard" in current_url or "home" in current_url:
                    print("Appears to be logged in!")
                else:
                    raise Exception(f"Login failed - ended up at: {current_url}")

            # Save session
            storage_path = config.session_storage_path
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(storage_path))

            print()
            print("=" * 60)
            print("SESSION ESTABLISHED SUCCESSFULLY!")
            print(f"Saved to: {storage_path}")
            print()
            print("Copy to server with:")
            print(f"  scp {storage_path} root@31.97.142.123:/root/.hypertide/session")
            print("=" * 60)

        except Exception as e:
            print(f"Error: {e}")
            # Take screenshot on error
            await page.screenshot(path="error_page.png")
            print("Error screenshot saved to error_page.png")
            print(f"Final URL was: {page.url}")
            raise
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(establish_session_auto())
