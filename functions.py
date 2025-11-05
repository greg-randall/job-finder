"""
This module provides a set of asynchronous functions to support web scraping tasks,
including browser initialization, page navigation, content extraction, and interaction
with the OpenAI API.
"""

import asyncio
import hashlib
import os
import secrets
import traceback
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, List, Set, Dict, Any
from urllib.parse import urljoin, urlparse

import aiofiles
import openai
import trafilatura
import undetected_chromedriver as uc
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from logging_config import ScraperLogger, setup_simple_logger

# Load environment variables
load_dotenv()

# Import config loader - load config at module import time
try:
    from config_loader import get_config
    _config = get_config()
    _use_config = True
except Exception:
    # Fallback if config not available
    _config = None
    _use_config = False


# ============================================================================
# CONSTANTS (Loaded from config.yaml when available)
# ============================================================================

class Timeouts:
    """Centralized timeout configuration (in milliseconds unless noted)."""
    PAGE_LOAD = _config.get('browser.timeouts.page_load_ms', 20000) if _use_config else 20000
    NETWORK_IDLE = _config.get('browser.timeouts.network_idle_ms', 20000) if _use_config else 20000
    DEFAULT_CONTEXT = _config.get('browser.timeouts.default_context_ms', 60000) if _use_config else 60000
    BROWSER_LAUNCH = _config.get('browser.timeouts.browser_launch_ms', 300000) if _use_config else 300000
    COOKIE_CLICK = _config.get('browser.timeouts.cookie_click_ms', 2000) if _use_config else 2000
    MODAL_CLOSE_WAIT = _config.get('browser.timeouts.modal_close_wait_ms', 1000) if _use_config else 1000
    WAIT_FOR_LOAD = _config.get('browser.timeouts.wait_for_load_ms', 2000) if _use_config else 2000
    SELENIUM_TIMEOUT = _config.get('browser.timeouts.selenium_timeout_sec', 20) if _use_config else 20


class Paths:
    """Centralized path configuration."""
    CACHE_DIR = Path(_config.get('paths.cache_dir', 'cache')) if _use_config else Path('cache')


class Limits:
    """Centralized limit configuration."""
    MAX_RETRIES = _config.get('browser.retries.max_retries', 3) if _use_config else 3
    MAX_CONSECUTIVE_ERRORS = _config.get('browser.retries.max_consecutive_errors', 8) if _use_config else 8


class UserAgents:
    """User agent strings."""
    CHROME = _config.get('browser.user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36') if _use_config else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'


class Resolutions:
    """Common screen resolutions."""
    COMMON = _config.get('browser.resolutions', [
        {'width': 1920, 'height': 1080},
        {'width': 1366, 'height': 768},
        {'width': 1536, 'height': 864},
        {'width': 1440, 'height': 900},
        {'width': 1280, 'height': 720}
    ]) if _use_config else [
        {'width': 1920, 'height': 1080},
        {'width': 1366, 'height': 768},
        {'width': 1536, 'height': 864},
        {'width': 1440, 'height': 900},
        {'width': 1280, 'height': 720}
    ]


class CookieSelectors:
    """Common cookie consent button selectors."""
    SELECTORS = _config.get('browser.cookie_selectors', [
        'button[data-action="init--explicit-consent-modal#accept"]',
        'button[aria-label*="accept" i]',
        'button:has-text("Accept")',
        'button:has-text("I agree")',
        '.accept-cookies',
        '#accept-cookies'
    ]) if _use_config else [
        'button[data-action="init--explicit-consent-modal#accept"]',
        'button[aria-label*="accept" i]',
        'button:has-text("Accept")',
        'button:has-text("I agree")',
        '.accept-cookies',
        '#accept-cookies'
    ]


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class ScraperError(Exception):
    """Base exception for scraper-related errors."""
    pass


class BrowserInitializationError(ScraperError):
    """Raised when browser initialization fails."""
    pass


class NavigationError(ScraperError):
    """Raised when page navigation fails."""
    pass


class ContentExtractionError(ScraperError):
    """Raised when content extraction fails."""
    pass


