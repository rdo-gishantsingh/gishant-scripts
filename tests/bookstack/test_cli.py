"""Tests for BookStack CLI."""

import os
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from gishant_scripts.bookstack.cli import app

runner = CliRunner()


@pytest.fixture
def mock_env():
    """Set up mock environment variables."""
    env_vars = {
        "BOOKSTACK_URL": "https://test.bookstack.local",
        "BOOKSTACK_TOKEN_ID": "test_token_id",
        "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
    }
    with patch.dict(os.environ, env_vars):
        yield


class TestBookStackCLI:
    """Test BookStack CLI commands."""

    def test_help(self):
        """Test help output."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "BookStack API CLI" in result.output

    def test_pages_help(self):
        """Test pages subcommand help."""
        result = runner.invoke(app, ["pages", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "read" in result.output
        assert "create" in result.output
        assert "update" in result.output
        assert "delete" in result.output
        assert "export" in result.output

    def test_chapters_help(self):
        """Test chapters subcommand help."""
        result = runner.invoke(app, ["chapters", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output

    def test_books_help(self):
        """Test books subcommand help."""
        result = runner.invoke(app, ["books", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output

    def test_shelves_help(self):
        """Test shelves subcommand help."""
        result = runner.invoke(app, ["shelves", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output

    def test_attachments_help(self):
        """Test attachments subcommand help."""
        result = runner.invoke(app, ["attachments", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create-link" in result.output
        assert "create-file" in result.output

    def test_users_help(self):
        """Test users subcommand help."""
        result = runner.invoke(app, ["users", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "create" in result.output

    def test_pages_create_dry_run(self, mock_env):
        """Test pages create in dry-run mode."""
        result = runner.invoke(
            app,
            ["pages", "create", "Test Page", "--book", "1"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Test Page" in result.output

    def test_pages_create_requires_parent(self, mock_env):
        """Test pages create requires book or chapter."""
        result = runner.invoke(
            app,
            ["pages", "create", "Test Page"],
        )
        assert result.exit_code == 1
        assert "book" in result.output.lower() or "chapter" in result.output.lower()

    def test_chapters_create_dry_run(self, mock_env):
        """Test chapters create in dry-run mode."""
        result = runner.invoke(
            app,
            ["chapters", "create", "1", "Test Chapter"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Test Chapter" in result.output

    def test_books_create_dry_run(self, mock_env):
        """Test books create in dry-run mode."""
        result = runner.invoke(
            app,
            ["books", "create", "Test Book"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Test Book" in result.output

    def test_shelves_create_dry_run(self, mock_env):
        """Test shelves create in dry-run mode."""
        result = runner.invoke(
            app,
            ["shelves", "create", "Test Shelf"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Test Shelf" in result.output

    def test_pages_delete_dry_run(self, mock_env):
        """Test pages delete in dry-run mode."""
        result = runner.invoke(
            app,
            ["pages", "delete", "123"],
        )
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Delete Page" in result.output

    def test_search_requires_config(self):
        """Test search requires configuration."""
        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, ["search", "test query"])
            assert result.exit_code == 1
            assert "Configuration" in result.output or "Error" in result.output

    def test_info_requires_config(self):
        """Test info requires configuration."""
        with patch.dict(os.environ, {}, clear=True):
            result = runner.invoke(app, ["info"])
            assert result.exit_code == 1
            assert "Configuration" in result.output or "Error" in result.output


class TestDryRunBehavior:
    """Test dry-run behavior across commands."""

    @pytest.fixture
    def env_with_config(self):
        """Environment with valid config."""
        env_vars = {
            "BOOKSTACK_URL": "https://test.bookstack.local",
            "BOOKSTACK_TOKEN_ID": "test_token_id",
            "BOOKSTACK_TOKEN_SECRET": "test_token_secret",
        }
        with patch.dict(os.environ, env_vars):
            yield

    def test_create_commands_default_dry_run(self, env_with_config):
        """Test that create commands default to dry-run."""
        commands = [
            ["pages", "create", "Test", "--book", "1"],
            ["chapters", "create", "1", "Test"],
            ["books", "create", "Test"],
            ["shelves", "create", "Test"],
            ["users", "create", "Test", "test@test.com"],
        ]

        for cmd in commands:
            result = runner.invoke(app, cmd)
            assert "DRY RUN" in result.output, f"Command {cmd} should default to dry-run"

    def test_update_commands_default_dry_run(self, env_with_config):
        """Test that update commands default to dry-run."""
        commands = [
            ["pages", "update", "1", "--name", "New Name"],
            ["chapters", "update", "1", "--name", "New Name"],
            ["books", "update", "1", "--name", "New Name"],
            ["shelves", "update", "1", "--name", "New Name"],
        ]

        for cmd in commands:
            result = runner.invoke(app, cmd)
            assert "DRY RUN" in result.output, f"Command {cmd} should default to dry-run"

    def test_delete_commands_default_dry_run(self, env_with_config):
        """Test that delete commands default to dry-run."""
        commands = [
            ["pages", "delete", "1"],
            ["chapters", "delete", "1"],
            ["books", "delete", "1"],
            ["shelves", "delete", "1"],
            ["attachments", "delete", "1"],
            ["users", "delete", "1"],
        ]

        for cmd in commands:
            result = runner.invoke(app, cmd)
            assert "DRY RUN" in result.output, f"Command {cmd} should default to dry-run"
