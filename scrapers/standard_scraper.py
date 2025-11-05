"""
Standard scraper for job boards with traditional pagination.

This scraper handles sites like Workday, ApplicantPro, and similar
boards that use standard pagination with next/previous buttons.
"""

from typing import List

from functions import wait_for_load
from scrapers.base_scraper import BaseScraper


class StandardScraper(BaseScraper):
    """
    Scraper for job boards with standard pagination.

    Supports sites that have:
    - A selector for job links
    - Optional next page button
    - Optional disabled next page button selector
    """

    async def extract_job_links(self) -> List[str]:
        """
        Extract job links from the current page using configured selector.

        Returns:
            List of job URLs
        """
        job_link_selector = self.selectors.get('job_link')
        if not job_link_selector:
            self.logger.error("No job_link selector configured")
            return []

        try:
            links = await self.page.evaluate(f'''() => {{
                const elements = document.querySelectorAll('{job_link_selector}');
                return Array.from(elements).map(el => el.href).filter(href => href);
            }}''')

            self.logger.debug(f"Extracted {len(links)} job links using selector: {job_link_selector}")

            if not links:
                # Selector didn't match anything - capture error context
                await self.logger.capture_error_context(
                    error_type="SelectorError",
                    error_message=f"Job link selector '{job_link_selector}' returned no results",
                    url=self.page.url,
                    page=self.page,
                    context={
                        "selector": job_link_selector,
                        "page_url": self.page.url,
                        "selector_type": "job_links"
                    }
                )

            return links

        except Exception as e:
            self.logger.error(f"Error extracting job links: {str(e)}")
            await self.logger.capture_error_context(
                error_type="SelectorError",
                error_message=f"Failed to extract job links with selector '{job_link_selector}'",
                url=self.page.url,
                page=self.page,
                stack_trace=str(e),
                context={
                    "selector": job_link_selector,
                    "error": str(e)
                }
            )
            return []

    async def navigate_to_next_page(self) -> bool:
        """
        Navigate to the next page using configured selectors.

        Returns:
            True if successfully navigated to next page, False if no more pages
        """
        next_page_selector = self.selectors.get('next_page')
        next_page_disabled_selector = self.selectors.get('next_page_disabled')

        # If no pagination is configured, return False (single page site)
        if not next_page_selector:
            self.logger.debug("No pagination configured for this site")
            return False

        # Check if on last page (disabled button)
        if next_page_disabled_selector:
            next_button_disabled = await self.page.query_selector(next_page_disabled_selector)
            if next_button_disabled:
                self.logger.info("Reached last page - next button is disabled")
                return False

        # Find and click next button
        next_button = await self.page.query_selector(next_page_selector)
        if not next_button:
            self.logger.info("No more next button found")
            return False

        try:
            await next_button.click()
            await wait_for_load(self.page)
            self.logger.debug("Successfully navigated to next page")
            return True

        except Exception as e:
            self.logger.error(f"Error clicking next button: {str(e)}")
            return False
