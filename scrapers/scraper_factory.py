"""
Scraper factory for creating appropriate scraper instances.

This module provides a factory function that instantiates the correct
scraper type based on configuration.
"""

from typing import Dict, Any, Optional

from logging_config import ScraperLogger

from scrapers.base_scraper import BaseScraper
from scrapers.standard_scraper import StandardScraper
from scrapers.iframe_scraper import IframeScraper
from scrapers.url_pagination_scraper import URLPaginationScraper
from scrapers.custom_click_scraper import CustomClickScraper
from scrapers.custom_navigation_scraper import CustomNavigationScraper


# Mapping of scraper types to classes
SCRAPER_TYPES = {
    'standard': StandardScraper,
    'iframe': IframeScraper,
    'url_pagination': URLPaginationScraper,
    'custom_click': CustomClickScraper,
    'custom_navigation': CustomNavigationScraper,
}


def create_scraper(
    site_config: Dict[str, Any],
    logger: Optional[ScraperLogger] = None
) -> BaseScraper:
    """
    Create a scraper instance based on site configuration.

    Args:
        site_config: Site configuration dictionary with _type key
        logger: Optional logger instance

    Returns:
        Appropriate scraper instance

    Raises:
        ValueError: If scraper type is not recognized

    Example:
        >>> site_config = {
        ...     'name': 'workday_site',
        ...     'url': 'https://example.com/jobs',
        ...     '_type': 'standard',
        ...     '_selectors': {...},
        ...     ...
        ... }
        >>> scraper = create_scraper(site_config)
        >>> await scraper.scrape()
    """
    scraper_type = site_config.get('_type', 'standard')

    if scraper_type not in SCRAPER_TYPES:
        raise ValueError(
            f"Unknown scraper type: {scraper_type}. "
            f"Available types: {', '.join(SCRAPER_TYPES.keys())}"
        )

    scraper_class = SCRAPER_TYPES[scraper_type]
    return scraper_class(site_config, logger=logger)


def get_available_types() -> list:
    """
    Get list of available scraper types.

    Returns:
        List of scraper type names
    """
    return list(SCRAPER_TYPES.keys())


def register_scraper_type(type_name: str, scraper_class: type) -> None:
    """
    Register a new scraper type.

    This allows for extending the factory with custom scraper types
    without modifying this file.

    Args:
        type_name: Name for the scraper type
        scraper_class: Scraper class (must inherit from BaseScraper)

    Raises:
        TypeError: If scraper_class doesn't inherit from BaseScraper

    Example:
        >>> class MyCustomScraper(BaseScraper):
        ...     pass
        >>> register_scraper_type('my_custom', MyCustomScraper)
    """
    if not issubclass(scraper_class, BaseScraper):
        raise TypeError(
            f"{scraper_class.__name__} must inherit from BaseScraper"
        )

    SCRAPER_TYPES[type_name] = scraper_class
