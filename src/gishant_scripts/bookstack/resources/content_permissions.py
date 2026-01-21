"""Content permissions resource for BookStack API."""

from __future__ import annotations

from typing import Any, Literal

from gishant_scripts.bookstack.resources.base import BaseResource

ContentType = Literal["page", "book", "chapter", "bookshelf"]


class ContentPermissionsResource(BaseResource):
    """Manage BookStack content-level permissions."""

    ENDPOINT = "content-permissions"

    def read(self, content_type: ContentType, content_id: int) -> dict[str, Any]:
        """Read content permissions for an item.

        Args:
            content_type: Type of content (page, book, chapter, bookshelf)
            content_id: ID of the content item

        Returns:
            Permission data including:
            - owner: Owner details
            - role_permissions: List of role-specific permissions
            - fallback_permissions: Default permissions when no role matches
        """
        endpoint = f"{self.ENDPOINT}/{content_type}/{content_id}"
        result = self.client.get(endpoint)
        if isinstance(result, bytes):
            return {}
        return result

    def update(
        self,
        content_type: ContentType,
        content_id: int,
        owner_id: int | None = None,
        role_permissions: list[dict[str, Any]] | None = None,
        fallback_permissions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update content permissions for an item.

        Args:
            content_type: Type of content (page, book, chapter, bookshelf)
            content_id: ID of the content item
            owner_id: New owner user ID
            role_permissions: List of role permissions:
                [{"role_id": 1, "view": True, "create": False, "update": True, "delete": False}]
            fallback_permissions: Default permissions:
                {"inheriting": False, "view": True, "create": False, "update": False, "delete": False}

        Returns:
            Updated permission data
        """
        data: dict[str, Any] = {}
        if owner_id is not None:
            data["owner_id"] = owner_id
        if role_permissions is not None:
            data["role_permissions"] = role_permissions
        if fallback_permissions is not None:
            data["fallback_permissions"] = fallback_permissions

        endpoint = f"{self.ENDPOINT}/{content_type}/{content_id}"
        return self.client.put(endpoint, data=data)

    def set_role_permission(
        self,
        content_type: ContentType,
        content_id: int,
        role_id: int,
        view: bool = True,
        create: bool = False,
        update: bool = False,
        delete: bool = False,
    ) -> dict[str, Any]:
        """Set permissions for a specific role on content.

        This is a convenience method that fetches existing permissions,
        updates the specified role, and saves.

        Args:
            content_type: Type of content
            content_id: ID of the content item
            role_id: Role ID to set permissions for
            view: Can view
            create: Can create
            update: Can update
            delete: Can delete

        Returns:
            Updated permission data
        """
        # Fetch existing permissions
        existing = self.read(content_type, content_id)
        role_perms = existing.get("role_permissions", [])

        # Update or add role permission
        found = False
        for perm in role_perms:
            if perm.get("role_id") == role_id:
                perm["view"] = view
                perm["create"] = create
                perm["update"] = update
                perm["delete"] = delete
                found = True
                break

        if not found:
            role_perms.append(
                {
                    "role_id": role_id,
                    "view": view,
                    "create": create,
                    "update": update,
                    "delete": delete,
                }
            )

        return self.update(content_type, content_id, role_permissions=role_perms)

    def clear_role_permissions(
        self,
        content_type: ContentType,
        content_id: int,
    ) -> dict[str, Any]:
        """Clear all role-specific permissions for content.

        Args:
            content_type: Type of content
            content_id: ID of the content item

        Returns:
            Updated permission data
        """
        return self.update(content_type, content_id, role_permissions=[])
