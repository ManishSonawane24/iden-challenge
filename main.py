import json
import os
import logging
import time
from typing import List, Dict
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

URL = "https://hiring.idenhq.com/"
SESSION_FILE = "session.json"
OUTPUT_FILE = "products.json"

EMAIL = "manishsonawane2424@gmail.com"
PASSWORD = "HdOBPoJA"

# Constants for retry attempts
MAX_RETRIES = 3
RETRY_DELAY = 2
PAGE_LOAD_TIMEOUT = 30000
DYNAMIC_LOAD_TIMEOUT = 5000

def save_session(context):
    """Save browser session state to file."""
    try:
        # Ensure the context is still valid
        if not context:
            raise Exception("Invalid context")
            
        # Save the session state
        context.storage_state(path=SESSION_FILE)
        logger.info("Session state saved successfully")
    except Exception as e:
        logger.error(f"Failed to save session state: {e}")
        # Remove invalid session file if it exists
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        raise

def load_session(playwright):
    """Load browser session state from file."""
    try:
        if not os.path.exists(SESSION_FILE):
            raise Exception("Session file not found")
            
        # Launch browser with specific arguments
        browser = playwright.chromium.launch(
            headless=False,
            args=['--disable-web-security', '--disable-features=IsolateOrigins,site-per-process']
        )
        
        # Create context with specific permissions
        context = browser.new_context(
            storage_state=SESSION_FILE,
            permissions=['geolocation'],
            viewport={'width': 1920, 'height': 1080}
        )
        
        logger.info("Session state loaded successfully")
        return context
    except Exception as e:
        logger.error(f"Failed to load session state: {e}")
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        raise

def wait_for_element(page, selector: str, timeout: int = PAGE_LOAD_TIMEOUT):
    """Wait for element to be visible and ready."""
    try:
        element = page.wait_for_selector(selector, timeout=timeout)
        if element:
            # Additional wait for element to be fully loaded
            page.wait_for_timeout(DYNAMIC_LOAD_TIMEOUT)
            return element
    except PlaywrightTimeoutError:
        logger.error(f"Element not found: {selector}")
        raise
    return None

def wait_and_click(page, selector: str, timeout: int = PAGE_LOAD_TIMEOUT):
    """Wait for element and click with retry mechanism."""
    for attempt in range(MAX_RETRIES):
        try:
            element = wait_for_element(page, selector, timeout)
            if element:
                # Ensure element is clickable
                element.wait_for_element_state("visible")
                element.click()
                # Wait for any navigation or state changes
                page.wait_for_timeout(DYNAMIC_LOAD_TIMEOUT)
                return True
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            logger.warning(f"Click attempt {attempt + 1} failed: {e}, retrying...")
            time.sleep(RETRY_DELAY)
    return False

