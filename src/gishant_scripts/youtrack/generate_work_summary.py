"""
Generate Work Summary from YouTrack Issues using Gemini AI.

This script fetches YouTrack issues where the user is involved (assigned or commented)
within a specified time period and generates a structured work summary using Google Gemini AI.

Output format:
- COMPLETED: Issues that are done/closed
- IN PROGRESS: Issues that are currently being worked on

For each issue, includes:
- Done: Completed work items
- Current Work: Ongoing activities
- Pending: Items waiting on others
- Blockers: Any obstacles
"""

import json
from datetime import datetime, timedelta

import click
from google import genai
from rich.console import Console
from rich.panel import Panel

from gishant_scripts.common.config import AppConfig
from gishant_scripts.common.errors import ConfigurationError
from gishant_scripts.youtrack.fetch_issues import YouTrackIssuesFetcher

# Available Gemini models
AVAILABLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash-exp",
]


def filter_issues_by_time(issues: list[dict], weeks: int) -> list[dict]:
    """
    Filter issues that were updated in the last N weeks.

    Args:
        issues: List of issue dictionaries
        weeks: Number of weeks to look back

    Returns:
        Filtered list of issues
    """
    console = Console()
    cutoff_date = datetime.now() - timedelta(weeks=weeks)
    cutoff_timestamp = int(cutoff_date.timestamp() * 1000)  # YouTrack uses milliseconds

    console.print(f"[cyan]Filtering issues updated after: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}[/cyan]")

    filtered = []
    for issue in issues:
        updated_timestamp = issue.get("updated_timestamp")

        if updated_timestamp and updated_timestamp >= cutoff_timestamp:
            filtered.append(issue)

    console.print(f"[green]Found {len(filtered)} issues updated in the last {weeks} weeks[/green]")
    return filtered


def filter_comments_by_time(issue: dict, weeks: int) -> dict:
    """
    Filter issue comments to only include those from the last N weeks.

    Args:
        issue: Issue dictionary
        weeks: Number of weeks to look back

    Returns:
        Issue dictionary with filtered comments
    """
    cutoff_date = datetime.now() - timedelta(weeks=weeks)
    cutoff_timestamp = int(cutoff_date.timestamp() * 1000)

    filtered_issue = issue.copy()
    original_comments = issue.get("comments", [])

    # Filter comments by timestamp
    filtered_comments = []
    for comment in original_comments:
        created_timestamp = comment.get("created_timestamp")
        if created_timestamp and created_timestamp >= cutoff_timestamp:
            filtered_comments.append(comment)

    filtered_issue["comments"] = filtered_comments
    filtered_issue["comments_count"] = len(filtered_comments)

    return filtered_issue


def prepare_issues_for_summary(issues: list[dict], weeks: int) -> dict:
    """
    Prepare issues data for Gemini AI processing.

    Args:
        issues: List of issue dictionaries
        weeks: Number of weeks (for context)

    Returns:
        Dictionary with categorized issues and metadata
    """
    console = Console()

    # Filter comments by time period for all issues
    # All issues passed here were already filtered by update time in filter_issues_by_time()
    # so we include all of them, just with filtered comments
    issues_with_filtered_comments = []
    for issue in issues:
        filtered_issue = filter_comments_by_time(issue, weeks)
        issues_with_filtered_comments.append(filtered_issue)

    console.print(
        f"[green]Found {len(issues_with_filtered_comments)} issues with activity in the last {weeks} weeks[/green]"
    )

    # Group issues by state for context
    state_groups = {}
    for issue in issues_with_filtered_comments:
        state = issue.get("state", "Unknown")
        if state not in state_groups:
            state_groups[state] = []
        state_groups[state].append(issue)

    return {
        "time_period_weeks": weeks,
        "total_issues": len(issues_with_filtered_comments),
        "state_groups": {state: len(issues) for state, issues in state_groups.items()},
        "issues": issues_with_filtered_comments,
    }


