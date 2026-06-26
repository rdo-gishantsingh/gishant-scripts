"""Tests for the sandbox CLI surface (no live backend calls)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from gishant_scripts.sandbox.cleanup import FolderDeletionPlan, ProjectRemovalPlan
from gishant_scripts.sandbox.cli import app
from gishant_scripts.sandbox.generate import GenerationPlan

runner = CliRunner()


def test_cleanup_requires_path_or_projects() -> None:
    result = runner.invoke(app, ["cleanup"])
    assert result.exit_code != 0
    assert "path" in result.output.lower() or "projects" in result.output.lower()


def test_cleanup_rejects_both_path_and_projects() -> None:
    result = runner.invoke(app, ["cleanup", "/assets/x", "--projects", "_test*"])
    assert result.exit_code != 0
    assert "mutually exclusive" in result.output.lower()


def test_cleanup_path_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeCleanup:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> FolderDeletionPlan:
            return FolderDeletionPlan(ayon_folders=[{"id": "1", "name": "x", "path": "/assets/x"}])
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None:
            raise AssertionError("execute must not run in dry-run")

    monkeypatch.setattr("gishant_scripts.sandbox.cli.FolderCleanup", FakeCleanup)
    result = runner.invoke(app, ["cleanup", "/assets/x", "-p", "SGAYONTEST"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


def test_cleanup_projects_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeRemoval:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> ProjectRemovalPlan:
            return ProjectRemovalPlan(kitsu_projects=[{"name": "_test_a"}])
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None:
            raise AssertionError("execute must not run in dry-run")

    monkeypatch.setattr("gishant_scripts.sandbox.cli.ProjectRemoval", FakeRemoval)
    result = runner.invoke(app, ["cleanup", "--projects", "_test*"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output


def test_generate_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeGenerator:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> GenerationPlan:
            return GenerationPlan(episode_name="ep_test", sequences=[], shots={})
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None:
            raise AssertionError("execute must not run in dry-run")

    class FakeCleanup:
        def __init__(self, *a, **k) -> None: ...
        def plan(self) -> FolderDeletionPlan:
            return FolderDeletionPlan()
        def display_plan(self, _plan) -> None: ...
        def execute(self, _plan) -> None: ...

    monkeypatch.setattr("gishant_scripts.sandbox.cli.EpisodeGenerator", FakeGenerator)
    monkeypatch.setattr("gishant_scripts.sandbox.cli.FolderCleanup", FakeCleanup)
    result = runner.invoke(app, ["generate", "ep_test", "-p", "SGAYONTEST", "--sequences", "2"])
    assert result.exit_code == 0
    assert "DRY RUN" in result.output
