# Job Board Finder

A tool to discover smaller job boards by searching through privacy-focused search engines and filtering out major job sites.

## Overview

The Job Board Finder uses `nodriver` (a stealth browser automation library) to:
1. Search Mullvad's Leta search engine with keyword combinations
2. Extract job-related websites from search results
3. Filter out large job boards (Indeed, LinkedIn, ZipRecruiter, etc.)
4. Score and save discovered smaller job boards
5. Handle rate limiting and 429 errors automatically

## Features

- **Keyword Combinations**: Mix and match job-related keywords (career, jobs, employment) with industries (real estate, web developer, plumber) and locations
- **Smart Rate Limiting**: Enforces minimum 5-second delay between requests
- **429 Error Handling**: Automatically sleeps 60 seconds and retries on rate limit errors
- **Domain Filtering**: Excludes major job boards to focus on smaller, niche sites
- **Scoring System**: Ranks discovered sites based on job-related indicators
- **Configurable**: All settings in YAML configuration file

## Installation

### Prerequisites

1. Python 3.11+
2. Chrome or Chromium browser installed
3. Required packages (install via pip):

```bash
pip install nodriver aiofiles trafilatura openai python-dotenv tqdm pyyaml
```

## Configuration

Edit `job_board_discovery_config.yaml` to customize:

### Search Engine Settings

```yaml
search_engine:
  base_url: "https://leta.mullvad.net/search"
  engine: "brave"  # Search engine to use
  rate_limit:
    min_delay_seconds: 5      # Minimum delay between requests
    retry_delay_seconds: 60   # Delay on 429 error
    max_retries: 3            # Max retries for 429
```

### Keywords

```yaml
job_keywords:
  - "career"
  - "jobs"
  - "employment"
  - "hiring"
  # Add more...

industry_keywords:
  - "real estate"
  - "web developer"
  - "plumber"
  # Add more...

location_keywords:
  - "richmond"
  - "virginia"
  # Add more...
```

### Excluded Domains

```yaml
excluded_domains:
  - "indeed.com"
  - "linkedin.com"
  - "ziprecruiter.com"
  # These domains will be filtered out
```

## Usage

### Basic Usage

Run with default settings (5 queries):

```bash
python run_job_board_finder.py
```

### Common Options

```bash
# Run specific number of queries
python run_job_board_finder.py --max-queries 10

# Run all possible query combinations
python run_job_board_finder.py --max-queries 0

# Use custom config file
python run_job_board_finder.py --config my_config.yaml

# Save to custom output file
python run_job_board_finder.py --output results.json

# Show browser window (non-headless)
python run_job_board_finder.py --no-headless

# Enable verbose logging
python run_job_board_finder.py --verbose
```

### Full Example

```bash
python run_job_board_finder.py \
  --max-queries 20 \
  --output discovered_boards_$(date +%Y%m%d).json \
  --verbose
```

## Output Format

Results are saved as JSON with this structure:

```json
{
  "discovery_date": "2025-11-05T12:00:00",
  "total_boards": 45,
  "boards": [
    {
      "url": "https://example-job-board.com/careers",
      "domain": "example-job-board.com",
      "title": "Careers at Example Company",
      "snippet": "Join our team! We're hiring for multiple positions...",
      "score": 3.5,
      "indicators": [
        "URL contains 'career'",
        "Content mentions 'job'",
        "Content mentions 'hiring'"
      ],
      "discovered_at": "2025-11-05T12:05:30"
    }
  ]
}
```

### Score Interpretation

- **Score > 2**: High confidence job board
- **Score 1-2**: Moderate confidence
- **Score < 1**: Low confidence (may be general career advice site)

## How It Works

### 1. Query Generation

The tool generates search queries by combining:
- Location keywords (e.g., "richmond")
- Industry keywords (e.g., "real estate")
- Job keywords (e.g., "career")

Example: "richmond real estate career"

### 2. Search & Extract

