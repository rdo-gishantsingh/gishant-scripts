"""Kitsu/Zou backend connection."""

from __future__ import annotations

import os

from sandbox.backends.base import (
    Backend,
    BackendUnavailableError,
    load_rdo_env,
)


class KitsuBackend(Backend):
    """Credentials, connection, and name for Kitsu (via gazu)."""

    @property
    def project_name(self) -> str:
        """Return the Kitsu-specific project name."""
        return self._project_config.kitsu if self._project_config else self._raw_project_name

    def credentials(self) -> tuple[str | None, str | None]:
        """Return ``(host, token)`` for the active environment."""
        load_rdo_env()
        if self._environment.is_test:
            return (
                os.environ.get("RDO_KITSU_TEST_HOST"),
                os.environ.get("RDO_KITSU_TEST_API_TOKEN"),
            )
        return os.environ.get("RDO_KITSU_HOST"), os.environ.get("RDO_KITSU_API_TOKEN")

    def connect(self) -> object:
        """Configure and return the ``gazu`` module. Raise BackendUnavailableError on failure."""
        host, token = self.credentials()
        if not host or not token:
            prefix = "RDO_KITSU_TEST_" if self._environment.is_test else "RDO_KITSU_"
            msg = f"Kitsu: {prefix}HOST or {prefix}API_TOKEN not set"
            raise BackendUnavailableError(msg)
        try:
            import gazu
        except ImportError as exc:
            msg = "Kitsu: gazu not installed"
            raise BackendUnavailableError(msg) from exc
        gazu.set_host(host + "/api")
        gazu.set_token(token)
        return gazu
