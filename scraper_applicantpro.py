"""This module scrapes job postings from ApplicantPro job boards."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


JOBS = [
    "https://cobbtechnologies.applicantpro.com/jobs/",
    "https://thalhimer.applicantpro.com/jobs/",
    "https://ymcarichmond.applicantpro.com/jobs/",
]


async def main():
    """Scrapes all ApplicantPro job boards."""
    # Initialize logger
    logger = get_logger("applicantpro")
    total_sites = len(JOBS)

    logger.info(f"Starting ApplicantPro Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        name = url.split('/')[2].split('.')[0]
        logger.info(f"Site {index}/{total_sites}: {name}")
        logger.add_breadcrumb(f"Processing {name} ({index}/{total_sites})")

        try:
            await scrape_site(url, name, ".listing-url", None, None, logger=logger)
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape {name}: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info(f"Completed all {total_sites} ApplicantPro job boards")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
