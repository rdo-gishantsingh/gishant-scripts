"""Unified YouTrack CLI tool for creating, fetching, and updating issues.

This module provides the Typer CLI commands that delegate to the creator,
fetcher, and updater modules for YouTrack issue management.
"""

from __future__ import annotations

import enum
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel


# --- CLI Setup ---

app = typer.Typer(help="YouTrack CLI tool")


@app.command()
def create(
    project: str = typer.Argument(..., help="Project short name (e.g., PIPE)"),
    summary: str = typer.Argument(..., help="Issue summary (max 255 characters)"),
    description: str | None = typer.Option(None, "--description", "-d", help="Issue description"),
    issue_type: str | None = typer.Option(None, "--type", "-t", help="Issue type (Bug, Feature, Task, etc.)"),
    priority: str | None = typer.Option(None, "--priority", "-p", help="Priority (Critical, Major, Normal, Minor)"),
    assignee: str | None = typer.Option(None, "--assignee", "-a", help="Assignee login name"),
    submitted_for: str | None = typer.Option(None, "--submitted-for", "-s", help="Submitted for user full name"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Validate without creating (default: True)"),
):
    """Create a new YouTrack issue."""
    from gishant_scripts._core.config import AppConfig
    from gishant_scripts._core.errors import ConfigurationError
    from gishant_scripts.youtrack.creator import YouTrackIssueCreator

    console = Console()
    try:
        config = AppConfig()
        config.require_valid("youtrack")
    except ConfigurationError as err:
        console.print(f"[red]❌ Configuration Error:[/red] {err}")
        return

    if not config.youtrack.url or not config.youtrack.api_token:
        console.print("[red]✖ Missing YouTrack URL or API token in configuration[/red]")
        raise typer.Exit(1)

    creator = YouTrackIssueCreator(config.youtrack.url, config.youtrack.api_token)
    try:
        result = creator.create_issue(
            project=project,
            summary=summary,
            description=description,
            issue_type=issue_type,
            priority=priority,
            assignee=assignee,
            submitted_for=submitted_for,
            dry_run=dry_run,
        )
        if dry_run:
            creator.print_dry_run_result(result)
        else:
            creator.print_created_issue(result)
    except Exception as err:
        console.print(f"[red]❌ Error:[/red] {err}")
        raise typer.Exit(1)


@app.command()
def fetch(
    issue_id: str | None = typer.Option(None, "--id", help="Fetch a specific issue by ID (e.g., PIPE-1234)"),
    summary: bool = typer.Option(False, "--summary", help="Show only key fields"),
    show_description: bool = typer.Option(False, "--description", help="Show only the description"),
    comments: bool = typer.Option(False, "--comments", help="Show only the comments"),
    max_results: int = typer.Option(100, "--max-results", help="Maximum number of issues to fetch"),
    save_json: bool = typer.Option(False, "--save-json", help="Save results to JSON file"),
):
    """Fetch YouTrack issues or a specific issue."""
    from gishant_scripts._core.config import AppConfig
    from gishant_scripts._core.errors import ConfigurationError
    from gishant_scripts.youtrack.fetcher import YouTrackIssuesFetcher

    console = Console()
    try:
        config = AppConfig()
        config.require_valid("youtrack")
    except ConfigurationError as err:
        console.print(f"[red]❌ Configuration Error:[/red] {err}")
        return

    if not config.youtrack.url or not config.youtrack.api_token:
        console.print("[red]✖ Missing YouTrack URL or API token in configuration[/red]")
        raise typer.Exit(1)

    fetcher = YouTrackIssuesFetcher(config.youtrack.url, config.youtrack.api_token)
    try:
        if issue_id:
            console.print(f"[cyan]Fetching issue:[/cyan] {issue_id}")
            issue = fetcher.fetch_issue_by_id(issue_id)

            show_fields = []
            if summary:
                show_fields.append("summary")
            if show_description:
                show_fields.append("description")
            if comments:
                show_fields.append("comments")

            fetcher.print_issue(issue, show_fields or None)
            if save_json:
                fetcher.save_to_json([issue], f"{issue_id.replace('-', '_')}.json")
            return

        console.print("[cyan]Fetching detailed issue information...[/cyan]")
        issues = fetcher.fetch_issues_with_details(max_results=max_results)
        fetcher.print_results(issues)
        if save_json:
            fetcher.save_to_json(issues)
    except Exception as err:
        console.print(f"[red]❌ Error:[/red] {err}")
        raise typer.Exit(1)


@app.command()
def update(
    issue_id: str = typer.Argument(..., help="Issue ID (e.g., PIPE-671)"),
    comment: str | None = typer.Option(None, "--comment", "-c", help="Add a comment"),
    summary: str | None = typer.Option(None, "--summary", "-s", help="Update summary"),
    description: str | None = typer.Option(None, "--description", "-d", help="Update description"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Validate without updating (default: True)"),
):
    """Update a YouTrack issue."""
    from gishant_scripts._core.config import AppConfig
    from gishant_scripts._core.errors import ConfigurationError
    from gishant_scripts.youtrack.updater import YouTrackIssueUpdater

    console = Console()
    try:
        config = AppConfig()
        config.require_valid("youtrack")
    except ConfigurationError as err:
        console.print(f"[red]❌ Configuration Error:[/red] {err}")
        return

    updater = YouTrackIssueUpdater(config.youtrack.url, config.youtrack.api_token)
    try:
        if summary or description:
            result = updater.update_fields(issue_id, summary=summary, description=description, dry_run=dry_run)
            if dry_run:
                updater.print_dry_run_result(result)
            else:
                updater.print_success_result(result)

        if comment:
            result = updater.post_comment(issue_id, comment, dry_run=dry_run)
            if dry_run:
                updater.print_dry_run_result(result)
            else:
                updater.print_success_result(result)

        if not (comment or summary or description):
            console.print("[yellow]No update action specified. Use --comment, --summary, or --description.[/yellow]")
    except Exception as err:
        console.print(f"[red]❌ Error:[/red] {err}")
        raise typer.Exit(1)


class YTSummaryModel(enum.StrEnum):
    """Gemini model for YouTrack summary generation."""

    flash_25 = "gemini-2.5-flash"
    pro_25 = "gemini-2.5-pro"
    flash_exp = "gemini-2.0-flash-exp"


@app.command()
def summary(
    weeks: Annotated[
        int,
        typer.Option("--weeks", help="Number of weeks to look back for issues"),
    ],
    model: Annotated[
        YTSummaryModel,
        typer.Option("--model", help="Gemini model to use for generation"),
    ] = YTSummaryModel.flash_25,
    save_to_file: Annotated[
        Path | None,
        typer.Option("--save-to-file", help="Save output to specified file"),
    ] = None,
    max_issues: Annotated[
        int,
        typer.Option("--max-issues", help="Maximum number of issues to fetch"),
    ] = 100,
) -> None:
    """Generate work summary from YouTrack issues using Gemini AI.

    Fetches issues where you are involved (assigned or commented) from the last N weeks
    and generates a structured summary with Done/Current Work/Pending/Blockers sections.

    Requires YOUTRACK_URL, YOUTRACK_API_TOKEN, and GOOGLE_AI_API_KEY in environment.
    """
    from gishant_scripts.youtrack.fetcher import YouTrackIssuesFetcher

    console = Console()

    try:
        from gishant_scripts._core.config import AppConfig, ConfigurationError
        from gishant_scripts.youtrack.generate_work_summary import (
            filter_issues_by_time,
            generate_work_summary_with_gemini,
            prepare_issues_for_summary,
        )

        console.print(
            Panel.fit(
                f"[bold cyan]YouTrack Work Summary Generator[/bold cyan]\n"
                f"Time period: Last {weeks} weeks\n"
                f"Model: {model.value}",
                border_style="cyan",
            )
        )

        app_config = AppConfig()
        app_config.require_valid("youtrack", "google_ai")

        console.print("\n[cyan]Step 1: Connecting to YouTrack...[/cyan]")
        fetcher = YouTrackIssuesFetcher(
            base_url=app_config.youtrack.url,
            token=app_config.youtrack.api_token,
        )

        console.print(f"[cyan]Step 2: Fetching issues (max {max_issues})...[/cyan]")
        issues = fetcher.fetch_issues_with_details(max_results=max_issues)

        if not issues:
            console.print("[yellow]No issues found where you are involved.[/yellow]")
            return

        console.print(f"[green]Found {len(issues)} total issues[/green]")

        console.print(f"\n[cyan]Step 3: Filtering issues from last {weeks} weeks...[/cyan]")
        filtered_issues = filter_issues_by_time(issues, weeks)

        if not filtered_issues:
            console.print(f"[yellow]No issues updated in the last {weeks} weeks.[/yellow]")
            return

        console.print("[cyan]Step 4: Preparing data for Gemini...[/cyan]")
        prepared_data = prepare_issues_for_summary(filtered_issues, weeks)

        if prepared_data["total_issues"] == 0:
            console.print(f"[yellow]No issues with activity in the last {weeks} weeks.[/yellow]")
            return

        console.print("\n[cyan]Step 5: Generating work summary with Gemini...[/cyan]")
        summary_text = generate_work_summary_with_gemini(
            data=prepared_data,
            api_key=app_config.google_ai.api_key,
            model=model.value,
        )

        console.print("\n" + "=" * 80)
        console.print(Panel.fit("[bold green]WORK SUMMARY GENERATED[/bold green]", border_style="green"))
        console.print("=" * 80 + "\n")
        console.print(summary_text)
        console.print("\n" + "=" * 80)

        if save_to_file:
            save_path = save_to_file if save_to_file.is_absolute() else Path.cwd() / save_to_file
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(summary_text)
            console.print(f"\n[green]Saved to: {save_path}[/green]")

        console.print(f"\n[dim]Generated from {prepared_data['total_issues']} issues over {weeks} weeks[/dim]")
        console.print(f"[dim]Model: {model.value}[/dim]")

    except ConfigurationError as e:
        err_console = Console(stderr=True)
        err_console.print(f"\n[bold red]Configuration Error:[/bold red] {e}")
        err_console.print("\n[yellow]Please ensure the following are set in your .env file:[/yellow]")
        err_console.print("  - YOUTRACK_URL")
        err_console.print("  - YOUTRACK_API_TOKEN")
        err_console.print("  - GOOGLE_AI_API_KEY")
        sys.exit(1)

    except Exception as e:
        Console(stderr=True).print(f"\n[bold red]Error:[/bold red] {e}")
        sys.exit(1)


def main():
    app()


if __name__ == "__main__":
    app()
