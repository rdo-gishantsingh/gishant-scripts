"""Shelves resource for BookStack API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gishant_scripts.bookstack.resources.base import CRUDResource


class ShelvesResource(CRUDResource):
    """Manage BookStack shelves.

    Shelves are collections of books, providing a way to group
    related books together.
    """

    ENDPOINT = "shelves"

    def create(
        self,
        name: str,
        description: str | None = None,
        description_html: str | None = None,
        books: list[int] | None = None,
        tags: list[dict[str, str]] | None = None,
        image: Path | None = None,
    ) -> dict[str, Any]:
        """Create a new shelf.

        Args:
            name: Shelf title (max 255 characters)
            description: Plain text description (max 1900 characters)
            description_html: HTML description (max 2000 characters)
            books: List of book IDs to add to shelf (in order)
            tags: List of tags [{"name": "...", "value": "..."}]
            image: Cover image file path

        Returns:
            Created shelf data
        """
        data: dict[str, Any] = {"name": name}
        if description:
            data["description"] = description
        if description_html:
            data["description_html"] = description_html
        if books:
            data["books"] = books
        if tags:
            data["tags"] = tags

        if image:
            files = {"image": (image.name, image.open("rb"), "image/jpeg")}
            return self.client.post(self.ENDPOINT, data=data, files=files)

        return self.client.post(self.ENDPOINT, data=data)

    def update(
        self,
        shelf_id: int,
        name: str | None = None,
        description: str | None = None,
        description_html: str | None = None,
        books: list[int] | None = None,
        tags: list[dict[str, str]] | None = None,
        image: Path | None = None,
    ) -> dict[str, Any]:
        """Update an existing shelf.

        Args:
            shelf_id: ID of shelf to update
            name: New shelf title
            description: Update plain text description
            description_html: Update HTML description
            books: Update book assignments (replaces existing)
            tags: Update tags
            image: Update cover image (set to None to remove)

        Returns:
            Updated shelf data
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if description_html is not None:
            data["description_html"] = description_html
        if books is not None:
            data["books"] = books
        if tags is not None:
            data["tags"] = tags

        if image:
            files = {"image": (image.name, image.open("rb"), "image/jpeg")}
            return self.client.put(self._get_endpoint(shelf_id), data=data, files=files)

        return self.client.put(self._get_endpoint(shelf_id), data=data)

    def read(self, shelf_id: int) -> dict[str, Any]:
        """Read shelf details including books.

        Args:
            shelf_id: Shelf ID

        Returns:
            Shelf data with books list
        """
        result = self.client.get(self._get_endpoint(shelf_id))
        if isinstance(result, bytes):
            return {}
        return result
