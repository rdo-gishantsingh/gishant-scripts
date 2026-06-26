"""Tests for StorageBackend name resolution and NAS-root fallback."""

from __future__ import annotations

from pathlib import Path

from gishant_scripts.sandbox.backends.storage import StorageBackend
from gishant_scripts.sandbox.config import ProjectConfig

_CFG = ProjectConfig(
    canonical_key="DEMO",
    shotgrid="DEMO_SG",
    kitsu="Demo Kitsu",
    ayon="Demo_Ayon",
    storage="Demo_Store",
)


def test_project_name_uses_config() -> None:
    assert StorageBackend("DEMO", project_config=_CFG).project_name == "Demo_Store"


def test_project_name_falls_back_to_raw() -> None:
    assert StorageBackend("DEMO").project_name == "DEMO"


def test_resolve_root_falls_back_when_ayon_unavailable() -> None:
    # ayon_api is not connected / not configured in the test env, so resolve_root
    # must swallow the error and return the default root.
    root = StorageBackend("DEMO").resolve_root("Demo_Ayon")
    assert root == Path("/projects")
