"""CLI for the sandbox tool -- generate and cleanup test data."""

from __future__ import annotations

import typer
from rich.console import Console

from sandbox.backends import Environment
from sandbox.cleanup import FolderCleanup, ProjectRemoval, parse_date_window
from sandbox.generate import EpisodeGenerator
from sandbox.selection import SelectionScope

app = typer.Typer(name="sandbox", help="Sandbox test data -- generate and cleanup.", no_args_is_help=True)
console = Console()


def _check_project(project_name: str) -> None:
    """Abort if project is not in the config allowlist."""
    from sandbox.config import allowed_project_keys

    allowed = allowed_project_keys()
    if project_name not in allowed:
        console.print(f"[bold red]REFUSED:[/] Project '{project_name}' is not in the config allowlist.")
        console.print(f"Allowed projects: {', '.join(sorted(allowed))}")
        raise typer.Exit(code=1)


def _print_server_mode(environment: Environment) -> None:
    """Display which server environment is active."""
    if environment.is_test:
        console.print("[bold yellow]Server: TEST[/]")
    else:
        console.print("[bold red]Server: PRODUCTION[/]")


@app.command("cleanup")
def cleanup_cmd(
    path: str | None = typer.Argument(
        None,
        help="AYON path to delete -- supports glob segments (e.g. /assets/vehicles, '/assets/*/car*')",
    ),
    projects: str | None = typer.Option(
        None,
        "--projects",
        help="Glob of whole project names to delete from ALL backends (e.g. '_test*'). Mutually exclusive with PATH.",
    ),
    project_name: str = typer.Option("SGAYONTEST", "--project", "-p", help="Project name for PATH mode (allowlist)"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview deletions (default) or execute them"),
    skip_kitsu: bool = typer.Option(False, help="Skip Kitsu"),
    skip_shotgrid: bool = typer.Option(False, help="Skip ShotGrid"),
    skip_ayon: bool = typer.Option(False, help="Skip AYON"),
    skip_storage: bool = typer.Option(False, help="Skip NAS storage"),
    server: Environment = typer.Option(Environment.TEST, "--server", help="Target environment: test or production"),
    created_after: str | None = typer.Option(
        None,
        "--created-after",
        help="Only delete entities created on/after this date (YYYY-MM-DD or ISO datetime, UTC). PATH mode only.",
    ),
    created_before: str | None = typer.Option(
        None,
        "--created-before",
        help="Only delete entities created on/before this date (YYYY-MM-DD or ISO datetime, UTC). PATH mode only.",
    ),
) -> None:
    """Delete an AYON path (PATH mode) or whole projects (--projects mode) across backends.

    Examples:
        gishant sandbox cleanup /assets/vehicles -p SGAYONTEST
        gishant sandbox cleanup '/assets/*/car*' --execute
        gishant sandbox cleanup '/episodes/hitro104/hitro106*' --created-after 2026-07-09
        gishant sandbox cleanup --projects '_test*' --execute
        gishant sandbox cleanup --projects '_test*' --server production --execute

    Project mode (--projects) matches whole project names independently on each
    backend and deletes them from Kitsu, AYON, ShotGrid, and NAS storage. NAS
    storage is resolved only for matched AYON projects.

    With --created-after/--created-before (PATH mode), the plan is pruned to
    entities whose created_at (NAS: mtime) falls in the inclusive UTC window.
    Out-of-window and undateable entities are preserved. AYON deletion is
    folder-cascade-only, so a folder is deleted only when its whole subtree is
    in-window; otherwise it is kept and only in-window leaves are pruned on
    ShotGrid/Kitsu/NAS.

    """
    if path is not None and projects is not None:
        console.print("[bold red]ERROR:[/] PATH and --projects are mutually exclusive.")
        raise typer.Exit(code=1)
    if path is None and projects is None:
        console.print("[bold red]ERROR:[/] provide a PATH or --projects PATTERN.")
        raise typer.Exit(code=1)
    if projects is not None and (created_after or created_before):
        console.print("[bold red]ERROR:[/] --created-after/--created-before apply to PATH mode only.")
        raise typer.Exit(code=1)

    try:
        date_window = parse_date_window(created_after, created_before)
    except ValueError as exc:
        console.print(f"[bold red]ERROR:[/] {exc}")
        raise typer.Exit(code=1) from exc

    _print_server_mode(server)

    if projects:
        remover = ProjectRemoval(
            pattern=projects,
            console=console,
            skip_kitsu=skip_kitsu,
            skip_shotgrid=skip_shotgrid,
            skip_ayon=skip_ayon,
            skip_storage=skip_storage,
            environment=server,
        )
        plan = remover.plan()
        remover.display_plan(plan)
        if dry_run:
            console.print("\n[bold yellow]DRY RUN -- nothing was deleted. Pass --execute to delete.[/]")
            return
        if not typer.confirm(f"\nThis will PERMANENTLY delete all projects matching '{projects}'. Continue?"):
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(code=0)
        remover.execute(plan)
        console.print("\n[bold green]Project removal complete.[/]")
        return

    # PATH mode
    _check_project(project_name)
    from sandbox.config import resolve_project

    project_config = resolve_project(project_name)
    cleaner = FolderCleanup(
        project_name=project_name,
        path=path,
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        skip_storage=skip_storage,
        environment=server,
        project_config=project_config,
        date_window=date_window,
    )
    plan = cleaner.plan()
    cleaner.display_plan(plan)
    if dry_run:
        console.print("\n[bold yellow]DRY RUN -- nothing was deleted. Pass --execute to delete.[/]")
        return
    if not typer.confirm(f"\nThis will PERMANENTLY delete all items above from '{project_name}'. Continue?"):
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(code=0)
    cleaner.execute(plan)
    console.print("\n[bold green]Cleanup complete.[/]")


@app.command("generate")
def generate_cmd(
    episode_name: str = typer.Argument(..., help="Episode name in lowercase (e.g. ep_test)"),
    project_name: str = typer.Option("SGAYONTEST", "--project", "-p", help="Project name (must be in allowlist)"),
    sequences: int = typer.Option(0, "--sequences", "-s", help="Number of sequences to create"),
    shots_per_sequence: int = typer.Option(0, "--shots", help="Number of shots per sequence"),
    sequence_patterns: list[str] | None = typer.Option(None, "--sequence", help="Sequence name or glob to create"),
    shot_patterns: list[str] | None = typer.Option(None, "--shot", help="Shot name or glob to create"),
    replace_existing: bool = typer.Option(False, "--replace-existing", help="Delete matching existing items first"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview what would be created"),
    skip_kitsu: bool = typer.Option(False, help="Skip Kitsu creation"),
    skip_shotgrid: bool = typer.Option(False, help="Skip ShotGrid creation"),
    skip_ayon: bool = typer.Option(False, help="Skip AYON creation"),
    server: Environment = typer.Option(Environment.TEST, "--server", help="Target environment: test or production"),
) -> None:
    """Create selected sandbox data across Kitsu, ShotGrid, and AYON.

    Examples:
        gishant sandbox generate ep_test --sequences 3 --shots 5
        gishant sandbox generate ep_test --sequence '*sq020' --shot '*_sh0030'

    """
    _check_project(project_name)
    _print_server_mode(server)

    from sandbox.config import resolve_project

    project_config = resolve_project(project_name)
    selection_scope = SelectionScope(sequence_patterns=sequence_patterns, shot_patterns=shot_patterns)

    generator = EpisodeGenerator(
        project_name=project_name,
        episode_name=episode_name,
        num_sequences=sequences,
        shots_per_sequence=shots_per_sequence,
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        environment=server,
        selection_scope=selection_scope,
        project_config=project_config,
    )
    conflict_cleaner = FolderCleanup(
        project_name=project_name,
        path=f"/episodes/{episode_name}",
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        skip_storage=False,
        environment=server,
        project_config=project_config,
    )

    conflict_plan = conflict_cleaner.plan()
    if not conflict_plan.is_empty:
        console.print("\n[bold yellow]Existing matching items found.[/]")
        conflict_cleaner.display_plan(conflict_plan)
        if not replace_existing:
            console.print("\n[bold yellow]Generation stopped. Pass --replace-existing to delete these items first.[/]")
            return

    plan = generator.plan()
    generator.display_plan(plan)
    if dry_run:
        console.print("\n[bold yellow]DRY RUN -- nothing was created. Pass --execute to create.[/]")
        return
    if not typer.confirm(f"\nThis will create all items above in '{project_name}'. Continue?"):
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(code=0)
    if replace_existing and not conflict_plan.is_empty:
        conflict_cleaner.execute(conflict_plan)
    generator.execute(plan)
    console.print("\n[bold green]Generation complete.[/]")


if __name__ == "__main__":
    app()
