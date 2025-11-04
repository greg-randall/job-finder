"""This module scrapes job postings from the University of Richmond job board."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


NAME = "richmond-u"
URL = "https://richmond.wd5.myworkdayjobs.com/staff_faculty"


async def main():
    """Scrapes the University of Richmond job board."""
    # Initialize logger
    logger = get_logger("richmond_u")

    logger.info("Starting University of Richmond Scraper")
    logger.add_breadcrumb("Processing University of Richmond job board")

    try:
        await scrape_site(
            URL, NAME, '[data-automation-id="jobTitle"]',
            '[data-uxi-widget-type="stepToNextButton"]:not([disabled])',
            '[data-uxi-widget-type="stepToNextButton"][disabled]',
            logger=logger
        )
        logger.increment_stat("sites_processed")
    except Exception as e:
        logger.error(f"Failed to scrape University of Richmond: {str(e)}")
        logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info("Completed University of Richmond job board scraping")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
