"""Folder cleanup: delete any AYON path hierarchy from all backends."""

from __future__ import annotations

import fnmatch
import logging
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    from collections.abc import Callable

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

# Row provenance: how an item entered the deletion plan.
_SRC_MATCHED = "matched"  # directly matched the path glob
_SRC_DESCENDANT = "descendant"  # child folder swept in under a match
_SRC_ATTACHED = "attached"  # task/version hanging off a matched/descendant entity

# Date-window status of a single entity, relative to an active filter.
_DATE_IN = "in"  # created within the window -> eligible for deletion
_DATE_OUT = "out"  # created outside the window -> preserved
_DATE_NODATE = "nodate"  # no datestamp -> preserved (never delete what we can't date)

# AYON folder fields we fetch explicitly so ``createdAt`` is always present
# (the ayon_api default folder field set omits it). Superset of the keys the
# planner and cross-backend resolution rely on.
_AYON_FOLDER_FIELDS = {
    "id",
    "name",
    "label",
    "folderType",
    "path",
    "parentId",
    "active",
    "status",
    "tags",
    "data",
    "createdAt",
}


@dataclass(frozen=True)
class DateWindow:
    """Inclusive ``created_at`` window (UTC) for date-filtered cleanup.

    ``after``/``before`` are tz-aware UTC datetimes. Comparisons throughout the
    tool are done in UTC, matching how :func:`_assess_risk` treats timestamps.
    """

    after: datetime | None = None
    before: datetime | None = None

    @property
    def active(self) -> bool:
        """True when at least one bound is set."""
        return self.after is not None or self.before is not None

    def status(self, value: object) -> str:
        """Classify a ``created_at`` value as in / out of window / undateable."""
        dt = _coerce_created_at(value)
        if dt is None:
            return _DATE_NODATE
        dt = dt.astimezone(UTC)
        if self.after is not None and dt < self.after:
            return _DATE_OUT
        if self.before is not None and dt > self.before:
            return _DATE_OUT
        return _DATE_IN

    def describe(self) -> str:
        """Human-readable window, e.g. ``2026-07-09 .. (open)``."""
        lo = self.after.date().isoformat() if self.after else "(open)"
        hi = self.before.date().isoformat() if self.before else "(open)"
        return f"{lo} .. {hi} (UTC)"


def _parse_date_bound(value: str, *, end_of_day: bool) -> datetime:
    """Parse ``YYYY-MM-DD`` or a full ISO datetime into a UTC-aware datetime.

    A bare date is anchored at UTC start-of-day, or end-of-day when it is the
    inclusive upper bound. Naive datetimes are assumed UTC. Raises ValueError
    on unparseable input.
    """
    text = value.strip()
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        msg = f"invalid date '{value}' -- use YYYY-MM-DD or an ISO 8601 datetime"
        raise ValueError(msg) from exc
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    if end_of_day and len(text) == 10:  # bare 'YYYY-MM-DD' upper bound
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def parse_date_window(after: str | None, before: str | None) -> DateWindow:
    """Build a :class:`DateWindow` from optional CLI date strings."""
    return DateWindow(
        after=_parse_date_bound(after, end_of_day=False) if after else None,
        before=_parse_date_bound(before, end_of_day=True) if before else None,
    )


def _filter_files_by_mtime(root: Path, window: DateWindow) -> tuple[list[Path], int]:
    """Return in-window files (by mtime) beneath ``root`` and their total size."""
    files: list[Path] = []
    total = 0
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
        if window.status(mtime) == _DATE_IN:
            files.append(f)
            total += f.stat().st_size
    return files, total


