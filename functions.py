"This module provides a set of asynchronous functions to support web scraping tasks, including browser initialization, page navigation, content extraction, and interaction with the OpenAI API."

import asyncio
import hashlib
import os
import secrets
import time
from urllib.parse import urljoin, urlparse

import aiofiles
import openai
import trafilatura
import undetected_chromedriver as uc
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv('OPENAI_API_KEY')


async def open_ai_call(model, prompt, debug=False):
    """
    Make an API call to OpenAI with the given model and prompt.

    Args:
        model (str): The OpenAI model to use (e.g., 'gpt-4', 'gpt-3.5-turbo').
        prompt (str): The prompt to send to the model.
        debug (bool): Whether to print debug information.

    Returns:
        str: The model's response text or None if an error occurs.
    """
    try:
        client = openai.AsyncOpenAI()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        if debug:
            print(f"\nDebug - Full OpenAI Response:\n{response}")
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        print(f"Error in OpenAI API call: {str(e)}")
        return None


async def handle_cookie_consent(page, consent_modal_class, debug=False):
    """
    Handle cookie consent modal if present.

    Args:
        page: Playwright page object.
        consent_modal_class (str): CSS class of the cookie consent modal.
        debug (bool): Whether to print debug information.

    Returns:
        bool: True if consent was handled, False otherwise.
    """
    try:
        if debug:
            print(f"\nLooking for cookie modal with class: {consent_modal_class}")

        cookie_modal = await page.query_selector(f'.{consent_modal_class}')

        if cookie_modal:
            if debug:
                print("Found cookie consent modal")
                modal_html = await cookie_modal.evaluate('element => element.outerHTML')
                print(f"Modal HTML: {modal_html}")

            selectors = [
                'button[data-action="init--explicit-consent-modal#accept"]',
                'button[aria-label*="accept" i]',
                'button:has-text("Accept")',
                'button:has-text("I agree")',
                '.accept-cookies',
                '#accept-cookies'
            ]
            for selector in selectors:
                if debug:
                    print(f"\nTrying selector: {selector}")
                    element = await page.query_selector(selector)
                    if element:
                        element_html = await element.evaluate('element => element.outerHTML')
                        print(f"Found element: {element_html}")
                    else:
                        print("Selector not found")

                try:
                    await page.click(selector, timeout=2000)
                    await page.wait_for_timeout(1000)  # Wait for modal to close
                    if debug:
                        print(f"Successfully clicked cookie consent button with selector: {selector}")
                    return True
                except TimeoutError:
                    if debug:
                        print(f"Click failed: {str(e)}")
                    continue

            if debug:
                print("\nTrying JavaScript removal approach...")
            try:
                result = await page.evaluate('''() => {
                    const modal = document.querySelector('.consent-modal');
                    if (modal) {
                        modal.remove();
                        document.body.style.overflow = 'auto';
                        return true;
                    }
                    return false;
                }''')
                if debug:
                    if result:
                        print("Successfully removed cookie modal via JavaScript")
                    else:
                        print("Modal element not found for JavaScript removal")
                return True
            except Exception as e:
                if debug:
                    print(f"Failed to remove cookie modal: {str(e)}")
                return False
    except Exception as e:
        if debug:
            print(f"Error handling cookie consent: {str(e)}")
        return False
    return False


async def get_html_with_selenium(url, timeout=20):
    """
    Fallback function to get page HTML using Selenium with stealth mode.

    Args:
        url (str): URL to fetch.
        timeout (int): Timeout in seconds.

    Returns:
        str: HTML content of the page or None if failed.
    """
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
        except TimeoutException:
            print(f"Timeout while loading {url} with Selenium")
            return None
        except Exception as e:
            print(f"Error loading {url} with Selenium: {str(e)}")
            return None
        finally:
            driver.quit()

    except Exception as e:
        print(f"Error initializing Selenium: {str(e)}")
        return None


