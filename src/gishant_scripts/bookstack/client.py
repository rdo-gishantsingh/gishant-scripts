"""BookStack API client with authentication, rate limiting, and pagination support."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import requests
from rich.console import Console

from gishant_scripts.common.errors import APIError

if TYPE_CHECKING:
    from pathlib import Path


class BookStackClient:
    """Client for interacting with the BookStack REST API.

    Handles authentication, rate limiting, pagination, and error handling.
    """

    DEFAULT_TIMEOUT = 30
    MAX_PAGE_SIZE = 500
    DEFAULT_PAGE_SIZE = 100
    RATE_LIMIT_RETRY_AFTER = 60  # Default retry delay if not specified in response

    def __init__(
        self,
        base_url: str,
        token_id: str,
        token_secret: str,
        timeout: int = DEFAULT_TIMEOUT,
        verify_ssl: bool = True,
    ):
        """Initialize the BookStack client.

        Args:
            base_url: BookStack instance URL (e.g., https://docs.example.com)
            token_id: API token ID
            token_secret: API token secret
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates (set to False for self-signed certs)
        """
        self.base_url = base_url.rstrip("/")
        self.token_id = token_id
        self.token_secret = token_secret
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.console = Console()

        self._session = requests.Session()
        self._session.headers.update(self._get_headers())
        self._session.verify = verify_ssl

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "Authorization": f"Token {self.token_id}:{self.token_secret}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _build_url(self, endpoint: str) -> str:
        """Build full API URL from endpoint.

        Args:
            endpoint: API endpoint path (e.g., /api/pages)

        Returns:
            Full URL
        """
        endpoint = endpoint.lstrip("/")
        if not endpoint.startswith("api/"):
            endpoint = f"api/{endpoint}"
        return f"{self.base_url}/{endpoint}"

    def _handle_response(self, response: requests.Response) -> dict[str, Any] | bytes:
        """Handle API response, checking for errors.

        Args:
            response: Response object from requests

        Returns:
            Parsed JSON response or raw bytes for binary content

        Raises:
            APIError: If the request failed
        """
        # Handle rate limiting
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", self.RATE_LIMIT_RETRY_AFTER))
            raise APIError(f"Rate limit exceeded. Retry after {retry_after} seconds.")

        # Handle other errors
        if not response.ok:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message", response.text)
            except (ValueError, KeyError):
                error_msg = response.text
            raise APIError(f"API request failed ({response.status_code}): {error_msg}")

        # Handle empty responses (e.g., DELETE)
        if response.status_code == 204 or not response.content:
            return {}

        # Check if response is binary (e.g., PDF export)
        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return response.content

        return response.json()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        retry_on_rate_limit: bool = True,
    ) -> dict[str, Any] | bytes:
        """Make an API request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint
            params: Query parameters
            json_data: JSON body data
            files: Files for multipart upload
            retry_on_rate_limit: Whether to automatically retry on rate limit

        Returns:
            API response data

        Raises:
            APIError: If the request failed
        """
        url = self._build_url(endpoint)

        # Handle file uploads - need different headers
        headers = None
        if files:
            headers = {
                "Authorization": f"Token {self.token_id}:{self.token_secret}",
                "Accept": "application/json",
            }
            # Don't send Content-Type for multipart; requests handles it

        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                json=json_data if not files else None,
                data=json_data if files else None,
                files=files,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as e:
            raise APIError(f"Request failed: {e}") from e

        # Handle rate limiting with retry
        if response.status_code == 429 and retry_on_rate_limit:
            retry_after = int(response.headers.get("Retry-After", self.RATE_LIMIT_RETRY_AFTER))
            self.console.print(f"[yellow]Rate limited. Waiting {retry_after}s before retry...[/yellow]")
            time.sleep(retry_after)
            return self._request(method, endpoint, params, json_data, files, retry_on_rate_limit=False)

        return self._handle_response(response)

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | bytes:
        """Make a GET request.

        Args:
            endpoint: API endpoint
            params: Query parameters

        Returns:
            API response data
        """
        return self._request("GET", endpoint, params=params)

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint
            data: Request body data
            files: Files for multipart upload

        Returns:
            API response data
        """
        result = self._request("POST", endpoint, json_data=data, files=files)
        if isinstance(result, bytes):
            raise APIError("Unexpected binary response for POST request")
        return result

    def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint
            data: Request body data
            files: Files for multipart upload

        Returns:
            API response data
        """
        result = self._request("PUT", endpoint, json_data=data, files=files)
        if isinstance(result, bytes):
            raise APIError("Unexpected binary response for PUT request")
        return result

    def delete(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint
            data: Request body data (optional)

        Returns:
            API response data (usually empty)
        """
        result = self._request("DELETE", endpoint, json_data=data)
        if isinstance(result, bytes):
            return {}
        return result

    def list_all(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        """Fetch all items from a listing endpoint with pagination.

        Args:
            endpoint: API endpoint for listing
            params: Additional query parameters (filters, sort)
            page_size: Number of items per page (max 500)

        Returns:
            List of all items
        """
        if params is None:
            params = {}

        page_size = min(page_size, self.MAX_PAGE_SIZE)
        results: list[dict[str, Any]] = []
        offset = 0

        while True:
            request_params = {
                **params,
                "count": page_size,
                "offset": offset,
            }

            response = self.get(endpoint, params=request_params)
            if isinstance(response, bytes):
                raise APIError("Unexpected binary response for list request")

            data = response.get("data", [])
            total = response.get("total", 0)

            results.extend(data)

            # Check if we've fetched all items
            if len(results) >= total or not data:
                break

            offset += page_size

        return results

    def download_file(
        self,
        endpoint: str,
        output_path: Path,
        params: dict[str, Any] | None = None,
    ) -> Path:
        """Download a file from an export endpoint.

        Args:
            endpoint: API endpoint for export
            output_path: Path to save the file
            params: Query parameters

        Returns:
            Path to the downloaded file

        Raises:
            APIError: If download failed or response is not binary
        """
        response = self.get(endpoint, params=params)

        if isinstance(response, dict):
            raise APIError("Expected binary response for file download")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(response)

        return output_path

    # Resource accessors for convenience
    @property
    def pages(self):
        """Access pages resource."""
        from gishant_scripts.bookstack.resources.pages import PagesResource

        return PagesResource(self)

    @property
    def chapters(self):
        """Access chapters resource."""
        from gishant_scripts.bookstack.resources.chapters import ChaptersResource

        return ChaptersResource(self)

    @property
    def books(self):
        """Access books resource."""
        from gishant_scripts.bookstack.resources.books import BooksResource

        return BooksResource(self)

    @property
    def shelves(self):
        """Access shelves resource."""
        from gishant_scripts.bookstack.resources.shelves import ShelvesResource

        return ShelvesResource(self)

    @property
    def attachments(self):
        """Access attachments resource."""
        from gishant_scripts.bookstack.resources.attachments import AttachmentsResource

        return AttachmentsResource(self)

    @property
    def search(self):
        """Access search resource."""
        from gishant_scripts.bookstack.resources.search import SearchResource

        return SearchResource(self)

    @property
    def users(self):
        """Access users resource."""
        from gishant_scripts.bookstack.resources.users import UsersResource

        return UsersResource(self)

    @property
    def system(self):
        """Access system resource."""
        from gishant_scripts.bookstack.resources.system import SystemResource

        return SystemResource(self)

    @property
    def image_gallery(self):
        """Access image gallery resource."""
        from gishant_scripts.bookstack.resources.image_gallery import ImageGalleryResource

        return ImageGalleryResource(self)

    @property
    def recycle_bin(self):
        """Access recycle bin resource."""
        from gishant_scripts.bookstack.resources.recycle_bin import RecycleBinResource

        return RecycleBinResource(self)

    @property
    def roles(self):
        """Access roles resource."""
        from gishant_scripts.bookstack.resources.roles import RolesResource

        return RolesResource(self)

    @property
    def comments(self):
        """Access comments resource."""
        from gishant_scripts.bookstack.resources.comments import CommentsResource

        return CommentsResource(self)

    @property
    def content_permissions(self):
        """Access content permissions resource."""
        from gishant_scripts.bookstack.resources.content_permissions import ContentPermissionsResource

        return ContentPermissionsResource(self)

    @property
    def audit_log(self):
        """Access audit log resource."""
        from gishant_scripts.bookstack.resources.audit_log import AuditLogResource

        return AuditLogResource(self)