For each query:
1. Navigate to search engine with query
2. Wait for results to load
3. Extract URLs, titles, and snippets
4. Check for 429 errors and handle accordingly

### 3. Filter & Score

For each result:
1. Check if domain is in excluded list → skip if yes
2. Analyze URL and content for job-related terms
3. Calculate relevance score
4. Add to discovered boards if score > 0

### 4. Rate Limiting

- **Minimum delay**: 5 seconds between requests
- **429 handling**: Sleep 60 seconds, retry up to 3 times
- **Automatic**: No manual intervention needed

## Architecture

### Files

- `job_board_finder.py` - Main scraper class
- `run_job_board_finder.py` - CLI runner script
- `job_board_discovery_config.yaml` - Configuration
- `discovered_job_boards.json` - Default output file

### `job_board_finder.py` Code

```python
"""
Job Board Discovery Scraper
Uses nodriver to search for smaller job boards via search engines.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse, urljoin, parse_qs, urlencode

import nodriver as uc
import yaml

from functions import init_browser, wait_for_selector, wait_for_load


class JobBoardFinder:
    """Discovers job boards by searching and spidering through search engine results."""

    def __init__(self, config_path: str = "job_board_discovery_config.yaml"):
        """Initialize the job board finder with configuration."""
        self.config = self._load_config(config_path)
        self.logger = self._setup_logging()

        # State tracking
        self.discovered_boards: Dict[str, Dict] = {}
        self.visited_urls: Set[str] = set()
        self.last_request_time = 0

        # Browser instances
        self.browser = None
        self.tab = None

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration."""
        log_level = self.config.get('output', {}).get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    async def initialize_browser(self):
        """Initialize nodriver browser."""
        headless = self.config.get('browser', {}).get('headless', True)
        self.logger.info(f"Initializing browser (headless={headless})")
        self.browser = await init_browser(headless=headless)
        self.tab = await self.browser.get(self.config['search_engine']['base_url'])
        self.logger.info("Browser initialized successfully")

    async def cleanup_browser(self):
        """Cleanup browser resources."""
        if self.browser:
            self.logger.info("Closing browser")
            try:
                self.browser.stop()
            except Exception as e:
                self.logger.warning(f"Error closing browser: {e}")

    def _generate_search_queries(self, max_queries: int = None) -> List[str]:
        """Generate search queries from keyword combinations."""
        job_keywords = self.config.get('job_keywords', [])
        industry_keywords = self.config.get('industry_keywords', [])
        location_keywords = self.config.get('location_keywords', [])

        queries = []

        # Generate combinations: [location] [industry] [job_keyword]
        for location, industry, job_kw in product(location_keywords, industry_keywords, job_keywords):
            query = f"{location} {industry} {job_kw}"
            queries.append(query)

        # Limit number of queries if specified
        if max_queries:
            queries = queries[:max_queries]

        self.logger.info(f"Generated {len(queries)} search queries")
        return queries

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        min_delay = self.config['search_engine']['rate_limit']['min_delay_seconds']
        elapsed = time.time() - self.last_request_time

        if elapsed < min_delay:
            sleep_time = min_delay - elapsed
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            await asyncio.sleep(sleep_time)

        self.last_request_time = time.time()

    async def _handle_429_error(self, retry_count: int) -> bool:
        """
        Handle 429 Too Many Requests error.
        Returns True if should retry, False if max retries exceeded.
        """
        max_retries = self.config['search_engine']['rate_limit']['max_retries']

        if retry_count >= max_retries:
            self.logger.error(f"Max retries ({max_retries}) exceeded for 429 errors")
            return False

        retry_delay = self.config['search_engine']['rate_limit']['retry_delay_seconds']
        self.logger.warning(f"429 Too Many Requests - sleeping {retry_delay}s (retry {retry_count + 1}/{max_retries})")
        await asyncio.sleep(retry_delay)
        return True

    def _build_search_url(self, query: str) -> str:
        """Build search URL with query parameters."""
        base_url = self.config['search_engine']['base_url']
        engine = self.config['search_engine']['engine']

        params = {
            'q': query,
            'engine': engine
        }

        return f"{base_url}?{urlencode(params)}"

    def _is_excluded_domain(self, url: str) -> bool:
        """Check if URL belongs to an excluded big job board."""
        try:
            domain = urlparse(url).netloc.lower()
            # Remove www. prefix
            domain = domain.replace('www.', '')

            excluded = self.config.get('excluded_domains', [])
            for excluded_domain in excluded:
                if excluded_domain.lower() in domain:
                    return True
            return False
        except Exception as e:
            self.logger.warning(f"Error parsing URL {url}: {e}")
            return False

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
            return domain
        except:
            return ""

    async def _check_for_429(self) -> bool:
        """Check if current page shows a 429 error."""
        try:
            # Check page title or content for rate limit indicators
            title = await self.tab.evaluate('document.title')
            if title and '429' in title:
                return True

            # Check for common rate limit messages in page content
            body_text = await self.tab.evaluate('document.body.innerText')
            if body_text:
                rate_limit_indicators = [
                    '429',
                    'too many requests',
                    'rate limit',
                    'slow down'
                ]
                body_lower = body_text.lower()
                for indicator in rate_limit_indicators:
                    if indicator in body_lower:
                        return True

            return False
        except Exception as e:
            self.logger.debug(f"Error checking for 429: {e}")
            return False

    async def _search_and_extract_results(self, query: str) -> List[Dict]:
        """
        Perform search and extract result links.
        Returns list of dicts with 'url', 'title', 'snippet'.
        """
        results = []
        retry_count = 0

        while retry_count <= self.config['search_engine']['rate_limit']['max_retries']:
            try:
                # Rate limit
                await self._rate_limit()

                # Build search URL
                search_url = self._build_search_url(query)
                self.logger.info(f"Searching: {query}")
                self.logger.debug(f"URL: {search_url}")

                # Navigate to search results
                await self.tab.get(search_url)
                await wait_for_load(self.tab, timeout=3000)

                # Check for 429 error
                if await self._check_for_429():
                    self.logger.warning("Detected 429 error on page")
                    if await self._handle_429_error(retry_count):
                        retry_count += 1
                        continue
                    else:
                        break

                # Wait for results to load
                # Mullvad/SearXNG uses different selectors based on the search engine
                result_selectors = [
                    '.result',
                    '.result-default',
                    'article.result',
                    '.search-result',
                    '#urls .result'
                ]

                # Try to find results with different selectors
                results_found = False
                for selector in result_selectors:
                    if await wait_for_selector(self.tab, selector, timeout=5000):
                        results_found = True
                        break

                if not results_found:
                    self.logger.warning(f"No results found for query: {query}")
                    break

                # Extract result data
                results_data = await self.tab.evaluate('''
                    () => {
                        const results = [];
                        const resultElements = document.querySelectorAll('.result, .result-default, article.result, .search-result');

                        resultElements.forEach(elem => {
                            try {
                                const linkElem = elem.querySelector('a[href], h3 a, h4 a, .result-link');
                                if (!linkElem) return;

                                const url = linkElem.href;
                                const title = linkElem.textContent || linkElem.innerText || '';

                                // Try to find snippet/description
                                let snippet = '';
                                const snippetElem = elem.querySelector('.content, .result-content, .result-description, p');
                                if (snippetElem) {
                                    snippet = snippetElem.textContent || snippetElem.innerText || '';
                                }

                                results.push({
                                    url: url,
                                    title: title.trim(),
                                    snippet: snippet.trim()
                                });
                            } catch (e) {
                                console.error('Error extracting result:', e);
                            }
                        });

                        return results;
                    }
                ''')

                if results_data:
                    results = results_data
                    self.logger.info(f"Extracted {len(results)} results for query: {query}")
                else:
                    self.logger.warning(f"No results extracted for query: {query}")

                break  # Success, exit retry loop

            except Exception as e:
                self.logger.error(f"Error during search for '{query}': {e}", exc_info=True)
                break

        return results

    def _analyze_job_board(self, url: str, title: str, snippet: str) -> Dict:
        """Analyze a URL to determine if it's a job board and extract metadata."""
        domain = self._extract_domain(url)

        # Score based on URL and content
        score = 0
        indicators = []

        # Check URL for job-related terms
        url_lower = url.lower()
        job_terms = ['career', 'job', 'employ', 'recruit', 'hiring', 'work', 'opportunity']
        for term in job_terms:
            if term in url_lower:
                score += 1
                indicators.append(f"URL contains '{term}'")

        # Check title and snippet
        content = f"{title} {snippet}".lower()
        for term in job_terms:
            if term in content:
                score += 0.5
                indicators.append(f"Content mentions '{term}'")

        return {
            'url': url,
            'domain': domain,
            'title': title,
            'snippet': snippet,
            'score': score,
            'indicators': indicators,
            'discovered_at': datetime.now().isoformat(),
        }

    async def discover_job_boards(self, max_queries: int = None) -> Dict[str, Dict]:
        """
        Main method to discover job boards.
        Returns dict of discovered boards keyed by domain.
        """
        try:
            # Initialize browser
            await self.initialize_browser()

            # Generate search queries
            queries = self._generate_search_queries(max_queries)

            # Process each query
            for i, query in enumerate(queries, 1):
                self.logger.info(f"Processing query {i}/{len(queries)}: {query}")

                # Search and extract results
                results = await self._search_and_extract_results(query)

                # Analyze results
                for result in results:
                    url = result.get('url', '')
                    if not url:
                        continue

                    # Skip if already visited
                    if url in self.visited_urls:
                        continue
                    self.visited_urls.add(url)

                    # Skip excluded domains
                    if self._is_excluded_domain(url):
                        self.logger.debug(f"Skipping excluded domain: {url}")
                        continue

                    # Analyze as potential job board
                    analysis = self._analyze_job_board(
                        url=url,
                        title=result.get('title', ''),
                        snippet=result.get('snippet', '')
                    )

                    # Only keep if score indicates it's job-related
                    if analysis['score'] > 0:
                        domain = analysis['domain']

                        # Add or update entry
                        if domain not in self.discovered_boards:
                            self.discovered_boards[domain] = analysis
                            self.logger.info(f"Discovered job board: {domain} (score: {analysis['score']})")
                        else:
                            # Update score if higher
                            existing_score = self.discovered_boards[domain]['score']
                            if analysis['score'] > existing_score:
                                self.discovered_boards[domain] = analysis

                # Progress update
                self.logger.info(f"Progress: {i}/{len(queries)} queries, {len(self.discovered_boards)} boards discovered")

            return self.discovered_boards

        finally:
            await self.cleanup_browser()

    def save_results(self, output_path: str = None):
        """Save discovered job boards to JSON file."""
        if output_path is None:
            output_path = self.config['output']['file_path']

        # Convert to list sorted by score
        boards_list = sorted(
            self.discovered_boards.values(),
            key=lambda x: x['score'],
            reverse=True
        )

        output_data = {
            'discovery_date': datetime.now().isoformat(),
            'total_boards': len(boards_list),
            'boards': boards_list
        }

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        self.logger.info(f"Saved {len(boards_list)} job boards to {output_path}")


async def main():
    """Main entry point for testing."""
    finder = JobBoardFinder()

    # Discover job boards (limit to 5 queries for testing)
    boards = await finder.discover_job_boards(max_queries=5)

    # Save results
    finder.save_results()

    # Print summary
    print(f"\n{'='*60}")
    print(f"Discovery Complete!")
    print(f"{'='*60}")
    print(f"Total boards discovered: {len(boards)}")
    print(f"\nTop 10 by score:")

    sorted_boards = sorted(boards.values(), key=lambda x: x['score'], reverse=True)
    for i, board in enumerate(sorted_boards[:10], 1):
        print(f"{i}. {board['domain']} (score: {board['score']})")
        print(f"   URL: {board['url']}")
        print(f"   Title: {board['title'][:80]}")
        print()


if __name__ == '__main__':
    asyncio.run(main())
```


