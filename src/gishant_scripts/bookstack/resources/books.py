"""Books resource for BookStack API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gishant_scripts.bookstack.resources.base import ExportableResource


class BooksResource(ExportableResource):
    """Manage BookStack books.

    Books are the top-level containers for documentation content.
    They contain chapters and pages.
    """

    ENDPOINT = "books"

    def create(
        self,
        name: str,
        description: str | None = None,
        description_html: str | None = None,
        tags: list[dict[str, str]] | None = None,
        image: Path | None = None,
        default_template_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new book.

        Args:
            name: Book title (max 255 characters)
            description: Plain text description (max 1900 characters)
            description_html: HTML description (max 2000 characters)
            tags: List of tags [{"name": "...", "value": "..."}]
            image: Cover image file path
            default_template_id: Default page template ID

        Returns:
            Created book data
        """
        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description
        if description_html:
            data["description_html"] = description_html
        if tags:
            data["tags"] = tags
        if default_template_id is not None:
            data["default_template_id"] = default_template_id

        if image:
            # Need multipart form data for image upload
            files = {"image": (image.name, image.open("rb"), "image/jpeg")}
            return self.client.post(self.ENDPOINT, data=data, files=files)

        return self.client.post(self.ENDPOINT, data=data)

    def update(
        self,
        book_id: int,
        name: str | None = None,
        description: str | None = None,
        description_html: str | None = None,
        tags: list[dict[str, str]] | None = None,
        image: Path | None = None,
        default_template_id: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing book.

        Args:
            book_id: ID of book to update
            name: New book title
            description: Update plain text description
            description_html: Update HTML description
            tags: Update tags
            image: Update cover image (set to None to remove)
            default_template_id: Update default template

        Returns:
            Updated book data
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if description_html is not None:
            data["description_html"] = description_html
        if tags is not None:
            data["tags"] = tags
        if default_template_id is not None:
            data["default_template_id"] = default_template_id

        if image:
            files = {"image": (image.name, image.open("rb"), "image/jpeg")}
            return self.client.put(self._get_endpoint(book_id), data=data, files=files)

        return self.client.put(self._get_endpoint(book_id), data=data)

    def read(self, book_id: int) -> dict[str, Any]:
        """Read book details including contents.

        The response includes a 'contents' property listing chapters and
        pages directly within the book.

        Args:
            book_id: Book ID

        Returns:
            Book data with contents
        """
        result = self.client.get(self._get_endpoint(book_id))
        if isinstance(result, bytes):
            return {}
        return result
