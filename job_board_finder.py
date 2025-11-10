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

# Create debug directory for saving page dumps
DEBUG_DIR = Path("debug_output")
DEBUG_DIR.mkdir(exist_ok=True)


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

        # Statistics tracking
        self.stats = {
            'queries_processed': 0,
            'total_results_found': 0,
            'excluded_big_boards': 0,
            'excluded_duplicate_urls': 0,
            'excluded_low_score': 0,
            'boards_added': 0,
            'rate_limits_hit': 0,
            'selector_failures': 0,
        }

        # Browser instances
        self.browser = None
        self.tab = None

        self.logger.info("="*70)
        self.logger.info("JobBoardFinder initialized")
        self.logger.info(f"Config loaded from: {config_path}")
        self.logger.info(f"Debug output directory: {DEBUG_DIR.absolute()}")
        self.logger.info("="*70)

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _setup_logging(self) -> logging.Logger:
        """Setup logging configuration."""
        log_level = self.config.get('output', {}).get('log_level', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(levelname)s - %(message)s',
            force=True
        )
        return logging.getLogger(__name__)

    async def _save_debug_html(self, filename: str, description: str = ""):
        """Save current page HTML for debugging."""
        try:
            html_content = await self.tab.evaluate('document.documentElement.outerHTML')
            page_url = await self.tab.evaluate('window.location.href')
            page_title = await self.tab.evaluate('document.title')

            debug_file = DEBUG_DIR / f"{filename}.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(f"<!-- URL: {page_url} -->\n")
                f.write(f"<!-- Title: {page_title} -->\n")
                f.write(f"<!-- Description: {description} -->\n")
                f.write(f"<!-- Timestamp: {datetime.now().isoformat()} -->\n\n")
                f.write(html_content)

            self.logger.info(f"💾 Debug HTML saved: {debug_file}")
            return debug_file
        except Exception as e:
            self.logger.error(f"Failed to save debug HTML: {e}")
            return None

    async def _save_debug_screenshot(self, filename: str):
        """Save screenshot for debugging."""
        try:
            screenshot_file = DEBUG_DIR / f"{filename}.png"
            await self.tab.save_screenshot(str(screenshot_file))
            self.logger.info(f"📸 Screenshot saved: {screenshot_file}")
            return screenshot_file
        except Exception as e:
            self.logger.error(f"Failed to save screenshot: {e}")
            return None

    def _log_stats(self):
        """Log current statistics."""
        self.logger.info("📊 CURRENT STATISTICS:")
        self.logger.info(f"   Queries processed: {self.stats['queries_processed']}")
        self.logger.info(f"   Results found: {self.stats['total_results_found']}")
        self.logger.info(f"   Boards discovered: {len(self.discovered_boards)}")
        self.logger.info(f"   URLs visited: {len(self.visited_urls)}")
        self.logger.info(f"   Excluded (big boards): {self.stats['excluded_big_boards']}")
        self.logger.info(f"   Excluded (duplicates): {self.stats['excluded_duplicate_urls']}")
        self.logger.info(f"   Excluded (low score): {self.stats['excluded_low_score']}")
        self.logger.info(f"   Rate limits hit: {self.stats['rate_limits_hit']}")
        self.logger.info(f"   Selector failures: {self.stats['selector_failures']}")

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
        self.logger.info("🔍 Generating search queries...")

        job_keywords = self.config.get('job_keywords', [])
        industry_keywords = self.config.get('industry_keywords', [])
        location_keywords = self.config.get('location_keywords', [])

        self.logger.info(f"   Job keywords: {len(job_keywords)} ({', '.join(job_keywords[:3])}...)")
        self.logger.info(f"   Industry keywords: {len(industry_keywords)} ({', '.join(industry_keywords[:3])}...)")
        self.logger.info(f"   Location keywords: {len(location_keywords)} ({', '.join(location_keywords)})")

        queries = []

        # Generate combinations: [location] [industry] [job_keyword]
        for location, industry, job_kw in product(location_keywords, industry_keywords, job_keywords):
            query = f"{location} {industry} {job_kw}"
            queries.append(query)

        self.logger.info(f"   Total possible combinations: {len(queries)}")

        # Limit number of queries if specified
        if max_queries:
            self.logger.info(f"   Limiting to first {max_queries} queries")
            queries = queries[:max_queries]

        self.logger.info(f"✅ Generated {len(queries)} search queries")

        # Log first few examples
        self.logger.info("   Example queries:")
        for i, query in enumerate(queries[:5], 1):
            self.logger.info(f"      {i}. \"{query}\"")
        if len(queries) > 5:
            self.logger.info(f"      ... and {len(queries) - 5} more")

        return queries

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        min_delay = self.config['search_engine']['rate_limit']['min_delay_seconds']
        elapsed = time.time() - self.last_request_time

        if elapsed < min_delay:
            sleep_time = min_delay - elapsed
            self.logger.info(f"⏱️  Rate limiting: sleeping {sleep_time:.2f}s (min delay: {min_delay}s)")
            await asyncio.sleep(sleep_time)
        else:
            self.logger.info(f"⏱️  Rate limit OK: {elapsed:.2f}s since last request")

        self.last_request_time = time.time()

    async def _handle_429_error(self, retry_count: int) -> bool:
        """
        Handle 429 Too Many Requests error.
        Returns True if should retry, False if max retries exceeded.
        """
        self.stats['rate_limits_hit'] += 1
        max_retries = self.config['search_engine']['rate_limit']['max_retries']

        if retry_count >= max_retries:
            self.logger.error(f"❌ Max retries ({max_retries}) exceeded for 429 errors")
            self.logger.error(f"   Total 429 errors this session: {self.stats['rate_limits_hit']}")
            return False

        retry_delay = self.config['search_engine']['rate_limit']['retry_delay_seconds']
        self.logger.warning(f"⚠️  429 Too Many Requests detected!")
        self.logger.warning(f"   Retry {retry_count + 1}/{max_retries}")
        self.logger.warning(f"   Sleeping {retry_delay}s before retry...")
        await asyncio.sleep(retry_delay)
        self.logger.info(f"   Retrying now...")
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
        self.logger.info("="*70)
        self.logger.info(f"🔎 SEARCHING: \"{query}\"")
        self.logger.info("="*70)

        results = []
        retry_count = 0

        while retry_count <= self.config['search_engine']['rate_limit']['max_retries']:
            try:
                # Rate limit
                await self._rate_limit()

                # Build search URL
                search_url = self._build_search_url(query)
                self.logger.info(f"📍 Search URL: {search_url}")

                # Navigate to search results
                self.logger.info("🌐 Navigating to search page...")
                await self.tab.get(search_url)
                await wait_for_load(self.tab, timeout=3000)

                # Get page info
                page_url = await self.tab.evaluate('window.location.href')
                page_title = await self.tab.evaluate('document.title')
                self.logger.info(f"✅ Page loaded successfully")
                self.logger.info(f"   Final URL: {page_url}")
                self.logger.info(f"   Page title: {page_title}")

                # Check for 429 error
                if await self._check_for_429():
                    self.logger.warning("⚠️  Detected 429 error on page")
                    await self._save_debug_html(f"429_error_{int(time.time())}", "429 rate limit page")
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

                self.logger.info("🔍 Testing result selectors...")

                # Try to find results with different selectors
                results_found = False
                successful_selector = None
                for selector in result_selectors:
                    self.logger.info(f"   Trying selector: '{selector}'")
                    if await wait_for_selector(self.tab, selector, timeout=5000):
                        # Count how many elements match
                        count = await self.tab.evaluate(f'document.querySelectorAll("{selector}").length')
                        self.logger.info(f"   ✅ Found {count} elements matching '{selector}'")
                        results_found = True
                        successful_selector = selector
                        break
                    else:
                        self.logger.info(f"   ❌ No elements found for '{selector}'")

                if not results_found:
                    self.logger.error(f"❌ SELECTOR FAILURE: No results found for query")
                    self.logger.error(f"   Tried selectors: {', '.join(result_selectors)}")
                    self.stats['selector_failures'] += 1

                    # Save debug files
                    timestamp = int(time.time())
                    await self._save_debug_html(f"selector_fail_{timestamp}", f"No selectors matched for query: {query}")
                    await self._save_debug_screenshot(f"selector_fail_{timestamp}")

                    # Log page structure for debugging
                    body_structure = await self.tab.evaluate('''
                        () => {
                            const body = document.body;
                            const classes = Array.from(body.querySelectorAll('[class]')).map(el => el.className).slice(0, 20);
                            const ids = Array.from(body.querySelectorAll('[id]')).map(el => el.id).slice(0, 20);
                            return {
                                classes: [...new Set(classes)],
                                ids: [...new Set(ids)]
                            };
                        }
                    ''')
                    self.logger.error(f"   Page classes found: {body_structure.get('classes', [])[:10]}")
                    self.logger.error(f"   Page IDs found: {body_structure.get('ids', [])[:10]}")
                    break

                self.logger.info(f"🎯 Extracting results using selector: '{successful_selector}'")

                # Extract result data
                results_data = await self.tab.evaluate('''
                    () => {
                        const results = [];
                        const resultElements = document.querySelectorAll('.result, .result-default, article.result, .search-result');

                        resultElements.forEach((elem, index) => {
                            try {
                                const linkElem = elem.querySelector('a[href], h3 a, h4 a, .result-link');
                                if (!linkElem) {
                                    console.log('No link found in result', index);
                                    return;
                                }

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
                    self.stats['total_results_found'] += len(results)
                    self.logger.info(f"✅ Extracted {len(results)} results")

                    # Log each result briefly
                    for i, result in enumerate(results, 1):
                        domain = self._extract_domain(result['url'])
                        self.logger.info(f"   [{i}] {domain}")
                        self.logger.info(f"       URL: {result['url'][:80]}{'...' if len(result['url']) > 80 else ''}")
                        self.logger.info(f"       Title: {result['title'][:80]}{'...' if len(result['title']) > 80 else ''}")
                else:
                    self.logger.warning(f"⚠️  No results extracted (empty results array)")

                break  # Success, exit retry loop

            except Exception as e:
                self.logger.error(f"❌ EXCEPTION during search for '{query}'", exc_info=True)
                # Save debug info on exception
                try:
                    timestamp = int(time.time())
                    await self._save_debug_html(f"exception_{timestamp}", f"Exception during search: {str(e)}")
                    await self._save_debug_screenshot(f"exception_{timestamp}")
                except:
                    pass
                break

        self.logger.info(f"📊 Search complete: {len(results)} results to process")
        return results

    def _analyze_job_board(self, url: str, title: str, snippet: str) -> Dict:
        """Analyze a URL to determine if it's a job board and extract metadata."""
        domain = self._extract_domain(url)

        # Score based on URL and content
        score = 0
        indicators = []

        self.logger.info(f"   🔬 Analyzing: {url}")

        # Check URL for job-related terms
        url_lower = url.lower()
        job_terms = ['career', 'job', 'employ', 'recruit', 'hiring', 'work', 'opportunity']

        url_matches = []
        for term in job_terms:
            if term in url_lower:
                score += 1
                indicators.append(f"URL contains '{term}'")
                url_matches.append(term)

        if url_matches:
            self.logger.info(f"      ✅ URL scoring: +{len(url_matches)} (terms: {', '.join(url_matches)})")
        else:
            self.logger.info(f"      ❌ URL scoring: +0 (no job terms in URL)")

        # Check title and snippet
        content = f"{title} {snippet}".lower()
        content_matches = []
        for term in job_terms:
            if term in content:
                score += 0.5
                indicators.append(f"Content mentions '{term}'")
                content_matches.append(term)

        if content_matches:
            self.logger.info(f"      ✅ Content scoring: +{len(content_matches)*0.5} (terms: {', '.join(content_matches)})")
        else:
            self.logger.info(f"      ❌ Content scoring: +0 (no job terms in title/snippet)")

        self.logger.info(f"      📊 FINAL SCORE: {score}")

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
                self.logger.info("")
                self.logger.info("="*70)
                self.logger.info(f"📋 QUERY {i}/{len(queries)}")
                self.logger.info("="*70)

                # Search and extract results
                results = await self._search_and_extract_results(query)

                self.logger.info("")
                self.logger.info(f"🔍 PROCESSING {len(results)} RESULTS")
                self.logger.info("-"*70)

                # Track decisions for this query
                query_stats = {
                    'excluded_big_boards': 0,
                    'excluded_duplicates': 0,
                    'excluded_low_score': 0,
                    'boards_added': 0,
                    'boards_updated': 0,
                }

                # Analyze results
                for result_num, result in enumerate(results, 1):
                    self.logger.info(f"\n🔎 Result {result_num}/{len(results)}")
                    self.logger.info("-"*70)

                    url = result.get('url', '')
                    if not url:
                        self.logger.warning(f"   ⚠️  Skipping: No URL in result")
                        continue

                    # Skip if already visited
                    if url in self.visited_urls:
                        self.logger.info(f"   ⏭️  SKIPPED: Already visited")
                        self.logger.info(f"      URL: {url}")
                        self.stats['excluded_duplicate_urls'] += 1
                        query_stats['excluded_duplicates'] += 1
                        continue

                    self.visited_urls.add(url)

                    # Skip excluded domains
                    if self._is_excluded_domain(url):
                        domain = self._extract_domain(url)
                        self.logger.info(f"   ⛔ EXCLUDED: Big job board")
                        self.logger.info(f"      Domain: {domain}")
                        self.logger.info(f"      URL: {url}")
                        self.stats['excluded_big_boards'] += 1
                        query_stats['excluded_big_boards'] += 1
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
                            self.logger.info(f"      ✨ NEW BOARD DISCOVERED!")
                            self.logger.info(f"         Domain: {domain}")
                            self.logger.info(f"         Score: {analysis['score']}")
                            self.logger.info(f"         Indicators: {', '.join(analysis['indicators'][:3])}")
                            self.stats['boards_added'] += 1
                            query_stats['boards_added'] += 1
                        else:
                            # Update score if higher
                            existing_score = self.discovered_boards[domain]['score']
                            if analysis['score'] > existing_score:
                                self.logger.info(f"      🔄 BOARD UPDATED (better score)")
                                self.logger.info(f"         Domain: {domain}")
                                self.logger.info(f"         Old score: {existing_score} → New score: {analysis['score']}")
                                self.discovered_boards[domain] = analysis
                                query_stats['boards_updated'] += 1
                            else:
                                self.logger.info(f"      ℹ️  SKIPPED: Domain already tracked with equal/higher score")
                                self.logger.info(f"         Domain: {domain}")
                                self.logger.info(f"         Existing score: {existing_score}, Current score: {analysis['score']}")
                    else:
                        self.logger.info(f"      ❌ REJECTED: Score too low (score: {analysis['score']})")
                        self.logger.info(f"         URL: {url}")
                        self.stats['excluded_low_score'] += 1
                        query_stats['excluded_low_score'] += 1

                # Query summary
                self.logger.info("")
                self.logger.info("="*70)
                self.logger.info(f"📊 QUERY {i} SUMMARY")
                self.logger.info("="*70)
                self.logger.info(f"   Results processed: {len(results)}")
                self.logger.info(f"   New boards added: {query_stats['boards_added']}")
                self.logger.info(f"   Boards updated: {query_stats['boards_updated']}")
                self.logger.info(f"   Excluded (big boards): {query_stats['excluded_big_boards']}")
                self.logger.info(f"   Excluded (duplicates): {query_stats['excluded_duplicates']}")
                self.logger.info(f"   Excluded (low score): {query_stats['excluded_low_score']}")
                self.logger.info(f"   Total boards discovered so far: {len(self.discovered_boards)}")
                self.logger.info("")

                # Overall stats every 5 queries
                if i % 5 == 0 or i == len(queries):
                    self._log_stats()
                    self.logger.info("")

                self.stats['queries_processed'] += 1

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
            'statistics': self.stats,
            'boards': boards_list
        }

        with open(output_path, 'w') as f:
            json.dump(output_data, f, indent=2)

        self.logger.info("")
        self.logger.info("="*70)
        self.logger.info(f"💾 RESULTS SAVED")
        self.logger.info("="*70)
        self.logger.info(f"   File: {output_path}")
        self.logger.info(f"   Total boards: {len(boards_list)}")
        if boards_list:
            self.logger.info(f"   Top score: {boards_list[0]['score']} ({boards_list[0]['domain']})")
            self.logger.info(f"   Lowest score: {boards_list[-1]['score']} ({boards_list[-1]['domain']})")
        self.logger.info("")


async def main():
    """Main entry point for testing."""
    finder = JobBoardFinder()

    try:
        # Discover job boards (limit to 5 queries for testing)
        boards = await finder.discover_job_boards(max_queries=5)

        # Save results
        finder.save_results()

        # Final summary
        print("\n")
        print("="*70)
        print("🎉 DISCOVERY COMPLETE!")
        print("="*70)
        print()
        print("📊 FINAL STATISTICS:")
        print("-"*70)
        print(f"Queries processed:       {finder.stats['queries_processed']}")
        print(f"Total results found:     {finder.stats['total_results_found']}")
        print(f"URLs visited:            {len(finder.visited_urls)}")
        print(f"Boards discovered:       {len(boards)}")
        print()
        print(f"EXCLUSIONS:")
        print(f"  Big job boards:        {finder.stats['excluded_big_boards']}")
        print(f"  Duplicate URLs:        {finder.stats['excluded_duplicate_urls']}")
        print(f"  Low score:             {finder.stats['excluded_low_score']}")
        print()
        print(f"ISSUES:")
        print(f"  Rate limits hit:       {finder.stats['rate_limits_hit']}")
        print(f"  Selector failures:     {finder.stats['selector_failures']}")
        print()

        if boards:
            print("="*70)
            print(f"🏆 TOP 10 DISCOVERED JOB BOARDS")
            print("="*70)
            sorted_boards = sorted(boards.values(), key=lambda x: x['score'], reverse=True)
            for i, board in enumerate(sorted_boards[:10], 1):
                print()
                print(f"{i}. {board['domain']}")
                print(f"   Score: {board['score']}")
                print(f"   URL: {board['url'][:75]}{'...' if len(board['url']) > 75 else ''}")
                print(f"   Title: {board['title'][:75]}{'...' if len(board['title']) > 75 else ''}")
                print(f"   Indicators: {', '.join(board['indicators'][:3])}")

            print()
            print("="*70)
            print(f"📁 Full results saved to: {finder.config['output']['file_path']}")
            print(f"📁 Debug files saved to: {DEBUG_DIR.absolute()}")
            print("="*70)
        else:
            print("⚠️  No job boards discovered. Check debug output for issues.")
            print("="*70)

    except Exception as e:
        print()
        print("="*70)
        print("❌ ERROR OCCURRED")
        print("="*70)
        print(f"Exception: {e}")
        print()
        print("Check the debug_output directory for HTML dumps and screenshots.")
        print("="*70)
        raise


if __name__ == '__main__':
    asyncio.run(main())
