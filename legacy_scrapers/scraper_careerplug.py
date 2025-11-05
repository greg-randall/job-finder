"""This module scrapes job postings from CareerPlug job boards."""

import asyncio
import random

from functions import init_browser, navigate_with_retries, download_all_links
from logging_config import get_logger


JOBS = [
    "https://call-federal-credit-union.careerplug.com/jobs",
    "https://the-goddard-school-careers.careerplug.com/jobs",
]


async def scrape_careerplug_site(url, logger):
    """Scrapes a single CareerPlug job board."""
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

        all_job_links = []
        page_num = 1

        logger.add_breadcrumb("Starting pagination")
        while True:
            current_url = f"{url}?page={page_num}"

            success = await navigate_with_retries(page, current_url)
            if not success:
                logger.error(f"Failed to load page {page_num}")
                break

            job_links = await page.evaluate('''() => {
                const jobTable = document.getElementById('job_table');
                if (!jobTable) return [];
                const links = jobTable.getElementsByTagName('a');
                return Array.from(links)
                    .map(link => link.href)
                    .filter(href => href);
            }''')

            if not job_links:
                logger.info("No jobs found on this page - reached the end")
                break

            all_job_links.extend(job_links)
            logger.info(f"Page {page_num}: Found {len(job_links)} job links - {current_url}")

            wait_time = random.uniform(3, 9)
            logger.info(f"Waiting {wait_time:.1f} seconds before next page...")
            await page.wait_for_timeout(wait_time * 1000)

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
    """Scrapes all CareerPlug job boards."""
    # Initialize logger
    logger = get_logger("careerplug")
    total_sites = len(JOBS)

    logger.info(f"Starting CareerPlug Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        logger.info(f"Site {index}/{total_sites}")
        logger.add_breadcrumb(f"Processing site {index}/{total_sites}")

        try:
            await scrape_careerplug_site(url, logger)
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape site {index}: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info(f"Completed all {total_sites} CareerPlug job boards")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
