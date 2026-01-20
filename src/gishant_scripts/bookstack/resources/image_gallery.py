"""Image gallery resource for BookStack API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gishant_scripts.bookstack.resources.base import CRUDResource


class ImageGalleryResource(CRUDResource):
    """Manage BookStack image gallery.

    Images can be gallery images (used in page content) or drawings
    (diagrams created via draw.io).
    """

    ENDPOINT = "image-gallery"

    def list(
        self,
        count: int | None = None,
        offset: int | None = None,
        sort: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List images visible to the user.

        Args:
            count: Number of items to return
            offset: Number of items to skip
            sort: Field to sort by
            filters: Filter criteria (e.g., {"type": "gallery"})

        Returns:
            Response with 'data' list and 'total' count
        """
        return super().list(count=count, offset=offset, sort=sort, filters=filters)

    def create(
        self,
        uploaded_to: int,
        image_path: Path,
        name: str | None = None,
        image_type: str = "gallery",
    ) -> dict[str, Any]:
        """Upload a new image.

        Args:
            uploaded_to: Page ID to associate image with
            image_path: Path to image file
            name: Image name (defaults to filename)
            image_type: Type of image ('gallery' or 'drawio')

        Returns:
            Created image data
        """
        data: dict[str, Any] = {
            "type": image_type,
            "uploaded_to": uploaded_to,
        }
        if name:
            data["name"] = name

        files = {"image": (image_path.name, image_path.open("rb"))}
        return self.client.post(self.ENDPOINT, data=data, files=files)

    def read(self, image_id: int) -> dict[str, Any]:
        """Read image details.

        Args:
            image_id: Image ID

        Returns:
            Image data including:
            - thumbs: Dictionary of thumbnail URLs
            - content: HTML and Markdown snippets for embedding
        """
        result = self.client.get(self._get_endpoint(image_id))
        if isinstance(result, bytes):
            return {}
        return result

    def read_data(self, image_id: int) -> bytes:
        """Read raw image data.

        Args:
            image_id: Image ID

        Returns:
            Image file bytes
        """
        result = self.client.get(self._get_endpoint(image_id, "data"))
        if isinstance(result, bytes):
            return result
        return b""

    def read_data_for_url(self, url: str) -> bytes:
        """Read raw image data using image URL.

        Args:
            url: Full image URL

        Returns:
            Image file bytes
        """
        result = self.client.get("image-gallery/url/data", params={"url": url})
        if isinstance(result, bytes):
            return result
        return b""

    def update(
        self,
        image_id: int,
        name: str | None = None,
        image_path: Path | None = None,
    ) -> dict[str, Any]:
        """Update an existing image.

        Args:
            image_id: ID of image to update
            name: Update image name
            image_path: Replace image file

        Returns:
            Updated image data
        """
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name

        if image_path:
            files = {"image": (image_path.name, image_path.open("rb"))}
            return self.client.put(self._get_endpoint(image_id), data=data, files=files)

        return self.client.put(self._get_endpoint(image_id), data=data)

    def download(self, image_id: int, output_path: Path) -> Path:
        """Download an image to a file.

        Args:
            image_id: Image ID
            output_path: Path to save the image

        Returns:
            Path to saved file
        """
        data = self.read_data(image_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return output_path
