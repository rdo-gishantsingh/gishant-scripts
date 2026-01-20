"""Tests for BookStack configuration."""

import os
from unittest.mock import patch

import pytest

from gishant_scripts.common.config import AppConfig, BookStackConfig
from gishant_scripts.common.errors import ConfigurationError


class TestBookStackConfig:
    """Test BookStackConfig dataclass."""

    def test_from_env_success(self):
        """Test successful loading from environment."""
        with patch.dict(
            os.environ,
            {
                "BOOKSTACK_URL": "https://docs.example.com",
                "BOOKSTACK_TOKEN_ID": "test_token_id",
                "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
            },
        ):
            config = BookStackConfig.from_env()
            assert config.url == "https://docs.example.com"
            assert config.token_id == "test_token_id"
            assert config.token_secret == "test_token_secret"

    def test_from_env_missing_url(self):
        """Test loading with missing URL."""
        with patch.dict(
            os.environ,
            {
                "BOOKSTACK_TOKEN_ID": "test_token_id",
                "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
            },
            clear=True,
        ):
            config = BookStackConfig.from_env()
            assert config.url is None
            assert config.token_id == "test_token_id"
            assert config.token_secret == "test_token_secret"

    def test_from_env_missing_token_id(self):
        """Test loading with missing token ID."""
        with patch.dict(
            os.environ,
            {
                "BOOKSTACK_URL": "https://docs.example.com",
                "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
            },
            clear=True,
        ):
            config = BookStackConfig.from_env()
            assert config.url == "https://docs.example.com"
            assert config.token_id is None
            assert config.token_secret == "test_token_secret"

    def test_from_env_missing_token_secret(self):
        """Test loading with missing token secret."""
        with patch.dict(
            os.environ,
            {
                "BOOKSTACK_URL": "https://docs.example.com",
                "BOOKSTACK_TOKEN_ID": "test_token_id",
            },
            clear=True,
        ):
            config = BookStackConfig.from_env()
            assert config.url == "https://docs.example.com"
            assert config.token_id == "test_token_id"
            assert config.token_secret is None

    def test_validate_success(self):
        """Test successful validation."""
        config = BookStackConfig(
            url="https://docs.example.com",
            token_id="test_token_id",
            token_secret="test_token_secret",
        )
        errors = config.validate()
        assert len(errors) == 0

    def test_validate_missing_url(self):
        """Test validation with missing URL."""
        config = BookStackConfig(
            url=None,
            token_id="test_token_id",
            token_secret="test_token_secret",
        )
        errors = config.validate()
        assert "url" in errors
        assert "BOOKSTACK_URL" in errors["url"]

    def test_validate_missing_token_id(self):
        """Test validation with missing token ID."""
        config = BookStackConfig(
            url="https://docs.example.com",
            token_id=None,
            token_secret="test_token_secret",
        )
        errors = config.validate()
        assert "token_id" in errors
        assert "BOOKSTACK_TOKEN_ID" in errors["token_id"]

    def test_validate_missing_token_secret(self):
        """Test validation with missing token secret."""
        config = BookStackConfig(
            url="https://docs.example.com",
            token_id="test_token_id",
            token_secret=None,
        )
        errors = config.validate()
        assert "token_secret" in errors
        assert "BOOKSTACK_TOKEN_SECRET" in errors["token_secret"]

    def test_validate_all_missing(self):
        """Test validation with all fields missing."""
        config = BookStackConfig(url=None, token_id=None, token_secret=None)
        errors = config.validate()
        assert len(errors) == 3
        assert "url" in errors
        assert "token_id" in errors
        assert "token_secret" in errors


class TestAppConfigBookStack:
    """Test AppConfig with BookStack integration."""

    def test_loads_bookstack_config(self):
        """Test that AppConfig loads BookStack configuration."""
        with patch.dict(
            os.environ,
            {
                "BOOKSTACK_URL": "https://docs.example.com",
                "BOOKSTACK_TOKEN_ID": "test_token_id",
                "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
            },
        ):
            config = AppConfig(load_env=False)
            assert config.bookstack is not None
            assert config.bookstack.url == "https://docs.example.com"
            assert config.bookstack.token_id == "test_token_id"
            assert config.bookstack.token_secret == "test_token_secret"

    def test_validate_bookstack(self):
        """Test validating BookStack configuration."""
        with patch.dict(
            os.environ,
            {
                "BOOKSTACK_URL": "https://docs.example.com",
                "BOOKSTACK_TOKEN_ID": "test_token_id",
                "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
            },
        ):
            config = AppConfig(load_env=False)
            errors = config.validate(["bookstack"])
            assert "bookstack" in errors
            assert len(errors["bookstack"]) == 0

    def test_validate_bookstack_errors(self):
        """Test validating invalid BookStack configuration."""
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig(load_env=False)
            errors = config.validate(["bookstack"])
            assert "bookstack" in errors
            assert len(errors["bookstack"]) == 3

    def test_require_valid_bookstack_success(self):
        """Test require_valid with valid BookStack config."""
        with patch.dict(
            os.environ,
            {
                "BOOKSTACK_URL": "https://docs.example.com",
                "BOOKSTACK_TOKEN_ID": "test_token_id",
                "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
            },
        ):
            config = AppConfig(load_env=False)
            config.require_valid("bookstack")  # Should not raise

    def test_require_valid_bookstack_raises(self):
        """Test require_valid raises for invalid BookStack config."""
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig(load_env=False)
            with pytest.raises(ConfigurationError) as exc_info:
                config.require_valid("bookstack")
            error_msg = str(exc_info.value)
            assert "bookstack" in error_msg.lower()
            assert "BOOKSTACK_URL" in error_msg
            assert "BOOKSTACK_TOKEN_ID" in error_msg
            assert "BOOKSTACK_TOKEN_SECRET" in error_msg
