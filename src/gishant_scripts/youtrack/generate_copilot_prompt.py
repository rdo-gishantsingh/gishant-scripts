"""Generate GitHub Copilot prompts from YouTrack issues using Gemini AI."""

from __future__ import annotations

import sys
from pathlib import Path

import click
import requests
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from gishant_scripts.common.gemini import (
    AVAILABLE_MODELS,
    DEFAULT_MODEL,
    GeminiClient,
)
from gishant_scripts.youtrack.fetch_issues import YouTrackIssuesFetcher


class CopilotPromptGenerator:
    """Generate GitHub Copilot prompts from YouTrack issues using Gemini AI.

    SECURITY NOTICE: This class operates in READ-ONLY mode.
    It ONLY fetches data from YouTrack using GET requests.
    NO modifications to YouTrack issues are performed.
    """

    def __init__(
        self,
        youtrack_fetcher: YouTrackIssuesFetcher,
        gemini_api_key: str,
        model: str = DEFAULT_MODEL,
    ):
        """Initialize the prompt generator.

        Args:
            youtrack_fetcher: YouTrack issues fetcher instance
            gemini_api_key: Google AI API key
            model: Gemini model to use
        """
        self.fetcher = youtrack_fetcher
        self.gemini_client = GeminiClient(api_key=gemini_api_key, model=model)
        self.console = Console()

    def _fetch_github_content(self, github_url: str) -> dict | None:
        """Fetch content from GitHub PR or issue.

        Args:
            github_url: GitHub PR or issue URL

        Returns:
            Dictionary with GitHub content or None if fetch fails
        """
        try:
            # Parse GitHub URL to get owner, repo, and number
            # Format: https://github.com/owner/repo/pull/123 or .../issues/123
            parts = github_url.rstrip("/").split("/")
            if len(parts) < 7:
                return None

            owner = parts[-4]
            repo = parts[-3]
            item_type = parts[-2]  # 'pull' or 'issues'
            number = parts[-1]

            # Use GitHub API
            if item_type == "pull":
                api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
            else:
                api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"

            response = requests.get(api_url, timeout=10)
            response.raise_for_status()

            data = response.json()
            return {
                "url": github_url,
                "type": item_type,
                "title": data.get("title", ""),
                "body": data.get("body", ""),
                "state": data.get("state", ""),
                "user": data.get("user", {}).get("login", ""),
            }

        except Exception as err:
            self.console.print(f"[yellow]Warning: Could not fetch GitHub content from {github_url}: {err}[/yellow]")
            return None

    def _build_analysis_prompt(self, issue: dict, github_contents: list[dict]) -> str:
        """Build the prompt for Gemini AI to analyze the issue.

        Args:
            issue: The YouTrack issue dictionary
            github_contents: List of GitHub PR/issue contents

        Returns:
            The analysis prompt for Gemini
        """
        prompt_parts = [
            "You are an AI assistant helping to analyze a YouTrack issue and generate a detailed GitHub Copilot prompt.",
            "",
            "# YouTrack Issue Details",
            "",
            f"**Issue ID:** {issue['id']}",
            f"**Summary:** {issue['summary']}",
            f"**Type:** {issue.get('type', 'N/A')}",
            f"**State:** {issue.get('state', 'N/A')}",
            f"**Priority:** {issue.get('priority', 'N/A')}",
            "",
            "## Description",
            issue.get("description", "No description provided"),
            "",
        ]

        # Add comments if available
        if issue.get("comments"):
            prompt_parts.extend(
                [
                    "## Comments",
                    "",
                ]
            )
            for idx, comment in enumerate(issue["comments"], 1):
                prompt_parts.append(f"### Comment {idx} by {comment['author']}")
                prompt_parts.append(comment["text"])
                prompt_parts.append("")

        # Add GitHub linked content
        if github_contents:
            prompt_parts.extend(
                [
                    "## Linked GitHub PRs/Issues",
                    "",
                ]
            )
            for gh_content in github_contents:
                prompt_parts.append(f"### [{gh_content['type'].upper()}] {gh_content['title']}")
                prompt_parts.append(f"**URL:** {gh_content['url']}")
                prompt_parts.append(f"**State:** {gh_content['state']}")
                prompt_parts.append(f"**Author:** {gh_content['user']}")
                prompt_parts.append("")
                prompt_parts.append("**Content:**")
                prompt_parts.append(gh_content.get("body", "No description"))
                prompt_parts.append("")

        # Add instructions for Gemini
        prompt_parts.extend(
            [
                "",
                "---",
                "",
                "# Task",
                "",
                "Based on the above YouTrack issue and any linked GitHub content, generate a comprehensive GitHub Copilot prompt that includes:",
                "",
                "1. **Issue Summary**: A clear, concise summary of what needs to be done",
                "2. **Context & Background**: Key information from the description, comments, and linked PRs/issues",
                "3. **Analysis Approach**: Specific steps to analyze the codebase and understand the problem",
                "4. **Implementation Plan**: High-level plan for addressing the issue",
                "5. **Key Areas to Investigate**: Specific files, functions, or modules that should be examined",
                "6. **Guardrails & Considerations**: Important constraints, edge cases, and things to avoid",
                "7. **Testing Strategy**: How to verify the solution works correctly",
                "",
                "Format the output as a well-structured markdown document suitable for pasting into GitHub Copilot.",
                "Make it actionable and specific - focus on concrete steps rather than generic advice.",
                "If linked GitHub PRs/issues provide relevant context, incorporate their insights into the analysis.",
            ]
        )

        return "\n".join(prompt_parts)

    def generate_prompt(self, issue_id: str) -> tuple[str, dict]:
        """Generate a GitHub Copilot prompt for the given issue.

        Args:
            issue_id: The YouTrack issue ID

        Returns:
            Tuple of (generated_prompt, issue_data)
        """
        self.console.print(f"[cyan]Fetching issue {issue_id}...[/cyan]")

        # Fetch the issue
        issue = self.fetcher.fetch_issue_by_id(issue_id)

        self.console.print(f"[green]✓ Fetched issue: {issue['summary']}[/green]")

        # Fetch linked GitHub content
        github_contents = []
        if issue.get("github_links"):
            self.console.print(f"[cyan]Fetching {len(issue['github_links'])} linked GitHub items...[/cyan]")
            for gh_url in issue["github_links"]:
                content = self._fetch_github_content(gh_url)
                if content:
                    github_contents.append(content)
                    self.console.print(f"[green]✓ Fetched: {content['title']}[/green]")

        # Build analysis prompt
        analysis_prompt = self._build_analysis_prompt(issue, github_contents)

        self.console.print("[cyan]Generating Copilot prompt with Gemini AI...[/cyan]")

        # Generate with Gemini
        try:
            generated_prompt = self.gemini_client.generate_content(
                analysis_prompt,
                show_progress=False,  # We already show our own progress message
            )

            self.console.print("[green]✓ Successfully generated Copilot prompt[/green]")

            return generated_prompt, issue

        except Exception as err:
            self.console.print(f"[red]Error generating prompt with Gemini: {err}[/red]")
            raise

    def print_prompt(self, prompt: str, issue: dict):
        """Print the generated prompt to console.

        Args:
            prompt: The generated Copilot prompt
            issue: The issue data
        """
        self.console.print("\n")
        self.console.print(
            Panel(
                f"[bold]Issue:[/bold] {issue['id']}\n[bold]Summary:[/bold] {issue['summary']}",
                title="[bold cyan]GitHub Copilot Prompt Generated[/bold cyan]",
                border_style="cyan",
            )
        )
        self.console.print("\n")

        # Print as markdown
        md = Markdown(prompt)
        self.console.print(md)

    def save_to_file(self, prompt: str, issue: dict, output_file: Path):
        """Save the generated prompt to a markdown file.

        Args:
            prompt: The generated Copilot prompt
            issue: The issue data
            output_file: Path to the output file
        """
        # Ensure parent directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Build markdown content with metadata
        content = [
            f"# GitHub Copilot Prompt: {issue['id']}",
            "",
            f"**Issue:** {issue['id']}",
            f"**Summary:** {issue['summary']}",
            f"**URL:** {issue['url']}",
            f"**Type:** {issue.get('type', 'N/A')}",
            f"**State:** {issue.get('state', 'N/A')}",
            f"**Priority:** {issue.get('priority', 'N/A')}",
            "",
            "---",
            "",
            prompt,
        ]

        output_file.write_text("\n".join(content), encoding="utf-8")
        self.console.print(f"\n[green]✓ Saved prompt to {output_file}[/green]")


