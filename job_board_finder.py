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
from typing import Dict, List, Set, Tuple, Optional
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

        # Per-domain adaptive rate limiting for validation
        self.domain_delays: Dict[str, float] = {}  # domain -> current delay in seconds

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
        """Save current page HTML for debugging with enhanced cleaning."""
        try:
            from logging_config import ScraperLogger

            html_content = await self.tab.evaluate('document.documentElement.outerHTML')
            page_url = await self.tab.evaluate('window.location.href')
            page_title = await self.tab.evaluate('document.title')

            # Clean the HTML using the enhanced cleaning function
            cleaned_html, cleaning_stats = ScraperLogger.clean_html_for_debugging(html_content)

            debug_file = DEBUG_DIR / f"{filename}.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(f"<!-- URL: {page_url} -->\n")
                f.write(f"<!-- Title: {page_title} -->\n")
                f.write(f"<!-- Description: {description} -->\n")
                f.write(f"<!-- Timestamp: {datetime.now().isoformat()} -->\n\n")
                f.write(cleaned_html)

            self.logger.info(f"💾 Debug HTML saved: {debug_file}")
            if cleaning_stats.get('attributes_removed', 0) > 0 or cleaning_stats.get('svg_tags_cleaned', 0) > 0:
                self.logger.debug(
                    f"   Cleaned: {cleaning_stats.get('attributes_removed', 0)} attrs, "
                    f"{cleaning_stats.get('svg_tags_cleaned', 0)} SVGs, "
                    f"{cleaning_stats.get('image_data_urls_removed', 0)} image data URLs"
                )
            return debug_file
        except Exception as e:
            self.logger.error(f"Failed to save debug HTML: {e}")
            return None

    async def _save_debug_screenshot(self, filename: str):
        """Save screenshot for debugging."""
        try:
            screenshot_file = DEBUG_DIR / f"{filename}.jpg"
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
        import random

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

        # RANDOMIZE order to avoid hitting same sites during debugging
        random.shuffle(queries)
        self.logger.info(f"   ⚡ Randomized query order")

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

    async def _adaptive_rate_limit(self, domain: str) -> float:
        """
        Adaptive rate limiting per domain for validation.
        Starts at 0.5s, doubles on 429/404 up to 30s.
        Returns the current delay being used.
        """
        # Initialize domain delay if not seen before
        if domain not in self.domain_delays:
            self.domain_delays[domain] = 0.5  # Start with 0.5 seconds

        delay = self.domain_delays[domain]
        self.logger.debug(f"      ⏱️  Domain delay for {domain}: {delay}s")
        await asyncio.sleep(delay)
        return delay

    def _increase_domain_delay(self, domain: str, reason: str = "error"):
        """Double the delay for a domain, capping at 30 seconds."""
        current = self.domain_delays.get(domain, 0.5)
        new_delay = min(current * 2, 30.0)  # Cap at 30 seconds
        self.domain_delays[domain] = new_delay
        self.logger.info(f"      ⚠️  Increased delay for {domain}: {current}s → {new_delay}s (reason: {reason})")

    def _reset_domain_delay(self, domain: str):
        """Reset domain delay back to initial 0.5s after success."""
        if domain in self.domain_delays and self.domain_delays[domain] > 0.5:
            old_delay = self.domain_delays[domain]
            self.domain_delays[domain] = 0.5
            self.logger.debug(f"      ✅ Reset delay for {domain}: {old_delay}s → 0.5s")

    async def _handle_429_error(self, retry_count: int) -> bool:
        """
        Handle 429 Too Many Requests error with exponential backoff.
        Returns True if should retry, False if max retries exceeded.
        """
        self.stats['rate_limits_hit'] += 1
        max_retries = self.config['search_engine']['rate_limit']['max_retries']

        if retry_count >= max_retries:
            self.logger.error(f"❌ Max retries ({max_retries}) exceeded for 429 errors")
            self.logger.error(f"   Total 429 errors this session: {self.stats['rate_limits_hit']}")
            return False

        # Exponential backoff: 30s, 60s, 120s, 240s...
        base_delay = self.config['search_engine']['rate_limit']['retry_delay_seconds']
        exponential_delay = base_delay * (2 ** retry_count)

        # Add jitter (randomize by ±20%) to appear more human-like
        import random
        jitter = exponential_delay * 0.2 * (random.random() * 2 - 1)  # ±20%
        actual_delay = exponential_delay + jitter

        self.logger.warning(f"⚠️  429 Too Many Requests detected!")
        self.logger.warning(f"   Retry {retry_count + 1}/{max_retries}")
        self.logger.warning(f"   Base delay: {base_delay}s")
        self.logger.warning(f"   Exponential backoff: {exponential_delay}s")
        self.logger.warning(f"   With jitter: {actual_delay:.1f}s")
        self.logger.warning(f"   Sleeping {actual_delay:.1f}s before retry...")

        await asyncio.sleep(actual_delay)
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

    async def _wait_for_results_rendered(self, wait_seconds: int = 5) -> bool:
        """
        Wait for search results to be rendered, then check if they exist.

        Args:
            wait_seconds: Seconds to wait before checking for results.

        Returns:
            True if results were found, False otherwise.
        """
        self.logger.info(f"⏳ Waiting {wait_seconds}s for results to render...")

        # Simple wait - results render quickly after search submission
        await asyncio.sleep(wait_seconds)

        try:
            # Direct synchronous check - no Promise needed
            articles_count = await self.tab.evaluate('document.querySelectorAll("article").length')
            links_count = await self.tab.evaluate('document.querySelectorAll("a[href^=\\"http\\"]").length')

            if articles_count > 0 or links_count > 5:
                self.logger.info(f"✅ Results found: {articles_count} articles, {links_count} http links")
                return True
            else:
                self.logger.warning(f"⚠️  No results found after {wait_seconds}s wait")
                return False

        except Exception as e:
            self.logger.error(f"Error checking for results: {e}")
            return False

    async def _perform_interactive_search(self, query: str) -> bool:
        """
        Perform an interactive search by filling the search form and clicking submit.

        Args:
            query: The search query to enter.

        Returns:
            True if search was performed successfully, False otherwise.
        """
        try:
            self.logger.info(f"🔍 Performing interactive search for: '{query}'")

            # Navigate to homepage first
            base_url = self.config['search_engine']['base_url'].split('/search')[0]
            self.logger.info(f"📍 Navigating to: {base_url}")

            try:
                await asyncio.wait_for(self.tab.get(base_url), timeout=20)
            except asyncio.TimeoutError:
                self.logger.warning("Navigation timeout, but continuing...")

            await asyncio.sleep(2)  # Give page time to load

            # Find and focus on search input
            self.logger.info("🔎 Looking for search input box...")
            search_input = await self.tab.select('#search')

            if not search_input:
                self.logger.error("❌ Could not find search input box")
                return False

            self.logger.info("✅ Found search input box")

            # Click the input to focus it
            await search_input.click()
            await asyncio.sleep(0.5)

            # Type the query
            self.logger.info(f"⌨️  Typing query: '{query}'")
            await search_input.send_keys(query)
            await asyncio.sleep(1)

            # Find and click search button
            self.logger.info("🔘 Looking for search button...")
            search_button = await self.tab.select('button[type="submit"][aria-label="Search"]')

            if not search_button:
                self.logger.error("❌ Could not find search button")
                return False

            self.logger.info("✅ Found search button, clicking...")
            await search_button.click()

            # Wait for navigation/results to load
            self.logger.info("⏳ Waiting for search results to load...")
            await asyncio.sleep(3)

            return True

        except Exception as e:
            self.logger.error(f"❌ Error performing interactive search: {e}")
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

        # per-query hard timeout (configurable, fallback to 90s - increased for interactive search)
        per_query_timeout = self.config.get('search_engine', {}).get('per_query_timeout_seconds', 90)
        query_start = time.time()

        while retry_count <= self.config['search_engine']['rate_limit']['max_retries']:
            # stop if overall per-query timeout exceeded
            if time.time() - query_start > per_query_timeout:
                self.logger.error(f"⏰ Query timeout exceeded ({per_query_timeout}s) for query: {query}")
                break

            try:
                # Rate limit
                await self._rate_limit()

                # Use interactive search instead of direct URL navigation
                search_success = await self._perform_interactive_search(query)

                if not search_success:
                    self.logger.error("❌ Interactive search failed")
                    retry_count += 1
                    continue

                # Get page info
                page_url = await self.tab.evaluate('window.location.href')
                page_title = await self.tab.evaluate('document.title')
                self.logger.info(f"✅ Search submitted successfully")
                self.logger.info(f"   Current URL: {page_url}")
                self.logger.info(f"   Page title: {page_title}")

                # Check for 429
                if await self._check_for_429():
                    self.logger.warning("⚠️  Detected 429 error on page")
                    await self._save_debug_html(f"429_error_{int(time.time())}", "429 rate limit page")
                    if await self._handle_429_error(retry_count):
                        retry_count += 1
                        continue
                    else:
                        break

                # Wait for results to be dynamically rendered
                if not await self._wait_for_results_rendered(wait_seconds=5):
                    self.logger.error("❌ Results were not found after waiting")
                    timestamp = int(time.time())
                    await self._save_debug_html(f"render_timeout_{timestamp}", f"Results not rendered for: {query}")
                    await self._save_debug_screenshot(f"render_timeout_{timestamp}")
                    retry_count += 1
                    continue

                # Extract results from article elements (Leta uses <article> for each result)
                self.logger.info("🔍 Extracting results from rendered page...")

                # Use Python HTML parsing instead of JavaScript extraction
                try:
                    from bs4 import BeautifulSoup

                    # Get the page HTML
                    html_content = await self.tab.get_content()
                    soup = BeautifulSoup(html_content, 'html.parser')

                    # Find all article elements
                    articles = soup.find_all('article')
                    self.logger.info(f"   Found {len(articles)} article elements on page")

                    results_data = []
                    for i, article in enumerate(articles):
                        try:
                            # Find the first link in the article
                            link = article.find('a', href=True)
                            if not link or not link.get('href'):
                                self.logger.warning(f"   ✗ Article {i}: no link found")
                                continue

                            # Get URL
                            url = link.get('href')
                            if not url.startswith('http'):
                                self.logger.warning(f"   ✗ Article {i}: invalid URL: {url}")
                                continue

                            # Get title from h3
                            h3 = article.find('h3')
                            title = h3.get_text(strip=True) if h3 else ''

                            # Get snippet from p.result__body
                            snippet_p = article.find('p', class_='result__body')
                            snippet = snippet_p.get_text(strip=True) if snippet_p else ''

                            results_data.append({
                                'url': url.strip(),
                                'title': title[:200] if title else '',
                                'snippet': snippet[:500] if snippet else ''
                            })
                            self.logger.info(f"   ✓ Extracted result {i+1}: {title[:50]}...")

                        except Exception as e:
                            self.logger.warning(f"   ✗ Error extracting article {i}: {e}")
                            continue

                    self.logger.info(f"   Successfully extracted {len(results_data)} results from {len(articles)} articles")

                except ImportError:
                    self.logger.error("   BeautifulSoup4 not installed. Please install with: pip install beautifulsoup4")
                    results_data = []
                except Exception as e:
                    self.logger.error(f"   Error during extraction: {e}")
                    results_data = []

                if results_data and len(results_data) > 0:
                    results = results_data
                    self.stats['total_results_found'] += len(results)
                    self.logger.info(f"✅ Extracted {len(results)} results")

                    for i, result in enumerate(results, 1):
                        domain = self._extract_domain(result['url'])
                        self.logger.info(f"   [{i}] {domain}")
                        self.logger.info(f"       URL: {result['url'][:80]}{'...' if len(result['url']) > 80 else ''}")
                        self.logger.info(f"       Title: {result['title'][:80]}{'...' if len(result['title']) > 80 else ''}")

                    # success, break retry loop
                    break
                else:
                    self.logger.warning("⚠️  No results extracted (empty results array)")
                    self.stats['selector_failures'] += 1
                    timestamp = int(time.time())
                    await self._save_debug_html(f"no_results_{timestamp}", f"No results extracted for: {query}")
                    await self._save_debug_screenshot(f"no_results_{timestamp}")

                    # Try to collect page structure for debugging
                    try:
                        body_structure = await self.tab.evaluate('''() => {
                            const body = document.body;
                            const classes = Array.from(body.querySelectorAll('[class]')).map(el => el.className).slice(0, 20);
                            const ids = Array.from(body.querySelectorAll('[id]')).map(el => el.id).slice(0, 20);
                            const articles = document.querySelectorAll('article').length;
                            const links = document.querySelectorAll('a[href^="http"]').length;
                            return { classes: [...new Set(classes)], ids: [...new Set(ids)], articles, links };
                        }''')
                        self.logger.error(f"   Page has {body_structure.get('articles', 0)} articles, {body_structure.get('links', 0)} http links")
                        self.logger.error(f"   Page classes: {body_structure.get('classes', [])[:5]}")
                        self.logger.error(f"   Page IDs: {body_structure.get('ids', [])[:5]}")
                    except Exception as e:
                        self.logger.error(f"   Could not extract page structure: {e}")

                    # Retry with next iteration
                    retry_count += 1
                    continue

            except Exception as e:
                self.logger.error(f"❌ EXCEPTION during search for '{query}': {e}", exc_info=True)
                try:
                    timestamp = int(time.time())
                    await self._save_debug_html(f"exception_{timestamp}", f"Exception during search: {str(e)}")
                    await self._save_debug_screenshot(f"exception_{timestamp}")
                except Exception:
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

    async def _score_job_board_page(self) -> Dict:
        """
        Score the current page based on job board indicators.
        Returns dict with score, job_count, has_pagination, and other metadata.
        """
        try:
            from bs4 import BeautifulSoup

            # Get page HTML
            html_content = await self.tab.get_content()
            soup = BeautifulSoup(html_content, 'html.parser')

            score = 0.0
            job_count = 0
            has_pagination = False

            # Check for pagination indicators
            pagination_selectors = [
                'nav[aria-label*="pagination"]',
                'nav[aria-label*="Pagination"]',
                '.pagination',
                'ul.pagination',
                'div.pagination',
                'a[aria-label*="next page"]',
                'a[aria-label*="Next page"]',
                'button[aria-label*="next"]',
                'a:contains("Next")',
                'a:contains("››")',
                'span:contains("Page")',
            ]

            for selector in pagination_selectors:
                if ':contains' not in selector:
                    if soup.select(selector):
                        has_pagination = True
                        score += 2.0
                        break

            # Try to find job count from text
            body_text = soup.get_text()
            import re

            # Look for patterns like "Found X jobs", "X jobs", "Showing X of Y", etc.
            job_count_patterns = [
                r'(?:found|showing)\s+(\d+)\s+(?:job|position|opening|career|opportunit)',
                r'(\d+)\s+(?:job|position|opening|career|opportunit)(?:s)?\s+(?:found|available)',
                r'(?:page\s+\d+\s+of\s+\d+)',
            ]

            for pattern in job_count_patterns:
                match = re.search(pattern, body_text.lower())
                if match:
                    try:
                        count = int(match.group(1))
                        job_count = count
                        score += min(count / 10, 5.0)  # Cap at 5 points
                        break
                    except (ValueError, IndexError):
                        pass

            # Count visible job listing elements
            job_listing_selectors = [
                '[data-testid*="job"]',
                '[class*="job-listing"]',
                '[class*="job-card"]',
                '[class*="job_card"]',
                '[class*="jobCard"]',
                'article[class*="job"]',
                'div[class*="job-item"]',
                'li[class*="job"]',
                '.job',
                '[id*="job-"]',
            ]

            visible_jobs = 0
            for selector in job_listing_selectors:
                elements = soup.select(selector)
                if len(elements) > visible_jobs:
                    visible_jobs = len(elements)

            # Score based on visible job elements
            if visible_jobs >= self.config['validation']['min_job_listings']:
                score += min(visible_jobs, 10.0)  # Cap at 10 points

            self.logger.debug(f"      Page score: {score:.1f} (pagination={has_pagination}, job_count={job_count}, visible={visible_jobs})")

            return {
                'score': score,
                'job_count': job_count,
                'has_pagination': has_pagination,
                'visible_job_elements': visible_jobs
            }

        except Exception as e:
            self.logger.debug(f"      Error scoring page: {e}")
            return {
                'score': 0.0,
                'job_count': 0,
                'has_pagination': False,
                'visible_job_elements': 0
            }

    async def _try_url_patterns(self, initial_url: str) -> Optional[Dict]:
        """
        Try common URL patterns to find the main job board page.
        Returns dict with best_url and metadata, or None if original is best.
        """
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(initial_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        # Generate candidate URLs from config patterns
        patterns = self.config['validation']['url_patterns']
        candidates = [initial_url]  # Start with original

        # Add pattern-based URLs
        for pattern in patterns:
            candidate = base_url + pattern
            if candidate not in candidates:
                candidates.append(candidate)

        # Add URL variations
        # Remove query params
        if parsed.query:
            no_query = urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
            if no_query not in candidates:
                candidates.append(no_query)

        # Try parent path
        path_parts = parsed.path.rstrip('/').split('/')
        if len(path_parts) > 2:  # Has more than just /something
            parent_path = '/'.join(path_parts[:-1]) + '/'
            parent_url = base_url + parent_path
            if parent_url not in candidates:
                candidates.append(parent_url)

        # Try base domain
        if base_url not in candidates:
            candidates.append(base_url)

        # Limit to max_patterns
        max_patterns = self.config['validation']['max_patterns_per_board']
        candidates = candidates[:max_patterns]

        self.logger.info(f"   📋 Trying {len(candidates)} URL patterns...")

        # Extract domain for adaptive rate limiting
        domain = parsed.netloc.lower().replace('www.', '')

        best_result = None
        best_score = 0.0

        for i, url in enumerate(candidates):
            try:
                # Adaptive rate limit between requests (0.5s initially, doubles on errors up to 30s)
                if i > 0:
                    await self._adaptive_rate_limit(domain)

                self.logger.debug(f"      Testing: {url}")

                # Navigate to URL with timeout
                timeout = self.config['validation']['timeout_per_url']
                try:
                    await asyncio.wait_for(self.tab.get(url), timeout=timeout)
                    await wait_for_load(self.tab)

                    # Check for 404 or 429 errors
                    status_code = None
                    try:
                        # Try to detect error pages
                        title = await self.tab.evaluate('document.title')
                        body_text = await self.tab.evaluate('document.body?.innerText || ""')

                        if '404' in title or '404' in body_text[:200]:
                            self.logger.debug(f"      🚫 404 Not Found: {url}")
                            self._increase_domain_delay(domain, "404")
                            continue
                        elif '429' in title or 'too many requests' in body_text.lower()[:500]:
                            self.logger.info(f"      ⚠️  429 Rate Limit: {url}")
                            self._increase_domain_delay(domain, "429")
                            continue
                    except Exception:
                        pass  # Continue if we can't check status

                except asyncio.TimeoutError:
                    self.logger.debug(f"      ⏱️  Timeout loading {url}")
                    self._increase_domain_delay(domain, "timeout")
                    continue

                # Score the page
                page_score = await self._score_job_board_page()

                # Success! Can reset delay on next iteration
                if page_score['score'] > 0:
                    self._reset_domain_delay(domain)

                if page_score['score'] > best_score:
                    best_score = page_score['score']
                    best_result = {
                        'url': url,
                        'method': f"pattern_{url.replace(base_url, '')}",
                        **page_score
                    }
                    self.logger.info(f"      ✨ New best: {url} (score={best_score:.1f})")

            except Exception as e:
                self.logger.debug(f"      ❌ Error testing {url}: {e}")
                self._increase_domain_delay(domain, "exception")
                continue

        return best_result

    async def _spider_menu_links(self, base_url: str) -> List[str]:
        """
        Extract job-related links from the site's main navigation menu.
        Returns list of candidate URLs to check.
        """
        try:
            from bs4 import BeautifulSoup
            from urllib.parse import urljoin

            # Navigate to base URL
            await self.tab.get(base_url)
            await wait_for_load(self.tab)

            # Get page HTML
            html_content = await self.tab.get_content()
            soup = BeautifulSoup(html_content, 'html.parser')

            # Find navigation elements
            nav_selectors = [
                'nav',
                'header nav',
                '[role="navigation"]',
                '.nav',
                '.navigation',
                '.menu',
                '#menu',
                'header',
            ]

            menu_links = []
            job_keywords = ['job', 'career', 'work', 'employ', 'opportunity', 'hiring', 'opening', 'position', 'join']

            for selector in nav_selectors:
                nav_elements = soup.select(selector)
                for nav in nav_elements:
                    # Find all links in this nav element
                    links = nav.find_all('a', href=True)
                    for link in links:
                        href = link.get('href')
                        text = link.get_text(strip=True).lower()

                        # Check if link text or href contains job keywords
                        if any(keyword in text or keyword in href.lower() for keyword in job_keywords):
                            # Make absolute URL
                            absolute_url = urljoin(base_url, href)
                            if absolute_url not in menu_links:
                                menu_links.append(absolute_url)
                                self.logger.debug(f"      Found menu link: {text} -> {absolute_url}")

            self.logger.info(f"   📋 Found {len(menu_links)} job-related menu links")
            return menu_links

        except Exception as e:
            self.logger.debug(f"   Error spidering menu links: {e}")
            return []

    async def _find_main_job_board_page(self, initial_url: str) -> Dict:
        """
        Find the main job board listing page using two-stage validation.
        Returns dict with validation results.
        """
        from urllib.parse import urlparse

        domain = urlparse(initial_url).netloc
        self.logger.info(f"🔍 Validating: {domain}")
        self.logger.info(f"   Original URL: {initial_url}")

        # Stage 1: Try URL patterns
        self.logger.info(f"   🎯 Stage 1: Pattern-based URL discovery")
        best_result = await self._try_url_patterns(initial_url)

        # Stage 2: Spider menu links if Stage 1 didn't find good page
        if self.config['validation']['spider_menu'] and (
            not best_result or best_result['score'] < self.config['validation']['min_job_listings']
        ):
            self.logger.info(f"   🕷️  Stage 2: Spidering menu links")
            base_url = f"{urlparse(initial_url).scheme}://{urlparse(initial_url).netloc}"
            menu_links = await self._spider_menu_links(base_url)

            # Test menu links with adaptive rate limiting
            domain = urlparse(initial_url).netloc.lower().replace('www.', '')
            for link in menu_links[:5]:  # Limit to first 5 menu links
                try:
                    await self._adaptive_rate_limit(domain)

                    timeout = self.config['validation']['timeout_per_url']
                    await asyncio.wait_for(self.tab.get(link), timeout=timeout)
                    await wait_for_load(self.tab)

                    page_score = await self._score_job_board_page()

                    # Success! Reset delay
                    if page_score['score'] > 0:
                        self._reset_domain_delay(domain)

                    if not best_result or page_score['score'] > best_result['score']:
                        link_text = link.split('/')[-1] or 'root'
                        best_result = {
                            'url': link,
                            'method': f"menu_link_{link_text}",
                            **page_score
                        }
                        self.logger.info(f"      ✨ New best from menu: {link} (score={best_result['score']:.1f})")

                except asyncio.TimeoutError:
                    self.logger.debug(f"      ⏱️  Timeout checking menu link: {link}")
                    self._increase_domain_delay(domain, "timeout")
                    continue
                except Exception as e:
                    self.logger.debug(f"      ❌ Error checking menu link {link}: {e}")
                    self._increase_domain_delay(domain, "exception")
                    continue

        # Determine validation status
        if best_result and best_result['url'] != initial_url:
            validation_status = 'validated'
            self.logger.info(f"   ✅ Found better URL: {best_result['url']}")
            self.logger.info(f"      Method: {best_result['method']}, Score: {best_result['score']:.1f}")
        elif best_result:
            validation_status = 'needs_review'
            self.logger.info(f"   ⚠️  Original URL is best (score={best_result['score']:.1f})")
        else:
            validation_status = 'needs_review'
            best_result = {
                'url': initial_url,
                'method': 'original',
                'score': 0.0,
                'job_count': 0,
                'has_pagination': False,
                'visible_job_elements': 0
            }
            self.logger.info(f"   ⚠️  Could not validate, keeping original")

        return {
            'url': best_result['url'],
            'original_url': initial_url,
            'validation_status': validation_status,
            'job_count': best_result.get('job_count', 0),
            'has_pagination': best_result.get('has_pagination', False),
            'visible_job_elements': best_result.get('visible_job_elements', 0),
            'discovery_method': best_result.get('method', 'original')
        }

    async def validate_discovered_boards(self):
        """
        Validate discovered boards by finding their main job board listing pages.
        Updates self.discovered_boards with validation results.
        """
        if not self.config['validation']['enabled']:
            self.logger.info("⚠️  Validation disabled in config")
            return

        self.logger.info("")
        self.logger.info("="*70)
        self.logger.info("🔍 VALIDATION PHASE: Finding main job board pages")
        self.logger.info("="*70)
        self.logger.info(f"Validating {len(self.discovered_boards)} discovered boards...")
        self.logger.info("")

        for i, (domain, board) in enumerate(list(self.discovered_boards.items()), 1):
            self.logger.info(f"[{i}/{len(self.discovered_boards)}] Validating {domain}")

            try:
                validation_result = await self._find_main_job_board_page(board['url'])

                # Update board entry with validation results
                self.discovered_boards[domain].update(validation_result)

            except Exception as e:
                self.logger.error(f"   ❌ Validation failed for {domain}: {e}")
                # Mark as needs review on error
                self.discovered_boards[domain]['validation_status'] = 'needs_review'
                self.discovered_boards[domain]['original_url'] = board['url']

            self.logger.info("")

        # Summary
        validated = sum(1 for b in self.discovered_boards.values() if b.get('validation_status') == 'validated')
        needs_review = sum(1 for b in self.discovered_boards.values() if b.get('validation_status') == 'needs_review')

        self.logger.info("="*70)
        self.logger.info("📊 VALIDATION SUMMARY")
        self.logger.info("="*70)
        self.logger.info(f"   ✅ Validated (found better URL): {validated}")
        self.logger.info(f"   ⚠️  Needs review: {needs_review}")
        self.logger.info("")

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

            # Validation phase: Find main job board pages
            if self.discovered_boards:
                await self.validate_discovered_boards()

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
        # Discover job boards (limit to 1 query for testing)
        boards = await finder.discover_job_boards(max_queries=1)

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
