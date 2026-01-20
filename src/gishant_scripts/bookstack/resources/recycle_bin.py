"""Recycle bin resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import BaseResource


class RecycleBinResource(BaseResource):
    """Manage BookStack recycle bin.

    Requires permission to manage both system settings and permissions.
    """

    ENDPOINT = "recycle-bin"

    def list(
        self,
        count: int | None = None,
        offset: int | None = None,
    ) -> dict[str, Any]:
        """List items in the recycle bin.

        Args:
            count: Number of items to return
            offset: Number of items to skip

        Returns:
            Response with 'data' list and 'total' count
        """
        params: dict[str, Any] = {}
        if count is not None:
            params["count"] = count
        if offset is not None:
            params["offset"] = offset

        result = self.client.get(self.ENDPOINT, params=params if params else None)
        if isinstance(result, bytes):
            return {"data": [], "total": 0}
        return result

    def list_all(self) -> list[dict[str, Any]]:
        """List all items in the recycle bin.

        Returns:
            List of all deleted items
        """
        return self.client.list_all(self.ENDPOINT)

    def restore(self, deletion_id: int) -> dict[str, Any]:
        """Restore an item from the recycle bin.

        Args:
            deletion_id: ID of the deletion record (not the original item ID)

        Returns:
            Response with 'restore_count' indicating number of items restored
        """
        return self.client.put(self._get_endpoint(deletion_id))

    def destroy(self, deletion_id: int) -> dict[str, Any]:
        """Permanently delete an item from the recycle bin.

        This action is irreversible.

        Args:
            deletion_id: ID of the deletion record (not the original item ID)

        Returns:
            Response with 'delete_count' indicating number of items deleted
        """
        return self.client.delete(self._get_endpoint(deletion_id))

    def empty(self) -> list[dict[str, Any]]:
        """Permanently delete all items in the recycle bin.

        This action is irreversible.

        Returns:
            List of deletion results
        """
        items = self.list_all()
        results = []
        for item in items:
            deletion_id = item.get("id")
            if deletion_id:
                results.append(self.destroy(deletion_id))
        return results
