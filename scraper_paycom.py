"""This module scrapes job postings from Paycom job boards."""

import asyncio

from functions import scrape_site


JOBS = [
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=3099D1521CBC547FA90B2DC8F8E16CE0&fromClientSide=true",
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=41D59970DD02B89289BC377057FA14AB",
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=895769C58B52D9DF59B67A02D35CF4C9",
    "https://www.paycomonline.net/v4/ats/web.php/jobs?clientkey=F82F5302A4516E0D2AFE5A9E45200B62",
]


async def main():
    """Scrapes all Paycom job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} Paycom job boards")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1]
        print(f"\n🔄 Processing site {index}/{total_sites}: {name}")
        await scrape_site(
            url, name, ".JobListing__container",
            ".js-pagination-link-next",
            ".js-pagination-link-next[aria-disabled=\"true\"]"
        )

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
