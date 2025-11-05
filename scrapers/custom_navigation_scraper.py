"""
Custom navigation scraper for job boards with unique navigation patterns.

This scraper handles sites like Virginia State Jobs that have:
- Custom cookie consent handling
- URL-based navigation with unique patterns
- Set-based deduplication
"""

from typing import List, Set

from functions import handle_cookie_consent, navigate_with_retries, wait_for_load
from scrapers.base_scraper import BaseScraper


class CustomNavigationScraper(BaseScraper):
    """
    Scraper for job boards with custom navigation patterns.

    This handles sites that don't fit the standard pagination models
    but still have recognizable patterns.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.all_job_links: Set[str] = set()
        self.base_url = self.settings.get('base_url', '')

    async def navigate_to_start_page(self) -> bool:
        """
        Navigate to start page and handle cookies if configured.

        Returns:
            True if navigation succeeded, False otherwise
        """
        # Standard navigation
        success = await super().navigate_to_start_page()
        if not success:
            return False

        # Handle cookie consent if configured
        if self.settings.get('handle_cookies', False):
            cookie_modal_class = self.selectors.get('cookie_modal_class')
            if cookie_modal_class:
                self.logger.debug(f"Handling cookie consent for modal: {cookie_modal_class}")
                await handle_cookie_consent(self.page, cookie_modal_class)
                await self.page.wait_for_timeout(1000)

        return True

    async def extract_job_links(self) -> List[str]:
        """
        Extract job links from the current page.

        Returns:
            List of job URLs
        """
        job_link_selector = self.selectors.get('job_link')
        if not job_link_selector:
            self.logger.error("No job_link selector configured")
            return []

        try:
            job_links = await self.page.evaluate(f'''() => {{
                const elements = document.querySelectorAll('{job_link_selector}');
                return Array.from(elements).map(el => el.href);
            }}''')

            # Add to set for deduplication
            self.all_job_links.update(job_links)

            self.logger.debug(f"Extracted {len(job_links)} job links (total unique: {len(self.all_job_links)})")
            return job_links

        except Exception as e:
            self.logger.error(f"Error extracting job links: {str(e)}")
            return []

    async def navigate_to_next_page(self) -> bool:
        """
        Navigate to the next page using custom logic.

        For Virginia-style sites, we:
        1. Find the next page link
        2. Extract the relative URL
        3. Construct full URL
        4. Navigate to it

        Returns:
            True if successfully navigated to next page, False if no more pages
        """
        next_page_selector = self.selectors.get('next_page')
        if not next_page_selector:
            self.logger.debug("No pagination configured")
            return False

        # Find next button
        next_button = await self.page.query_selector(next_page_selector)
        if not next_button:
            self.logger.info("No more next button found")
            return False

        # Get next page URL
        next_url = await next_button.get_attribute('href')
        if not next_url:
            self.logger.info("Could not get next page URL")
            return False

        # Construct full URL if needed
        if self.base_url and not next_url.startswith('http'):
            next_url = self.base_url + next_url

        self.logger.debug(f"Navigating to next page: {next_url}")

        # Navigate to next page
        success = await navigate_with_retries(self.page, next_url, logger=self.logger)
        if not success:
            self.logger.error("Failed to load next page")
            return False

        await wait_for_load(self.page)
        return True

    async def scrape_all_pages(self) -> List[str]:
        """
        Scrape all pages and return deduplicated job links.

        Returns:
            List of unique job URLs
        """
        page_num = 1

        while True:
            self.logger.info(f"Scraping page {page_num}...")

            # Extract job links (automatically adds to self.all_job_links set)
            job_links = await self.extract_job_links()

            self.stats['pages_scraped'] = page_num
            self.stats['jobs_found'] = len(self.all_job_links)

            self.logger.info(f"Page {page_num}: Found {len(job_links)} job links on page ({len(self.all_job_links)} unique total)")

            # Try to navigate to next page
            has_next = await self.navigate_to_next_page()
            if not has_next:
                self.logger.info("Reached last page")
                break

            page_num += 1

        # Convert set to list for return
        return list(self.all_job_links)
