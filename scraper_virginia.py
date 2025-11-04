"""This module scrapes job postings from the Virginia state job board."""

import asyncio

from functions import init_browser, navigate_with_retries, handle_cookie_consent, wait_for_load, download_all_links
from logging_config import get_logger


NAME = "virginia"
URL = "https://www.jobs.virginia.gov/jobs/search?page=1&cities%5B%5D=Richmond&query="


async def main():
    """Scrapes the Virginia state job board."""
    # Initialize logger
    logger = get_logger("virginia")

    logger.info("Starting Virginia State Job Board Scraper")
    logger.add_breadcrumb("Initializing browser")

    page = await init_browser(headless=True)

    logger.add_breadcrumb("Navigating to job board")
    success = await navigate_with_retries(page, URL)
    if not success:
        logger.error("Failed to load the page")
        return

    logger.add_breadcrumb("Handling cookie consent")
    await handle_cookie_consent(page, "consent-modal")
    await page.wait_for_timeout(1000)

    all_job_links = set()
    page_num = 1

    logger.add_breadcrumb("Starting pagination")
    while True:
        job_links = await page.evaluate('''() => {
            const elements = document.querySelectorAll('.job-search-results-title a');
            return Array.from(elements).map(el => el.href);
        }''')

        all_job_links.update(job_links)
        logger.info(f"Page {page_num}: Found {len(job_links)} job links")

        next_button = await page.query_selector('li.next.next_page a')
        if not next_button:
            logger.info("No more next button found")
            break

        next_url = await next_button.get_attribute('href')
        if not next_url:
            logger.info("Could not get next page URL")
            break

        next_url = 'https://www.jobs.virginia.gov' + next_url
        success = await navigate_with_retries(page, next_url)
        if not success:
            logger.error("Failed to load next page")
            break

        await wait_for_load(page)
        page_num += 1

    logger.info(f"Total unique job links found across {page_num} pages: {len(all_job_links)}")
    logger.increment_stat("total_jobs_found", len(all_job_links))
    logger.increment_stat("pages_scraped", page_num)

    all_job_links_list = list(all_job_links)

    logger.add_breadcrumb("Starting job download")
    logger.info("Starting download of job postings...")
    await download_all_links(all_job_links_list, page, NAME)

    await page.context.close()

    # Write summary
    duration = logger.write_summary()
    logger.info("Completed Virginia state job board scraping")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
