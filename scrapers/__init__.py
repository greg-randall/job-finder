"""
Scrapers package for job board scraping.

This package provides a unified interface for scraping different types
of job boards through configuration-driven scrapers.
"""

from scrapers.base_scraper import BaseScraper
from scrapers.standard_scraper import StandardScraper
from scrapers.iframe_scraper import IframeScraper
from scrapers.url_pagination_scraper import URLPaginationScraper
from scrapers.custom_click_scraper import CustomClickScraper
from scrapers.custom_navigation_scraper import CustomNavigationScraper
from scrapers.scraper_factory import (
    create_scraper,
    get_available_types,
    register_scraper_type
)

__all__ = [
    # Base class
    'BaseScraper',

    # Scraper implementations
    'StandardScraper',
    'IframeScraper',
    'URLPaginationScraper',
    'CustomClickScraper',
    'CustomNavigationScraper',

    # Factory functions
    'create_scraper',
    'get_available_types',
    'register_scraper_type',
]
