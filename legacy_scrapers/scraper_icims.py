"""This module scrapes job postings from iCIMS job boards."""

import asyncio
import os

import aiofiles

from functions import init_browser, navigate_with_retries, download_all_links
from logging_config import get_logger


JOBS = [
    "https://careers-audacy.icims.com/jobs/search?ss=1",
    "https://careers-chesbank.icims.com/jobs/search?ss=1",
    "https://careers-dewberry.icims.com/jobs/search?ss=1",
    "https://careers-gilbaneco.icims.com/jobs/search?ss=1",
]


async def scrape_icims_site(url, logger):
    """Scrapes a single iCIMS job board."""
    name = url.split('.')[0].split('//')[1]

    logger.info(f"Starting to scrape: {name}")
    logger.info(f"URL: {url}")
    logger.add_breadcrumb(f"Scraping {name}")

    logger.add_breadcrumb("Initializing browser")
    page = await init_browser(headless=True)

    try:
        logger.add_breadcrumb("Navigating to job board")
        success = await navigate_with_retries(page, url)
        if not success:
            logger.error(f"Failed to load the page: {url}")
            return
        logger.info("Successfully loaded job board")

        screenshot_dir = 'debug_screenshots'
        html_dir = 'debug_html'
        os.makedirs(screenshot_dir, exist_ok=True)
        os.makedirs(html_dir, exist_ok=True)

        screenshot_path = os.path.join(screenshot_dir, f"{name}_page_load.jpg")
        await page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"Saved full page screenshot to {screenshot_path}")

        html_path = os.path.join(html_dir, f"{name}_page.html")
        html_content = await page.content()
        async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
            await f.write(html_content)
        logger.info(f"Saved page HTML to {html_path}")

        logger.add_breadcrumb("Looking for jobs iframe")
        iframe = await page.wait_for_selector('iframe[id="icims_content_iframe"]')
        frame = await iframe.content_frame()
        logger.info("Switched to jobs iframe")

        all_job_links = []
        page_num = 1

        logger.add_breadcrumb("Starting pagination")
        while True:
            await frame.wait_for_selector('.iCIMS_Anchor', state='visible')

            job_links = await frame.evaluate('''() => {
                const elements = document.querySelectorAll('a.iCIMS_Anchor');
                return Array.from(elements)
                    .filter(el => el.href && el.href.includes('/jobs/'))
                    .filter(el => el.querySelector('h3'))
                    .map(a => a.href);
            }''')

            all_job_links.extend(job_links)
            logger.info(f"Page {page_num}: Found {len(job_links)} job links")

            next_button = await frame.query_selector('a.iCIMS_Pagination_Bottom-next')
            if not next_button:
                logger.info("Reached last page - no next button found")
                break

            is_disabled = await next_button.evaluate('''(el) => {
                const style = window.getComputedStyle(el);
                return el.classList.contains('disabled') ||
                       el.classList.contains('iCIMS_Pagination_Bottom-next-disabled') ||
                       style.display === "none" ||
                       style.visibility === "hidden" ||
                       !el.offsetParent ||
                       el.getAttribute('aria-disabled') === 'true';
            }''')

            if is_disabled:
                logger.info("Reached last page - next button is disabled")
                break

            await next_button.click()
            await frame.wait_for_load_state('networkidle')
            await frame.wait_for_selector('.iCIMS_Anchor', state='visible')
            page_num += 1

        logger.info(f"Summary for {name}: {page_num} pages scraped, {len(all_job_links)} job links found")
        logger.increment_stat("total_jobs_found", len(all_job_links))
        logger.increment_stat("pages_scraped", page_num)

        logger.add_breadcrumb("Starting job download")
        logger.info("Starting download of job postings...")
        await download_all_links(all_job_links, page, name)

    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}")

    finally:
        logger.add_breadcrumb("Cleaning up browser")
        await page.context.close()


async def main():
    """Scrapes all iCIMS job boards."""
    # Initialize logger
    logger = get_logger("icims")
    total_sites = len(JOBS)

    logger.info(f"Starting iCIMS Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        logger.info(f"Site {index}/{total_sites}")
        logger.add_breadcrumb(f"Processing site {index}/{total_sites}")

        try:
            await scrape_icims_site(url, logger)
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape site {index}: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info(f"Completed all {total_sites} iCIMS job boards")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
