"""Unified YouTrack CLI tool for creating, fetching, and updating issues.

This module provides the Typer CLI commands that delegate to the creator,
fetcher, and updater modules for YouTrack issue management.
"""

from __future__ import annotations

import enum
import sys
from typing import Annotated

import typer
from rich.console import Console

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

    pro_31 = "gemini-3.1-pro-preview"
    flash_lite_31 = "gemini-3.1-flash-lite-preview"
    pro_3 = "gemini-3-pro-preview"
    flash_3 = "gemini-3-flash-preview"
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
    ] = YTSummaryModel.flash_3,
    save_to_file: Annotated[
        str | None,
        typer.Option("--save-to-file", help="Save output to specified file"),
    ] = None,
    max_issues: Annotated[
        int,
        typer.Option("--max-issues", help="Maximum number of issues to fetch"),
    ] = 100,
) -> None:
    """Generate work summary from YouTrack issues using Gemini AI.

    Delegates to the full generate_work_summary module which provides the Live TUI,
    role filtering, work log integration, and cost analysis.

    Requires YOUTRACK_URL, YOUTRACK_API_TOKEN, and GOOGLE_AI_API_KEY in environment.
    """
    from gishant_scripts.youtrack.generate_work_summary import main as summary_main

    exit_code = summary_main(
        weeks=weeks,
        model=model.value,
        save_to_file=save_to_file,
        max_issues=max_issues,
    )
    if exit_code:
        sys.exit(exit_code)


def main():
    app()


if __name__ == "__main__":
    app()
