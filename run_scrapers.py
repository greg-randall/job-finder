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
        logger: Logger instance (group logger for coordination)

    Returns:
        Result dictionary with success status and stats
    """
    site_name = site_config.get('name', 'unknown')
    site_url = site_config.get('url', 'unknown')

    logger.info(f"Starting scraper for: {site_name}")
    logger.info(f"URL: {site_url}")
    logger.add_breadcrumb(f"Started {site_name}")

    # Create site-specific logger for proper error artifact tagging
    site_logger = get_logger(site_name)

    try:
        # Create appropriate scraper with site-specific logger
        scraper = create_scraper(site_config, logger=site_logger)

        # Run the scraper with a 60-second timeout
        try:
            result = await asyncio.wait_for(scraper.scrape(), timeout=60.0)
        except asyncio.TimeoutError:
            site_logger.error(f"Scraper for {site_name} timed out after 60 seconds.")
            logger.increment_stat("sites_failed")
            # Capture error context if possible
            try:
                if scraper.tab:
                    current_url = await scraper.tab.evaluate('window.location.href')
                    await site_logger.capture_error_context(
                        error_type="ScraperTimeout",
                        error_message="Scraper timed out after 60 seconds",
                        url=current_url,
                        page=scraper.tab,
                    )
            except Exception as context_error:
                site_logger.warning(f"Could not capture timeout context: {str(context_error)}")

            return {
                'success': False,
                'reason': 'timeout',
                'stats': scraper.stats if hasattr(scraper, 'stats') else {}
            }


        if result.get('success'):
            logger.increment_stat("sites_processed")
        else:
            logger.increment_stat("sites_failed")
            site_logger.error(f"Scraper failed for {site_name}: {result.get('reason', 'Unknown error')}")

        return result

    except Exception as e:
        site_logger.error(f"Failed to scrape {site_name}: {str(e)}")
        logger.increment_stat("sites_failed")

        return {
            'success': False,
            'reason': str(e),
            'stats': {}
        }


async def run_backend_worker(
    backend_type: str,
    sites: List[dict],
    logger
) -> dict:
    """
    Worker function to run all sites for a specific backend sequentially.

    Args:
        backend_type: The backend/scraper type (e.g., 'workday', 'icims')
        sites: List of site configurations for this backend
        logger: Logger instance

    Returns:
        Dictionary with success/failure counts for this backend
    """
    logger.info(f"[{backend_type.upper()}] Starting worker with {len(sites)} sites")

    successful = 0
    failed = 0

    for index, site_config in enumerate(sites, 1):
        site_name = site_config.get('name', 'unknown')
        logger.info(f"[{backend_type.upper()}] Site {index}/{len(sites)}: {site_name}")

        result = await run_site(site_config, logger)

        if result.get('success'):
            successful += 1
        else:
            failed += 1

    logger.info(f"[{backend_type.upper()}] Worker complete: {successful} successful, {failed} failed")

    return {
        'backend': backend_type,
        'successful': successful,
        'failed': failed
    }


async def run_scrapers(
    group: Optional[str] = None,
    site: Optional[str] = None
) -> None:
    """
    Run scrapers based on filters with backend-based parallelization.

    Sites are grouped by their scraper type (backend), and one scraper per
    backend runs at a time. Different backends run in parallel for maximum
    efficiency while avoiding rate limiting issues.

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

    # Group sites by scraper type (backend)
    from collections import defaultdict
    backend_groups = defaultdict(list)

    for site_config in sites:
        # Note: config loader prefixes with underscore
        scraper_type = site_config.get('_type', site_config.get('type', 'unknown'))
        backend_groups[scraper_type].append(site_config)

    # Log backend distribution
    logger.info(f"\n{'='*80}")
    logger.info("Backend Distribution (for parallel execution)")
    logger.info(f"{'='*80}")
    for backend_type, backend_sites in backend_groups.items():
        logger.info(f"  {backend_type}: {len(backend_sites)} sites")
    logger.info(f"Total backends: {len(backend_groups)}")
    logger.info(f"Max concurrent scrapers: {len(backend_groups)}")
    logger.info(f"{'='*80}\n")

    # Track results
    total_sites = len(sites)

    # Run backend workers in parallel
    logger.info("Starting parallel execution...")
    tasks = [
        run_backend_worker(backend_type, backend_sites, logger)
        for backend_type, backend_sites in backend_groups.items()
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate results
    successful = 0
    failed = 0

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Backend worker failed with exception: {result}")
            failed += 1
        elif isinstance(result, dict):
            successful += result.get('successful', 0)
            failed += result.get('failed', 0)

    # Print summary
    logger.info(f"\n{'='*80}")
    logger.info("Summary")
    logger.info(f"{'='*80}")
    logger.info(f"Total sites processed: {total_sites}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Backends run in parallel: {len(backend_groups)}")

    # Show performance optimization info if any scrapers used early stopping
    logger.info(f"\nPerformance: Early stopping optimization is active")
    logger.info(f"  Scrapers will stop when hitting pages with 100% cached jobs")
    logger.info(f"  See individual scraper logs for early-stop details")

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
