"""System resource for BookStack API."""

from __future__ import annotations

from typing import Any

from gishant_scripts.bookstack.resources.base import BaseResource


class SystemResource(BaseResource):
    """Access BookStack system information."""

    ENDPOINT = "system"

    def info(self) -> dict[str, Any]:
        """Get BookStack system information.

        Returns:
            System info including:
            - version: BookStack version
            - instance_id: Unique instance identifier
            - app_name: Configured application name
            - app_logo: URL to application logo (may be null)
            - base_url: Base URL of the instance
        """
        result = self.client.get(self.ENDPOINT)
        if isinstance(result, bytes):
            return {}
        return result