## Rate Limiting Details

### Normal Flow

```
Request 1 → Wait 5s → Request 2 → Wait 5s → Request 3 → ...
```

### 429 Error Flow

```
Request → 429 Error → Wait 60s → Retry → Success
                                ↓
                         (Retry #2) → Wait 60s → Retry → Success
                                                 ↓
                                          (Retry #3, max) → Skip
```

## Customization

### Add New Keywords

Edit `job_board_discovery_config.yaml`:

```yaml
industry_keywords:
  - "nursing"
  - "teaching"
  - "retail"
  - "your custom keyword"
```

### Exclude More Domains

```yaml
excluded_domains:
  - "another-big-site.com"
  - "also-exclude-this.com"
```

### Adjust Rate Limits

```yaml
search_engine:
  rate_limit:
    min_delay_seconds: 10  # Slower, more conservative
    retry_delay_seconds: 120  # Wait longer on 429
```

## Troubleshooting

### Browser Not Found

**Error**: `could not find a valid chrome browser binary`

**Solution**: Install Chrome or Chromium, or specify path:

```python
# In job_board_finder.py, modify initialize_browser():
self.browser = await uc.start(
    browser_executable_path="/path/to/chrome"
)
```

### Too Many 429 Errors

**Solution**: Increase rate limit delays:

