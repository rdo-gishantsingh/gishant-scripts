"""Unit tests for the prefix-safety validation in remove_projects."""

from __future__ import annotations

import pytest
import typer

from gishant_scripts.testdata.remove_projects import validate_prefix


class TestValidatePrefix:
    """Tests for the prefix-safety validator."""

    def test_empty_prefix_exits(self) -> None:
        """An empty prefix must raise typer.Exit with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            validate_prefix("")
        assert exc_info.value.exit_code == 1

    def test_prefix_without_leading_underscore_exits(self) -> None:
        """A prefix without a leading underscore must raise typer.Exit with code 1."""
        with pytest.raises(typer.Exit) as exc_info:
            validate_prefix("test_")
        assert exc_info.value.exit_code == 1

    def test_prefix_with_leading_underscore_ok(self) -> None:
        """A well-formed prefix must not raise."""
        # Should return None without raising.
        assert validate_prefix("_test_edl_ingester_") is None

    def test_single_underscore_prefix_ok(self) -> None:
        """A bare underscore is technically valid."""
        assert validate_prefix("_") is None
