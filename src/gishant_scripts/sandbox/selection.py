"""Shared selection helpers for granular testdata operations."""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field


def _normalize_patterns(patterns: Iterable[str] | None = None) -> tuple[str, ...]:
    """Return non-empty patterns in stable order without duplicates."""
    if not patterns:
        return ()

    normalized: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        value = pattern.strip()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return tuple(normalized)


def _matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    """Return True when *name* matches any exact or glob pattern."""
    if not patterns:
        return True
    return any(name == pattern or fnmatch.fnmatch(name, pattern) for pattern in patterns)


@dataclass(frozen=True)
class SelectionScope:
    """Exact/glob sequence and shot selectors shared by generate and cleanup."""

    sequence_patterns: Iterable[str] | None = field(default=None)
    shot_patterns: Iterable[str] | None = field(default=None)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence_patterns", _normalize_patterns(self.sequence_patterns))
        object.__setattr__(self, "shot_patterns", _normalize_patterns(self.shot_patterns))

    @property
    def is_episode_scope(self) -> bool:
        """Return True when no sequence or shot filters narrow the operation."""
        return not self.sequence_patterns and not self.shot_patterns

    @property
    def is_sequence_scope(self) -> bool:
        """Return True when sequence filters are present and shot filters are not."""
        return bool(self.sequence_patterns) and not self.shot_patterns

    @property
    def is_shot_scope(self) -> bool:
        """Return True when shot filters are present."""
        return bool(self.shot_patterns)

    def matches_sequence(self, sequence_name: str) -> bool:
        """Return True when a sequence name is selected."""
        return _matches_any(sequence_name, self.sequence_patterns)

    def matches_shot(self, sequence_name: str, shot_name: str) -> bool:
        """Return True when a shot is selected within its sequence."""
        return self.matches_sequence(sequence_name) and _matches_any(shot_name, self.shot_patterns)
