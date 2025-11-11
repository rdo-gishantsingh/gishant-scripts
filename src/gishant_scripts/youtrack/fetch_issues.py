import json
import re
from datetime import datetime

import click
import requests
from rich.console import Console
from rich.panel import Panel


class YouTrackIssuesFetcher:
    """Fetch YouTrack issues where the authenticated user is involved."""

    def __init__(self, base_url: str, token: str):
        """
        Initialize the YouTrack API client.

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

    def get_current_user(self) -> dict:
        """Get the current authenticated user's information."""
        url = f"{self.base_url}/api/users/me"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def fetch_issue_by_id(self, issue_id: str) -> dict:
        """
        Fetch a specific issue by its ID with complete details.

        Args:
            issue_id: The issue ID (e.g., 'PIPE-1234')

        Returns:
            Dictionary containing complete issue information
        """
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
        """Extract GitHub PR/issue links from text."""
        if not text:
            return []

        # Pattern for GitHub PR and issue URLs
        github_pattern = r"https?://github\.com/[\w-]+/[\w-]+/(?:pull|issues)/\d+"
        matches = re.findall(github_pattern, text)
        return list(set(matches))  # Remove duplicates

    def _process_issue(self, issue: dict) -> dict:
        """Process raw issue data into formatted structure."""
        # Get current user for comparison
        try:
            current_user = self.get_current_user()
            user_login = current_user.get("login", "")
            user_full_name = current_user.get("fullName", "")
        except Exception:
            user_login = ""
            user_full_name = ""

        # Extract custom fields
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

        # Get ALL comments
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
                        "created_timestamp": comment.get("created"),  # Raw timestamp in milliseconds
                        "updated": self._format_timestamp(comment.get("updated")),
                        "updated_timestamp": comment.get("updated"),  # Raw timestamp in milliseconds
                    }
                )  # Get tags
        tags = [tag.get("name", "") for tag in issue.get("tags", [])]

        # Extract GitHub links from description and custom fields
        github_links = []
        description = issue.get("description", "")
        github_links.extend(self._extract_github_links(description))

        # Check custom fields for GitHub links
        for field_name, field_value in custom_fields.items():
            if isinstance(field_value, str):
                github_links.extend(self._extract_github_links(field_value))

        # Remove duplicates and sort
        github_links = sorted(list(set(github_links)))

        # Build comprehensive issue information
        return {
            "id": issue.get("idReadable", "N/A"),
            "summary": issue.get("summary", "No summary"),
            "description": issue.get("description", "No description"),
            "type": issue_type,
            "state": state,
            "priority": priority,
            "created": self._format_timestamp(issue.get("created")),
            "created_timestamp": issue.get("created"),  # Raw timestamp in milliseconds
            "updated": self._format_timestamp(issue.get("updated")),
            "updated_timestamp": issue.get("updated"),  # Raw timestamp in milliseconds
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

    def fetch_issues_where_involved(self, max_results: int = 100) -> list[str]:
        """
        Fetch all issues where the current user is involved (assigned to or commented on).

        Args:
            max_results: Maximum number of issues to fetch (default: 100)

        Returns:
            List of issue IDs
        """
        # Get current user info first
        current_user = self.get_current_user()
        user_login = current_user.get("login", "")

        self.console.print(f"[cyan]Fetching issues for user:[/cyan] {user_login}")

        # Build the query to find issues where you're involved
        # YouTrack query: issues assigned to me OR where I commented
        query = "Assignee: me or commented by: me"

        # API endpoint for searching issues
        url = f"{self.base_url}/api/issues"

        params = {"query": query, "fields": "id,idReadable", "$top": max_results}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        issues = response.json()

        # Extract just the issue IDs
        issue_ids = [issue.get("idReadable", "") for issue in issues if issue.get("idReadable")]

        return issue_ids

    def fetch_issues_with_details(self, max_results: int = 100) -> list[dict]:
        """
        Fetch all issues where the current user is involved with COMPLETE details.
        Includes description, all comments, all custom fields, and full metadata.

        Args:
            max_results: Maximum number of issues to fetch (default: 100)

        Returns:
            List of issue dictionaries with complete information
        """
        # Get current user info first
        current_user = self.get_current_user()
        user_login = current_user.get("login", "")
        user_full_name = current_user.get("fullName", "")

        self.console.print(f"[cyan]Fetching complete issue data for user:[/cyan] {user_full_name} ({user_login})")

        # Build the query to find issues where you're involved
        query = "Assignee: me or commented by: me"

        # API endpoint for searching issues
        url = f"{self.base_url}/api/issues"

        # Fetch ALL fields including description and all comments
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

        # Process and format the results with ALL data
        results = []
        for idx, issue in enumerate(issues, 1):
            self.console.print(f"[dim]Processing issue {idx}/{len(issues)}: {issue.get('idReadable', 'N/A')}[/dim]")
            results.append(self._process_issue(issue))

        return results

    def _format_timestamp(self, timestamp: int | None) -> str:
        """Convert Unix timestamp (milliseconds) to readable format."""
        if timestamp:
            return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
        return "N/A"

    def print_issue(self, issue: dict, show_fields: list[str] | None = None):
        """Print a single issue with Rich formatting.

        Args:
            issue: The issue dictionary
            show_fields: List of specific fields to show. If None, show all.
                        Valid fields: 'summary', 'description', 'comments', 'type',
                        'state', 'priority', 'assignee', 'reporter', 'tags', 'url'
        """
        # If specific fields requested, only show those
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

        # Show full issue details
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

        # Description preview
        if issue.get("description"):
            desc = issue["description"]
            desc_preview = desc[:150] + "..." if len(desc) > 150 else desc
            content.append(f"\n[bold]Description:[/bold]\n{desc_preview}")

        panel = Panel("\n".join(content), title=f"[bold cyan]{issue['id']}[/bold cyan]", border_style="cyan")
        self.console.print(panel)

    def print_results(self, issues: list[dict]):
        """Print the issues in a readable format."""
        if not issues:
            self.console.print("\n[yellow]No issues found where you're involved.[/yellow]")
            return

        self.console.print(f"\n[bold green]Found {len(issues)} issue(s) where you're involved[/bold green]\n")

        for issue in issues:
            self.print_issue(issue)

    def print_issue_ids(self, issue_ids: list[str]):
        """Print just the issue IDs."""
        if not issue_ids:
            self.console.print("\n[yellow]No issues found where you're involved.[/yellow]")
            return

        self.console.print(f"\n[bold green]Found {len(issue_ids)} issue(s) where you're involved:[/bold green]\n")
        for issue_id in issue_ids:
            self.console.print(f"  • {issue_id}")

    def save_to_json(self, issues: list[dict], filename: str = "my_youtrack_issues.json"):
        """Save the results to a JSON file."""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)
        self.console.print(f"\n[green]✓ Results saved to {filename}[/green]")

    def save_ids_to_file(self, issue_ids: list[str], filename: str = "my_youtrack_issue_ids.txt"):
        """Save just the issue IDs to a text file."""
        with open(filename, "w", encoding="utf-8") as f:
            for issue_id in issue_ids:
                f.write(f"{issue_id}\n")
        self.console.print(f"\n[green]✓ Issue IDs saved to {filename}[/green]")


