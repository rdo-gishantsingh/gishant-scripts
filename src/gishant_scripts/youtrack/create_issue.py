"""Create YouTrack issues via API with dry-run support.

This module provides functionality to create YouTrack issues programmatically
with a dry-run mode for testing and validation before actual creation.

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


class YouTrackIssueCreator:
    """Create YouTrack issues with dry-run support.

    WARNING: This class performs WRITE operations (POST requests).
    Always use dry-run mode first to validate your issue before creation.
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

    def get_project_info(self, project_id: str) -> dict[str, Any] | None:
        """Get project information to validate it exists.

        Args:
            project_id: The project short name (e.g., 'PIPE')

        Returns:
            Project information dictionary or None if not found
        """
        url = f"{self.base_url}/api/admin/projects/{project_id}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return None

    def validate_issue_data(
        self,
        project: str,
        summary: str,
        description: str | None = None,
        issue_type: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
    ) -> tuple[bool, list[str]]:
        """Validate issue data before creation.

        Args:
            project: Project short name
            summary: Issue summary
            description: Issue description
            issue_type: Issue type (e.g., 'Bug', 'Feature', 'Task')
            priority: Priority (e.g., 'Critical', 'Major', 'Normal', 'Minor')
            assignee: Assignee login name

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Validate project exists
        project_info = self.get_project_info(project)
        if not project_info:
            errors.append(f"Project '{project}' not found or not accessible")

        # Validate required fields
        if not summary or not summary.strip():
            errors.append("Summary is required and cannot be empty")

        if summary and len(summary) > 255:
            errors.append(f"Summary too long ({len(summary)} chars, max 255)")

        return len(errors) == 0, errors

    def create_issue(
        self,
        project: str,
        summary: str,
        description: str | None = None,
        issue_type: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        submitted_for: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Create a YouTrack issue.

        Args:
            project: Project short name (e.g., 'PIPE')
            summary: Issue summary (max 255 characters)
            description: Issue description (optional)
            issue_type: Issue type (e.g., 'Bug', 'Feature', 'Task')
            priority: Priority (e.g., 'Critical', 'Major', 'Normal', 'Minor')
            assignee: Assignee login name (optional)
            submitted_for: Submitted for user full name (optional)
            dry_run: If True, validate but don't create the issue

        Returns:
            Dictionary containing the created issue data or validation results

        Raises:
            requests.exceptions.HTTPError: If the API request fails
            ValueError: If validation fails
        """
        # Validate issue data
        is_valid, errors = self.validate_issue_data(
            project=project,
            summary=summary,
            description=description,
            issue_type=issue_type,
            priority=priority,
            assignee=assignee,
        )

        if not is_valid:
            error_msg = "\n".join(f"  • {err}" for err in errors)
            raise ValueError(f"Issue validation failed:\n{error_msg}")

        # Build the issue payload
        payload: dict[str, Any] = {
            "project": {"$type": "Project", "shortName": project},
            "summary": summary,
        }

        # Add optional fields
        custom_fields = []

        if description:
            payload["description"] = description

        if issue_type:
            custom_fields.append({"$type": "SingleEnumIssueCustomField", "name": "Type", "value": {"name": issue_type}})

        if priority:
            custom_fields.append({"$type": "SingleEnumIssueCustomField", "name": "Priority", "value": {"name": priority}})

        if assignee:
            custom_fields.append({"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": assignee}})

        if submitted_for:
            custom_fields.append({"$type": "SingleUserIssueCustomField", "name": "Submitted for", "value": {"login": submitted_for}})

        if custom_fields:
            payload["customFields"] = custom_fields

        # Dry-run mode: just validate and show what would be created
        if dry_run:
            return {
                "dry_run": True,
                "valid": True,
                "payload": payload,
                "message": "✓ Issue is valid and ready to be created",
            }

        # Actually create the issue
        url = f"{self.base_url}/api/issues"
        params = {"fields": "id,idReadable,summary,description,created"}

        response = requests.post(url, headers=self.headers, json=payload, params=params, timeout=30)
        response.raise_for_status()

        issue = response.json()
        return {
            "dry_run": False,
            "created": True,
            "issue": issue,
            "url": f"{self.base_url}/issue/{issue.get('idReadable', '')}",
        }

    def print_dry_run_result(self, result: dict[str, Any]):
        """Print dry-run validation results."""
        if not result.get("dry_run"):
            return

        self.console.print()
        self.console.print(Panel.fit("🔍 [bold cyan]DRY RUN MODE[/bold cyan]", border_style="cyan"))
        self.console.print()

        if result.get("valid"):
            self.console.print("[green]✓ Issue validation passed[/green]")
            self.console.print(f"[dim]{result.get('message', '')}[/dim]")
            self.console.print()

            # Show what would be created
            payload = result.get("payload", {})

            table = Table(title="Issue Details", border_style="cyan")
            table.add_column("Field", style="cyan", no_wrap=True)
            table.add_column("Value", style="white")

            table.add_row("Project", payload.get("project", {}).get("shortName", "N/A"))
            table.add_row("Summary", payload.get("summary", "N/A"))

            if payload.get("description"):
                desc = payload["description"]
                desc_preview = (desc[:100] + "...") if len(desc) > 100 else desc
                table.add_row("Description", desc_preview)

            # Show custom fields
            for field in payload.get("customFields", []):
                field_name = field.get("name", "Unknown")
                field_value = field.get("value", {})

                if "name" in field_value:
                    value = field_value["name"]
                elif "login" in field_value:
                    value = field_value["login"]
                else:
                    value = str(field_value)

                table.add_row(field_name, value)

            self.console.print(table)
            self.console.print()
            self.console.print(
                "[yellow]💡 To actually create this issue, run the command again with --no-dry-run[/yellow]"
            )
        else:
            self.console.print("[red]✗ Issue validation failed[/red]")

    def print_created_issue(self, result: dict[str, Any]):
        """Print created issue information."""
        if result.get("dry_run") or not result.get("created"):
            return

        issue = result.get("issue", {})

        self.console.print()
        self.console.print(
            Panel.fit("✅ [bold green]Issue Created Successfully[/bold green]", border_style="green")
        )
        self.console.print()

        content = []
        content.append(f"[bold]ID:[/bold] {issue.get('idReadable', 'N/A')}")
        content.append(f"[bold]Summary:[/bold] {issue.get('summary', 'N/A')}")
        content.append(f"[bold]Created:[/bold] {issue.get('created', 'N/A')}")
        content.append(f"[bold]URL:[/bold] {result.get('url', 'N/A')}")

        if issue.get("description"):
            desc = issue["description"]
            desc_preview = (desc[:150] + "...") if len(desc) > 150 else desc
            content.append(f"\n[bold]Description:[/bold]\n{desc_preview}")

        panel = Panel(
            "\n".join(content),
            title=f"[bold green]{issue.get('idReadable', 'Issue')}[/bold green]",
            border_style="green",
        )
        self.console.print(panel)


