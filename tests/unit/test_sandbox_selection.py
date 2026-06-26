"""Tests for sandbox sequence and shot selection."""

from __future__ import annotations

from gishant_scripts.sandbox.selection import SelectionScope


def test_episode_scope_when_no_patterns() -> None:
    scope = SelectionScope()
    assert scope.is_episode_scope
    assert scope.matches_sequence("ep_test_sq010")
    assert scope.matches_shot("ep_test_sq010", "ep_test_sq010_sh0010")


def test_sequence_glob_matches() -> None:
    scope = SelectionScope(sequence_patterns=["*sq020"])
    assert scope.is_sequence_scope
    assert scope.matches_sequence("ep_test_sq020")
    assert not scope.matches_sequence("ep_test_sq010")


def test_shot_scope_requires_sequence_and_shot_match() -> None:
    scope = SelectionScope(shot_patterns=["*_sh0030"])
    assert scope.is_shot_scope
    assert scope.matches_shot("ep_test_sq020", "ep_test_sq020_sh0030")
    assert not scope.matches_shot("ep_test_sq020", "ep_test_sq020_sh0010")


def test_patterns_normalized_and_deduped() -> None:
    scope = SelectionScope(sequence_patterns=[" a ", "a", "", "b"])
    assert tuple(scope.sequence_patterns) == ("a", "b")
