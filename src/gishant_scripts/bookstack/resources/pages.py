"""Pages resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import ExportableResource


class PagesResource(ExportableResource):
    """Manage BookStack pages.

    Pages contain the actual content in BookStack. They can exist directly
    within a book or inside a chapter.
    """

    ENDPOINT = "pages"

    def create(
        self,
        name: str,
        book_id: int | None = None,
        chapter_id: int | None = None,
        html: str | None = None,
        markdown: str | None = None,
        tags: list[dict[str, str]] | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        """Create a new page.

        Either book_id or chapter_id must be provided to indicate where
        the page should be created.

        Args:
            name: Page title (max 255 characters)
            book_id: ID of book to create page in (required if no chapter_id)
            chapter_id: ID of chapter to create page in (required if no book_id)
            html: Page content as HTML
            markdown: Page content as Markdown
            tags: List of tags [{"name": "...", "value": "..."}]
            priority: Sort order priority

        Returns:
            Created page data
        """
        if not book_id and not chapter_id:
            raise ValueError("Either book_id or chapter_id must be provided")

        data: dict[str, Any] = {"name": name}
        if book_id:
            data["book_id"] = book_id
        if chapter_id:
            data["chapter_id"] = chapter_id
        if html:
            data["html"] = html
        elif markdown:
            data["markdown"] = markdown
        if tags:
            data["tags"] = tags
        if priority is not None:
            data["priority"] = priority

        return self.client.post(self.ENDPOINT, data=data)

    def update(
        self,
        page_id: int,
        name: str | None = None,
        book_id: int | None = None,
        chapter_id: int | None = None,
        html: str | None = None,
        markdown: str | None = None,
        tags: list[dict[str, str]] | None = None,
        priority: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing page.

        Providing book_id or chapter_id will move the page to that location.

        Args:
            page_id: ID of page to update
            name: New page title
            book_id: Move to book
            chapter_id: Move to chapter
            html: Update content as HTML
            markdown: Update content as Markdown
            tags: Update tags
            priority: Update sort order

        Returns:
            Updated page data
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if book_id is not None:
            data["book_id"] = book_id
        if chapter_id is not None:
            data["chapter_id"] = chapter_id
        if html is not None:
            data["html"] = html
        if markdown is not None:
            data["markdown"] = markdown
        if tags is not None:
            data["tags"] = tags
        if priority is not None:
            data["priority"] = priority

        return self.client.put(self._get_endpoint(page_id), data=data)

    def list_by_book(self, book_id: int) -> list[dict[str, Any]]:
        """List all pages in a book.

        Args:
            book_id: Book ID

        Returns:
            List of pages
        """
        return self.list_all(filters={"book_id": book_id})

    def list_by_chapter(self, chapter_id: int) -> list[dict[str, Any]]:
        """List all pages in a chapter.

        Args:
            chapter_id: Chapter ID

        Returns:
            List of pages
        """
        return self.list_all(filters={"chapter_id": chapter_id})
