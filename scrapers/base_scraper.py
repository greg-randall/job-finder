"""
Base scraper class providing common functionality for all scrapers.
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional

from config_loader import get_config
from functions import init_browser, navigate_with_retries, download_all_links, DownloadStats, wait_for_selector, generate_cache_filename
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
            'errors': 0,
            'early_stopped': False,
            'cached_on_last_page': 0,
            'new_on_last_page': 0,
            'total_pages_available': 0,
            'total_new_jobs': 0,
            'total_cached_jobs': 0
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
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self.browser.stop)
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

        This method implements the main pagination loop with smart early stopping.
        If enabled, stops when a page contains only already-cached jobs.

        Subclasses can override this for custom behavior.

        Returns:
            List of all collected job URLs
        """
        all_job_links: List[str] = []
        page_num = 1

        # Get early stopping configuration
        early_stop_enabled = self.settings.get('early_stop_on_cached', True)
        min_new_jobs = self.settings.get('min_new_jobs_per_page', 0)
        max_pages = self.settings.get('max_pages', None)

        # Track overall cache statistics
        total_new_jobs = 0
        total_cached_jobs = 0

        while True:
            self.logger.info(f"Scraping page {page_num}...")

            # Extract job links from current page
            job_links = await self.extract_job_links()
            all_job_links.extend(job_links)

            self.stats['pages_scraped'] = page_num
            self.stats['jobs_found'] = len(all_job_links)

            # Check cache status for early stopping
            if early_stop_enabled and len(job_links) > 0:
                cached_count = 0
                for job_url in job_links:
                    cache_file = generate_cache_filename(self.name, job_url)
                    if cache_file.exists():
                        cached_count += 1

                new_count = len(job_links) - cached_count
                cache_percentage = (cached_count / len(job_links)) * 100

                # Update overall totals
                total_new_jobs += new_count
                total_cached_jobs += cached_count

                self.stats['cached_on_last_page'] = cached_count
                self.stats['new_on_last_page'] = new_count
                self.stats['total_new_jobs'] = total_new_jobs
                self.stats['total_cached_jobs'] = total_cached_jobs

                self.logger.info(
                    f"Page {page_num}: Found {len(job_links)} job links "
                    f"({new_count} new, {cached_count} cached - {cache_percentage:.1f}%)"
                )

                # Early stop if all jobs on this page are cached
                if new_count <= min_new_jobs:
                    self.stats['early_stopped'] = True
                    self.logger.info(
                        f"⚡ Early stopping at page {page_num}: "
                        f"All jobs already cached (found {min_new_jobs} or fewer new jobs)"
                    )
                    break
            else:
                self.logger.info(f"Page {page_num}: Found {len(job_links)} job links")

            # Check max pages limit if configured
            if max_pages and page_num >= max_pages:
                self.logger.info(f"Reached max_pages limit ({max_pages})")
                break

            # Try to navigate to next page
            has_next = await self.navigate_to_next_page()
            if not has_next:
                self.logger.info("Reached last page (no next button)")
                self.stats['total_pages_available'] = page_num
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
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Summary for {self.name}:")
            self.logger.info(f"{'='*60}")
            self.logger.info(f"  Pages scraped: {self.stats['pages_scraped']}")
            self.logger.info(f"  Total jobs found: {self.stats['jobs_found']}")

            # Show cache efficiency stats if available
            if self.stats['total_new_jobs'] > 0 or self.stats['total_cached_jobs'] > 0:
                total_jobs = self.stats['total_new_jobs'] + self.stats['total_cached_jobs']
                cache_rate = (self.stats['total_cached_jobs'] / total_jobs * 100) if total_jobs > 0 else 0
                self.logger.info(f"  New jobs: {self.stats['total_new_jobs']}")
                self.logger.info(f"  Already cached: {self.stats['total_cached_jobs']} ({cache_rate:.1f}%)")

            # Show early stopping info
            if self.stats['early_stopped']:
                self.logger.info(f"\n  ⚡ Early Stopping Activated:")
                self.logger.info(f"     Stopped at page {self.stats['pages_scraped']} (100% cached jobs)")

                # Estimate time saved if we know there are more pages
                # (Conservative estimate: assume at least 2-3 more pages could have existed)
                if self.stats['jobs_found'] >= self.stats['pages_scraped'] * 15:  # Average 15+ jobs per page
                    self.logger.info(f"     Likely saved time by not loading additional pages")
                    self.logger.info(f"     (All jobs on last page were already cached)")
            elif self.stats['total_pages_available'] > 0:
                self.logger.info(f"  Completed: Scraped all {self.stats['total_pages_available']} available pages")

            self.logger.info(f"{'='*60}\n")

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
