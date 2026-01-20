"""Roles resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import CRUDResource


class RolesResource(CRUDResource):
    """Manage BookStack roles.

    Requires permission to manage roles.
    """

    ENDPOINT = "roles"

    def create(
        self,
        display_name: str,
        description: str | None = None,
        mfa_enforced: bool = False,
        external_auth_id: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new role.

        Args:
            display_name: Role display name (3-180 characters)
            description: Role description (max 180 characters)
            mfa_enforced: Whether MFA is required for this role
            external_auth_id: External authentication ID
            permissions: List of permission names

        Returns:
            Created role data
        """
        data: dict[str, Any] = {"display_name": display_name}
        if description:
            data["description"] = description
        if mfa_enforced:
            data["mfa_enforced"] = mfa_enforced
        if external_auth_id:
            data["external_auth_id"] = external_auth_id
        if permissions:
            data["permissions"] = permissions

        return self.client.post(self.ENDPOINT, data=data)

    def update(
        self,
        role_id: int,
        display_name: str | None = None,
        description: str | None = None,
        mfa_enforced: bool | None = None,
        external_auth_id: str | None = None,
        permissions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update an existing role.

        Note: Providing an empty permissions array will clear all permissions.

        Args:
            role_id: ID of role to update
            display_name: Update display name
            description: Update description
            mfa_enforced: Update MFA enforcement
            external_auth_id: Update external auth ID
            permissions: Update permissions list

        Returns:
            Updated role data
        """
        data: dict[str, Any] = {}
        if display_name is not None:
            data["display_name"] = display_name
        if description is not None:
            data["description"] = description
        if mfa_enforced is not None:
            data["mfa_enforced"] = mfa_enforced
        if external_auth_id is not None:
            data["external_auth_id"] = external_auth_id
        if permissions is not None:
            data["permissions"] = permissions

        return self.client.put(self._get_endpoint(role_id), data=data)
