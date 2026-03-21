"""YouTrack issue creator with dry-run support."""

from __future__ import annotations

from typing import Any

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class YouTrackIssueCreator:
    """Create YouTrack issues with dry-run support."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.console = Console()

    def get_project_info(self, project_id: str) -> dict[str, Any] | None:
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
        errors = []
        project_info = self.get_project_info(project)
        if not project_info:
            errors.append(f"Project '{project}' not found or not accessible")

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

        payload: dict[str, Any] = {
            "project": {"$type": "Project", "shortName": project},
            "summary": summary,
        }

        custom_fields = []
        if description:
            payload["description"] = description
        if issue_type:
            custom_fields.append({"$type": "SingleEnumIssueCustomField", "name": "Type", "value": {"name": issue_type}})
        if priority:
            custom_fields.append(
                {"$type": "SingleEnumIssueCustomField", "name": "Priority", "value": {"name": priority}}
            )
        if assignee:
            custom_fields.append(
                {"$type": "SingleUserIssueCustomField", "name": "Assignee", "value": {"login": assignee}}
            )
        if submitted_for:
            custom_fields.append(
                {"$type": "SingleUserIssueCustomField", "name": "Submitted for", "value": {"login": submitted_for}}
            )

        if custom_fields:
            payload["customFields"] = custom_fields

        if dry_run:
            return {
                "dry_run": True,
                "valid": True,
                "payload": payload,
                "message": "✓ Issue is valid and ready to be created",
            }

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
        if not result.get("dry_run"):
            return
        self.console.print()
        self.console.print(Panel.fit("🔍 [bold cyan]DRY RUN MODE[/bold cyan]", border_style="cyan"))
        self.console.print()

        if result.get("valid"):
            self.console.print("[green]✓ Issue validation passed[/green]")
            self.console.print(f"[dim]{result.get('message', '')}[/dim]")
            self.console.print()
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
        if result.get("dry_run") or not result.get("created"):
            return
        issue = result.get("issue", {})
        self.console.print()
        self.console.print(Panel.fit("✅ [bold green]Issue Created Successfully[/bold green]", border_style="green"))
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
