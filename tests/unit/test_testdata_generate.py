"""Tests for granular testdata generation planning."""

from __future__ import annotations

from rich.console import Console

from gishant_scripts.testdata.generate import EpisodeGenerator
from gishant_scripts.testdata.selection import SelectionScope


def _generator(*, scope: SelectionScope | None = None, sequences: int = 3, shots: int = 3) -> EpisodeGenerator:
    return EpisodeGenerator(
        project_name="SGAYONTEST",
        episode_name="ep_test",
        num_sequences=sequences,
        shots_per_sequence=shots,
        console=Console(),
        selection_scope=scope,
    )


def test_plan_filters_count_generated_sequences_and_shots() -> None:
    scope = SelectionScope(sequence_patterns=("*sq020",), shot_patterns=("*_sh0030",))

    plan = _generator(scope=scope).plan()

    assert plan.sequences == ["ep_test_sq020"]
    assert plan.shots == {"ep_test_sq020": ["ep_test_sq020_sh0030"]}


def test_plan_can_create_explicit_sequence_without_counts() -> None:
    scope = SelectionScope(sequence_patterns=("ep_test_sq040",))

    plan = _generator(scope=scope, sequences=0, shots=0).plan()

    assert plan.sequences == ["ep_test_sq040"]
    assert plan.shots == {"ep_test_sq040": []}


def test_plan_can_create_explicit_shot_and_infer_sequence() -> None:
    scope = SelectionScope(shot_patterns=("ep_test_sq050_sh0010",))

    plan = _generator(scope=scope, sequences=0, shots=0).plan()

    assert plan.sequences == ["ep_test_sq050"]
    assert plan.shots == {"ep_test_sq050": ["ep_test_sq050_sh0010"]}
