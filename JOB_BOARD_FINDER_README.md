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

### Key Classes & Methods

```python
class JobBoardFinder:
    async def initialize_browser()
    async def discover_job_boards(max_queries)
    async def _search_and_extract_results(query)
    async def _rate_limit()
    async def _handle_429_error(retry_count)
    def _is_excluded_domain(url)
    def _analyze_job_board(url, title, snippet)
    def save_results(output_path)
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
