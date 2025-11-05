"""This module scrapes job postings from CSOD job boards."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


JOBS = [
    "https://vcu.csod.com/ux/ats/careersite/1/home?c=vcu",
    "https://unoslearn.csod.com/ux/ats/careersite/1/home?c=unoslearn#/"
]


async def main():
    """Scrapes all CSOD job boards."""
    # Initialize logger
    logger = get_logger("csod")
    total_sites = len(JOBS)

    logger.info(f"Starting CSOD Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1].lower()
        logger.info(f"Site {index}/{total_sites}: {name}")
        logger.add_breadcrumb(f"Processing {name} ({index}/{total_sites})")

        try:
            await scrape_site(
                url, name, '[data-tag="displayJobTitle"]',
                'button.page-nav-caret.next:not([disabled])',
                'button.page-nav-caret.next[disabled]',
                logger=logger
            )
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape {name}: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info(f"Completed all {total_sites} CSOD job boards")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
