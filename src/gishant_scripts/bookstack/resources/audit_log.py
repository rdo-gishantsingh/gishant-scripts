"""Audit log resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import BaseResource


class AuditLogResource(BaseResource):
    """Access BookStack audit log.

    Requires permission to manage both users and system settings.
    """

    ENDPOINT = "audit-log"

    def list(
        self,
        count: int | None = None,
        offset: int | None = None,
        sort: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List audit log entries.

        Args:
            count: Number of items to return
            offset: Number of items to skip
            sort: Field to sort by
            filters: Filter criteria

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

        result = self.client.get(self.ENDPOINT, params=params if params else None)
        if isinstance(result, bytes):
            return {"data": [], "total": 0}
        return result

    def list_all(
        self,
        sort: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """List all audit log entries.

        Args:
            sort: Field to sort by
            filters: Filter criteria

        Returns:
            List of all audit log entries
        """
        params: dict[str, Any] = {}
        if sort is not None:
            params["sort"] = sort
        if filters:
            for key, value in filters.items():
                params[f"filter[{key}]"] = value

        return self.client.list_all(self.ENDPOINT, params=params)

    def list_by_user(self, user_id: int) -> list[dict[str, Any]]:
        """List audit log entries for a specific user.

        Args:
            user_id: User ID

        Returns:
            List of audit log entries
        """
        return self.list_all(filters={"user_id": user_id})

    def list_by_type(self, event_type: str) -> list[dict[str, Any]]:
        """List audit log entries of a specific type.

        Args:
            event_type: Event type (e.g., 'page_create', 'auth_login')

        Returns:
            List of audit log entries
        """
        return self.list_all(filters={"type": event_type})