async def init_browser(headless=False):
    """
    Initialize a Chromium browser with anti-detection measures using Playwright.

    Args:
        headless (bool): Whether to run browser in headless mode.

    Returns:
        Browser context with configured settings.
    """
    resolutions = [
        {'width': 1920, 'height': 1080},
        {'width': 1366, 'height': 768},
        {'width': 1536, 'height': 864},
        {'width': 1440, 'height': 900},
        {'width': 1280, 'height': 720}
    ]

    viewport = secrets.SystemRandom().choice(resolutions)

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
            timeout=300000  # 5 minutes
        )
    except Exception as e:
        print(f"Failed to launch browser: {str(e)}")
        await playwright.stop()
        raise

    context = await browser.new_context(
        viewport=viewport,
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
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

    context.set_default_timeout(60000)  # 60 seconds

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
    """ ) # Corrected: Removed unnecessary triple quotes around the string literal

    page = await context.new_page()

    return page


def make_absolute_url(base_url, relative_url):
    """
    Convert a relative URL to an absolute URL.

    Args:
        base_url (str): The base URL of the website.
        relative_url (str): The relative URL to convert.

    Returns:
        str: The absolute URL.
    """
    if not relative_url:
        return None

    if bool(urlparse(relative_url).netloc):
        return relative_url

    parsed_base = urlparse(base_url)
    clean_base = f"{parsed_base.scheme}://{parsed_base.netloc}{parsed_base.path}"
    if clean_base.endswith('/search-results'):
        clean_base = clean_base[:-14]
    elif '?' in clean_base:
        clean_base = clean_base.split('?', maxsplit=1)[0]

    return urljoin(clean_base, relative_url)


async def navigate_with_retries(page, url, max_retries=3):
    """
    Navigate to a URL with retry logic and Selenium fallback.

    Args:
        page: Playwright page object.
        url (str): URL to navigate to.
        max_retries (int): Maximum number of retry attempts.

    Returns:
        bool: True if navigation succeeded, False otherwise.
    """
    retry_count = 0
    while retry_count < max_retries:
        try:
            await page.goto(url, timeout=20000)
            await page.wait_for_load_state('networkidle', timeout=20000)
            return True
        except TimeoutError as e:
            retry_count += 1
            print(f"Attempt {retry_count}: Error loading page: {str(e)}")
            if retry_count == max_retries:
                print("Playwright failed, attempting Selenium fallback...")
                try:
                    content = await get_html_with_selenium(url)
                    if content:
                        await page.set_content(content)
                        return True

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

                        print("Lynx fallback also failed")
                    except FileNotFoundError:
                        print("Lynx is not installed, skipping.")
                    except Exception as le:
                        print(f"Lynx fallback error: {str(le)}")
                except Exception as se:
                    print(f"Selenium fallback error: {str(se)}")
                return False
            await asyncio.sleep(5)
    return False


async def wait_for_load(page, timeout=2000):
    """
    Wait for page to load completely using multiple wait conditions.

    Args:
        page: Playwright page object.
        timeout (int): Time to wait in milliseconds after networkidle.
    """
    try:
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(timeout)
    except TimeoutError as e:
        print(f"Error waiting for page load: {str(e)}")


async def download_all_links(links, page, name, sleep=0):
    """
    Downloads content from all provided URLs and saves them to a cache folder.

    Args:
        links (list): List of URLs to download.
        page (Page): Playwright page object.
        name (str): Name prefix for saved files.
        sleep (int): Optional sleep time between requests.
    """
    links_list = list(links)
    secrets.SystemRandom().shuffle(links_list)

    cache_dir = 'cache'
    os.makedirs(cache_dir, exist_ok=True)

    processed_urls = set()
    skipped_session = 0
    skipped_existing = 0

    consecutive_errors = 0
    max_consecutive_errors = 8

    for i, url in enumerate(links, 1):
        if url in processed_urls:
            skipped_session += 1
            continue

        try:
            filename = f"{name}_{hashlib.sha256(url.encode()).hexdigest()}.txt"
            filepath = os.path.join(cache_dir, filename)

            if os.path.exists(filepath):
                skipped_existing += 1
                continue

            try:
                await navigate_with_retries(page, url)
                await wait_for_load(page)
                content = await page.content()
            except Exception as nav_error:
                print(f"Navigation error for {url}: {str(nav_error)}")
                continue

            extracted_text = trafilatura.extract(content, favor_recall=True)
            if extracted_text:
                content = f"{url}\n\n{extracted_text}"

            async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                await f.write(content)

            print(f"Downloaded {i}/{len(links)}: {url}")
            processed_urls.add(url)

            consecutive_errors = 0

            if sleep != 0:
                print(f"Extra Sleep Requested {sleep} seconds.")
                time.sleep(sleep)

        except Exception as e:
            consecutive_errors += 1
            wait_time = 2 ** consecutive_errors
            print(f"Error downloading {url}: {str(e)}")
            print(f"Consecutive errors: {consecutive_errors}")

            if consecutive_errors >= max_consecutive_errors:
                print(f"Exiting after {consecutive_errors} consecutive errors")
                break

            print(f"Waiting {wait_time} seconds before next attempt...")
            await asyncio.sleep(wait_time)

    if total_skipped > 0:
        print(f"\nSkipped {total_skipped} of {len(links)} total links:")
        if skipped_session > 0:
            print(f"- {skipped_session} already processed in this session")
        if skipped_existing > 0:
            print(f"- {skipped_existing} already existed in cache")


async def scrape_site(url, name, job_link_selector, next_page_selector, next_page_disabled_selector, headless=True):
    """
    Scrapes a job board site for job postings.

    Args:
        url (str): The URL of the job board to scrape.
        name (str): The name of the company.
        job_link_selector (str): The CSS selector for the job links.
        next_page_selector (str): The CSS selector for the next page button.
        next_page_disabled_selector (str): The CSS selector for the disabled next page button.
        headless (bool): Whether to run the browser in headless mode.
    """
    print(f"\n{'='*80}")
    print(f"Starting to scrape: {name}")
    print(f"URL: {url}")
    print(f"{'='*80}\n")

    print("Initializing browser...")
    page = await init_browser(headless=headless)

    try:
        print("Attempting to navigate to job board...")
        success = await navigate_with_retries(page, url)
        if not success:
            print(f"❌ Failed to load the page: {url}")
            return
        print("✅ Successfully loaded job board")

        all_job_links = []
        page_num = 1

        while True:
            job_links = await page.evaluate(f'''() => {{
                const elements = document.querySelectorAll("{job_link_selector}");
                return Array.from(elements).map(el => el.href);
            }}''')

            all_job_links.extend(job_links)
            print(f"📄 Page {page_num}: Found {len(job_links)} job links")

            next_button = await page.query_selector(next_page_disabled_selector)
            if next_button:
                print("🏁 Reached last page - next button is disabled")
                break

            next_button = await page.query_selector(next_page_selector)
            if not next_button:
                print("No more next button found")
                break

            await next_button.click()
            await wait_for_load(page)
            page_num += 1

        print(f"\n📊 Summary for {name}:")
        print(f"- Total pages scraped: {page_num}")
        print(f"- Total job links found: {len(all_job_links)}")

        print("\n⬇️ Starting download of job postings...")
        await download_all_links(all_job_links, page, name)

    except Exception as e:
        print(f"❌ Error processing {url}: {str(e)}")

    finally:
        print("🧹 Cleaning up browser resources...")
        await page.context.close()
        print(f"\n{'='*80}")
