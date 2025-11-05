#!/usr/bin/env python3
"""
Example: Using JobBoardFinder Programmatically
Demonstrates how to use the JobBoardFinder class in your own scripts.
"""

import asyncio
import json
from job_board_finder import JobBoardFinder


async def basic_example():
    """Simple example - use default config."""
    print("=== Basic Example ===\n")

    # Initialize with default config
    finder = JobBoardFinder()

    # Discover boards (limit to 3 queries for demo)
    boards = await finder.discover_job_boards(max_queries=3)

    # Save results
    finder.save_results("example_output.json")

    # Print summary
    print(f"Found {len(boards)} job boards")
    for domain, data in list(boards.items())[:5]:
        print(f"  - {domain}: {data['title'][:50]}")


async def custom_config_example():
    """Example with custom configuration."""
    print("\n=== Custom Config Example ===\n")

    # Initialize with custom config
    finder = JobBoardFinder("job_board_discovery_config.yaml")

    # Override some config values programmatically
    finder.config['search_engine']['rate_limit']['min_delay_seconds'] = 3

    # Run discovery
    boards = await finder.discover_job_boards(max_queries=5)

    # Filter to high-scoring boards only
    high_scoring = {
        domain: data for domain, data in boards.items()
        if data['score'] >= 2.0
    }

    print(f"Found {len(high_scoring)} high-scoring boards (score >= 2.0)")
    for domain, data in sorted(high_scoring.items(), key=lambda x: x[1]['score'], reverse=True):
        print(f"  - {domain} (score: {data['score']:.1f})")


async def filtered_example():
    """Example showing filtering and analysis."""
    print("\n=== Filtered Analysis Example ===\n")

    finder = JobBoardFinder()

    # Discover boards
    boards = await finder.discover_job_boards(max_queries=5)

    # Group by score ranges
    high = [b for b in boards.values() if b['score'] >= 2.5]
    medium = [b for b in boards.values() if 1.5 <= b['score'] < 2.5]
    low = [b for b in boards.values() if b['score'] < 1.5]

    print(f"Score Distribution:")
    print(f"  High (>=2.5): {len(high)} boards")
    print(f"  Medium (1.5-2.5): {len(medium)} boards")
    print(f"  Low (<1.5): {len(low)} boards")

    # Show top indicators
    all_indicators = {}
    for board in boards.values():
        for indicator in board.get('indicators', []):
            all_indicators[indicator] = all_indicators.get(indicator, 0) + 1

    print(f"\nTop Indicators:")
    for indicator, count in sorted(all_indicators.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  - {indicator}: {count} times")


async def custom_keywords_example():
    """Example showing how to customize keywords programmatically."""
    print("\n=== Custom Keywords Example ===\n")

    finder = JobBoardFinder()

    # Customize keywords for specific search
    finder.config['job_keywords'] = ['careers', 'opportunities']
    finder.config['industry_keywords'] = ['software', 'engineering']
    finder.config['location_keywords'] = ['remote', 'nationwide']

    # Regenerate queries with new keywords
    queries = finder._generate_search_queries(max_queries=4)
    print(f"Generated {len(queries)} custom queries:")
    for i, query in enumerate(queries, 1):
        print(f"  {i}. {query}")

    # Run discovery
    boards = await finder.discover_job_boards(max_queries=4)
    print(f"\nFound {len(boards)} boards with custom keywords")


async def export_example():
    """Example showing different export formats."""
    print("\n=== Export Example ===\n")

    finder = JobBoardFinder()
    boards = await finder.discover_job_boards(max_queries=3)

    # Save as JSON (default)
    finder.save_results("boards.json")
    print("Saved to boards.json")

    # Custom export to CSV-like format
    with open("boards.txt", "w") as f:
        f.write("Domain,URL,Score,Title\n")
        for board in sorted(boards.values(), key=lambda x: x['score'], reverse=True):
            f.write(f"{board['domain']},{board['url']},{board['score']},\"{board['title']}\"\n")
    print("Saved to boards.txt")

    # Export just high-scoring domains
    high_scoring_domains = [
        board['domain'] for board in boards.values()
        if board['score'] >= 2.0
    ]
    with open("high_scoring_domains.txt", "w") as f:
        f.write("\n".join(high_scoring_domains))
    print("Saved high-scoring domains to high_scoring_domains.txt")


async def main():
    """Run all examples."""
    print("Job Board Finder - Programmatic Examples\n")
    print("=" * 60)

    try:
        # Run examples (comment out ones you don't want)
        await basic_example()
        # await custom_config_example()
        # await filtered_example()
        # await custom_keywords_example()
        # await export_example()

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    # Run the examples
    print("Note: This is a demo script. Uncomment examples in main() to run them.\n")
    asyncio.run(main())
