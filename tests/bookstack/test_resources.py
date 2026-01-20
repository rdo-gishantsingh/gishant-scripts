"""Tests for BookStack resource classes."""

from unittest.mock import MagicMock

import pytest

from gishant_scripts.bookstack.resources.pages import PagesResource
from gishant_scripts.bookstack.resources.chapters import ChaptersResource
from gishant_scripts.bookstack.resources.books import BooksResource
from gishant_scripts.bookstack.resources.shelves import ShelvesResource
from gishant_scripts.bookstack.resources.search import SearchResource
from gishant_scripts.bookstack.resources.system import SystemResource


class TestPagesResource:
    """Test PagesResource class."""

    def test_endpoint(self, mock_client):
        """Test resource endpoint."""
        pages = PagesResource(mock_client)
        assert pages.ENDPOINT == "pages"

    def test_create_requires_parent(self, mock_client):
        """Test create raises error without book_id or chapter_id."""
        pages = PagesResource(mock_client)

        with pytest.raises(ValueError) as exc_info:
            pages.create(name="Test Page")

        assert "book_id or chapter_id" in str(exc_info.value)

    def test_create_with_book(self, mock_client, sample_page):
        """Test create page in book."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = sample_page
        mock_client._session.request.return_value = mock_response

        pages = PagesResource(mock_client)
        result = pages.create(name="Test Page", book_id=1, html="<p>Content</p>")

        assert result["id"] == 1
        assert result["name"] == "Test Page"

    def test_create_with_chapter(self, mock_client, sample_page):
        """Test create page in chapter."""
        sample_page["chapter_id"] = 1
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = sample_page
        mock_client._session.request.return_value = mock_response

        pages = PagesResource(mock_client)
        result = pages.create(name="Test Page", chapter_id=1, markdown="# Content")

        assert result["chapter_id"] == 1

    def test_list_by_book(self, mock_client, sample_list_response):
        """Test list pages by book."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = sample_list_response
        mock_client._session.request.return_value = mock_response

        pages = PagesResource(mock_client)
        result = pages.list_by_book(1)

        assert len(result) == 1

    def test_export_formats(self, mock_client):
        """Test export formats list."""
        pages = PagesResource(mock_client)
        assert "html" in pages.EXPORT_FORMATS
        assert "pdf" in pages.EXPORT_FORMATS
        assert "markdown" in pages.EXPORT_FORMATS
        assert "plaintext" in pages.EXPORT_FORMATS
        assert "zip" in pages.EXPORT_FORMATS


class TestChaptersResource:
    """Test ChaptersResource class."""

    def test_endpoint(self, mock_client):
        """Test resource endpoint."""
        chapters = ChaptersResource(mock_client)
        assert chapters.ENDPOINT == "chapters"

    def test_create(self, mock_client, sample_chapter):
        """Test create chapter."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = sample_chapter
        mock_client._session.request.return_value = mock_response

        chapters = ChaptersResource(mock_client)
        result = chapters.create(book_id=1, name="Test Chapter", description="Description")

        assert result["id"] == 1
        assert result["name"] == "Test Chapter"


class TestBooksResource:
    """Test BooksResource class."""

    def test_endpoint(self, mock_client):
        """Test resource endpoint."""
        books = BooksResource(mock_client)
        assert books.ENDPOINT == "books"

    def test_create(self, mock_client, sample_book):
        """Test create book."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = sample_book
        mock_client._session.request.return_value = mock_response

        books = BooksResource(mock_client)
        result = books.create(name="Test Book", description="Description")

        assert result["id"] == 1
        assert result["name"] == "Test Book"


class TestShelvesResource:
    """Test ShelvesResource class."""

    def test_endpoint(self, mock_client):
        """Test resource endpoint."""
        shelves = ShelvesResource(mock_client)
        assert shelves.ENDPOINT == "shelves"

    def test_create_with_books(self, mock_client, sample_shelf):
        """Test create shelf with books."""
        sample_shelf["books"] = [1, 2, 3]
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = sample_shelf
        mock_client._session.request.return_value = mock_response

        shelves = ShelvesResource(mock_client)
        result = shelves.create(name="Test Shelf", books=[1, 2, 3])

        assert result["id"] == 1


class TestSearchResource:
    """Test SearchResource class."""

    def test_endpoint(self, mock_client):
        """Test resource endpoint."""
        search = SearchResource(mock_client)
        assert search.ENDPOINT == "search"

    def test_all(self, mock_client):
        """Test search all."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {
            "data": [{"id": 1, "type": "page", "name": "Test"}],
            "total": 1,
        }
        mock_client._session.request.return_value = mock_response

        search = SearchResource(mock_client)
        result = search.all("test query")

        assert result["total"] == 1
        assert result["data"][0]["type"] == "page"

    def test_search_filter_pages(self, mock_client):
        """Test search with page filter."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {
            "data": [
                {"id": 1, "type": "page", "name": "Page 1"},
                {"id": 2, "type": "chapter", "name": "Chapter 1"},
                {"id": 3, "type": "page", "name": "Page 2"},
            ],
            "total": 3,
        }
        mock_client._session.request.return_value = mock_response

        search = SearchResource(mock_client)
        result = search.pages("test")

        assert len(result) == 2
        assert all(r["type"] == "page" for r in result)


class TestSystemResource:
    """Test SystemResource class."""

    def test_endpoint(self, mock_client):
        """Test resource endpoint."""
        system = SystemResource(mock_client)
        assert system.ENDPOINT == "system"

    def test_info(self, mock_client, sample_system_info):
        """Test system info."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = sample_system_info
        mock_client._session.request.return_value = mock_response

        system = SystemResource(mock_client)
        result = system.info()

        assert result["version"] == "v25.02.4"
        assert result["app_name"] == "Test BookStack"
