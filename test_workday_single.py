"""Diagnostic test script for Workday scraping - tests a single site."""

import asyncio
from functions import scrape_site
from logging_config import get_logger


async def main():
    """Test scraping a single Workday site with visible browser."""
    logger = get_logger("workday_test")

    # Test URL
    url = "https://bbinsurance.wd1.myworkdayjobs.com/en-US/Careers"
    name = "bbinsurance"

    logger.info("Starting diagnostic test for Workday scraper")
    logger.info(f"Testing: {name}")
    logger.info(f"URL: {url}")
    logger.info("Running with visible browser (headless=False)")

    try:
        await scrape_site(
            url,
            name,
            '[data-automation-id="jobTitle"]',
            '[data-uxi-widget-type="stepToNextButton"]:not([disabled])',
            '[data-uxi-widget-type="stepToNextButton"][disabled]',
            headless=False,  # Run with visible browser
            logger=logger
        )
        logger.info("Test completed successfully")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise
    finally:
        duration = logger.write_summary()
        logger.info(f"Summary saved to: {duration}")


if __name__ == "__main__":
    print("="*80)
    print("WORKDAY SCRAPER DIAGNOSTIC TEST")
    print("="*80)
    print("\nThis test will:")
    print("1. Open a VISIBLE browser window (not headless)")
    print("2. Navigate to a single Workday job board")
    print("3. Wait for React app to render")
    print("4. Attempt to extract job links")
    print("\nWatch the browser window to see what happens!")
    print("="*80)
    print()

    asyncio.run(main())
