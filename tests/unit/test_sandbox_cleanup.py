"""Tests for sandbox path-cleanup planning (fake AYON, no live calls)."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

import pytest
from rich.console import Console

from gishant_scripts.sandbox.cleanup import (
    FolderCleanup,
    FolderDeletionPlan,
    _assess_risk,
    _coerce_created_at,
    _entity_source,
    _folder_index,
    _risk_banner_text,
)


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


# --------------------------------------------------------------------------
# Provenance parsing
# --------------------------------------------------------------------------


def test_coerce_created_at_from_datetime_keeps_tz() -> None:
    dt = datetime(2024, 11, 21, 9, 30, tzinfo=UTC)
    assert _coerce_created_at(dt) == dt


def test_coerce_created_at_from_naive_datetime_assumes_utc() -> None:
    naive = datetime(2024, 11, 21, 9, 30)  # noqa: DTZ001 - deliberately naive input
    assert _coerce_created_at(naive) == datetime(2024, 11, 21, 9, 30, tzinfo=UTC)


def test_coerce_created_at_from_iso_string() -> None:
    assert _coerce_created_at("2024-11-21T09:30:00Z") == datetime(2024, 11, 21, 9, 30, tzinfo=UTC)


def test_coerce_created_at_from_garbage_is_none() -> None:
    assert _coerce_created_at("not-a-date") is None
    assert _coerce_created_at(None) is None


# --------------------------------------------------------------------------
# Risk assessment heuristic (the real guardrail)
# --------------------------------------------------------------------------

_NOW = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)


def test_assess_risk_flags_aged_multi_author_target() -> None:
    records = [
        {"created_at": datetime(2024, 11, 21, tzinfo=UTC), "created_by": {"name": "Alice"}},
        {"created_at": datetime(2025, 3, 2, tzinfo=UTC), "created_by": {"name": "Bob"}},
        {"created_at": _NOW, "created_by": {"name": "Alice"}},
    ]
    risk = _assess_risk(records, _NOW)
    assert risk.total == 3
    assert risk.created_earlier == 2
    assert risk.created_today == 1
    assert risk.oldest == datetime(2024, 11, 21, tzinfo=UTC)
    assert risk.authors == ["Alice", "Bob"]
    assert risk.is_risky


def test_assess_risk_fresh_single_author_target_is_safe() -> None:
    records = [
        {"created_at": _NOW, "created_by": {"name": "sandbox-service"}},
        {"created_at": _NOW, "created_by": {"name": "sandbox-service"}},
    ]
    risk = _assess_risk(records, _NOW)
    assert risk.created_earlier == 0
    assert risk.authors == ["sandbox-service"]
    assert not risk.is_risky


def test_assess_risk_fresh_but_multiple_authors_is_risky() -> None:
    records = [
        {"created_at": _NOW, "created_by": {"name": "sandbox-service"}},
        {"created_at": _NOW, "created_by": {"name": "real-artist"}},
    ]
    risk = _assess_risk(records, _NOW)
    assert risk.created_earlier == 0
    assert risk.is_risky  # a second author means it is not pure service output


def test_assess_risk_empty_is_not_risky() -> None:
    risk = _assess_risk([], _NOW)
    assert risk.total == 0
    assert not risk.is_risky


def test_risk_banner_text_reports_counts_and_oldest() -> None:
    risk = _assess_risk(
        [
            {"created_at": datetime(2024, 11, 21, tzinfo=UTC), "created_by": {"name": "Alice"}},
            {"created_at": _NOW, "created_by": {"name": "Bob"}},
        ],
        _NOW,
    )
    text = _risk_banner_text(risk)
    assert "1/2 entities predate today" in text
    assert "2024-11-21" in text
    assert "Alice" in text
    assert "not fresh sandbox data" in text


# --------------------------------------------------------------------------
# Path resolution + source classification
# --------------------------------------------------------------------------

_FOLDERS = [
    {"folderType": "Episode", "name": "hitro104", "path": "/episodes/hitro104", "id": "ep"},
    {"folderType": "Sequence", "name": "hitro106_0010", "path": "/episodes/hitro104/hitro106_0010", "id": "seq"},
    {
        "folderType": "Shot",
        "name": "hitro106_0010_0010",
        "path": "/episodes/hitro104/hitro106_0010/hitro106_0010_0010",
        "id": "shot",
    },
]


def test_folder_index_maps_sg_type_and_name_to_path() -> None:
    from gishant_scripts.sandbox.cleanup import _SG_TYPE_MAP

    index = _folder_index(_FOLDERS, _SG_TYPE_MAP)
    # Episode folderType maps to the ShotGrid "Scene" entity type.
    assert index[("Scene", "hitro104")]["path"] == "/episodes/hitro104"
    assert index[("Shot", "hitro106_0010_0010")]["path"].endswith("hitro106_0010_0010")


def test_entity_source_matched_vs_descendant() -> None:
    matched_ids = {"seq"}
    seq = _FOLDERS[1]
    shot = _FOLDERS[2]
    assert _entity_source(seq, matched_ids) == "matched"
    assert _entity_source(shot, matched_ids) == "descendant"
    assert _entity_source(None, matched_ids) == "descendant"


# --------------------------------------------------------------------------
# ShotGrid planning fetches provenance fields
# --------------------------------------------------------------------------


class _FakeSg:
    """Records the field lists requested in each find() call."""

    def __init__(self) -> None:
        self.requested: dict[str, list[str]] = {}

    def find_one(self, entity_type: str, _filters: list) -> dict:
        assert entity_type == "Project"
        return {"type": "Project", "id": 1, "name": "DEMO_SG"}

    def find(self, entity_type: str, _filters: list, fields: list[str]) -> list[dict]:
        self.requested[entity_type] = fields
        if entity_type == "Shot":
            return [
                {
                    "type": "Shot",
                    "id": 11,
                    "code": "hitro106_0010_0010",
                    "created_at": datetime(2024, 11, 21, tzinfo=UTC),
                    "created_by": {"name": "Alice"},
                }
            ]
        return []


class _FakeShotgridBackend:
    project_name = "DEMO_SG"

    def __init__(self, sg: _FakeSg) -> None:
        self._sg = sg

    def connect(self) -> _FakeSg:
        return self._sg


def test_plan_shotgrid_fetches_created_fields() -> None:
    fake = _FakeSg()
    cleaner = FolderCleanup("DEMO", "/episodes/hitro104/hitro106_0010", Console())
    cleaner._shotgrid = _FakeShotgridBackend(fake)  # type: ignore[assignment]
    result = FolderDeletionPlan(
        ayon_folders=[
            {
                "folderType": "Shot",
                "name": "hitro106_0010_0010",
                "path": "/episodes/hitro104/hitro106_0010/hitro106_0010_0010",
                "id": "shot",
            }
        ]
    )
    cleaner._plan_shotgrid(result)

    for entity_type in ("Shot", "Task", "Version"):
        assert "created_at" in fake.requested[entity_type]
        assert "created_by" in fake.requested[entity_type]
    assert result.shotgrid_entities[0]["created_by"]["name"] == "Alice"


# --------------------------------------------------------------------------
# display_plan integration: banners + path/provenance rendering
# --------------------------------------------------------------------------


def _render(plan: FolderDeletionPlan, path: str = "/episodes/hitro104/hitro106_0010") -> str:
    console = Console(file=StringIO(), width=200, force_terminal=False)
    FolderCleanup("HITRO", path, console).display_plan(plan)
    return console.file.getvalue()  # type: ignore[union-attr]


def test_display_plan_flags_aged_target_with_paths() -> None:
    plan = FolderDeletionPlan(
        ayon_folders=_FOLDERS[1:],
        ayon_matched_ids={"seq"},
        shotgrid_entities=[
            {
                "type": "Sequence",
                "code": "hitro106_0010",
                "id": 100,
                "created_at": datetime(2024, 11, 21, tzinfo=UTC),
                "created_by": {"name": "Alice"},
            },
        ],
        shotgrid_versions=[
            {
                "code": "v001",
                "id": 200,
                "entity": {"type": "Shot", "name": "hitro106_0010_0010"},
                "created_at": datetime(2025, 1, 1, tzinfo=UTC),
                "created_by": {"name": "Bob"},
            },
        ],
    )
    out = _render(plan)
    # Risk banner
    assert "DELETE RISK" in out
    assert "predate today" in out
    assert "2024-11-21" in out
    assert "Alice" in out
    # Target banner + provenance
    assert "Cleanup target" in out
    assert "matched" in out
    assert "descendant" in out
    assert "attached" in out


def test_display_plan_marks_fresh_target_safe() -> None:
    now = datetime.now(UTC)
    plan = FolderDeletionPlan(
        ayon_folders=[_FOLDERS[1]],
        ayon_matched_ids={"seq"},
        shotgrid_entities=[
            {
                "type": "Sequence",
                "code": "hitro106_0010",
                "id": 100,
                "created_at": now,
                "created_by": {"name": "sandbox-service"},
            },
        ],
    )
    out = _render(plan)
    assert "DELETE RISK" not in out
    assert "sandbox-fresh" in out
