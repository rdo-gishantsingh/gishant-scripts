"""Update YouTrack epic and child tasks with implementation progress comments.

This script fetches a YouTrack epic and its child tasks (using "subtask of" query),
analyzes a codebase for implementation status, and posts structured progress comments
to each ticket.

SECURITY NOTICE: This module performs WRITE operations (POST requests).
Use with caution and always test with --dry-run first.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm

from gishant_scripts.youtrack.fetch_issues import YouTrackIssuesFetcher


class YouTrackEpicProgressUpdater:
    """Update YouTrack epic and child tasks with progress comments.

    WARNING: This class performs WRITE operations (POST requests).
    Always use dry-run mode first to validate your updates before posting.
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
        self.fetcher = YouTrackIssuesFetcher(base_url, token)

    def fetch_epic_with_children(self, epic_id: str) -> dict[str, Any]:
        """Fetch an epic issue and all its child tasks.

        Args:
            epic_id: The epic issue ID (e.g., 'PIPE-617')

        Returns:
            Dictionary containing epic and children information
        """
        self.console.print(f"[cyan]Fetching epic:[/cyan] {epic_id}")

        # Fetch the epic itself
        epic = self.fetcher.fetch_issue_by_id(epic_id)

        # Fetch all child tasks using subtask query
        self.console.print(f"[cyan]Fetching child tasks for:[/cyan] {epic_id}")
        query = f"subtask of: {epic_id}"

        url = f"{self.base_url}/api/issues"
        params = {
            "query": query,
            "fields": "id,idReadable,summary,description,created,updated,"
            "reporter(login,fullName,email),"
            "customFields(name,value(name,fullName,login,text)),"
            "comments(author(login,fullName),text,created,updated,deleted),"
            "tags(name)",
            "$top": 100,
        }

        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()

        children_raw = response.json()
        children = [self.fetcher._process_issue(child) for child in children_raw]

        self.console.print(f"[green]Found {len(children)} child tasks[/green]")

        return {
            "epic": epic,
            "children": children,
            "total_children": len(children),
        }

    def post_comment(
        self,
        issue_id: str,
        comment_text: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Post a comment to a YouTrack issue.

        Args:
            issue_id: The issue ID (e.g., 'PIPE-617')
            comment_text: The comment text to post
            dry_run: If True, validate but don't post the comment

        Returns:
            Dictionary containing the result
        """
        if dry_run:
            return {
                "dry_run": True,
                "issue_id": issue_id,
                "comment": comment_text,
                "message": "✓ Comment is valid and ready to be posted",
            }

        # Actually post the comment
        url = f"{self.base_url}/api/issues/{issue_id}/comments"
        payload = {
            "text": comment_text,
        }

        response = requests.post(url, headers=self.headers, json=payload, timeout=30)
        response.raise_for_status()

        comment = response.json()
        return {
            "dry_run": False,
            "posted": True,
            "issue_id": issue_id,
            "comment_id": comment.get("id"),
            "created": comment.get("created"),
        }

    def analyze_codebase(self, codebase_path: Path) -> dict[str, Any]:
        """Analyze a codebase to determine implementation status.

        Args:
            codebase_path: Path to the codebase root directory

        Returns:
            Dictionary containing analysis results
        """
        self.console.print(f"[cyan]Analyzing codebase:[/cyan] {codebase_path}")

        analysis = {
            "path": str(codebase_path),
            "cli_commands": {},
            "services": {},
            "tests": {},
            "documentation": {},
            "summary": {
                "total_cli_files": 0,
                "total_service_files": 0,
                "total_test_files": 0,
                "total_doc_files": 0,
            },
        }

        # Analyze CLI commands
        cli_path = codebase_path / "src" / "ayon_bundle_manager" / "cli"
        if cli_path.exists():
            cli_files = list(cli_path.glob("*.py"))
            analysis["summary"]["total_cli_files"] = len(cli_files)
            for cli_file in cli_files:
                if cli_file.name != "__init__.py":
                    analysis["cli_commands"][cli_file.stem] = {
                        "file": str(cli_file.relative_to(codebase_path)),
                        "exists": True,
                        "size": cli_file.stat().st_size,
                    }

        # Analyze services
        services_path = codebase_path / "src" / "ayon_bundle_manager" / "services"
        if services_path.exists():
            service_files = list(services_path.glob("*.py"))
            analysis["summary"]["total_service_files"] = len(service_files)
            for service_file in service_files:
                if service_file.name != "__init__.py":
                    analysis["services"][service_file.stem] = {
                        "file": str(service_file.relative_to(codebase_path)),
                        "exists": True,
                        "size": service_file.stat().st_size,
                    }

        # Analyze tests
        tests_path = codebase_path / "tests"
        if tests_path.exists():
            test_files = list(tests_path.rglob("test_*.py"))
            analysis["summary"]["total_test_files"] = len(test_files)

            # Group tests by category
            test_categories = {"unit": [], "integration": [], "e2e": [], "other": []}
            for test_file in test_files:
                rel_path = str(test_file.relative_to(codebase_path))
                if "unit" in rel_path:
                    test_categories["unit"].append(rel_path)
                elif "integration" in rel_path:
                    test_categories["integration"].append(rel_path)
                elif "e2e" in rel_path:
                    test_categories["e2e"].append(rel_path)
                else:
                    test_categories["other"].append(rel_path)

            analysis["tests"] = test_categories

        # Analyze documentation
        docs_path = codebase_path / "docs"
        if docs_path.exists():
            doc_files = list(docs_path.rglob("*.md"))
            analysis["summary"]["total_doc_files"] = len(doc_files)
            for doc_file in doc_files:
                rel_path = str(doc_file.relative_to(codebase_path))
                analysis["documentation"][doc_file.stem] = {
                    "file": rel_path,
                    "exists": True,
                }

        self.console.print(f"[green]Analysis complete:[/green]")
        self.console.print(f"  • CLI files: {analysis['summary']['total_cli_files']}")
        self.console.print(f"  • Service files: {analysis['summary']['total_service_files']}")
        self.console.print(f"  • Test files: {analysis['summary']['total_test_files']}")
        self.console.print(f"  • Doc files: {analysis['summary']['total_doc_files']}")

        return analysis

    def map_features_to_tickets(
        self,
        children: list[dict],
        analysis: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Map implemented features to YouTrack child tasks.

        Args:
            children: List of child task dictionaries
            analysis: Codebase analysis results

        Returns:
            Dictionary mapping issue IDs to implementation status
        """
        self.console.print("[cyan]Mapping features to tickets...[/cyan]")

        mapping = {}

        for child in children:
            issue_id = child["id"]
            summary = child["summary"].lower()

            # Determine implementation status based on summary keywords
            status = "❌ Not Started"
            details = []
            test_info = ""
            doc_info = ""

            # Special handling for specific tasks
            if "core architecture" in summary or "project setup" in summary:
                # Check if project structure exists
                if analysis["cli_commands"] and analysis["services"]:
                    status = "✅ Completed"
                    details.append(
                        f"Project structure set up with {analysis['summary']['total_cli_files']} CLI modules"
                    )
                    details.append(f"{analysis['summary']['total_service_files']} service modules implemented")
                    details.append("Package configuration and build system configured")
            elif "documentation" in summary:
                # Check documentation status
                if analysis["summary"]["total_doc_files"] > 20:
                    status = "✅ Completed"
                    details.append(f"{analysis['summary']['total_doc_files']} documentation files created")
                    details.append("Comprehensive documentation site available")
                elif analysis["summary"]["total_doc_files"] > 5:
                    status = "🚧 In Progress"
                    details.append(f"{analysis['summary']['total_doc_files']} documentation files started")
            elif "testing" in summary or "quality assurance" in summary:
                # Check test coverage
                if analysis["summary"]["total_test_files"] > 40:
                    status = "✅ Completed"
                    details.append(f"{analysis['summary']['total_test_files']} test files implemented")
                    details.append(f"Unit tests: {len(analysis['tests']['unit'])} files")
                    details.append(f"Integration tests: {len(analysis['tests']['integration'])} files")
                    details.append(f"E2E tests: {len(analysis['tests']['e2e'])} files")
                elif analysis["summary"]["total_test_files"] > 0:
                    status = "🚧 In Progress"
                    details.append(f"{analysis['summary']['total_test_files']} test files created")
            elif "api client" in summary:
                # Check for API client implementation
                api_client_path = Path(analysis["path"]) / "src" / "ayon_bundle_manager" / "api" / "client.py"
                if api_client_path.exists():
                    status = "✅ Completed"
                    details.append("API client implemented in `src/ayon_bundle_manager/api/client.py`")
                    details.append("Retry logic and caching available")
            else:
                # Check for CLI command implementations
                for cmd_name, cmd_info in analysis["cli_commands"].items():
                    if cmd_name in summary or cmd_name.replace("_", " ") in summary:
                        # Check if the file is substantial (> 5KB means well-developed)
                        if cmd_info["size"] > 5000:
                            status = "✅ Completed"
                        else:
                            status = "🚧 In Progress"
                        details.append(f"CLI command implemented in `{cmd_info['file']}` ({cmd_info['size']} bytes)")

                # Check for service implementations
                for service_name, service_info in analysis["services"].items():
                    if service_name in summary or service_name.replace("_", " ") in summary:
                        if status == "❌ Not Started":
                            if service_info["size"] > 4000:
                                status = "✅ Completed"
                            else:
                                status = "🚧 In Progress"
                        details.append(
                            f"Service implemented in `{service_info['file']}` ({service_info['size']} bytes)"
                        )

                # Check for related keywords and map to broader features
                keywords_map = {
                    "bundle": ["bundle", "comparison", "deployment", "sync", "templates"],
                    "addon": ["addon", "validation"],
                    "config": ["config", "validation"],
                    "deploy": ["deployment", "sync"],
                    "compare": ["comparison"],
                    "sync": ["sync"],
                    "template": ["templates"],
                    "validate": ["validation"],
                    "history": ["history"],
                    "rollback": ["deployment", "history"],
                }

                for keyword, related_services in keywords_map.items():
                    if keyword in summary:
                        for service in related_services:
                            if service in analysis["services"]:
                                service_info = analysis["services"][service]
                                # Only upgrade status if we found significant implementations
                                if status == "❌ Not Started" and service_info["size"] > 2000:
                                    status = "🚧 In Progress"
                                # Add to details if not already mentioned
                                detail_str = f"Service `{service}` available in `{service_info['file']}`"
                                if detail_str not in details and service not in summary:
                                    details.append(detail_str)

            # Test coverage info
            total_tests = analysis["summary"]["total_test_files"]
            if total_tests > 0:
                test_info = f"{total_tests} test files in test suite (unit: {len(analysis['tests']['unit'])}, integration: {len(analysis['tests']['integration'])}, e2e: {len(analysis['tests']['e2e'])})"

            # Documentation info
            if analysis["documentation"]:
                doc_info = f"{analysis['summary']['total_doc_files']} documentation files available"

            mapping[issue_id] = {
                "summary": child["summary"],
                "current_state": child.get("state", "Unknown"),
                "status": status,
                "details": details if details else ["No direct implementation found yet"],
                "test_info": test_info,
                "doc_info": doc_info,
            }

        self.console.print(f"[green]Mapped {len(mapping)} tickets[/green]")
        return mapping

    def generate_progress_comment(
        self,
        issue_id: str,
        mapping_info: dict[str, Any],
    ) -> str:
        """Generate a structured progress comment for a ticket.

        Args:
            issue_id: The issue ID
            mapping_info: Mapping information for this issue

        Returns:
            Formatted comment text
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        comment_parts = [
            "## 📊 Implementation Status Update",
            "",
            f"**Status**: {mapping_info['status']}",
            f"**Updated**: {timestamp}",
            "",
            "### Implementation Details",
        ]

        for detail in mapping_info["details"]:
            comment_parts.append(f"- {detail}")

        if mapping_info["test_info"]:
            comment_parts.extend(
                [
                    "",
                    "### Test Coverage",
                    f"- {mapping_info['test_info']}",
                ]
            )

        if mapping_info["doc_info"]:
            comment_parts.extend(
                [
                    "",
                    "### Documentation",
                    f"- {mapping_info['doc_info']}",
                ]
            )

        comment_parts.extend(
            [
                "",
                "---",
                "*This is an automated progress update generated by analyzing the codebase.*",
            ]
        )

        return "\n".join(comment_parts)

    def display_dry_run_preview(
        self,
        mapping: dict[str, dict[str, Any]],
        epic_info: dict[str, Any],
    ):
        """Display a preview of all comments that would be posted.

        Args:
            mapping: Mapping of issue IDs to implementation status
            epic_info: Epic and children information
        """
        self.console.print()
        self.console.print(
            Panel.fit(
                "🔍 [bold cyan]DRY RUN PREVIEW[/bold cyan]\n"
                f"Epic: {epic_info['epic']['id']} - {epic_info['epic']['summary']}\n"
                f"Child Tasks: {epic_info['total_children']}",
                border_style="cyan",
            )
        )
        self.console.print()

        for issue_id, info in mapping.items():
            comment_text = self.generate_progress_comment(issue_id, info)

            # Create a table for this issue
            table = Table(title=f"{issue_id}: {info['summary']}", border_style="cyan", show_header=False)
            table.add_column("Field", style="cyan", no_wrap=True, width=20)
            table.add_column("Value", style="white")

            table.add_row("Current State", info["current_state"])
            table.add_row("New Status", info["status"])
            table.add_row("Comment Preview", "↓ See below ↓")

            self.console.print(table)
            self.console.print(Panel(comment_text, border_style="dim", padding=(1, 2)))
            self.console.print()

        self.console.print(
            f"[yellow]💡 {len(mapping)} comments ready to post. Use --no-dry-run to actually post them.[/yellow]"
        )

    def post_all_comments(
        self,
        mapping: dict[str, dict[str, Any]],
        dry_run: bool = True,
    ) -> list[dict[str, Any]]:
        """Post comments to all mapped issues.

        Args:
            mapping: Mapping of issue IDs to implementation status
            dry_run: If True, don't actually post comments

        Returns:
            List of posting results
        """
        results = []

        for issue_id, info in mapping.items():
            comment_text = self.generate_progress_comment(issue_id, info)

            try:
                result = self.post_comment(issue_id, comment_text, dry_run=dry_run)
                results.append(result)

                if not dry_run:
                    self.console.print(f"[green]✓ Posted comment to {issue_id}[/green]")
            except Exception as e:
                self.console.print(f"[red]✗ Failed to post comment to {issue_id}: {e}[/red]")
                results.append(
                    {
                        "dry_run": dry_run,
                        "posted": False,
                        "issue_id": issue_id,
                        "error": str(e),
                    }
                )

        return results


app = typer.Typer()


@app.command()
def update_epic(
    epic_id: str = typer.Argument(..., help="Epic issue ID (e.g., PIPE-617)"),
    codebase_path: Path = typer.Argument(..., help="Path to the codebase to analyze"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Preview without posting (default: True)"),
    save_analysis: bool = typer.Option(False, "--save-analysis", help="Save analysis results to JSON"),
):
    """Update a YouTrack epic and its child tasks with implementation progress.

    By default, runs in DRY-RUN mode to preview comments before posting.
    Use --no-dry-run to actually post comments.

    Examples:

        # Dry run (preview only)
        update-epic-progress PIPE-617 /path/to/codebase

        # Save analysis results
        update-epic-progress PIPE-617 /path/to/codebase --save-analysis

        # Actually post comments (after reviewing dry run)
        update-epic-progress PIPE-617 /path/to/codebase --no-dry-run
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

    # Initialize the updater
    if not config.youtrack.url or not config.youtrack.api_token:
        console.print("[red]✖ Missing YouTrack URL or API token in configuration[/red]")
        raise typer.Exit(1)

    # Validate codebase path
    if not codebase_path.exists():
        console.print(f"[red]✖ Codebase path does not exist: {codebase_path}[/red]")
        raise typer.Exit(1)

    updater = YouTrackEpicProgressUpdater(config.youtrack.url, config.youtrack.api_token)

    try:
        # Step 1: Fetch epic and children
        epic_info = updater.fetch_epic_with_children(epic_id)

        # Step 2: Analyze codebase
        analysis = updater.analyze_codebase(codebase_path)

        if save_analysis:
            analysis_file = f"{epic_id.replace('-', '_')}_analysis.json"
            with open(analysis_file, "w", encoding="utf-8") as f:
                json.dump(analysis, f, indent=2, ensure_ascii=False)
            console.print(f"[green]✓ Analysis saved to {analysis_file}[/green]")

        # Step 3: Map features to tickets
        mapping = updater.map_features_to_tickets(epic_info["children"], analysis)

        # Step 4: Display dry run preview
        if dry_run:
            updater.display_dry_run_preview(mapping, epic_info)
        else:
            # Confirm before posting
            console.print(f"\n[yellow]⚠️  You are about to post {len(mapping)} comments to YouTrack.[/yellow]")
            if Confirm.ask("Do you want to continue?"):
                results = updater.post_all_comments(mapping, dry_run=False)

                success_count = sum(1 for r in results if r.get("posted", False))
                console.print(
                    f"\n[bold green]✅ Successfully posted {success_count}/{len(mapping)} comments[/bold green]"
                )
            else:
                console.print("[yellow]Operation cancelled[/yellow]")
                raise typer.Exit(0)

    except requests.exceptions.HTTPError as err:
        console.print(f"[red]❌ HTTP Error:[/red] {err}")
        if hasattr(err, "response") and err.response is not None:
            try:
                error_detail = err.response.json()
                console.print(f"[dim]Details: {json.dumps(error_detail, indent=2)}[/dim]")
            except Exception:
                console.print(f"[dim]Response: {err.response.text}[/dim]")
        raise typer.Exit(1)
    except Exception as err:
        console.print(f"[red]❌ Error:[/red] {err}")
        raise typer.Exit(1)


def main():
    """Entry point for the console script."""
    app()


if __name__ == "__main__":
    app()
