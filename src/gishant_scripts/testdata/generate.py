"""Episode generation orchestrator across Kitsu, ShotGrid, and AYON."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.tree import Tree

_log = logging.getLogger(__name__)

# Default .env location for RDO credentials.
_RDO_ENV_PATH = Path.home() / ".rdo" / ".env"


@dataclass
class GenerationPlan:
    """Describes the episode hierarchy that will be created."""

    episode_name: str
    sequences: list[str] = field(default_factory=list)
    shots: dict[str, list[str]] = field(default_factory=dict)

    @property
    def total_shots(self) -> int:
        """Return the total number of shots across all sequences."""
        return sum(len(s) for s in self.shots.values())


class EpisodeGenerator:
    """Orchestrates creation of an episode hierarchy across multiple backends."""

    def __init__(
        self,
        project_name: str,
        episode_name: str,
        num_sequences: int,
        shots_per_sequence: int,
        *,
        console: Console,
        skip_kitsu: bool = False,
        skip_shotgrid: bool = False,
        skip_ayon: bool = False,
        use_test_server: bool = False,
    ) -> None:
        self._project_name = project_name
        self._episode_name = episode_name
        self._num_sequences = num_sequences
        self._shots_per_seq = shots_per_sequence
        self._console = console
        self._skip_kitsu = skip_kitsu
        self._skip_shotgrid = skip_shotgrid
        self._skip_ayon = skip_ayon
        self._use_test_server = use_test_server

    # ------------------------------------------------------------------
    # Credential helpers (shared pattern with cleanup)
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
        """Return (url, script_name, api_key) for ShotGrid."""
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
    # Planning (pure computation, no API calls)
    # ------------------------------------------------------------------

    def plan(self) -> GenerationPlan:
        """Build the naming hierarchy -- pure computation, no API calls."""
        seq_names = [
            f"{self._episode_name}_sq{(i + 1) * 10:03d}"
            for i in range(self._num_sequences)
        ]
        shots: dict[str, list[str]] = {}
        for seq in seq_names:
            shots[seq] = [
                f"{seq}_sh{(j + 1) * 10:04d}"
                for j in range(self._shots_per_seq)
            ]
        return GenerationPlan(
            episode_name=self._episode_name,
            sequences=seq_names,
            shots=shots,
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def display_plan(self, plan: GenerationPlan) -> None:
        """Show what will be created using a Rich tree."""
        tree = Tree(f"[bold]Episode: {plan.episode_name}[/]")

        for seq_name in plan.sequences:
            seq_branch = tree.add(f"[cyan]{seq_name}[/]")
            shot_list = plan.shots.get(seq_name, [])
            for shot_name in shot_list:
                seq_branch.add(f"[dim]{shot_name}[/]")

        self._console.print(tree)
        self._console.print()

        # Summary line.
        num_seq = len(plan.sequences)
        num_shots = plan.total_shots
        self._console.print(
            f"Total: [bold]1[/] episode, [bold]{num_seq}[/] sequences, [bold]{num_shots}[/] shots"
        )

        # Target indicators.
        kitsu_mark = "[green]yes[/]" if not self._skip_kitsu else "[dim]skip[/]"
        sg_mark = "[green]yes[/]" if not self._skip_shotgrid else "[dim]skip[/]"
        ayon_mark = "[green]yes[/]" if not self._skip_ayon else "[dim]skip[/]"
        self._console.print(
            f"Targets: Kitsu {kitsu_mark}  ShotGrid {sg_mark}  AYON {ayon_mark}"
        )

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self, plan: GenerationPlan) -> None:
        """Create entities in Kitsu, ShotGrid, and AYON."""
        if not self._skip_kitsu:
            self._create_kitsu(plan)
        if not self._skip_shotgrid:
            self._create_shotgrid(plan)
        if not self._skip_ayon:
            self._create_ayon(plan)

    # -- Kitsu ----------------------------------------------------------

    def _create_kitsu(self, plan: GenerationPlan) -> None:
        """Create episode, sequences, and shots in Kitsu."""
        try:
            import gazu
        except ImportError:
            self._console.print("[yellow]Kitsu: gazu not installed -- skipping[/]")
            return

        host, token = self._get_kitsu_creds()
        if not host or not token:
            env_prefix = "RDO_KITSU_TEST_" if self._use_test_server else "RDO_KITSU_"
            self._console.print(
                f"[yellow]Kitsu: {env_prefix}HOST or {env_prefix}API_TOKEN not set -- skipping[/]"
            )
            return

        gazu.set_host(host + "/api")
        gazu.set_token(token)

        self._console.print("[bold cyan]Creating in Kitsu...[/]")

        project = gazu.project.get_project_by_name(self._project_name)
        if not project:
            self._console.print(
                f"[red]Kitsu: project '{self._project_name}' not found[/]"
            )
            return

        episode = gazu.shot.new_episode(project, plan.episode_name)
        _log.info("Kitsu: created episode %s", plan.episode_name)

        for seq_name in plan.sequences:
            sequence = gazu.shot.new_sequence(project, seq_name, episode)
            _log.info("Kitsu: created sequence %s", seq_name)

            for shot_name in plan.shots[seq_name]:
                gazu.shot.new_shot(project, sequence, shot_name)
                _log.info("Kitsu: created shot %s", shot_name)

        self._console.print(
            f"[green]Kitsu: created 1 episode, {len(plan.sequences)} sequences, "
            f"{plan.total_shots} shots[/]"
        )

    # -- ShotGrid -------------------------------------------------------

    def _create_shotgrid(self, plan: GenerationPlan) -> None:
        """Create scene, sequences, and shots in ShotGrid using batch API."""
        try:
            import shotgun_api3
        except ImportError:
            self._console.print("[yellow]ShotGrid: shotgun_api3 not installed -- skipping[/]")
            return

        sg_url, sg_script, sg_key = self._get_shotgrid_creds()
        if not sg_url or not sg_script or not sg_key:
            self._console.print(
                "[yellow]ShotGrid: SHOTGRID_SERVER_URL, SHOTGRID_SCRIPT, or "
                "SHOTGRID_API_KEY not set -- skipping[/]"
            )
            return

        sg = shotgun_api3.Shotgun(sg_url, script_name=sg_script, api_key=sg_key)

        self._console.print("[bold magenta]Creating in ShotGrid...[/]")

        project = sg.find_one("Project", [["name", "is", self._project_name]])
        if not project:
            self._console.print(
                f"[red]ShotGrid: project '{self._project_name}' not found[/]"
            )
            return

        # Create scene (episode equivalent in ShotGrid).
        scene = sg.create("Scene", {"project": project, "code": plan.episode_name})
        _log.info("ShotGrid: created scene %s (id=%s)", plan.episode_name, scene["id"])

        # Batch create sequences.
        seq_batch = [
            {
                "request_type": "create",
                "entity_type": "Sequence",
                "data": {"project": project, "code": name, "sg_episode": scene},
            }
            for name in plan.sequences
        ]
        seq_results = sg.batch(seq_batch)
        _log.info("ShotGrid: batch-created %d sequences", len(seq_results))

        # Batch create shots.
        shot_batch = []
        for seq_result, seq_name in zip(seq_results, plan.sequences):
            for shot_name in plan.shots[seq_name]:
                shot_batch.append({
                    "request_type": "create",
                    "entity_type": "Shot",
                    "data": {
                        "project": project,
                        "code": shot_name,
                        "sg_sequence": seq_result,
                        "sg_scene": scene,
                    },
                })

        if shot_batch:
            sg.batch(shot_batch)
            _log.info("ShotGrid: batch-created %d shots", len(shot_batch))

        self._console.print(
            f"[green]ShotGrid: created 1 scene, {len(plan.sequences)} sequences, "
            f"{plan.total_shots} shots[/]"
        )

    # -- AYON -----------------------------------------------------------

    def _create_ayon(self, plan: GenerationPlan) -> None:
        """Create episode, sequence, and shot folders in AYON.

        AYON requires parent IDs for folder creation, so we create level
        by level: episode first, then sequences, then shots.
        """
        try:
            import ayon_api
        except ImportError:
            self._console.print("[yellow]AYON: ayon_api not installed -- skipping[/]")
            return

        server_url, api_key = self._get_ayon_creds()
        if not server_url or not api_key:
            env_prefix = "AYON_TEST_" if self._use_test_server else "AYON_"
            self._console.print(
                f"[yellow]AYON: {env_prefix}SERVER_URL or {env_prefix}API_KEY not set -- skipping[/]"
            )
            return

        self._setup_ayon_connection(server_url, api_key)

        self._console.print("[bold green]Creating in AYON...[/]")

        # Find the Episodes root folder to use as parent.
        episodes_root = None
        for path_candidate in ("episodes", "Episodes"):
            episodes_root = ayon_api.get_folder_by_path(self._project_name, path_candidate)
            if episodes_root:
                break

        parent_id = episodes_root["id"] if episodes_root else None

        # Create episode folder.
        episode_id = ayon_api.create_folder(
            self._project_name,
            name=plan.episode_name,
            folder_type="Episode",
            parent_id=parent_id,
        )
        _log.info("AYON: created episode folder %s (id=%s)", plan.episode_name, episode_id)

        # Create sequence folders under the episode.
        seq_ids: dict[str, str] = {}
        for seq_name in plan.sequences:
            seq_id = ayon_api.create_folder(
                self._project_name,
                name=seq_name,
                folder_type="Sequence",
                parent_id=episode_id,
            )
            seq_ids[seq_name] = seq_id
            _log.info("AYON: created sequence folder %s (id=%s)", seq_name, seq_id)

        # Create shot folders under respective sequences.
        shot_count = 0
        for seq_name, seq_id in seq_ids.items():
            for shot_name in plan.shots[seq_name]:
                ayon_api.create_folder(
                    self._project_name,
                    name=shot_name,
                    folder_type="Shot",
                    parent_id=seq_id,
                )
                shot_count += 1

        _log.info("AYON: created %d shot folders", shot_count)

        self._console.print(
            f"[green]AYON: created 1 episode, {len(plan.sequences)} sequences, "
            f"{shot_count} shots[/]"
        )
