"""YouTrack issue updater with dry-run support."""

from __future__ import annotations

from typing import Any

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


class YouTrackIssueUpdater:
    """Update YouTrack issues with dry-run support."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.console = Console()

    def get_issue_info(self, issue_id: str) -> dict[str, Any] | None:
        url = f"{self.base_url}/api/issues/{issue_id}"
        params = {"fields": "id,idReadable,summary,description"}
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            return None

    def update_fields(
        self,
        issue_id: str,
        summary: str | None = None,
        description: str | None = None,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        issue_info = self.get_issue_info(issue_id)
        if not issue_info:
            raise ValueError(f"Issue '{issue_id}' not found or not accessible")

        payload: dict[str, Any] = {}
        if summary:
            payload["summary"] = summary
        if description:
            payload["description"] = description

        if not payload:
            return {"dry_run": dry_run, "valid": True, "action": "no_change", "message": "No fields to update"}

        if dry_run:
            return {
                "dry_run": True,
                "valid": True,
                "action": "update_fields",
                "issue_id": issue_id,
                "issue_summary": issue_info.get("summary"),
                "payload": payload,
                "message": "✓ Fields are valid and ready to be updated",
            }

        url = f"{self.base_url}/api/issues/{issue_id}"
        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        return {
            "dry_run": False,
            "updated": True,
            "action": "update_fields",
            "issue_id": issue_id,
            "issue": result,
            "url": f"{self.base_url}/issue/{issue_id}",
        }

    def post_comment(
        self,
        issue_id: str,
        comment: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
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
            if "summary" in payload:
                table.add_row("New Summary", payload["summary"])
            if "description" in payload:
                desc = payload["description"]
                desc_preview = (desc[:100] + "...") if len(desc) > 100 else desc
                table.add_row("New Description", desc_preview)
            self.console.print(table)
            self.console.print()
            self.console.print(
                "[yellow]💡 To actually execute this update, run the command again with --no-dry-run[/yellow]"
            )
        else:
            self.console.print("[red]✗ Validation failed[/red]")

    def print_success_result(self, result: dict[str, Any]):
        if result.get("dry_run"):
            return
        self.console.print()
        self.console.print(Panel.fit("✅ [bold green]Update Successful[/bold green]", border_style="green"))
        self.console.print(f"Issue: {result.get('issue_id')} updated.")
        self.console.print(f"URL: {result.get('url')}")
