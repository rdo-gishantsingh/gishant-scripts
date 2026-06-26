"""ShotGrid backend connection."""

from __future__ import annotations

import os

from gishant_scripts.sandbox.backends.base import (
    Backend,
    BackendUnavailableError,
    load_rdo_env,
)


class ShotGridBackend(Backend):
    """Credentials, connection, and name for ShotGrid (via shotgun_api3).

    ShotGrid credentials are environment-independent (one server for both
    test and production), unlike Kitsu and AYON.
    """

    @property
    def project_name(self) -> str:
        """Return the ShotGrid-specific project name."""
        return self._project_config.shotgrid if self._project_config else self._raw_project_name

    def credentials(self) -> tuple[str | None, str | None, str | None]:
        """Return ``(url, script_name, api_key)``."""
        load_rdo_env()
        return (
            os.environ.get("SHOTGRID_SERVER_URL"),
            os.environ.get("SHOTGRID_SCRIPT"),
            os.environ.get("SHOTGRID_API_KEY"),
        )

    def connect(self) -> object:
        """Return a ``shotgun_api3.Shotgun`` instance. Raise BackendUnavailableError on failure."""
        url, script, key = self.credentials()
        if not url or not script or not key:
            msg = "ShotGrid: SHOTGRID_SERVER_URL, SHOTGRID_SCRIPT, or SHOTGRID_API_KEY not set"
            raise BackendUnavailableError(msg)
        try:
            import shotgun_api3
        except ImportError as exc:
            msg = "ShotGrid: shotgun_api3 not installed"
            raise BackendUnavailableError(msg) from exc
        return shotgun_api3.Shotgun(url, script_name=script, api_key=key)
