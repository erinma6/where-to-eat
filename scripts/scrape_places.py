#!/usr/bin/env python3
"""
Headless scraper for a public Google Maps shared list.
Returns a list of {"name": str} dicts.
"""

import time
from playwright.sync_api import sync_playwright

MAPS_URL = "https://maps.app.goo.gl/3e5T2mMKUMQvjDcY8"
ITEM_SELECTOR = "div.fontHeadlineSmall.rZF81c"


def scrape_saved_places() -> list[dict]:
    """
    Scrape all places from the public shared Google Maps list.
    Returns list of dicts with 'name'.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = context.new_page()

        print(f"Opening: {MAPS_URL}")
        page.goto(MAPS_URL, wait_until="domcontentloaded", timeout=60000)
        time.sleep(5)

        # Google injects a "Join to edit" interstitial on unauthenticated list views
        try:
            cancel = page.locator('button:has-text("Cancel")').first
            if cancel.is_visible(timeout=2000):
                cancel.click()
                time.sleep(1)
        except Exception:
            pass

        # Mouse-wheel events are required; programmatic scroll doesn't trigger Maps' virtual scroller
        print("Scrolling to load all items...")
        page.mouse.move(300, 400)
        prev_count = 0
        stale_rounds = 0

        while stale_rounds < 4:
            page.mouse.wheel(0, 600)
            time.sleep(0.6)

            current_count = page.evaluate(
                f"() => document.querySelectorAll('{ITEM_SELECTOR}').length"
            )
            if current_count == prev_count:
                stale_rounds += 1
            else:
                stale_rounds = 0
                prev_count = current_count
                print(f"  {current_count} items loaded...")

        names = page.evaluate(f"""
            () => Array.from(document.querySelectorAll('{ITEM_SELECTOR}'))
                       .map(el => el.innerText.trim())
                       .filter(t => t.length > 0)
        """)

        browser.close()

    print(f"Scraped {len(names)} places total")
    return [{"name": name} for name in names]


if __name__ == "__main__":
    places = scrape_saved_places()
    for i, p in enumerate(places, 1):
        print(f"  {i}. {p['name']}")
