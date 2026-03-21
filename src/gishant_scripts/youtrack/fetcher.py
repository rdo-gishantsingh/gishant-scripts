"""YouTrack issue fetcher for retrieving issues where the authenticated user is involved."""

from __future__ import annotations

import json
import re
from datetime import datetime

import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table


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

    def get_user_by_login(self, login: str) -> dict:
        """Fetch user info by login name."""
        self._validate_http_method("GET")
        url = f"{self.base_url}/api/users/{login}"
        params = {"fields": "id,login,fullName,email"}
        response = requests.get(url, headers=self.headers, params=params, timeout=10)
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

    def _process_issue(self, issue: dict, target_user: dict | None = None) -> dict:
        if target_user is not None:
            user_login = target_user.get("login", "")
            user_full_name = target_user.get("fullName", "")
        else:
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

    def fetch_issues_with_details(
        self,
        max_results: int = 100,
        user_login: str | None = None,
        *,
        silent: bool = False,
    ) -> list[dict]:
        self._validate_http_method("GET")
        if user_login is None:
            current_user = self.get_current_user()
            target_user = current_user
            query = "Assignee: me or commented by: me"
        else:
            target_user = self.get_user_by_login(user_login)
            query = f"Assignee: {user_login} or commented by: {user_login}"
        if not silent:
            user_display = target_user.get("fullName", "") or target_user.get("login", "")
            login_display = target_user.get("login", "")
            self.console.print(f"[cyan]Fetching complete issue data for user:[/cyan] {user_display} ({login_display})")
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
        if not silent:
            self.console.print(f"[green]Fetched {len(issues)} issues. Processing details...[/green]")
        results = []
        if not issues:
            return results
        if silent:
            for issue in issues:
                results.append(self._process_issue(issue, target_user=target_user))
        else:
            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=self.console,
            ) as progress:
                task_id = progress.add_task("Processing issues", total=len(issues))
                for issue in issues:
                    results.append(self._process_issue(issue, target_user=target_user))
                    progress.update(
                        task_id,
                        advance=1,
                        description=f"Processing {issue.get('idReadable', 'N/A')}",
                    )
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
            f.writelines(f"{issue_id}\n" for issue_id in issue_ids)
        self.console.print(f"\n[green]✓ Issue IDs saved to {filename}[/green]")
