"""This module scrapes job postings from CSOD job boards."""

import asyncio

from functions import scrape_site


JOBS = [
    "https://vcu.csod.com/ux/ats/careersite/1/home?c=vcu",
    "https://unoslearn.csod.com/ux/ats/careersite/1/home?c=unoslearn#/"
]


async def main():
    """Scrapes all CSOD job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} CSOD job boards")

    for index, url in enumerate(JOBS, 1):
        name = url.split('.')[0].split('//')[1].lower()
        print(f"\n🔄 Processing site {index}/{total_sites}: {name}")
        await scrape_site(
            url, name, '[data-tag="displayJobTitle"]',
            'button.page-nav-caret.next:not([disabled])',
            'button.page-nav-caret.next[disabled]'
        )

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
