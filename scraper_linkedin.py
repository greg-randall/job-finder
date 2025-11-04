"This module scrapes job postings from LinkedIn."

import asyncio
import random
import time
from urllib.parse import quote

from bs4 import BeautifulSoup
from pyppeteer import launch
from pyppeteer_stealth import stealth
from termcolor import cprint

from functions import download_all_links, init_browser


def rand_sleep():
    """Returns a random float between 0.1 and 0.3."""
    return random.uniform(0.1, 0.3)


def get_linkedin_search(url):
    """Gets the raw HTML of a LinkedIn search results page."""
    async def get_feed_raw():
        browser = await launch(headless=False)
        page = await browser.newPage()
        await page.setViewport({"width": 1024, "height": 768})
        await stealth(page)
        await page.goto(url)

        if len(await page.content()) < 100:
            cprint("ERROR: the linkedin page didn't load", "magenta")
            return 0

        no_results_texts = ["No matching jobs found.", "Please make sure your keywords are spelled correctly"]
        for no_results_text in no_results_texts:
            is_text_visible = await page.evaluate(f'''() => {{
                return document.body.innerText.includes("{no_results_text}");
            }}''')
            if is_text_visible:
                return 0

        last_height = 0
        scroll_attempts = 0
        max_attempts = 30
        jobs_found = 0

        while scroll_attempts < max_attempts:
            current_height = await page.evaluate('document.body.scrollHeight')

            if current_height == last_height:
                scroll_attempts += 1
                if scroll_attempts >= 3:
                    break
            else:
                scroll_attempts = 0

            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await asyncio.sleep(2)

            end_messages = [
                "You've viewed all jobs for this search",
                "No more results to show"
            ]
            for msg in end_messages:
                is_end = await page.evaluate(f'document.body.innerText.includes("{msg}")')
                if is_end:
                    print("Reached end of job listings")
                    scroll_attempts = max_attempts
                    break

            current_jobs = await page.evaluate('''
                () => document.querySelectorAll('div[data-entity-urn*="jobPosting:"]').length
            ''')

            if current_jobs > jobs_found:
                jobs_found = current_jobs
                print(f"      Found {jobs_found} jobs so far...")

            last_height = current_height

        feed_raw = await page.content()
        await browser.close()
        return feed_raw

    try:
        feed_raw = asyncio.get_event_loop().run_until_complete(
            get_feed_raw()
        )
    except Exception:
        cprint("ERROR: get_feed_raw failed", "magenta")
        return False

    if len(str(feed_raw)) > 100:
        soup = BeautifulSoup(feed_raw, "html.parser")
        divs = soup.find_all("div", attrs={"data-entity-urn": True})

        jobs = []
        for div in divs:
            job_id = div["data-entity-urn"].split(":")[-1]
            jobs.append(f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}")
        print(f"      Found    {len(jobs)} jobs on linkedin")

        if not jobs:
            return 0
        return jobs

    cprint("ERROR: get_feed_raw seemed to work, but didn't return full results", "magenta")
    print(f"feed_raw: {feed_raw}")
    return False


LINKEDIN_BASE_URL = "https://www.linkedin.com/jobs/search/?f_WT=1%2C3&geoId=102114334&keywords="

SEARCH_WORDS = ["Web Developer",
                "Frontend Developer",
                "Backend Developer",
                "Full Stack Developer",
                "WordPress Developer",
                "Digital Content Manager",
                "Technical Content Manager",
                "Web Content Specialist",
                "Digital Communications Manager",
                "UI Developer",
                "Web Production Manager",
                "University Web Developer",
                "Media Specialist",
                "Digital Media Coordinator",
                "Technical Support Specialist",
                "Systems Administrator",
                "IT Support Manager",
                "Website Manager",
                "Digital Asset Manager",
                "Creative Technologist",
                "SEO Specialist",
                "Accessibility Specialist",
                "Photography Director",
                "Video Production Manager",
                "Digital Content Producer",
                "CMS Developer",
                "API Developer",
                "AI Integration Developer",
                "Technical Documentation Specialist",
                "Website Optimization Specialist",
                "Digital Education Specialist",
                "Learning Technology Specialist",
                "Digital Communications Specialist",
                "User Experience Developer",
                "Web Accessibility Engineer"]

if __name__ == "__main__":
    browser_page = asyncio.get_event_loop().run_until_complete(init_browser(headless=False))

    try:
        count = 1
        for search_term in SEARCH_WORDS:
            print(f"\nSearching for: {search_term}")
            print(f"{count}/{len(SEARCH_WORDS)}")
            count += 1

            search_url = LINKEDIN_BASE_URL + quote(search_term)
            print(f"URL: {search_url}")

            results = get_linkedin_search(search_url)
            if results:
                print(f"Found {len(results)} job listings")
                asyncio.get_event_loop().run_until_complete(
                    download_all_links(results, browser_page, 'linkedin', 5)
                )
                for job in results[:5]:
                    print(f"Job URL: {job}")
            else:
                print("No results found or an error occurred")

            sleep_time = random.uniform(15, 60)
            print(f"\nWaiting {sleep_time:.1f} seconds before next search...")
            time.sleep(sleep_time)

    finally:
        asyncio.get_event_loop().run_until_complete(browser_page.close())
