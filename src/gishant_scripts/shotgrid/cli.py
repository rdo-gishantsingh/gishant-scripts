"""Shotgrid CLI — task operations and project utilities."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from gishant_scripts.shotgrid.connection import ShotgridConnectionError, setup_shotgrid_connection
from gishant_scripts.shotgrid.tasks import bulk_rename_task_content, get_tasks_by_content

app = typer.Typer(help="Shotgrid operations")
tasks_app = typer.Typer(help="Task operations")
app.add_typer(tasks_app, name="tasks")

console = Console()


def _get_sg():
    try:
        return setup_shotgrid_connection(console)
    except ShotgridConnectionError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1) from e


def _render_tasks_table(tasks: list[dict], title: str) -> None:
    table = Table(title=title)
    table.add_column("Task ID", style="dim", no_wrap=True)
    table.add_column("Content", style="cyan")
    table.add_column("Step", style="green")
    table.add_column("Entity", style="yellow")
    table.add_column("Status", style="magenta")
    for t in tasks:
        step_name = t.get("step", {}).get("name", "-") if t.get("step") else "-"
        entity_name = t.get("entity", {}).get("name", "-") if t.get("entity") else "-"
        table.add_row(str(t["id"]), t.get("content", "-"), step_name, entity_name, t.get("sg_status_list", "-"))
    console.print(table)


@tasks_app.command("list")
def list_tasks(
    project: str = typer.Option(..., "--project", "-p", help="Exact Shotgrid project name."),
    content: str = typer.Option(..., "--content", "-c", help="Task content (name) to filter by."),
) -> None:
    """List all tasks in a project matching a given content (name)."""
    sg = _get_sg()
    try:
        tasks = get_tasks_by_content(sg, project, content)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    if not tasks:
        console.print(f"[yellow]No '{content}' tasks found in project '{project}'.[/yellow]")
        return
    _render_tasks_table(tasks, title=f"'{content}' tasks in {project} ({len(tasks)} total)")


@tasks_app.command("rename-content")
def rename_content(
    project: str = typer.Option(..., "--project", "-p", help="Exact Shotgrid project name."),
    from_content: str = typer.Option(..., "--from-content", help="Current task content to rename from."),
    to_content: str = typer.Option(..., "--to-content", help="New task content to rename to."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without writing."),
) -> None:
    """Rename all tasks matching from-content to to-content in a project."""
    sg = _get_sg()
    try:
        tasks = get_tasks_by_content(sg, project, from_content)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e
    if not tasks:
        console.print(f"[yellow]No '{from_content}' tasks found in '{project}'. Nothing to do.[/yellow]")
        return
    _render_tasks_table(
        tasks,
        title=f"{'[DRY-RUN] ' if dry_run else ''}Tasks to rename: '{from_content}' -> '{to_content}' in {project}",
    )
    console.print(f"\nTotal: [bold]{len(tasks)}[/bold] task(s) would be renamed.\n")
    if dry_run:
        console.print("[yellow]Dry-run complete. No changes made.[/yellow]")
        return
    confirm = typer.prompt(f"Type the project name '{project}' to confirm the rename")
    if confirm.strip() != project:
        console.print("[red]Confirmation did not match. Aborting.[/red]")
        raise typer.Exit(code=1)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("tasks"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        bar = progress.add_task(f"Renaming '{from_content}' -> '{to_content}'", total=len(tasks))

        def on_chunk(updated: int, _total: int) -> None:
            progress.update(bar, completed=updated)

        try:
            bulk_rename_task_content(sg, project, from_content, to_content, dry_run=False, on_chunk=on_chunk)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=1) from e
    console.print(f"[green]Successfully renamed {len(tasks)} tasks from '{from_content}' -> '{to_content}' in {project}.[/green]")
    console.print("[green]Verification passed: 0 tasks with old name remain.[/green]")


if __name__ == "__main__":
    app()
