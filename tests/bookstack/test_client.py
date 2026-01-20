"""Tests for BookStack client."""

from unittest.mock import MagicMock

import pytest

from gishant_scripts.bookstack.client import BookStackClient
from gishant_scripts.common.errors import APIError


class TestBookStackClient:
    """Test BookStackClient class."""

    def test_init(self):
        """Test client initialization."""
        client = BookStackClient(
            base_url="https://test.bookstack.local",
            token_id="test_id",
            token_secret="test_secret",
        )

        assert client.base_url == "https://test.bookstack.local"
        assert client.token_id == "test_id"
        assert client.token_secret == "test_secret"
        assert client.timeout == BookStackClient.DEFAULT_TIMEOUT

    def test_init_strips_trailing_slash(self):
        """Test that trailing slash is stripped from base URL."""
        client = BookStackClient(
            base_url="https://test.bookstack.local/",
            token_id="test_id",
            token_secret="test_secret",
        )

        assert client.base_url == "https://test.bookstack.local"

    def test_get_headers(self):
        """Test authentication headers."""
        client = BookStackClient(
            base_url="https://test.bookstack.local",
            token_id="test_id",
            token_secret="test_secret",
        )

        headers = client._get_headers()

        assert headers["Authorization"] == "Token test_id:test_secret"
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"

    def test_build_url(self):
        """Test URL building."""
        client = BookStackClient(
            base_url="https://test.bookstack.local",
            token_id="test_id",
            token_secret="test_secret",
        )

        # Without api prefix
        assert client._build_url("pages") == "https://test.bookstack.local/api/pages"
        assert client._build_url("/pages") == "https://test.bookstack.local/api/pages"

        # With api prefix
        assert client._build_url("api/pages") == "https://test.bookstack.local/api/pages"
        assert client._build_url("/api/pages") == "https://test.bookstack.local/api/pages"

    def test_handle_response_success(self, mock_client):
        """Test successful response handling."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"id": 1, "name": "Test"}

        result = mock_client._handle_response(mock_response)

        assert result == {"id": 1, "name": "Test"}

    def test_handle_response_empty(self, mock_client):
        """Test empty response handling (e.g., DELETE)."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 204
        mock_response.content = b""

        result = mock_client._handle_response(mock_response)

        assert result == {}

    def test_handle_response_binary(self, mock_client):
        """Test binary response handling (e.g., PDF export)."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_response.content = b"PDF content"

        result = mock_client._handle_response(mock_response)

        assert result == b"PDF content"

    def test_handle_response_rate_limit(self, mock_client):
        """Test rate limit error handling."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "60"}

        with pytest.raises(APIError) as exc_info:
            mock_client._handle_response(mock_response)

        assert "Rate limit" in str(exc_info.value)
        assert "60" in str(exc_info.value)

    def test_handle_response_error(self, mock_client):
        """Test error response handling."""
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_response.json.return_value = {"error": {"code": 404, "message": "Not found"}}

        with pytest.raises(APIError) as exc_info:
            mock_client._handle_response(mock_response)

        assert "404" in str(exc_info.value)
        assert "Not found" in str(exc_info.value)

    def test_get(self, mock_client):
        """Test GET request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"data": [], "total": 0}
        mock_client._session.request.return_value = mock_response

        result = mock_client.get("pages", params={"count": 10})

        assert result == {"data": [], "total": 0}
        mock_client._session.request.assert_called_once()

    def test_post(self, mock_client):
        """Test POST request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"id": 1, "name": "New Page"}
        mock_client._session.request.return_value = mock_response

        result = mock_client.post("pages", data={"name": "New Page", "book_id": 1})

        assert result == {"id": 1, "name": "New Page"}
        mock_client._session.request.assert_called_once()

    def test_put(self, mock_client):
        """Test PUT request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {"id": 1, "name": "Updated Page"}
        mock_client._session.request.return_value = mock_response

        result = mock_client.put("pages/1", data={"name": "Updated Page"})

        assert result == {"id": 1, "name": "Updated Page"}
        mock_client._session.request.assert_called_once()

    def test_delete(self, mock_client):
        """Test DELETE request."""
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 204
        mock_response.content = b""
        mock_client._session.request.return_value = mock_response

        result = mock_client.delete("pages/1")

        assert result == {}
        mock_client._session.request.assert_called_once()

    def test_list_all_pagination(self, mock_client):
        """Test paginated listing."""
        # First page
        response1 = MagicMock()
        response1.ok = True
        response1.status_code = 200
        response1.headers = {"Content-Type": "application/json"}
        response1.json.return_value = {
            "data": [{"id": 1}, {"id": 2}],
            "total": 4,
        }

        # Second page
        response2 = MagicMock()
        response2.ok = True
        response2.status_code = 200
        response2.headers = {"Content-Type": "application/json"}
        response2.json.return_value = {
            "data": [{"id": 3}, {"id": 4}],
            "total": 4,
        }

        mock_client._session.request.side_effect = [response1, response2]

        result = mock_client.list_all("pages", page_size=2)

        assert len(result) == 4
        assert result[0]["id"] == 1
        assert result[3]["id"] == 4

    def test_resource_accessors(self, mock_client):
        """Test resource property accessors."""
        # These should return resource instances without error
        assert mock_client.pages is not None
        assert mock_client.chapters is not None
        assert mock_client.books is not None
        assert mock_client.shelves is not None
        assert mock_client.attachments is not None
        assert mock_client.search is not None
        assert mock_client.users is not None
        assert mock_client.system is not None
        assert mock_client.image_gallery is not None
        assert mock_client.recycle_bin is not None
        assert mock_client.roles is not None
        assert mock_client.comments is not None
        assert mock_client.content_permissions is not None
        assert mock_client.audit_log is not None