app = typer.Typer()


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
    """Create a new YouTrack issue.

    By default, runs in DRY-RUN mode to validate the issue before creation.
    Use --no-dry-run to actually create the issue.

    Examples:

        # Dry run (validate only)
        create-youtrack-issue PIPE "Fix login bug"

        # Create with description
        create-youtrack-issue PIPE "Add user export" --description "Export users to CSV" --no-dry-run

        # Create with all fields
        create-youtrack-issue PIPE "Critical database issue" \\
            --description "Database connection pool exhausted" \\
            --type Bug \\
            --priority Critical \\
            --assignee john.doe \\
            --no-dry-run
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
        console.print("\n[yellow]💡 Set up your .env file with:[/yellow]")
        console.print("  YOUTRACK_URL=https://your-instance.youtrack.cloud")
        console.print("  YOUTRACK_API_TOKEN=perm-your-token-here")
        console.print("\n[dim]You can copy .env.example to .env and fill in your values.[/dim]")
        raise typer.Exit(1)

    # Initialize the creator
    if not config.youtrack.url or not config.youtrack.api_token:
        console.print("[red]✖ Missing YouTrack URL or API token in configuration[/red]")
        raise typer.Exit(1)

    creator = YouTrackIssueCreator(config.youtrack.url, config.youtrack.api_token)

    try:
        # Create or validate the issue
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

        # Print results
        if dry_run:
            creator.print_dry_run_result(result)
        else:
            creator.print_created_issue(result)

    except ValueError as err:
        console.print("\n[red]❌ Validation Error:[/red]")
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(1)
    except requests.exceptions.HTTPError as err:
        console.print(f"\n[red]❌ HTTP Error:[/red] {err}")
        if hasattr(err, "response") and err.response is not None:
            try:
                error_detail = err.response.json()
                console.print(f"[dim]Details: {json.dumps(error_detail, indent=2)}[/dim]")
            except Exception:
                console.print(f"[dim]Response: {err.response.text}[/dim]")
        raise typer.Exit(1)
    except Exception as err:
        console.print(f"\n[red]❌ Error:[/red] {err}")
        raise typer.Exit(1)


def main():
    """Entry point for the console script."""
    app()


if __name__ == "__main__":
    app()
