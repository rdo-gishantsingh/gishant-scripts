"""Episode cleanup orchestrator across Kitsu, ShotGrid, AYON, and NAS storage."""

from __future__ import annotations

import fnmatch
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

_log = logging.getLogger(__name__)

# Default .env location for RDO credentials.
_RDO_ENV_PATH = Path.home() / ".rdo" / ".env"

# Maximum items to display per section before truncating.
_DISPLAY_HEAD = 25
_DISPLAY_TAIL = 5
_DISPLAY_THRESHOLD = _DISPLAY_HEAD + _DISPLAY_TAIL


def _is_glob(pattern: str) -> bool:
    """Return True if *pattern* contains glob metacharacters."""
    return any(c in pattern for c in "*?[")


def _truncate_id(entity_id: str | int, max_len: int = 8) -> str:
    """Truncate a UUID string to *max_len* chars; integers pass through as-is."""
    if isinstance(entity_id, int):
        return str(entity_id)
    s = str(entity_id)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


@dataclass
class DeletionPlan:
    """Holds everything that will be deleted, organized by backend."""

    matched_episodes: list[str] = field(default_factory=list)

    kitsu_episodes: list[dict] = field(default_factory=list)
    kitsu_sequences: list[dict] = field(default_factory=list)
    kitsu_shots: list[dict] = field(default_factory=list)

    shotgrid_scenes: list[dict] = field(default_factory=list)
    shotgrid_sequences: list[dict] = field(default_factory=list)
    shotgrid_shots: list[dict] = field(default_factory=list)
    shotgrid_versions: list[dict] = field(default_factory=list)
    shotgrid_tasks: list[dict] = field(default_factory=list)

    ayon_folders: list[dict] = field(default_factory=list)

    storage_paths: list[Path] = field(default_factory=list)
    storage_total_bytes: int = 0

    errors: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Return True if nothing was found to delete across all backends."""
        return not any([
            self.kitsu_episodes,
            self.kitsu_sequences,
            self.kitsu_shots,
            self.shotgrid_scenes,
            self.shotgrid_sequences,
            self.shotgrid_shots,
            self.shotgrid_versions,
            self.shotgrid_tasks,
            self.ayon_folders,
            self.storage_paths,
        ])


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
    """Add rows to a Rich table, truncating if there are too many items.

    When the item count exceeds ``_DISPLAY_THRESHOLD``, shows the first
    ``_DISPLAY_HEAD`` rows, a separator indicating how many were omitted,
    and the last ``_DISPLAY_TAIL`` rows.

    Args:
        table: The Rich table to add rows to.
        items: List of tuples, each tuple is one row's column values.
        total_label: Label for the summary row (e.g. "Total episodes").
    """
    if len(items) > _DISPLAY_THRESHOLD:
        for row in items[:_DISPLAY_HEAD]:
            table.add_row(*row)
        omitted = len(items) - _DISPLAY_HEAD - _DISPLAY_TAIL
        # Build a separator row with the right number of columns.
        ncols = len(items[0]) if items else 1
        sep = ("...",) + (f"... and {omitted} more ...",) + ("",) * (ncols - 2)
        table.add_row(*sep, style="dim")
        for row in items[-_DISPLAY_TAIL:]:
            table.add_row(*row)
    else:
        for row in items:
            table.add_row(*row)

    # Summary footer.
    ncols = len(items[0]) if items else 1
    footer = (f"[bold]{total_label}: {len(items)}[/]",) + ("",) * (ncols - 1)
    table.add_row(*footer, end_section=True)


class EpisodeCleanup:
    """Orchestrates deletion of an episode and all its children across multiple backends."""

    def __init__(
        self,
        project_name: str,
        episode_name: str,
        console: Console,
        *,
        skip_kitsu: bool = False,
        skip_shotgrid: bool = False,
        skip_ayon: bool = False,
        skip_storage: bool = False,
        use_test_server: bool = False,
    ) -> None:
        self._project_name = project_name
        self._pattern = episode_name
        self._console = console
        self._skip_kitsu = skip_kitsu
        self._skip_shotgrid = skip_shotgrid
        self._skip_ayon = skip_ayon
        self._skip_storage = skip_storage
        self._use_test_server = use_test_server

    # ------------------------------------------------------------------
    # Credential helpers
    # ------------------------------------------------------------------

    def _get_kitsu_creds(self) -> tuple[str | None, str | None]:
        """Return (host, token) for Kitsu based on server mode."""
        load_dotenv(_RDO_ENV_PATH)
        if self._use_test_server:
            host = os.environ.get("RDO_KITSU_TEST_HOST")
            token = os.environ.get("RDO_KITSU_TEST_API_TOKEN")
        else:
            host = os.environ.get("RDO_KITSU_HOST")
            token = os.environ.get("RDO_KITSU_API_TOKEN")
        return host, token

    def _get_shotgrid_creds(self) -> tuple[str | None, str | None, str | None]:
        """Return (url, script_name, api_key) for ShotGrid.

        ShotGrid has no separate test server; only the project differs.
        """
        load_dotenv(_RDO_ENV_PATH)
        sg_url = os.environ.get("SHOTGRID_SERVER_URL")
        sg_script = os.environ.get("SHOTGRID_SCRIPT")
        sg_key = os.environ.get("SHOTGRID_API_KEY")
        return sg_url, sg_script, sg_key

    def _get_ayon_creds(self) -> tuple[str | None, str | None]:
        """Return (server_url, api_key) for AYON based on server mode."""
        load_dotenv(_RDO_ENV_PATH)
        if self._use_test_server:
            server_url = os.environ.get("AYON_TEST_SERVER_URL")
            api_key = os.environ.get("AYON_TEST_API_KEY")
        else:
            server_url = os.environ.get("AYON_SERVER_URL")
            api_key = os.environ.get("AYON_API_KEY")
        return server_url, api_key

    def _setup_ayon_connection(self, server_url: str, api_key: str) -> None:
        """Set AYON env vars and create the connection if needed."""
        import ayon_api

        os.environ["AYON_SERVER_URL"] = server_url
        os.environ["AYON_API_KEY"] = api_key

        if not ayon_api.is_connection_created():
            ayon_api.create_connection()

    # ------------------------------------------------------------------
    # Episode resolution
    # ------------------------------------------------------------------

    def _resolve_episodes(self) -> list[str]:
        """Resolve the pattern to a list of matching episode names.

        When the pattern is an exact name (no glob chars), returns it as-is
        to avoid fetching all episodes from every backend.  When it contains
        glob metacharacters, queries each enabled backend for all episodes
        and returns the union of names that match.
        """
        if not _is_glob(self._pattern):
            return [self._pattern]

        self._console.print(f"[dim]Resolving glob pattern: {self._pattern}[/]")
        matched: set[str] = set()

        if not self._skip_kitsu:
            matched.update(self._resolve_kitsu_episodes())
        if not self._skip_shotgrid:
            matched.update(self._resolve_shotgrid_episodes())
        if not self._skip_ayon:
            matched.update(self._resolve_ayon_episodes())

        result = sorted(matched)
        if result:
            self._console.print(
                f"[bold]Matched {len(result)} episode(s):[/] {', '.join(result)}"
            )
        else:
            self._console.print("[yellow]No episodes matched the pattern.[/]")
        return result

    def _resolve_kitsu_episodes(self) -> list[str]:
        """Fetch all Kitsu episodes and return names matching the pattern."""
        try:
            import gazu
        except ImportError:
            _log.debug("gazu not installed, skipping Kitsu episode resolution")
            return []

        try:
            host, token = self._get_kitsu_creds()
            if not host or not token:
                return []

            gazu.set_host(host + "/api")
            gazu.set_token(token)

            project = gazu.project.get_project_by_name(self._project_name)
            if not project:
                return []

            all_episodes = gazu.shot.all_episodes_for_project(project)
            return [
                ep["name"]
                for ep in all_episodes
                if fnmatch.fnmatch(ep.get("name", ""), self._pattern)
            ]
        except Exception as exc:  # gazu raises varied exception types
            _log.warning("Kitsu episode resolution failed: %s", exc)
            return []

    def _resolve_shotgrid_episodes(self) -> list[str]:
        """Fetch all ShotGrid scenes and return codes matching the pattern."""
        try:
            import shotgun_api3
        except ImportError:
            _log.debug("shotgun_api3 not installed, skipping ShotGrid episode resolution")
            return []

        try:
            sg_url, sg_script, sg_key = self._get_shotgrid_creds()
            if not sg_url or not sg_script or not sg_key:
                return []

            sg = shotgun_api3.Shotgun(sg_url, script_name=sg_script, api_key=sg_key)

            project = sg.find_one("Project", [["name", "is", self._project_name]])
            if not project:
                return []

            scenes = sg.find("Scene", [["project", "is", project]], ["code"])
            return [
                s["code"]
                for s in scenes
                if fnmatch.fnmatch(s.get("code", ""), self._pattern)
            ]
        except Exception as exc:  # shotgun_api3 raises varied exception types
            _log.warning("ShotGrid episode resolution failed: %s", exc)
            return []

    def _resolve_ayon_episodes(self) -> list[str]:
        """Fetch all AYON episode folders and return names matching the pattern."""
        try:
            import ayon_api
        except ImportError:
            _log.debug("ayon_api not installed, skipping AYON episode resolution")
            return []

        try:
            server_url, api_key = self._get_ayon_creds()
            if not server_url or not api_key:
                return []

            self._setup_ayon_connection(server_url, api_key)

            folders = ayon_api.get_folders(self._project_name, folder_types=["Episode"])
            return [
                f["name"]
                for f in folders
                if fnmatch.fnmatch(f.get("name", ""), self._pattern)
            ]
        except Exception as exc:  # ayon_api raises varied exception types
            _log.warning("AYON episode resolution failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    def plan(self) -> DeletionPlan:
        """Connect to each backend and discover entities to delete (read-only).

        Resolves the episode name/pattern to concrete episode names, then
        plans deletion for each matched episode.

        Returns:
            A ``DeletionPlan`` describing everything that would be removed.
        """
        result = DeletionPlan()
        episodes = self._resolve_episodes()
        result.matched_episodes = episodes

        if not episodes:
            return result

        for ep_name in episodes:
            if not self._skip_kitsu:
                self._plan_kitsu(result, ep_name)
            if not self._skip_shotgrid:
                self._plan_shotgrid(result, ep_name)
            if not self._skip_ayon:
                self._plan_ayon(result, ep_name)
            if not self._skip_storage:
                self._plan_storage(result, ep_name)

        return result

    # -- Kitsu ----------------------------------------------------------

    def _plan_kitsu(self, plan: DeletionPlan, episode_name: str) -> None:
        """Discover Kitsu episode, sequences, and shots."""
        try:
            import gazu
        except ImportError:
            plan.errors.append("Kitsu: gazu not installed -- skipping")
            _log.warning("gazu not installed, skipping Kitsu planning")
            return

        try:
            host, token = self._get_kitsu_creds()
            if not host or not token:
                env_prefix = "RDO_KITSU_TEST_" if self._use_test_server else "RDO_KITSU_"
                plan.errors.append("Kitsu: %sHOST or %sAPI_TOKEN not set" % (env_prefix, env_prefix))
                return

            gazu.set_host(host + "/api")
            gazu.set_token(token)

            self._console.print("[dim]Kitsu: discovering entities for %s...[/]" % episode_name)

            project = gazu.project.get_project_by_name(self._project_name)
            if not project:
                _log.info("Kitsu: project %s not found", self._project_name)
                return

            episode = gazu.shot.get_episode_by_name(project, episode_name)
            if not episode:
                _log.info("Kitsu: episode %s not found in project %s", episode_name, self._project_name)
                return

            plan.kitsu_episodes.append(episode)
            sequences = gazu.shot.all_sequences_for_episode(episode)
            plan.kitsu_sequences.extend(sequences)

            for seq in sequences:
                shots = gazu.shot.all_shots_for_sequence(seq)
                plan.kitsu_shots.extend(shots)

            _log.info(
                "Kitsu plan for %s: 1 episode, %d sequences, %d shots",
                episode_name,
                len(sequences),
                len(shots) if sequences else 0,
            )
        except Exception as exc:  # gazu raises varied exception types
            msg = f"Kitsu: connection/discovery failed for {episode_name} -- {exc}"
            plan.errors.append(msg)
            _log.warning(msg)

    # -- ShotGrid -------------------------------------------------------

    def _plan_shotgrid(self, plan: DeletionPlan, episode_name: str) -> None:
        """Discover ShotGrid scene, sequences, shots, tasks, and versions."""
        try:
            import shotgun_api3
        except ImportError:
            plan.errors.append("ShotGrid: shotgun_api3 not installed -- skipping")
            _log.warning("shotgun_api3 not installed, skipping ShotGrid planning")
            return

        try:
            sg_url, sg_script, sg_key = self._get_shotgrid_creds()
            if not sg_url or not sg_script or not sg_key:
                plan.errors.append("ShotGrid: SHOTGRID_SERVER_URL, SHOTGRID_SCRIPT, or SHOTGRID_API_KEY not set")
                return

            sg = shotgun_api3.Shotgun(sg_url, script_name=sg_script, api_key=sg_key)

            self._console.print("[dim]ShotGrid: discovering entities for %s...[/]" % episode_name)

            project = sg.find_one("Project", [["name", "is", self._project_name]])
            if not project:
                _log.info("ShotGrid: project %s not found", self._project_name)
                return

            scene = sg.find_one("Scene", [["project", "is", project], ["code", "is", episode_name]])
            if not scene:
                _log.info("ShotGrid: scene %s not found in project %s", episode_name, self._project_name)
                return

            plan.shotgrid_scenes.append(scene)

            sequences = sg.find(
                "Sequence",
                [["project", "is", project], ["sg_episode", "is", scene]],
                ["code"],
            )
            plan.shotgrid_sequences.extend(sequences)

            # Find shots via two paths: through sequence link AND direct scene link.
            # Some shots may be linked to the scene directly without a sequence.
            shots_via_seq = (
                sg.find(
                    "Shot",
                    [["project", "is", project], ["sg_sequence", "in", sequences]],
                    ["code"],
                )
                if sequences
                else []
            )
            shots_via_scene = sg.find(
                "Shot",
                [["project", "is", project], ["sg_scene", "is", scene]],
                ["code"],
            )
            # Merge, deduplicate by id
            seen_ids: set[int] = set()
            shots: list[dict] = []
            for sh in shots_via_seq + shots_via_scene:
                if sh["id"] not in seen_ids:
                    seen_ids.add(sh["id"])
                    shots.append(sh)
            plan.shotgrid_shots.extend(shots)

            if shots:
                tasks = sg.find(
                    "Task",
                    [["project", "is", project], ["entity", "in", shots]],
                    ["content"],
                )
                plan.shotgrid_tasks.extend(tasks)

                versions = sg.find(
                    "Version",
                    [["project", "is", project], ["entity", "in", shots]],
                    ["code"],
                )
                plan.shotgrid_versions.extend(versions)

            _log.info(
                "ShotGrid plan for %s: 1 scene, %d sequences, %d shots",
                episode_name,
                len(sequences),
                len(plan.shotgrid_shots),
            )
        except Exception as exc:  # shotgun_api3 raises varied exception types
            msg = f"ShotGrid: connection/discovery failed for {episode_name} -- {exc}"
            plan.errors.append(msg)
            _log.warning(msg)

    # -- AYON -----------------------------------------------------------

    def _plan_ayon(self, plan: DeletionPlan, episode_name: str) -> None:
        """Discover AYON episode folder and all descendants."""
        try:
            import ayon_api
        except ImportError:
            plan.errors.append("AYON: ayon_api not installed -- skipping")
            _log.warning("ayon_api not installed, skipping AYON planning")
            return

        try:
            server_url, api_key = self._get_ayon_creds()
            if not server_url or not api_key:
                env_prefix = "AYON_TEST_" if self._use_test_server else "AYON_"
                plan.errors.append("AYON: %sSERVER_URL or %sAPI_KEY not set" % (env_prefix, env_prefix))
                return

            self._setup_ayon_connection(server_url, api_key)

            self._console.print("[dim]AYON: discovering folders for %s...[/]" % episode_name)

            # Try common episode path patterns.
            episode_folder = None
            for path_pattern in (
                f"episodes/{episode_name}",
                f"Episodes/{episode_name}",
                episode_name,
            ):
                episode_folder = ayon_api.get_folder_by_path(self._project_name, path_pattern)
                if episode_folder:
                    break

            if not episode_folder:
                _log.info("AYON: episode folder not found for %s in %s", episode_name, self._project_name)
                return

            # Collect episode + all descendants.
            all_folders = [episode_folder]
            self._collect_ayon_children(ayon_api, self._project_name, episode_folder["id"], all_folders)
            plan.ayon_folders.extend(all_folders)

            _log.info("AYON plan for %s: %d folders (episode + descendants)", episode_name, len(all_folders))
        except Exception as exc:  # ayon_api raises varied exception types
            msg = f"AYON: connection/discovery failed for {episode_name} -- {exc}"
            plan.errors.append(msg)
            _log.warning(msg)

    @staticmethod
    def _collect_ayon_children(
        ayon_api_mod: object,
        project_name: str,
        parent_id: str,
        accumulator: list[dict],
    ) -> None:
        """Recursively collect child folders under a parent."""
        children = ayon_api_mod.get_folders(project_name, parent_ids=[parent_id])  # type: ignore[attr-defined]
        for child in children:
            accumulator.append(child)
            EpisodeCleanup._collect_ayon_children(ayon_api_mod, project_name, child["id"], accumulator)

    # -- NAS storage ----------------------------------------------------

    def _plan_storage(self, plan: DeletionPlan, episode_name: str) -> None:
        """Discover NAS publish directories for the episode.

        Derives the storage root from AYON project anatomy (``work`` root on
        Linux).  Falls back to ``/projects`` if the anatomy lookup fails.
        """
        try:
            root = self._get_storage_root()
            episode_path = root / self._project_name / "episodes" / episode_name
            if not episode_path.exists():
                _log.info("Storage: path %s does not exist", episode_path)
                return

            self._console.print("[dim]Storage: scanning %s ...[/]" % episode_path)

            plan.storage_paths.append(episode_path)
            total = sum(f.stat().st_size for f in episode_path.rglob("*") if f.is_file())
            plan.storage_total_bytes += total

            _log.info("Storage plan for %s: %s at %s", episode_name, _human_size(total), episode_path)
        except Exception as exc:  # filesystem errors
            msg = "Storage: scan failed for %s -- %s" % (episode_name, exc)
            plan.errors.append(msg)
            _log.warning(msg)

    def _get_storage_root(self) -> Path:
        """Resolve the NAS project root from AYON anatomy or fall back to /projects."""
        try:
            import ayon_api

            response = ayon_api.get("projects/%s/anatomy" % self._project_name)
            roots = response.data.get("roots", [])
            for r in roots:
                if r.get("name") == "work" and r.get("linux"):
                    return Path(r["linux"])
            # Fallback: use the first root with a linux path
            for r in roots:
                if r.get("linux"):
                    return Path(r["linux"])
        except Exception:  # AYON unavailable or anatomy lookup failed
            _log.debug("Could not resolve storage root from AYON anatomy, using /projects")
        return Path("/projects")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def display_plan(self, plan: DeletionPlan) -> None:
        """Print a Rich summary of the deletion plan with per-item detail."""
        if plan.errors:
            for err in plan.errors:
                self._console.print(f"[yellow]WARNING: {err}[/]")
            self._console.print()

        if plan.is_empty:
            self._console.print("[dim]Nothing found to delete.[/]")
            return

        # Show matched episodes header.
        if plan.matched_episodes:
            count = len(plan.matched_episodes)
            names = ", ".join(plan.matched_episodes)
            self._console.print(
                f"\n[bold]Matched {count} episode(s):[/] {names}\n"
            )

        # Kitsu
        kitsu_items = plan.kitsu_episodes or plan.kitsu_sequences or plan.kitsu_shots
        if kitsu_items:
            table = Table(title="Kitsu", show_header=True, header_style="bold cyan")
            table.add_column("Type", style="cyan")
            table.add_column("Name")
            table.add_column("ID", style="dim")

            rows: list[tuple[str, str, str]] = []
            for e in plan.kitsu_episodes:
                rows.append(("Episode", e.get("name", ""), _truncate_id(e.get("id", ""))))
            for s in plan.kitsu_sequences:
                rows.append(("Sequence", s.get("name", ""), _truncate_id(s.get("id", ""))))
            for s in plan.kitsu_shots:
                rows.append(("Shot", s.get("name", ""), _truncate_id(s.get("id", ""))))

            _add_rows_with_truncation(table, rows, "Total Kitsu entities")
            self._console.print(Panel(table, border_style="cyan"))

        # ShotGrid
        sg_items = (
            plan.shotgrid_scenes
            or plan.shotgrid_sequences
            or plan.shotgrid_shots
            or plan.shotgrid_versions
            or plan.shotgrid_tasks
        )
        if sg_items:
            table = Table(title="ShotGrid", show_header=True, header_style="bold magenta")
            table.add_column("Type", style="magenta")
            table.add_column("Name")
            table.add_column("ID", style="dim")

            rows = []
            for s in plan.shotgrid_scenes:
                rows.append(("Scene", s.get("code", ""), _truncate_id(s.get("id", ""))))
            for s in plan.shotgrid_sequences:
                rows.append(("Sequence", s.get("code", ""), _truncate_id(s.get("id", ""))))
            for s in plan.shotgrid_shots:
                rows.append(("Shot", s.get("code", ""), _truncate_id(s.get("id", ""))))
            for v in plan.shotgrid_versions:
                rows.append(("Version", v.get("code", ""), _truncate_id(v.get("id", ""))))
            for t in plan.shotgrid_tasks:
                rows.append(("Task", t.get("content", ""), _truncate_id(t.get("id", ""))))

            _add_rows_with_truncation(table, rows, "Total ShotGrid entities")
            self._console.print(Panel(table, border_style="magenta"))

        # AYON
        if plan.ayon_folders:
            table = Table(title="AYON", show_header=True, header_style="bold green")
            table.add_column("Type", style="green")
            table.add_column("Path")
            table.add_column("ID", style="dim")

            rows = []
            for f in plan.ayon_folders:
                rows.append(("Folder", f.get("path", f.get("name", "")), _truncate_id(f.get("id", ""))))

            _add_rows_with_truncation(table, rows, "Total AYON folders")
            self._console.print(Panel(table, border_style="green"))

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

    def execute(self, plan: DeletionPlan) -> None:
        """Perform the actual deletions described by *plan*.

        Deletions proceed in dependency-safe order within each backend.
        Errors on individual entities are logged but do not abort the run.
        """
        if not self._skip_kitsu and plan.kitsu_episodes:
            self._execute_kitsu(plan)
        if not self._skip_shotgrid and plan.shotgrid_scenes:
            self._execute_shotgrid(plan)
        if not self._skip_ayon and plan.ayon_folders:
            self._execute_ayon(plan)
        if not self._skip_storage and plan.storage_paths:
            self._execute_storage(plan)

    # -- Kitsu ----------------------------------------------------------

    def _execute_kitsu(self, plan: DeletionPlan) -> None:
        import gazu

        self._console.print("[bold cyan]Deleting from Kitsu...[/]")

        # Shots first, then sequences, then episodes.
        for shot in plan.kitsu_shots:
            try:
                gazu.shot.remove_shot(shot, force=True)
                _log.info("Kitsu: deleted shot %s", shot.get("name", shot.get("id")))
            except Exception as exc:  # gazu raises varied types on delete failure
                _log.warning("Kitsu: failed to delete shot %s -- %s", shot.get("id"), exc)

        for seq in plan.kitsu_sequences:
            try:
                gazu.shot.remove_sequence(seq)
                _log.info("Kitsu: deleted sequence %s", seq.get("name", seq.get("id")))
            except Exception as exc:  # gazu raises varied types on delete failure
                _log.warning("Kitsu: failed to delete sequence %s -- %s", seq.get("id"), exc)

        for episode in plan.kitsu_episodes:
            try:
                gazu.shot.remove_episode(episode)
                _log.info("Kitsu: deleted episode %s", episode.get("name"))
            except Exception as exc:  # gazu raises varied types on delete failure
                _log.warning("Kitsu: failed to delete episode %s -- %s", episode.get("id"), exc)

        self._console.print("[green]Kitsu cleanup done.[/]")

    # -- ShotGrid -------------------------------------------------------

    def _execute_shotgrid(self, plan: DeletionPlan) -> None:
        import shotgun_api3

        sg_url, sg_script, sg_key = self._get_shotgrid_creds()
        sg = shotgun_api3.Shotgun(sg_url, script_name=sg_script, api_key=sg_key)

        self._console.print("[bold magenta]Deleting from ShotGrid...[/]")

        # Order: versions -> tasks -> shots -> sequences -> scenes
        batch: list[dict] = []
        for v in plan.shotgrid_versions:
            batch.append({"request_type": "delete", "entity_type": "Version", "entity_id": v["id"]})
        for t in plan.shotgrid_tasks:
            batch.append({"request_type": "delete", "entity_type": "Task", "entity_id": t["id"]})
        for s in plan.shotgrid_shots:
            batch.append({"request_type": "delete", "entity_type": "Shot", "entity_id": s["id"]})
        for seq in plan.shotgrid_sequences:
            batch.append({"request_type": "delete", "entity_type": "Sequence", "entity_id": seq["id"]})
        for scene in plan.shotgrid_scenes:
            batch.append({"request_type": "delete", "entity_type": "Scene", "entity_id": scene["id"]})

        if batch:
            try:
                sg.batch(batch)
                _log.info("ShotGrid: batch-deleted %d entities", len(batch))
            except Exception as exc:  # shotgun_api3 batch can raise on partial failure
                _log.warning("ShotGrid: batch delete error -- %s", exc)

        self._console.print("[green]ShotGrid cleanup done.[/]")

    # -- AYON -----------------------------------------------------------

    def _execute_ayon(self, plan: DeletionPlan) -> None:
        import ayon_api

        self._console.print("[bold green]Deleting from AYON...[/]")

        proj = self._project_name

        # Only delete top-level episode folders with force=True.
        # force=True cascades: AYON deletes all child folders, products,
        # versions, representations, and tasks in a single server-side
        # operation -- no need for per-entity teardown.
        episode_folders = [
            f for f in plan.ayon_folders
            if f.get("folderType") == "Episode"
            or f.get("parentId") is None
            or "/episodes/" in f.get("path", "") and f.get("path", "").count("/") == 2
        ]

        # Fallback: if we can't identify episode-level folders, just delete
        # leaf-first with force=True on each.
        targets = episode_folders if episode_folders else reversed(plan.ayon_folders)

        for folder in targets:
            fid = folder["id"]
            fname = folder.get("name", fid)
            try:
                ayon_api.delete_folder(proj, fid, force=True)
                _log.info("AYON: deleted folder %s and all children (%s)", fname, fid)
            except Exception as exc:  # ayon_api raises varied types on delete failure
                _log.warning("AYON: failed to delete folder %s -- %s", fid, exc)

        self._console.print("[green]AYON cleanup done.[/]")

    # -- Storage --------------------------------------------------------

    def _execute_storage(self, plan: DeletionPlan) -> None:
        self._console.print("[bold red]Deleting NAS storage...[/]")

        trash_bin = shutil.which("trash")

        for path in plan.storage_paths:
            try:
                if trash_bin:
                    import subprocess

                    subprocess.run([trash_bin, str(path)], check=True)  # noqa: S603
                    _log.info("Storage: trashed %s", path)
                else:
                    shutil.rmtree(path)
                    _log.info("Storage: removed %s", path)
            except Exception as exc:  # filesystem/subprocess errors
                _log.warning("Storage: failed to remove %s -- %s", path, exc)

        self._console.print("[green]Storage cleanup done.[/]")
