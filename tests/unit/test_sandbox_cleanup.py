"""Tests for sandbox path-cleanup planning (fake AYON, no live calls)."""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from gishant_scripts.sandbox.cleanup import (
    DateWindow,
    FolderCleanup,
    FolderDeletionPlan,
    _assess_risk,
    _coerce_created_at,
    _entity_episode,
    _entity_source,
    _folder_index,
    _parse_date_bound,
    _resolve_root_tokens,
    _risk_banner_text,
    _sg_entity_fields,
    _target_episodes,
    _version_publish_dir,
    parse_date_window,
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

    def get_folder_by_path(self, _project: str, path: str, fields=None) -> dict | None:  # noqa: ARG002
        return self._by_path.get(path)

    def get_folders(self, _project: str, parent_ids=None, fields=None):  # noqa: ARG002
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


# --------------------------------------------------------------------------
# Date-window parsing
# --------------------------------------------------------------------------


def test_parse_date_bound_bare_date_is_start_of_day_utc() -> None:
    assert _parse_date_bound("2026-07-09", end_of_day=False) == datetime(2026, 7, 9, 0, 0, tzinfo=UTC)


def test_parse_date_bound_bare_date_end_of_day() -> None:
    assert _parse_date_bound("2026-07-09", end_of_day=True) == datetime(2026, 7, 9, 23, 59, 59, 999999, tzinfo=UTC)


def test_parse_date_bound_full_iso_datetime() -> None:
    # A full datetime is used verbatim (end_of_day only pads bare dates).
    assert _parse_date_bound("2026-07-09T08:30:00+00:00", end_of_day=True) == datetime(2026, 7, 9, 8, 30, tzinfo=UTC)


def test_parse_date_bound_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="invalid date"):
        _parse_date_bound("not-a-date", end_of_day=False)


def test_parse_date_window_builds_inclusive_bounds() -> None:
    window = parse_date_window("2026-07-01", "2026-07-09")
    assert window.after == datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
    assert window.before == datetime(2026, 7, 9, 23, 59, 59, 999999, tzinfo=UTC)
    assert window.active


def test_empty_window_is_inactive() -> None:
    assert not parse_date_window(None, None).active


def test_window_status_classifies_in_out_nodate() -> None:
    window = DateWindow(after=datetime(2026, 7, 9, tzinfo=UTC))
    assert window.status(datetime(2026, 7, 9, 8, 0, tzinfo=UTC)) == "in"
    assert window.status(datetime(2024, 11, 21, tzinfo=UTC)) == "out"
    assert window.status(None) == "nodate"


# --------------------------------------------------------------------------
# AYON deletable-subtree logic (folder-cascade-only safety)
# --------------------------------------------------------------------------


def _cleaner(window: DateWindow) -> FolderCleanup:
    return FolderCleanup("HITRO", "/episodes/hitro104/hitro106_0010", Console(), date_window=window)


def test_ayon_deletable_ids_whole_subtree_in_window() -> None:
    window = DateWindow(after=datetime(2026, 7, 1, tzinfo=UTC))
    folders = [
        {"id": "p", "parentId": None, "createdAt": "2026-07-05T00:00:00+00:00"},
        {"id": "c", "parentId": "p", "createdAt": "2026-07-06T00:00:00+00:00"},
    ]
    assert _cleaner(window)._ayon_deletable_ids(folders) == {"p", "c"}


def test_ayon_deletable_ids_out_of_window_descendant_blocks_parent() -> None:
    window = DateWindow(after=datetime(2026, 7, 1, tzinfo=UTC))
    folders = [
        {"id": "p", "parentId": None, "createdAt": "2026-07-05T00:00:00+00:00"},
        {"id": "c", "parentId": "p", "createdAt": "2024-01-01T00:00:00+00:00"},  # old descendant
    ]
    # Parent's cascade would take the old child, so neither is deletable.
    assert _cleaner(window)._ayon_deletable_ids(folders) == set()


