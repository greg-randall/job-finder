"""
Logging configuration and utilities for job scraper project.

Provides structured logging with:
- Clean console output for progress tracking
- Detailed file logging for debugging
- Error context capture with HTML dumps and screenshots
- LLM-friendly error reports in JSON format
"""

import logging
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from logging.handlers import RotatingFileHandler


class ScraperLogger:
    """Enhanced logger for scraper operations with error context capture."""

    def __init__(self, scraper_name: str):
        """
        Initialize logger for a specific scraper.

        Args:
            scraper_name: Name of the scraper (e.g., 'workday', 'adp')
        """
        self.scraper_name = scraper_name
        self.start_time = datetime.now()
        self.timestamp_str = self.start_time.strftime("%Y-%m-%d_%H%M%S")
        self.unix_timestamp = int(self.start_time.timestamp())

        # Create log directories
        self.log_dir = Path("logs")
        self.summary_dir = self.log_dir / "summaries"

        for directory in [self.log_dir, self.summary_dir]:
            directory.mkdir(exist_ok=True)

        # Create timestamped error folder in errors/unfixed
        self.error_dir = Path("errors") / "unfixed" / f"{scraper_name}_{self.unix_timestamp}"
        self.error_dir.mkdir(parents=True, exist_ok=True)

        # Store path to the main log file for later copying
        self.log_file_path = self.log_dir / f"scraper_{self.scraper_name}_{self.timestamp_str}.log"

        # Operation breadcrumbs for context
        self.operation_history: List[str] = []

        # Console message storage
        self.console_messages: List[Dict[str, Any]] = []
        self.max_console_messages = 100

        # Statistics tracking
        self.stats = {
            "start_time": self.start_time.isoformat(),
            "scraper": scraper_name,
            "sites_processed": 0,
            "sites_failed": 0,
            "total_jobs_found": 0,
            "total_jobs_downloaded": 0,
            "total_jobs_skipped": 0,
            "errors": 0,
            "warnings": 0,
        }

        # Set up logger
        self.logger = self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        """Set up logger with console and file handlers."""
        logger = logging.getLogger(f"scraper.{self.scraper_name}")
        logger.setLevel(logging.DEBUG)

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # Get log level from environment or default to INFO
        console_level_str = os.environ.get("SCRAPER_LOG_LEVEL", "INFO").upper()
        console_level = getattr(logging, console_level_str, logging.INFO)

        # Console handler - clean, formatted output
        console_handler = logging.StreamHandler()
        console_handler.setLevel(console_level)
        console_formatter = ColoredConsoleFormatter()
        console_handler.setFormatter(console_formatter)

        # File handler - detailed debug output
        file_handler = logging.FileHandler(self.log_file_path, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

        return logger

    def add_breadcrumb(self, operation: str):
        """Add an operation to the breadcrumb trail."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.operation_history.append(f"[{timestamp}] {operation}")

    def add_console_message(self, msg_type: str, message: str, timestamp: str):
        """Add a browser console message to the internal list."""
        if len(self.console_messages) >= self.max_console_messages:
            self.console_messages.pop(0)  # Remove the oldest message
        
        self.console_messages.append({
            'type': msg_type,
            'message': message,
            'timestamp': timestamp
        })

    async def attach_console_listener(self, page: Any):
        """Attach a listener to the browser's console events."""
        try:
            # Handler for standard console API calls (log, error, warn, etc.)
            async def on_console_api(event):
                msg_type = event['type']
                message = ' '.join([str(arg.get('value', '')) for arg in event['args']])
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000).isoformat()
                self.add_console_message(msg_type, message, timestamp)

            # Handler for uncaught exceptions in the page
            async def on_exception_thrown(event):
                exception_details = event['exceptionDetails']
                message = exception_details['exception']['description']
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000).isoformat()
                self.add_console_message('exception', message, timestamp)

            # Add listeners to the page
            await page.add_listener('Runtime.consoleAPICalled', on_console_api)
            await page.add_listener('Runtime.exceptionThrown', on_exception_thrown)
            
            self.info("Console listener attached successfully.")
        except Exception as e:
            self.warning(f"Failed to attach console listener: {e}")

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, extra=kwargs)
        self.add_breadcrumb(f"DEBUG: {message}")

    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, extra=kwargs)
        self.add_breadcrumb(f"INFO: {message}")

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, extra=kwargs)
        self.add_breadcrumb(f"WARNING: {message}")
        self.stats["warnings"] += 1

    def error(self, message: str, **kwargs):
        """Log error message."""
        self.logger.error(message, extra=kwargs)
        self.add_breadcrumb(f"ERROR: {message}")
        self.stats["errors"] += 1

    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self.logger.critical(message, extra=kwargs)
        self.add_breadcrumb(f"CRITICAL: {message}")
        self.stats["errors"] += 1

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) > len(s2):
            s1, s2 = s2, s1

        distances = range(len(s1) + 1)
        for i2, c2 in enumerate(s2):
            distances_ = [i2 + 1]
            for i1, c1 in enumerate(s1):
                if c1 == c2:
                    distances_.append(distances[i1])
                else:
                    distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
            distances = distances_
        return distances[-1]

    async def analyze_failed_selector(self, page, selector: str) -> Dict[str, Any]:
        """Run analysis in-browser to diagnose a failed selector."""
        try:
            # This script is executed in the browser's context
            js_script = """
            (selector) => {
                const analysis = {};
                try {
                    analysis.full_selector_count = document.querySelectorAll(selector).length;
                    
                    const parts = selector.split(' ').map(p => p.trim()).filter(p => p);
                    analysis.part_counts = {};
                    for (const part of parts) {
                        try {
                            analysis.part_counts[part] = document.querySelectorAll(part).length;
                        } catch (e) {
                            analysis.part_counts[part] = 'Error: ' + e.message;
                        }
                    }

                    const class_set = new Set();
                    document.querySelectorAll('[class]').forEach(el => {
                        el.classList.forEach(c => class_set.add(c));
                    });
                    analysis.all_class_names = Array.from(class_set);
                    
                    analysis.document_ready_state = document.readyState;
                    analysis.total_element_count = document.getElementsByTagName('*').length;

                } catch (e) {
                    analysis.error = 'Error during analysis: ' + e.message;
                }
                return analysis;
            }
            """
            analysis_result = await page.evaluate(js_script, selector)

            # Find similar class names
            if 'all_class_names' in analysis_result and analysis_result['all_class_names']:
                # A simple heuristic to find a class in the selector
                selector_class_match = re.search(r'\.([a-zA-Z0-9_-]+)', selector)
                if selector_class_match:
                    failed_class = selector_class_match.group(1)
                    similar_classes = []
                    for cls in analysis_result['all_class_names']:
                        distance = self._levenshtein_distance(failed_class, cls)
                        if distance < 3:  # Threshold for similarity
                            similar_classes.append({'class': cls, 'distance': distance})
                    
                    # Sort by distance and take the top 5
                    analysis_result['similar_classes'] = sorted(similar_classes, key=lambda x: x['distance'])[:5]

            return analysis_result
        except Exception as e:
            self.warning(f"Could not run selector analysis: {e}")
            return {"error": f"Failed to execute analysis script: {e}"}

    @staticmethod
    def clean_html_for_debugging(html_content: str) -> Tuple[str, Dict[str, int]]:
        """
        Clean HTML content by removing scripts, styles, inline styles, image data,
        non-whitelisted attributes, and SVG content.

        Args:
            html_content: Raw HTML content

        Returns:
            Tuple of (cleaned_html, statistics_dict)
        """
        stats = {
            'script_tags_removed': 0,
            'script_chars_removed': 0,
            'style_tags_removed': 0,
            'style_chars_removed': 0,
            'inline_styles_removed': 0,
            'image_data_urls_removed': 0,
            'svg_tags_cleaned': 0,
            'attributes_removed': 0
        }

        # Remove script tags and count them
        script_pattern = re.compile(r'<script\b[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL)
        scripts = script_pattern.findall(html_content)
        stats['script_tags_removed'] = len(scripts)
        stats['script_chars_removed'] = sum(len(s) for s in scripts)
        cleaned = script_pattern.sub('', html_content)

        # Remove style tags and count them
        style_pattern = re.compile(r'<style\b[^>]*>.*?</style>', re.IGNORECASE | re.DOTALL)
        styles = style_pattern.findall(cleaned)
        stats['style_tags_removed'] = len(styles)
        stats['style_chars_removed'] = sum(len(s) for s in styles)
        cleaned = style_pattern.sub('', cleaned)

        # Remove inline style attributes and count them
        inline_style_pattern = re.compile(r'\s+style\s*=\s*["\'][^"\']*["\']', re.IGNORECASE)
        inline_styles = inline_style_pattern.findall(cleaned)
        stats['inline_styles_removed'] = len(inline_styles)
        cleaned = inline_style_pattern.sub('', cleaned)

        # Remove image data URLs (src="data:image/...")
        image_data_pattern = re.compile(r'\s+src\s*=\s*["\']data:image/[^"\']*["\']', re.IGNORECASE)
        image_data_urls = image_data_pattern.findall(cleaned)
        stats['image_data_urls_removed'] = len(image_data_urls)
        cleaned = image_data_pattern.sub('', cleaned)

        # Clean SVG tags - keep opening/closing tags with whitelisted attributes, remove content
        svg_pattern = re.compile(r'<svg\b([^>]*)>(.*?)</svg>', re.IGNORECASE | re.DOTALL)
        def clean_svg(match):
            attrs = match.group(1)
            # Keep only whitelisted attributes from SVG tag
            cleaned_attrs = ScraperLogger._clean_attributes(attrs)
            stats['svg_tags_cleaned'] += 1
            return f'<svg{cleaned_attrs}><!-- SVG content removed --></svg>'

        cleaned = svg_pattern.sub(clean_svg, cleaned)

        # Remove non-whitelisted attributes from all tags
        # Whitelist: id, class, href, src, type, name, value, role, for, action, method, alt
        tag_pattern = re.compile(r'<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>', re.IGNORECASE)

        def clean_tag_attributes(match):
            tag_name = match.group(1)
            attrs = match.group(2)

            # Skip if no attributes
            if not attrs.strip():
                return match.group(0)

            original_attr_count = len(re.findall(r'\b[\w-]+\s*=', attrs))
            cleaned_attrs = ScraperLogger._clean_attributes(attrs)
            new_attr_count = len(re.findall(r'\b[\w-]+\s*=', cleaned_attrs))

            stats['attributes_removed'] += (original_attr_count - new_attr_count)

            return f'<{tag_name}{cleaned_attrs}>'

        cleaned = tag_pattern.sub(clean_tag_attributes, cleaned)

        # Add summary comment at the top
        summary_lines = []
        if stats['script_tags_removed'] > 0:
            summary_lines.append(
                f"<!-- Removed {stats['script_tags_removed']} <script> tag(s) "
                f"({stats['script_chars_removed']:,} characters of JavaScript) -->"
            )
        if stats['style_tags_removed'] > 0:
            summary_lines.append(
                f"<!-- Removed {stats['style_tags_removed']} <style> tag(s) "
                f"({stats['style_chars_removed']:,} characters of CSS) -->"
            )
        if stats['inline_styles_removed'] > 0:
            summary_lines.append(
                f"<!-- Removed {stats['inline_styles_removed']} inline style attribute(s) -->"
            )
        if stats['image_data_urls_removed'] > 0:
            summary_lines.append(
                f"<!-- Removed {stats['image_data_urls_removed']} image data URL(s) -->"
            )
        if stats['svg_tags_cleaned'] > 0:
            summary_lines.append(
                f"<!-- Cleaned {stats['svg_tags_cleaned']} SVG tag(s) (removed internal content) -->"
            )
        if stats['attributes_removed'] > 0:
            summary_lines.append(
                f"<!-- Removed {stats['attributes_removed']} non-whitelisted attribute(s) -->"
            )

        if summary_lines:
            summary = '\n'.join(summary_lines) + '\n\n'
            cleaned = summary + cleaned

        return cleaned, stats

    @staticmethod
    def _clean_attributes(attrs_string: str) -> str:
        """
        Clean attributes string, keeping only whitelisted attributes.

        Whitelisted attributes: id, class, href, src, type, name, value, role, for, action, method, alt

        Args:
            attrs_string: String containing HTML attributes

        Returns:
            Cleaned attributes string with only whitelisted attributes
        """
        whitelist = {'id', 'class', 'href', 'src', 'type', 'name', 'value', 'role', 'for', 'action', 'method', 'alt'}

        # Pattern to match individual attributes
        attr_pattern = re.compile(r'\b([\w-]+)\s*=\s*(["\'][^"\']*["\']|[^\s>]+)', re.IGNORECASE)

        cleaned_attrs = []
        for match in attr_pattern.finditer(attrs_string):
            attr_name = match.group(1).lower()
            attr_value = match.group(2)

            # Keep only whitelisted attributes
            if attr_name in whitelist:
                cleaned_attrs.append(f'{attr_name}={attr_value}')

        # Return with leading space if attributes exist
        if cleaned_attrs:
            return ' ' + ' '.join(cleaned_attrs)
        return ''

    async def capture_error_context(
        self,
        error_type: str,
        error_message: str,
        url: Optional[str] = None,
        page: Optional[Any] = None,  # nodriver Tab object
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        failed_selector: Optional[str] = None,
    ) -> str:
        """
        Capture comprehensive error context for LLM analysis.

        Args:
            error_type: Type of error (e.g., 'NavigationError', 'SelectorError')
            error_message: Human-readable error message
            url: URL where error occurred
            page: nodriver Tab object (for HTML dump and screenshot)
            stack_trace: Full stack trace
            context: Additional context dictionary
            failed_selector: The CSS selector that failed, if applicable.

        Returns:
            Path to the error context JSON file
        """
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y-%m-%d_%H%M%S_%f")[:-3]

        error_data = {
            "timestamp": timestamp.isoformat(),
            "error_type": error_type,
            "scraper": self.scraper_name,
            "url": url,
            "error_message": error_message,
            "stack_trace": stack_trace,
            "context": context or {},
            "operation_history": self.operation_history.copy(),
        }

        # Capture HTML dump and screenshot if page is available
        if page:
            try:
                # Get body HTML content only (more relevant for debugging)
                raw_html = await page.evaluate('document.body ? document.body.innerHTML : document.documentElement.outerHTML')

                # Clean the HTML to remove noise
                cleaned_html, cleaning_stats = self.clean_html_for_debugging(raw_html)

                # Save cleaned HTML
                html_file = self.error_dir / f"{timestamp_str}_page_dump.html"
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(cleaned_html)

                error_data["html_dump_file"] = str(html_file)
                error_data["html_preview"] = cleaned_html[:500] + "..." if len(cleaned_html) > 500 else cleaned_html
                error_data["html_size_bytes"] = len(cleaned_html)
                error_data["html_cleaning_stats"] = cleaning_stats

                self.logger.debug(f"Captured HTML dump: {html_file}")
                if cleaning_stats['script_tags_removed'] > 0 or cleaning_stats['style_tags_removed'] > 0:
                    self.logger.debug(
                        f"Cleaned HTML: removed {cleaning_stats['script_tags_removed']} scripts, "
                        f"{cleaning_stats['style_tags_removed']} styles, "
                        f"{cleaning_stats['inline_styles_removed']} inline styles"
                    )
            except Exception as e:
                error_data["html_capture_error"] = str(e)
                self.logger.warning(f"Failed to capture HTML: {e}")

            try:
                # Set viewport to 1920x1080 before capturing screenshot
                try:
                    await page.evaluate('''() => {
                        window.resizeTo(1920, 1080);
                    }''')
                    # Alternative method using CDP
                    await page.send(
                        'Emulation.setDeviceMetricsOverride',
                        {
                            'width': 1920,
                            'height': 1080,
                            'deviceScaleFactor': 1,
                            'mobile': False
                        }
                    )
                except Exception as resize_error:
                    self.logger.debug(f"Could not resize viewport for screenshot: {resize_error}")

                # Capture screenshot (nodriver uses save_screenshot)
                screenshot_file = self.error_dir / f"{timestamp_str}_screenshot.jpg"
                await page.save_screenshot(str(screenshot_file))
                error_data["screenshot_file"] = str(screenshot_file)
                self.logger.debug(f"Captured screenshot: {screenshot_file}")
            except Exception as e:
                error_data["screenshot_error"] = str(e)
                self.logger.warning(f"Failed to capture screenshot: {e}")

        # Run selector analysis if a failed selector is provided
        if failed_selector and page:
            analysis_data = await self.analyze_failed_selector(page, failed_selector)
            error_data["selector_analysis"] = analysis_data

        # Add console messages to the error data
        error_data["console_messages"] = self.console_messages.copy()

        # Write structured error JSON
        error_json_file = self.error_dir / f"{timestamp_str}_{error_type.lower()}.json"
        with open(error_json_file, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, indent=2, ensure_ascii=False)

        # Copy log excerpts to error folder
        self.copy_log_excerpts()

        self.logger.error(f"Error context saved: {error_json_file}")
        return str(error_json_file)

    def copy_log_excerpts(self):
        """
        Copy relevant log excerpts (errors, warnings, and context) to the error folder.

        This method extracts important log lines from the full log file and saves them
        to scraper.log in the error folder for easier debugging.
        """
        try:
            if not self.log_file_path.exists():
                self.logger.warning(f"Log file not found: {self.log_file_path}")
                return

            # Read the log file
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                log_lines = f.readlines()

            # Extract relevant lines (errors, warnings, and some context)
            relevant_lines = []
            context_buffer = []  # Keep last 3 lines for context
            context_size = 3

            for line in log_lines:
                # Add to context buffer
                context_buffer.append(line)
                if len(context_buffer) > context_size:
                    context_buffer.pop(0)

                # Check if line is important (ERROR, WARNING, CRITICAL)
                if any(level in line for level in ['ERROR', 'WARNING', 'CRITICAL']):
                    # Add context lines if not already added
                    for ctx_line in context_buffer[:-1]:
                        if ctx_line not in relevant_lines:
                            relevant_lines.append(ctx_line)
                    # Add the important line
                    if line not in relevant_lines:
                        relevant_lines.append(line)
                    context_buffer.clear()

            # Write excerpts to error folder
            excerpt_file = self.error_dir / "scraper.log"
            with open(excerpt_file, 'w', encoding='utf-8') as f:
                f.write(f"# Log excerpts from {self.scraper_name} (errors and warnings only)\n")
                f.write(f"# Full log available at: {self.log_file_path}\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n\n")
                f.writelines(relevant_lines)

            self.logger.debug(f"Log excerpts copied to: {excerpt_file}")
        except Exception as e:
            self.logger.warning(f"Failed to copy log excerpts: {e}")

    def update_stats(self, **kwargs):
        """Update statistics dictionary."""
        self.stats.update(kwargs)

    def increment_stat(self, stat_name: str, amount: int = 1):
        """Increment a statistic counter."""
        if stat_name in self.stats:
            self.stats[stat_name] += amount
        else:
            self.stats[stat_name] = amount

    def write_summary(self):
        """Write run summary to JSON file."""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        self.stats.update({
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "duration_human": f"{int(duration // 60)}m {int(duration % 60)}s",
        })

        summary_file = self.summary_dir / f"scraper_{self.scraper_name}_{self.timestamp_str}.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Summary written: {summary_file}")
        return summary_file


class ColoredConsoleFormatter(logging.Formatter):
    """Custom formatter for clean, emoji-enhanced console output."""

    # Emoji prefixes for different log levels
    FORMATS = {
        logging.DEBUG: "🔍 [DEBUG] %(message)s",
        logging.INFO: "[INFO] %(message)s",
        logging.WARNING: "⚠️  [WARN] %(message)s",
        logging.ERROR: "❌ [ERROR] %(message)s",
        logging.CRITICAL: "🚨 [CRITICAL] %(message)s",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, "%(message)s")
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_logger(scraper_name: str) -> ScraperLogger:
    """
    Get or create a logger for a specific scraper.

    Args:
        scraper_name: Name of the scraper (e.g., 'workday', 'adp')

    Returns:
        ScraperLogger instance
    """
    return ScraperLogger(scraper_name)


# Convenience function for simple logging without full ScraperLogger
def setup_simple_logger(name: str) -> logging.Logger:
    """
    Set up a simple logger for utility functions.

    Args:
        name: Logger name

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    console_level_str = os.environ.get("SCRAPER_LOG_LEVEL", "INFO").upper()
    console_level = getattr(logging, console_level_str, logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(ColoredConsoleFormatter())

    logger.addHandler(console_handler)

    return logger
