"""
Standard scraper for job boards with traditional pagination.

This scraper handles sites like Workday, ApplicantPro, and similar
boards that use standard pagination with next/previous buttons.
"""

from typing import List

from functions import wait_for_load, wait_for_selector
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
            # Wait for job link elements to appear before extracting
            self.logger.debug(f"Waiting for job links to load: {job_link_selector}")
            element_found = await wait_for_selector(
                self.tab,
                job_link_selector,
                logger=self.logger
            )

            if not element_found:
                self.logger.warning(f"Job link elements did not load within timeout: {job_link_selector}")
                # Continue anyway to capture error context

            # Use nodriver's native select_all method instead of evaluate
            try:
                # Get all matching elements using nodriver's native method
                elements = await self.tab.select_all(job_link_selector)
                self.logger.debug(f"select_all returned: {type(elements)}, len={len(elements) if elements else 0}")

                if elements:
                    # Get the base URL
                    base_url = await self.tab.evaluate('window.location.origin')

                    # Extract href from each element
                    links = []
                    for i, element in enumerate(elements):
                        try:
                            # Get href using direct property access
                            href = element.href
                            self.logger.debug(f"Element {i}: type={type(element)}, href={href}")
                            if href:
                                # href is already a relative URL, convert to absolute
                                if href.startswith('http'):
                                    links.append(href)
                                else:
                                    # Ensure we don't double-add slashes
                                    if href.startswith('/'):
                                        links.append(f"{base_url}{href}")
                                    else:
                                        links.append(f"{base_url}/{href}")
                        except Exception as e:
                            self.logger.debug(f"Error getting href from element {i}: {str(e)}")
                            import traceback
                            self.logger.debug(f"Traceback: {traceback.format_exc()}")
                            continue
                else:
                    self.logger.debug("select_all returned None or empty list")
                    links = []

            except Exception as extract_error:
                self.logger.error(f"Error extracting job links: {str(extract_error)}")
                links = []

            self.logger.debug(f"Extracted {len(links)} job links using selector: {job_link_selector}")

            if not links:
                # Selector didn't match anything - capture error context
                current_url = await self.tab.evaluate('window.location.href')
                await self.logger.capture_error_context(
                    error_type="SelectorError",
                    error_message=f"Job link selector '{job_link_selector}' returned no results",
                    url=current_url,
                    page=self.tab,
                    context={
                        "selector": job_link_selector,
                        "page_url": current_url,
                        "selector_type": "job_links"
                    }
                )

            return links

        except Exception as e:
            self.logger.error(f"Error extracting job links: {str(e)}")
            current_url = await self.tab.evaluate('window.location.href')
            await self.logger.capture_error_context(
                error_type="SelectorError",
                error_message=f"Failed to extract job links with selector '{job_link_selector}'",
                url=current_url,
                page=self.tab,
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
            next_button_disabled = await self.tab.select(next_page_disabled_selector)
            if next_button_disabled:
                self.logger.info("Reached last page - next button is disabled")
                return False

        # Find and click next button
        next_button = await self.tab.select(next_page_selector)
        if not next_button:
            self.logger.info("No more next button found")
            return False

        try:
            await next_button.click()
            await wait_for_load(self.tab)
            self.logger.debug("Successfully navigated to next page")
            return True

        except Exception as e:
            self.logger.error(f"Error clicking next button: {str(e)}")
            return False