```yaml
min_delay_seconds: 10  # Increase from 5
retry_delay_seconds: 120  # Increase from 60
```

### No Results Found

**Solution**:
1. Run with `--verbose` to see detailed logs
2. Try `--no-headless` to watch browser behavior
3. Check if search engine is accessible
4. Verify keyword combinations make sense

## Examples

### Discover Healthcare Job Boards

```yaml
# Config snippet
job_keywords: ["career", "jobs", "employment"]
industry_keywords: ["nursing", "healthcare", "medical"]
location_keywords: ["nationwide", "remote"]
```

```bash
python run_job_board_finder.py --max-queries 15 --output healthcare_boards.json
```

### Find Local Trade Job Boards

```yaml
# Config snippet
job_keywords: ["jobs", "hiring", "openings"]
industry_keywords: ["plumber", "electrician", "HVAC", "construction"]
location_keywords: ["richmond", "virginia beach", "norfolk"]
```

```bash
python run_job_board_finder.py --max-queries 20 --output trade_boards.json
```

## Integration with Existing Scrapers

Once you've discovered job boards, you can:

1. Review the `discovered_job_boards.json` file
2. Visit the high-scoring domains manually
3. Identify their scraper type (standard, URL pagination, etc.)
4. Add to main `config.yaml` for regular scraping

Example:

```yaml
# In config.yaml
job_boards:
  - group: "discovered_boards"
    type: "standard"
    enabled: true
    sites:
      - name: "example_board"
        url: "https://example-job-board.com/careers"
        enabled: true
```

## Performance

- **Typical run** (10 queries): 1-2 minutes
- **Memory usage**: ~200-300 MB (browser overhead)
- **Output size**: ~10-50 KB JSON (depends on results)

## Limitations

- Only searches one search engine at a time (configurable)
- Doesn't visit individual result pages (optional feature)
- Scoring is heuristic-based (may need tuning)
- Requires Chrome/Chromium installed

## Future Enhancements

Potential improvements:

- [ ] Multi-search engine support
- [ ] Deep link following (visit each result to verify it's a job board)
- [ ] Machine learning-based scoring
- [ ] Automatic scraper type detection
- [ ] Browser-less mode using HTTP requests
- [ ] Deduplication across multiple runs
- [ ] Export to CSV format

## License

Part of the job-finder project.
