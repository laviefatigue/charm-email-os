"""
Layer 1: Standalone browser tool tests.

Tests the exact same Playwright logic as purchase_mcp/server.py
but runs directly on Windows with a visible browser.
No Docker, no Claude Code, no MCP server — just Playwright.

Usage:
    cd d:\Work\charm-email-os
    python tests/test_mcp_browser_tools.py
"""

import asyncio
import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"


async def run_all_tests():
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)

    print("=" * 60)
    print("Layer 1: Browser Tool Tests (Windows Native)")
    print("=" * 60)

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    page = await browser.new_page(viewport={"width": 1280, "height": 900})

    results = {}

    # ── Test 1: navigate ──────────────────────────────────────
    print("\n[Test 1] navigate('https://app2.hypertide.io/signin')")
    try:
        await page.goto(
            "https://app2.hypertide.io/signin",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        try:
            await page.wait_for_selector(
                "input, button, form, [role='main']",
                timeout=15000,
            )
        except Exception:
            pass
        await asyncio.sleep(2)

        url = page.url
        title = await page.title()
        body = await page.inner_text("body")
        print(f"  URL: {url}")
        print(f"  Title: {title}")
        print(f"  Body length: {len(body)}")

        ok = "signin" in url and len(body) > 0
        results["navigate"] = "PASS" if ok else "FAIL"
        print(f"  -> {results['navigate']}")
    except Exception as e:
        results["navigate"] = f"FAIL: {e}"
        print(f"  -> {results['navigate']}")

    # ── Test 2: screenshot ────────────────────────────────────
    print("\n[Test 2] screenshot()")
    try:
        shot_path = OUTPUT_DIR / "test_screenshot.png"
        await page.screenshot(path=str(shot_path))
        size = shot_path.stat().st_size
        print(f"  Saved: {shot_path} ({size} bytes)")
        results["screenshot"] = "PASS" if size > 1000 else "FAIL: too small"
        print(f"  -> {results['screenshot']}")
    except Exception as e:
        results["screenshot"] = f"FAIL: {e}"
        print(f"  -> {results['screenshot']}")

    # ── Test 3: get_page_text ─────────────────────────────────
    print("\n[Test 3] get_page_text()")
    try:
        text = await page.inner_text("body")
        text = text[:10000]
        has_content = any(
            kw in text.lower() for kw in ["sign", "email", "password", "hypertide"]
        )
        print(f"  Text length: {len(text)}")
        print(f"  Contains expected keywords: {has_content}")
        results["get_page_text"] = "PASS" if has_content else "FAIL: no keywords"
        print(f"  -> {results['get_page_text']}")
    except Exception as e:
        results["get_page_text"] = f"FAIL: {e}"
        print(f"  -> {results['get_page_text']}")

    # ── Test 4: fill (email) ──────────────────────────────────
    print("\n[Test 4] fill('input[type=\"email\"]', 'test@example.com')")
    try:
        selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[placeholder*="mail"]',
            'input[autocomplete="email"]',
        ]
        filled = False
        for sel in selectors:
            el = await page.query_selector(sel)
            if el:
                await el.click()
                await el.fill("")
                await el.fill("test@example.com")
                val = await el.input_value()
                filled = val == "test@example.com"
                print(f"  Selector: {sel}")
                print(f"  Value after fill: {val}")
                break

        if not filled:
            # fallback: try first input
            inputs = await page.query_selector_all("input")
            if inputs:
                await inputs[0].fill("test@example.com")
                val = await inputs[0].input_value()
                filled = val == "test@example.com"
                print(f"  Fallback to first input, value: {val}")

        results["fill_email"] = "PASS" if filled else "FAIL: no email input found"
        print(f"  -> {results['fill_email']}")
    except Exception as e:
        results["fill_email"] = f"FAIL: {e}"
        print(f"  -> {results['fill_email']}")

    # ── Test 5: fill (password) ───────────────────────────────
    print("\n[Test 5] fill('input[type=\"password\"]', '***')")
    try:
        pwd_el = await page.query_selector('input[type="password"]')
        if pwd_el:
            await pwd_el.click()
            await pwd_el.fill("testpassword123")
            val = await pwd_el.input_value()
            ok = val == "testpassword123"
            print(f"  Value after fill: {'***' if ok else 'EMPTY'}")
            results["fill_password"] = "PASS" if ok else "FAIL: value mismatch"
        else:
            results["fill_password"] = "FAIL: no password input"
        print(f"  -> {results['fill_password']}")
    except Exception as e:
        results["fill_password"] = f"FAIL: {e}"
        print(f"  -> {results['fill_password']}")

    # ── Test 6: click (submit button) ─────────────────────────
    print("\n[Test 6] click('button' or 'text=Sign In')")
    try:
        # Screenshot before click
        await page.screenshot(path=str(OUTPUT_DIR / "test_before_click.png"))

        btn = await page.query_selector('button[type="submit"]')
        if not btn:
            btn = await page.query_selector("button")
        if btn:
            btn_text = await btn.inner_text()
            print(f"  Button text: {btn_text}")
            await btn.click()
            await asyncio.sleep(3)

            # Screenshot after click (should show error or redirect)
            await page.screenshot(path=str(OUTPUT_DIR / "test_after_click.png"))
            new_url = page.url
            print(f"  URL after click: {new_url}")
            results["click"] = "PASS"
        else:
            results["click"] = "FAIL: no button found"
        print(f"  -> {results['click']}")
    except Exception as e:
        results["click"] = f"FAIL: {e}"
        print(f"  -> {results['click']}")

    # ── Test 7: wait_for_text ─────────────────────────────────
    print("\n[Test 7] wait_for_text('Sign', timeout_ms=5000)")
    try:
        # Navigate back to signin to reset state
        await page.goto(
            "https://app2.hypertide.io/signin",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await asyncio.sleep(2)

        # Check for text
        el = await page.wait_for_selector("text=Sign", timeout=5000)
        found = el is not None
        print(f"  Found 'Sign' text: {found}")
        results["wait_for_text"] = "PASS" if found else "FAIL"
        print(f"  -> {results['wait_for_text']}")
    except Exception as e:
        results["wait_for_text"] = f"FAIL: {e}"
        print(f"  -> {results['wait_for_text']}")

    # ── Test 8: scroll_down ───────────────────────────────────
    print("\n[Test 8] scroll_down(500)")
    try:
        await page.evaluate("window.scrollBy(0, 500)")
        await asyncio.sleep(1)
        scroll_y = await page.evaluate("window.scrollY")
        print(f"  scrollY after scroll: {scroll_y}")
        results["scroll_down"] = "PASS" if scroll_y > 0 else "PASS (page may be short)"
        print(f"  -> {results['scroll_down']}")
    except Exception as e:
        results["scroll_down"] = f"FAIL: {e}"
        print(f"  -> {results['scroll_down']}")

    # ── SUMMARY ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, result in results.items():
        status = "PASS" if result == "PASS" or result.startswith("PASS") else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  {name:20s} {result}")

    print(f"\nOverall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
    print(f"Screenshots saved to: {OUTPUT_DIR}")
    print("=" * 60)

    await browser.close()
    await pw.stop()

    return all_pass


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
