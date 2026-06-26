"""Tests for whole-project removal planning (mocked backends)."""

from __future__ import annotations

from rich.console import Console

from gishant_scripts.sandbox.cleanup import ProjectRemoval, ProjectRemovalPlan


def test_plan_empty_by_default() -> None:
    assert ProjectRemovalPlan().is_empty


def test_match_glob_filters_names() -> None:
    names = ["_test_a", "_test_b", "WEDRO", "prod"]
    matched = ProjectRemoval._match(names, "_test*")
    assert matched == ["_test_a", "_test_b"]


def test_match_exact_name() -> None:
    assert ProjectRemoval._match(["WEDRO", "WED"], "WEDRO") == ["WEDRO"]


def test_remover_constructs_without_project_config() -> None:
    remover = ProjectRemoval("_test*", Console())
    # No canonical project; backends carry empty config.
    assert remover._kitsu._project_config is None
