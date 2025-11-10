"""Tests for common.config module."""

import os
from unittest.mock import patch

import pytest

from gishant_scripts.common.config import (
    AppConfig,
    AYONConfig,
    GitHubConfig,
    GoogleAIConfig,
    YouTrackConfig,
)
from gishant_scripts.common.errors import ConfigurationError


class TestYouTrackConfig:
    """Test YouTrackConfig dataclass."""

    def test_from_env_success(self):
        """Test successful loading from environment."""
        with patch.dict(
            os.environ,
            {
                "YOUTRACK_URL": "https://test.youtrack.cloud",
                "YOUTRACK_API_TOKEN": "test-token-123",
            },
        ):
            config = YouTrackConfig.from_env()
            assert config.url == "https://test.youtrack.cloud"
            assert config.api_token == "test-token-123"

    def test_from_env_missing_url(self):
        """Test loading with missing URL."""
        with patch.dict(os.environ, {"YOUTRACK_API_TOKEN": "test-token"}, clear=True):
            config = YouTrackConfig.from_env()
            assert config.url is None
            assert config.api_token == "test-token"

    def test_from_env_missing_token(self):
        """Test loading with missing token."""
        with patch.dict(os.environ, {"YOUTRACK_URL": "https://test.youtrack.cloud"}, clear=True):
            config = YouTrackConfig.from_env()
            assert config.url == "https://test.youtrack.cloud"
            assert config.api_token is None

    def test_validate_success(self):
        """Test successful validation."""
        config = YouTrackConfig(url="https://test.youtrack.cloud", api_token="test-token")
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_missing_url(self):
        """Test validation with missing URL."""
        config = YouTrackConfig(url=None, api_token="test-token")
        errors = config.validate()
        assert "url" in errors
        assert "YOUTRACK_URL" in errors["url"]

    def test_validate_missing_token(self):
        """Test validation with missing token."""
        config = YouTrackConfig(url="https://test.youtrack.cloud", api_token=None)
        errors = config.validate()
        assert "api_token" in errors
        assert "YOUTRACK_API_TOKEN" in errors["api_token"]

    def test_validate_both_missing(self):
        """Test validation with both fields missing."""
        config = YouTrackConfig(url=None, api_token=None)
        errors = config.validate()
        assert len(errors) == 2
        assert "url" in errors
        assert "api_token" in errors


class TestGitHubConfig:
    """Test GitHubConfig dataclass."""

    def test_from_env_with_token(self):
        """Test loading with token."""
        with patch.dict(os.environ, {"GITHUB_TOKEN": "gh-token-123"}):
            config = GitHubConfig.from_env()
            assert config.token == "gh-token-123"

    def test_from_env_without_token(self):
        """Test loading without token (optional)."""
        with patch.dict(os.environ, {}, clear=True):
            config = GitHubConfig.from_env()
            assert config.token is None

    def test_validate_always_passes(self):
        """Test validation always passes (token is optional)."""
        config = GitHubConfig(token=None)
        errors = config.validate()
        assert len(errors) == 0

        config = GitHubConfig(token="test-token")
        errors = config.validate()
        assert len(errors) == 0


class TestGoogleAIConfig:
    """Test GoogleAIConfig dataclass."""

    def test_from_env_success(self):
        """Test successful loading from environment."""
        with patch.dict(os.environ, {"GOOGLE_AI_API_KEY": "ai-key-123"}):
            config = GoogleAIConfig.from_env()
            assert config.api_key == "ai-key-123"

    def test_from_env_missing(self):
        """Test loading with missing API key."""
        with patch.dict(os.environ, {}, clear=True):
            config = GoogleAIConfig.from_env()
            assert config.api_key is None

    def test_validate_success(self):
        """Test successful validation."""
        config = GoogleAIConfig(api_key="test-key")
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_missing(self):
        """Test validation with missing key."""
        config = GoogleAIConfig(api_key=None)
        errors = config.validate()
        assert "api_key" in errors
        assert "GOOGLE_AI_API_KEY" in errors["api_key"]


