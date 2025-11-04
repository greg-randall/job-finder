"""This module scrapes job postings from Dayforce job boards."""

import asyncio

from functions import scrape_site


JOBS = [
    "https://us242.dayforcehcm.com/CandidatePortal/en-US/lumos",
    "https://us242.dayforcehcm.com/CandidatePortal/en-us/omega",
    "https://us59.dayforcehcm.com/CandidatePortal/en-US/leeenterprises/SITE/CANDIDATEPORTAL",
    "https://www.dayforcehcm.com/CandidatePortal/en-US/southu/",
]


async def main():
    """Scrapes all Dayforce job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} Dayforce job boards")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1]
        print(f"\n🔄 Processing site {index}/{total_sites}: {name}")
        await scrape_site(
            url, name, ".posting-title a",
            'a[aria-label="Next Page"]',
            'a[aria-label="Next Page"][aria-disabled="true"]'
        )

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
