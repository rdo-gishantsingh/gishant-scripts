"""Backend connection layer for the sandbox tool.

Each backend owns its credentials, connection, and per-backend project-name
resolution. Orchestrators (generate / cleanup) call into these and keep the
operation logic (discovery, create, delete) to themselves.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from gishant_scripts.sandbox.config import ProjectConfig

_RDO_ENV_PATH = Path.home() / ".rdo" / ".env"


class Environment(StrEnum):
    """Target server environment selected by the ``--server`` flag."""

    TEST = "test"
    PRODUCTION = "production"

    @property
    def is_test(self) -> bool:
        """Return True for the test environment."""
        return self is Environment.TEST


class BackendUnavailableError(Exception):
    """Raised when a backend cannot be used (library missing or creds unset)."""


def load_rdo_env() -> None:
    """Load RDO credentials from ``~/.rdo/.env`` into the environment."""
    load_dotenv(_RDO_ENV_PATH)


class Backend(ABC):
    """Base for a single tracking backend: credentials, connection, name."""

    def __init__(
        self,
        raw_project_name: str,
        environment: Environment = Environment.TEST,
        project_config: ProjectConfig | None = None,
    ) -> None:
        self._raw_project_name = raw_project_name
        self._environment = environment
        self._project_config = project_config

    @property
    @abstractmethod
    def project_name(self) -> str:
        """Per-backend project name (from config, fallback to raw name)."""
