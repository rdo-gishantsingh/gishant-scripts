"""AYON backend connection."""

from __future__ import annotations

import os

from sandbox.backends.base import (
    Backend,
    BackendUnavailableError,
    load_rdo_env,
)


class AyonBackend(Backend):
    """Credentials, connection, and name for AYON (via ayon_api)."""

    @property
    def project_name(self) -> str:
        """Return the AYON-specific project name."""
        return self._project_config.ayon if self._project_config else self._raw_project_name

    def credentials(self) -> tuple[str | None, str | None]:
        """Return ``(server_url, api_key)`` for the active environment."""
        load_rdo_env()
        if self._environment.is_test:
            return (
                os.environ.get("AYON_TEST_SERVER_URL"),
                os.environ.get("AYON_TEST_API_KEY"),
            )
        return os.environ.get("AYON_SERVER_URL"), os.environ.get("AYON_API_KEY")

    def connect(self) -> object:
        """Configure and return the ``ayon_api`` module. Raise BackendUnavailableError on failure."""
        server_url, api_key = self.credentials()
        if not server_url or not api_key:
            prefix = "AYON_TEST_" if self._environment.is_test else "AYON_"
            msg = f"AYON: {prefix}SERVER_URL or {prefix}API_KEY not set"
            raise BackendUnavailableError(msg)
        try:
            import ayon_api
        except ImportError as exc:
            msg = "AYON: ayon_api not installed"
            raise BackendUnavailableError(msg) from exc
        os.environ["AYON_SERVER_URL"] = server_url
        os.environ["AYON_API_KEY"] = api_key
        if not ayon_api.is_connection_created():
            ayon_api.create_connection()
        return ayon_api
