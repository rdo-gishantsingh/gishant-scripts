"""Update YouTrack issues via API with dry-run support.

This module provides functionality to update YouTrack issues programmatically
including adding comments and updating fields, with a dry-run mode validation.

SECURITY NOTICE: This module performs WRITE operations (POST requests).
Use with caution and always test with --dry-run first.
"""

import json
from typing import Any

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class YouTrackIssueUpdater:
    """Update YouTrack issues with dry-run support.

    WARNING: This class performs WRITE operations (POST requests).
    Always use dry-run mode first to validate your updates.
    """

    def __init__(self, base_url: str, token: str):
        """Initialize the YouTrack API client.

        Args:
            base_url: Your YouTrack instance URL (e.g., 'https://yourcompany.youtrack.cloud')
            token: Your permanent API token
        """
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.console = Console()

    def get_issue_info(self, issue_id: str) -> dict[str, Any] | None:
        """Get issue information to validate it exists.

        Args:
            issue_id: The issue ID (e.g., 'PIPE-671')

        Returns:
            Issue information dictionary or None if not found
        """
        url = f"{self.base_url}/api/issues/{issue_id}"
        params = {"fields": "id,idReadable,summary,description"}
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return None

    def post_comment(
        self,
        issue_id: str,
        comment: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Post a comment to an issue.

        Args:
            issue_id: The issue ID
            comment: The comment text
            dry_run: If True, validate but don't post

        Returns:
            Result dictionary
        """
        # Validate issue exists
        issue_info = self.get_issue_info(issue_id)
        if not issue_info:
            raise ValueError(f"Issue '{issue_id}' not found or not accessible")

        if dry_run:
            return {
                "dry_run": True,
                "valid": True,
                "action": "post_comment",
                "issue_id": issue_id,
                "issue_summary": issue_info.get("summary"),
                "payload": {"text": comment},
                "message": "✓ Comment is valid and ready to be posted",
            }

        url = f"{self.base_url}/api/issues/{issue_id}/comments"
        payload = {"text": comment}

        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()

        result = response.json()
        return {
            "dry_run": False,
            "updated": True,
            "action": "post_comment",
            "issue_id": issue_id,
            "comment_id": result.get("id"),
            "url": f"{self.base_url}/issue/{issue_id}",
        }

    def print_dry_run_result(self, result: dict[str, Any]):
        """Print dry-run validation results."""
        if not result.get("dry_run"):
            return

        self.console.print()
        self.console.print(Panel.fit("🔍 [bold cyan]DRY RUN MODE[/bold cyan]", border_style="cyan"))
        self.console.print()

        if result.get("valid"):
            self.console.print(f"[green]✓ {result.get('message', 'Validation passed')}[/green]")
            self.console.print()

            table = Table(title=f"Update Details: {result.get('issue_id')}", border_style="cyan")
            table.add_column("Field", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            table.add_row("Issue Summary", result.get("issue_summary", "N/A"))
            table.add_row("Action", result.get("action", "N/A"))

            payload = result.get("payload", {})
            if "text" in payload:
                 table.add_row("Comment", payload["text"])

            self.console.print(table)
            self.console.print()
            self.console.print(
                "[yellow]💡 To actually execute this update, run the command again with --no-dry-run[/yellow]"
            )
        else:
            self.console.print("[red]✗ Validation failed[/red]")

    def print_success_result(self, result: dict[str, Any]):
        """Print success result."""
        if result.get("dry_run"):
            return

        self.console.print()
        self.console.print(
            Panel.fit("✅ [bold green]Update Successful[/bold green]", border_style="green")
        )
        self.console.print(f"Issue: {result.get('issue_id')} updated.")
        self.console.print(f"URL: {result.get('url')}")


app = typer.Typer()


@app.command()
def update(
    issue_id: str = typer.Argument(..., help="Issue ID (e.g., PIPE-671)"),
    comment: str | None = typer.Option(None, "--comment", "-c", help="Add a comment to the issue"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Validate without updating (default: True)"),
):
    """Update a YouTrack issue.

    Currently supports adding comments.
    """
    from gishant_scripts.common.config import AppConfig
    from gishant_scripts.common.errors import ConfigurationError

    console = Console()

    # Load configuration
    try:
        config = AppConfig()
        config.require_valid("youtrack")
    except ConfigurationError as err:
        console.print(f"[red]❌ Configuration Error:[/red] {err}")
        return

    updater = YouTrackIssueUpdater(config.youtrack.url, config.youtrack.api_token)

    try:
        if comment:
            result = updater.post_comment(issue_id, comment, dry_run=dry_run)

            if dry_run:
                updater.print_dry_run_result(result)
            else:
                updater.print_success_result(result)
        else:
            console.print("[yellow]No update action specified. Use --comment to add a comment.[/yellow]")

    except Exception as err:
        console.print(f"[red]❌ Error:[/red] {err}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