class OpenAIError(ScraperError):
    """Raised when OpenAI API calls fail."""
    pass


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class DownloadStats:
    """Statistics for download operations."""
    total: int
    processed: int
    skipped_session: int
    skipped_existing: int
    errors: int

    @property
    def total_skipped(self) -> int:
        """Calculate total skipped items."""
        return self.skipped_session + self.skipped_existing


# ============================================================================
# OPENAI FUNCTIONS
# ============================================================================

async def open_ai_call(
    model: str,
    prompt: str,
    debug: bool = False,
    api_key: Optional[str] = None
) -> Optional[str]:
    """
    Make an API call to OpenAI with the given model and prompt.

    Args:
        model: The OpenAI model to use (e.g., 'gpt-4', 'gpt-3.5-turbo').
        prompt: The prompt to send to the model.
        debug: Whether to print debug information.
        api_key: OpenAI API key. If None, reads from environment.

    Returns:
        The model's response text or None if an error occurs.

    Raises:
        OpenAIError: If the API call fails.
    """
    if not prompt:
        raise ValueError("Prompt cannot be empty")

    if not model:
        raise ValueError("Model cannot be empty")

    try:
        # Use provided API key or get from environment
        client_api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not client_api_key:
            raise OpenAIError("OpenAI API key not found in environment variables")

        client = openai.AsyncOpenAI(api_key=client_api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        if debug:
            print(f"\nDebug - Full OpenAI Response:\n{response}")

        content = response.choices[0].message.content
        return content.strip() if content else None

    except openai.APIError as e:
        error_msg = f"Error in OpenAI API call: {str(e)}"
        print(error_msg)
        raise OpenAIError(error_msg) from e


# ============================================================================
# COOKIE CONSENT FUNCTIONS
# ============================================================================

async def _try_click_cookie_button(
    page: Page,
    selector: str,
    debug: bool = False
) -> bool:
    """
    Attempt to click a cookie consent button with the given selector.

    Args:
        page: Playwright page object.
        selector: CSS selector for the button.
        debug: Whether to print debug information.

    Returns:
        True if the button was clicked successfully, False otherwise.
    """
    if debug:
        print(f"\nTrying selector: {selector}")
        element = await page.query_selector(selector)
        if element:
            element_html = await element.evaluate('element => element.outerHTML')
            print(f"Found element: {element_html}")
        else:
            print("Selector not found")

    try:
        await page.click(selector, timeout=Timeouts.COOKIE_CLICK)
        await page.wait_for_timeout(Timeouts.MODAL_CLOSE_WAIT)
        if debug:
            print(f"Successfully clicked cookie consent button with selector: {selector}")
        return True
    except Exception as e:
        if debug:
            print(f"Click failed: {str(e)}")
        return False


async def _remove_cookie_modal_js(page: Page, modal_class: str, debug: bool = False) -> bool:
    """
    Remove cookie modal using JavaScript as a fallback.

    Args:
        page: Playwright page object.
        modal_class: CSS class of the modal to remove.
        debug: Whether to print debug information.

    Returns:
        True if modal was removed, False otherwise.
    """
    if debug:
        print("\nTrying JavaScript removal approach...")

    try:
        result = await page.evaluate(f'''() => {{
            const modal = document.querySelector('.{modal_class}');
            if (modal) {{
                modal.remove();
                document.body.style.overflow = 'auto';
                return true;
            }}
            return false;
        }}''')

        if debug:
            if result:
                print("Successfully removed cookie modal via JavaScript")
            else:
                print("Modal element not found for JavaScript removal")
        return bool(result)

    except Exception as e:
        if debug:
            print(f"Failed to remove cookie modal: {str(e)}")
        return False


async def handle_cookie_consent(
    page: Page,
    consent_modal_class: str,
    debug: bool = False
) -> bool:
    """
    Handle cookie consent modal if present.

    Args:
        page: Playwright page object.
        consent_modal_class: CSS class of the cookie consent modal.
        debug: Whether to print debug information.

    Returns:
        True if consent was handled, False otherwise.
    """
    try:
        if debug:
            print(f"\nLooking for cookie modal with class: {consent_modal_class}")

        cookie_modal = await page.query_selector(f'.{consent_modal_class}')

        if not cookie_modal:
            return False

        if debug:
            print("Found cookie consent modal")
            modal_html = await cookie_modal.evaluate('element => element.outerHTML')
            print(f"Modal HTML: {modal_html}")

        # Try clicking various accept buttons
        for selector in CookieSelectors.SELECTORS:
            if await _try_click_cookie_button(page, selector, debug):
                return True

        # Fallback to JavaScript removal
        return await _remove_cookie_modal_js(page, consent_modal_class, debug)

    except Exception as e:
        if debug:
            print(f"Error handling cookie consent: {str(e)}")
        return False


# ============================================================================
# SELENIUM FUNCTIONS
# ============================================================================

async def get_html_with_selenium(
    url: str,
    timeout: int = Timeouts.SELENIUM_TIMEOUT
) -> Optional[str]:
    """
    Fallback function to get page HTML using Selenium with stealth mode.

    Args:
        url: URL to fetch.
        timeout: Timeout in seconds.

    Returns:
        HTML content of the page or None if failed.

    Raises:
        NavigationError: If navigation fails after all retries.
    """
    if not url:
        raise ValueError("URL cannot be empty")

    driver = None
    try:
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--disable-infobars')
        options.add_argument('--disable-blink-features=AutomationControlled')

        try:
            driver = uc.Chrome(options=options)
        except Exception as chrome_error:
            if "This version of ChromeDriver only supports Chrome version" in str(chrome_error):
                driver = uc.Chrome(options=options, version_main=None)
            else:
                raise

        driver.set_page_load_timeout(timeout)

        try:
            driver.get(url)
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located(('tag name', 'body'))
            )
            return driver.page_source

        except TimeoutException as e:
            error_msg = f"Timeout while loading {url} with Selenium"
            print(error_msg)
            raise NavigationError(error_msg) from e

        except Exception as e:
            error_msg = f"Error loading {url} with Selenium: {str(e)}"
            print(error_msg)
            raise NavigationError(error_msg) from e

    except Exception as e:
        error_msg = f"Error initializing Selenium: {str(e)}"
        print(error_msg)
        raise BrowserInitializationError(error_msg) from e

    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                print(f"Error closing Selenium driver: {str(e)}")


