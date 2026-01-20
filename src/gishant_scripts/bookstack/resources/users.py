"""Users resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import CRUDResource


class UsersResource(CRUDResource):
    """Manage BookStack users.

    Requires permission to manage users.
    """

    ENDPOINT = "users"

    def create(
        self,
        name: str,
        email: str,
        roles: list[int] | None = None,
        password: str | None = None,
        language: str | None = None,
        external_auth_id: str | None = None,
        send_invite: bool = False,
    ) -> dict[str, Any]:
        """Create a new user.

        Args:
            name: User's display name (max 100 characters)
            email: User's email address
            roles: List of role IDs to assign
            password: User's password (min 8 characters)
            language: Language code (e.g., 'en', 'fr')
            external_auth_id: External authentication ID
            send_invite: Whether to send invite email

        Returns:
            Created user data
        """
        data: dict[str, Any] = {
            "name": name,
            "email": email,
        }
        if roles:
            data["roles"] = roles
        if password:
            data["password"] = password
        if language:
            data["language"] = language
        if external_auth_id:
            data["external_auth_id"] = external_auth_id
        if send_invite:
            data["send_invite"] = send_invite

        return self.client.post(self.ENDPOINT, data=data)

    def update(
        self,
        user_id: int,
        name: str | None = None,
        email: str | None = None,
        roles: list[int] | None = None,
        password: str | None = None,
        language: str | None = None,
        external_auth_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing user.

        Args:
            user_id: ID of user to update
            name: Update display name
            email: Update email address
            roles: Update role assignments
            password: Update password
            language: Update language preference
            external_auth_id: Update external auth ID

        Returns:
            Updated user data
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if email is not None:
            data["email"] = email
        if roles is not None:
            data["roles"] = roles
        if password is not None:
            data["password"] = password
        if language is not None:
            data["language"] = language
        if external_auth_id is not None:
            data["external_auth_id"] = external_auth_id

        return self.client.put(self._get_endpoint(user_id), data=data)

    def delete(
        self,
        user_id: int,
        migrate_ownership_id: int | None = None,
    ) -> dict[str, Any]:
        """Delete a user.

        Args:
            user_id: ID of user to delete
            migrate_ownership_id: ID of user to transfer content ownership to

        Returns:
            Empty dict on success
        """
        data: dict[str, Any] = {}
        if migrate_ownership_id:
            data["migrate_ownership_id"] = migrate_ownership_id

        return self.client.delete(self._get_endpoint(user_id), data=data if data else None)
