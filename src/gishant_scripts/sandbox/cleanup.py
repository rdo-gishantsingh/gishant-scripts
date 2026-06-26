"""Folder cleanup: delete any AYON path hierarchy from all backends."""

from __future__ import annotations

import fnmatch
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from gishant_scripts.sandbox.backends import (
    AyonBackend,
    BackendUnavailableError,
    Environment,
    KitsuBackend,
    ShotGridBackend,
    StorageBackend,
)

if TYPE_CHECKING:
    from rich.console import Console

    from gishant_scripts.sandbox.config import ProjectConfig

_log = logging.getLogger(__name__)
_DISPLAY_HEAD = 25
_DISPLAY_TAIL = 5
_DISPLAY_THRESHOLD = _DISPLAY_HEAD + _DISPLAY_TAIL

# AYON folderType → ShotGrid entity type
_SG_TYPE_MAP: dict[str, str] = {
    "Episode": "Scene",
    "Sequence": "Sequence",
    "Shot": "Shot",
    "Asset": "Asset",
}


def _is_glob(pattern: str) -> bool:
    """Return True if pattern contains glob metacharacters."""
    return any(c in pattern for c in "*?[")


def _truncate_id(entity_id: str | int, max_len: int = 8) -> str:
    """Truncate a UUID string; integers pass through unchanged."""
    if isinstance(entity_id, int):
        return str(entity_id)
    s = str(entity_id)
    return s[:max_len] + "..." if len(s) > max_len else s


def _human_size(num_bytes: int) -> str:
    """Convert bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0  # type: ignore[assignment]
    return f"{num_bytes:.1f} PB"


def _add_rows_with_truncation(
    table: Table,
    items: list[tuple[str, ...]],
    total_label: str,
) -> None:
    """Add rows to a Rich table, truncating mid-list when there are too many."""
    if len(items) > _DISPLAY_THRESHOLD:
        for row in items[:_DISPLAY_HEAD]:
            table.add_row(*row)
        omitted = len(items) - _DISPLAY_HEAD - _DISPLAY_TAIL
        ncols = len(items[0]) if items else 1
        sep = ("...",) + (f"... and {omitted} more ...",) + ("",) * (ncols - 2)
        table.add_row(*sep, style="dim")
        for row in items[-_DISPLAY_TAIL:]:
            table.add_row(*row)
    else:
        for row in items:
            table.add_row(*row)
    ncols = len(items[0]) if items else 1
    footer = (f"[bold]{total_label}: {len(items)}[/]",) + ("",) * (ncols - 1)
    table.add_row(*footer, end_section=True)


@dataclass
class FolderDeletionPlan:
    """Everything to be deleted, organized by backend.

    AYON is the canonical source.  Kitsu and ShotGrid entries are resolved
    from the AYON folder list via ``kitsuId`` data field and name matching.
    """

    # AYON — matched roots + all descendants (the authoritative list)
    ayon_folders: list[dict] = field(default_factory=list)

    # Kitsu — grouped by entity type for dependency-safe deletion ordering
    kitsu_episodes: list[dict] = field(default_factory=list)
    kitsu_sequences: list[dict] = field(default_factory=list)
    kitsu_shots: list[dict] = field(default_factory=list)
    kitsu_assets: list[dict] = field(default_factory=list)

    # ShotGrid — entities (Scene/Sequence/Shot/Asset) plus their dependants
    shotgrid_entities: list[dict] = field(default_factory=list)
    shotgrid_tasks: list[dict] = field(default_factory=list)
    shotgrid_versions: list[dict] = field(default_factory=list)

    # NAS storage — populated only for plan roots whose AYON path is under /episodes/
    storage_paths: list[Path] = field(default_factory=list)
    storage_total_bytes: int = 0

    errors: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if nothing was found to delete across all backends."""
        return not any(
            (
                self.ayon_folders,
                self.kitsu_episodes,
                self.kitsu_sequences,
                self.kitsu_shots,
                self.kitsu_assets,
                self.shotgrid_entities,
                self.shotgrid_tasks,
                self.shotgrid_versions,
                self.storage_paths,
            )
        )


