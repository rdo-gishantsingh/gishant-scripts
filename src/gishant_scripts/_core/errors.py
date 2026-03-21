"""Custom exceptions for gishant scripts."""

from __future__ import annotations


class GishantScriptsError(Exception):
    """Base exception for all gishant scripts errors."""


class ConfigurationError(GishantScriptsError):
    """Raised when configuration is invalid or missing."""


class APIError(GishantScriptsError):
    """Raised when an API call fails."""


class ValidationError(GishantScriptsError):
    """Raised when data validation fails."""
