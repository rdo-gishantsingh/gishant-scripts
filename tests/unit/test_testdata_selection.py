"""Tests for granular testdata sequence and shot selection."""

from __future__ import annotations

from gishant_scripts.testdata.selection import SelectionScope


def test_empty_scope_matches_every_sequence_and_shot() -> None:
    scope = SelectionScope()

    assert scope.matches_sequence("ep_test_sq010")
    assert scope.matches_shot("ep_test_sq010", "ep_test_sq010_sh0010")
    assert scope.is_episode_scope


def test_sequence_patterns_match_exact_names_and_globs() -> None:
    scope = SelectionScope(sequence_patterns=("ep_test_sq010", "*sq030"))

    assert scope.matches_sequence("ep_test_sq010")
    assert scope.matches_sequence("ep_test_sq030")
    assert not scope.matches_sequence("ep_test_sq020")
    assert scope.is_sequence_scope
    assert not scope.is_episode_scope


def test_shot_patterns_match_full_shot_names() -> None:
    scope = SelectionScope(shot_patterns=("ep_test_sq010_sh0020", "*_sh0040"))

    assert scope.matches_shot("ep_test_sq010", "ep_test_sq010_sh0020")
    assert scope.matches_shot("ep_test_sq020", "ep_test_sq020_sh0040")
    assert not scope.matches_shot("ep_test_sq010", "ep_test_sq010_sh0030")
    assert scope.is_shot_scope
    assert not scope.is_episode_scope


def test_shot_matching_respects_sequence_scope() -> None:
    scope = SelectionScope(sequence_patterns=("ep_test_sq010",), shot_patterns=("*_sh0020",))

    assert scope.matches_shot("ep_test_sq010", "ep_test_sq010_sh0020")
    assert not scope.matches_shot("ep_test_sq020", "ep_test_sq020_sh0020")


def test_patterns_are_normalized_from_lists_and_empty_values() -> None:
    scope = SelectionScope(sequence_patterns=["", "ep_test_sq010", "ep_test_sq010"], shot_patterns=["*_sh0010", ""])

    assert scope.sequence_patterns == ("ep_test_sq010",)
    assert scope.shot_patterns == ("*_sh0010",)