def test_ayon_deletable_ids_fresh_subtree_under_old_parent() -> None:
    window = DateWindow(after=datetime(2026, 7, 1, tzinfo=UTC))
    folders = [
        {"id": "p", "parentId": None, "createdAt": "2024-01-01T00:00:00+00:00"},  # old parent -> preserved
        {"id": "c", "parentId": "p", "createdAt": "2026-07-06T00:00:00+00:00"},  # fresh, fully in-window
    ]
    # The fresh child is independently deletable; the old parent is preserved.
    assert _cleaner(window)._ayon_deletable_ids(folders) == {"c"}


# --------------------------------------------------------------------------
# CRITICAL SAFETY INVARIANT (this morning's near-miss)
# --------------------------------------------------------------------------


def test_created_after_prunes_to_only_the_fresh_version() -> None:
    """--created-after 2026-07-09 must keep ONLY the fresh version, preserve all
    folders and every 2024->2026-06 entity, and exclude undateable entities.
    """
    fresh = {
        "type": "Version",
        "id": 2489715,
        "code": "hitro106_0010_0050_v001",
        "entity": {"type": "Shot", "name": "hitro106_0010_0050"},
        "created_at": datetime(2026, 7, 9, 8, 15, tzinfo=UTC),
        "created_by": {"name": "sandbox-service"},
    }
    old_version = {
        "type": "Version",
        "id": 1000,
        "code": "hitro106_0010_0050_comp_v007",
        "entity": {"type": "Shot", "name": "hitro106_0010_0050"},
        "created_at": datetime(2025, 6, 1, tzinfo=UTC),
        "created_by": {"name": "Mei L."},
    }
    undateable = {
        "type": "Version",
        "id": 1001,
        "code": "hitro106_0010_0050_v_nodate",
        "entity": {"type": "Shot", "name": "hitro106_0010_0050"},
        "created_at": None,
        "created_by": {"name": "Unknown"},
    }
    plan = FolderDeletionPlan(
        ayon_folders=[
            {
                "id": "seq",
                "parentId": None,
                "name": "hitro106_0010",
                "folderType": "Sequence",
                "path": "/episodes/hitro104/hitro106_0010",
                "createdAt": "2024-11-21T00:00:00+00:00",
            },
            {
                "id": "shot",
                "parentId": "seq",
                "name": "hitro106_0010_0050",
                "folderType": "Shot",
                "path": "/episodes/hitro104/hitro106_0010/hitro106_0010_0050",
                "createdAt": "2024-12-01T00:00:00+00:00",
            },
        ],
        ayon_matched_ids={"seq"},
        shotgrid_entities=[
            {
                "type": "Sequence",
                "id": 10,
                "code": "hitro106_0010",
                "created_at": datetime(2024, 11, 21, tzinfo=UTC),
                "created_by": {"name": "Priya R."},
            },
            {
                "type": "Shot",
                "id": 11,
                "code": "hitro106_0010_0050",
                "created_at": datetime(2024, 12, 1, tzinfo=UTC),
                "created_by": {"name": "Sam T."},
            },
        ],
        shotgrid_versions=[fresh, old_version, undateable],
        shotgrid_tasks=[
            {
                "content": "comp",
                "id": 300,
                "entity": {"type": "Shot", "name": "hitro106_0010_0050"},
                "created_at": datetime(2025, 2, 2, tzinfo=UTC),
                "created_by": {"name": "Jonas K."},
            },
        ],
        kitsu_shots=[{"id": "k1", "name": "hitro106_0010_0050", "created_at": "2024-12-01T00:00:00"}],
    )

    _cleaner(parse_date_window("2026-07-09", None))._apply_date_filter(plan)

    # Only the fresh version survives on ShotGrid.
    assert [v["id"] for v in plan.shotgrid_versions] == [2489715]
    assert plan.shotgrid_entities == []
    assert plan.shotgrid_tasks == []
    assert plan.kitsu_shots == []
    # NO AYON folder is deletable -> the Sequence/Shot folders are preserved.
    assert plan.ayon_deletable_ids == set()
    assert len(plan.ayon_folders) == 2
    # Undateable version is excluded (never delete what we cannot date).
    excluded_names = {name: reason for (_b, _k, name, _c, reason) in plan.date_excluded}
    assert excluded_names["hitro106_0010_0050_v_nodate"] == "no date"
    assert excluded_names["hitro106_0010_0050_comp_v007"] == "out of window"
    assert plan.date_kept == 1