@click.command()
@click.option("--id", "issue_id", help="Fetch a specific issue by ID (e.g., PIPE-1234)")
@click.option("--summary", is_flag=True, help="Show only the summary of the issue")
@click.option("--description", "show_description", is_flag=True, help="Show only the description of the issue")
@click.option("--comments", is_flag=True, help="Show only the comments of the issue")
@click.option("--type", "show_type", is_flag=True, help="Show only the type of the issue")
@click.option("--state", is_flag=True, help="Show only the state of the issue")
@click.option("--priority", is_flag=True, help="Show only the priority of the issue")
@click.option("--assignee", is_flag=True, help="Show only the assignee of the issue")
@click.option("--reporter", is_flag=True, help="Show only the reporter of the issue")
@click.option("--tags", is_flag=True, help="Show only the tags of the issue")
@click.option("--url", "show_url", is_flag=True, help="Show only the URL of the issue")
@click.option("--max-results", default=200, help="Maximum number of issues to fetch (default: 200)")
@click.option("--save-json", is_flag=True, help="Save results to JSON file")
@click.option("--save-ids", is_flag=True, help="Save issue IDs to text file")
def main(
    issue_id: str | None,
    summary: bool,
    show_description: bool,
    comments: bool,
    show_type: bool,
    state: bool,
    priority: bool,
    assignee: bool,
    reporter: bool,
    tags: bool,
    show_url: bool,
    max_results: int,
    save_json: bool,
    save_ids: bool,
):
    """Fetch YouTrack issues where you're involved or a specific issue by ID.

    Examples:

        # Fetch all your issues
        fetch-issues

        # Fetch a specific issue with all details
        fetch-issues --id PIPE-1234

        # Fetch only the description of a specific issue
        fetch-issues --id PIPE-1234 --description

        # Fetch multiple fields of a specific issue
        fetch-issues --id PIPE-1234 --summary --description --comments

        # Fetch all issues and save to files
        fetch-issues --save-json --save-ids
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
        raise click.Abort()

    # Initialize the fetcher
    if not config.youtrack.url or not config.youtrack.api_token:
        console.print("[red]✖ Missing YouTrack URL or API token in configuration[/red]")
        raise click.Abort()

    fetcher = YouTrackIssuesFetcher(config.youtrack.url, config.youtrack.api_token)

    try:
        # If specific issue ID is provided
        if issue_id:
            console.print(f"[cyan]Fetching issue:[/cyan] {issue_id}")
            issue = fetcher.fetch_issue_by_id(issue_id)

            # Determine which fields to show
            show_fields = []
            if summary:
                show_fields.append("summary")
            if show_description:
                show_fields.append("description")
            if comments:
                show_fields.append("comments")
            if show_type:
                show_fields.append("type")
            if state:
                show_fields.append("state")
            if priority:
                show_fields.append("priority")
            if assignee:
                show_fields.append("assignee")
            if reporter:
                show_fields.append("reporter")
            if tags:
                show_fields.append("tags")
            if show_url:
                show_fields.append("url")

            # If no specific fields requested, show all
            fetcher.print_issue(issue, show_fields if show_fields else None)

            if save_json:
                fetcher.save_to_json([issue], f"{issue_id.replace('-', '_')}.json")

            return

        # Fetch all issues where user is involved
        console.print("[cyan]Fetching detailed issue information...[/cyan]")
        issues = fetcher.fetch_issues_with_details(max_results=max_results)

        # Display results
        fetcher.print_results(issues)

        # Save to files if requested
        if save_json:
            fetcher.save_to_json(issues)

        if save_ids:
            issue_ids = [issue["id"] for issue in issues]
            fetcher.save_ids_to_file(issue_ids)

        console.print(f"\n[bold green]✅ Successfully fetched {len(issues)} issues[/bold green]")
        if save_json:
            console.print("[green]📄 Detailed data saved to: my_youtrack_issues.json[/green]")
        if save_ids:
            console.print("[green]📋 Issue IDs saved to: my_youtrack_issue_ids.txt[/green]")

    except requests.exceptions.HTTPError as err:
        console.print(f"[red]❌ HTTP Error:[/red] {err}")
        if hasattr(err, "response"):
            console.print(f"[red]Response:[/red] {err.response.text}")
        raise click.Abort()
    except Exception as err:
        console.print(f"[red]❌ Error:[/red] {err}")
        raise click.Abort()


if __name__ == "__main__":
    import sys

    sys.exit(main())
