"""CLI for test data management -- generate and cleanup."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(name="testdata", help="Test data management -- generate and cleanup.", no_args_is_help=True)
console = Console()

def _check_project(project_name: str) -> None:
    """Abort if project is not in the config allowlist."""
    from gishant_scripts.testdata.config import allowed_project_keys
    allowed = allowed_project_keys()
    if project_name not in allowed:
        console.print(f"[bold red]REFUSED:[/] Project '{project_name}' is not in the config allowlist.")
        console.print(f"Allowed projects: {', '.join(sorted(allowed))}")
        raise typer.Exit(code=1)


def _print_server_mode(test_server: bool) -> None:
    """Display which server mode is active."""
    if test_server:
        console.print("[bold yellow]Server: TEST[/]")
    else:
        console.print("[bold green]Server: PRODUCTION[/] (use --test-server for test servers)")


@app.command("cleanup")
def cleanup_episode(
    episode_name: str = typer.Argument(..., help="Episode name or glob pattern (e.g. p773*, *test*)"),
    project_name: str = typer.Option("SGAYONTEST", "--project", "-p", help="Project name (must be in allowlist)"),
    sequence_patterns: list[str] | None = typer.Option(None, "--sequence", help="Sequence name or glob to delete"),
    shot_patterns: list[str] | None = typer.Option(None, "--shot", help="Shot name or glob to delete"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview deletions (default) or execute them"),
    skip_kitsu: bool = typer.Option(False, help="Skip Kitsu cleanup"),
    skip_shotgrid: bool = typer.Option(False, help="Skip ShotGrid cleanup"),
    skip_ayon: bool = typer.Option(False, help="Skip AYON cleanup"),
    skip_storage: bool = typer.Option(False, help="Skip NAS storage cleanup"),
    test_server: bool = typer.Option(False, "--test-server", help="Use test server env vars instead of production"),
) -> None:
    """Delete selected testdata from Kitsu, ShotGrid, AYON, and NAS.

    Examples:
        gishant testdata cleanup ep_test --sequence '*sq020'
        gishant testdata cleanup ep_test --shot '*_sh0030' --execute

    """
    _check_project(project_name)
    _print_server_mode(test_server)

    from gishant_scripts.testdata.cleanup import EpisodeCleanup
    from gishant_scripts.testdata.config import resolve_project
    from gishant_scripts.testdata.selection import SelectionScope

    project_config = resolve_project(project_name)

    selection_scope = SelectionScope(
        sequence_patterns=sequence_patterns,
        shot_patterns=shot_patterns,
    )

    cleaner = EpisodeCleanup(
        project_name=project_name,
        episode_name=episode_name,
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        skip_storage=skip_storage,
        use_test_server=test_server,
        selection_scope=selection_scope,
        project_config=project_config,
    )

    plan = cleaner.plan()
    cleaner.display_plan(plan)

    if dry_run:
        console.print("\n[bold yellow]DRY RUN -- nothing was deleted. Pass --execute to delete.[/]")
        return

    # Double confirmation for execute mode
    if not typer.confirm(f"\nThis will PERMANENTLY delete all items above from '{project_name}'. Continue?"):
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(code=0)

    cleaner.execute(plan)
    console.print("\n[bold green]Cleanup complete.[/]")


@app.command("generate")
def generate_episode(
    episode_name: str = typer.Argument(..., help="Episode name in lowercase (e.g. ep_test)"),
    project_name: str = typer.Option("SGAYONTEST", "--project", "-p", help="Project name (must be in allowlist)"),
    sequences: int = typer.Option(0, "--sequences", "-s", help="Number of sequences to create"),
    shots_per_sequence: int = typer.Option(0, "--shots", help="Number of shots per sequence"),
    sequence_patterns: list[str] | None = typer.Option(None, "--sequence", help="Sequence name or glob to create"),
    shot_patterns: list[str] | None = typer.Option(None, "--shot", help="Shot name or glob to create"),
    replace_existing: bool = typer.Option(False, "--replace-existing", help="Delete matching existing items before create"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview what would be created"),
    skip_kitsu: bool = typer.Option(False, help="Skip Kitsu creation"),
    skip_shotgrid: bool = typer.Option(False, help="Skip ShotGrid creation"),
    skip_ayon: bool = typer.Option(False, help="Skip AYON creation"),
    test_server: bool = typer.Option(False, "--test-server", help="Use test server env vars"),
) -> None:
    """Create selected testdata across Kitsu, ShotGrid, and AYON.

    Examples:
        gishant testdata generate ep_test --sequences 3 --shots 5
        gishant testdata generate ep_test --sequence '*sq020' --shot '*_sh0030'
        gishant testdata generate ep_test --sequence ep_test_sq020 --replace-existing --execute

    """
    _check_project(project_name)
    _print_server_mode(test_server)

    from gishant_scripts.testdata.cleanup import EpisodeCleanup
    from gishant_scripts.testdata.config import resolve_project
    from gishant_scripts.testdata.generate import EpisodeGenerator
    from gishant_scripts.testdata.selection import SelectionScope

    project_config = resolve_project(project_name)

    selection_scope = SelectionScope(
        sequence_patterns=sequence_patterns,
        shot_patterns=shot_patterns,
    )

    generator = EpisodeGenerator(
        project_name=project_name,
        episode_name=episode_name,
        num_sequences=sequences,
        shots_per_sequence=shots_per_sequence,
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        use_test_server=test_server,
        selection_scope=selection_scope,
        project_config=project_config,
    )
    conflict_cleaner = EpisodeCleanup(
        project_name=project_name,
        episode_name=episode_name,
        console=console,
        skip_kitsu=skip_kitsu,
        skip_shotgrid=skip_shotgrid,
        skip_ayon=skip_ayon,
        skip_storage=False,
        use_test_server=test_server,
        selection_scope=selection_scope,
        project_config=project_config,
    )

    conflict_plan = conflict_cleaner.plan()
    if not conflict_plan.is_empty:
        console.print("\n[bold yellow]Existing matching items found.[/]")
        conflict_cleaner.display_plan(conflict_plan)
        if not replace_existing:
            console.print(
                "\n[bold yellow]Generation stopped. Pass --replace-existing to delete these items before creating.[/]"
            )
            return

    plan = generator.plan()
    generator.display_plan(plan)

    if dry_run:
        console.print("\n[bold yellow]DRY RUN -- nothing was created. Pass --execute to create.[/]")
        return

    # Confirmation for execute mode
    if not typer.confirm(f"\nThis will create all items above in '{project_name}'. Continue?"):
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(code=0)

    if replace_existing and not conflict_plan.is_empty:
        conflict_cleaner.execute(conflict_plan)

    generator.execute(plan)
    console.print("\n[bold green]Generation complete.[/]")


@app.command("remove-projects")
def remove_projects_cmd(
    prefix: str = typer.Option(..., "--prefix", help="Project name prefix (must start with '_')."),
    server: str = typer.Option(..., "--server", help="Target server: kitsu, ayon, or both."),
    env: str = typer.Option("test", "--env", help="Environment: test (default) or prod."),
    dry_run: bool = typer.Option(False, "--dry-run", help="List matches without deleting."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the prod confirmation prompt."),
) -> None:
    """Bulk-remove test projects from Kitsu and/or AYON by name prefix."""
    from gishant_scripts.testdata.remove_projects import remove_projects

    remove_projects(
        prefix=prefix,
        server=server,
        env=env,
        dry_run=dry_run,
        yes=yes,
        console=console,
    )