def _coerce_created_at(value: object) -> datetime | None:
    """Best-effort parse of a backend ``created_at`` into a tz-aware datetime.

    ShotGrid returns ``datetime`` objects; gazu/AYON return ISO strings.
    Naive datetimes are assumed UTC.  Unparseable values yield ``None``.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _author_name(value: object) -> str:
    """Extract a display name from a backend ``created_by`` value.

    ShotGrid returns ``{"type": ..., "name": ...}``; gazu may return a plain
    name string or a ``first_name``/``last_name`` pair.  Returns ``""`` when
    no author information is available.
    """
    if isinstance(value, dict):
        name = value.get("name") or value.get("full_name")
        if name:
            return str(name)
        first = value.get("first_name", "")
        last = value.get("last_name", "")
        return f"{first} {last}".strip()
    return str(value) if value else ""


def _fmt_date(value: object) -> str:
    """Render a backend ``created_at`` value as ``YYYY-MM-DD`` (or ``""``)."""
    dt = _coerce_created_at(value)
    return dt.date().isoformat() if dt else ""


def _sg_entity_fields(sg_type: str) -> list[str]:
    """Fields to fetch for a ShotGrid entity type, incl. the episode-anchor links."""
    fields = ["id", "code", "created_at", "created_by"]
    if sg_type == "Sequence":
        fields.append("sg_episode")
    elif sg_type == "Shot":
        fields.extend(("sg_sequence", "sg_scene"))
    return fields


def _target_episodes(folders: list[dict]) -> set[str]:
    """Episode name(s) the AYON path resolves under (the segment after ``/episodes/``)."""
    episodes: set[str] = set()
    for f in folders:
        parts = f.get("path", "").split("/")
        if len(parts) >= 3 and parts[1] == "episodes":  # ['', 'episodes', '<ep>', ...]
            episodes.add(parts[2])
    return episodes


def _entity_episode(entity: dict, seq_episode: dict[int, str | None]) -> str | None:
    """Resolve the episode name of a matched SG entity, or ``None`` when unknown.

    ``seq_episode`` maps a Sequence id to its ``sg_episode`` name, used to resolve a
    Shot's episode when the Shot has no direct Scene (episode) link.
    """
    etype = entity.get("type")
    if etype == "Scene":  # a Scene *is* the episode
        return entity.get("code")
    if etype == "Sequence":
        ep = entity.get("sg_episode")
        return ep.get("name") if ep else None
    if etype == "Shot":
        scene = entity.get("sg_scene")  # Shot's own episode link (Scene == Episode)
        if scene:
            return scene.get("name")
        seq = entity.get("sg_sequence")
        return seq_episode.get(seq.get("id")) if seq else None
    return None


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
    # IDs of folders that directly matched the path glob (vs swept-in descendants)
    ayon_matched_ids: set[str] = field(default_factory=set)

    # Kitsu — grouped by entity type for dependency-safe deletion ordering
    kitsu_episodes: list[dict] = field(default_factory=list)
    kitsu_sequences: list[dict] = field(default_factory=list)
    kitsu_shots: list[dict] = field(default_factory=list)
    kitsu_assets: list[dict] = field(default_factory=list)

    # ShotGrid — entities (Scene/Sequence/Shot/Asset) plus their dependants
    shotgrid_entities: list[dict] = field(default_factory=list)
    shotgrid_tasks: list[dict] = field(default_factory=list)
    shotgrid_versions: list[dict] = field(default_factory=list)
    # Path-anchoring: SG entities excluded because their episode != the target
    # episode(s) -- (type, code, detail). And entities kept but whose episode link
    # could not be resolved -- (type, code).
    shotgrid_dropped: list[tuple[str, str, str]] = field(default_factory=list)
    shotgrid_unverified: list[tuple[str, str]] = field(default_factory=list)

    # NAS storage — populated only for plan roots whose AYON path is under /episodes/
    storage_paths: list[Path] = field(default_factory=list)
    storage_total_bytes: int = 0
    # NAS files pruned individually when a date filter is active (never whole dirs)
    storage_files: list[Path] = field(default_factory=list)
    storage_files_total_bytes: int = 0

    # Date-filter bookkeeping (populated only when a --created-after/before is set).
    # AYON is folder-cascade-only, so we can only force-delete a folder whose whole
    # subtree is in-window; this holds the ids that are safe to delete.
    ayon_deletable_ids: set[str] = field(default_factory=set)
    # Leaf entities preserved by the filter: (backend, kind, name, created, reason)
    date_excluded: list[tuple[str, str, str, str, str]] = field(default_factory=list)
    date_kept: int = 0

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
                self.storage_files,
            )
        )


@dataclass
class RiskAssessment:
    """Provenance summary of a plan, used to flag non-fresh delete targets.

    Computed purely from the ``created_at``/``created_by`` fields already
    fetched during planning, so it stays a read-only, side-effect-free view.
    """

    total: int = 0
    created_today: int = 0
    created_earlier: int = 0
    oldest: datetime | None = None
    authors: list[str] = field(default_factory=list)

    @property
    def is_risky(self) -> bool:
        """True when the target does not look like fresh sandbox data.

        Heuristic: any tracked entity predates today (i.e. was created earlier
        than the current day) OR more than one distinct author is present.
        Fresh sandbox data is created moments ago by a single service account,
        so either signal means real production work may be in scope.
        """
        return self.created_earlier > 0 or len(self.authors) > 1


def _assess_risk(records: list[dict], now: datetime) -> RiskAssessment:
    """Summarise provenance of ``records`` (dicts with created_at/created_by).

    ``now`` is passed in (rather than read from the clock) so the assessment
    is deterministic and unit-testable.
    """
    today = now.astimezone(UTC).date()
    total = 0
    created_today = 0
    created_earlier = 0
    oldest: datetime | None = None
    authors: list[str] = []

    for rec in records:
        created = _coerce_created_at(rec.get("created_at"))
        author = _author_name(rec.get("created_by"))
        if author and author not in authors:
            authors.append(author)
        if created is None:
            continue
        total += 1
        if created.astimezone(UTC).date() < today:
            created_earlier += 1
        else:
            created_today += 1
        if oldest is None or created < oldest:
            oldest = created

    return RiskAssessment(
        total=total,
        created_today=created_today,
        created_earlier=created_earlier,
        oldest=oldest,
        authors=sorted(authors),
    )


def _folder_index(folders: list[dict], type_map: dict[str, str] | None = None) -> dict[tuple[str, str], dict]:
    """Map ``(entity_type, name)`` to the owning AYON folder dict.

    ``type_map`` translates AYON folderType to a backend entity type (e.g.
    ``_SG_TYPE_MAP`` for ShotGrid); when ``None`` the folderType is used as-is.
    Lets the display resolve a full AYON path and provenance for entities that
    only carry ``(type, name)``.
    """
    index: dict[tuple[str, str], dict] = {}
    for folder in folders:
        name = folder.get("name", "")
        if not name:
            continue
        ftype = folder.get("folderType", "")
        etype = type_map.get(ftype, ftype) if type_map else ftype
        index.setdefault((etype, name), folder)
    return index


def _entity_source(folder: dict | None, matched_ids: set[str]) -> str:
    """Classify an entity as directly matched vs a swept-in descendant."""
    if folder is not None and folder.get("id") in matched_ids:
        return _SRC_MATCHED
    return _SRC_DESCENDANT


def _risk_banner_text(assessment: RiskAssessment) -> str:
    """Render the pre-flight RISK panel body from a risk assessment."""
    oldest = assessment.oldest.date().isoformat() if assessment.oldest else "unknown"
    authors = assessment.authors
    author_str = ", ".join(authors) if authors else "unknown"
    return (
        f"[bold]{assessment.created_earlier}/{assessment.total} entities predate today[/] "
        f"(oldest {oldest}; {len(authors)} author(s): {author_str}).\n"
        "This is [bold]not fresh sandbox data[/] -- confirm before --execute."
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
        date_window: DateWindow | None = None,
    ) -> None:
        normalized = path.strip("/")
        if not normalized:
            msg = "path must not be empty or '/'"
            raise ValueError(msg)
        self._path = "/" + normalized
        self._project_name = project_name
        self._environment = environment
        self._window = date_window or DateWindow()
        self._console = console
        self._skip_kitsu = skip_kitsu
        self._skip_shotgrid = skip_shotgrid
        self._skip_ayon = skip_ayon
        self._skip_storage = skip_storage
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
            folder = ayon_api_mod.get_folder_by_path(
                self._ayon.project_name, "/".join(segments), fields=_AYON_FOLDER_FIELDS
            )
            return [folder] if folder else []

        if first_glob > 0:
            # Resolve the exact prefix, then fan out at the first glob
            prefix = "/".join(segments[:first_glob])
            anchor = ayon_api_mod.get_folder_by_path(self._ayon.project_name, prefix, fields=_AYON_FOLDER_FIELDS)
            if not anchor:
                return []
            children = list(
                ayon_api_mod.get_folders(self._ayon.project_name, parent_ids=[anchor["id"]], fields=_AYON_FOLDER_FIELDS)
            )
            candidates = [c for c in children if fnmatch.fnmatch(c.get("name", ""), segments[first_glob])]
            remaining = segments[first_glob + 1 :]
        else:
            # Path starts with a glob — must enumerate all root-level folders
            all_folders = list(ayon_api_mod.get_folders(self._ayon.project_name, fields=_AYON_FOLDER_FIELDS))
            candidates = [
                f for f in all_folders if f.get("parentId") is None and fnmatch.fnmatch(f.get("name", ""), segments[0])
            ]
            remaining = segments[1:]

        for seg in remaining:
            if not candidates:
                return []
            next_candidates: list[dict] = []
            for parent in candidates:
                children = list(
                    ayon_api_mod.get_folders(
                        self._ayon.project_name, parent_ids=[parent["id"]], fields=_AYON_FOLDER_FIELDS
                    )
                )
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
                for child in ayon_api_mod.get_folders(
                    project_name, parent_ids=[parent["id"]], fields=_AYON_FOLDER_FIELDS
                ):
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

        self._apply_date_filter(result)
        return result

    # -- Date filter (Option A: leaf-level scalpel) --------------------

    def _apply_date_filter(self, result: FolderDeletionPlan) -> None:
        """Restrict the plan to in-window entities (leaf-level pruning).

        No-op unless a window is active. When active:

        * ShotGrid/Kitsu leaf entities are kept only if their own ``created_at``
          is in-window; out-of-window and undateable ones are preserved.
        * AYON is folder-cascade-only, so a folder is deletable only when its
          entire subtree is in-window (:meth:`_ayon_deletable_ids`); otherwise
          the folder is preserved -- we never force-delete an out-of-window
          folder to reach an in-window entity inside it.
        * NAS files were already filtered by mtime in :meth:`_plan_storage`.
        """
        if not self._window.active:
            # No filter: every discovered folder is deletable, as before.
            result.ayon_deletable_ids = {f["id"] for f in result.ayon_folders}
            return

        result.shotgrid_entities = self._partition(
            result, result.shotgrid_entities, "ShotGrid", lambda e: e.get("type", "Entity"), "code"
        )
        result.shotgrid_versions = self._partition(result, result.shotgrid_versions, "ShotGrid", "Version", "code")
        result.shotgrid_tasks = self._partition(result, result.shotgrid_tasks, "ShotGrid", "Task", "content")
        result.kitsu_episodes = self._partition(result, result.kitsu_episodes, "Kitsu", "Episode", "name")
        result.kitsu_sequences = self._partition(result, result.kitsu_sequences, "Kitsu", "Sequence", "name")
        result.kitsu_shots = self._partition(result, result.kitsu_shots, "Kitsu", "Shot", "name")
        result.kitsu_assets = self._partition(result, result.kitsu_assets, "Kitsu", "Asset", "name")

        result.ayon_deletable_ids = self._ayon_deletable_ids(result.ayon_folders)

    def _partition(
        self,
        result: FolderDeletionPlan,
        items: list[dict],
        backend: str,
        kind: str | Callable[[dict], str],
        name_key: str,
    ) -> list[dict]:
        """Return the in-window subset of ``items``; record the rest as excluded."""
        kept: list[dict] = []
        for item in items:
            status = self._window.status(item.get("created_at"))
            if status == _DATE_IN:
                kept.append(item)
                result.date_kept += 1
                continue
            reason = "out of window" if status == _DATE_OUT else "no date"
            label = kind(item) if callable(kind) else kind
            result.date_excluded.append(
                (backend, label, str(item.get(name_key, "")), _fmt_date(item.get("created_at")), reason)
            )
        return kept

    def _ayon_deletable_ids(self, folders: list[dict]) -> set[str]:
        """Ids of folders whose entire subtree is in-window (safe to cascade-delete)."""
        by_id = {f["id"]: f for f in folders}
        children: dict[str, list[str]] = {}
        for f in folders:
            pid = f.get("parentId")
            if pid in by_id:
                children.setdefault(pid, []).append(f["id"])

        memo: dict[str, bool] = {}

        def subtree_in_window(fid: str) -> bool:
            if fid in memo:
                return memo[fid]
            in_window = self._window.status(by_id[fid].get("createdAt")) == _DATE_IN
            if in_window:
                in_window = all(subtree_in_window(cid) for cid in children.get(fid, []))
            memo[fid] = in_window
            return in_window

        return {fid for fid in by_id if subtree_in_window(fid)}

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
            result.ayon_matched_ids.update(f["id"] for f in matched)
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
                    _sg_entity_fields(sg_type),
                )
                all_entities.extend(entities)

            # Path-anchored verification: a project-wide code match can grab a
            # same-named entity under a DIFFERENT episode. Keep only entities that
            # belong to the target path's episode(s); drop + report the rest, and
            # fetch dependants for the kept set only.
            kept = self._verify_shotgrid_episodes(sg, project, all_entities, result)
            result.shotgrid_entities.extend(kept)

            if kept:
                result.shotgrid_tasks.extend(
                    sg.find(
                        "Task",
                        [["project", "is", project], ["entity", "in", kept]],
                        ["id", "content", "entity", "created_at", "created_by"],
                    )
                )
                result.shotgrid_versions.extend(
                    sg.find(
                        "Version",
                        [["project", "is", project], ["entity", "in", kept]],
                        ["id", "code", "entity", "created_at", "created_by"],
                    )
                )

            _log.info(
                "ShotGrid: %d entities kept, %d dropped (episode mismatch), %d tasks, %d versions",
                len(result.shotgrid_entities),
                len(result.shotgrid_dropped),
                len(result.shotgrid_tasks),
                len(result.shotgrid_versions),
            )

        except Exception as exc:  # shotgun_api3 raises varied exception types
            msg = f"ShotGrid: discovery failed -- {exc}"
            result.errors.append(msg)
            _log.warning(msg)

    def _verify_shotgrid_episodes(
        self,
        sg: object,
        project: dict,
        entities: list[dict],
        result: FolderDeletionPlan,
    ) -> list[dict]:
        """Keep only SG entities under the target episode(s); drop + report mismatches.

        The project-wide ``["code", "in", names]`` match can return a same-named
        sequence/shot living under a different episode. We anchor to the episode(s)
        the AYON path resolved under and verify each entity's own episode link.
        Entities whose episode cannot be determined (unpopulated link) are kept --
        AYON already resolved them under the target path -- but reported as
        unverified so nothing is silently kept or dropped.
        """
        targets = _target_episodes(result.ayon_folders)
        if not targets:
            return entities  # not an episode-scoped path (e.g. /assets/...)

        # Resolve Shot -> episode via referenced sequences (one batched read) for
        # shots that lack a direct Scene link.
        seq_ids = {
            e["sg_sequence"]["id"]
            for e in entities
            if e.get("type") == "Shot" and e.get("sg_sequence") and not e.get("sg_scene")
        }
        seq_episode: dict[int, str | None] = {}
        if seq_ids:
            for seq in sg.find(
                "Sequence",
                [["project", "is", project], ["id", "in", list(seq_ids)]],
                ["id", "sg_episode"],
            ):
                ep = seq.get("sg_episode")
                seq_episode[seq["id"]] = ep.get("name") if ep else None

        kept: list[dict] = []
        for entity in entities:
            episode = _entity_episode(entity, seq_episode)
            etype = entity.get("type", "Entity")
            code = entity.get("code", "")
            if episode is None:
                kept.append(entity)
                result.shotgrid_unverified.append((etype, code))
            elif episode in targets:
                kept.append(entity)
            else:
                result.shotgrid_dropped.append((etype, code, f"episode {episode} not in {sorted(targets)}"))
        return kept

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
            if self._window.active:
                # Leaf-level pruning: only in-window files, never the parent dir
                # (which may predate the window or hold out-of-window files).
                files, total = _filter_files_by_mtime(nas_path, self._window)
                result.storage_files.extend(files)
                result.storage_files_total_bytes += total
                _log.info("Storage: %d in-window file(s) under %s (%s)", len(files), nas_path, _human_size(total))
            else:
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

        if plan.is_empty and not plan.date_excluded and not plan.shotgrid_dropped:
            self._console.print("[dim]Nothing found to delete.[/]")
            return

        active = self._window.active

        # Provenance/age guardrails shown before the raw entity tables.
        self._display_target_banner(plan)
        self._display_risk_banner(plan)
        self._display_episode_anchoring(plan)

        # AYON — source of truth shown first
        if plan.ayon_folders:
            table = Table(title="AYON Folders", show_header=True, header_style="bold green")
            table.add_column("Type", style="green")
            table.add_column("Path")
            table.add_column("Source", style="dim")
            if active:
                table.add_column("Created", style="dim")
                table.add_column("Filter", style="dim")
            table.add_column("ID", style="dim")

            def _ayon_row(f: dict) -> tuple[str, ...]:
                base = (
                    f.get("folderType") or "Folder",
                    f.get("path", f.get("name", "")),
                    _entity_source(f, plan.ayon_matched_ids),
                )
                if active:
                    verdict = "delete" if f["id"] in plan.ayon_deletable_ids else "preserve"
                    base = (*base, _fmt_date(f.get("createdAt")), verdict)
                return (*base, _truncate_id(f.get("id", "")))

            rows: list[tuple[str, ...]] = [_ayon_row(f) for f in plan.ayon_folders]
            _add_rows_with_truncation(table, rows, "Total AYON folders")
            self._console.print(Panel(table, border_style="green"))

        # Kitsu
        kitsu_any = plan.kitsu_episodes or plan.kitsu_sequences or plan.kitsu_shots or plan.kitsu_assets
        if kitsu_any:
            kitsu_index = _folder_index(plan.ayon_folders)

            def _kitsu_row(ktype: str, entity: dict) -> tuple[str, ...]:
                folder = kitsu_index.get((ktype, entity.get("name", "")))
                path = folder.get("path", "") if folder else ""
                return (
                    ktype,
                    entity.get("name", ""),
                    path,
                    _fmt_date(entity.get("created_at")),
                    _author_name(entity.get("created_by")),
                    _entity_source(folder, plan.ayon_matched_ids),
                    _truncate_id(entity.get("id", "")),
                )

            table = Table(title="Kitsu", show_header=True, header_style="bold cyan")
            table.add_column("Type", style="cyan")
            table.add_column("Name")
            table.add_column("Path")
            table.add_column("Created", style="dim")
            table.add_column("By", style="dim")
            table.add_column("Source", style="dim")
            table.add_column("ID", style="dim")
            rows = [_kitsu_row("Episode", e) for e in plan.kitsu_episodes]
            rows.extend(_kitsu_row("Sequence", s) for s in plan.kitsu_sequences)
            rows.extend(_kitsu_row("Shot", s) for s in plan.kitsu_shots)
            rows.extend(_kitsu_row("Asset", a) for a in plan.kitsu_assets)
            _add_rows_with_truncation(table, rows, "Total Kitsu entities")
            self._console.print(Panel(table, border_style="cyan"))

        # ShotGrid
        sg_any = plan.shotgrid_entities or plan.shotgrid_tasks or plan.shotgrid_versions
        if sg_any:
            sg_index = _folder_index(plan.ayon_folders, _SG_TYPE_MAP)

            def _sg_entity_row(entity: dict) -> tuple[str, ...]:
                etype = entity.get("type", "Entity")
                folder = sg_index.get((etype, entity.get("code", "")))
                return (
                    etype,
                    entity.get("code", ""),
                    folder.get("path", "") if folder else "",
                    _fmt_date(entity.get("created_at")),
                    _author_name(entity.get("created_by")),
                    _entity_source(folder, plan.ayon_matched_ids),
                    _truncate_id(entity.get("id", "")),
                )

            def _sg_attached_row(kind: str, name: str, item: dict) -> tuple[str, ...]:
                link = item.get("entity") or {}
                folder = sg_index.get((link.get("type", ""), link.get("name", "")))
                return (
                    kind,
                    name,
                    folder.get("path", "") if folder else "",
                    _fmt_date(item.get("created_at")),
                    _author_name(item.get("created_by")),
                    _SRC_ATTACHED,
                    _truncate_id(item.get("id", "")),
                )

            table = Table(title="ShotGrid", show_header=True, header_style="bold magenta")
            table.add_column("Type", style="magenta")
            table.add_column("Name")
            table.add_column("Path")
            table.add_column("Created", style="dim")
            table.add_column("By", style="dim")
            table.add_column("Source", style="dim")
            table.add_column("ID", style="dim")
            rows = [_sg_entity_row(e) for e in plan.shotgrid_entities]
            rows.extend(_sg_attached_row("Version", v.get("code", ""), v) for v in plan.shotgrid_versions)
            rows.extend(_sg_attached_row("Task", t.get("content", ""), t) for t in plan.shotgrid_tasks)
            _add_rows_with_truncation(table, rows, "Total ShotGrid entities")
            self._console.print(Panel(table, border_style="magenta"))

        # Storage
        if plan.storage_paths or plan.storage_files:
            table = Table(title="NAS Storage", show_header=True, header_style="bold red")
            table.add_column("Path", style="red")
            table.add_column("Size", justify="right")
            for p in plan.storage_paths:
                table.add_row(str(p), "")
            for f in plan.storage_files:
                table.add_row(str(f), "")
            total_bytes = plan.storage_total_bytes + plan.storage_files_total_bytes
            label = "Total (in-window files)" if plan.storage_files else "Total"
            table.add_row(f"[bold]{label}[/]", _human_size(total_bytes))
            self._console.print(Panel(table, border_style="red"))

        # Date-filter accounting shown after the entity tables.
        if active:
            self._display_date_filter_summary(plan)

    def _display_date_filter_summary(self, plan: FolderDeletionPlan) -> None:
        """Print the kept/excluded counts, the preserved rows, and the AYON constraint."""
        excluded = plan.date_excluded
        self._console.print(
            f"[bold]Date filter:[/] {plan.date_kept} entity(ies) kept, {len(excluded)} excluded (preserved)."
        )
        if excluded:
            table = Table(
                title="Preserved by date filter (outside window / undateable)",
                show_header=True,
                header_style="bold yellow",
            )
            table.add_column("Backend", style="dim")
            table.add_column("Type")
            table.add_column("Name")
            table.add_column("Created", style="dim")
            table.add_column("Reason", style="dim")
            rows: list[tuple[str, ...]] = list(excluded)
            _add_rows_with_truncation(table, rows, "Total preserved")
            self._console.print(Panel(table, border_style="yellow"))

        # Surface the AYON folder-only constraint whenever leaves are pruned but
        # AYON must keep a parent folder it cannot prune at version level.
        preserved_folders = [f for f in plan.ayon_folders if f["id"] not in plan.ayon_deletable_ids]
        pruned_leaves = plan.shotgrid_versions or plan.shotgrid_tasks or plan.shotgrid_entities or plan.storage_files
        if preserved_folders and pruned_leaves:
            self._console.print(
                "[yellow]Note:[/] AYON deletion is folder-cascade-only. In-window leaf entities inside the "
                f"{len(preserved_folders)} preserved folder(s) are pruned on ShotGrid/Kitsu/NAS but remain as "
                "AYON products/versions (AYON has no version-level delete here)."
            )

    def _display_target_banner(self, plan: FolderDeletionPlan) -> None:
        """Print the resolved delete target: project, server, glob, and roots."""
        roots = [f for f in plan.ayon_folders if f.get("id") in plan.ayon_matched_ids]
        lines = [
            f"[bold]Project:[/] {self._project_name}",
            f"[bold]Server:[/]  {self._environment.value}",
            f"[bold]Target:[/]  {self._path}",
        ]
        if self._window.active:
            lines.append(f"[bold yellow]Date filter:[/] created_at within {self._window.describe()}")
        if roots:
            lines.append("[bold]Resolved:[/]")
            lines.extend(
                f"  - {f.get('path', f.get('name', ''))} ([bold]{f.get('folderType') or 'Folder'}[/])" for f in roots
            )
        descendants = len(plan.ayon_folders) - len(roots)
        if descendants:
            lines.append(f"[dim]+ {descendants} descendant folder(s) swept in (see AYON table).[/]")
        self._console.print(Panel("\n".join(lines), title="Cleanup target", border_style="yellow"))

    def _display_risk_banner(self, plan: FolderDeletionPlan) -> None:
        """Print a pre-flight provenance/age warning derived from the plan.

        Only ShotGrid carries per-entity ``created_at``/``created_by``, so the
        assessment is computed from its entities, tasks, and versions. A bold
        red panel is shown when the target does not look sandbox-fresh; a quiet
        confirmation line is shown when it does.
        """
        records = [*plan.shotgrid_entities, *plan.shotgrid_tasks, *plan.shotgrid_versions]
        if not records:
            return
        assessment = _assess_risk(records, datetime.now(UTC))
        if assessment.is_risky:
            self._console.print(
                Panel(
                    _risk_banner_text(assessment),
                    title="[bold red]:warning:  DELETE RISK[/]",
                    border_style="bold red",
                )
            )
        elif assessment.total:
            self._console.print(
                f"[dim]Target looks sandbox-fresh: {assessment.total} entity(ies), "
                f"all created today, {len(assessment.authors)} author(s).[/]"
            )

    def _display_episode_anchoring(self, plan: FolderDeletionPlan) -> None:
        """Report ShotGrid entities dropped (episode mismatch) or kept-but-unverified.

        Path-anchoring closes a name-collision hole: a project-wide code match can
        return a same-named entity under a different episode. Dropped entities are
        excluded from the plan; unverified ones are kept but flagged so nothing is
        silently kept or dropped.
        """
        if plan.shotgrid_dropped:
            self._console.print(
                f"[bold yellow]Dropped {len(plan.shotgrid_dropped)} ShotGrid entity(ies) "
                "-- episode mismatch, not in delete plan:[/]"
            )
            for etype, code, detail in plan.shotgrid_dropped:
                self._console.print(f"  [dim]- {etype} {code}: {detail}[/]")
        if plan.shotgrid_unverified:
            self._console.print(
                f"[dim]{len(plan.shotgrid_unverified)} ShotGrid entity(ies) episode-unverified "
                "(kept; AYON-resolved, SG episode link unpopulated).[/]"
            )

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
        if not self._skip_storage and (plan.storage_paths or plan.storage_files):
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
        # Under a date filter, ayon_deletable_ids holds only folders whose whole
        # subtree is in-window; out-of-window folders are never deleted, and the
        # top-most deletable folders cascade-delete their (in-window) descendants.
        deletable = plan.ayon_deletable_ids
        roots = [f for f in plan.ayon_folders if f["id"] in deletable and f.get("parentId") not in deletable]

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
        # No filter: remove whole resolved directories.
        for path in plan.storage_paths:
            try:
                shutil.rmtree(path)
                _log.info("Storage: removed %s", path)
            except Exception as exc:  # filesystem errors
                _log.warning("Storage: failed to remove %s -- %s", path, exc)
        # Filter active: prune only in-window files, never their parent dirs.
        for file_path in plan.storage_files:
            try:
                file_path.unlink()
                _log.info("Storage: removed file %s", file_path)
            except Exception as exc:  # filesystem errors
                _log.warning("Storage: failed to remove file %s -- %s", file_path, exc)
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
                result.errors.append("Storage: skipped -- no matching AYON projects to resolve NAS roots from")
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
