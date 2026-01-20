"""Attachments resource for BookStack API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gishant_scripts.bookstack.resources.base import CRUDResource


class AttachmentsResource(CRUDResource):
    """Manage BookStack attachments.

    Attachments can be either file uploads or external links
    associated with pages.
    """

    ENDPOINT = "attachments"

    def create_link(
        self,
        name: str,
        uploaded_to: int,
        link: str,
    ) -> dict[str, Any]:
        """Create a link attachment.

        Args:
            name: Attachment name (max 255 characters)
            uploaded_to: Page ID to attach to
            link: External URL

        Returns:
            Created attachment data
        """
        return self.client.post(
            self.ENDPOINT,
            data={
                "name": name,
                "uploaded_to": uploaded_to,
                "link": link,
            },
        )

    def create_file(
        self,
        name: str,
        uploaded_to: int,
        file_path: Path,
    ) -> dict[str, Any]:
        """Create a file attachment.

        Args:
            name: Attachment name (max 255 characters)
            uploaded_to: Page ID to attach to
            file_path: Path to file to upload

        Returns:
            Created attachment data
        """
        files = {"file": (file_path.name, file_path.open("rb"))}
        data = {
            "name": name,
            "uploaded_to": uploaded_to,
        }
        return self.client.post(self.ENDPOINT, data=data, files=files)

    def update(
        self,
        attachment_id: int,
        name: str | None = None,
        uploaded_to: int | None = None,
        link: str | None = None,
        file_path: Path | None = None,
    ) -> dict[str, Any]:
        """Update an existing attachment.

        Args:
            attachment_id: ID of attachment to update
            name: New attachment name
            uploaded_to: Move to different page
            link: Update link URL (for link attachments)
            file_path: Update file (for file attachments)

        Returns:
            Updated attachment data
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if uploaded_to is not None:
            data["uploaded_to"] = uploaded_to
        if link is not None:
            data["link"] = link

        if file_path:
            files = {"file": (file_path.name, file_path.open("rb"))}
            return self.client.put(self._get_endpoint(attachment_id), data=data, files=files)

        return self.client.put(self._get_endpoint(attachment_id), data=data)

    def read(self, attachment_id: int) -> dict[str, Any]:
        """Read attachment details and content.

        For file attachments, the 'content' field contains base64-encoded data.
        For link attachments, the 'content' field contains the URL.

        Args:
            attachment_id: Attachment ID

        Returns:
            Attachment data with content
        """
        result = self.client.get(self._get_endpoint(attachment_id))
        if isinstance(result, bytes):
            return {}
        return result

    def list_by_page(self, page_id: int) -> list[dict[str, Any]]:
        """List all attachments for a page.

        Args:
            page_id: Page ID

        Returns:
            List of attachments
        """
        return self.list_all(filters={"uploaded_to": page_id})
