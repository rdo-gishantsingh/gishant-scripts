"""Unit tests for YouTrackIssueCreator.validate_issue_data() pure logic."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from gishant_scripts.youtrack.creator import YouTrackIssueCreator


@pytest.fixture()
def creator() -> YouTrackIssueCreator:
    """Create a YouTrackIssueCreator with dummy credentials (no real HTTP calls)."""
    return YouTrackIssueCreator(base_url="https://fake.youtrack.test", token="fake-token")


class TestValidateIssueData:
    """Tests for validate_issue_data() — pure validation logic.

    get_project_info is mocked so no HTTP calls are made.
    """

    def test_valid_data_returns_true(self, creator: YouTrackIssueCreator) -> None:
        with patch.object(creator, "get_project_info", return_value={"id": "PIPE", "name": "Pipeline"}):
            is_valid, errors = creator.validate_issue_data(
                project="PIPE",
                summary="Add unit tests for config module",
            )
        assert is_valid is True
        assert errors == []

    def test_valid_data_with_all_fields(self, creator: YouTrackIssueCreator) -> None:
        with patch.object(creator, "get_project_info", return_value={"id": "PIPE"}):
            is_valid, errors = creator.validate_issue_data(
                project="PIPE",
                summary="Test summary",
                description="Some description",
                issue_type="Feature",
                priority="Normal",
                assignee="gisi",
            )
        assert is_valid is True
        assert errors == []

    def test_empty_summary_returns_error(self, creator: YouTrackIssueCreator) -> None:
        with patch.object(creator, "get_project_info", return_value={"id": "PIPE"}):
            is_valid, errors = creator.validate_issue_data(
                project="PIPE",
                summary="",
            )
        assert is_valid is False
        assert any("Summary is required" in e for e in errors)

    def test_whitespace_only_summary_returns_error(self, creator: YouTrackIssueCreator) -> None:
        with patch.object(creator, "get_project_info", return_value={"id": "PIPE"}):
            is_valid, errors = creator.validate_issue_data(
                project="PIPE",
                summary="   ",
            )
        assert is_valid is False
        assert any("Summary is required" in e for e in errors)

    def test_summary_too_long_returns_error(self, creator: YouTrackIssueCreator) -> None:
        long_summary = "x" * 256
        with patch.object(creator, "get_project_info", return_value={"id": "PIPE"}):
            is_valid, errors = creator.validate_issue_data(
                project="PIPE",
                summary=long_summary,
            )
        assert is_valid is False
        assert any("too long" in e for e in errors)

    def test_summary_exactly_255_chars_is_valid(self, creator: YouTrackIssueCreator) -> None:
        summary = "x" * 255
        with patch.object(creator, "get_project_info", return_value={"id": "PIPE"}):
            is_valid, errors = creator.validate_issue_data(
                project="PIPE",
                summary=summary,
            )
        assert is_valid is True
        assert errors == []

    def test_project_not_found_returns_error(self, creator: YouTrackIssueCreator) -> None:
        with patch.object(creator, "get_project_info", return_value=None):
            is_valid, errors = creator.validate_issue_data(
                project="NONEXISTENT",
                summary="Valid summary",
            )
        assert is_valid is False
        assert any("not found" in e for e in errors)

    def test_multiple_errors_accumulated(self, creator: YouTrackIssueCreator) -> None:
        """Both project-not-found and empty-summary should appear."""
        with patch.object(creator, "get_project_info", return_value=None):
            is_valid, errors = creator.validate_issue_data(
                project="BAD",
                summary="",
            )
        assert is_valid is False
        assert len(errors) >= 2
