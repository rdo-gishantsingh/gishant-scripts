"""Unified YouTrack CLI tool for creating, fetching, and updating issues.

This module combines functionality to manage YouTrack issues programmatically
via the API, supporting create, fetch, and update operations.
"""

import json
import re
from datetime import datetime
from typing import Any

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# --- Classes moved from original scripts ---


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


class YouTrackIssuesFetcher:
    """Fetch YouTrack issues where the authenticated user is involved."""

    READ_ONLY_MODE: bool = True

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self.console = Console()
        self._ensure_read_only_mode()

    def _ensure_read_only_mode(self) -> None:
        if not self.READ_ONLY_MODE:
            raise RuntimeError("SECURITY ERROR: YouTrackIssuesFetcher must operate in READ_ONLY_MODE.")

    def _validate_http_method(self, method: str) -> None:
        if method.upper() != "GET":
            raise ValueError(f"SECURITY ERROR: HTTP {method} not allowed. Only GET requests supported.")

    def get_current_user(self) -> dict:
        self._validate_http_method("GET")
        url = f"{self.base_url}/api/users/me"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def fetch_issue_by_id(self, issue_id: str) -> dict:
        self._validate_http_method("GET")
        url = f"{self.base_url}/api/issues/{issue_id}"
        params = {
            "fields": "id,idReadable,summary,description,created,updated,"
            "reporter(login,fullName,email),"
            "customFields(name,value(name,fullName,login,text)),"
            "comments(author(login,fullName),text,created,updated,deleted),"
            "tags(name),"
            "links(direction,linkType(name),issues(id,idReadable))"
        }
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        issue = response.json()
        return self._process_issue(issue)

    def _extract_github_links(self, text: str | None) -> list[str]:
        if not text:
            return []
        github_pattern = r"https?://github\.com/[\w-]+/[\w-]+/(?:pull|issues)/\d+"
        matches = re.findall(github_pattern, text)
        return list(set(matches))

    def _process_issue(self, issue: dict) -> dict:
        try:
            current_user = self.get_current_user()
            user_login = current_user.get("login", "")
            user_full_name = current_user.get("fullName", "")
        except Exception:
            user_login = ""
            user_full_name = ""

        custom_fields = {}
        assignee = None
        state = None
        priority = None
        issue_type = None

        for field in issue.get("customFields", []):
            field_name = field.get("name", "")
            value = field.get("value")
            if field_name == "Assignee" and value:
                assignee = value.get("fullName") or value.get("name", "Unknown")
                custom_fields["Assignee"] = assignee
            elif field_name == "State" and value:
                state = value.get("name", "Unknown")
                custom_fields["State"] = state
            elif field_name == "Priority" and value:
                priority = value.get("name", "Unknown")
                custom_fields["Priority"] = priority
            elif field_name == "Type" and value:
                issue_type = value.get("name", "Unknown")
                custom_fields["Type"] = issue_type
            elif value:
                if isinstance(value, dict):
                    custom_fields[field_name] = value.get("name") or value.get("text", str(value))
                else:
                    custom_fields[field_name] = str(value)

        all_comments = []
        user_commented = False
        for comment in issue.get("comments", []):
            if comment.get("deleted"):
                continue
            author = comment.get("author", {})
            author_login = author.get("login", "Unknown")
            comment_text = comment.get("text", "")
            if author_login == user_login:
                user_commented = True
            all_comments.append(
                {
                    "author": author.get("fullName", "Unknown"),
                    "author_login": author_login,
                    "text": comment_text,
                    "created": self._format_timestamp(comment.get("created")),
                    "created_timestamp": comment.get("created"),
                    "updated": self._format_timestamp(comment.get("updated")),
                    "updated_timestamp": comment.get("updated"),
                }
            )
        tags = [tag.get("name", "") for tag in issue.get("tags", [])]

        github_links = []
        description = issue.get("description", "")
        github_links.extend(self._extract_github_links(description))
        for field_name, field_value in custom_fields.items():
            if isinstance(field_value, str):
                github_links.extend(self._extract_github_links(field_value))
        github_links = sorted(list(set(github_links)))

        return {
            "id": issue.get("idReadable", "N/A"),
            "summary": issue.get("summary", "No summary"),
            "description": issue.get("description", "No description"),
            "type": issue_type,
            "state": state,
            "priority": priority,
            "created": self._format_timestamp(issue.get("created")),
            "created_timestamp": issue.get("created"),
            "updated": self._format_timestamp(issue.get("updated")),
            "updated_timestamp": issue.get("updated"),
            "reporter": issue.get("reporter", {}).get("fullName", "Unknown"),
            "reporter_login": issue.get("reporter", {}).get("login", "Unknown"),
            "assignee": assignee,
            "tags": tags,
            "custom_fields": custom_fields,
            "comments": all_comments,
            "comments_count": len(all_comments),
            "user_commented": user_commented,
            "user_is_assignee": assignee == user_full_name if assignee else False,
            "url": f"{self.base_url}/issue/{issue.get('idReadable', '')}",
            "github_links": github_links,
        }

    def fetch_issues_with_details(self, max_results: int = 100) -> list[dict]:
        self._validate_http_method("GET")
        current_user = self.get_current_user()
        user_login = current_user.get("login", "")
        user_full_name = current_user.get("fullName", "")
        self.console.print(f"[cyan]Fetching complete issue data for user:[/cyan] {user_full_name} ({user_login})")
        query = "Assignee: me or commented by: me"
        url = f"{self.base_url}/api/issues"
        params = {
            "query": query,
            "fields": "id,idReadable,summary,description,created,updated,"
            "reporter(login,fullName,email),"
            "customFields(name,value(name,fullName,login,text)),"
            "comments(author(login,fullName),text,created,updated,deleted),"
            "tags(name),"
            "links(direction,linkType(name),issues(id,idReadable))",
            "$top": max_results,
        }
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        issues = response.json()
        self.console.print(f"[green]Fetched {len(issues)} issues. Processing details...[/green]")
        results = []
        for idx, issue in enumerate(issues, 1):
            self.console.print(f"[dim]Processing issue {idx}/{len(issues)}: {issue.get('idReadable', 'N/A')}[/dim]")
            results.append(self._process_issue(issue))
        return results

    def _format_timestamp(self, timestamp: int | None) -> str:
        if timestamp:
            return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
        return "N/A"

    def print_issue(self, issue: dict, show_fields: list[str] | None = None):
        if show_fields:
            content = []
            for field in show_fields:
                if field == "summary":
                    content.append(f"[bold]Summary:[/bold] {issue.get('summary', 'N/A')}")
                elif field == "description":
                    desc = issue.get("description", "No description")
                    content.append(f"[bold]Description:[/bold]\n{desc}")
                elif field == "comments":
                    content.append(f"[bold]Comments ({issue.get('comments_count', 0)}):[/bold]")
                    for comment in issue.get("comments", []):
                        content.append(f"\n[cyan]{comment['author']}[/cyan] - {comment['created']}")
                        content.append(comment["text"])
                elif field == "type":
                    content.append(f"[bold]Type:[/bold] {issue.get('type', 'N/A')}")
                elif field == "state":
                    content.append(f"[bold]State:[/bold] {issue.get('state', 'N/A')}")
                elif field == "priority":
                    content.append(f"[bold]Priority:[/bold] {issue.get('priority', 'N/A')}")
                elif field == "assignee":
                    content.append(f"[bold]Assignee:[/bold] {issue.get('assignee', 'Unassigned')}")
                elif field == "reporter":
                    content.append(f"[bold]Reporter:[/bold] {issue.get('reporter', 'Unknown')}")
                elif field == "tags":
                    tags = issue.get("tags", [])
                    if tags:
                        content.append(f"[bold]Tags:[/bold] {', '.join(tags)}")
                elif field == "url":
                    content.append(f"[bold]URL:[/bold] {issue.get('url', 'N/A')}")
            panel = Panel("\n".join(content), title=f"[bold cyan]{issue['id']}[/bold cyan]", border_style="cyan")
            self.console.print(panel)
            return

        content = []
        content.append(f"[bold]Summary:[/bold] {issue['summary']}")
        content.append(
            f"[bold]Type:[/bold] {issue.get('type', 'N/A')} | [bold]State:[/bold] {issue.get('state', 'N/A')} | [bold]Priority:[/bold] {issue.get('priority', 'N/A')}"
        )
        content.append(f"[bold]Created:[/bold] {issue['created']} | [bold]Updated:[/bold] {issue['updated']}")
        content.append(f"[bold]Reporter:[/bold] {issue['reporter']}")
        if issue.get("assignee"):
            assignee_text = f"[bold]Assignee:[/bold] {issue['assignee']}"
            if issue.get("user_is_assignee"):
                assignee_text += " [green]✓ (You)[/green]"
            content.append(assignee_text)
        if issue.get("user_commented"):
            content.append("[green]✓ You have commented on this issue[/green]")
        content.append(f"[bold]Total Comments:[/bold] {issue['comments_count']}")
        if issue.get("tags"):
            content.append(f"[bold]Tags:[/bold] {', '.join(issue['tags'])}")
        content.append(f"[bold]URL:[/bold] {issue['url']}")
        if issue.get("description"):
            desc = issue["description"]
            desc_preview = desc[:150] + "..." if len(desc) > 150 else desc
            content.append(f"\n[bold]Description:[/bold]\n{desc_preview}")
        panel = Panel("\n".join(content), title=f"[bold cyan]{issue['id']}[/bold cyan]", border_style="cyan")
        self.console.print(panel)

    def print_results(self, issues: list[dict]):
        if not issues:
            self.console.print("\n[yellow]No issues found where you're involved.[/yellow]")
            return
        self.console.print(f"\n[bold green]Found {len(issues)} issue(s) where you're involved[/bold green]\n")
        for issue in issues:
            self.print_issue(issue)

    def save_to_json(self, issues: list[dict], filename: str = "my_youtrack_issues.json"):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)
        self.console.print(f"\n[green]✓ Results saved to {filename}[/green]")

    def save_ids_to_file(self, issue_ids: list[str], filename: str = "my_youtrack_issue_ids.txt"):
        with open(filename, "w", encoding="utf-8") as f:
            for issue_id in issue_ids:
                f.write(f"{issue_id}\n")
        self.console.print(f"\n[green]✓ Issue IDs saved to {filename}[/green]")


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
    from gishant_scripts.common.config import AppConfig
    from gishant_scripts.common.errors import ConfigurationError

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
    from gishant_scripts.common.config import AppConfig
    from gishant_scripts.common.errors import ConfigurationError

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

            fetcher.print_issue(issue, show_fields if show_fields else None)
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
    from gishant_scripts.common.config import AppConfig
    from gishant_scripts.common.errors import ConfigurationError

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


def main():
    app()


if __name__ == "__main__":
    app()
