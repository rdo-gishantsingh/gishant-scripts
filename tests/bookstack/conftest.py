"""Shared fixtures for BookStack tests."""

from unittest.mock import MagicMock

import pytest

from gishant_scripts.bookstack.client import BookStackClient


@pytest.fixture
def mock_client():
    """Create a BookStack client with mocked requests."""
    # Mock the session to avoid real API calls
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "application/json"}
    mock_response.json.return_value = {}
    mock_response.content = b"{}"
    mock_session.request.return_value = mock_response

    client = BookStackClient(
        base_url="https://test.bookstack.local",
        token_id="test_token_id",
        token_secret="test_token_secret",
    )
    client._session = mock_session

    return client


@pytest.fixture
def sample_page():
    """Sample page data."""
    return {
        "id": 1,
        "book_id": 1,
        "chapter_id": None,
        "name": "Test Page",
        "slug": "test-page",
        "html": "<p>Test content</p>",
        "priority": 0,
        "draft": False,
        "revision_count": 1,
        "template": False,
        "created_at": "2024-01-01T00:00:00.000000Z",
        "updated_at": "2024-01-01T00:00:00.000000Z",
        "created_by": 1,
        "updated_by": 1,
        "owned_by": 1,
        "editor": "wysiwyg",
        "book_slug": "test-book",
    }


@pytest.fixture
def sample_chapter():
    """Sample chapter data."""
    return {
        "id": 1,
        "book_id": 1,
        "name": "Test Chapter",
        "slug": "test-chapter",
        "description": "Test description",
        "priority": 0,
        "created_at": "2024-01-01T00:00:00.000000Z",
        "updated_at": "2024-01-01T00:00:00.000000Z",
        "created_by": 1,
        "updated_by": 1,
        "owned_by": 1,
        "book_slug": "test-book",
    }


@pytest.fixture
def sample_book():
    """Sample book data."""
    return {
        "id": 1,
        "name": "Test Book",
        "slug": "test-book",
        "description": "Test description",
        "created_at": "2024-01-01T00:00:00.000000Z",
        "updated_at": "2024-01-01T00:00:00.000000Z",
        "created_by": 1,
        "updated_by": 1,
        "owned_by": 1,
        "cover": None,
    }


@pytest.fixture
def sample_shelf():
    """Sample shelf data."""
    return {
        "id": 1,
        "name": "Test Shelf",
        "slug": "test-shelf",
        "description": "Test description",
        "created_at": "2024-01-01T00:00:00.000000Z",
        "updated_at": "2024-01-01T00:00:00.000000Z",
        "created_by": 1,
        "updated_by": 1,
        "owned_by": 1,
        "cover": None,
    }


@pytest.fixture
def sample_list_response(sample_page):
    """Sample list response."""
    return {
        "data": [sample_page],
        "total": 1,
    }


@pytest.fixture
def sample_system_info():
    """Sample system info response."""
    return {
        "version": "v25.02.4",
        "instance_id": "1234abcd-cc12-7808-af0a-264cb0cbd611",
        "app_name": "Test BookStack",
        "app_logo": None,
        "base_url": "https://test.bookstack.local",
    }
