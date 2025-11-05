"""This module scrapes job postings from the Bon Secours job board."""

import asyncio

from functions import init_browser, navigate_with_retries, wait_for_load, download_all_links
from logging_config import get_logger


NAME = "bon-secours"
URL = ("https://careers.bonsecours.com/us/en/search-results?"
       "keywords=&p=65a8e27d8879283831b664bd8b7f0ad4&location=Richmond,%20Virginia,%20United%20States")


async def main():
    """Scrapes the Bon Secours job board."""
    # Initialize logger
    logger = get_logger("bon_secours")

    logger.info("Starting Bon Secours Scraper")
    logger.add_breadcrumb("Initializing browser")

    page = await init_browser(headless=True)

    logger.add_breadcrumb("Navigating to job board")
    success = await navigate_with_retries(page, URL)
    if not success:
        logger.error("Failed to load the page")
        return

    try:
        await page.wait_for_timeout(2000)
        logger.add_breadcrumb("Selecting Richmond location filter")
        checked = await page.evaluate('''() => {
            const checkbox = document.querySelector('input[data-ph-at-text="Richmond"]');
            if (checkbox) {
                checkbox.checked = true;
                checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
            return false;
        }''')

        if checked:
            await wait_for_load(page)
            logger.info("Selected Richmond location filter using JavaScript")
        else:
            logger.error("Could not find Richmond checkbox")
            return
    except Exception as e:
        logger.error(f"Error selecting Richmond location: {str(e)}")
        return

    all_job_links = set()
    page_num = 1

    logger.add_breadcrumb("Starting pagination through job listings")
    while True:
        job_links = await page.evaluate('''() => {
            const elements = document.querySelectorAll('[ph-tevent="job_click"]');
            return Array.from(elements).map(el => el.href);
        }''')

        all_job_links.update(job_links)
        logger.info(f"Page {page_num}: Found {len(job_links)} job links")

        next_button = await page.query_selector('a.next-btn')
        if not next_button:
            logger.info("No more next button found - reached last page")
            break

        try:
            await next_button.click()
        except Exception:
            logger.info("Could not click next button - reached last page")
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
    logger.info("Completed Bon Secours job board scraping")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
