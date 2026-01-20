"""Base resource class for BookStack API resources."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from gishant_scripts.bookstack.client import BookStackClient


class BaseResource:
    """Base class for BookStack API resources.

    Provides common functionality for all resource types.
    """

    ENDPOINT: str = ""

    def __init__(self, client: BookStackClient):
        """Initialize the resource.

        Args:
            client: BookStack API client instance
        """
        self.client = client

    def _get_endpoint(self, *parts: str | int) -> str:
        """Build endpoint URL from parts.

        Args:
            *parts: URL path segments to append

        Returns:
            Full endpoint path
        """
        endpoint = self.ENDPOINT
        for part in parts:
            endpoint = f"{endpoint}/{part}"
        return endpoint


class CRUDResource(BaseResource):
    """Resource class with standard CRUD operations."""

    def list(
        self,
        count: int | None = None,
        offset: int | None = None,
        sort: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List items with optional pagination and filtering.

        Args:
            count: Number of items to return (max 500)
            offset: Number of items to skip
            sort: Field to sort by (prefix with + or - for direction)
            filters: Filter criteria (e.g., {"name:like": "%test%"})

        Returns:
            Response with 'data' list and 'total' count
        """
        params: dict[str, Any] = {}
        if count is not None:
            params["count"] = count
        if offset is not None:
            params["offset"] = offset
        if sort is not None:
            params["sort"] = sort
        if filters:
            for key, value in filters.items():
                params[f"filter[{key}]"] = value

        result = self.client.get(self.ENDPOINT, params=params)
        if isinstance(result, bytes):
            return {"data": [], "total": 0}
        return result

    def list_all(
        self,
        sort: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """List all items with automatic pagination.

        Args:
            sort: Field to sort by
            filters: Filter criteria

        Returns:
            List of all items
        """
        params: dict[str, Any] = {}
        if sort is not None:
            params["sort"] = sort
        if filters:
            for key, value in filters.items():
                params[f"filter[{key}]"] = value

        return self.client.list_all(self.ENDPOINT, params=params)

    def read(self, item_id: int) -> dict[str, Any]:
        """Read a single item by ID.

        Args:
            item_id: Item ID

        Returns:
            Item data
        """
        result = self.client.get(self._get_endpoint(item_id))
        if isinstance(result, bytes):
            return {}
        return result

    def create(self, **data: Any) -> dict[str, Any]:
        """Create a new item.

        Args:
            **data: Item data

        Returns:
            Created item data
        """
        return self.client.post(self.ENDPOINT, data=data)

    def update(self, item_id: int, **data: Any) -> dict[str, Any]:
        """Update an existing item.

        Args:
            item_id: Item ID
            **data: Fields to update

        Returns:
            Updated item data
        """
        return self.client.put(self._get_endpoint(item_id), data=data)

    def delete(self, item_id: int) -> dict[str, Any]:
        """Delete an item.

        Args:
            item_id: Item ID

        Returns:
            Empty dict on success
        """
        return self.client.delete(self._get_endpoint(item_id))


class ExportableResource(CRUDResource):
    """Resource class with export capabilities."""

    EXPORT_FORMATS = ["html", "pdf", "plaintext", "markdown", "zip"]

    def export(
        self,
        item_id: int,
        format: str,
        output_path: Path | None = None,
    ) -> bytes | Path:
        """Export an item in the specified format.

        Args:
            item_id: Item ID
            format: Export format (html, pdf, plaintext, markdown, zip)
            output_path: Optional path to save the file

        Returns:
            Raw bytes if no output_path, otherwise the output path
        """
        if format not in self.EXPORT_FORMATS:
            raise ValueError(f"Invalid export format: {format}. Valid formats: {self.EXPORT_FORMATS}")

        endpoint = self._get_endpoint(item_id, "export", format)
        result = self.client.get(endpoint)

        if output_path:
            if isinstance(result, bytes):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(result)
                return output_path
            else:
                # JSON response - save as text
                import json

                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(json.dumps(result, indent=2))
                return output_path

        if isinstance(result, bytes):
            return result
        # Return empty bytes for non-binary response
        return b""

    def export_html(self, item_id: int, output_path: Path | None = None) -> bytes | Path:
        """Export as HTML."""
        return self.export(item_id, "html", output_path)

    def export_pdf(self, item_id: int, output_path: Path | None = None) -> bytes | Path:
        """Export as PDF."""
        return self.export(item_id, "pdf", output_path)

    def export_plaintext(self, item_id: int, output_path: Path | None = None) -> bytes | Path:
        """Export as plain text."""
        return self.export(item_id, "plaintext", output_path)

    def export_markdown(self, item_id: int, output_path: Path | None = None) -> bytes | Path:
        """Export as Markdown."""
        return self.export(item_id, "markdown", output_path)

    def export_zip(self, item_id: int, output_path: Path | None = None) -> bytes | Path:
        """Export as ZIP archive."""
        return self.export(item_id, "zip", output_path)
