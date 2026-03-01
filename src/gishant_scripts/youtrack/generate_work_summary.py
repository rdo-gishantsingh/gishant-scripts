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
import re
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.box import SIMPLE
from rich.console import Console
from rich.console import Group as RichGroup
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from gishant_scripts.common.config import AppConfig
from gishant_scripts.common.errors import ConfigurationError
from gishant_scripts.common.gemini import (
    DEFAULT_MODEL,
    GeminiClient,
    GeminiModel,
    validate_model,
)
from gishant_scripts.youtrack.cli import YouTrackIssuesFetcher


class Phase(Enum):
    """Workflow phases for the work summary generator."""

    CONFIG = "Config"
    FETCH = "Fetch"
    FILTER = "Filter"
    PREPARE = "Prepare"
    GENERATE = "Generate"
    SAVE = "Save"


def build_header(weeks: int, model: str, user_count: int, current_user_label: str | None = None) -> Panel:
    """Build minimal header panel with config (time period, model, user)."""
    lines = [
        "[bold cyan]YouTrack Work Summary Generator[/bold cyan]",
        f"[dim]Time period: Last {weeks} weeks[/dim]",
        f"[dim]Model: {model}[/dim]",
        f"[dim]Users: {user_count}[/dim]",
    ]
    if current_user_label:
        lines.append(f"[dim]User: {current_user_label}[/dim]")
    return Panel.fit("\n".join(lines), border_style="cyan")


def build_phase_checklist(
    completed: set[Phase],
    current: Phase | None,
    status_message: str = "",
) -> Text:
    """Build phase checklist with checkmarks for completed, label for current."""
    order = [Phase.CONFIG, Phase.FETCH, Phase.FILTER, Phase.PREPARE, Phase.GENERATE, Phase.SAVE]
    parts = []
    for p in order:
        if p in completed:
            parts.append(f"[green]✓[/green] {p.value}")
        elif p is current:
            suffix = f" — [cyan]{status_message}[/cyan]" if status_message else ""
            parts.append(f"[cyan]→[/cyan] {p.value}{suffix}")
        else:
            parts.append(f"[dim]○ {p.value}[/dim]")
    return Text.from_markup("\n".join(parts))


def build_stats_table(
    total_fetched: int | None = None,
    after_filter: int | None = None,
    with_activity: int | None = None,
) -> Table | None:
    """Build minimal statistics table for issue counts."""
    if total_fetched is None and after_filter is None and with_activity is None:
        return None
    table = Table(box=SIMPLE, show_header=True, header_style="dim")
    table.add_column("Metric", style="dim")
    table.add_column("Count", justify="right")
    if total_fetched is not None:
        table.add_row("Total fetched", str(total_fetched))
    if after_filter is not None:
        table.add_row("After filter", str(after_filter))
    if with_activity is not None:
        table.add_row("With activity", str(with_activity))
    return table


def build_live_display(
    weeks: int,
    model: str,
    user_count: int,
    current_user_label: str | None,
    completed_phases: set[Phase],
    current_phase: Phase | None,
    status_message: str,
    total_fetched: int | None,
    after_filter: int | None,
    with_activity: int | None,
    *,
    show_spinner: bool = False,
) -> RichGroup:
    """Build the full live-updating display (header + phases + status + stats)."""
    header = build_header(weeks, model, user_count, current_user_label)
    phase_status = "" if show_spinner else status_message
    phases = build_phase_checklist(completed_phases, current_phase, phase_status)
    parts = [header, "", phases]
    if show_spinner:
        parts.append("")
        parts.append(RichGroup(Spinner("dots", text=status_message)))
    stats = build_stats_table(total_fetched, after_filter, with_activity)
    if stats is not None:
        parts.extend(["", stats])
    return RichGroup(*parts)


