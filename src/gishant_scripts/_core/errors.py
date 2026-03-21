"""Custom exceptions for gishant scripts."""


class GishantScriptsError(Exception):
    """Base exception for all gishant scripts errors."""

    pass


class ConfigurationError(GishantScriptsError):
    """Raised when configuration is invalid or missing."""

    pass


class APIError(GishantScriptsError):
    """Raised when an API call fails."""

    pass


class ValidationError(GishantScriptsError):
    """Raised when data validation fails."""

    pass
