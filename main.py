import json
import os
import logging
import time
from typing import List, Dict
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from dotenv import load_dotenv

# ─── Load credentials from .env ──────────────────────────────────────────────
load_dotenv()
EMAIL    = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
if not EMAIL or not PASSWORD:
    raise ValueError("Please set both EMAIL and PASSWORD in your .env file")

# ─── Logging setup ───────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Constants ──────────────────────────────────────────────────────────────
URL                  = "https://hiring.idenhq.com/"
SESSION_FILE         = "session.json"
OUTPUT_FILE          = "products.json"

MAX_RETRIES          = 3
RETRY_DELAY          = 2            # seconds
PAGE_LOAD_TIMEOUT    = 30_000       # ms
DYNAMIC_LOAD_TIMEOUT = 5_000        # ms

# ─── Session Persistence ────────────────────────────────────────────────────
def save_session(context):
    try:
        context.storage_state(path=SESSION_FILE)
        logger.info("Session state saved to %s", SESSION_FILE)
    except Exception as e:
        logger.error("Failed to save session state: %s", e)
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        raise

def load_session(playwright):
    if not os.path.exists(SESSION_FILE):
        raise FileNotFoundError("Session file not found")
    browser = playwright.chromium.launch(
        headless=False,
        args=["--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"]
    )
    context = browser.new_context(
        storage_state=SESSION_FILE,
        permissions=["geolocation"],
        viewport={"width": 1280, "height": 1080}
    )
    logger.info("Loaded existing session from %s", SESSION_FILE)
    return context

# ─── Helpers ────────────────────────────────────────────────────────────────
def wait_for_element(page, selector: str, timeout: int = PAGE_LOAD_TIMEOUT):
    el = page.wait_for_selector(selector, timeout=timeout)
    page.wait_for_timeout(DYNAMIC_LOAD_TIMEOUT)
    return el

def wait_and_click(page, selector: str, timeout: int = PAGE_LOAD_TIMEOUT):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            el = wait_for_element(page, selector, timeout)
            el.wait_for_element_state("visible")
            el.click()
            page.wait_for_timeout(DYNAMIC_LOAD_TIMEOUT)
            return
        except Exception as e:
            logger.warning("Click #%d failed (%s): %s", attempt, selector, e)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(RETRY_DELAY)

# ─── Login Flow ─────────────────────────────────────────────────────────────
def login(page):
    logger.info("Logging in with %s", EMAIL)
    page.context.clear_cookies()

    # Navigate to login page
    for i in range(MAX_RETRIES):
        try:
            page.goto(URL, timeout=PAGE_LOAD_TIMEOUT)
            break
        except Exception as e:
            logger.warning("Nav attempt #%d failed: %s", i+1, e)
            time.sleep(RETRY_DELAY)

    # Wait for form
    wait_for_element(page, 'input#email')
    wait_for_element(page, 'input[type="password"]')

    # Fill & submit
    page.fill('input#email', EMAIL)
    page.fill('input[type="password"]', PASSWORD)
    page.click('button[type="submit"]')

    # Wait for post-login button
    wait_for_element(page, 'text=Launch Challenge', timeout=PAGE_LOAD_TIMEOUT)
    wait_and_click(page, 'text=Launch Challenge')
    page.wait_for_url("**/challenge", timeout=PAGE_LOAD_TIMEOUT)
    page.wait_for_selector("text=Dashboard", timeout=5_000)

    save_session(page.context)
    logger.info("Login successful and session saved")

# ─── Navigation & Scraping ─────────────────────────────────────────────────
def navigate_to_full_catalog(page):
    page.wait_for_load_state("networkidle")
    wait_and_click(page, 'button:has-text("Dashboard")')
    page.wait_for_load_state("networkidle")
    wait_and_click(page, 'h3.font-medium:has-text("Inventory")')
    page.wait_for_load_state("networkidle")
    wait_and_click(page, 'h3.font-medium:has-text("Products")')
    wait_and_click(page, 'h3:has-text("Full Catalog")')
    wait_for_element(page, "table")
    logger.info("Reached Full Catalog")

