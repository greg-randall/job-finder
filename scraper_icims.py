"""This module scrapes job postings from iCIMS job boards."""

import asyncio
import os

import aiofiles

from functions import init_browser, navigate_with_retries, download_all_links


JOBS = [
    "https://careers-audacy.icims.com/jobs/search?ss=1",
    "https://careers-chesbank.icims.com/jobs/search?ss=1",
    "https://careers-dewberry.icims.com/jobs/search?ss=1",
    "https://careers-gilbaneco.icims.com/jobs/search?ss=1",
]


async def scrape_icims_site(url):
    """Scrapes a single iCIMS job board."""
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

        screenshot_dir = 'debug_screenshots'
        html_dir = 'debug_html'
        os.makedirs(screenshot_dir, exist_ok=True)
        os.makedirs(html_dir, exist_ok=True)

        screenshot_path = os.path.join(screenshot_dir, f"{name}_page_load.png")
        await page.screenshot(path=screenshot_path, full_page=True)
        print(f"📸 Saved full page screenshot to {screenshot_path}")

        html_path = os.path.join(html_dir, f"{name}_page.html")
        html_content = await page.content()
        async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
            await f.write(html_content)
        print(f"💾 Saved page HTML to {html_path}")

        print("Looking for jobs iframe...")
        iframe = await page.wait_for_selector('iframe[id="icims_content_iframe"]')
        frame = await iframe.content_frame()
        print("✅ Switched to jobs iframe")

        all_job_links = []
        page_num = 1

        while True:
            await frame.wait_for_selector('.iCIMS_Anchor', state='visible')

            job_links = await frame.evaluate('''() => {
                const elements = document.querySelectorAll('a.iCIMS_Anchor');
                return Array.from(elements)
                    .filter(el => el.href && el.href.includes('/jobs/'))
                    .filter(el => el.querySelector('h3'))
                    .map(a => a.href);
            }''')

            all_job_links.extend(job_links)
            print(f"📄 Page {page_num}: Found {len(job_links)} job links")

            next_button = await frame.query_selector('a.iCIMS_Pagination_Bottom-next')
            if not next_button:
                print("🏁 Reached last page - no next button found")
                break

            is_disabled = await next_button.evaluate('''(el) => {
                const style = window.getComputedStyle(el);
                return el.classList.contains('disabled') ||
                       el.classList.contains('iCIMS_Pagination_Bottom-next-disabled') ||
                       style.display === "none" ||
                       style.visibility === "hidden" ||
                       !el.offsetParent ||
                       el.getAttribute('aria-disabled') === 'true';
            }''')

            if is_disabled:
                print("🏁 Reached last page - next button is disabled")
                break

            await next_button.click()
            await frame.wait_for_load_state('networkidle')
            await frame.wait_for_selector('.iCIMS_Anchor', state='visible')
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
    """Scrapes all iCIMS job boards."""
    total_sites = len(JOBS)
    print(f"\n🎯 Starting to scrape {total_sites} iCIMS job boards")

    for index, url in enumerate(JOBS, 1):
        print(f"\n🔄 Processing site {index}/{total_sites}")
        await scrape_icims_site(url)

    print("\n✨ Finished scraping all job boards!")


if __name__ == "__main__":
    asyncio.run(main())
