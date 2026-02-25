"""
Local test script to verify Hypertide login page renders with our Playwright config.
Exercises the exact same logic as purchase_mcp/server.py navigate handler.
"""
import asyncio
import base64
import time
from pathlib import Path

async def test_hypertide_signin():
    from playwright.async_api import async_playwright

    print("--- Starting Playwright ---")
    pw = await async_playwright().start()

    # Match the MCP server config exactly (except headless=False is fine on Windows with a real display)
    browser = await pw.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ]
    )
    page = await browser.new_page(viewport={"width": 1280, "height": 900})

    url = "https://app2.hypertide.io/signin"
    print(f"\n--- Navigating to {url} ---")
    t0 = time.time()

    # This is the EXACT logic from purchase_mcp/server.py navigate handler
    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    t1 = time.time()
    print(f"  domcontentloaded fired in {t1 - t0:.2f}s")

    # Wait for meaningful content (form elements, buttons, etc.)
    try:
        await page.wait_for_selector(
            "input, button, form, [role='main']",
            timeout=15000
        )
        t2 = time.time()
        print(f"  Form elements found in {t2 - t0:.2f}s")
    except Exception as e:
        t2 = time.time()
        print(f"  WARNING: No form elements found after {t2 - t0:.2f}s: {e}")

    # Brief pause for React hydration (same as MCP server)
    await asyncio.sleep(2)

    # Take screenshot
    screenshot_bytes = await page.screenshot(full_page=False)
    screenshot_path = Path("D:/Work/charm-email-os/test_screenshot_signin.png")
    screenshot_path.write_bytes(screenshot_bytes)
    print(f"\n--- Screenshot saved to {screenshot_path} ---")

    # Get page info
    title = await page.title()
    current_url = page.url
    print(f"  URL: {current_url}")
    print(f"  Title: {title}")

    # Get body text length (the metric that was failing in Docker)
    body_text = await page.inner_text("body")
    print(f"  Body text length: {len(body_text)}")
    print(f"  Body text preview: {body_text[:500]}")

    # Check for specific elements
    print("\n--- Element checks ---")
    for selector, desc in [
        ("input[type='email']", "Email input"),
        ("input[type='password']", "Password input"),
        ("button", "Any button"),
        ("text=Sign In", "Sign In text"),
    ]:
        try:
            if selector.startswith("text="):
                el = page.get_by_text(selector[5:], exact=False).first
                count = await el.count()
            else:
                count = await page.locator(selector).count()
            print(f"  {desc}: {'FOUND' if count > 0 else 'NOT FOUND'} ({count})")
        except Exception as e:
            print(f"  {desc}: ERROR - {e}")

    print("\n--- Test complete ---")
    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(test_hypertide_signin())
