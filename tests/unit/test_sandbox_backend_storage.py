"""Tests for StorageBackend name resolution and NAS-root fallback."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from gishant_scripts.sandbox.backends.storage import StorageBackend
from gishant_scripts.sandbox.config import ProjectConfig

if TYPE_CHECKING:
    import pytest

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


def test_resolve_root_falls_back_when_ayon_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys
    import types

    fake = types.ModuleType("ayon_api")

    def _raise(*_args, **_kwargs):
        raise RuntimeError("no connection")

    fake.get = _raise
    monkeypatch.setitem(sys.modules, "ayon_api", fake)
    root = StorageBackend("DEMO").resolve_root("Demo_Ayon")
    assert root == Path("/projects")
