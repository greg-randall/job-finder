"This module scrapes job postings from ADP job boards."

import asyncio
import hashlib
import os
import traceback

import aiofiles
import trafilatura

from functions import init_browser, navigate_with_retries, wait_for_load
from logging_config import get_logger


JOBS = [
    ("https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?"
     "cid=1a28f084-a840-489f-a837-e68fd3bb5078&ccId=1215116661_159&lang=en_US"),
    ("https://workforcenow.adp.com/mascsr/default/mdf/recruitment/recruitment.html?"
     "cid=3be72b98-ef48-44d6-a55f-809db03ac7bc&ccId=19000101_000001&type=MP&lang=en_US"),
]


async def scrape_adp_site(url, logger=None):
    """Scrapes a single ADP job board."""
    name = url.split('cid=')[1][:8]

    if logger:
        logger.info(f"Starting to scrape: {name}")
        logger.info(f"URL: {url}")
        logger.add_breadcrumb(f"Started scraping ADP site {name}")
    else:
        print(f"\n{'='*80}")
        print(f"Starting to scrape: {name}")
        print(f"URL: {url}")
        print(f"{'='*80}\n")

    if logger:
        logger.debug("Initializing browser...")
    else:
        print("Initializing browser...")

    page, playwright, browser = await init_browser(headless=True)

    try:
        if logger:
            logger.info("Attempting to navigate to job board...")
        else:
            print("Attempting to navigate to job board...")

        success = await navigate_with_retries(page, url, logger=logger)
        if not success:
            if logger:
                logger.error(f"Failed to load the page: {url}")
            else:
                print(f"❌ Failed to load the page: {url}")
            return

        if logger:
            logger.info("Successfully loaded job board")
        else:
            print("✅ Successfully loaded job board")

        await wait_for_load(page)

        try:
            if logger:
                logger.debug("Looking for 'View all' button...")
            else:
                print("Looking for 'View all' button...")

            view_all_button = await page.wait_for_selector('#recruitment_careerCenter_showAllJobs', timeout=5000)
            if view_all_button:
                if logger:
                    logger.info("Found 'View all' button, clicking...")
                else:
                    print("Found 'View all' button, clicking...")
                await view_all_button.click()
                await wait_for_load(page)
                if logger:
                    logger.info("Clicked 'View all' button")
                else:
                    print("✅ Clicked 'View all' button")
        except Exception as e:
            if logger:
                logger.warning(f"No 'View all' button found or error clicking it: {str(e)}")
            else:
                print("Note: No 'View all' button found or error clicking it.")

        if logger:
            logger.info("Processing job listings...")
        else:
            print("\nProcessing job listings...")

        cache_dir = 'cache'
        os.makedirs(cache_dir, exist_ok=True)

        processed_count = 0
        consecutive_errors = 0
        max_consecutive_errors = 8

        job_buttons = await page.query_selector_all('sdf-button[id^="lblTitle_"]')

        if not job_buttons:
            if logger:
                logger.error("No job buttons found - capturing error context")
                await logger.capture_error_context(
                    error_type="SelectorError",
                    error_message="No job buttons found with selector 'sdf-button[id^=\"lblTitle_\"]'",
                    url=url,
                    page=page,
                    context={
                        "selector": 'sdf-button[id^="lblTitle_"]',
                        "selector_type": "job_buttons"
                    }
                )
            else:
                print("No job buttons found")
            return

        if logger:
            logger.info(f"Found {len(job_buttons)} job buttons")
        else:
            print(f"Found {len(job_buttons)} job buttons")

        button_ids = []
        for button in job_buttons:
            button_id = await button.get_attribute('id')
            button_ids.append(button_id)

        processed_jobs = set()

        for button_id in button_ids:
            button = await page.query_selector(f'sdf-button[id="{button_id}"]')
            if not button:
                print(f"Could not find button with ID {button_id}, skipping...")
                continue

            try:
                job_id = button_id.split('_')[1]
                job_title = await button.get_attribute('aria-label')

                if job_id in processed_jobs:
                    print(f"Already processed in this session: {job_title}")
                    continue

                base_url = await page.evaluate('window.location.href.split("?")[0]')
                cid = await page.evaluate('new URLSearchParams(window.location.search).get("cid")')
                job_url = f"{base_url}?cid={cid}&jobId={job_id}&source=CareerSite"

                filename = f"{name}_{hashlib.sha256(job_url.encode()).hexdigest()}.txt"
                filepath = os.path.join(cache_dir, filename)

                if os.path.exists(filepath):
                    print(f"Skipping already cached: {job_title}")
                    continue

                await page.evaluate('''() => {
                    const container = document.querySelector('.current-openings-details');
                    if (container) {
                        const button = container.querySelector('sdf-button');
                        if (button) {
                            button.click();
                        } else {
                            console.log('Button not found inside container');
                        }
                    } else {
                        console.log('Container not found');
                    }
                }''')
                await wait_for_load(page)

                content = await page.content()
                extracted_text = trafilatura.extract(content, favor_recall=True)

                if extracted_text:
                    async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                        await f.write(f"{job_url}\n\n{extracted_text}")

                    processed_count += 1
                    processed_jobs.add(job_id)
                    print(f"Processed {processed_count}: {job_title}")

                    await page.evaluate("document.getElementById('recruitment_jobDescription_back').click();")
                    await wait_for_load(page)

                    try:
                        view_all_button = await page.wait_for_selector(
                            '#recruitment_careerCenter_showAllJobs', timeout=5000
                        )
                        if view_all_button:
                            await view_all_button.click()
                            await wait_for_load(page)
                    except TimeoutError:
                        print("Note: Error clicking 'View all' button after back.")

                    consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                wait_time = 2 ** consecutive_errors
                print(f"Error processing job {job_title}: {str(e)}")
                print(f"Consecutive errors: {consecutive_errors}")

                if consecutive_errors >= max_consecutive_errors:
                    print(f"Exiting after {consecutive_errors} consecutive errors")
                    return

                print(f"Waiting {wait_time} seconds before next attempt...")
                await asyncio.sleep(wait_time)

                try:
                    await page.evaluate("document.getElementById('recruitment_jobDescription_back').click();")
                    await wait_for_load(page)
                except Exception:
                    pass

        if logger:
            logger.info(f"Progress: Jobs processed: {processed_count}")
            logger.increment_stat("total_jobs_found", processed_count)
        else:
            print("\n📊 Progress:")
            print(f"- Jobs processed so far: {processed_count}")

    except Exception as e:
        if logger:
            logger.error(f"Error in main processing loop: {str(e)}")
        else:
            print(f"Error in main processing loop: {str(e)}")

    finally:
        if logger:
            logger.debug("Cleaning up browser resources...")
        else:
            print("🧹 Cleaning up browser resources...")

        try:
            await page.context.close()
            await browser.close()
            await playwright.stop()
        except Exception as e:
            if logger:
                logger.warning(f"Error during cleanup: {str(e)}")

        if not logger:
            print(f"\n{'='*80}")


async def main():
    """Scrapes all ADP job boards."""
    # Initialize logger
    logger = get_logger("adp")
    total_sites = len(JOBS)

    logger.info(f"Starting ADP Scraper ({total_sites} sites)")

    for index, url in enumerate(JOBS, 1):
        logger.info(f"Processing site {index}/{total_sites}")
        logger.add_breadcrumb(f"Processing ADP site {index}/{total_sites}")

        try:
            await scrape_adp_site(url, logger)
            logger.increment_stat("sites_processed")
        except Exception as e:
            logger.error(f"Failed to scrape ADP site: {str(e)}")
            logger.increment_stat("sites_failed")

    # Write summary
    summary_path = logger.write_summary()
    logger.info(f"Completed all {total_sites} ADP job boards")
    logger.info(f"Summary saved to: {summary_path}")


if __name__ == "__main__":
    asyncio.run(main())
