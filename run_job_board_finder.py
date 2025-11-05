#!/usr/bin/env python3
"""
Runner script for Job Board Discovery
Provides command-line interface to discover job boards via search engines.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from job_board_finder import JobBoardFinder


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Discover job boards by searching through search engines',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with default config (5 queries for quick test)
  python run_job_board_finder.py

  # Run with custom number of queries
  python run_job_board_finder.py --max-queries 10

  # Run all possible queries
  python run_job_board_finder.py --max-queries 0

  # Use custom config file
  python run_job_board_finder.py --config my_config.yaml

  # Save to custom output file
  python run_job_board_finder.py --output my_boards.json

  # Run in non-headless mode to see the browser
  python run_job_board_finder.py --no-headless
        """
    )

    parser.add_argument(
        '--config',
        type=str,
        default='job_board_discovery_config.yaml',
        help='Path to configuration file (default: job_board_discovery_config.yaml)'
    )

    parser.add_argument(
        '--max-queries',
        type=int,
        default=5,
        help='Maximum number of search queries to run (0 = unlimited, default: 5)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output file path (overrides config file setting)'
    )

    parser.add_argument(
        '--no-headless',
        action='store_true',
        help='Run browser in non-headless mode (visible browser window)'
    )

    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Enable verbose logging (DEBUG level)'
    )

    return parser.parse_args()


async def run_discovery(args):
    """Run the job board discovery process."""
    print(f"{'='*60}")
    print("Job Board Discovery")
    print(f"{'='*60}")
    print(f"Config: {args.config}")
    print(f"Max queries: {args.max_queries if args.max_queries > 0 else 'unlimited'}")
    print(f"{'='*60}\n")

    # Initialize finder
    finder = JobBoardFinder(config_path=args.config)

    # Override config settings from command line
    if args.no_headless:
        if 'browser' not in finder.config:
            finder.config['browser'] = {}
        finder.config['browser']['headless'] = False

    if args.verbose:
        finder.config['output']['log_level'] = 'DEBUG'
        finder.logger.setLevel('DEBUG')

    # Discover job boards
    max_queries = args.max_queries if args.max_queries > 0 else None
    boards = await finder.discover_job_boards(max_queries=max_queries)

    # Save results
    output_path = args.output if args.output else None
    finder.save_results(output_path=output_path)

    # Print summary
    print(f"\n{'='*60}")
    print("Discovery Complete!")
    print(f"{'='*60}")
    print(f"Total boards discovered: {len(boards)}")
    print(f"Output saved to: {args.output or finder.config['output']['file_path']}")

    if boards:
        print(f"\nTop 15 discovered job boards by relevance score:")
        print(f"{'-'*60}")

        sorted_boards = sorted(boards.values(), key=lambda x: x['score'], reverse=True)
        for i, board in enumerate(sorted_boards[:15], 1):
            print(f"\n{i}. {board['domain']} (score: {board['score']:.1f})")
            print(f"   URL: {board['url']}")
            print(f"   Title: {board['title'][:70]}")
            if board['indicators']:
                print(f"   Indicators: {', '.join(board['indicators'][:3])}")
    else:
        print("\nNo job boards discovered. Try:")
        print("  - Increasing max-queries")
        print("  - Adjusting keywords in config file")
        print("  - Running with --verbose to see detailed logs")

    print(f"\n{'='*60}\n")


def main():
    """Main entry point."""
    args = parse_args()

    # Check config file exists
    if not Path(args.config).exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    # Run discovery
    try:
        asyncio.run(run_discovery(args))
    except KeyboardInterrupt:
        print("\n\nDiscovery interrupted by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
