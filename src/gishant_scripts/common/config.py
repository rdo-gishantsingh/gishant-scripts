"""Configuration management for gishant scripts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from gishant_scripts.common.errors import ConfigurationError


@dataclass
class YouTrackConfig:
    """YouTrack API configuration."""

    url: str | None
    api_token: str | None

    @classmethod
    def from_env(cls) -> YouTrackConfig:
        """Load configuration from environment variables.

        Expected variables:
            YOUTRACK_URL: YouTrack instance URL
            YOUTRACK_API_TOKEN: API token for authentication

        Returns:
            YouTrackConfig instance
        """
        return cls(
            url=os.getenv("YOUTRACK_URL") or None,
            api_token=os.getenv("YOUTRACK_API_TOKEN") or None,
        )

    def validate(self) -> dict[str, str]:
        """Validate configuration.

        Returns:
            Dict of field names to error messages (empty if valid)
        """
        errors = {}
        if not self.url:
            errors["url"] = "YOUTRACK_URL not set"
        if not self.api_token:
            errors["api_token"] = "YOUTRACK_API_TOKEN not set"
        return errors


@dataclass
class GitHubConfig:
    """GitHub API configuration."""

    token: str | None = None

    @classmethod
    def from_env(cls) -> GitHubConfig:
        """Load configuration from environment variables.

        Expected variables:
            GITHUB_TOKEN: GitHub personal access token (optional if using gh CLI)

        Returns:
            GitHubConfig instance
        """
        return cls(token=os.getenv("GITHUB_TOKEN"))

    def validate(self) -> dict[str, str]:
        """Validate configuration.

        Returns:
            Dict of field names to error messages (empty if valid)
        """
        # GitHub token is optional since we can use gh CLI
        return {}


@dataclass
class GoogleAIConfig:
    """Google AI API configuration."""

    api_key: str | None

    @classmethod
    def from_env(cls) -> GoogleAIConfig:
        """Load configuration from environment variables.

        Expected variables:
            GOOGLE_AI_API_KEY: Google AI API key

        Returns:
            GoogleAIConfig instance
        """
        return cls(api_key=os.getenv("GOOGLE_AI_API_KEY") or None)

    def validate(self) -> dict[str, str]:
        """Validate configuration.

        Returns:
            Dict of field names to error messages (empty if valid)
        """
        errors = {}
        if not self.api_key:
            errors["api_key"] = "GOOGLE_AI_API_KEY not set"
        return errors


@dataclass
class AYONConfig:
    """AYON API configuration."""

    server_url: str | None = None
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> AYONConfig:
        """Load configuration from environment variables.

        Expected variables:
            AYON_SERVER_URL: AYON server URL (optional, uses ayon_api defaults)
            AYON_API_KEY: AYON API key (optional, uses ayon_api defaults)

        Returns:
            AYONConfig instance
        """
        return cls(
            server_url=os.getenv("AYON_SERVER_URL"),
            api_key=os.getenv("AYON_API_KEY"),
        )

    def validate(self) -> dict[str, str]:
        """Validate configuration.

        Returns:
            Dict of field names to error messages (empty if valid)
        """
        # AYON config is optional since ayon_api uses its own config
        return {}


class AppConfig:
    """Main application configuration loader."""

    def __init__(self, env_file: Path | None = None, load_env: bool = True):
        """Initialize configuration from environment.

        Args:
            env_file: Optional path to .env file. If not provided,
                     looks for .env in current directory or ~/.gishant_scripts.env
            load_env: Whether to load from .env files (default True). Set False in tests.

        Raises:
            ConfigurationError: If configuration is invalid
        """
        # Load .env file
        if load_env:
            if env_file and env_file.exists():
                load_dotenv(env_file)
            else:
                # Try default locations
                for default in [
                    Path(".env"),
                    Path.home() / ".gishant_scripts.env",
                ]:
                    if default.exists():
                        load_dotenv(default)
                        break

        # Load all configurations
        self.youtrack = YouTrackConfig.from_env()
        self.github = GitHubConfig.from_env()
        self.google_ai = GoogleAIConfig.from_env()
        self.ayon = AYONConfig.from_env()

        # Store output directory
        self.output_dir = Path(os.getenv("OUTPUT_DIR", "./output"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

    def validate(self, services: list[str] | None = None) -> dict[str, dict[str, str]]:
        """Validate configurations for specified services.

        Args:
            services: List of service names to validate. If None, validates all.
                     Valid names: 'youtrack', 'github', 'google_ai', 'ayon'

        Returns:
            Dictionary mapping service names to dicts of field errors

        Example:
            >>> config = AppConfig()
            >>> errors = config.validate(['youtrack'])
            >>> if errors['youtrack']:
            ...     print("YouTrack config invalid")
        """
        all_services = {
            "youtrack": self.youtrack,
            "github": self.github,
            "google_ai": self.google_ai,
            "ayon": self.ayon,
        }

        if services is None:
            services = list(all_services.keys())

        return {service: all_services[service].validate() for service in services if service in all_services}

    def require_valid(self, *services: str) -> None:
        """Require specified services to have valid configuration.

        Args:
            *services: Service names that must be configured

        Raises:
            ConfigurationError: If any specified service has invalid config

        Example:
            >>> config = AppConfig()
            >>> config.require_valid('youtrack')  # Raises if invalid
        """
        errors = self.validate(list(services))

        all_errors = []
        for service, field_errors in errors.items():
            if field_errors:
                for field, error_msg in field_errors.items():
                    all_errors.append(f"{service}.{field}: {error_msg}")

        if all_errors:
            raise ConfigurationError("Configuration validation failed:\n  - " + "\n  - ".join(all_errors))
