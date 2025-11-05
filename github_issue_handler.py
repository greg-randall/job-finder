#!/usr/bin/env python3
"""
GitHub Issue Handler for Scraper Failures

This module manages automatic GitHub issue creation and updates when scrapers fail.
It aggregates error information and artifacts into a single issue per scraper.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import logging


class GitHubIssueHandler:
    """Handles creation and updating of GitHub issues for scraper failures."""

    def __init__(self, logger: logging.Logger):
        """
        Initialize the GitHub issue handler.

        Args:
            logger: Logger instance for output
        """
        self.logger = logger
        self.repo_root = Path(__file__).parent
        self.error_dir = self.repo_root / "logs" / "errors"

    def _run_gh_command(self, args: List[str], input_data: Optional[str] = None) -> Tuple[bool, str]:
        """
        Run a GitHub CLI command.

        Args:
            args: Command arguments (e.g., ['issue', 'list'])
            input_data: Optional stdin data

        Returns:
            Tuple of (success, output)
        """
        try:
            cmd = ["gh"] + args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                input=input_data,
                cwd=str(self.repo_root),
                timeout=30
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                self.logger.error(f"gh command failed: {result.stderr}")
                return False, result.stderr
        except subprocess.TimeoutExpired:
            self.logger.error("gh command timed out")
            return False, "Command timed out"
        except FileNotFoundError:
            self.logger.error("gh command not found. Please install GitHub CLI.")
            return False, "gh not installed"
        except Exception as e:
            self.logger.error(f"Error running gh command: {e}")
            return False, str(e)

    def find_existing_issue(self, scraper_name: str) -> Optional[int]:
        """
        Check if an open issue already exists for this scraper.

        Args:
            scraper_name: Name of the scraper

        Returns:
            Issue number if found, None otherwise
        """
        self.logger.debug(f"Checking for existing issue for scraper: {scraper_name}")

        # Search for open issues with the scraper label
        success, output = self._run_gh_command([
            "issue", "list",
            "--label", f"scraper:{scraper_name}",
            "--label", "scraper-failure",
            "--state", "open",
            "--json", "number,title",
            "--limit", "1"
        ])

        if not success:
            self.logger.warning(f"Could not search for existing issues: {output}")
            return None

        try:
            issues = json.loads(output)
            if issues and len(issues) > 0:
                issue_number = issues[0]['number']
                self.logger.info(f"Found existing issue #{issue_number} for {scraper_name}")
                return issue_number
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse issue list: {e}")

        return None

    def collect_error_artifacts(self, scraper_name: str) -> Dict[str, Optional[Path]]:
        """
        Collect one example of each error artifact type for a scraper.

        Args:
            scraper_name: Name of the scraper

        Returns:
            Dictionary with paths to artifacts (json, screenshot, html)
        """
        artifacts = {
            'json': None,
            'screenshot': None,
            'html': None
        }

        if not self.error_dir.exists():
            self.logger.warning(f"Error directory does not exist: {self.error_dir}")
            return artifacts

        # Get all error files sorted by modification time (most recent first)
        error_files = sorted(
            self.error_dir.glob("*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        # Find one of each type
        for file_path in error_files:
            if file_path.suffix == '.json' and artifacts['json'] is None:
                artifacts['json'] = file_path
            elif file_path.suffix == '.png' and artifacts['screenshot'] is None:
                artifacts['screenshot'] = file_path
            elif file_path.suffix == '.html' and artifacts['html'] is None:
                artifacts['html'] = file_path

            # Stop if we have all three
            if all(artifacts.values()):
                break

        self.logger.debug(f"Collected artifacts: {artifacts}")
        return artifacts

    def format_issue_body(
        self,
        scraper_name: str,
        scraper_url: str,
        error_summary: str,
        stats: Dict,
        artifacts: Dict[str, Optional[Path]],
        update: bool = False
    ) -> str:
        """
        Format the issue body markdown.

        Args:
            scraper_name: Name of the scraper
            scraper_url: URL that was being scraped
            error_summary: Summary of the error
            stats: Statistics dictionary
            artifacts: Dictionary of artifact paths
            update: Whether this is an update to an existing issue

        Returns:
            Formatted markdown string
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if update:
            body = f"\n\n---\n\n## Update: {timestamp}\n\n"
        else:
            body = f"## Scraper Failure Report\n\n"
            body += f"**Scraper:** `{scraper_name}`\n"
            body += f"**URL:** {scraper_url}\n\n"

        body += f"**Timestamp:** {timestamp}\n\n"

        # Error summary
        body += f"### Error Summary\n\n"
        body += f"{error_summary}\n\n"

        # Statistics
        body += f"### Statistics\n\n"
        body += f"- Pages scraped: {stats.get('pages_scraped', 0)}\n"
        body += f"- Jobs found: {stats.get('jobs_found', 0)}\n"
        body += f"- Jobs downloaded: {stats.get('jobs_downloaded', 0)}\n"
        body += f"- Errors: {stats.get('errors', 0)}\n\n"

        # Load and display error details from JSON if available
        if artifacts.get('json'):
            try:
                with open(artifacts['json'], 'r') as f:
                    error_data = json.load(f)

                body += f"### Error Details\n\n"
                body += f"**Error Type:** `{error_data.get('error_type', 'Unknown')}`\n"
                body += f"**Error Message:** {error_data.get('error_message', 'N/A')}\n\n"

                # Operation history (breadcrumbs)
                if error_data.get('operation_history'):
                    body += f"### Operation History\n\n"
                    body += "```\n"
                    for entry in error_data.get('operation_history', [])[-10:]:  # Last 10 operations
                        body += f"{entry}\n"
                    body += "```\n\n"

                # Stack trace
                if error_data.get('stack_trace'):
                    body += f"### Stack Trace\n\n"
                    body += f"```\n{error_data.get('stack_trace')}\n```\n\n"

            except Exception as e:
                self.logger.warning(f"Could not load error JSON: {e}")

        # Attachments note
        body += f"### Debug Artifacts\n\n"
        body += f"The following debug artifacts have been generated:\n\n"

        if artifacts.get('json'):
            body += f"- ✅ Error context JSON: `{artifacts['json'].name}`\n"
        else:
            body += f"- ❌ Error context JSON: Not available\n"

        if artifacts.get('screenshot'):
            body += f"- ✅ Screenshot: `{artifacts['screenshot'].name}`\n"
        else:
            body += f"- ❌ Screenshot: Not available\n"

        if artifacts.get('html'):
            body += f"- ✅ HTML dump: `{artifacts['html'].name}`\n"
        else:
            body += f"- ❌ HTML dump: Not available\n"

        body += "\n---\n"
        body += "*This issue was automatically generated by the scraper failure handler.*\n"

        return body

    def create_issue(
        self,
        scraper_name: str,
        scraper_url: str,
        error_summary: str,
        stats: Dict,
        artifacts: Dict[str, Optional[Path]]
    ) -> Optional[int]:
        """
        Create a new GitHub issue for a scraper failure.

        Args:
            scraper_name: Name of the scraper
            scraper_url: URL that was being scraped
            error_summary: Summary of the error
            stats: Statistics dictionary
            artifacts: Dictionary of artifact paths

        Returns:
            Issue number if created successfully, None otherwise
        """
        self.logger.info(f"Creating new issue for scraper: {scraper_name}")

        timestamp = datetime.now().strftime("%Y-%m-%d")
        title = f"Scraper Failure: {scraper_name} - {timestamp}"

        body = self.format_issue_body(
            scraper_name, scraper_url, error_summary, stats, artifacts, update=False
        )

        # Create the issue
        success, output = self._run_gh_command([
            "issue", "create",
            "--title", title,
            "--body", body,
            "--label", "scraper-failure",
            "--label", "auto-generated",
            "--label", f"scraper:{scraper_name}"
        ])

        if not success:
            self.logger.error(f"Failed to create issue: {output}")
            return None

        # Extract issue number from output
        try:
            # gh issue create returns URL like: https://github.com/owner/repo/issues/123
            issue_url = output.strip()
            issue_number = int(issue_url.split('/')[-1])
            self.logger.info(f"Created issue #{issue_number}: {issue_url}")

            # Upload artifacts as attachments
            self._upload_artifacts(issue_number, artifacts)

            return issue_number
        except (ValueError, IndexError) as e:
            self.logger.error(f"Could not parse issue number from output: {e}")
            return None

    def update_issue(
        self,
        issue_number: int,
        scraper_name: str,
        scraper_url: str,
        error_summary: str,
        stats: Dict,
        artifacts: Dict[str, Optional[Path]]
    ) -> bool:
        """
        Update an existing GitHub issue with new failure information.

        Args:
            issue_number: The issue number to update
            scraper_name: Name of the scraper
            scraper_url: URL that was being scraped
            error_summary: Summary of the error
            stats: Statistics dictionary
            artifacts: Dictionary of artifact paths

        Returns:
            True if updated successfully, False otherwise
        """
        self.logger.info(f"Updating issue #{issue_number} for scraper: {scraper_name}")

        update_body = self.format_issue_body(
            scraper_name, scraper_url, error_summary, stats, artifacts, update=True
        )

        # Add comment to existing issue
        success, output = self._run_gh_command([
            "issue", "comment", str(issue_number),
            "--body", update_body
        ])

        if not success:
            self.logger.error(f"Failed to update issue: {output}")
            return False

        self.logger.info(f"Successfully updated issue #{issue_number}")

        # Upload new artifacts
        self._upload_artifacts(issue_number, artifacts)

        return True

    def _upload_artifacts(self, issue_number: int, artifacts: Dict[str, Optional[Path]]) -> None:
        """
        Upload artifact files as attachments to the issue.

        Note: GitHub CLI doesn't support direct file uploads to issues via gh issue command.
        Files would need to be uploaded via the API or manually referenced in comments.
        For now, we just log the artifact locations.

        Args:
            issue_number: The issue number
            artifacts: Dictionary of artifact paths
        """
        self.logger.info(f"Artifacts for issue #{issue_number}:")
        for artifact_type, path in artifacts.items():
            if path:
                self.logger.info(f"  {artifact_type}: {path}")

    def handle_scraper_failure(
        self,
        scraper_name: str,
        scraper_url: str,
        error_summary: str,
        stats: Dict
    ) -> bool:
        """
        Main entry point for handling a scraper failure.

        This will either create a new issue or update an existing one.

        Args:
            scraper_name: Name of the scraper that failed
            scraper_url: URL that was being scraped
            error_summary: Summary of what went wrong
            stats: Statistics dictionary from the scraper

        Returns:
            True if issue was created/updated successfully, False otherwise
        """
        try:
            # Collect artifacts
            artifacts = self.collect_error_artifacts(scraper_name)

            # Check for existing issue
            existing_issue = self.find_existing_issue(scraper_name)

            if existing_issue:
                # Update existing issue
                return self.update_issue(
                    existing_issue,
                    scraper_name,
                    scraper_url,
                    error_summary,
                    stats,
                    artifacts
                )
            else:
                # Create new issue
                issue_number = self.create_issue(
                    scraper_name,
                    scraper_url,
                    error_summary,
                    stats,
                    artifacts
                )
                return issue_number is not None

        except Exception as e:
            self.logger.error(f"Error handling scraper failure: {e}")
            return False


def report_scraper_failure(
    scraper_name: str,
    scraper_url: str,
    error_summary: str,
    stats: Dict,
    logger: logging.Logger
) -> bool:
    """
    Convenience function to report a scraper failure.

    Args:
        scraper_name: Name of the scraper that failed
        scraper_url: URL that was being scraped
        error_summary: Summary of what went wrong
        stats: Statistics dictionary from the scraper
        logger: Logger instance

    Returns:
        True if issue was created/updated successfully, False otherwise
    """
    handler = GitHubIssueHandler(logger)
    return handler.handle_scraper_failure(
        scraper_name,
        scraper_url,
        error_summary,
        stats
    )
