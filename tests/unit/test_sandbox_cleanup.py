"""Tests for sandbox path-cleanup planning (fake AYON, no live calls)."""

from __future__ import annotations

import pytest
from rich.console import Console

from gishant_scripts.sandbox.cleanup import FolderCleanup, FolderDeletionPlan


def test_deletion_plan_is_empty_by_default() -> None:
    assert FolderDeletionPlan().is_empty


def test_deletion_plan_not_empty_with_folders() -> None:
    plan = FolderDeletionPlan(ayon_folders=[{"id": "1"}])
    assert not plan.is_empty


def test_empty_path_rejected() -> None:
    with pytest.raises(ValueError, match="path must not be empty"):
        FolderCleanup("DEMO", "/", Console())


class _FakeAyon:
    """Minimal stand-in for the ayon_api module used by _walk_ayon_path."""

    def __init__(self, folders: dict[str, dict]) -> None:
        self._by_path = folders

    def get_folder_by_path(self, _project: str, path: str) -> dict | None:
        return self._by_path.get(path)

    def get_folders(self, _project: str, parent_ids=None):
        if parent_ids is None:
            return list(self._by_path.values())
        parent = set(parent_ids)
        return [f for f in self._by_path.values() if f.get("parentId") in parent]


def test_walk_exact_path_returns_single_folder() -> None:
    fake = _FakeAyon({"assets/vehicles": {"id": "v1", "name": "vehicles", "parentId": None}})
    cleaner = FolderCleanup("DEMO", "/assets/vehicles", Console())
    matched = cleaner._walk_ayon_path(fake)
    assert [f["id"] for f in matched] == ["v1"]


def test_walk_glob_segment_matches_children() -> None:
    fake = _FakeAyon(
        {
            "assets": {"id": "a", "name": "assets", "parentId": None},
            "_child_car": {"id": "c1", "name": "car_suv", "parentId": "a"},
            "_child_van": {"id": "c2", "name": "van", "parentId": "a"},
        }
    )
    cleaner = FolderCleanup("DEMO", "/assets/car*", Console())
    matched = cleaner._walk_ayon_path(fake)
    assert [f["id"] for f in matched] == ["c1"]
