"""
Base scraper class providing common functionality for all scrapers.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional

from config_loader import get_config
from functions import init_browser, navigate_with_retries, download_all_links, DownloadStats, wait_for_selector
from logging_config import ScraperLogger, get_logger


class BaseScraper(ABC):
    """
    Abstract base class for all job board scrapers.

    This class provides common functionality like browser initialization,
    navigation, and job downloading. Subclasses implement specific
    scraping logic for different job board types.
    """

    def __init__(self, site_config: Dict[str, Any], logger: Optional[ScraperLogger] = None):
        """
        Initialize the scraper.

        Args:
            site_config: Site configuration dictionary containing url, name, selectors, etc.
            logger: Optional logger instance. If None, creates a new logger.
        """
        self.site_config = site_config
        self.name = site_config.get('name', 'unknown')
        self.url = site_config.get('url')
        self.enabled = site_config.get('enabled', True)

        # Extract group metadata
        self.group = site_config.get('_group', 'unknown')
        self.scraper_type = site_config.get('_type', 'standard')
        self.selectors = site_config.get('_selectors', {})
        self.settings = site_config.get('_settings', {})

        # Load global config
        self.config = get_config()

        # Logger
        self.logger = logger or get_logger(self.group)

        # Browser instances (initialized in scrape())
        self.tab = None  # nodriver Tab instance
        self.browser = None  # nodriver Browser instance

        # Statistics
        self.stats = {
            'pages_scraped': 0,
            'jobs_found': 0,
            'jobs_downloaded': 0,
            'jobs_skipped': 0,
            'errors': 0
        }

    @abstractmethod
    async def extract_job_links(self) -> List[str]:
        """
        Extract job links from the current page.

        This method must be implemented by subclasses to handle
        their specific job board structure.

        Returns:
            List of job URLs
        """
        pass

    @abstractmethod
    async def navigate_to_next_page(self) -> bool:
        """
        Navigate to the next page of results.

        This method must be implemented by subclasses to handle
        their specific pagination logic.

        Returns:
            True if successfully navigated to next page, False if no more pages
        """
        pass

    async def initialize_browser(self) -> None:
        """Initialize the browser with configured settings."""
        self.logger.debug("Initializing browser...")
        headless = self.config.get('browser.headless', True)
        self.browser = await init_browser(headless=headless)

    async def cleanup_browser(self) -> None:
        """Cleanup browser resources."""
        self.logger.debug("Cleaning up browser resources...")
        try:
            if self.browser:
                self.browser.stop()
        except Exception as e:
            self.logger.warning(f"Error during cleanup: {str(e)}")

    async def navigate_to_start_page(self) -> bool:
        """
        Navigate to the initial page of the job board.

        Returns:
            True if navigation succeeded, False otherwise
        """
        self.logger.info(f"Attempting to navigate to job board: {self.url}")

        # In nodriver, we get a tab by navigating to a URL
        try:
            self.tab = await self.browser.get(self.url)
            self.logger.info("Successfully loaded job board")

            # Wait for job links to be present after navigation
            job_link_selector = self.selectors.get('job_link')
            if job_link_selector:
                self.logger.debug(f"Waiting for initial job links: {job_link_selector}")
                await wait_for_selector(
                    self.tab,
                    job_link_selector,
                    logger=self.logger
                )

            return True
        except Exception as e:
            self.logger.error(f"Failed to load the page: {self.url}: {str(e)}")
            return False

    async def download_jobs(self, job_links: List[str]) -> DownloadStats:
        """
        Download all job postings.

        Args:
            job_links: List of job URLs to download

        Returns:
            DownloadStats object with download statistics
        """
        self.logger.info(f"Starting download of {len(job_links)} job postings...")

        sleep_time = self.settings.get('sleep_between_jobs', 0)
        stats = await download_all_links(
            job_links,
            self.tab,
            self.name,
            sleep=sleep_time,
            logger=self.logger
        )

        self.stats['jobs_downloaded'] = stats.processed
        self.stats['jobs_skipped'] = stats.total_skipped
        self.stats['errors'] = stats.errors

        return stats

    async def scrape_all_pages(self) -> List[str]:
        """
        Scrape all pages and collect job links.

        This method implements the main pagination loop.
        Subclasses can override this for custom behavior.

        Returns:
            List of all collected job URLs
        """
        all_job_links: List[str] = []
        page_num = 1

        while True:
            self.logger.info(f"Scraping page {page_num}...")

            # Extract job links from current page
            job_links = await self.extract_job_links()
            all_job_links.extend(job_links)

            self.stats['pages_scraped'] = page_num
            self.stats['jobs_found'] = len(all_job_links)

            self.logger.info(f"Page {page_num}: Found {len(job_links)} job links")

            # Try to navigate to next page
            has_next = await self.navigate_to_next_page()
            if not has_next:
                self.logger.info("Reached last page")
                break

            page_num += 1

        return all_job_links

    async def scrape(self) -> Dict[str, Any]:
        """
        Main scraping method that orchestrates the entire scraping process.

        This is the primary entry point for scraping a site.

        Returns:
            Dictionary with scraping statistics and results
        """
        if not self.enabled:
            self.logger.info(f"Scraper for {self.name} is disabled, skipping...")
            return {'success': False, 'reason': 'disabled'}

        self.logger.info(f"Starting to scrape: {self.name}")
        self.logger.info(f"URL: {self.url}")
        self.logger.add_breadcrumb(f"Started scraping {self.name}")

        try:
            # Initialize browser
            await self.initialize_browser()

            # Navigate to start page
            success = await self.navigate_to_start_page()
            if not success:
                return {
                    'success': False,
                    'reason': 'navigation_failed',
                    'stats': self.stats
                }

            # Scrape all pages
            all_job_links = await self.scrape_all_pages()

            # Log summary
            self.logger.info(f"Summary for {self.name}:")
            self.logger.info(f"  - Pages scraped: {self.stats['pages_scraped']}")
            self.logger.info(f"  - Job links found: {self.stats['jobs_found']}")

            self.logger.increment_stat("total_jobs_found", self.stats['jobs_found'])

            # Download all jobs
            download_stats = await self.download_jobs(all_job_links)

            return {
                'success': True,
                'stats': self.stats,
                'download_stats': {
                    'processed': download_stats.processed,
                    'skipped': download_stats.total_skipped,
                    'errors': download_stats.errors
                }
            }

        except Exception as e:
            self.logger.error(f"Error processing {self.url}: {str(e)}")
            self.stats['errors'] += 1

            # Try to capture error context with tab if available
            try:
                if self.tab:
                    import traceback
                    current_url = await self.tab.evaluate('window.location.href')
                    await self.logger.capture_error_context(
                        error_type=type(e).__name__,
                        error_message=str(e),
                        url=current_url,
                        page=self.tab,
                        stack_trace=traceback.format_exc()
                    )
            except Exception as context_error:
                # If context capture fails (e.g., browser already closed), just log it
                self.logger.warning(f"Could not capture error context: {str(context_error)}")

            return {
                'success': False,
                'reason': str(e),
                'stats': self.stats
            }

        finally:
            # Always cleanup browser resources
            await self.cleanup_browser()

    def __repr__(self) -> str:
        """String representation of the scraper."""
        return f"{self.__class__.__name__}(name='{self.name}', type='{self.scraper_type}')"
