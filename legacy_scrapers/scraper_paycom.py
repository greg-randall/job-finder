"""This module scrapes job postings from Paycom job boards."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


JOBS = [
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=3099D1521CBC547FA90B2DC8F8E16CE0&fromClientSide=true",
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=41D59970DD02B89289BC377057FA14AB",
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=895769C58B52D9DF59B67A02D35CF4C9",
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=F82F5302A4516E0D2AFE5A9E45200B62",
]


async def main():
    """Scrapes all Paycom job boards."""
    # Initialize logger
    logger = get_logger("paycom")
    total_sites = len(JOBS)

    logger.info(f"Starting Paycom Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1]
        logger.info(f"Site {index}/{total_sites}: {name}")
        logger.add_breadcrumb(f"Processing {name} ({index}/{total_sites})")

        try:
            await scrape_site(
                url, name, ".JobListing__container",
                ".js-pagination-link-next",
                ".js-pagination-link-next[aria-disabled=\"true\"]",
                logger=logger
            )
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape {name}: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info(f"Completed all {total_sites} Paycom job boards")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
