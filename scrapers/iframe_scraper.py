"""
Iframe scraper for job boards that use iframes.

This scraper handles sites like iCIMS that embed their job listings
within an iframe element.
"""

from typing import List, Optional

from playwright.async_api import Frame

from scrapers.base_scraper import BaseScraper


class IframeScraper(BaseScraper):
    """
    Scraper for job boards that use iframes (e.g., iCIMS).

    This scraper switches to an iframe context before scraping
    and handles pagination within the iframe.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.frame: Optional[Frame] = None

    async def navigate_to_start_page(self) -> bool:
        """
        Navigate to start page and switch to iframe context.

        Returns:
            True if navigation and iframe switch succeeded, False otherwise
        """
        # First, navigate to the page
        success = await super().navigate_to_start_page()
        if not success:
            return False

        # Now find and switch to the iframe
        iframe_selector = self.selectors.get('iframe')
        if not iframe_selector:
            self.logger.error("No iframe selector configured")
            return False

        try:
            self.logger.debug(f"Looking for iframe: {iframe_selector}")
            iframe = await self.page.wait_for_selector(iframe_selector)
            self.frame = await iframe.content_frame()

            if not self.frame:
                self.logger.error("Failed to get iframe content frame")
                return False

            self.logger.info("Successfully switched to iframe")
            return True

        except Exception as e:
            self.logger.error(f"Error switching to iframe: {str(e)}")
            return False

    async def extract_job_links(self) -> List[str]:
        """
        Extract job links from the iframe using configured selector and filter.

        Returns:
            List of job URLs
        """
        if not self.frame:
            self.logger.error("Frame not initialized")
            return []

        job_link_selector = self.selectors.get('job_link')
        job_link_filter = self.selectors.get('job_link_filter', '')

        if not job_link_selector:
            self.logger.error("No job_link selector configured")
            return []

        try:
            # Wait for job links to be visible
            await self.frame.wait_for_selector(job_link_selector, state='visible')

            # Extract links with optional filtering
            if job_link_filter:
                # Use custom filter function
                job_links = await self.frame.evaluate(f'''() => {{
                    const elements = document.querySelectorAll('{job_link_selector}');
                    const filterFn = {job_link_filter};
                    return Array.from(elements)
                        .filter(filterFn)
                        .map(a => a.href);
                }}''')
            else:
                # Simple extraction
                job_links = await self.frame.evaluate(f'''() => {{
                    const elements = document.querySelectorAll('{job_link_selector}');
                    return Array.from(elements).map(el => el.href);
                }}''')

            self.logger.debug(f"Extracted {len(job_links)} job links from iframe")
            return job_links

        except Exception as e:
            self.logger.error(f"Error extracting job links from iframe: {str(e)}")
            return []

    async def navigate_to_next_page(self) -> bool:
        """
        Navigate to the next page within the iframe.

        Returns:
            True if successfully navigated to next page, False if no more pages
        """
        if not self.frame:
            self.logger.error("Frame not initialized")
            return False

        next_page_selector = self.selectors.get('next_page')
        if not next_page_selector:
            self.logger.debug("No pagination configured for this site")
            return False

        # Find next button
        next_button = await self.frame.query_selector(next_page_selector)
        if not next_button:
            self.logger.info("No more next button found")
            return False

        # Check if disabled using custom check function
        disabled_check = self.selectors.get('next_page_disabled_check')
        if disabled_check:
            try:
                is_disabled = await next_button.evaluate(f'''(el) => {{
                    const checkFn = {disabled_check};
                    return checkFn(el);
                }}''')

                if is_disabled:
                    self.logger.info("Reached last page - next button is disabled")
                    return False

            except Exception as e:
                self.logger.warning(f"Error checking if next button is disabled: {str(e)}")

        # Click next button
        try:
            await next_button.click()
            await self.frame.wait_for_load_state('networkidle')
            await self.frame.wait_for_selector(self.selectors.get('job_link'), state='visible')
            self.logger.debug("Successfully navigated to next page in iframe")
            return True

        except Exception as e:
            self.logger.error(f"Error clicking next button in iframe: {str(e)}")
            return False
