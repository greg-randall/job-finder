"""This module scrapes job postings from iSolved job boards."""

import asyncio

from functions import scrape_site


JOBS = [
    "https://ausa.isolvedhire.com/jobs/",
    "https://dominionpayroll.isolvedhire.com/jobs/",
    "https://kbjwgroup.isolvedhire.com/jobs/",
    "https://trolleyhouseva.isolvedhire.com/jobs/",
]


async def main():
    """Scrapes all iSolved job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} iSolved job boards")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1]
        print(f"\n🔄 Processing site {index}/{total_sites}: {name}")
        await scrape_site(url, name, "a.listing-url", None, None)

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
