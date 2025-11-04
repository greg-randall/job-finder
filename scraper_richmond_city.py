"""This module scrapes job postings from the City of Richmond job board."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


NAME = "richmond-city"
URL = "https://www.governmentjobs.com/careers/richmond"


async def main():
    """Scrapes the City of Richmond job board."""
    # Initialize logger
    logger = get_logger("richmond_city")

    logger.info("Starting Richmond City Scraper")
    logger.add_breadcrumb("Processing Richmond City job board")

    try:
        await scrape_site(URL, NAME, ".item-details-link", ".PagedList-skipToNext a", ".PagedList-skipToNext.disabled", logger=logger)
        logger.increment_stat("sites_processed")
    except Exception as e:
        logger.error(f"Failed to scrape Richmond City: {str(e)}")
        logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info("Completed Richmond City job board scraping")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
