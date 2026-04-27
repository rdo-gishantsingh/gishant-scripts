"""Tests for granular testdata cleanup planning."""

from __future__ import annotations

from rich.console import Console

from gishant_scripts.testdata.cleanup import DeletionPlan, EpisodeCleanup
from gishant_scripts.testdata.selection import SelectionScope


def _cleaner(*, scope: SelectionScope | None = None) -> EpisodeCleanup:
    return EpisodeCleanup(
        project_name="SGAYONTEST",
        episode_name="ep_test",
        console=Console(),
        selection_scope=scope,
    )


def test_apply_scope_keeps_selected_sequence_children_only() -> None:
    plan = DeletionPlan(
        kitsu_episodes=[{"id": "ep", "name": "ep_test"}],
        kitsu_sequences=[
            {"id": "seq-10", "name": "ep_test_sq010"},
            {"id": "seq-20", "name": "ep_test_sq020"},
        ],
        kitsu_shots=[
            {"id": "shot-10", "name": "ep_test_sq010_sh0010"},
            {"id": "shot-20", "name": "ep_test_sq020_sh0010"},
        ],
    )

    _cleaner(scope=SelectionScope(sequence_patterns=("*sq020",)))._apply_scope(plan)

    assert plan.kitsu_episodes == []
    assert [seq["name"] for seq in plan.kitsu_sequences] == ["ep_test_sq020"]
    assert [shot["name"] for shot in plan.kitsu_shots] == ["ep_test_sq020_sh0010"]


def test_apply_scope_keeps_selected_shot_dependencies_only() -> None:
    selected_shot = {"id": 20, "code": "ep_test_sq020_sh0020"}
    plan = DeletionPlan(
        shotgrid_scenes=[{"id": 1, "code": "ep_test"}],
        shotgrid_sequences=[{"id": 10, "code": "ep_test_sq020"}],
        shotgrid_shots=[
            {"id": 11, "code": "ep_test_sq020_sh0010"},
            selected_shot,
        ],
        shotgrid_versions=[
            {"id": 30, "code": "v001", "entity": selected_shot},
            {"id": 31, "code": "v002", "entity": {"id": 11, "type": "Shot"}},
        ],
        shotgrid_tasks=[
            {"id": 40, "content": "comp", "entity": selected_shot},
            {"id": 41, "content": "anim", "entity": {"id": 11, "type": "Shot"}},
        ],
    )

    _cleaner(scope=SelectionScope(shot_patterns=("*_sh0020",)))._apply_scope(plan)

    assert plan.shotgrid_scenes == []
    assert plan.shotgrid_sequences == []
    assert [shot["code"] for shot in plan.shotgrid_shots] == ["ep_test_sq020_sh0020"]
    assert [version["id"] for version in plan.shotgrid_versions] == [30]
    assert [task["id"] for task in plan.shotgrid_tasks] == [40]


def test_plan_storage_selects_sequence_directories(tmp_path, monkeypatch) -> None:
    episode_path = tmp_path / "SGAYONTEST" / "episodes" / "ep_test"
    selected = episode_path / "ep_test_sq020"
    skipped = episode_path / "ep_test_sq010"
    (selected / "ep_test_sq020_sh0010").mkdir(parents=True)
    skipped.mkdir()

    cleaner = _cleaner(scope=SelectionScope(sequence_patterns=("*sq020",)))
    monkeypatch.setattr(cleaner, "_get_storage_root", lambda: tmp_path)
    plan = DeletionPlan()

    cleaner._plan_storage(plan, "ep_test")

    assert plan.storage_paths == [selected]


def test_plan_storage_selects_shot_directories(tmp_path, monkeypatch) -> None:
    episode_path = tmp_path / "SGAYONTEST" / "episodes" / "ep_test"
    selected = episode_path / "ep_test_sq010" / "ep_test_sq010_sh0020"
    skipped = episode_path / "ep_test_sq010" / "ep_test_sq010_sh0010"
    selected.mkdir(parents=True)
    skipped.mkdir()

    cleaner = _cleaner(scope=SelectionScope(shot_patterns=("*_sh0020",)))
    monkeypatch.setattr(cleaner, "_get_storage_root", lambda: tmp_path)
    plan = DeletionPlan()

    cleaner._plan_storage(plan, "ep_test")

    assert plan.storage_paths == [selected]
    assert plan.storage_total_bytes == 0

def test_filter_shotgrid_uses_sg_sequence_relationship() -> None:
    """Shot with non-standard code is included when sg_sequence.name matches the scope."""
    weird_shot = {"id": 99, "code": "weird_shot_name", "sg_sequence": {"id": 10, "name": "ep_test_sq020"}}
    plan = DeletionPlan(
        shotgrid_shots=[weird_shot],
    )

    _cleaner(scope=SelectionScope(sequence_patterns=("*sq020",)))._apply_scope(plan)

    assert [shot["code"] for shot in plan.shotgrid_shots] == ["weird_shot_name"]
