"""This module scrapes job postings from ApplicantPro job boards."""

import asyncio

from functions import scrape_site


JOBS = [
    "https://cobbtechnologies.applicantpro.com/jobs/",
    "https://thalhimer.applicantpro.com/jobs/",
    "https://ymcarichmond.applicantpro.com/jobs/",
]


async def main():
    """Scrapes all ApplicantPro job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} ApplicantPro job boards")

    for index, url in enumerate(JOBS, 1):
        name = url.split('/')[2].split('.')[0]
        print(f"\n🔄 Processing site {index}/{total_sites}: {name}")
        await scrape_site(url, name, ".listing-url", None, None)

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
