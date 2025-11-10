"""Tests for core.errors module."""

import pytest

from gishant_scripts.common.errors import (
    APIError,
    ConfigurationError,
    GishantScriptsError,
    ValidationError,
)


class TestExceptionHierarchy:
    """Test custom exception hierarchy."""

    def test_base_exception(self):
        """Test GishantScriptsError base exception."""
        error = GishantScriptsError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_configuration_error(self):
        """Test ConfigurationError inherits from base."""
        error = ConfigurationError("Config error")
        assert str(error) == "Config error"
        assert isinstance(error, GishantScriptsError)
        assert isinstance(error, Exception)

    def test_api_error(self):
        """Test APIError inherits from base."""
        error = APIError("API error")
        assert str(error) == "API error"
        assert isinstance(error, GishantScriptsError)
        assert isinstance(error, Exception)

    def test_validation_error(self):
        """Test ValidationError inherits from base."""
        error = ValidationError("Validation error")
        assert str(error) == "Validation error"
        assert isinstance(error, GishantScriptsError)
        assert isinstance(error, Exception)

    def test_exception_with_details(self):
        """Test exceptions can include detailed messages."""
        error = ConfigurationError("Missing configuration: YOUTRACK_API_TOKEN not found in environment")
        assert "YOUTRACK_API_TOKEN" in str(error)
        assert "Missing configuration" in str(error)

    def test_exception_raising(self):
        """Test exceptions can be raised and caught."""
        with pytest.raises(ConfigurationError) as exc_info:
            raise ConfigurationError("Test config error")
        assert str(exc_info.value) == "Test config error"

        with pytest.raises(GishantScriptsError) as exc_info:
            raise APIError("Test API error")
        assert str(exc_info.value) == "Test API error"
