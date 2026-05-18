"""
Keep-alive probe for Streamlit Community Cloud.

When an app sleeps, Streamlit shows an interstitial page with a
"Yes, get this app back up!" button.  A plain HTTP request (curl /
requests / urllib) gets a 200 with a static HTML shell but never
boots the Python process.  A real browser is required to render the
page, find the button, and click it.

The button can appear on the main page OR inside an iframe, so both
are checked.
"""

import asyncio
import sys

from playwright.async_api import async_playwright

APP_URL = "https://sblnow.streamlit.app"
WAKE_BUTTON_TEXT = "Yes, get this app back up!"

# How long to wait for the initial page to render (ms)
PAGE_LOAD_WAIT_MS = 8_000
# How long to wait after clicking the wake button for the app to boot (ms)
POST_WAKE_WAIT_MS = 90_000
# Navigation timeout (ms) — sleeping apps can be slow to respond
NAV_TIMEOUT_MS = 120_000


async def find_wake_button(page):
    """Look for the wake-up button on the main page and inside all frames."""
    # Check main page
    btn = page.get_by_role("button", name=WAKE_BUTTON_TEXT)
    if await btn.count() > 0:
        return btn.first

    # Check inside iframes
    for frame in page.frames:
        try:
            btn = frame.get_by_role("button", name=WAKE_BUTTON_TEXT)
            if await btn.count() > 0:
                return btn.first
        except Exception:
            continue

    return None


async def keepalive():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        print(f"Navigating to {APP_URL} ...")
        try:
            await page.goto(APP_URL, wait_until="domcontentloaded",
                            timeout=NAV_TIMEOUT_MS)
        except Exception as exc:
            print(f"Navigation error (may still work): {exc}")

        # Give the page time to render the interstitial or the app
        print(f"Waiting {PAGE_LOAD_WAIT_MS / 1000:.0f}s for page to render ...")
        await page.wait_for_timeout(PAGE_LOAD_WAIT_MS)

        btn = await find_wake_button(page)

        if btn is not None:
            print("App is SLEEPING — clicking wake-up button ...")
            await btn.click()
            print(f"Waiting {POST_WAKE_WAIT_MS / 1000:.0f}s for app to boot ...")
            await page.wait_for_timeout(POST_WAKE_WAIT_MS)

            # Verify — check if the button is gone
            btn_after = await find_wake_button(page)
            if btn_after is None:
                print("SUCCESS — app is awake.")
            else:
                print("WARNING — wake button still present; app may not have started.")
                await browser.close()
                sys.exit(1)
        else:
            print("App is already AWAKE (no wake button found).")
            # Stay on the page briefly to register as traffic
            await page.wait_for_timeout(5_000)

        title = await page.title()
        print(f"Page title: {title}")
        await browser.close()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(keepalive())