def generate_work_summary_with_gemini(
    data: dict,
    api_key: str,
    model: str = "gemini-2.5-flash",
) -> str:
    """
    Use Gemini AI to generate a structured work summary.

    Args:
        data: Prepared issues data
        api_key: Google AI API key
        model: Gemini model to use

    Returns:
        Generated work summary text
    """
    console = Console()
    client = genai.Client(api_key=api_key)

    # Create detailed prompt with strict formatting requirements
    prompt = f"""
You are a technical professional creating a work summary for management review.

TASK: Analyze the following YouTrack issues from the past {data["time_period_weeks"]} weeks and generate a STRUCTURED work summary.

CRITICAL FORMATTING REQUIREMENTS:

1. Group issues into TWO categories:
   - COMPLETED: Issues with state "Done", "Closed", "Resolved", or where work is clearly finished
   - IN PROGRESS: Issues with state "In Progress", "Open", "To Do", or where work is ongoing

2. For EACH issue, use EXACTLY this structure:

```
PIPE-XXX: Issue-Title
Done
• Bullet point of completed work item
• Another completed work item
• PR links, deployment info, etc.
Current Work
• What you're currently working on
• Or "None" if not applicable
Pending
• Items waiting on others (with person's name if mentioned)
• Or "None" if not applicable
Blockers
• Any obstacles preventing progress
• Or "None" if not applicable
```

3. IMPORTANT RULES:
   - Keep the EXACT issue ID format (e.g., PIPE-527, USER-362)
   - Replace spaces in titles with hyphens (e.g., "Fix the bug" → "Fix-the-bug")
   - Use bullet points (•) for lists under Done/Current Work/Pending/Blockers
   - If a section has no content, write "None" on a bullet point
   - Extract information from comments chronologically
   - Focus on concrete actions, PRs, deployments, decisions
   - Be specific with names when mentioning people
   - Include PR links if mentioned in comments or stored in github_links field

4. GITHUB PR LINKS:
   - Each issue may have a "github_links" field with GitHub PR/issue URLs
   - If github_links exist, include them in the "Done" section with format: "PR: [url]"
   - Also extract any GitHub links mentioned in comments
   - Example: "• PR: https://github.com/org/repo/pull/123"

5. ANALYSIS GUIDELINES:
   - "Done" items: Completed work, merged PRs, deployed features, resolved issues
   - "Current Work": Recently mentioned ongoing activities, work in progress
   - "Pending": Waiting for code review, testing by others, external dependencies
   - "Blockers": Technical issues, missing resources, dependencies blocking progress

6. DATE CONTEXT: Today is {datetime.now().strftime("%Y-%m-%d")}. All issues have activity in the last {data["time_period_weeks"]} weeks.

YOUTRACK ISSUES DATA:

Total Issues: {data["total_issues"]}
State Distribution: {json.dumps(data["state_groups"], indent=2)}

DETAILED ISSUES:
{json.dumps(data["issues"], indent=2)}

Generate the work summary now following the EXACT format specified above.
Start with "COMPLETED:" or "IN PROGRESS:" headers and list issues under each category.
"""

    console.print(f"[cyan]Generating work summary with {model}...[/cyan]")
    console.print("[dim]This may take 30-60 seconds...[/dim]")

    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
        )

        if not response.text:
            raise ValueError("Empty response from Gemini API")

        return str(response.text)

    except Exception as e:
        console.print(f"[red]Error generating summary: {e}[/red]")
        raise


