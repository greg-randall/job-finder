"""This module scrapes job postings from the Federal Reserve job board."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


NAME = "fed-reserve"
URL = "https://rb.wd5.myworkdayjobs.com/FRS?locations=fd925bdfc7240167c220be442401af07"


async def main():
    """Scrapes the Federal Reserve job board."""
    # Initialize logger
    logger = get_logger("fed_reserve")

    logger.info("Starting Federal Reserve Scraper")
    logger.add_breadcrumb("Processing Federal Reserve job board")

    try:
        await scrape_site(
            URL, NAME, '[data-automation-id="jobTitle"]',
            '[data-uxi-widget-type="stepToNextButton"]:not([disabled])',
            '[data-uxi-widget-type="stepToNextButton"][disabled]',
            logger=logger
        )
        logger.increment_stat("sites_processed")
    except Exception as e:
        logger.error(f"Failed to scrape Federal Reserve: {str(e)}")
        logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info("Completed Federal Reserve job board scraping")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
