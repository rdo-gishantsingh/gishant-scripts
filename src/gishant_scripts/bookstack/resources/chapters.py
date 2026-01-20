"""Chapters resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import ExportableResource


class ChaptersResource(ExportableResource):
    """Manage BookStack chapters.

    Chapters are containers for pages within a book. They help organize
    content into logical sections.
    """

    ENDPOINT = "chapters"

    def create(
        self,
        book_id: int,
        name: str,
        description: str | None = None,
        description_html: str | None = None,
        tags: list[dict[str, str]] | None = None,
        priority: int | None = None,
        default_template_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new chapter.

        Args:
            book_id: ID of book to create chapter in
            name: Chapter title (max 255 characters)
            description: Plain text description (max 1900 characters)
            description_html: HTML description (max 2000 characters)
            tags: List of tags [{"name": "...", "value": "..."}]
            priority: Sort order priority
            default_template_id: Default page template ID

        Returns:
            Created chapter data
        """
        data: dict[str, Any] = {
            "book_id": book_id,
            "name": name,
        }
        if description:
            data["description"] = description
        if description_html:
            data["description_html"] = description_html
        if tags:
            data["tags"] = tags
        if priority is not None:
            data["priority"] = priority
        if default_template_id is not None:
            data["default_template_id"] = default_template_id

        return self.client.post(self.ENDPOINT, data=data)

    def update(
        self,
        chapter_id: int,
        book_id: int | None = None,
        name: str | None = None,
        description: str | None = None,
        description_html: str | None = None,
        tags: list[dict[str, str]] | None = None,
        priority: int | None = None,
        default_template_id: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing chapter.

        Providing book_id will move the chapter to that book.

        Args:
            chapter_id: ID of chapter to update
            book_id: Move to different book
            name: New chapter title
            description: Update plain text description
            description_html: Update HTML description
            tags: Update tags
            priority: Update sort order
            default_template_id: Update default template

        Returns:
            Updated chapter data
        """
        data: dict[str, Any] = {}
        if book_id is not None:
            data["book_id"] = book_id
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if description_html is not None:
            data["description_html"] = description_html
        if tags is not None:
            data["tags"] = tags
        if priority is not None:
            data["priority"] = priority
        if default_template_id is not None:
            data["default_template_id"] = default_template_id

        return self.client.put(self._get_endpoint(chapter_id), data=data)

    def list_by_book(self, book_id: int) -> list[dict[str, Any]]:
        """List all chapters in a book.

        Args:
            book_id: Book ID

        Returns:
            List of chapters
        """
        return self.list_all(filters={"book_id": book_id})