def extract_table_headers(page) -> List[str]:
    return [th.inner_text().strip() for th in page.query_selector_all("table thead th")]

def get_total_products(page) -> int:
    txt = page.query_selector(
        'div.text-sm.text-muted-foreground:has-text("Showing")'
    ).inner_text()
    return int(txt.split("of")[-1].split()[0])

def scroll_table_to_bottom(page):
    """
    Attempts to scroll either the grid container, the table, or the page itself
    until no new scrollHeight appears for 3 consecutive tries.
    """
    # Define the JS element expressions
    candidates = [
        ("div[role=\"grid\"]",    "document.querySelector('div[role=\"grid\"]')"),
        ("table",                  "document.querySelector('table')"),
        ("scrollingElement",       "document.scrollingElement")
    ]

    for name, js_el in candidates:
        # Check existence
        exists = page.evaluate(f"() => !!{js_el}")
        if not exists:
            continue

        # Now scroll that element
        last = page.evaluate(f"() => {js_el}.scrollHeight")
        stable = 0
        while stable < 3:
            page.evaluate(f"() => {js_el}.scrollTo(0, {js_el}.scrollHeight)")
            time.sleep(0.5)
            now = page.evaluate(f"() => {js_el}.scrollHeight")
            if now == last:
                stable += 1
            else:
                last = now
                stable = 0
        return  # done with first-found scrollable container

def scrape_products(page) -> List[Dict]:
    headers = extract_table_headers(page)
    total   = get_total_products(page)
    logger.info("Expect ~%d products", total)

    data, seen, page_num = [], set(), 1
    while len(data) < total:
        logger.info("Scraping page %d", page_num)
        wait_for_element(page, "table tbody tr")
        scroll_table_to_bottom(page)
        rows = page.query_selector_all("table tbody tr")
        for row in rows:
            key = row.get_attribute("data-row-id") or row.inner_text()
            if key in seen:
                continue
            seen.add(key)
            cells = row.query_selector_all("td")
            if len(cells) != len(headers):
                continue
            data.append({headers[i]: cells[i].inner_text().strip() for i in range(len(headers))})

        # Next page?
        nxt = page.query_selector('button:has-text("Next")')
        if nxt and not nxt.get_attribute("disabled"):
            nxt.click()
            page.wait_for_timeout(DYNAMIC_LOAD_TIMEOUT)
            page_num += 1
            continue
        break

    logger.info("Scraped %d products total", len(data))
    return data

# ─── Main ───────────────────────────────────────────────────────────────────
def main():
    browser = None
    context = None
    with sync_playwright() as p:
        # Try reusing session
        if os.path.exists(SESSION_FILE):
            try:
                context = load_session(p)
                page = context.new_page()
                page.goto(URL, timeout=PAGE_LOAD_TIMEOUT)
                if not page.is_visible("text=Launch Challenge"):
                    raise Exception("stale session")
                logger.info("Reused existing session")
            except Exception as e:
                logger.warning("Session reuse failed: %s", e)
                os.remove(SESSION_FILE)
                context = None

        # Fresh login if needed
        if not context:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"]
            )
            context = browser.new_context(
                permissions=["geolocation"],
                viewport={"width": 1280, "height": 1080}
            )
            page = context.new_page()
            login(page)
        else:
            page = context.new_page()

        # Scrape
        navigate_to_full_catalog(page)
        products = scrape_products(page)

        # Save output
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(products, f, indent=4, ensure_ascii=False)
        logger.info("✅ Done! Saved %d products to %s", len(products), OUTPUT_FILE)

        # Cleanup
        if context:
            context.close()
        if browser:
            browser.close()

if __name__ == "__main__":
    main()