# --------------------------------------------------------------------------
# #5 — NAS pruning keyed to in-window versions' representation paths
# --------------------------------------------------------------------------


def test_resolve_root_tokens_substitutes_anatomy_roots() -> None:
    roots = {"work": "/projects", "renders": "/mnt/renders"}
    assert _resolve_root_tokens("{root[work]}/SGAYONTEST/x.mp4", roots) == "/projects/SGAYONTEST/x.mp4"
    # An unknown token is left intact rather than guessed.
    assert _resolve_root_tokens("{root[unknown]}/x", roots) == "{root[unknown]}/x"


def test_version_publish_dir_from_attrib_path() -> None:
    reps = [{"attrib": {"path": "/projects/P/episodes/ep/sq/sh/publish/render/comp/v003/sh_comp_v003.exr"}}]
    assert _version_publish_dir(reps, {}) == Path("/projects/P/episodes/ep/sq/sh/publish/render/comp/v003")


def test_version_publish_dir_resolves_template_files() -> None:
    reps = [{"files": [{"path": "{root[work]}/P/episodes/ep/publish/model/main/v001/x.abc"}]}]
    assert _version_publish_dir(reps, {"work": "/projects"}) == Path("/projects/P/episodes/ep/publish/model/main/v001")


def test_version_publish_dir_unmappable_returns_none() -> None:
    assert _version_publish_dir([], {}) is None  # no representations
    assert _version_publish_dir([{"attrib": {"path": "/projects/P/no/version/segment.exr"}}], {}) is None


class _FakeAyonApi:
    """Stand-in for the ayon_api module for version-based NAS planning."""

    def __init__(self, roots: dict, products: list[dict], versions: list[dict], reps: list[dict]) -> None:
        self._roots = roots
        self._products = products
        self._versions = versions
        self._reps = reps

    def get(self, _endpoint: str) -> object:
        return type("Resp", (), {"data": {"roots": [{"name": k, "linux": v} for k, v in self._roots.items()]}})()

    def get_products(self, _project: str, folder_ids=None):  # noqa: ARG002
        return list(self._products)

    def get_versions(self, _project: str, product_ids=None, fields=None):  # noqa: ARG002
        return list(self._versions)

    def get_representations(self, _project: str, version_ids=None):
        wanted = set(version_ids or [])
        return [r for r in self._reps if r.get("versionId") in wanted]


class _FakeAyonBackend:
    project_name = "P"

    def __init__(self, api: _FakeAyonApi) -> None:
        self._api = api

    def connect(self) -> _FakeAyonApi:
        return self._api


def _nas_version_plan(tmp_path: Path, window: DateWindow) -> FolderDeletionPlan:
    """Build a plan on a real on-disk publish tree and run version-based NAS planning."""
    base = tmp_path / "P" / "episodes" / "ep01" / "sq010" / "sh0010" / "publish" / "render" / "comp"
    in_dir = base / "v002"
    out_dir = base / "v001"
    for d in (in_dir, out_dir):
        d.mkdir(parents=True)
        (d / "frame.exr").write_bytes(b"x" * 10)
    api = _FakeAyonApi(
        roots={"work": str(tmp_path)},
        products=[{"id": "prod1"}],
        versions=[
            {"id": "vA", "version": 2, "createdAt": "2026-07-09T08:00:00+00:00"},  # in-window
            {"id": "vB", "version": 1, "createdAt": "2024-11-21T00:00:00+00:00"},  # out-of-window
        ],
        reps=[
            {"versionId": "vA", "attrib": {"path": str(in_dir / "sh0010_comp_v002.exr")}},
            {"versionId": "vB", "attrib": {"path": str(out_dir / "sh0010_comp_v001.exr")}},
        ],
    )
    cleaner = FolderCleanup("HITRO", "/episodes/ep01/sq010/sh0010", Console(), date_window=window)
    cleaner._ayon = _FakeAyonBackend(api)  # type: ignore[assignment]
    result = FolderDeletionPlan(
        ayon_folders=[{"id": "sh", "path": "/episodes/ep01/sq010/sh0010", "folderType": "Shot", "name": "sh0010"}]
    )
    cleaner._plan_storage(result)
    return result


