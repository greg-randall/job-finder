"""This module scrapes job postings from the University of Richmond job board."""

import asyncio

from functions import scrape_site


NAME = "richmond-u"
URL = "https://richmond.wd5.myworkdayjobs.com/staff_faculty"


async def main():
    """Scrapes the University of Richmond job board."""
    await scrape_site(
        URL, NAME, '[data-automation-id="jobTitle"]',
        '[data-uxi-widget-type="stepToNextButton"]:not([disabled])',
        '[data-uxi-widget-type="stepToNextButton"][disabled]'
    )


if __name__ == "__main__":
    asyncio.run(main())
