"""Episode generation orchestrator across Kitsu, ShotGrid, and AYON."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.tree import Tree

from gishant_scripts.sandbox.backends import (
    AyonBackend,
    BackendUnavailableError,
    Environment,
    KitsuBackend,
    ShotGridBackend,
)
from gishant_scripts.sandbox.selection import SelectionScope

if TYPE_CHECKING:
    from rich.console import Console

    from gishant_scripts.sandbox.config import ProjectConfig

_log = logging.getLogger(__name__)


def _is_glob_pattern(pattern: str) -> bool:
    """Return True when *pattern* contains shell-style glob metacharacters."""
    return any(char in pattern for char in "*?[")


def _sequence_from_shot_name(shot_name: str) -> str | None:
    """Infer the sequence name from a conventional full shot name."""
    if _is_glob_pattern(shot_name) or "_sh" not in shot_name:
        return None
    return shot_name.rsplit("_sh", 1)[0]


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
        environment: Environment = Environment.TEST,
        selection_scope: SelectionScope | None = None,
        project_config: ProjectConfig | None = None,
    ) -> None:
        self._project_name = project_name
        self._episode_name = episode_name
        self._num_sequences = num_sequences
        self._shots_per_seq = shots_per_sequence
        self._console = console
        self._skip_kitsu = skip_kitsu
        self._skip_shotgrid = skip_shotgrid
        self._skip_ayon = skip_ayon
        self._environment = environment
        self._scope = selection_scope or SelectionScope()
        self._kitsu = KitsuBackend(project_name, environment, project_config)
        self._shotgrid = ShotGridBackend(project_name, environment, project_config)
        self._ayon = AyonBackend(project_name, environment, project_config)

    # ------------------------------------------------------------------
    # Planning (pure computation, no API calls)
    # ------------------------------------------------------------------

    def plan(self) -> GenerationPlan:
        """Build the naming hierarchy -- pure computation, no API calls."""
        generated_sequences = [f"{self._episode_name}_sq{(i + 1) * 10:03d}" for i in range(self._num_sequences)]

        seq_names: list[str] = []
        for seq_name in generated_sequences + self._explicit_sequence_names():
            if seq_name in seq_names or not self._scope.matches_sequence(seq_name):
                continue
            seq_names.append(seq_name)

        shots: dict[str, list[str]] = {}
        for seq in seq_names:
            generated_shots = [f"{seq}_sh{(j + 1) * 10:04d}" for j in range(self._shots_per_seq)]
            selected_shots: list[str] = []
            for shot_name in generated_shots + self._explicit_shot_names_for_sequence(seq):
                if shot_name in selected_shots or not self._scope.matches_shot(seq, shot_name):
                    continue
                selected_shots.append(shot_name)

            if self._scope.is_shot_scope and not selected_shots:
                continue

            shots[seq] = selected_shots
        return GenerationPlan(
            episode_name=self._episode_name,
            sequences=list(shots),
            shots=shots,
        )

    def _explicit_sequence_names(self) -> list[str]:
        """Return exact sequence names from selector patterns and exact shots."""
        names: list[str] = []
        for pattern in self._scope.sequence_patterns:
            if _is_glob_pattern(pattern) or pattern in names:
                continue
            names.append(pattern)

        for shot_name in self._scope.shot_patterns:
            seq_name = _sequence_from_shot_name(shot_name)
            if seq_name and seq_name not in names:
                names.append(seq_name)
        return names

    def _explicit_shot_names_for_sequence(self, sequence_name: str) -> list[str]:
        """Return exact shot selector names that belong to *sequence_name*."""
        result: list[str] = []
        for pattern in self._scope.shot_patterns:
            if _is_glob_pattern(pattern):
                continue
            if _sequence_from_shot_name(pattern) == sequence_name:
                result.append(pattern)
        return result

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
        self._console.print(f"Total: [bold]1[/] episode, [bold]{num_seq}[/] sequences, [bold]{num_shots}[/] shots")

        # Target indicators.
        kitsu_mark = "[green]yes[/]" if not self._skip_kitsu else "[dim]skip[/]"
        sg_mark = "[green]yes[/]" if not self._skip_shotgrid else "[dim]skip[/]"
        ayon_mark = "[green]yes[/]" if not self._skip_ayon else "[dim]skip[/]"
        self._console.print(f"Targets: Kitsu {kitsu_mark}  ShotGrid {sg_mark}  AYON {ayon_mark}")

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
            gazu = self._kitsu.connect()
        except BackendUnavailableError as exc:
            self._console.print(f"[yellow]{exc} -- skipping[/]")
            return

        self._console.print("[bold cyan]Creating in Kitsu...[/]")
        project = gazu.project.get_project_by_name(self._kitsu.project_name)
        if not project:
            self._console.print(f"[red]Kitsu: project '{self._kitsu.project_name}' not found[/]")
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
            f"[green]Kitsu: created 1 episode, {len(plan.sequences)} sequences, {plan.total_shots} shots[/]"
        )

    # -- ShotGrid -------------------------------------------------------

    def _create_shotgrid(self, plan: GenerationPlan) -> None:
        """Create scene, sequences, and shots in ShotGrid using batch API."""
        try:
            sg = self._shotgrid.connect()
        except BackendUnavailableError as exc:
            self._console.print(f"[yellow]{exc} -- skipping[/]")
            return

        self._console.print("[bold magenta]Creating in ShotGrid...[/]")
        project = sg.find_one("Project", [["name", "is", self._shotgrid.project_name]])
        if not project:
            self._console.print(f"[red]ShotGrid: project '{self._shotgrid.project_name}' not found[/]")
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
        for seq_result, seq_name in zip(seq_results, plan.sequences, strict=False):
            shot_batch.extend(
                {
                    "request_type": "create",
                    "entity_type": "Shot",
                    "data": {
                        "project": project,
                        "code": shot_name,
                        "sg_sequence": seq_result,
                        "sg_scene": scene,
                    },
                }
                for shot_name in plan.shots[seq_name]
            )

        if shot_batch:
            sg.batch(shot_batch)
            _log.info("ShotGrid: batch-created %d shots", len(shot_batch))

        self._console.print(
            f"[green]ShotGrid: created 1 scene, {len(plan.sequences)} sequences, {plan.total_shots} shots[/]"
        )

    # -- AYON -----------------------------------------------------------

    def _create_ayon(self, plan: GenerationPlan) -> None:
        """Create episode, sequence, and shot folders in AYON.

        AYON requires parent IDs for folder creation, so we create level
        by level: episode first, then sequences, then shots.
        """
        try:
            ayon_api = self._ayon.connect()
        except BackendUnavailableError as exc:
            self._console.print(f"[yellow]{exc} -- skipping[/]")
            return

        self._console.print("[bold green]Creating in AYON...[/]")
        proj = self._ayon.project_name

        # Find the Episodes root folder to use as parent.
        episodes_root = None
        for path_candidate in ("episodes", "Episodes"):
            episodes_root = ayon_api.get_folder_by_path(proj, path_candidate)
            if episodes_root:
                break

        parent_id = episodes_root["id"] if episodes_root else None

        # Create episode folder.
        episode_id = ayon_api.create_folder(
            proj,
            name=plan.episode_name,
            folder_type="Episode",
            parent_id=parent_id,
        )
        _log.info("AYON: created episode folder %s (id=%s)", plan.episode_name, episode_id)

        # Create sequence folders under the episode.
        seq_ids: dict[str, str] = {}
        for seq_name in plan.sequences:
            seq_id = ayon_api.create_folder(
                proj,
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
                    proj,
                    name=shot_name,
                    folder_type="Shot",
                    parent_id=seq_id,
                )
                shot_count += 1

        _log.info("AYON: created %d shot folders", shot_count)

        self._console.print(f"[green]AYON: created 1 episode, {len(plan.sequences)} sequences, {shot_count} shots[/]")
