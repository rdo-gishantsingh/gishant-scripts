"""Tests for sandbox generation planning (pure, no backend calls)."""

from __future__ import annotations

from rich.console import Console

from gishant_scripts.sandbox.generate import EpisodeGenerator, GenerationPlan
from gishant_scripts.sandbox.selection import SelectionScope


def _gen(**kwargs) -> EpisodeGenerator:
    defaults = {
        "project_name": "DEMO",
        "episode_name": "ep_test",
        "num_sequences": 0,
        "shots_per_sequence": 0,
        "console": Console(),
    }
    defaults.update(kwargs)
    return EpisodeGenerator(**defaults)


def test_count_based_plan() -> None:
    plan = _gen(num_sequences=2, shots_per_sequence=3).plan()
    assert plan.sequences == ["ep_test_sq010", "ep_test_sq020"]
    assert plan.total_shots == 6
    assert plan.shots["ep_test_sq010"] == [
        "ep_test_sq010_sh0010",
        "ep_test_sq010_sh0020",
        "ep_test_sq010_sh0030",
    ]


def test_sequence_glob_filters_generated() -> None:
    scope = SelectionScope(sequence_patterns=["*sq020"])
    plan = _gen(num_sequences=3, shots_per_sequence=0, selection_scope=scope).plan()
    assert plan.sequences == ["ep_test_sq020"]


def test_explicit_shot_infers_sequence() -> None:
    scope = SelectionScope(shot_patterns=["ep_test_sq050_sh0010"])
    plan = _gen(selection_scope=scope).plan()
    assert plan.sequences == ["ep_test_sq050"]
    assert plan.shots["ep_test_sq050"] == ["ep_test_sq050_sh0010"]


def test_generation_plan_total_shots() -> None:
    plan = GenerationPlan(episode_name="e", shots={"a": ["x", "y"], "b": ["z"]})
    assert plan.total_shots == 3