@click.command()
@click.option(
    "--weeks",
    type=int,
    required=True,
    help="Number of weeks to look back for issues",
)
@click.option(
    "--model",
    type=click.Choice(AVAILABLE_MODELS, case_sensitive=False),
    default="gemini-2.5-flash",
    help="Gemini model to use for generation",
)
@click.option(
    "--save-to-file",
    type=str,
    help="Save output to specified file (e.g., work_summary.txt)",
)
@click.option(
    "--max-issues",
    type=int,
    default=100,
    help="Maximum number of issues to fetch",
)
def main(weeks: int, model: str, save_to_file: str | None, max_issues: int):
    """
    Generate work summary from YouTrack issues using Gemini AI.

    Fetches issues where you are involved (assigned or commented) from the last N weeks
    and generates a structured summary with Done/Current Work/Pending/Blockers sections.

    Examples:

        # Generate summary for last 4 weeks
        gishant youtrack-summary --weeks 4

        # Use a different model
        gishant youtrack-summary --weeks 2 --model gemini-2.5-pro

        # Save to file
        gishant youtrack-summary --weeks 4 --save-to-file my_summary.txt

    Prerequisites:
        - YOUTRACK_URL and YOUTRACK_API_TOKEN in environment
        - GOOGLE_AI_API_KEY in environment
    """
    console = Console()

    console.print(
        Panel.fit(
            f"[bold cyan]YouTrack Work Summary Generator[/bold cyan]\nTime period: Last {weeks} weeks\nModel: {model}",
            border_style="cyan",
        )
    )

    try:
        # Load configuration
        config = AppConfig()
        config.require_valid("youtrack", "google_ai")

        # Initialize YouTrack fetcher
        console.print("\n[cyan]Step 1: Connecting to YouTrack...[/cyan]")

        if not config.youtrack.url:
            raise ValueError("YouTrack URL not configured")
        if not config.youtrack.api_token:
            raise ValueError("YouTrack API token not configured")

        fetcher = YouTrackIssuesFetcher(
            base_url=config.youtrack.url,
            token=config.youtrack.api_token,
        )

        # Fetch issues
        console.print(f"[cyan]Step 2: Fetching issues (max {max_issues})...[/cyan]")
        issues = fetcher.fetch_issues_with_details(max_results=max_issues)

        if not issues:
            console.print("[yellow]No issues found where you are involved.[/yellow]")
            return 0

        console.print(f"[green]✓ Found {len(issues)} total issues[/green]")

        # Filter by time
        console.print(f"\n[cyan]Step 3: Filtering issues from last {weeks} weeks...[/cyan]")
        filtered_issues = filter_issues_by_time(issues, weeks)

        if not filtered_issues:
            console.print(f"[yellow]No issues updated in the last {weeks} weeks.[/yellow]")
            return 0

        # Prepare data for Gemini
        console.print("[cyan]Step 4: Preparing data for Gemini...[/cyan]")
        prepared_data = prepare_issues_for_summary(filtered_issues, weeks)

        if prepared_data["total_issues"] == 0:
            console.print(f"[yellow]No issues with activity in the last {weeks} weeks.[/yellow]")
            return 0

        # Generate summary with Gemini
        console.print("\n[cyan]Step 5: Generating work summary with Gemini...[/cyan]")

        if not config.google_ai.api_key:
            raise ValueError("Google AI API key not configured")

        summary = generate_work_summary_with_gemini(
            data=prepared_data,
            api_key=config.google_ai.api_key,
            model=model,
        )

        # Display results
        console.print("\n" + "=" * 80)
        console.print(Panel.fit("[bold green]WORK SUMMARY GENERATED[/bold green]", border_style="green"))
        console.print("=" * 80 + "\n")
        console.print(summary)
        console.print("\n" + "=" * 80)

        # Save to file if requested
        if save_to_file:
            with open(save_to_file, "w", encoding="utf-8") as f:
                f.write(summary)
            console.print(f"\n[green]✓ Saved to: {save_to_file}[/green]")

        # Summary stats
        console.print(f"\n[dim]Generated from {prepared_data['total_issues']} issues over {weeks} weeks[/dim]")
        console.print(f"[dim]Model: {model}[/dim]")

        return 0

    except ConfigurationError as e:
        console.print(f"\n[red]Configuration Error:[/red] {e}")
        console.print("\n[yellow]Please ensure the following are set in your .env file:[/yellow]")
        console.print("  - YOUTRACK_URL")
        console.print("  - YOUTRACK_API_TOKEN")
        console.print("  - GOOGLE_AI_API_KEY")
        return 1

    except Exception as e:
        console.print(f"\n[red]Error:[/red] {e}")
        import traceback

        console.print("\n[dim]" + traceback.format_exc() + "[/dim]")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