def login(page):
    """Handle login process with retry mechanism and access verification."""
    try:
        # Clear any existing cookies
        page.context.clear_cookies()
        
        # Navigate to login page with retry
        for attempt in range(MAX_RETRIES):
            try:
                page.goto("https://hiring.idenhq.com/", timeout=PAGE_LOAD_TIMEOUT)
                break
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                logger.warning(f"Navigation attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(RETRY_DELAY)
        
        # Wait for login form with retry
        for attempt in range(MAX_RETRIES):
            try:
                wait_for_element(page, 'input#email', timeout=PAGE_LOAD_TIMEOUT)
                break
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                logger.warning(f"Login form wait attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(RETRY_DELAY)
        
        # Fill login form with retry mechanism
        for attempt in range(MAX_RETRIES):
            try:
                # Clear any existing input
                page.get_by_placeholder("name@example.com").fill("")
                page.fill('input[type="password"]', "")
                
                # Fill credentials
                page.get_by_placeholder("name@example.com").fill(EMAIL)
                page.fill('input[type="password"]', PASSWORD)
                
                # Click submit and wait for navigation
                page.click('button[type="submit"]')
                
                # Wait for successful login with timeout
                try:
                    wait_for_element(page, "text=Launch Challenge", timeout=PAGE_LOAD_TIMEOUT)
                except PlaywrightTimeoutError:
                    # Check for error messages
                    error_text = page.query_selector("text=Access denied")
                    if error_text:
                        logger.error("Access denied error detected")
                        raise Exception("Access denied: Authentication failed")
                    
                    # Check for other error messages
                    error_messages = page.query_selector_all("[role='alert']")
                    for error in error_messages:
                        logger.error(f"Login error: {error.inner_text()}")
                    
                    raise Exception("Login failed: Could not find Launch Challenge button")
                
                # Click Launch Challenge
                wait_and_click(page, "text=Launch Challenge")
                
                # Verify we're on the challenge page
                page.wait_for_url("**/challenge", timeout=PAGE_LOAD_TIMEOUT)
                
                # Additional verification of successful login
                try:
                    # Wait for any admin-specific elements or verify access
                    page.wait_for_selector("text=Dashboard", timeout=5000)
                except PlaywrightTimeoutError:
                    logger.error("Could not verify admin access after login")
                    raise Exception("Login verification failed: Admin access not confirmed")
                
                # Save session after successful login
                context = page.context
                save_session(context)
                logger.info("Login successful and session saved")
                return
                
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                logger.warning(f"Login attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(RETRY_DELAY)
                
    except Exception as e:
        logger.error(f"Login failed after {MAX_RETRIES} attempts: {e}")
        raise

def navigate_to_full_catalog(page):
    """Navigate to full catalog with improved navigation handling."""
    try:
        # Wait for the page to be fully loaded
        page.wait_for_load_state("networkidle")
        
        # Click Dashboard with explicit wait and correct selector
        logger.info("Attempting to click Dashboard...")
        dashboard_button = page.wait_for_selector('button:has-text("Dashboard")', timeout=PAGE_LOAD_TIMEOUT)
        if not dashboard_button:
            raise Exception("Dashboard button not found")
        dashboard_button.click()
        page.wait_for_load_state("networkidle")
        
        # Click Inventory with correct selector
        logger.info("Attempting to click Inventory...")
        inventory_element = page.wait_for_selector('h3.font-medium:has-text("Inventory")', timeout=PAGE_LOAD_TIMEOUT)
        if not inventory_element:
            raise Exception("Inventory element not found")
        inventory_element.click()
        page.wait_for_load_state("networkidle")
        
        # Click Products with correct selector
        logger.info("Attempting to click Products...")
        products_element = page.wait_for_selector('h3.font-medium:has-text("Products")', timeout=PAGE_LOAD_TIMEOUT)
        if not products_element:
            raise Exception("Products element not found")
        products_element.click()
        page.wait_for_load_state("networkidle")
        
        # Click Full Catalog with correct selector
        logger.info("Attempting to click Full Catalog...")
        full_catalog_button = page.wait_for_selector('h3:has-text("Full Catalog")', timeout=PAGE_LOAD_TIMEOUT)
        if not full_catalog_button:
            raise Exception("Full Catalog button not found")
        full_catalog_button.click()
        
        # Wait for table to be visible and fully loaded
        wait_for_element(page, "table", timeout=PAGE_LOAD_TIMEOUT)
        logger.info("Successfully navigated to full catalog")
    except Exception as e:
        logger.error(f"Failed to navigate to full catalog: {e}")
        raise

def extract_table_headers(page) -> List[str]:
    """Extract table headers for structured data."""
    headers = page.query_selector_all("table thead th")
    return [header.inner_text().strip() for header in headers]

def wait_for_table_update(page):
    """Wait for table to update after pagination."""
    try:
        # Wait for any loading indicators to disappear
        page.wait_for_selector("div[role='progressbar']", state="hidden", timeout=DYNAMIC_LOAD_TIMEOUT)
    except:
        pass
    # Additional wait for table to stabilize
    page.wait_for_timeout(DYNAMIC_LOAD_TIMEOUT)

def get_total_products(page) -> int:
    """Extract total number of products from the page."""
    try:
        # Wait for the product count text to be visible with a more specific selector
        count_text = page.wait_for_selector('div.text-sm.text-muted-foreground:has-text("Showing")', timeout=PAGE_LOAD_TIMEOUT)
        if not count_text:
            raise Exception("Product count text not found")
            
        text = count_text.inner_text()
        logger.info(f"Found product count text: {text}")
        
        # More robust text parsing
        try:
            # First try to find the number after "of"
            if "of" in text:
                parts = text.split("of")
                if len(parts) >= 2:
                    number_text = parts[1].strip().split()[0]
                    total_products = int(number_text)
                    logger.info(f"Total products to collect: {total_products}")
                    return total_products
                    
            # If that fails, try to find any number in the text
            import re
            numbers = re.findall(r'\d+', text)
            if numbers:
                total_products = int(numbers[-1])  # Take the last number found
                logger.info(f"Total products to collect (from regex): {total_products}")
                return total_products
                
            raise Exception(f"Could not parse product count from text: {text}")
            
        except ValueError as ve:
            raise Exception(f"Failed to convert product count to number: {ve}")
            
    except Exception as e:
        logger.error(f"Failed to get total products: {e}")
        # If we can't get the total, return a default value to continue scraping
        logger.warning("Using default total of 100 products")
        return 100

def scroll_table_to_bottom(page):
    """Scroll the table to the bottom to ensure all content is loaded."""
    try:
        # Find the table container
        table_container = page.wait_for_selector('div[role="grid"]', timeout=PAGE_LOAD_TIMEOUT)
        if not table_container:
            raise Exception("Table container not found")
            
        # Get initial scroll position
        last_height = page.evaluate("document.querySelector('div[role=\"grid\"]').scrollHeight")
        scroll_attempts = 0
        max_scroll_attempts = 50
        
        while scroll_attempts < max_scroll_attempts:
            # Scroll to bottom of table
            page.evaluate("document.querySelector('div[role=\"grid\"]').scrollTo(0, document.querySelector('div[role=\"grid\"]').scrollHeight)")
            page.wait_for_timeout(1000)  # Wait for content to load
            
            # Get new scroll height
            new_height = page.evaluate("document.querySelector('div[role=\"grid\"]').scrollHeight")
            
            # Break if no more content is loading
            if new_height == last_height:
                scroll_attempts += 1
                if scroll_attempts >= 3:  # If no change after 3 attempts, break
                    break
            else:
                scroll_attempts = 0
                last_height = new_height
                
            logger.info(f"Scrolling table... (attempt {scroll_attempts + 1})")
            
    except Exception as e:
        logger.error(f"Error while scrolling table: {e}")

def scrape_products(page) -> List[Dict]:
    """Scrape products with improved pagination, dynamic loading, and scroll-based collection."""
    all_data = []
    headers = extract_table_headers(page)
    page_number = 1
    retry_count = 0
    max_retries = 3
    processed_rows = set()  # Track processed rows to avoid duplicates
    
    try:
        # Get total number of products to collect
        total_products = get_total_products(page)
        
        while len(all_data) < total_products:
            logger.info(f"Processing page {page_number}...")
            
            # Wait for table to be fully loaded with retry mechanism
            for attempt in range(max_retries):
                try:
                    # Wait for table rows to be visible and fully loaded
                    wait_for_element(page, "table tbody tr")
                    
                    # Scroll table to ensure all content is loaded
                    scroll_table_to_bottom(page)
                    
                    # Additional wait for any dynamic content
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(1000)  # Small delay to ensure content is stable
                    
                    # Get all rows in current page
                    rows = page.query_selector_all("table tbody tr")
                    if not rows:
                        raise Exception("No rows found in table")
                    
                    # Process rows
                    for row in rows:
                        # Generate unique identifier for row
                        row_id = row.get_attribute("data-row-id") or row.inner_text()
                        if row_id in processed_rows:
                            continue
                            
                        cells = row.query_selector_all("td")
                        if len(cells) != len(headers):
                            logger.warning(f"Row has {len(cells)} cells, expected {len(headers)}")
                            continue
                            
                        row_data = [cell.inner_text().strip() for cell in cells]
                        
                        # Validate row data
                        if all(row_data):  # Check if all cells have content
                            product_data = dict(zip(headers, row_data))
                            all_data.append(product_data)
                            processed_rows.add(row_id)
                    
                    logger.info(f"Scraped {len(all_data)} of {total_products} products...")
                    retry_count = 0  # Reset retry count on success
                    break
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(f"Failed to process page {page_number} after {max_retries} attempts")
                        raise
                    logger.warning(f"Attempt {retry_count} failed: {e}, retrying...")
                    page.wait_for_timeout(2000)  # Wait before retry
            
            # Check for next page with improved detection
            try:
                # Wait for the next button to be visible
                next_button = page.wait_for_selector('button:has-text("Next")', timeout=5000)
                if next_button:
                    # Check if the button is disabled
                    is_disabled = next_button.get_attribute("disabled") is not None
                    if not is_disabled:
                        logger.info("Clicking Next button...")
                        next_button.click()
                        wait_for_table_update(page)
                        page_number += 1
                        continue
                    else:
                        logger.info("Next button is disabled")
                else:
                    logger.info("Next button not found")
            except Exception as e:
                logger.error(f"Error checking next button: {e}")
            
            # If we get here, either there's no next button or it's disabled
            logger.info("Reached last page or no more pages available")
            break
                
        logger.info(f"Successfully scraped {len(all_data)} products from {page_number} pages")
        return all_data
    except Exception as e:
        logger.error(f"Error during product scraping: {e}")
        raise

def main():
    """Main execution function with improved error handling."""
    browser = None
    context = None
    try:
        with sync_playwright() as p:
            # First, try to load existing session
            if os.path.exists(SESSION_FILE):
                try:
                    context = load_session(p)
                    logger.info("Successfully loaded existing session")
                    
                    # Verify session is still valid
                    page = context.new_page()
                    try:
                        page.goto(URL, timeout=PAGE_LOAD_TIMEOUT)
                        # Check if we're still logged in
                        if page.query_selector("text=Launch Challenge"):
                            logger.info("Session is still valid")
                        else:
                            raise Exception("Session is invalid")
                    except Exception as e:
                        logger.warning(f"Session validation failed: {e}")
                        if context:
                            context.close()
                        context = None
                        if os.path.exists(SESSION_FILE):
                            os.remove(SESSION_FILE)
                except Exception as e:
                    logger.warning(f"Failed to load session: {e}")
                    if os.path.exists(SESSION_FILE):
                        os.remove(SESSION_FILE)
                    context = None

            # If no valid session, create new one
            if not context:
                browser = p.chromium.launch(
                    headless=False,
                    args=['--disable-web-security', '--disable-features=IsolateOrigins,site-per-process']
                )
                context = browser.new_context(
                    permissions=['geolocation'],
                    viewport={'width': 1920, 'height': 1080}
                )
                page = context.new_page()
                login(page)
            else:
                page = context.new_page()
                page.goto(URL)

            # Navigate and scrape
            navigate_to_full_catalog(page)
            data = scrape_products(page)

            # Save data with proper formatting
            with open(OUTPUT_FILE, "w", encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            logger.info(f"✅ Done! Saved {len(data)} products to {OUTPUT_FILE}")
            
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise
    finally:
        # Cleanup resources
        if context:
            try:
                context.close()
            except Exception as e:
                logger.error(f"Error closing context: {e}")
        if browser:
            try:
                browser.close()
            except Exception as e:
                logger.error(f"Error closing browser: {e}")

if __name__ == "__main__":
    main()
