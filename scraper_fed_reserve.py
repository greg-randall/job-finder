"""This module scrapes job postings from the Federal Reserve job board."""

import asyncio

from functions import scrape_site


NAME = "fed-reserve"
URL = "https://rb.wd5.myworkdayjobs.com/FRS?locations=fd925bdfc7240167c220be442401af07"


async def main():
    """Scrapes the Federal Reserve job board."""
    await scrape_site(
        URL, NAME, '[data-automation-id="jobTitle"]',
        '[data-uxi-widget-type="stepToNextButton"]:not([disabled])',
        '[data-uxi-widget-type="stepToNextButton"][disabled]'
    )


if __name__ == "__main__":
    asyncio.run(main())