class FolderCleanup:
    """Delete any AYON folder path (with optional glob segments) from all backends.

    AYON is the canonical source of truth.  Path resolution and hierarchy
    discovery run through AYON.  Kitsu entities are matched via the
    ``kitsuId`` field stored in AYON folder data, with a name-matching
    fallback for episodes and assets.  ShotGrid entities are matched by
    ``(folderType → entity type, name)`` lookup.  NAS storage is cleaned
    for plan roots whose AYON path starts with ``/episodes/``.

    Examples::

        FolderCleanup(project, "/assets/vehicles/carsuv", ...)   # one asset
        FolderCleanup(project, "/assets/vehicles", ...)           # whole type folder
        FolderCleanup(project, "/assets/*/car*", ...)             # glob across types
        FolderCleanup(project, "/episodes/ep01", ...)             # full episode
        FolderCleanup(project, "/episodes/ep01/sq010", ...)       # one sequence
    """

    def __init__(
        self,
        project_name: str,
        path: str,
        console: Console,
        *,
        skip_kitsu: bool = False,
        skip_shotgrid: bool = False,
        skip_ayon: bool = False,
        skip_storage: bool = False,
        environment: Environment = Environment.TEST,
        project_config: ProjectConfig | None = None,
    ) -> None:
        normalized = path.strip("/")
        if not normalized:
            msg = "path must not be empty or '/'"
            raise ValueError(msg)
        self._path = "/" + normalized
        self._console = console
        self._skip_kitsu = skip_kitsu
        self._skip_shotgrid = skip_shotgrid
        self._skip_ayon = skip_ayon
        self._skip_storage = skip_storage
        self._environment = environment
        self._kitsu = KitsuBackend(project_name, environment, project_config)
        self._shotgrid = ShotGridBackend(project_name, environment, project_config)
        self._ayon = AyonBackend(project_name, environment, project_config)
        self._storage = StorageBackend(project_name, environment, project_config)

    # ------------------------------------------------------------------
    # AYON path resolution
    # ------------------------------------------------------------------

    def _walk_ayon_path(self, ayon_api_mod: object) -> list[dict]:
        """Resolve self._path against the AYON folder hierarchy.

        Glob characters (``*``, ``?``, ``[…]``) may appear in any segment.
        Returns the folders matching the final segment; callers are
        responsible for collecting descendants separately.
        """
        segments = self._path.lstrip("/").split("/")
        first_glob = next((i for i, s in enumerate(segments) if _is_glob(s)), len(segments))

        if first_glob == len(segments):
            # Fully exact path — single server call
            folder = ayon_api_mod.get_folder_by_path(self._ayon.project_name, "/".join(segments))
            return [folder] if folder else []

        if first_glob > 0:
            # Resolve the exact prefix, then fan out at the first glob
            prefix = "/".join(segments[:first_glob])
            anchor = ayon_api_mod.get_folder_by_path(self._ayon.project_name, prefix)
            if not anchor:
                return []
            children = list(ayon_api_mod.get_folders(self._ayon.project_name, parent_ids=[anchor["id"]]))
            candidates = [c for c in children if fnmatch.fnmatch(c.get("name", ""), segments[first_glob])]
            remaining = segments[first_glob + 1 :]
        else:
            # Path starts with a glob — must enumerate all root-level folders
            all_folders = list(ayon_api_mod.get_folders(self._ayon.project_name))
            candidates = [
                f for f in all_folders if f.get("parentId") is None and fnmatch.fnmatch(f.get("name", ""), segments[0])
            ]
            remaining = segments[1:]

        for seg in remaining:
            if not candidates:
                return []
            next_candidates: list[dict] = []
            for parent in candidates:
                children = list(ayon_api_mod.get_folders(self._ayon.project_name, parent_ids=[parent["id"]]))
                if _is_glob(seg):
                    next_candidates.extend(c for c in children if fnmatch.fnmatch(c.get("name", ""), seg))
                else:
                    next_candidates.extend(c for c in children if c.get("name") == seg)
            candidates = next_candidates

        return candidates

    @staticmethod
    def _collect_descendants(
        ayon_api_mod: object,
        project_name: str,
        roots: list[dict],
    ) -> list[dict]:
        """Return roots plus all AYON descendants (BFS, one API call per parent)."""
        result = list(roots)
        seen: set[str] = {f["id"] for f in roots}
        queue = list(roots)
        while queue:
            next_level: list[dict] = []
            for parent in queue:
                for child in ayon_api_mod.get_folders(project_name, parent_ids=[parent["id"]]):
                    if child["id"] not in seen:
                        seen.add(child["id"])
                        result.append(child)
                        next_level.append(child)
            queue = next_level
        return result

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan(self) -> FolderDeletionPlan:
        """Discover all entities to delete across backends (read-only).

        AYON is always resolved first to build the folder list; Kitsu,
        ShotGrid, and storage planning are driven from that list.
        """
        result = FolderDeletionPlan()

        # AYON discovery always runs — even when skip_ayon=True, we need
        # the folder list to drive cross-backend resolution.
        self._plan_ayon(result)

        if not result.ayon_folders:
            return result

        if not self._skip_kitsu:
            self._plan_kitsu(result)
        if not self._skip_shotgrid:
            self._plan_shotgrid(result)
        if not self._skip_storage:
            self._plan_storage(result)

        return result

    # -- AYON -----------------------------------------------------------

    def _plan_ayon(self, result: FolderDeletionPlan) -> None:
        """Resolve the AYON path and collect all descendant folders."""
        try:
            ayon_api = self._ayon.connect()
        except BackendUnavailableError as exc:
            result.errors.append(str(exc))
            return

        try:
            self._console.print(f"[dim]AYON: resolving path {self._path}...[/]")
            matched = self._walk_ayon_path(ayon_api)
            if not matched:
                self._console.print(f"[yellow]AYON: no folders matched {self._path}[/]")
                return
            self._console.print(f"[dim]AYON: {len(matched)} match(es), collecting descendants...[/]")
            all_folders = self._collect_descendants(ayon_api, self._ayon.project_name, matched)
            result.ayon_folders.extend(all_folders)
            _log.info("AYON: %d folder(s) total (matched + descendants)", len(all_folders))
        except Exception as exc:  # ayon_api raises varied types
            msg = f"AYON: discovery failed -- {exc}"
            result.errors.append(msg)
            _log.warning(msg)

    # -- Kitsu ----------------------------------------------------------

    def _plan_kitsu(self, result: FolderDeletionPlan) -> None:
        """Resolve Kitsu entities for each AYON folder via kitsuId or name fallback."""
        try:
            gazu = self._kitsu.connect()
        except BackendUnavailableError as exc:
            result.errors.append(str(exc))
            return

        try:
            project = gazu.project.get_project_by_name(self._kitsu.project_name)
            if not project:
                _log.info("Kitsu: project %s not found", self._kitsu.project_name)
                return

            self._console.print("[dim]Kitsu: resolving entities from AYON folder data...[/]")

            unresolved_episodes: list[str] = []
            unresolved_assets: list[str] = []
            seen_kitsu_ids: set[str] = set()

            for folder in result.ayon_folders:
                folder_type = folder.get("folderType")
                if folder_type not in ("Episode", "Sequence", "Shot", "Asset"):
                    continue

                kitsu_id = (folder.get("data") or {}).get("kitsuId")
                entity: dict | None = None

                if kitsu_id and kitsu_id not in seen_kitsu_ids:
                    try:
                        if folder_type == "Episode":
                            entity = gazu.shot.get_episode(kitsu_id)
                        elif folder_type == "Sequence":
                            entity = gazu.shot.get_sequence(kitsu_id)
                        elif folder_type == "Shot":
                            entity = gazu.shot.get_shot(kitsu_id)
                        elif folder_type == "Asset":
                            entity = gazu.asset.get_asset(kitsu_id)
                    except Exception:  # gazu raises varied types on not-found; entity stays None
                        _log.debug("Kitsu: kitsuId %s lookup failed for %s", kitsu_id, folder_type)

                if entity:
                    seen_kitsu_ids.add(kitsu_id)  # type: ignore[arg-type]
                    self._add_kitsu_entity(result, folder_type, entity)
                elif not kitsu_id:
                    if folder_type == "Episode":
                        unresolved_episodes.append(folder.get("name", ""))
                    elif folder_type == "Asset":
                        unresolved_assets.append(folder.get("name", ""))
                    # Sequences/shots without kitsuId: name alone is ambiguous across
                    # episodes/sequences, so we skip rather than risk incorrect matches.

            # Fallback: episodes by name (unambiguous within a project)
            for name in unresolved_episodes:
                ep = gazu.shot.get_episode_by_name(project, name)
                if ep:
                    self._add_kitsu_entity(result, "Episode", ep)

            # Fallback: assets — one bulk fetch then filter by name set
            if unresolved_assets:
                asset_names = set(unresolved_assets)
                for asset in gazu.asset.all_assets_for_project(project):
                    if asset.get("name") in asset_names:
                        self._add_kitsu_entity(result, "Asset", asset)

            _log.info(
                "Kitsu: %d episodes, %d sequences, %d shots, %d assets",
                len(result.kitsu_episodes),
                len(result.kitsu_sequences),
                len(result.kitsu_shots),
                len(result.kitsu_assets),
            )

        except Exception as exc:  # gazu raises varied exception types
            msg = f"Kitsu: discovery failed -- {exc}"
            result.errors.append(msg)
            _log.warning(msg)

    def _add_kitsu_entity(
        self,
        plan: FolderDeletionPlan,
        folder_type: str,
        entity: dict,
    ) -> None:
        """Append a Kitsu entity to the correct plan list, guarding duplicates."""
        eid = entity.get("id")
        if folder_type == "Episode":
            if not any(e.get("id") == eid for e in plan.kitsu_episodes):
                plan.kitsu_episodes.append(entity)
        elif folder_type == "Sequence":
            if not any(e.get("id") == eid for e in plan.kitsu_sequences):
                plan.kitsu_sequences.append(entity)
        elif folder_type == "Shot":
            if not any(e.get("id") == eid for e in plan.kitsu_shots):
                plan.kitsu_shots.append(entity)
        elif folder_type == "Asset" and not any(e.get("id") == eid for e in plan.kitsu_assets):
            plan.kitsu_assets.append(entity)

    # -- ShotGrid -------------------------------------------------------

    def _plan_shotgrid(self, result: FolderDeletionPlan) -> None:
        """Discover ShotGrid entities by (entity_type, name) — one call per type."""
        try:
            sg = self._shotgrid.connect()
        except BackendUnavailableError as exc:
            result.errors.append(str(exc))
            return

        try:
            project = sg.find_one("Project", [["name", "is", self._shotgrid.project_name]])
            if not project:
                _log.info("ShotGrid: project %s not found", self._shotgrid.project_name)
                return

            self._console.print("[dim]ShotGrid: discovering entities...[/]")

            # Group folder names by SG type — one API call per entity type
            by_sg_type: dict[str, list[str]] = {}
            for folder in result.ayon_folders:
                sg_type = _SG_TYPE_MAP.get(folder.get("folderType", ""))
                if sg_type:
                    by_sg_type.setdefault(sg_type, []).append(folder.get("name", ""))

            all_entities: list[dict] = []
            for sg_type, names in by_sg_type.items():
                entities = sg.find(
                    sg_type,
                    [["project", "is", project], ["code", "in", names]],
                    ["id", "code"],
                )
                all_entities.extend(entities)
                result.shotgrid_entities.extend(entities)

            if all_entities:
                result.shotgrid_tasks.extend(
                    sg.find(
                        "Task",
                        [["project", "is", project], ["entity", "in", all_entities]],
                        ["id", "content", "entity"],
                    )
                )
                result.shotgrid_versions.extend(
                    sg.find(
                        "Version",
                        [["project", "is", project], ["entity", "in", all_entities]],
                        ["id", "code", "entity"],
                    )
                )

            _log.info(
                "ShotGrid: %d entities, %d tasks, %d versions",
                len(result.shotgrid_entities),
                len(result.shotgrid_tasks),
                len(result.shotgrid_versions),
            )

        except Exception as exc:  # shotgun_api3 raises varied exception types
            msg = f"ShotGrid: discovery failed -- {exc}"
            result.errors.append(msg)
            _log.warning(msg)

    # -- NAS storage ----------------------------------------------------

    def _plan_storage(self, result: FolderDeletionPlan) -> None:
        """Discover NAS paths for plan roots whose AYON path is under /episodes/."""
        folder_ids = {f["id"] for f in result.ayon_folders}
        roots = [f for f in result.ayon_folders if f.get("parentId") not in folder_ids]
        episode_roots = [f for f in roots if f.get("path", "").startswith("/episodes/")]
        if not episode_roots:
            return

        storage_root = self._storage.resolve_root(self._ayon.project_name)

        for folder in episode_roots:
            ayon_rel = folder["path"].lstrip("/")
            nas_path = storage_root / self._storage.project_name / ayon_rel
            if not nas_path.exists():
                _log.info("Storage: path not found -- %s", nas_path)
                continue
            result.storage_paths.append(nas_path)
            total = sum(f.stat().st_size for f in nas_path.rglob("*") if f.is_file())
            result.storage_total_bytes += total
            _log.info("Storage: found %s (%s)", nas_path, _human_size(total))

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def display_plan(self, plan: FolderDeletionPlan) -> None:
        """Print a Rich summary of the deletion plan with per-item detail."""
        if plan.errors:
            for err in plan.errors:
                self._console.print(f"[yellow]WARNING: {err}[/]")
            self._console.print()

        if plan.is_empty:
            self._console.print("[dim]Nothing found to delete.[/]")
            return

        # AYON — source of truth shown first
        if plan.ayon_folders:
            table = Table(title="AYON Folders", show_header=True, header_style="bold green")
            table.add_column("Type", style="green")
            table.add_column("Path")
            table.add_column("ID", style="dim")
            rows: list[tuple[str, str, str]] = [
                (
                    f.get("folderType") or "Folder",
                    f.get("path", f.get("name", "")),
                    _truncate_id(f.get("id", "")),
                )
                for f in plan.ayon_folders
            ]
            _add_rows_with_truncation(table, rows, "Total AYON folders")
            self._console.print(Panel(table, border_style="green"))

        # Kitsu
        kitsu_any = plan.kitsu_episodes or plan.kitsu_sequences or plan.kitsu_shots or plan.kitsu_assets
        if kitsu_any:
            table = Table(title="Kitsu", show_header=True, header_style="bold cyan")
            table.add_column("Type", style="cyan")
            table.add_column("Name")
            table.add_column("ID", style="dim")
            rows = [("Episode", e.get("name", ""), _truncate_id(e.get("id", ""))) for e in plan.kitsu_episodes]
            rows.extend(("Sequence", s.get("name", ""), _truncate_id(s.get("id", ""))) for s in plan.kitsu_sequences)
            rows.extend(("Shot", s.get("name", ""), _truncate_id(s.get("id", ""))) for s in plan.kitsu_shots)
            rows.extend(("Asset", a.get("name", ""), _truncate_id(a.get("id", ""))) for a in plan.kitsu_assets)
            _add_rows_with_truncation(table, rows, "Total Kitsu entities")
            self._console.print(Panel(table, border_style="cyan"))

        # ShotGrid
        sg_any = plan.shotgrid_entities or plan.shotgrid_tasks or plan.shotgrid_versions
        if sg_any:
            table = Table(title="ShotGrid", show_header=True, header_style="bold magenta")
            table.add_column("Type", style="magenta")
            table.add_column("Name")
            table.add_column("ID", style="dim")
            rows = [
                (e.get("type", "Entity"), e.get("code", ""), _truncate_id(e.get("id", "")))
                for e in plan.shotgrid_entities
            ]
            rows.extend(("Version", v.get("code", ""), _truncate_id(v.get("id", ""))) for v in plan.shotgrid_versions)
            rows.extend(("Task", t.get("content", ""), _truncate_id(t.get("id", ""))) for t in plan.shotgrid_tasks)
            _add_rows_with_truncation(table, rows, "Total ShotGrid entities")
            self._console.print(Panel(table, border_style="magenta"))

        # Storage
        if plan.storage_paths:
            table = Table(title="NAS Storage", show_header=True, header_style="bold red")
            table.add_column("Path", style="red")
            table.add_column("Size", justify="right")
            for p in plan.storage_paths:
                table.add_row(str(p), "")
            table.add_row("[bold]Total[/]", _human_size(plan.storage_total_bytes))
            self._console.print(Panel(table, border_style="red"))

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, plan: FolderDeletionPlan) -> None:
        """Perform the deletions described by plan.

        Order: Kitsu → ShotGrid → AYON → Storage.  AYON uses ``force=True``
        on root folders only, which cascades all children server-side.
        """
        kitsu_any = plan.kitsu_episodes or plan.kitsu_sequences or plan.kitsu_shots or plan.kitsu_assets
        if not self._skip_kitsu and kitsu_any:
            self._execute_kitsu(plan)
        sg_any = plan.shotgrid_entities or plan.shotgrid_tasks or plan.shotgrid_versions
        if not self._skip_shotgrid and sg_any:
            self._execute_shotgrid(plan)
        if not self._skip_ayon and plan.ayon_folders:
            self._execute_ayon(plan)
        if not self._skip_storage and plan.storage_paths:
            self._execute_storage(plan)

    def _execute_kitsu(self, plan: FolderDeletionPlan) -> None:
        import gazu

        self._console.print("[bold cyan]Deleting from Kitsu...[/]")
        # Dependency order within hierarchy: shots → sequences → episodes; assets independent
        for shot in plan.kitsu_shots:
            try:
                gazu.shot.remove_shot(shot, force=True)
                _log.info("Kitsu: deleted shot %s", shot.get("name"))
            except Exception as exc:  # gazu raises varied types on delete failure
                _log.warning("Kitsu: failed to delete shot %s -- %s", shot.get("id"), exc)

        for seq in plan.kitsu_sequences:
            try:
                gazu.shot.remove_sequence(seq, force=True)
                _log.info("Kitsu: deleted sequence %s", seq.get("name"))
            except Exception as exc:  # gazu raises varied types on delete failure
                _log.warning("Kitsu: failed to delete sequence %s -- %s", seq.get("id"), exc)

        for ep in plan.kitsu_episodes:
            try:
                gazu.shot.remove_episode(ep)
                _log.info("Kitsu: deleted episode %s", ep.get("name"))
            except Exception as exc:  # gazu raises varied types on delete failure
                _log.warning("Kitsu: failed to delete episode %s -- %s", ep.get("id"), exc)

        for asset in plan.kitsu_assets:
            try:
                gazu.asset.remove_asset(asset, force=True)
                _log.info("Kitsu: deleted asset %s", asset.get("name"))
            except Exception as exc:  # gazu raises varied types on delete failure
                _log.warning("Kitsu: failed to delete asset %s -- %s", asset.get("id"), exc)

        self._console.print("[green]Kitsu cleanup done.[/]")

    def _execute_shotgrid(self, plan: FolderDeletionPlan) -> None:
        sg = self._shotgrid.connect()

        self._console.print("[bold magenta]Deleting from ShotGrid...[/]")
        # Dependency order: versions → tasks → entities
        batch: list[dict] = [
            {"request_type": "delete", "entity_type": "Version", "entity_id": v["id"]} for v in plan.shotgrid_versions
        ]
        batch.extend(
            {"request_type": "delete", "entity_type": "Task", "entity_id": t["id"]} for t in plan.shotgrid_tasks
        )
        batch.extend(
            {"request_type": "delete", "entity_type": e.get("type", "Entity"), "entity_id": e["id"]}
            for e in plan.shotgrid_entities
        )

        if batch:
            try:
                sg.batch(batch)
                _log.info("ShotGrid: batch-deleted %d items", len(batch))
            except Exception as exc:  # shotgun_api3 batch can raise on partial failure
                _log.warning("ShotGrid: batch delete error -- %s", exc)

        self._console.print("[green]ShotGrid cleanup done.[/]")

    def _execute_ayon(self, plan: FolderDeletionPlan) -> None:
        ayon_api = self._ayon.connect()

        self._console.print("[bold green]Deleting from AYON...[/]")
        proj = self._ayon.project_name
        # Only delete root folders — force=True cascades all children server-side,
        # so per-child deletes are unnecessary and would cause 404s for already-deleted items.
        folder_ids = {f["id"] for f in plan.ayon_folders}
        roots = [f for f in plan.ayon_folders if f.get("parentId") not in folder_ids]

        for folder in roots:
            fid = folder["id"]
            fname = folder.get("path", folder.get("name", fid))
            try:
                ayon_api.delete_folder(proj, fid, force=True)
                _log.info("AYON: deleted %s (%s)", fname, fid)
            except Exception as exc:  # ayon_api raises varied types on delete failure
                _log.warning("AYON: failed to delete %s -- %s", fid, exc)

        self._console.print("[green]AYON cleanup done.[/]")

    def _execute_storage(self, plan: FolderDeletionPlan) -> None:
        self._console.print("[bold red]Deleting NAS storage...[/]")
        for path in plan.storage_paths:
            try:
                shutil.rmtree(path)
                _log.info("Storage: removed %s", path)
            except Exception as exc:  # filesystem errors
                _log.warning("Storage: failed to remove %s -- %s", path, exc)
        self._console.print("[green]Storage cleanup done.[/]")


