"""Comments resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import CRUDResource


class CommentsResource(CRUDResource):
    """Manage BookStack comments.

    Comments are associated with pages and can be nested as replies.
    """

    ENDPOINT = "comments"

    def create(
        self,
        page_id: int,
        html: str,
        reply_to: int | None = None,
        content_ref: str | None = None,
    ) -> dict[str, Any]:
        """Create a new comment on a page.

        Args:
            page_id: Page ID to comment on
            html: Comment content as HTML
            reply_to: Local ID of parent comment (for replies)
            content_ref: Content reference string

        Returns:
            Created comment data
        """
        data: dict[str, Any] = {
            "page_id": page_id,
            "html": html,
        }
        if reply_to is not None:
            data["reply_to"] = reply_to
        if content_ref is not None:
            data["content_ref"] = content_ref

        return self.client.post(self.ENDPOINT, data=data)

    def update(
        self,
        comment_id: int,
        html: str | None = None,
        archived: bool | None = None,
    ) -> dict[str, Any]:
        """Update an existing comment.

        Only top-level comments (non-replies) can be archived/unarchived.

        Args:
            comment_id: ID of comment to update
            html: Update comment content
            archived: Update archive status

        Returns:
            Updated comment data
        """
        data: dict[str, Any] = {}
        if html is not None:
            data["html"] = html
        if archived is not None:
            data["archived"] = archived

        return self.client.put(self._get_endpoint(comment_id), data=data)

    def list_by_page(self, page_id: int) -> list[dict[str, Any]]:
        """List all comments for a page.

        Args:
            page_id: Page ID

        Returns:
            List of comments
        """
        return self.list_all(filters={"commentable_id": page_id})
