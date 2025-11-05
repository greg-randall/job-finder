#!/usr/bin/env python3
"""
Test script for GitHub Issue Handler

This script tests the GitHub issue creation functionality without running a full scraper.
It simulates a scraper failure and creates/updates a GitHub issue.

Usage:
    python test_github_issue_handler.py [--scraper-name NAME]
"""

import argparse
import sys
from pathlib import Path

from logging_config import get_logger
from github_issue_handler import report_scraper_failure


def test_issue_creation(scraper_name: str = "test-scraper") -> bool:
    """
    Test the GitHub issue creation/update functionality.

    Args:
        scraper_name: Name of the test scraper

    Returns:
        True if successful, False otherwise
    """
    # Create logger
    logger = get_logger("test_github_handler")

    logger.info("="*80)
    logger.info("Testing GitHub Issue Handler")
    logger.info("="*80)

    # Simulate scraper failure data
    test_url = "https://example.com/jobs"
    error_summary = "Test scraper failure - This is a test of the automatic issue reporting system"

    test_stats = {
        'pages_scraped': 5,
        'jobs_found': 25,
        'jobs_downloaded': 10,
        'errors': 3,
        'jobs_skipped': 12
    }

    logger.info(f"Simulating failure for scraper: {scraper_name}")
    logger.info(f"URL: {test_url}")
    logger.info(f"Error: {error_summary}")
    logger.info(f"Stats: {test_stats}")
    logger.info("")

    # Attempt to report the failure
    try:
        success = report_scraper_failure(
            scraper_name=scraper_name,
            scraper_url=test_url,
            error_summary=error_summary,
            stats=test_stats,
            logger=logger
        )

        if success:
            logger.info("="*80)
            logger.info("✓ Test PASSED: Successfully created/updated GitHub issue")
            logger.info("="*80)
            logger.info("Check your GitHub repository for the issue.")
            logger.info("It should be labeled with:")
            logger.info("  - scraper-failure")
            logger.info("  - auto-generated")
            logger.info(f"  - scraper:{scraper_name}")
            logger.info("="*80)
            return True
        else:
            logger.error("="*80)
            logger.error("✗ Test FAILED: Could not create/update GitHub issue")
            logger.error("="*80)
            logger.error("Possible reasons:")
            logger.error("  1. GitHub CLI (gh) is not installed")
            logger.error("  2. Not authenticated with GitHub (run: gh auth login)")
            logger.error("  3. No permission to create issues in this repository")
            logger.error("="*80)
            return False

    except Exception as e:
        logger.error("="*80)
        logger.error(f"✗ Test FAILED with exception: {e}")
        logger.error("="*80)
        return False


def check_gh_cli() -> bool:
    """
    Check if GitHub CLI is installed and authenticated.

    Returns:
        True if gh CLI is available and authenticated
    """
    import subprocess

    logger = get_logger("test_github_handler")

    # Check if gh is installed
    try:
        result = subprocess.run(
            ["gh", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info(f"✓ GitHub CLI is installed: {result.stdout.split()[2]}")
        else:
            logger.error("✗ GitHub CLI is not installed")
            return False
    except FileNotFoundError:
        logger.error("✗ GitHub CLI (gh) is not installed")
        logger.error("Install it from: https://cli.github.com/")
        return False
    except Exception as e:
        logger.error(f"✗ Error checking gh CLI: {e}")
        return False

    # Check if authenticated
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            logger.info("✓ GitHub CLI is authenticated")
            return True
        else:
            logger.error("✗ GitHub CLI is not authenticated")
            logger.error("Run: gh auth login")
            return False
    except Exception as e:
        logger.error(f"✗ Error checking gh auth status: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Test GitHub Issue Handler functionality',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Test with default scraper name
  %(prog)s --scraper-name mytest    # Test with custom scraper name
  %(prog)s --check-only             # Only check gh CLI status
        """
    )

    parser.add_argument(
        '--scraper-name',
        type=str,
        default='test-scraper',
        help='Name of test scraper (default: test-scraper)'
    )

    parser.add_argument(
        '--check-only',
        action='store_true',
        help='Only check if gh CLI is installed and authenticated'
    )

    args = parser.parse_args()

    # Check gh CLI first
    logger = get_logger("test_github_handler")
    logger.info("Checking GitHub CLI status...")
    logger.info("")

    gh_available = check_gh_cli()

    if args.check_only:
        sys.exit(0 if gh_available else 1)

    if not gh_available:
        logger.error("")
        logger.error("Cannot proceed with test - GitHub CLI is not available")
        sys.exit(1)

    logger.info("")
    logger.info("GitHub CLI is ready. Proceeding with test...")
    logger.info("")

    # Run the test
    success = test_issue_creation(args.scraper_name)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