class TestAYONConfig:
    """Test AYONConfig dataclass."""

    def test_from_env_complete(self):
        """Test loading with all fields."""
        with patch.dict(
            os.environ,
            {
                "AYON_SERVER_URL": "https://ayon.example.com",
                "AYON_API_KEY": "ayon-key-123",
            },
        ):
            config = AYONConfig.from_env()
            assert config.server_url == "https://ayon.example.com"
            assert config.api_key == "ayon-key-123"

    def test_from_env_missing(self):
        """Test loading with missing fields (optional)."""
        with patch.dict(os.environ, {}, clear=True):
            config = AYONConfig.from_env()
            assert config.server_url is None
            assert config.api_key is None

    def test_validate_always_passes(self):
        """Test validation always passes (optional config)."""
        config = AYONConfig(server_url=None, api_key=None)
        errors = config.validate()
        assert len(errors) == 0


class TestAppConfig:
    """Test AppConfig orchestrator."""

    def test_load_all_configs(self):
        """Test loading all configuration sections."""
        with patch.dict(
            os.environ,
            {
                "YOUTRACK_URL": "https://test.youtrack.cloud",
                "YOUTRACK_API_TOKEN": "yt-token",
                "GITHUB_TOKEN": "gh-token",
                "GOOGLE_AI_API_KEY": "ai-key",
                "AYON_SERVER_URL": "https://ayon.example.com",
                "AYON_API_KEY": "ayon-key",
            },
        ):
            config = AppConfig(load_env=False)
            assert config.youtrack.url == "https://test.youtrack.cloud"
            assert config.youtrack.api_token == "yt-token"
            assert config.github.token == "gh-token"
            assert config.google_ai.api_key == "ai-key"
            assert config.ayon.server_url == "https://ayon.example.com"
            assert config.ayon.api_key == "ayon-key"

    def test_validate_no_errors(self):
        """Test validate with all configs valid."""
        with patch.dict(
            os.environ,
            {
                "YOUTRACK_URL": "https://test.youtrack.cloud",
                "YOUTRACK_API_TOKEN": "yt-token",
                "GOOGLE_AI_API_KEY": "ai-key",
            },
        ):
            config = AppConfig(load_env=False)
            errors = config.validate()
            # All service dicts should be empty
            assert all(not service_errors for service_errors in errors.values())

    def test_validate_specific_service(self):
        """Test validate for specific service."""
        with patch.dict(os.environ, {"YOUTRACK_URL": "https://test.youtrack.cloud"}, clear=True):
            config = AppConfig(load_env=False)
            errors = config.validate(["youtrack"])
            assert "youtrack" in errors
            # Should have api_token error
            assert "api_token" in errors["youtrack"]

    def test_validate_multiple_services(self):
        """Test validate for multiple services."""
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig(load_env=False)
            errors = config.validate(["youtrack", "google_ai"])
            assert "youtrack" in errors
            assert "google_ai" in errors
            assert len(errors["youtrack"]) == 2  # url and api_token
            assert len(errors["google_ai"]) == 1  # api_key

    def test_require_valid_success(self):
        """Test require_valid with valid config."""
        with patch.dict(
            os.environ,
            {
                "YOUTRACK_URL": "https://test.youtrack.cloud",
                "YOUTRACK_API_TOKEN": "yt-token",
            },
        ):
            config = AppConfig(load_env=False)
            config.require_valid("youtrack")  # Should not raise

    def test_require_valid_raises(self):
        """Test require_valid raises ConfigurationError."""
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig(load_env=False)
            with pytest.raises(ConfigurationError) as exc_info:
                config.require_valid("youtrack")
            error_msg = str(exc_info.value)
            assert "youtrack" in error_msg.lower()
            assert "YOUTRACK_URL" in error_msg
            assert "YOUTRACK_API_TOKEN" in error_msg

    def test_require_valid_multiple_services(self):
        """Test require_valid with multiple services."""
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig(load_env=False)
            with pytest.raises(ConfigurationError) as exc_info:
                config.require_valid("youtrack", "google_ai")
            error_msg = str(exc_info.value)
            assert "youtrack" in error_msg.lower()
            assert "google_ai" in error_msg.lower()
