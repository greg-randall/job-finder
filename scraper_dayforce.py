"""This module scrapes job postings from Dayforce job boards."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


JOBS = [
    "https://us242.dayforcehcm.com/CandidatePortal/en-US/lumos",
    "https://us242.dayforcehcm.com/CandidatePortal/en-us/omega",
    "https://us59.dayforcehcm.com/CandidatePortal/en-US/leeenterprises/SITE/CANDIDATEPORTAL",
    "https://www.dayforcehcm.com/CandidatePortal/en-US/southu/",
]


async def main():
    """Scrapes all Dayforce job boards."""
    # Initialize logger
    logger = get_logger("dayforce")
    total_sites = len(JOBS)

    logger.info(f"Starting Dayforce Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1]
        logger.info(f"Site {index}/{total_sites}: {name}")
        logger.add_breadcrumb(f"Processing {name} ({index}/{total_sites})")

        try:
            await scrape_site(
                url, name, ".posting-title a",
                'a[aria-label="Next Page"]',
                'a[aria-label="Next Page"][aria-disabled="true"]',
                logger=logger
            )
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape {name}: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info(f"Completed all {total_sites} Dayforce job boards")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
