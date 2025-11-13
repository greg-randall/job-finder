"""
Iframe scraper for job boards that use iframes.

This scraper handles sites like iCIMS that embed their job listings
within an iframe element.
"""

from typing import List

from scrapers.base_scraper import BaseScraper


class IframeScraper(BaseScraper):
    """
    Scraper for job boards that use iframes (e.g., iCIMS).

    This scraper handles iframe content extraction and pagination.
    """

    async def navigate_to_start_page(self) -> bool:
        """
        Navigate to start page and verify iframe is present.

        Returns:
            True if navigation succeeded and iframe found, False otherwise
        """
        # First, navigate to the page
        success = await super().navigate_to_start_page()
        if not success:
            return False

        # Verify iframe is present
        iframe_selector = self.selectors.get('iframe')
        if not iframe_selector:
            self.logger.error("No iframe selector configured")
            return False

        try:
            self.logger.debug(f"Looking for iframe: {iframe_selector}")
            iframe = await self.tab.select(iframe_selector)

            if not iframe:
                self.logger.error("Failed to find iframe")
                return False

            self.logger.info("Successfully found iframe")
            return True

        except Exception as e:
            self.logger.error(f"Error finding iframe: {str(e)}")
            return False

    async def extract_job_links(self) -> List[str]:
        """
        Extract job links from the iframe using configured selector and filter.

        Returns:
            List of job URLs
        """
        iframe_selector = self.selectors.get('iframe')
        job_link_selector = self.selectors.get('job_link')
        job_link_filter = self.selectors.get('job_link_filter', '')

        if not job_link_selector:
            self.logger.error("No job_link selector configured")
            return []

        try:
            # Add a sleep to wait for the iframe to load
            self.logger.debug("Waiting 5 seconds for iframe content to load...")
            await self.tab.sleep(5)

            # Extract links from iframe using JavaScript
            if job_link_filter:
                # Use custom filter function
                job_links = await self.tab.evaluate(f'''() => {{
                    const iframe = document.querySelector('{iframe_selector}');
                    if (!iframe || !iframe.contentDocument) return null; // Return null to indicate iframe issue
                    const doc = iframe.contentDocument;
                    const elements = doc.querySelectorAll('{job_link_selector}');
                    const filterFn = {job_link_filter};
                    return Array.from(elements)
                        .filter(filterFn)
                        .map(a => a.href);
                }}''')
            else:
                # Simple extraction
                job_links = await self.tab.evaluate(f'''() => {{
                    const iframe = document.querySelector('{iframe_selector}');
                    if (!iframe || !iframe.contentDocument) return null; // Return null to indicate iframe issue
                    const doc = iframe.contentDocument;
                    const elements = doc.querySelectorAll('{job_link_selector}');
                    return Array.from(elements).map(el => el.href);
                }}''')

            if job_links is None:
                self.logger.warning("Could not find iframe or its content document.")
                return []

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
        iframe_selector = self.selectors.get('iframe')
        next_page_selector = self.selectors.get('next_page')
        if not next_page_selector:
            self.logger.debug("No pagination configured for this site")
            return False

        try:
            # Check if next button exists and click it via JavaScript
            disabled_check = self.selectors.get('next_page_disabled_check', '')

            if disabled_check:
                # Check if button is disabled using custom check
                is_disabled = await self.tab.evaluate(f'''() => {{
                    const iframe = document.querySelector('{iframe_selector}');
                    if (!iframe || !iframe.contentDocument) return true;
                    const doc = iframe.contentDocument;
                    const button = doc.querySelector('{next_page_selector}');
                    if (!button) return true;
                    const checkFn = {disabled_check};
                    return checkFn(button);
                }}''')

                if is_disabled:
                    self.logger.info("Reached last page - next button is disabled or not found")
                    return False

            # Click the next button
            clicked = await self.tab.evaluate(f'''() => {{
                const iframe = document.querySelector('{iframe_selector}');
                if (!iframe || !iframe.contentDocument) return false;
                const doc = iframe.contentDocument;
                const button = doc.querySelector('{next_page_selector}');
                if (button) {{
                    button.click();
                    return true;
                }}
                return false;
            }}''')

            if not clicked:
                self.logger.info("No more next button found")
                return False

            # Wait for page to load
            await self.tab.sleep(2)
            self.logger.debug("Successfully navigated to next page in iframe")
            return True

        except Exception as e:
            self.logger.error(f"Error clicking next button in iframe: {str(e)}")
            return False
