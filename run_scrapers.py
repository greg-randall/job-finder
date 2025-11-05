#!/usr/bin/env python3
"""
Unified entry point for running job board scrapers.

This script provides a single interface for running all configured
job board scrapers based on config.yaml.

Usage:
    python run_scrapers.py                    # Run all enabled scrapers
    python run_scrapers.py --group workday    # Run specific group
    python run_scrapers.py --site bbinsurance # Run specific site
    python run_scrapers.py --list             # List available scrapers
"""

import argparse
import asyncio
import sys
from typing import List, Optional

from config_loader import get_config
from logging_config import get_logger
from scrapers import create_scraper


async def run_site(site_config: dict, logger) -> dict:
    """
    Run a single site scraper.

    Args:
        site_config: Site configuration dictionary
        logger: Logger instance

    Returns:
        Result dictionary with success status and stats
    """
    site_name = site_config.get('name', 'unknown')
    site_url = site_config.get('url', 'unknown')

    logger.info(f"Starting scraper for: {site_name}")
    logger.info(f"URL: {site_url}")
    logger.add_breadcrumb(f"Started {site_name}")

    try:
        # Create appropriate scraper
        scraper = create_scraper(site_config, logger=logger)

        # Run the scraper
        result = await scraper.scrape()

        if result.get('success'):
            logger.increment_stat("sites_processed")
        else:
            logger.increment_stat("sites_failed")

        return result

    except Exception as e:
        logger.error(f"Failed to scrape {site_name}: {str(e)}")
        logger.increment_stat("sites_failed")
        return {
            'success': False,
            'reason': str(e),
            'stats': {}
        }


async def run_scrapers(
    group: Optional[str] = None,
    site: Optional[str] = None
) -> None:
    """
    Run scrapers based on filters.

    Args:
        group: Optional group name to filter by
        site: Optional specific site name to run
    """
    config = get_config()

    # Determine logger name
    logger_name = site or group or "all_scrapers"
    logger = get_logger(logger_name)

    # Get enabled sites
    if site:
        # Run specific site
        sites = [s for s in config.get_enabled_sites() if s.get('name') == site]
        if not sites:
            logger.error(f"Site '{site}' not found or not enabled")
            return
        logger.info(f"Running specific site: {site}")
    elif group:
        # Run specific group
        sites = config.get_enabled_sites(group_name=group)
        if not sites:
            logger.error(f"Group '{group}' not found or has no enabled sites")
            return
        logger.info(f"Running group: {group} ({len(sites)} sites)")
    else:
        # Run all enabled sites
        sites = config.get_enabled_sites()
        logger.info(f"Running all enabled scrapers ({len(sites)} sites)")

    # Track results
    total_sites = len(sites)
    successful = 0
    failed = 0

    # Run each site
    for index, site_config in enumerate(sites, 1):
        site_name = site_config.get('name', 'unknown')
        logger.info(f"\n{'='*80}")
        logger.info(f"Site {index}/{total_sites}: {site_name}")
        logger.info(f"{'='*80}")

        result = await run_site(site_config, logger)

        if result.get('success'):
            successful += 1
        else:
            failed += 1

    # Print summary
    logger.info(f"\n{'='*80}")
    logger.info("Summary")
    logger.info(f"{'='*80}")
    logger.info(f"Total sites processed: {total_sites}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")

    # Write detailed summary to file
    summary_path = logger.write_summary()
    logger.info(f"Detailed summary saved to: {summary_path}")


def list_scrapers() -> None:
    """List all available scrapers from configuration."""
    config = get_config()

    print("\n" + "="*80)
    print("Available Job Board Scrapers")
    print("="*80)

    job_boards = config.get_job_boards(enabled_only=False)

    for board in job_boards:
        group_name = board.get('group', 'unknown')
        scraper_type = board.get('type', 'unknown')
        enabled = board.get('enabled', True)
        sites = board.get('sites', [])

        status = "✓ ENABLED" if enabled else "✗ DISABLED"
        print(f"\n{status} Group: {group_name} (Type: {scraper_type})")
        print(f"  Sites: {len(sites)}")

        for site in sites:
            site_name = site.get('name', 'unknown')
            site_enabled = site.get('enabled', True)
            site_status = "✓" if site_enabled else "✗"
            print(f"    {site_status} {site_name}")

    print("\n" + "="*80)

    # Count stats
    enabled_groups = len([b for b in job_boards if b.get('enabled', True)])
    total_sites = len(config.get_enabled_sites())

    print(f"Total groups: {len(job_boards)} ({enabled_groups} enabled)")
    print(f"Total enabled sites: {total_sites}")
    print("="*80 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Run job board scrapers based on configuration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Run all enabled scrapers
  %(prog)s --group workday          Run all Workday sites
  %(prog)s --site bbinsurance       Run specific site
  %(prog)s --list                   List all available scrapers
  %(prog)s --config custom.yaml     Use custom config file
        """
    )

    parser.add_argument(
        '--group',
        type=str,
        help='Run scrapers for a specific group (e.g., workday, icims, adp)'
    )

    parser.add_argument(
        '--site',
        type=str,
        help='Run a specific site by name (e.g., bbinsurance)'
    )

    parser.add_argument(
        '--list',
        action='store_true',
        help='List all available scrapers and their status'
    )

    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='Path to configuration file (default: config.yaml)'
    )

    args = parser.parse_args()

    # Handle list command
    if args.list:
        list_scrapers()
        return

    # Validate arguments
    if args.group and args.site:
        print("Error: Cannot specify both --group and --site", file=sys.stderr)
        sys.exit(1)

    # Load config if custom path specified
    if args.config != 'config.yaml':
        from config_loader import reload_config
        reload_config(args.config)

    # Run scrapers
    try:
        asyncio.run(run_scrapers(group=args.group, site=args.site))
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Exiting...")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