def test_nas_prune_targets_only_in_window_version_dir(tmp_path: Path) -> None:
    window = parse_date_window("2026-07-09", None)
    plan = _nas_version_plan(tmp_path, window)

    targeted = [p.name for p in plan.storage_version_dirs]
    assert targeted == ["v002"]  # only the in-window version dir
    assert plan.storage_versions_preserved == 1  # the out-of-window v001 is preserved
    assert plan.storage_versions_skipped == []
    assert plan.storage_paths == []  # never the whole folder under a filter
    # out-of-window media is untouched on disk
    assert (tmp_path / "P/episodes/ep01/sq010/sh0010/publish/render/comp/v001/frame.exr").exists()


def test_nas_prune_no_filter_deletes_whole_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cleaner = FolderCleanup("HITRO", "/episodes/ep01", Console())  # no date window
    # NAS path is <root>/<storage project name>/<ayon rel>; project name is "HITRO".
    nas = tmp_path / cleaner._storage.project_name / "episodes" / "ep01"
    (nas / "sq010").mkdir(parents=True)
    (nas / "sq010" / "f.exr").write_bytes(b"y" * 5)
    monkeypatch.setattr(cleaner._storage, "resolve_root", lambda _p: tmp_path)
    result = FolderDeletionPlan(
        ayon_folders=[{"id": "ep", "parentId": None, "path": "/episodes/ep01", "folderType": "Episode", "name": "ep01"}]
    )
    cleaner._plan_storage(result)

    assert result.storage_paths == [nas]  # whole folder targeted
    assert result.storage_version_dirs == []


def test_nas_prune_skips_and_reports_unmappable_version(tmp_path: Path) -> None:
    api = _FakeAyonApi(
        roots={"work": str(tmp_path)},
        products=[{"id": "prod1"}],
        versions=[{"id": "vA", "version": 5, "createdAt": "2026-07-09T08:00:00+00:00"}],
        reps=[{"versionId": "vA", "attrib": {}, "files": []}],  # no path -> unmappable
    )
    cleaner = FolderCleanup(
        "HITRO", "/episodes/ep01/sq010/sh0010", Console(), date_window=parse_date_window("2026-07-09", None)
    )
    cleaner._ayon = _FakeAyonBackend(api)  # type: ignore[assignment]
    result = FolderDeletionPlan(
        ayon_folders=[{"id": "sh", "path": "/episodes/ep01/sq010/sh0010", "folderType": "Shot", "name": "sh0010"}]
    )
    cleaner._plan_storage(result)

    assert result.storage_version_dirs == []
    assert len(result.storage_versions_skipped) == 1
    assert result.storage_versions_skipped[0][0] == "version 5"


# --------------------------------------------------------------------------
# display_plan with a date filter active
# --------------------------------------------------------------------------


def test_display_plan_shows_date_filter_and_folder_only_note() -> None:
    plan = FolderDeletionPlan(
        ayon_folders=[
            {
                "id": "seq",
                "parentId": None,
                "name": "hitro106_0010",
                "folderType": "Sequence",
                "path": "/episodes/hitro104/hitro106_0010",
                "createdAt": "2024-11-21T00:00:00+00:00",
            },
        ],
        ayon_matched_ids={"seq"},
        shotgrid_versions=[
            {
                "type": "Version",
                "id": 2489715,
                "code": "hitro106_0010_0050_v001",
                "entity": {"type": "Shot", "name": "hitro106_0010"},
                "created_at": datetime(2026, 7, 9, 8, 0, tzinfo=UTC),
                "created_by": {"name": "sandbox-service"},
            },
        ],
        shotgrid_entities=[
            {
                "type": "Sequence",
                "id": 10,
                "code": "hitro106_0010",
                "created_at": datetime(2024, 11, 21, tzinfo=UTC),
                "created_by": {"name": "Priya R."},
            },
        ],
    )
    cleaner = _cleaner(parse_date_window("2026-07-09", None))
    cleaner._apply_date_filter(plan)
    console = Console(file=StringIO(), width=200, force_terminal=False)
    cleaner._console = console
    cleaner.display_plan(plan)
    out = console.file.getvalue()  # type: ignore[union-attr]

    assert "Date filter:" in out
    assert "2026-07-09" in out  # window shown in target banner
    assert "preserve" in out  # AYON folder marked preserved
    assert "Preserved by date filter" in out  # excluded panel
    assert "folder-cascade-only" in out  # AYON constraint surfaced
    assert "1 entity(ies) kept, 1 excluded" in out


