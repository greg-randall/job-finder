"""This module scrapes job postings from Workday job boards."""

import asyncio

from functions import scrape_site
from logging_config import get_logger


JOBS = ["https://bbinsurance.wd1.myworkdayjobs.com/en-US/Careers",
        "https://graybar.wd1.myworkdayjobs.com/Careers",
        "https://gsknch.wd3.myworkdayjobs.com/GSKCareers",
        "https://hksinc.wd5.myworkdayjobs.com/HKSCareers",
        "https://indivior.wd3.myworkdayjobs.com/Indivior",
        ("https://jdrf.wd1.myworkdayjobs.com/JDRF?"
         "_ga=2.68390741.594165681.1704744294-2139354499.1696866599&"
         "_gac=1.47826835.1703000449.EAIaIQobChMI_ufrg-ubgwMV-0tHAR39qwUqEAAYASAAEgJlRfD_BwE"),
        "https://markelcorp.wd5.myworkdayjobs.com/GlobalCareers",
        "https://nascar.wd1.myworkdayjobs.com/NASCAR",
        "https://patientfirst.wd5.myworkdayjobs.com/PatientFirst",
        "https://pgatoursuperstore.wd12.myworkdayjobs.com/PGAT_SS",
        "https://qtsdatacenters.wd5.myworkdayjobs.com/en-US/qts",
        "https://richmond.wd5.myworkdayjobs.com/staff_faculty",
        "https://sci.wd5.myworkdayjobs.com/SCI",
        "https://scripps.wd5.myworkdayjobs.com/Scripps_Careers",
        "https://sonoco.wd1.myworkdayjobs.com/en-US/CorporateCareers",
        "https://vacu.wd1.myworkdayjobs.com/VACU_Careers?jobFamilyGroup=7701a7cf554a0101b6e137cc26780000",
        "https://xylem.wd5.myworkdayjobs.com/xylem-careers"]


async def main():
    """Scrapes all Workday job boards."""
    # Initialize logger
    logger = get_logger("workday")
    total_sites = len(JOBS)

    logger.info(f"Starting Workday Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1]
        logger.info(f"Site {index}/{total_sites}: {name}")
        logger.add_breadcrumb(f"Processing {name} ({index}/{total_sites})")

        try:
            await scrape_site(
                url, name, '[data-automation-id="jobTitle"]',
                '[data-uxi-widget-type="stepToNextButton"]:not([disabled])',
                '[data-uxi-widget-type="stepToNextButton"][disabled]',
                logger=logger
            )
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape {name}: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    duration = logger.write_summary()
    logger.info(f"Completed all {total_sites} Workday job boards")
    logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    asyncio.run(main())
