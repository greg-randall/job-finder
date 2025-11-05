"""
URL pagination scraper for job boards that use URL parameters for pagination.

This scraper handles sites like CareerPlug that paginate by modifying
the URL (e.g., adding ?page=2, ?page=3, etc.).
"""

import random
from typing import List

from functions import navigate_with_retries
from scrapers.base_scraper import BaseScraper


class URLPaginationScraper(BaseScraper):
    """
    Scraper for job boards that use URL-based pagination.

    Instead of clicking next buttons, this scraper constructs
    URLs with page parameters (e.g., ?page=1, ?page=2, etc.)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.current_page_num = self.settings.get('start_page', 1)

    async def extract_job_links(self) -> List[str]:
        """
        Extract job links from a job table or container.

        Returns:
            List of job URLs
        """
        job_table_selector = self.selectors.get('job_table')
        job_link_selector = self.selectors.get('job_link', 'a')

        if not job_table_selector:
            self.logger.error("No job_table selector configured")
            return []

        try:
            # Extract all links from the job table
            job_links = await self.tab.evaluate(f'''() => {{
                const jobTable = document.querySelector('{job_table_selector}');
                if (!jobTable) return [];
                const links = jobTable.querySelectorAll('{job_link_selector}');
                return Array.from(links)
                    .map(link => link.href)
                    .filter(href => href);
            }}''')

            self.logger.debug(f"Extracted {len(job_links)} job links from page {self.current_page_num}")
            return job_links

        except Exception as e:
            self.logger.error(f"Error extracting job links: {str(e)}")
            return []

    async def navigate_to_next_page(self) -> bool:
        """
        Navigate to the next page by constructing a new URL.

        Returns:
            True if successfully navigated to next page and found jobs,
            False if no jobs found (end of pagination)
        """
        # Increment page number
        self.current_page_num += 1

        # Construct next page URL
        url_pattern = self.settings.get('url_pattern', '{base_url}?page={page_num}')
        next_url = url_pattern.format(
            base_url=self.url,
            page_num=self.current_page_num
        )

        self.logger.debug(f"Navigating to page {self.current_page_num}: {next_url}")

        # Navigate to next page
        success = await navigate_with_retries(self.page, next_url, logger=self.logger)
        if not success:
            self.logger.error(f"Failed to load page {self.current_page_num}")
            return False

        # Add random wait between pages to be polite
        wait_min = self.settings.get('wait_between_pages_min', 0)
        wait_max = self.settings.get('wait_between_pages_max', 0)

        if wait_min > 0 and wait_max > 0:
            wait_time = random.uniform(wait_min, wait_max)
            self.logger.debug(f"Waiting {wait_time:.1f} seconds before next page...")
            await self.tab.wait_for_timeout(int(wait_time * 1000))

        return True

    async def scrape_all_pages(self) -> List[str]:
        """
        Override scrape_all_pages to handle URL pagination logic.

        For URL pagination, we keep going until we get an empty page.

        Returns:
            List of all collected job URLs
        """
        all_job_links: List[str] = []

        # First page (already navigated to in navigate_to_start_page)
        while True:
            self.logger.info(f"Scraping page {self.current_page_num}...")

            # Extract job links from current page
            job_links = await self.extract_job_links()

            # If no jobs found, we've reached the end
            if not job_links:
                self.logger.info(f"No jobs found on page {self.current_page_num} - reached the end")
                break

            all_job_links.extend(job_links)

            self.stats['pages_scraped'] = self.current_page_num
            self.stats['jobs_found'] = len(all_job_links)

            self.logger.info(f"Page {self.current_page_num}: Found {len(job_links)} job links")

            # Navigate to next page
            has_next = await self.navigate_to_next_page()
            if not has_next:
                break

        return all_job_links
