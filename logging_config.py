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
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
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

        # Create log directories
        self.log_dir = Path("logs")
        self.error_dir = self.log_dir / "errors"
        self.summary_dir = self.log_dir / "summaries"

        for directory in [self.log_dir, self.error_dir, self.summary_dir]:
            directory.mkdir(exist_ok=True)

        # Operation breadcrumbs for context
        self.operation_history: List[str] = []

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
        log_file = self.log_dir / f"scraper_{self.scraper_name}_{self.timestamp_str}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
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

    async def capture_error_context(
        self,
        error_type: str,
        error_message: str,
        url: Optional[str] = None,
        page: Optional[Any] = None,  # Playwright page object
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Capture comprehensive error context for LLM analysis.

        Args:
            error_type: Type of error (e.g., 'NavigationError', 'SelectorError')
            error_message: Human-readable error message
            url: URL where error occurred
            page: Playwright page object (for HTML dump and screenshot)
            stack_trace: Full stack trace
            context: Additional context dictionary

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
                # Get HTML content
                html_content = await page.content()
                html_file = self.error_dir / f"{timestamp_str}_page_dump.html"
                with open(html_file, 'w', encoding='utf-8') as f:
                    f.write(html_content)

                error_data["html_dump_file"] = str(html_file)
                error_data["html_preview"] = html_content[:500] + "..." if len(html_content) > 500 else html_content
                error_data["html_size_bytes"] = len(html_content)

                self.logger.debug(f"Captured HTML dump: {html_file}")
            except Exception as e:
                error_data["html_capture_error"] = str(e)
                self.logger.warning(f"Failed to capture HTML: {e}")

            try:
                # Capture screenshot
                screenshot_file = self.error_dir / f"{timestamp_str}_screenshot.png"
                await page.screenshot(path=str(screenshot_file), full_page=True)
                error_data["screenshot_file"] = str(screenshot_file)
                self.logger.debug(f"Captured screenshot: {screenshot_file}")
            except Exception as e:
                error_data["screenshot_error"] = str(e)
                self.logger.warning(f"Failed to capture screenshot: {e}")

        # Write structured error JSON
        error_json_file = self.error_dir / f"{timestamp_str}_{error_type.lower()}.json"
        with open(error_json_file, 'w', encoding='utf-8') as f:
            json.dump(error_data, f, indent=2, ensure_ascii=False)

        self.logger.error(f"Error context saved: {error_json_file}")
        return str(error_json_file)

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
        logging.INFO: "📍 [INFO] %(message)s",
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
