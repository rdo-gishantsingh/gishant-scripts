"""Tests for the multi-project configuration loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from gishant_scripts.testdata.config import (
    ProjectConfig,
    allowed_project_keys,
    load_projects,
    resolve_project,
)


@pytest.fixture()
def tmp_toml(tmp_path: Path) -> Path:
    toml = tmp_path / "projects.toml"
    toml.write_text(
        """
[projects.SGAYONTEST]
shotgrid = "SGAYONTEST"
kitsu = "SGAYONTEST"
ayon = "SGAYONTEST"
storage = "SGAYONTEST"

[projects.BARBIE_NUTCRACKER]
shotgrid = "Barbie_Nutcracker"
kitsu = "Barbie Nutcracker"
ayon = "barbie_nutcracker"
storage = "Barbie_Nutcracker"
"""
    )
    return toml


def test_load_projects_returns_all_keys(tmp_toml: Path) -> None:
    projects = load_projects(tmp_toml)

    assert set(projects) == {"SGAYONTEST", "BARBIE_NUTCRACKER"}


def test_load_projects_maps_backend_names(tmp_toml: Path) -> None:
    projects = load_projects(tmp_toml)
    cfg = projects["BARBIE_NUTCRACKER"]

    assert cfg.canonical_key == "BARBIE_NUTCRACKER"
    assert cfg.shotgrid == "Barbie_Nutcracker"
    assert cfg.kitsu == "Barbie Nutcracker"
    assert cfg.ayon == "barbie_nutcracker"
    assert cfg.storage == "Barbie_Nutcracker"


def test_resolve_project_returns_config(tmp_toml: Path) -> None:
    cfg = resolve_project("SGAYONTEST", tmp_toml)

    assert isinstance(cfg, ProjectConfig)
    assert cfg.shotgrid == "SGAYONTEST"
    assert cfg.kitsu == "SGAYONTEST"
    assert cfg.ayon == "SGAYONTEST"


def test_resolve_project_raises_for_unknown_key(tmp_toml: Path) -> None:
    with pytest.raises(KeyError, match="UNKNOWN"):
        resolve_project("UNKNOWN", tmp_toml)


def test_allowed_project_keys_matches_loaded_keys(tmp_toml: Path) -> None:
    keys = allowed_project_keys(tmp_toml)

    assert keys == frozenset({"SGAYONTEST", "BARBIE_NUTCRACKER"})


def test_default_toml_contains_sgayontest() -> None:
    # Verifies the shipped projects.toml is valid and backward-compatible.
    keys = allowed_project_keys()

    assert "SGAYONTEST" in keys


def test_default_sgayontest_all_names_match() -> None:
    cfg = resolve_project("SGAYONTEST")

    assert cfg.shotgrid == cfg.kitsu == cfg.ayon == "SGAYONTEST"


def test_storage_falls_back_to_shotgrid_when_omitted(tmp_path: Path) -> None:
    toml = tmp_path / "projects.toml"
    toml.write_text(
        """
[projects.NO_STORAGE_KEY]
shotgrid = "NoStorage_SG"
kitsu = "NoStorage Kitsu"
ayon = "nostorage_ayon"
"""
    )
    cfg = resolve_project("NO_STORAGE_KEY", toml)

    assert cfg.storage == "NoStorage_SG"


def test_default_sgayontest_has_storage_field() -> None:
    cfg = resolve_project("SGAYONTEST")

    assert cfg.storage == "SGAYONTEST"
