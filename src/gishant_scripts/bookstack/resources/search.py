"""Search resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import BaseResource


class SearchResource(BaseResource):
    """Search across BookStack content.

    Provides full-text search across shelves, books, chapters, and pages.
    """

    ENDPOINT = "search"

    def all(
        self,
        query: str,
        page: int = 1,
        count: int = 20,
    ) -> dict[str, Any]:
        """Search all content types.

        The query supports BookStack's search syntax including:
        - {created_by:me} - Filter by creator
        - {updated_by:me} - Filter by updater
        - {owned_by:me} - Filter by owner
        - {in_name:text} - Search in names only
        - {in_body:text} - Search in body only
        - [tag_name] - Search by tag name
        - [tag_name=value] - Search by tag name and value

        Args:
            query: Search query string
            page: Page number (1-based)
            count: Results per page (max 100)

        Returns:
            Search results with 'data' and 'total' fields
        """
        params = {
            "query": query,
            "page": page,
            "count": min(count, 100),
        }

        result = self.client.get(self.ENDPOINT, params=params)
        if isinstance(result, bytes):
            return {"data": [], "total": 0}
        return result

    def search_all(self, query: str, max_results: int = 500) -> list[dict[str, Any]]:
        """Search and return all matching results with pagination.

        Args:
            query: Search query string
            max_results: Maximum number of results to return

        Returns:
            List of all matching items
        """
        results: list[dict[str, Any]] = []
        page = 1
        count = 100

        while len(results) < max_results:
            response = self.all(query, page=page, count=count)
            data = response.get("data", [])
            total = response.get("total", 0)

            results.extend(data)

            if len(results) >= total or not data:
                break

            page += 1

        return results[:max_results]

    def pages(self, query: str) -> list[dict[str, Any]]:
        """Search only pages.

        Args:
            query: Search query string

        Returns:
            List of matching pages
        """
        results = self.search_all(query)
        return [r for r in results if r.get("type") == "page"]

    def chapters(self, query: str) -> list[dict[str, Any]]:
        """Search only chapters.

        Args:
            query: Search query string

        Returns:
            List of matching chapters
        """
        results = self.search_all(query)
        return [r for r in results if r.get("type") == "chapter"]

    def books(self, query: str) -> list[dict[str, Any]]:
        """Search only books.

        Args:
            query: Search query string

        Returns:
            List of matching books
        """
        results = self.search_all(query)
        return [r for r in results if r.get("type") == "book"]

    def shelves(self, query: str) -> list[dict[str, Any]]:
        """Search only shelves.

        Args:
            query: Search query string

        Returns:
            List of matching shelves
        """
        results = self.search_all(query)
        return [r for r in results if r.get("type") == "bookshelf"]
