"""
Configuration loader for the job finder application.

This module provides utilities to load and access configuration from config.yaml.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


class Config:
    """Configuration class that loads and provides access to config.yaml settings."""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize configuration from YAML file.

        Args:
            config_path: Path to the configuration file (default: config.yaml)
        """
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value using dot notation.

        Args:
            key: Configuration key in dot notation (e.g., 'openai.model')
            default: Default value if key is not found

        Returns:
            Configuration value or default

        Example:
            config.get('openai.model')  # Returns 'gpt-4o-mini'
            config.get('rating.weights.experience')  # Returns 0.35
        """
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    def get_openai_config(self) -> Dict[str, Any]:
        """Get OpenAI configuration."""
        return self._config.get('openai', {})

    def get_location_config(self) -> Dict[str, Any]:
        """Get location configuration."""
        return self._config.get('location', {})

    def get_rating_config(self) -> Dict[str, Any]:
        """Get rating configuration."""
        return self._config.get('rating', {})

    def get_paths_config(self) -> Dict[str, Any]:
        """Get file paths configuration."""
        return self._config.get('paths', {})

    def get_processing_config(self) -> Dict[str, Any]:
        """Get processing configuration."""
        return self._config.get('processing', {})

    def get_browser_config(self) -> Dict[str, Any]:
        """Get browser configuration."""
        return self._config.get('browser', {})

    def get_job_boards(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get job boards configuration.

        Args:
            enabled_only: If True, return only enabled job boards (default: True)

        Returns:
            List of job board group configurations
        """
        boards = self._config.get('job_boards', [])
        if enabled_only:
            return [board for board in boards if board.get('enabled', True)]
        return boards

    def get_job_board_by_group(self, group_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific job board group by name.

        Args:
            group_name: Name of the job board group (e.g., 'workday', 'icims')

        Returns:
            Job board group configuration or None if not found
        """
        boards = self.get_job_boards(enabled_only=False)
        for board in boards:
            if board.get('group') == group_name:
                return board
        return None

    def get_enabled_sites(self, group_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all enabled sites, optionally filtered by group.

        Args:
            group_name: Optional group name to filter by

        Returns:
            List of enabled site configurations with their group info
        """
        enabled_sites = []
        boards = self.get_job_boards(enabled_only=True)

        for board in boards:
            if group_name and board.get('group') != group_name:
                continue

            sites = board.get('sites', [])
            for site in sites:
                if site.get('enabled', True):
                    # Add group metadata to site
                    site_with_group = site.copy()
                    site_with_group['_group'] = board.get('group')
                    site_with_group['_type'] = board.get('type')
                    site_with_group['_selectors'] = board.get('selectors', {})
                    site_with_group['_settings'] = board.get('settings', {})
                    enabled_sites.append(site_with_group)

        return enabled_sites

    def get_timeout(self, timeout_name: str, default: int = 20000) -> int:
        """
        Get a specific timeout value in milliseconds.

        Args:
            timeout_name: Name of the timeout (e.g., 'page_load_ms')
            default: Default value if not found

        Returns:
            Timeout value in milliseconds
        """
        return self.get(f'browser.timeouts.{timeout_name}', default)

    def get_retry_limit(self, limit_name: str, default: int = 3) -> int:
        """
        Get a specific retry limit.

        Args:
            limit_name: Name of the retry limit (e.g., 'max_retries')
            default: Default value if not found

        Returns:
            Retry limit value
        """
        return self.get(f'browser.retries.{limit_name}', default)

    def __repr__(self) -> str:
        """String representation of Config object."""
        return f"Config(config_path='{self.config_path}')"


# Global configuration instance
_config_instance: Optional[Config] = None


def get_config(config_path: str = "config.yaml") -> Config:
    """
    Get the global configuration instance (singleton pattern).

    Args:
        config_path: Path to the configuration file (default: config.yaml)

    Returns:
        Config instance
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance


def reload_config(config_path: str = "config.yaml") -> Config:
    """
    Reload the configuration from file.

    Args:
        config_path: Path to the configuration file (default: config.yaml)

    Returns:
        Reloaded Config instance
    """
    global _config_instance
    _config_instance = Config(config_path)
    return _config_instance


# Convenience functions for common config access
def get_openai_api_key() -> str:
    """
    Get OpenAI API key from environment variable.

    Returns:
        OpenAI API key

    Raises:
        ValueError: If API key is not found in environment
    """
    config = get_config()
    env_var = config.get('openai.api_key_env', 'OPENAI_API_KEY')
    api_key = os.getenv(env_var)
    if not api_key:
        raise ValueError(f"OpenAI API key not found in environment variable: {env_var}")
    return api_key


def get_cache_dir() -> Path:
    """Get cache directory path."""
    config = get_config()
    cache_dir = config.get('paths.cache_dir', 'cache')
    return Path(cache_dir)


def get_resume_path() -> Path:
    """Get resume file path."""
    config = get_config()
    resume_path = config.get('paths.resume', 'resume.md')
    return Path(resume_path)


def get_cover_letter_path() -> Optional[Path]:
    """Get cover letter file path (if configured)."""
    config = get_config()
    cover_letter = config.get('paths.cover_letter')
    return Path(cover_letter) if cover_letter else None
