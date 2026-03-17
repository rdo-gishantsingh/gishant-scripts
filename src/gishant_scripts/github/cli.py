"""GitHub CLI operations."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(help="GitHub operations.")


@app.command(name="fetch-prs")
def fetch_prs(
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Save results to JSON file"),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of PRs to fetch"),
    ] = 100,
) -> None:
    """Fetch GitHub pull requests assigned to the authenticated user."""
    from gishant_scripts.github.fetch_prs import GitHubPRFetcher

    console = Console()

    try:
        fetcher = GitHubPRFetcher()

        if not fetcher.check_gh_cli():
            raise typer.Exit(1)

        fetcher.get_current_user()
        prs = fetcher.fetch_user_prs(limit=limit)

        if not prs:
            console.print("[yellow]No pull requests found.[/yellow]")
            return

        fetcher.print_results(prs)

        if output:
            save_path = output if output.is_absolute() else Path.cwd() / output
            fetcher.save_to_json(prs, str(save_path))
            console.print(f"\n[green]Saved to: {save_path}[/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
