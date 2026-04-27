"""Tests for the testdata CLI surface."""

from __future__ import annotations

from typer.testing import CliRunner

from gishant_scripts.testdata.cleanup import DeletionPlan
from gishant_scripts.testdata.cli import app
from gishant_scripts.testdata.generate import GenerationPlan

runner = CliRunner()


def test_cleanup_help_includes_granular_selectors() -> None:
    result = runner.invoke(app, ["cleanup", "--help"])

    assert result.exit_code == 0
    assert "--sequence" in result.output
    assert "--shot" in result.output


def test_generate_help_includes_granular_selectors_and_replace_flag() -> None:
    result = runner.invoke(app, ["generate", "--help"])

    assert result.exit_code == 0
    assert "--sequence" in result.output
    assert "--shot" in result.output
    assert "--replace-existing" in result.output


def test_cleanup_passes_selection_scope_to_cleaner(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeCleanup:
        def __init__(self, **kwargs) -> None:
            seen["scope"] = kwargs["selection_scope"]

        def plan(self) -> DeletionPlan:
            return DeletionPlan()

        def display_plan(self, _plan: DeletionPlan) -> None:
            return None

    monkeypatch.setattr("gishant_scripts.testdata.cleanup.EpisodeCleanup", FakeCleanup)

    result = runner.invoke(
        app,
        ["cleanup", "ep_test", "--sequence", "ep_test_sq010", "--shot", "*_sh0010"],
    )

    assert result.exit_code == 0
    assert seen["scope"].sequence_patterns == ("ep_test_sq010",)
    assert seen["scope"].shot_patterns == ("*_sh0010",)


def test_generate_passes_selection_scope_to_generator_and_conflict_checker(monkeypatch) -> None:
    seen: dict[str, object] = {}

    class FakeGenerator:
        def __init__(self, **kwargs) -> None:
            seen["generator_scope"] = kwargs["selection_scope"]

        def plan(self) -> GenerationPlan:
            return GenerationPlan(episode_name="ep_test", sequences=[], shots={})

        def display_plan(self, _plan: GenerationPlan) -> None:
            return None

    class FakeCleanup:
        def __init__(self, **kwargs) -> None:
            seen["cleanup_scope"] = kwargs["selection_scope"]

        def plan(self) -> DeletionPlan:
            return DeletionPlan()

        def display_plan(self, _plan: DeletionPlan) -> None:
            return None

    monkeypatch.setattr("gishant_scripts.testdata.generate.EpisodeGenerator", FakeGenerator)
    monkeypatch.setattr("gishant_scripts.testdata.cleanup.EpisodeCleanup", FakeCleanup)

    result = runner.invoke(
        app,
        ["generate", "ep_test", "--sequence", "ep_test_sq010", "--shot", "*_sh0010"],
    )

    assert result.exit_code == 0
    assert seen["generator_scope"].sequence_patterns == ("ep_test_sq010",)
    assert seen["generator_scope"].shot_patterns == ("*_sh0010",)
    assert seen["cleanup_scope"].sequence_patterns == ("ep_test_sq010",)
    assert seen["cleanup_scope"].shot_patterns == ("*_sh0010",)


def test_generate_blocks_existing_items_without_replace(monkeypatch) -> None:
    executed = False

    class FakeGenerator:
        def __init__(self, **_kwargs) -> None:
            return None

        def plan(self) -> GenerationPlan:
            return GenerationPlan(episode_name="ep_test", sequences=["ep_test_sq010"], shots={"ep_test_sq010": []})

        def display_plan(self, _plan: GenerationPlan) -> None:
            return None

        def execute(self, _plan: GenerationPlan) -> None:
            nonlocal executed
            executed = True

    class FakeCleanup:
        def __init__(self, **_kwargs) -> None:
            return None

        def plan(self) -> DeletionPlan:
            return DeletionPlan(kitsu_sequences=[{"id": "seq-1", "name": "ep_test_sq010"}])

        def display_plan(self, _plan: DeletionPlan) -> None:
            return None

    monkeypatch.setattr("gishant_scripts.testdata.generate.EpisodeGenerator", FakeGenerator)
    monkeypatch.setattr("gishant_scripts.testdata.cleanup.EpisodeCleanup", FakeCleanup)

    result = runner.invoke(app, ["generate", "ep_test", "--execute"])

    assert result.exit_code == 0
    assert "--replace-existing" in result.output
    assert not executed