@dataclass
class ProjectRemovalPlan:
    """Whole projects matched for removal, grouped by backend."""

    kitsu_projects: list[dict] = field(default_factory=list)
    ayon_projects: list[dict] = field(default_factory=list)
    shotgrid_projects: list[dict] = field(default_factory=list)
    storage_paths: list[Path] = field(default_factory=list)
    storage_total_bytes: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True when no projects matched on any backend."""
        return not any(
            (
                self.kitsu_projects,
                self.ayon_projects,
                self.shotgrid_projects,
                self.storage_paths,
            )
        )


class ProjectRemoval:
    """Glob-match and delete whole projects across all four backends.

    Project names are matched independently on each backend (there is no
    canonical-key mapping for arbitrary projects). NAS storage is resolved
    from each matched AYON project's anatomy; projects that exist only on
    Kitsu cannot have storage resolved and are skipped for storage with a
    warning.

    Safety is provided by dry-run-by-default plus an explicit confirmation
    in the CLI -- there is no prefix guard.
    """

    def __init__(
        self,
        pattern: str,
        console: Console,
        *,
        skip_kitsu: bool = False,
        skip_shotgrid: bool = False,
        skip_ayon: bool = False,
        skip_storage: bool = False,
        environment: Environment = Environment.TEST,
    ) -> None:
        if not pattern.strip():
            msg = "pattern must not be empty"
            raise ValueError(msg)
        self._pattern = pattern.strip()
        self._console = console
        self._skip_kitsu = skip_kitsu
        self._skip_shotgrid = skip_shotgrid
        self._skip_ayon = skip_ayon
        self._skip_storage = skip_storage
        self._environment = environment
        # No canonical key for arbitrary projects -> empty config.
        self._kitsu = KitsuBackend("", environment, None)
        self._shotgrid = ShotGridBackend("", environment, None)
        self._ayon = AyonBackend("", environment, None)
        self._storage = StorageBackend("", environment, None)

    @staticmethod
    def _match(names: list[str], pattern: str) -> list[str]:
        """Return names equal to or fnmatch-matching the pattern, stable order."""
        return [n for n in names if n == pattern or fnmatch.fnmatch(n, pattern)]

    # -- Planning -------------------------------------------------------

    def plan(self) -> ProjectRemovalPlan:
        """Discover matching projects across backends (read-only)."""
        result = ProjectRemovalPlan()
        if not self._skip_kitsu:
            self._plan_kitsu(result)
        if not self._skip_ayon:
            self._plan_ayon(result)
        if not self._skip_shotgrid:
            self._plan_shotgrid(result)
        if not self._skip_storage:
            self._plan_storage(result)
        return result

    def _plan_kitsu(self, result: ProjectRemovalPlan) -> None:
        try:
            gazu = self._kitsu.connect()
        except BackendUnavailableError as exc:
            result.errors.append(str(exc))
            return
        try:
            self._console.print("[dim]Kitsu: matching projects...[/]")
            all_projects = gazu.project.all_projects()
            matched = self._match([p.get("name", "") for p in all_projects], self._pattern)
            result.kitsu_projects.extend(p for p in all_projects if p.get("name", "") in set(matched))
        except Exception as exc:  # gazu raises varied types
            result.errors.append(f"Kitsu: matching failed -- {exc}")

    def _plan_ayon(self, result: ProjectRemovalPlan) -> None:
        try:
            ayon_api = self._ayon.connect()
        except BackendUnavailableError as exc:
            result.errors.append(str(exc))
            return
        try:
            self._console.print("[dim]AYON: matching projects...[/]")
            all_projects = list(ayon_api.get_projects(fields=["name"]))
            matched = set(self._match([p.get("name", "") for p in all_projects], self._pattern))
            result.ayon_projects.extend(p for p in all_projects if p.get("name", "") in matched)
        except Exception as exc:  # ayon_api raises varied types
            result.errors.append(f"AYON: matching failed -- {exc}")

    def _plan_shotgrid(self, result: ProjectRemovalPlan) -> None:
        try:
            sg = self._shotgrid.connect()
        except BackendUnavailableError as exc:
            result.errors.append(str(exc))
            return
        try:
            self._console.print("[dim]ShotGrid: matching projects...[/]")
            all_projects = sg.find("Project", [], ["id", "name"])
            matched = set(self._match([p.get("name", "") for p in all_projects], self._pattern))
            result.shotgrid_projects.extend(p for p in all_projects if p.get("name", "") in matched)
        except Exception as exc:  # shotgun_api3 raises varied types
            result.errors.append(f"ShotGrid: matching failed -- {exc}")

    def _plan_storage(self, result: ProjectRemovalPlan) -> None:
        """Resolve NAS folders for matched AYON projects only."""
        if not result.ayon_projects:
            if result.kitsu_projects:
                result.errors.append(
                    "Storage: skipped -- no matching AYON projects to resolve NAS roots from"
                )
            return
        for project in result.ayon_projects:
            name = project.get("name", "")
            try:
                storage_root = self._storage.resolve_root(name)
            except Exception as exc:  # anatomy/filesystem errors
                result.errors.append(f"Storage: could not resolve root for {name} -- {exc}")
                continue
            nas_path = storage_root / name
            if not nas_path.exists():
                _log.info("Storage: path not found -- %s", nas_path)
                continue
            result.storage_paths.append(nas_path)
            total = sum(f.stat().st_size for f in nas_path.rglob("*") if f.is_file())
            result.storage_total_bytes += total

    # -- Display --------------------------------------------------------

    def display_plan(self, plan: ProjectRemovalPlan) -> None:
        """Print a Rich summary of the projects to be removed."""
        for err in plan.errors:
            self._console.print(f"[yellow]WARNING: {err}[/]")
        if plan.errors:
            self._console.print()
        if plan.is_empty:
            self._console.print("[dim]No matching projects found.[/]")
            return

        table = Table(title=f"Projects matching '{self._pattern}'", show_header=True, header_style="bold red")
        table.add_column("Backend", style="red")
        table.add_column("Project")
        for p in plan.kitsu_projects:
            table.add_row("Kitsu", p.get("name", ""))
        for p in plan.ayon_projects:
            table.add_row("AYON", p.get("name", ""))
        for p in plan.shotgrid_projects:
            table.add_row("ShotGrid", p.get("name", ""))
        for path in plan.storage_paths:
            table.add_row("Storage", str(path))
        self._console.print(Panel(table, border_style="red"))
        if plan.storage_paths:
            self._console.print(f"Storage total: [bold]{_human_size(plan.storage_total_bytes)}[/]")

    # -- Execution ------------------------------------------------------

    def execute(self, plan: ProjectRemovalPlan) -> None:
        """Delete matched projects from each backend."""
        if not self._skip_kitsu and plan.kitsu_projects:
            self._execute_kitsu(plan)
        if not self._skip_ayon and plan.ayon_projects:
            self._execute_ayon(plan)
        if not self._skip_shotgrid and plan.shotgrid_projects:
            self._execute_shotgrid(plan)
        if not self._skip_storage and plan.storage_paths:
            self._execute_storage(plan)

    def _execute_kitsu(self, plan: ProjectRemovalPlan) -> None:
        gazu = self._kitsu.connect()
        self._console.print("[bold cyan]Removing Kitsu projects...[/]")
        try:
            closed_status = gazu.project.get_project_status_by_name("Closed")
        except Exception as exc:  # gazu raises varied types; degrade gracefully
            _log.warning("Kitsu: could not fetch 'Closed' status -- %s", exc)
            closed_status = None
        for project in plan.kitsu_projects:
            name = project.get("name", "")
            try:
                # remove_project(force=True) returns HTTP 400 unless status is Closed first.
                if closed_status:
                    project["project_status_id"] = closed_status["id"]
                    gazu.project.update_project(project)
                gazu.project.remove_project(project, force=True)
                self._console.print(f"[green]OK[/] Kitsu: removed {name}")
            except Exception as exc:  # gazu raises varied types
                _log.warning("Kitsu: failed to remove %s -- %s", name, exc)
                self._console.print(f"[red]FAIL[/] Kitsu: {name} -- {exc}")

    def _execute_ayon(self, plan: ProjectRemovalPlan) -> None:
        ayon_api = self._ayon.connect()
        self._console.print("[bold green]Removing AYON projects...[/]")
        for project in plan.ayon_projects:
            name = project.get("name", "")
            try:
                ayon_api.delete_project(name)
                self._console.print(f"[green]OK[/] AYON: removed {name}")
            except Exception as exc:  # ayon_api raises varied types
                _log.warning("AYON: failed to remove %s -- %s", name, exc)
                self._console.print(f"[red]FAIL[/] AYON: {name} -- {exc}")

    def _execute_shotgrid(self, plan: ProjectRemovalPlan) -> None:
        sg = self._shotgrid.connect()
        self._console.print("[bold magenta]Removing ShotGrid projects...[/]")
        for project in plan.shotgrid_projects:
            name = project.get("name", "")
            try:
                sg.delete("Project", project["id"])
                self._console.print(f"[green]OK[/] ShotGrid: removed {name}")
            except Exception as exc:  # shotgun_api3 raises varied types
                _log.warning("ShotGrid: failed to remove %s -- %s", name, exc)
                self._console.print(f"[red]FAIL[/] ShotGrid: {name} -- {exc}")

    def _execute_storage(self, plan: ProjectRemovalPlan) -> None:
        self._console.print("[bold red]Removing NAS storage...[/]")
        for path in plan.storage_paths:
            try:
                shutil.rmtree(path)
                self._console.print(f"[green]OK[/] Storage: removed {path}")
            except Exception as exc:  # filesystem errors
                _log.warning("Storage: failed to remove %s -- %s", path, exc)
                self._console.print(f"[red]FAIL[/] Storage: {path} -- {exc}")
