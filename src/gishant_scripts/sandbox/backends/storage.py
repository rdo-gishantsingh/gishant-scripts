"""NAS storage backend — path resolution for project folders on disk."""

from __future__ import annotations

import logging
from pathlib import Path

from gishant_scripts.sandbox.backends.base import Backend

_log = logging.getLogger(__name__)

_DEFAULT_ROOT = Path("/projects")


class StorageBackend(Backend):
    """Per-backend name plus NAS-root resolution for project folders."""

    @property
    def project_name(self) -> str:
        """Return the NAS folder name for this project."""
        return self._project_config.storage if self._project_config else self._raw_project_name

    def resolve_root(self, ayon_project_name: str) -> Path:
        """Resolve the NAS project root from AYON anatomy, fallback /projects.

        Requires an active AYON connection. Any failure (AYON unavailable,
        anatomy not configured) falls back to ``/projects``.
        """
        try:
            import ayon_api

            response = ayon_api.get(f"projects/{ayon_project_name}/anatomy")
            roots = response.data.get("roots", [])
            for root in roots:
                if root.get("name") == "work" and root.get("linux"):
                    return Path(root["linux"])
            for root in roots:
                if root.get("linux"):
                    return Path(root["linux"])
        except Exception:  # AYON unavailable or anatomy not configured
            _log.debug("Could not resolve storage root from AYON anatomy; using %s", _DEFAULT_ROOT)
        return _DEFAULT_ROOT
