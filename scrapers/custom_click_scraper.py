"""
Custom click-through scraper for ADP and similar job boards.

This scraper handles sites where job content must be accessed by clicking
through individual job buttons rather than navigating to separate URLs.
"""

import asyncio
import hashlib
import os
from pathlib import Path
from typing import List

import aiofiles
import trafilatura

from functions import wait_for_load
from scrapers.base_scraper import BaseScraper


class CustomClickScraper(BaseScraper):
    """
    Scraper for job boards that require clicking through individual jobs.

    This is used for sites like ADP where:
    1. Jobs are listed as buttons/elements on a page
    2. Clicking opens the job details inline
    3. Content must be scraped before clicking back
    4. Process repeats for each job
    """

    async def extract_job_links(self) -> List[str]:
        """
        For click-through scrapers, we don't extract links.
        This method is not used in the standard workflow.

        Returns:
            Empty list
        """
        return []

    async def navigate_to_next_page(self) -> bool:
        """
        For click-through scrapers, pagination is handled differently.
        This returns False to indicate single-page processing.

        Returns:
            False (no pagination)
        """
        return False

    async def click_view_all_button(self) -> bool:
        """
        Click the "View All" button if present.

        Returns:
            True if button was clicked (or didn't exist), False on error
        """
        view_all_selector = self.selectors.get('view_all_button')
        if not view_all_selector:
            return True  # No button configured, continue

        try:
            self.logger.debug("Looking for 'View all' button...")
            # In nodriver, we use select to find elements
            view_all_button = await self.tab.select(view_all_selector)

            if view_all_button:
                self.logger.info("Found 'View all' button, clicking...")
                await view_all_button.click()
                await wait_for_load(self.tab)
                self.logger.info("Clicked 'View all' button")

            return True

        except Exception as e:
            self.logger.warning(f"No 'View all' button found or error clicking it: {str(e)}")
            return True  # Continue even if button not found

    async def scrape_all_pages(self) -> List[str]:
        """
        Override to handle click-through scraping instead of pagination.

        For ADP-style sites, we:
        1. Click "View All" if needed
        2. Get all job buttons
        3. Click each button to view details
        4. Save the job content
        5. Click back
        6. Repeat

        Returns:
            List of processed job URLs (constructed URLs)
        """
        # Click view all button if configured
        await self.click_view_all_button()

        self.logger.info("Processing job listings...")

        # Get cache directory
        cache_dir = Path(self.config.get('paths.cache_dir', 'cache'))
        cache_dir.mkdir(exist_ok=True)

        # Track processing
        processed_count = 0
        consecutive_errors = 0
        max_consecutive_errors = self.settings.get('max_consecutive_errors', 8)
        processed_jobs = set()

        # Get all job buttons
        job_button_selector = self.selectors.get('job_button')
        if not job_button_selector:
            self.logger.error("No job_button selector configured")
            return []

        job_buttons = await self.tab.select_all(job_button_selector)

        if not job_buttons:
            self.logger.error("No job buttons found")
            await self.logger.capture_error_context(
                error_type="SelectorError",
                error_message=f"No job buttons found with selector '{job_button_selector}'",
                url=self.url,
                page=self.tab,
                context={
                    "selector": job_button_selector,
                    "selector_type": "job_buttons"
                }
            )
            return []

        self.logger.info(f"Found {len(job_buttons)} job buttons")

        # Collect button IDs for iteration
        button_ids = []
        for button in job_buttons:
            button_id = button.attrs.get('id')
            if button_id:
                button_ids.append(button_id)

        # Process each job
        for button_id in button_ids:
            button = await self.tab.select(f'[id="{button_id}"]')
            if not button:
                self.logger.warning(f"Could not find button with ID {button_id}, skipping...")
                continue

            try:
                # Extract job info
                job_id = button_id.split('_')[1] if '_' in button_id else button_id
                # Get aria-label from element attributes (synchronous in nodriver)
                job_title_attr = button.attrs.get('aria-label')
                job_title = job_title_attr or f"Job {job_id}"

                # Check if already processed in this session
                if job_id in processed_jobs:
                    self.logger.debug(f"Already processed in this session: {job_title}")
                    continue

                # Construct job URL
                base_url = await self.tab.evaluate('window.location.href.split("?")[0]')
                cid = await self.tab.evaluate('new URLSearchParams(window.location.search).get("cid")')
                job_url = f"{base_url}?cid={cid}&jobId={job_id}&source=CareerSite"

                # Check if already cached
                filename = f"{self.name}_{hashlib.sha256(job_url.encode()).hexdigest()}.txt"
                filepath = cache_dir / filename

                if filepath.exists():
                    self.logger.debug(f"Skipping already cached: {job_title}")
                    continue

                # Click the job to open details
                container_selector = self.selectors.get('container')
                if container_selector:
                    await self.tab.evaluate(f'''() => {{
                        const container = document.querySelector('{container_selector}');
                        if (container) {{
                            const button = container.querySelector('sdf-button');
                            if (button) {{
                                button.click();
                            }}
                        }}
                    }}''')
                else:
                    await button.click()

                await wait_for_load(self.tab)

                # Extract content
                content = await self.tab.get_content()
                extracted_text = trafilatura.extract(content, favor_recall=True)

                if extracted_text:
                    async with aiofiles.open(filepath, 'w', encoding='utf-8') as f:
                        await f.write(f"{job_url}\n\n{extracted_text}")

                    processed_count += 1
                    processed_jobs.add(job_id)
                    self.logger.info(f"Processed {processed_count}: {job_title}")

                    # Click back button
                    if self.settings.get('click_back_after_job', True):
                        back_button_selector = self.selectors.get('back_button')
                        if back_button_selector:
                            await self.tab.evaluate(f"document.querySelector('{back_button_selector}').click();")
                            await wait_for_load(self.tab)

                            # Click view all again if configured
                            if self.settings.get('click_view_all_after_back', True):
                                await self.click_view_all_button()

                    consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                wait_time = 2 ** consecutive_errors
                self.logger.error(f"Error processing job {button_id}: {str(e)}")
                self.logger.warning(f"Consecutive errors: {consecutive_errors}")

                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error(f"Exiting after {consecutive_errors} consecutive errors")
                    break

                self.logger.info(f"Waiting {wait_time} seconds before next attempt...")
                await asyncio.sleep(wait_time)

                # Try to click back
                try:
                    back_button_selector = self.selectors.get('back_button')
                    if back_button_selector:
                        await self.tab.evaluate(f"document.querySelector('{back_button_selector}').click();")
                        await wait_for_load(self.tab)
                except Exception:
                    pass

        self.stats['jobs_found'] = processed_count
        self.stats['jobs_downloaded'] = processed_count
        self.logger.info(f"Processed {processed_count} jobs")

        # Return empty list since we already saved the jobs
        return []

    async def download_jobs(self, job_links: List[str]):
        """
        Override download_jobs since we already downloaded during scraping.

        Returns:
            Mock DownloadStats
        """
        from functions import DownloadStats

        self.logger.debug("Jobs already downloaded during click-through scraping")
        return DownloadStats(
            total=self.stats['jobs_found'],
            processed=self.stats['jobs_downloaded'],
            skipped_session=0,
            skipped_existing=0,
            errors=self.stats['errors']
        )
