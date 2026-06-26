"""Tests for sandbox project-name configuration."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from gishant_scripts.sandbox.config import (
    allowed_project_keys,
    resolve_project,
)


@pytest.fixture
def projects_file(tmp_path: Path) -> Path:
    content = textwrap.dedent(
        """
        [projects.DEMO]
        shotgrid = "DEMO_SG"
        kitsu = "Demo Kitsu"
        ayon = "Demo_Ayon"
        storage = "Demo_Store"

        [projects.NOSTORE]
        shotgrid = "NoStore"
        kitsu = "NoStore"
        ayon = "NoStore"
        """
    )
    path = tmp_path / "projects.toml"
    path.write_text(content)
    return path


def test_load_and_resolve(projects_file: Path) -> None:
    cfg = resolve_project("DEMO", projects_file)
    assert cfg.kitsu == "Demo Kitsu"
    assert cfg.shotgrid == "DEMO_SG"
    assert cfg.ayon == "Demo_Ayon"
    assert cfg.storage == "Demo_Store"


def test_storage_defaults_to_shotgrid(projects_file: Path) -> None:
    cfg = resolve_project("NOSTORE", projects_file)
    assert cfg.storage == "NoStore"


def test_unknown_key_raises(projects_file: Path) -> None:
    with pytest.raises(KeyError):
        resolve_project("MISSING", projects_file)


def test_allowed_keys(projects_file: Path) -> None:
    assert allowed_project_keys(projects_file) == frozenset({"DEMO", "NOSTORE"})