# ============================================================================
# PLAYWRIGHT BROWSER FUNCTIONS
# ============================================================================

async def init_browser(headless: bool = False) -> tuple[Page, Playwright, Browser]:
    """
    Initialize a Chromium browser with anti-detection measures using Playwright.

    Args:
        headless: Whether to run browser in headless mode.

    Returns:
        Tuple of (page, playwright, browser) for proper resource management.

    Raises:
        BrowserInitializationError: If browser initialization fails.
    """
    viewport = secrets.SystemRandom().choice(Resolutions.COMMON)

    playwright = await async_playwright().start()

    try:
        browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ],
            timeout=Timeouts.BROWSER_LAUNCH
        )
    except Exception as e:
        await playwright.stop()
        raise BrowserInitializationError(f"Failed to launch browser: {str(e)}") from e

    try:
        context = await browser.new_context(
            viewport=viewport,
            user_agent=UserAgents.CHROME,
            java_script_enabled=True,
            bypass_csp=True,
            ignore_https_errors=True,
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            extra_http_headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'max-age=0'
            }
        )

        context.set_default_timeout(Timeouts.DEFAULT_CONTEXT)

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });

            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Open Source Technology Center';
                }
                if (parameter === 37446) {
                    return 'Mesa DRI Intel(R) HD Graphics (SKL GT2)';
                }
                return getParameter.apply(this, [parameter]);
            };
        """)

        page = await context.new_page()
        return page, playwright, browser

    except Exception as e:
        await browser.close()
        await playwright.stop()
        raise BrowserInitializationError(f"Failed to create browser context: {str(e)}") from e


# ============================================================================
# URL UTILITY FUNCTIONS
# ============================================================================

def make_absolute_url(base_url: str, relative_url: Optional[str]) -> Optional[str]:
    """
    Convert a relative URL to an absolute URL.

    Args:
        base_url: The base URL of the website.
        relative_url: The relative URL to convert.

    Returns:
        The absolute URL or None if relative_url is None/empty.
    """
    if not relative_url:
        return None

    # Check if URL is already absolute
    if urlparse(relative_url).netloc:
        return relative_url

    # Clean the base URL
    parsed_base = urlparse(base_url)
    clean_base = f"{parsed_base.scheme}://{parsed_base.netloc}{parsed_base.path}"

    # Remove specific query patterns
    if clean_base.endswith('/search-results'):
        clean_base = clean_base[:-14]
    elif '?' in clean_base:
        clean_base = clean_base.split('?', maxsplit=1)[0]

    return urljoin(clean_base, relative_url)


# ============================================================================
# NAVIGATION FUNCTIONS
# ============================================================================

async def _try_lynx_fallback(url: str, page: Page, logger: Optional[ScraperLogger] = None) -> bool:
    """
    Try using lynx as a last resort fallback.

    Args:
        url: URL to fetch.
        page: Playwright page to set content on.
        logger: Optional logger for structured logging.

    Returns:
        True if successful, False otherwise.
    """
    if logger:
        logger.warning("Selenium fallback failed, trying lynx...")
    else:
        print("Selenium fallback failed, trying lynx...")

    try:
        process = await asyncio.create_subprocess_exec(
            'lynx', '-source', url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await process.communicate()
        if stdout:
            await page.set_content(stdout.decode())
            return True

        if logger:
            logger.warning("Lynx fallback also failed")
        else:
            print("Lynx fallback also failed")
        return False

    except FileNotFoundError:
        if logger:
            logger.debug("Lynx is not installed, skipping.")
        else:
            print("Lynx is not installed, skipping.")
        return False

    except Exception as e:
        if logger:
            logger.error(f"Lynx fallback error: {str(e)}")
        else:
            print(f"Lynx fallback error: {str(e)}")
        return False


async def navigate_with_retries(
    page: Page,
    url: str,
    max_retries: int = Limits.MAX_RETRIES,
    logger: Optional[ScraperLogger] = None
) -> bool:
    """
    Navigate to a URL with retry logic and Selenium fallback.

    Args:
        page: Playwright page object.
        url: URL to navigate to.
        max_retries: Maximum number of retry attempts.
        logger: Optional logger for structured logging.

    Returns:
        True if navigation succeeded, False otherwise.
    """
    if not url:
        raise ValueError("URL cannot be empty")

    last_error = None
    for retry_count in range(1, max_retries + 1):
        try:
            if logger:
                logger.debug(f"Navigation attempt {retry_count}/{max_retries} to {url}")
            await page.goto(url, timeout=Timeouts.PAGE_LOAD)
            await page.wait_for_load_state('networkidle', timeout=Timeouts.NETWORK_IDLE)
            if logger:
                logger.debug(f"Successfully navigated to {url}")
            return True

        except Exception as e:
            last_error = e
            if logger:
                logger.warning(f"Attempt {retry_count}/{max_retries}: Error loading {url}: {str(e)}")
            else:
                print(f"Attempt {retry_count}: Error loading page: {str(e)}")

            if retry_count == max_retries:
                # Try Selenium fallback
                if logger:
                    logger.warning("Playwright failed all retries, attempting Selenium fallback...")
                else:
                    print("Playwright failed, attempting Selenium fallback...")

                try:
                    content = await get_html_with_selenium(url)
                    if content:
                        await page.set_content(content)
                        if logger:
                            logger.info("Selenium fallback successful")
                        return True
                except Exception as se:
                    if logger:
                        logger.error(f"Selenium fallback failed: {str(se)}")
                    else:
                        print(f"Selenium fallback error: {str(se)}")

                # Try lynx as last resort
                if await _try_lynx_fallback(url, page, logger):
                    if logger:
                        logger.info("Lynx fallback successful")
                    return True

                # All methods failed - capture error context
                if logger:
                    await logger.capture_error_context(
                        error_type="NavigationError",
                        error_message=f"Failed to navigate to {url} after {max_retries} retries and all fallbacks",
                        url=url,
                        page=page,
                        stack_trace=traceback.format_exc(),
                        context={
                            "max_retries": max_retries,
                            "last_error": str(last_error),
                            "attempted_methods": ["playwright", "selenium", "lynx"],
                            "timeout_ms": Timeouts.PAGE_LOAD
                        }
                    )
                return False

            # Wait before retry
            await asyncio.sleep(5)

    return False


async def wait_for_load(page: Page, timeout: int = Timeouts.WAIT_FOR_LOAD) -> None:
    """
    Wait for page to load completely using multiple wait conditions.

    Args:
        page: Playwright page object.
        timeout: Time to wait in milliseconds after networkidle.
    """
    try:
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(timeout)
    except Exception as e:
        print(f"Error waiting for page load: {str(e)}")


# ============================================================================
# CONTENT DOWNLOAD FUNCTIONS
# ============================================================================

def _generate_cache_filename(name: str, url: str) -> Path:
    """
    Generate a unique cache filename for a URL.

    Args:
        name: Name prefix for the file.
        url: URL to generate hash from.

    Returns:
        Path object for the cache file.

    Raises:
        ValueError: If url is None or empty.
    """
    if not url:
        raise ValueError(f"Cannot generate cache filename: URL is {url!r}")
    url_hash = hashlib.sha256(url.encode()).hexdigest()
    filename = f"{name}_{url_hash}.txt"
    return Paths.CACHE_DIR / filename


async def _download_single_link(
    url: str,
    page: Page,
    name: str,
    stats: DownloadStats,
    processed_urls: Set[str],
    sleep_time: int = 0,
    logger: Optional[ScraperLogger] = None
) -> bool:
    """
    Download content from a single URL.

    Args:
        url: URL to download.
        page: Playwright page object.
        name: Name prefix for saved file.
        stats: Download statistics object.
        processed_urls: Set of already processed URLs.
        sleep_time: Optional sleep time between requests.
        logger: Optional logger for structured logging.

    Returns:
        True if successful, False if error occurred.
    """
    # Check if already processed in this session
    if url in processed_urls:
        stats.skipped_session += 1
        if logger:
            logger.debug(f"Skipped (already processed): {url}")
        return True

    # Check if file already exists
    filepath = _generate_cache_filename(name, url)
    if filepath.exists():
        stats.skipped_existing += 1
        if logger:
            logger.debug(f"Skipped (cached): {url}")
        return True

    try:
        # Navigate to the page
        try:
            await navigate_with_retries(page, url, logger=logger)
            await wait_for_load(page)
            content = await page.content()
        except Exception as nav_error:
            if logger:
                logger.error(f"Navigation error for {url}: {str(nav_error)}")
            else:
                print(f"Navigation error for {url}: {str(nav_error)}")
            return False

        # Extract clean text using trafilatura
        extracted_text = trafilatura.extract(content, favor_recall=True)
        if extracted_text:
            content = f"{url}\n\n{extracted_text}"

        # Save to file
        async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
            await f.write(content)

        stats.processed += 1
        if logger:
            logger.debug(f"Downloaded {stats.processed}/{stats.total}: {url}")
        else:
            print(f"Downloaded {stats.processed}/{stats.total}: {url}")
        processed_urls.add(url)

        # Sleep if requested (using async sleep)
        if sleep_time > 0:
            if logger:
                logger.debug(f"Sleeping {sleep_time} seconds...")
            else:
                print(f"Extra Sleep Requested {sleep_time} seconds.")
            await asyncio.sleep(sleep_time)

        return True

    except Exception as e:
        if logger:
            logger.error(f"Error downloading {url}: {str(e)}")
        else:
            print(f"Error downloading {url}: {str(e)}")
        stats.errors += 1
        return False


async def download_all_links(
    links: List[str],
    page: Page,
    name: str,
    sleep: int = 0,
    logger: Optional[ScraperLogger] = None
) -> DownloadStats:
    """
    Downloads content from all provided URLs and saves them to a cache folder.

    Args:
        links: List of URLs to download.
        page: Playwright page object.
        name: Name prefix for saved files.
        sleep: Optional sleep time between requests in seconds.
        logger: Optional logger for structured logging.

    Returns:
        DownloadStats object with download statistics.
    """
    # Filter out None/empty URLs and log warning
    valid_links = [link for link in links if link]
    invalid_count = len(links) - len(valid_links)

    if invalid_count > 0:
        if logger:
            logger.warning(f"Filtered out {invalid_count} invalid (None/empty) URLs from link list")
        else:
            print(f"Warning: Filtered out {invalid_count} invalid URLs")

    # Shuffle links for randomization
    links_list = list(valid_links)
    secrets.SystemRandom().shuffle(links_list)

    # Ensure cache directory exists
    Paths.CACHE_DIR.mkdir(exist_ok=True)

    # Initialize tracking
    processed_urls: Set[str] = set()
    stats = DownloadStats(
        total=len(links_list),
        processed=0,
        skipped_session=0,
        skipped_existing=0,
        errors=0
    )
    consecutive_errors = 0

    for url in links_list:
        success = await _download_single_link(
            url, page, name, stats, processed_urls, sleep, logger
        )

        if success:
            consecutive_errors = 0
        else:
            consecutive_errors += 1
            wait_time = 2 ** consecutive_errors

            if logger:
                logger.warning(f"Consecutive errors: {consecutive_errors}, wait time: {wait_time}s")
            else:
                print(f"Consecutive errors: {consecutive_errors}")

            if consecutive_errors >= Limits.MAX_CONSECUTIVE_ERRORS:
                if logger:
                    logger.error(f"Exiting after {consecutive_errors} consecutive errors")
                else:
                    print(f"Exiting after {consecutive_errors} consecutive errors")
                break

            if not logger:
                print(f"Waiting {wait_time} seconds before next attempt...")
            await asyncio.sleep(wait_time)

    # Print summary
    if logger:
        logger.info(f"Download complete: {stats.processed} processed, {stats.total_skipped} skipped, {stats.errors} errors")
        logger.increment_stat("total_jobs_downloaded", stats.processed)
        logger.increment_stat("total_jobs_skipped", stats.total_skipped)
    else:
        if stats.total_skipped > 0:
            print(f"\nSkipped {stats.total_skipped} of {stats.total} total links:")
            if stats.skipped_session > 0:
                print(f"- {stats.skipped_session} already processed in this session")
            if stats.skipped_existing > 0:
                print(f"- {stats.skipped_existing} already existed in cache")

    return stats


# ============================================================================
# MAIN SCRAPING FUNCTION
# ============================================================================

async def _extract_job_links(
    page: Page,
    job_link_selector: str,
    logger: Optional[ScraperLogger] = None
) -> List[str]:
    """
    Extract job links from the current page.

    Args:
        page: Playwright page object.
        job_link_selector: CSS selector for job links.
        logger: Optional logger for structured logging.

    Returns:
        List of job link URLs.
    """
    try:
        links = await page.evaluate(f'''() => {{
            const elements = document.querySelectorAll('{job_link_selector}');
            return Array.from(elements).map(el => el.href);
        }}''')

        if logger:
            logger.debug(f"Extracted {len(links)} job links using selector: {job_link_selector}")

        if not links and logger:
            # Selector didn't match anything - capture error context
            await logger.capture_error_context(
                error_type="SelectorError",
                error_message=f"Job link selector '{job_link_selector}' returned no results",
                url=page.url,
                page=page,
                context={
                    "selector": job_link_selector,
                    "page_url": page.url,
                    "selector_type": "job_links"
                }
            )

        return links

    except Exception as e:
        if logger:
            logger.error(f"Error extracting job links: {str(e)}")
            await logger.capture_error_context(
                error_type="SelectorError",
                error_message=f"Failed to extract job links with selector '{job_link_selector}'",
                url=page.url,
                page=page,
                stack_trace=traceback.format_exc(),
                context={
                    "selector": job_link_selector,
                    "error": str(e)
                }
            )
        raise


async def _navigate_to_next_page(
    page: Page,
    next_page_selector: str,
    next_page_disabled_selector: str,
    logger: Optional[ScraperLogger] = None
) -> bool:
    """
    Navigate to the next page of results.

    Args:
        page: Playwright page object.
        next_page_selector: CSS selector for next page button.
        next_page_disabled_selector: CSS selector for disabled next page button.
        logger: Optional logger for structured logging.

    Returns:
        True if navigation succeeded, False if on last page.
    """
    # Check if on last page
    next_button_disabled = await page.query_selector(next_page_disabled_selector)
    if next_button_disabled:
        if logger:
            logger.info("Reached last page - next button is disabled")
        else:
            print("🏁 Reached last page - next button is disabled")
        return False

    # Find and click next button
    next_button = await page.query_selector(next_page_selector)
    if not next_button:
        if logger:
            logger.info("No more next button found")
        else:
            print("No more next button found")
        return False

    await next_button.click()
    await wait_for_load(page)
    return True


async def scrape_site(
    url: str,
    name: str,
    job_link_selector: str,
    next_page_selector: str,
    next_page_disabled_selector: str,
    headless: bool = True,
    logger: Optional[ScraperLogger] = None
) -> None:
    """
    Scrapes a job board site for job postings.

    Args:
        url: The URL of the job board to scrape.
        name: The name of the company.
        job_link_selector: The CSS selector for the job links.
        next_page_selector: The CSS selector for the next page button.
        next_page_disabled_selector: The CSS selector for the disabled next page button.
        headless: Whether to run the browser in headless mode.
        logger: Optional logger for structured logging.

    Raises:
        BrowserInitializationError: If browser initialization fails.
        NavigationError: If initial navigation fails.
    """
    if not url:
        raise ValueError("URL cannot be empty")
    if not name:
        raise ValueError("Name cannot be empty")
    if not job_link_selector:
        raise ValueError("Job link selector cannot be empty")

    if logger:
        logger.info(f"Starting to scrape: {name}")
        logger.info(f"URL: {url}")
        logger.add_breadcrumb(f"Started scraping {name} at {url}")
    else:
        print(f"\n{'='*80}")
        print(f"Starting to scrape: {name}")
        print(f"URL: {url}")
        print(f"{'='*80}\n")

    if logger:
        logger.debug("Initializing browser...")
    else:
        print("Initializing browser...")

    page, playwright, browser = await init_browser(headless=headless)

    try:
        if logger:
            logger.info("Attempting to navigate to job board...")
        else:
            print("Attempting to navigate to job board...")

        success = await navigate_with_retries(page, url, logger=logger)
        if not success:
            raise NavigationError(f"Failed to load the page: {url}")

        if logger:
            logger.info("Successfully loaded job board")
        else:
            print("✅ Successfully loaded job board")

        all_job_links: List[str] = []
        page_num = 1

        # Scrape all pages
        while True:
            job_links = await _extract_job_links(page, job_link_selector, logger)
            all_job_links.extend(job_links)

            if logger:
                logger.info(f"Page {page_num}: Found {len(job_links)} job links")
            else:
                print(f"📄 Page {page_num}: Found {len(job_links)} job links")

            # Try to navigate to next page
            if not await _navigate_to_next_page(page, next_page_selector, next_page_disabled_selector, logger):
                break

            page_num += 1

        # Print summary
        if logger:
            logger.info(f"Summary for {name}: {page_num} pages scraped, {len(all_job_links)} job links found")
            logger.increment_stat("total_jobs_found", len(all_job_links))
        else:
            print(f"\n📊 Summary for {name}:")
            print(f"- Total pages scraped: {page_num}")
            print(f"- Total job links found: {len(all_job_links)}")

        # Download all job postings
        if logger:
            logger.info("Starting download of job postings...")
        else:
            print("\n⬇️ Starting download of job postings...")

        await download_all_links(all_job_links, page, name, logger=logger)

    except Exception as e:
        if logger:
            logger.error(f"Error processing {url}: {str(e)}")
        else:
            print(f"❌ Error processing {url}: {str(e)}")
        raise

    finally:
        if logger:
            logger.debug("Cleaning up browser resources...")
        else:
            print("🧹 Cleaning up browser resources...")

        try:
            await page.context.close()
            await browser.close()
            await playwright.stop()
        except Exception as e:
            if logger:
                logger.warning(f"Error during cleanup: {str(e)}")
            else:
                print(f"Error during cleanup: {str(e)}")

        if not logger:
            print(f"\n{'='*80}")
