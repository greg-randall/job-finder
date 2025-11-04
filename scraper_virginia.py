"""This module scrapes job postings from the Virginia state job board."""

import asyncio

from functions import init_browser, navigate_with_retries, handle_cookie_consent, wait_for_load, download_all_links


NAME = "virginia"
URL = "https://www.jobs.virginia.gov/jobs/search?page=1&cities%5B%5D=Richmond&query="


async def main():
    """Scrapes the Virginia state job board."""
    page = await init_browser(headless=True)

    success = await navigate_with_retries(page, URL)
    if not success:
        print("Failed to load the page")
        return

    await handle_cookie_consent(page, "consent-modal")
    await page.wait_for_timeout(1000)

    all_job_links = set()
    page_num = 1

    while True:
        job_links = await page.evaluate('''() => {
            const elements = document.querySelectorAll('.job-search-results-title a');
            return Array.from(elements).map(el => el.href);
        }''')

        all_job_links.update(job_links)
        print(f"Page {page_num}: Found {len(job_links)} job links")

        next_button = await page.query_selector('li.next.next_page a')
        if not next_button:
            print("No more next button found")
            break

        next_url = await next_button.get_attribute('href')
        if not next_url:
            print("Could not get next page URL")
            break

        next_url = 'https://www.jobs.virginia.gov' + next_url
        success = await navigate_with_retries(page, next_url)
        if not success:
            print("Failed to load next page")
            break

        await wait_for_load(page)
        page_num += 1

    print(f"\nTotal unique job links found across {page_num} pages: {len(all_job_links)}")

    all_job_links_list = list(all_job_links)

    print("\nStarting download of job postings...")
    await download_all_links(all_job_links_list, page, NAME)

    await page.context.close()


if __name__ == "__main__":
    asyncio.run(main())
