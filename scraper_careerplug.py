"""This module scrapes job postings from CareerPlug job boards."""

import asyncio
import random

from functions import init_browser, navigate_with_retries, download_all_links


JOBS = [
    "https://call-federal-credit-union.careerplug.com/jobs",
    "https://the-goddard-school-careers.careerplug.com/jobs",
]


async def scrape_careerplug_site(url):
    """Scrapes a single CareerPlug job board."""
    name = url.split('.')[0].split('//')[1]

    print(f"\n{'='*80}")
    print(f"Starting to scrape: {name}")
    print(f"URL: {url}")
    print(f"{'='*80}\n")

    print("Initializing browser...")
    page = await init_browser(headless=True)

    try:
        print("Attempting to navigate to job board...")
        success = await navigate_with_retries(page, url)
        if not success:
            print(f"❌ Failed to load the page: {url}")
            return
        print("✅ Successfully loaded job board")

        all_job_links = []
        page_num = 1

        while True:
            current_url = f"{url}?page={page_num}"

            success = await navigate_with_retries(page, current_url)
            if not success:
                print(f"❌ Failed to load page {page_num}")
                break

            job_links = await page.evaluate('''() => {
                const jobTable = document.getElementById('job_table');
                if (!jobTable) return [];
                const links = jobTable.getElementsByTagName('a');
                return Array.from(links)
                    .map(link => link.href)
                    .filter(href => href);
            }''')

            if not job_links:
                print("🏁 No jobs found on this page - reached the end")
                break

            all_job_links.extend(job_links)
            print(f"📄 Page {page_num}: Found {len(job_links)} job links\n\t{current_url}")

            wait_time = random.uniform(3, 9)
            print(f"Waiting {wait_time:.1f} seconds before next page...")
            await page.wait_for_timeout(wait_time * 1000)

            page_num += 1

        print(f"\n📊 Summary for {name}:")
        print(f"- Total pages scraped: {page_num}")
        print(f"- Total job links found: {len(all_job_links)}")

        print("\n⬇️ Starting download of job postings...")
        await download_all_links(all_job_links, page, name)

    except Exception as e:
        print(f"❌ Error processing {url}: {str(e)}")

    finally:
        print("🧹 Cleaning up browser resources...")
        await page.context.close()
        print(f"\n{'='*80}")


async def main():
    """Scrapes all CareerPlug job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} CareerPlug job boards")

    for index, url in enumerate(JOBS, 1):
        print(f"\n🔄 Processing site {index}/{total_sites}")
        await scrape_careerplug_site(url)

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
