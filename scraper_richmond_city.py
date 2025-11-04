"""This module scrapes job postings from the City of Richmond job board."""

import asyncio

from functions import scrape_site


NAME = "richmond-city"
URL = "https://www.governmentjobs.com/careers/richmond"


async def main():
    """Scrapes the City of Richmond job board."""
    await scrape_site(URL, NAME, ".item-details-link", ".PagedList-skipToNext a", ".PagedList-skipToNext.disabled")


if __name__ == "__main__":
    asyncio.run(main())