# --------------------------------------------------------------------------
# #4 — path-anchored ShotGrid matching (episode verification)
# --------------------------------------------------------------------------


def test_sg_entity_fields_include_episode_links() -> None:
    assert "sg_episode" in _sg_entity_fields("Sequence")
    assert "sg_sequence" in _sg_entity_fields("Shot")
    assert "sg_scene" in _sg_entity_fields("Shot")
    assert "sg_episode" not in _sg_entity_fields("Scene")


def test_target_episodes_from_paths() -> None:
    folders = [
        {"path": "/episodes/hitro104/hitro106_0010"},
        {"path": "/episodes/hitro104/hitro106_0010/sh010"},
        {"path": "/assets/vehicles/car"},  # non-episode, ignored
    ]
    assert _target_episodes(folders) == {"hitro104"}


def test_entity_episode_resolution() -> None:
    assert _entity_episode({"type": "Scene", "code": "hitro104"}, {}) == "hitro104"
    assert _entity_episode({"type": "Sequence", "sg_episode": {"name": "hitro104"}}, {}) == "hitro104"
    assert _entity_episode({"type": "Sequence", "sg_episode": None}, {}) is None
    # Shot with a direct Scene (episode) link
    assert _entity_episode({"type": "Shot", "sg_scene": {"name": "hitro104"}}, {}) == "hitro104"
    # Shot resolved via its sequence -> that sequence's episode
    assert _entity_episode({"type": "Shot", "sg_sequence": {"id": 99}}, {99: "hitro104"}) == "hitro104"
    # Shot with no usable link -> unknown
    assert _entity_episode({"type": "Shot", "sg_sequence": None, "sg_scene": None}, {}) is None


class _EpisodeFakeSg:
    """Configurable ShotGrid stand-in for episode-anchoring tests."""

    def __init__(self, entities_by_type: dict[str, list[dict]], sequences_by_id: dict[int, dict] | None = None) -> None:
        self._by_type = entities_by_type
        self._seqs = sequences_by_id or {}
        self.calls: list[tuple[str, list[str]]] = []

    def find_one(self, entity_type: str, _filters: list) -> dict:
        assert entity_type == "Project"
        return {"type": "Project", "id": 1, "name": "DEMO_SG"}

    def find(self, entity_type: str, filters: list, fields: list[str]) -> list[dict]:
        self.calls.append((entity_type, fields))
        # The Shot->episode resolution query filters by ["id", "in", [...]].
        for f in filters:
            if f[0] == "id" and f[1] == "in":
                return [self._seqs[i] for i in f[2] if i in self._seqs]
        return list(self._by_type.get(entity_type, []))


def _anchor_plan(path: str, ayon_folders: list[dict], fake: _EpisodeFakeSg) -> FolderDeletionPlan:
    cleaner = FolderCleanup("HITRO", path, Console())
    cleaner._shotgrid = _FakeShotgridBackend(fake)  # type: ignore[assignment]
    result = FolderDeletionPlan(ayon_folders=ayon_folders)
    cleaner._plan_shotgrid(result)
    return result