def filter_issues_by_time(issues: list[dict], weeks: int) -> list[dict]:
    """
    Filter issues that were updated in the last N weeks.

    Args:
        issues: List of issue dictionaries
        weeks: Number of weeks to look back

    Returns:
        Filtered list of issues
    """
    cutoff_date = datetime.now() - timedelta(weeks=weeks)
    cutoff_timestamp = int(cutoff_date.timestamp() * 1000)  # YouTrack uses milliseconds

    filtered = []
    for issue in issues:
        updated_timestamp = issue.get("updated_timestamp")
        if updated_timestamp and updated_timestamp >= cutoff_timestamp:
            filtered.append(issue)
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
    # Filter comments by time period for all issues
    # All issues passed here were already filtered by update time in filter_issues_by_time()
    # so we include all of them, just with filtered comments
    issues_with_filtered_comments = []
    for issue in issues:
        filtered_issue = filter_comments_by_time(issue, weeks)
        issues_with_filtered_comments.append(filtered_issue)

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
    model: GeminiModel = DEFAULT_MODEL,
    user_full_name: str | None = None,
    *,
    show_progress: bool = True,
) -> str:
    """
    Use Gemini AI to generate a structured work summary.

    Args:
        data: Prepared issues data
        api_key: Google AI API key
        model: Gemini model to use
        user_full_name: Full name of the user this report is for (for first-person wording)
        show_progress: Whether to print progress messages (set False when using Live TUI)

    Returns:
        Generated work summary text
    """
    gemini_client = GeminiClient(api_key=api_key, model=model)
    person_instruction = (
        f'You are {user_full_name}, so use "I" instead of "we" or "{user_full_name}" when writing.'
        if user_full_name
        else 'Use first person "I" when writing from the report owner\'s perspective.'
    )

    # Create detailed prompt with strict formatting requirements
    prompt = f"""
You are a technical professional creating a work summary for management review.

TASK: Analyze the following YouTrack issues from the past {data["time_period_weeks"]} weeks and generate a STRUCTURED work summary.

CRITICAL FORMATTING REQUIREMENTS (Markdown Format):

1. The entire report MUST be in valid **Markdown** format.

2. Group issues into TWO categories, each as a Markdown H2 heading:
   - ## COMPLETED
     (for issues with state "Done", "Closed", "Resolved", or where work is clearly finished)
   - ## IN PROGRESS
     (for issues with state "In Progress", "Open", "To Do", or where work is ongoing)

3. For EACH issue, follow this Markdown structure EXACTLY:

### [PIPE-XXX](https://ro.youtrack.cloud/issue/PIPE-XXX): Issue-Title-With-Hyphens

**Done**
- Bullet point of completed work item
- Another completed work item
- PR links, deployment info, etc.

**Current Work**
- What you're currently working on
- Or "None" if not applicable

**Pending**
- Items waiting on others (with person's name if mentioned)
- Or "None" if not applicable

**Blockers**
- Any obstacles preventing progress
- Or "None" if not applicable

(Rules for formatting the above:
- The issue header is an H3 with a Markdown link showing `[PIPE-XXX](https://ro.youtrack.cloud/issue/PIPE-XXX)` for the ticket ID, followed by the issue title using hyphens instead of spaces.
- Bullet lists use dash (`- `) not `•`.
- Each section title (Done, Current Work, Pending, Blockers) is bolded using double asterisks.
- If a section has no items, write `- None`.)

4. IMPORTANT RULES:
   - Always create the ticket ID as a clickable Markdown link as above, do not show the ID without the link.
   - Replace spaces in issue titles with hyphens (e.g., "Fix the bug" → "Fix-the-bug").
   - Use dash bullets (`-`) for all lists.
   - If a section has no content, write `- None`.
   - Extract information from comments chronologically.
   - Focus on concrete actions, PRs, deployments, decisions.
   - Be specific with names when mentioning people.
   - Include PR links if mentioned in comments or present in `github_links` field.
   - For PR links, add as: `- PR: <url>` in the **Done** section.

5. GITHUB PR LINKS:
   - Each issue may have a "github_links" field with GitHub PR/issue URLs.
   - If github_links exist, include them in the "Done" section as `- PR: <url>`.
   - Also extract any GitHub links mentioned in comments.
   - Example: `- PR: https://github.com/org/repo/pull/123`

6. ANALYSIS GUIDELINES:
   - "Done" items: Completed work, merged PRs, deployed features, resolved issues
   - "Current Work": Recently mentioned ongoing activities, work in progress
   - "Pending": Waiting for code review, testing by others, external dependencies
   - "Blockers": Technical issues, missing resources, dependencies blocking progress

7. DATE CONTEXT: Today is {datetime.now().strftime("%Y-%m-%d")}. All issues have activity in the last {data["time_period_weeks"]} weeks.

8. {person_instruction}

YOUTRACK ISSUES DATA:

Total Issues: {data["total_issues"]}
State Distribution: {json.dumps(data["state_groups"], indent=2)}

DETAILED ISSUES:
{json.dumps(data["issues"], indent=2)}

Generate the work summary in Markdown exactly as specified, starting with the ## COMPLETED or ## IN PROGRESS headings and listing each issue using the described format with ticket links.
"""

    try:
        result = gemini_client.generate_content(
            prompt,
            show_progress=show_progress,
            show_usage=show_progress,
        )
        gemini_client.print_usage_summary()
        return result
    except Exception as e:
        gemini_client.console.print(f"[red]Error generating summary: {e}[/red]")
        raise