@click.command()
@click.argument("issue_id")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Save the prompt to a markdown file",
)
@click.option(
    "--model",
    type=click.Choice(AVAILABLE_MODELS, case_sensitive=False),
    default=DEFAULT_MODEL,
    help=f"Gemini model to use (default: {DEFAULT_MODEL})",
)
def main(issue_id: str, output: Path | None, model: str):
    """Generate a GitHub Copilot prompt from a YouTrack issue using Gemini AI.

    This tool fetches the specified YouTrack issue, analyzes it (including any
    linked GitHub PRs/issues), and uses Gemini AI to generate a comprehensive
    prompt suitable for GitHub Copilot.

    SECURITY NOTICE: This tool operates in READ-ONLY mode.
    It ONLY fetches data from YouTrack - NO modifications are made.

    Examples:

        # Generate and display prompt in console
        generate-copilot-prompt PIPE-1234

        # Generate and save to file
        generate-copilot-prompt PIPE-1234 --output copilot_prompt.md

        # Use a different Gemini model
        generate-copilot-prompt PIPE-1234 --model gemini-2.5-pro
    """
    from gishant_scripts.common.config import AppConfig
    from gishant_scripts.common.errors import ConfigurationError

    console = Console()

    # Load configuration
    try:
        config = AppConfig()
        config.require_valid("youtrack", "google_ai")
    except ConfigurationError as err:
        console.print(f"[red]Configuration Error:[/red] {err}")
        console.print(
            "\n[yellow]Please ensure YOUTRACK_URL, YOUTRACK_API_TOKEN, and GOOGLE_AI_API_KEY are set.[/yellow]"
        )
        console.print("[yellow]You can set them in a .env file or as environment variables.[/yellow]")
        sys.exit(1)

    try:
        # Initialize fetcher and generator
        fetcher = YouTrackIssuesFetcher(config.youtrack.url, config.youtrack.api_token)
        generator = CopilotPromptGenerator(fetcher, config.google_ai.api_key, model)

        # Generate prompt
        prompt, issue = generator.generate_prompt(issue_id)

        # Display prompt
        generator.print_prompt(prompt, issue)

        # Save to file if requested
        if output:
            generator.save_to_file(prompt, issue, output)

    except requests.exceptions.HTTPError as err:
        console.print(f"[red]HTTP Error:[/red] {err}")
        if err.response.status_code == 404:
            console.print(f"[yellow]Issue {issue_id} not found. Please check the issue ID.[/yellow]")
        sys.exit(1)
    except Exception as err:
        console.print(f"[red]Error:[/red] {err}")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