def test_sg_matching_drops_entity_in_different_episode() -> None:
    folders = [
        {"folderType": "Sequence", "name": "hitro106_0010", "path": "/episodes/hitro104/hitro106_0010", "id": "seq"}
    ]
    fake = _EpisodeFakeSg(
        {
            "Sequence": [
                {"type": "Sequence", "id": 1, "code": "hitro106_0010", "sg_episode": {"name": "hitro104"}},
                {"type": "Sequence", "id": 2, "code": "hitro106_0010", "sg_episode": {"name": "hitro999"}},  # collision
            ]
        }
    )
    plan = _anchor_plan("/episodes/hitro104/hitro106_0010", folders, fake)

    assert [e["id"] for e in plan.shotgrid_entities] == [1]  # only the hitro104 one kept
    assert len(plan.shotgrid_dropped) == 1
    dtype, dcode, detail = plan.shotgrid_dropped[0]
    assert (dtype, dcode) == ("Sequence", "hitro106_0010")
    assert "hitro999" in detail
    # The episode-anchor field was requested.
    assert any(t == "Sequence" and "sg_episode" in fields for t, fields in fake.calls)


def test_sg_matching_keeps_entity_in_target_episode() -> None:
    folders = [{"folderType": "Shot", "name": "sh010", "path": "/episodes/hitro104/sq01/sh010", "id": "shot"}]
    fake = _EpisodeFakeSg({"Shot": [{"type": "Shot", "id": 5, "code": "sh010", "sg_scene": {"name": "hitro104"}}]})
    plan = _anchor_plan("/episodes/hitro104/sq01/sh010", folders, fake)

    assert [e["id"] for e in plan.shotgrid_entities] == [5]
    assert plan.shotgrid_dropped == []


def test_sg_matching_drops_shot_via_sequence_episode() -> None:
    folders = [{"folderType": "Shot", "name": "sh020", "path": "/episodes/hitro104/sq01/sh020", "id": "shot"}]
    fake = _EpisodeFakeSg(
        {
            "Shot": [
                {"type": "Shot", "id": 6, "code": "sh020", "sg_scene": None, "sg_sequence": {"id": 99, "name": "sq01"}}
            ]
        },
        sequences_by_id={99: {"id": 99, "sg_episode": {"name": "hitro999"}}},  # wrong episode
    )
    plan = _anchor_plan("/episodes/hitro104/sq01/sh020", folders, fake)

    assert plan.shotgrid_entities == []
    assert len(plan.shotgrid_dropped) == 1
    assert "hitro999" in plan.shotgrid_dropped[0][2]


def test_sg_matching_keeps_unverified_when_link_unpopulated() -> None:
    folders = [{"folderType": "Shot", "name": "sh030", "path": "/episodes/hitro104/sq01/sh030", "id": "shot"}]
    fake = _EpisodeFakeSg({"Shot": [{"type": "Shot", "id": 7, "code": "sh030", "sg_scene": None, "sg_sequence": None}]})
    plan = _anchor_plan("/episodes/hitro104/sq01/sh030", folders, fake)

    assert [e["id"] for e in plan.shotgrid_entities] == [7]  # kept
    assert plan.shotgrid_dropped == []
    assert ("Shot", "sh030") in plan.shotgrid_unverified


def test_sg_matching_skips_check_for_non_episode_path() -> None:
    folders = [{"folderType": "Asset", "name": "car", "path": "/assets/vehicles/car", "id": "a"}]
    fake = _EpisodeFakeSg({"Asset": [{"type": "Asset", "id": 8, "code": "car"}]})
    plan = _anchor_plan("/assets/vehicles/car", folders, fake)

    assert [e["id"] for e in plan.shotgrid_entities] == [8]
    assert plan.shotgrid_dropped == []
    assert plan.shotgrid_unverified == []


def test_display_reports_dropped_episode_mismatch() -> None:
    plan = FolderDeletionPlan(
        ayon_folders=[
            {"id": "seq", "folderType": "Sequence", "name": "hitro106_0010", "path": "/episodes/hitro104/hitro106_0010"}
        ],
        ayon_matched_ids={"seq"},
        shotgrid_entities=[{"type": "Sequence", "id": 1, "code": "hitro106_0010"}],
        shotgrid_dropped=[("Sequence", "hitro106_0010", "episode hitro999 not in ['hitro104']")],
    )
    out = _render(plan)
    assert "Dropped 1 ShotGrid entity(ies)" in out
    assert "episode mismatch" in out
    assert "hitro999" in out