def main(
    weeks: Annotated[
        int,
        typer.Option(help="Number of weeks to look back for issues"),
    ],
    model: Annotated[
        str,
        typer.Option(help="Gemini model to use for generation"),
    ] = DEFAULT_MODEL.model_name,
    save_to_file: Annotated[
        str | None,
        typer.Option("--save-to-file", help="Save output to specified file (single-user mode only)"),
    ] = None,
    users: Annotated[
        str | None,
        typer.Option(
            help="Comma-separated list of YouTrack usernames (e.g. gishant,john,jane). If omitted, report is for the authenticated user."
        ),
    ] = None,
    output_dir: Annotated[
        Path,
        typer.Option(
            help="Directory to save reports when using --users (each file: work_summary_{username}.md)"
        ),
    ] = Path("."),
    max_issues: Annotated[
        int,
        typer.Option(help="Maximum number of issues to fetch per user"),
    ] = 100,
) -> int:
    """
    Generate work summary from YouTrack issues using Gemini AI.

    Fetches issues where the user(s) are involved (assigned or commented) from the last N weeks
    and generates a structured summary with Done/Current Work/Pending/Blockers sections.

    Use --users to generate separate reports for multiple users; each is saved as
    work_summary_{username}.md in --output-dir.

    SECURITY NOTICE: This tool operates in READ-ONLY mode.
    It ONLY fetches data from YouTrack - NO modifications are made to any issues.

    Examples:

        # Generate summary for current user (last 4 weeks)
        gishant youtrack-summary --weeks 4

        # Save current user report to a file
        gishant youtrack-summary --weeks 4 --save-to-file my_summary.txt

        # Generate reports for multiple users (each in work_summary_{username}.md)
        gishant youtrack-summary --weeks 4 --users gishant,john,jane --output-dir ./reports

        # Single user by login, export with username as filename
        gishant youtrack-summary --weeks 4 --users gishant --output-dir .

    Prerequisites:
        - YOUTRACK_URL and YOUTRACK_API_TOKEN in environment
        - GOOGLE_AI_API_KEY in environment
    """
    console = Console()

    user_logins: list[str | None] = (
        [u.strip() for u in users.split(",") if u.strip()] if users else [None]
    )
    if users is not None:
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

    def make_render(user_label: str):
        def render(
            completed_phases: set[Phase],
            current_phase: Phase | None,
            status_message: str,
            total_fetched: int | None,
            after_filter: int | None,
            with_activity: int | None,
            show_spinner: bool = False,
        ):
            return build_live_display(
                weeks,
                model,
                len(user_logins),
                user_label,
                completed_phases,
                current_phase,
                status_message,
                total_fetched,
                after_filter,
                with_activity,
                show_spinner=show_spinner,
            )
        return render

    try:
        config = AppConfig()
        config.require_valid("youtrack", "google_ai")

        if not config.youtrack.url:
            raise ValueError("YouTrack URL not configured")
        if not config.youtrack.api_token:
            raise ValueError("YouTrack API token not configured")
        if not config.google_ai.api_key:
            raise ValueError("Google AI API key not configured")

        fetcher = YouTrackIssuesFetcher(
            base_url=config.youtrack.url,
            token=config.youtrack.api_token,
        )

        for idx, user_login in enumerate(user_logins, 1):
            label = user_login or "current user"
            current_user_label = f"{idx}/{len(user_logins)}: {label}"
            render = make_render(current_user_label)

            if user_login is None:
                user_info = fetcher.get_current_user()
            else:
                user_info = fetcher.get_user_by_login(user_login)
            user_full_name = user_info.get("fullName") or user_info.get("login") or ""
            raw_username = (user_login or user_info.get("login") or "current").strip()
            username_for_file = re.sub(r"[^\w.-]", "_", raw_username) or "user"

            completed_phases: set[Phase] = {Phase.CONFIG}
            current_phase = Phase.FETCH
            status_message = "Fetching issues..."
            total_fetched: int | None = None
            after_filter_count: int | None = None
            with_activity_count: int | None = None

            with Live(
                render(
                    completed_phases,
                    current_phase,
                    status_message,
                    total_fetched,
                    after_filter_count,
                    with_activity_count,
                ),
                console=console,
                refresh_per_second=10,
            ) as live:
                issues = fetcher.fetch_issues_with_details(
                    max_results=max_issues,
                    user_login=user_login,
                    silent=True,
                )

                if not issues:
                    live.stop()
                    console.print(f"[yellow]No issues found for {label}.[/yellow]\n")
                    continue

                completed_phases.add(Phase.FETCH)
                current_phase = Phase.FILTER
                total_fetched = len(issues)
                status_message = "Filtering by time..."
                live.update(
                    render(
                        completed_phases,
                        current_phase,
                        status_message,
                        total_fetched,
                        after_filter_count,
                        with_activity_count,
                    )
                )

                filtered_issues = filter_issues_by_time(issues, weeks)

                if not filtered_issues:
                    live.stop()
                    console.print(
                        f"[yellow]No issues updated in the last {weeks} weeks for {label}.[/yellow]\n"
                    )
                    continue

                completed_phases.add(Phase.FILTER)
                current_phase = Phase.PREPARE
                after_filter_count = len(filtered_issues)
                status_message = "Preparing data..."
                live.update(
                    render(
                        completed_phases,
                        current_phase,
                        status_message,
                        total_fetched,
                        after_filter_count,
                        with_activity_count,
                    )
                )

                prepared_data = prepare_issues_for_summary(filtered_issues, weeks)

                if prepared_data["total_issues"] == 0:
                    live.stop()
                    console.print(
                        f"[yellow]No issues with activity in the last {weeks} weeks for {label}.[/yellow]\n"
                    )
                    continue

                completed_phases.add(Phase.PREPARE)
                current_phase = Phase.GENERATE
                with_activity_count = prepared_data["total_issues"]
                status_message = "Generating with Gemini... (30-60s)"

                result_holder: list[str | None] = [None]
                exc_holder: list[Exception | None] = [None]

                def run_gemini() -> None:
                    try:
                        result_holder[0] = generate_work_summary_with_gemini(
                            data=prepared_data,
                            api_key=config.google_ai.api_key,
                            model=validate_model(model),
                            user_full_name=user_full_name or None,
                            show_progress=False,
                        )
                    except Exception as e:
                        exc_holder[0] = e

                thread = threading.Thread(target=run_gemini)
                thread.start()
                while thread.is_alive():
                    live.update(
                        render(
                            completed_phases,
                            current_phase,
                            status_message,
                            total_fetched,
                            after_filter_count,
                            with_activity_count,
                            show_spinner=True,
                        )
                    )
                    time.sleep(0.1)
                thread.join()

                if exc_holder[0]:
                    raise exc_holder[0]
                summary = result_holder[0]
                assert summary is not None

                completed_phases.add(Phase.GENERATE)
                current_phase = Phase.SAVE
                status_message = "Saving output..."
                live.update(
                    render(
                        completed_phases,
                        current_phase,
                        status_message,
                        total_fetched,
                        after_filter_count,
                        with_activity_count,
                    )
                )

                if users is not None:
                    out_path = output_dir / f"work_summary_{username_for_file}.md"
                    out_path.write_text(summary, encoding="utf-8")
                elif save_to_file:
                    Path(save_to_file).write_text(summary, encoding="utf-8")

                completed_phases.add(Phase.SAVE)
                live.update(
                    render(
                        completed_phases,
                        None,
                        "Done",
                        total_fetched,
                        after_filter_count,
                        with_activity_count,
                    )
                )

            console.print("\n" + "=" * 80)
            console.print(
                Panel.fit(
                    f"[bold green]WORK SUMMARY: {user_full_name or username_for_file}[/bold green]",
                    border_style="green",
                )
            )
            console.print("=" * 80 + "\n")
            console.print(summary)
            console.print("\n" + "=" * 80)

            if users is not None:
                out_path = output_dir / f"work_summary_{username_for_file}.md"
                console.print(f"\n[green]✓ Saved to: {out_path}[/green]")
            elif save_to_file:
                console.print(f"\n[green]✓ Saved to: {save_to_file}[/green]")

            console.print(
                f"\n[dim]Generated from {prepared_data['total_issues']} issues over {weeks} weeks[/dim]"
            )
            console.print(f"[dim]Model: {model}[/dim]\n")

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
    raise SystemExit(typer.run(main))
