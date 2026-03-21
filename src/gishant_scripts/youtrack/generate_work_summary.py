"""Generate Work Summary from YouTrack Issues using Gemini AI.

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

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

import typer
from rich.box import SIMPLE
from rich.console import Console
from rich.console import Group as RichGroup
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from gishant_scripts._core.config import AppConfig
from gishant_scripts._core.errors import ConfigurationError
from gishant_scripts._core.gemini import (
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


def load_work_logs(worktrees_dir: Path | None = None) -> dict[str, str]:
    """Load WORK_LOG.md files from all worktrees and map them to YouTrack ticket IDs.

    Scans ``~/dev/worktrees/<slug>/WORK_LOG.md``. Recognises slugs of the form
    ``pipe-NNN`` → ``PIPE-NNN`` and ``user-NNN`` → ``USER-NNN``.

    Args:
        worktrees_dir: Path to the worktrees directory. Defaults to ``~/dev/worktrees``.

    Returns:
        Dict mapping ticket ID (e.g. ``"PIPE-523"``) to ``WORK_LOG.md`` content.

    """
    if worktrees_dir is None:
        worktrees_dir = Path.home() / "dev" / "worktrees"

    if not worktrees_dir.is_dir():
        return {}

    slug_pattern = re.compile(r"^(pipe|user)-(\d+)", re.IGNORECASE)
    work_logs: dict[str, str] = {}

    for slug_dir in worktrees_dir.iterdir():
        if not slug_dir.is_dir():
            continue
        log_file = slug_dir / "WORK_LOG.md"
        if not log_file.is_file():
            continue
        match = slug_pattern.match(slug_dir.name)
        if not match:
            continue
        ticket_id = f"{match.group(1).upper()}-{match.group(2)}"
        content = log_file.read_text(encoding="utf-8").strip()
        if content:
            work_logs[ticket_id] = content

    return work_logs


def filter_issues_by_time(issues: list[dict], weeks: int) -> list[dict]:
    """Filter issues that were updated in the last N weeks.

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
    """Filter issue comments to only include those from the last N weeks.

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


def prepare_issues_for_summary(
    issues: list[dict],
    weeks: int,
    work_logs: dict[str, str] | None = None,
    user_login: str | None = None,
) -> dict:
    """Prepare issues data for Gemini AI processing.

    Args:
        issues: List of issue dictionaries.
        weeks: Number of weeks (for context).
        work_logs: Optional dict mapping ticket ID to WORK_LOG.md content.
            When provided, each matching issue gets a ``work_log`` field injected.
        user_login: Login of the report owner. Used to compute ``user_role`` per
            issue so Gemini can decide whether to include, skip, or flag a handoff.

    Returns:
        Dictionary with categorized issues and metadata.

    """
    # Filter comments by time period for all issues.
    # All issues passed here were already filtered by update time in filter_issues_by_time()
    # so we include all of them, just with filtered comments.
    issues_with_filtered_comments = []
    for issue in issues:
        filtered_issue = filter_comments_by_time(issue, weeks)

        # Inject WORK_LOG.md content when available — Claude session notes capture
        # technical detail that may not be reflected in the YouTrack description.
        if work_logs:
            ticket_id = filtered_issue.get("id") or filtered_issue.get("idReadable") or ""
            log_content = work_logs.get(ticket_id)
            if log_content:
                filtered_issue["work_log"] = log_content

        # Compute user_role so the prompt can apply ownership-aware filtering.
        #
        # Roles (mutually exclusive, in priority order):
        #   reporter_only         — user filed the ticket but is not the assignee and has
        #                           no comments in the reporting period; they raised it for
        #                           IT or another team member → Gemini should skip it.
        #   assignee_active       — user is current assignee AND has recent comments.
        #   assignee_quiet        — user is current assignee but no recent comments
        #                           (e.g. blocked, waiting).
        #   contributor_handed_off — user commented recently but is no longer assignee;
        #                           work was handed off → Gemini should note the transition.
        #   contributor           — user commented recently but was never the assignee.
        #   watcher               — user has no recent involvement at all → skip.
        if user_login:
            is_reporter = filtered_issue.get("reporter_login", "") == user_login
            is_assignee = filtered_issue.get("user_is_assignee", False)
            recent_user_comments = sum(
                1 for c in filtered_issue.get("comments", []) if c.get("author_login") == user_login
            )
            had_recent_activity = recent_user_comments > 0
            ever_commented = filtered_issue.get("user_commented", False)

            if is_reporter and not is_assignee and not had_recent_activity:
                role = "reporter_only"
            elif is_assignee and had_recent_activity:
                role = "assignee_active"
            elif is_assignee and not had_recent_activity:
                role = "assignee_quiet"
            elif not is_assignee and had_recent_activity and ever_commented:
                role = "contributor_handed_off"
            elif not is_assignee and had_recent_activity:
                role = "contributor"
            else:
                role = "watcher"

            filtered_issue["user_role"] = role
            filtered_issue["user_recent_comment_count"] = recent_user_comments

        issues_with_filtered_comments.append(filtered_issue)

    # Group issues by state for context.
    state_groups: dict[str, list[dict]] = {}
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
    audience: str = "management",
    *,
    show_progress: bool = True,
) -> str:
    """Use Gemini AI to generate a structured work summary.

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

    prompt = f"""\
{person_instruction}

Analyze the YouTrack issues below (last {data["time_period_weeks"]} weeks, as of {datetime.now().strftime("%Y-%m-%d")}) \
and produce a work summary for management review.

IMPORTANT: The output will be copy-pasted directly into Google Chat/Meet. \
Google Chat only supports: *bold* (SINGLE asterisk), bare URLs (auto-linked), and bullet points with `• `. \
Do NOT use Markdown syntax ([label](url), **double asterisks**, `- ` dashes) — Google Chat does not render it.

# Step 1 — Ownership filter (apply before anything else)

Each issue has a `user_role` field. Use it to decide whether to include the issue:

| user_role               | Action                                                                                       |
|-------------------------|----------------------------------------------------------------------------------------------|
| `reporter_only`         | *Skip entirely.* The user raised this ticket for IT or another team member — it is not their work. |
| `watcher`               | *Skip entirely.* The user has no recent involvement in this period.                          |
| `assignee_active`       | *Include normally.*                                                                          |
| `assignee_quiet`        | *Include normally.* User is assignee but blocked or waiting — show Pending/Blockers.        |
| `contributor`           | *Include normally.* User contributed comments but was not the formal assignee.               |
| `contributor_handed_off`| *Include with a transition note.* User was working on this and handed it to someone else — mention who took it over and why if the comments say so. |

# Step 2 — Classification

Assign each included issue to exactly one category:

- ✅ *COMPLETED* — state is "Done", "Closed", "Resolved", or all work is clearly finished.
- 🔄 *IN PROGRESS* — state is "In Progress", "Open", "To Do", or work is ongoing.

# Step 3 — Analysis

For each issue, read the comments chronologically and extract full narrative sentences:

| Section              | What to include                                                                                          |
|----------------------|----------------------------------------------------------------------------------------------------------|
| ✅ *Done*            | Completed work as full sentences — what was built/fixed, who confirmed it, PRs raised. List all GitHub PR URLs explicitly. |
| 🔨 *Current Work*   | Ongoing activities as full sentences — what is actively being investigated or developed right now.       |
| ⏳ *Pending*        | What is waiting and on whom — name the person, describe what they need to do.                            |
| 🚫 *Blockers*       | Specific obstacles — name the blocking ticket, person, or technical issue.                               |

Some issues include a `work_log` field. This contains timestamped technical notes written during Claude AI development sessions — they record exactly what was implemented, decisions made, and what remains. **When `work_log` is present, treat it as the most authoritative source for implementation detail.** It supplements the YouTrack description and comments; if they conflict, the work log reflects ground truth.

Rules for bullet content:
- Write full sentences, not fragments. E.g. "Fixed the FPS rounding issue so Unreal defaults to 23.976 for the Barbie project." not "Fixed FPS".
- If a ticket depends on or is related to another ticket, mention it explicitly. E.g. "Blocked by PIPE-772 which must be completed first."
- List every GitHub PR URL from the `github_links` field and from comment text, each on its own bullet under ✅ *Done*.
- Name people when they are mentioned in comments (reviewers, testers, collaborators).
- For `contributor_handed_off` issues: add a 🔁 *Handed off to [Name]* note explaining what was transitioned and why.
- *Verbosity:* aim for 2–3 bullets per section maximum. Combine related small actions into one sentence rather than listing each separately.
- *Deduplication:* if the same fix, PR, or decision is referenced across multiple tickets, mention it once under the most relevant ticket and cross-reference briefly in the others (e.g. "See also USER-747"). Do not repeat the same detail verbatim.
- Omit sections that have no items — do NOT write "None".

# Output format

Use this exact structure. No preamble, no summary, no closing text.

```
✅ *COMPLETED*

PROJ-42 — https://ro.youtrack.cloud/issue/PROJ-42 : Short issue title
✅ *Done*
• Built the X feature for the asset loader, resolving the import failure reported by Kiran.
• PR: https://github.com/org/repo/pull/99

PROJ-51 — https://ro.youtrack.cloud/issue/PROJ-51 : Another issue title
✅ *Done*
• Deployed the hotfix to production after confirmation from Yogesh that staging tests passed.

🔄 *IN PROGRESS*

PROJ-78 — https://ro.youtrack.cloud/issue/PROJ-78 : Third issue title
✅ *Done*
• Completed the initial prototype and demoed it to the Production team.
• PR: https://github.com/org/repo/pull/101
🔨 *Current Work*
• Integrating the prototype with the rendering pipeline based on feedback from the demo.
⏳ *Pending*
• Waiting for Alex to complete texture review before the PR can be merged.
🚫 *Blockers*
• Blocked by PROJ-77 — upstream API returns 500 on large payloads and must be resolved first.
```

After all issues, append this section if any PRs are awaiting review:

```
⏳ *Awaiting review:* N PRs
• PR: https://github.com/...
• PR: https://github.com/...
```

Collect every PR URL that appears under a ⏳ *Pending* "awaiting code review" bullet across all issues and list them here. If no PRs are pending review, omit this section entirely.

Formatting rules:
- Ticket IDs as plain text followed by an em dash and the bare URL: `PROJ-42 — https://...`.
- Issue titles use normal spaces (never hyphens).
- Use `•` (bullet) for all list items.
- Section labels are bold with single asterisks and prefixed with their emoji.
- Omit any section (Current Work, Pending, Blockers) with nothing to report.
- If a category (COMPLETED or IN PROGRESS) has no issues, omit it entirely.
- One blank line between issues; one blank line between categories.

---

Total: {data["total_issues"]}
State distribution: {json.dumps(data["state_groups"], indent=2)}

{json.dumps(data["issues"], indent=2)}
"""

    if audience == "standup":
        prompt = f"""\
{person_instruction}

Analyze the YouTrack issues below (last {data["time_period_weeks"]} weeks, as of {datetime.now().strftime("%Y-%m-%d")}) \
and produce a compact standup-style work summary.

IMPORTANT: The output will be copy-pasted directly into Google Chat/Meet. \
Google Chat only supports: *bold* (SINGLE asterisk), bare URLs (auto-linked), and bullet points with `• `. \
Do NOT use Markdown syntax.

# Ownership filter

Apply the same `user_role` filter as normal: skip `reporter_only` and `watcher` issues entirely.

# Output format

One bullet per included issue. Group under ✅ *COMPLETED* and 🔄 *IN PROGRESS*. \
Each bullet: ticket ID, bare URL, one sentence of what was done or is being done.

```
✅ *COMPLETED*
• PROJ-42 — https://ro.youtrack.cloud/issue/PROJ-42 : Closed after redirecting frame boundary work to USER-747.

🔄 *IN PROGRESS*
• PROJ-78 — https://ro.youtrack.cloud/issue/PROJ-78 : Testing preliminary fix for animcache loop; validating across project files.
• PROJ-99 — https://ro.youtrack.cloud/issue/PROJ-99 : Refactoring codebase; 3 PRs awaiting review.
```

Rules:
- One bullet per issue, max two short clauses.
- Mention the current blocker or pending person only if it is the key fact.
- No section labels (Done / Current Work / Pending / Blockers) — everything in one line.
- If a category has no issues, omit it entirely.

---

Total: {data["total_issues"]}
State distribution: {json.dumps(data["state_groups"], indent=2)}

{json.dumps(data["issues"], indent=2)}
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
        typer.Option(help="Directory to save reports when using --users (each file: work_summary_{username}.md)"),
    ] = Path(),
    max_issues: Annotated[
        int,
        typer.Option(help="Maximum number of issues to fetch per user"),
    ] = 100,
    audience: Annotated[
        Literal["management", "standup"],
        typer.Option(
            "--audience",
            help="Output style: 'management' (detailed, full sentences) or 'standup' (one bullet per ticket, compact)",
        ),
    ] = "management",
    exclude: Annotated[
        str | None,
        typer.Option(
            "--exclude",
            help="Comma-separated ticket IDs to force-exclude regardless of computed role (e.g. PIPE-123,USER-456)",
        ),
    ] = None,
    include: Annotated[
        str | None,
        typer.Option(
            "--include",
            help="Comma-separated ticket IDs to force-include regardless of computed role (e.g. PIPE-123,USER-456)",
        ),
    ] = None,
    debug_roles: Annotated[
        bool,
        typer.Option(
            "--debug-roles",
            help="Print a table showing each issue's computed user_role and exit without generating",
        ),
    ] = False,
) -> int:
    """Generate work summary from YouTrack issues using Gemini AI.

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

    user_logins: list[str | None] = [u.strip() for u in users.split(",") if u.strip()] if users else [None]
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

        # Load local WORK_LOG.md files from worktrees — these contain Claude session notes
        # that capture technical detail not always reflected in the YouTrack ticket.
        work_logs = load_work_logs()

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
                    console.print(f"[yellow]No issues updated in the last {weeks} weeks for {label}.[/yellow]\n")
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

                prepared_data = prepare_issues_for_summary(
                    filtered_issues,
                    weeks,
                    work_logs=work_logs,
                    user_login=user_login or user_info.get("login"),
                )

                # Apply --exclude and --include overrides.
                exclude_ids = {t.strip().upper() for t in exclude.split(",") if t.strip()} if exclude else set()
                include_ids = {t.strip().upper() for t in include.split(",") if t.strip()} if include else set()
                for issue in prepared_data["issues"]:
                    tid = (issue.get("id") or "").upper()
                    if tid in exclude_ids:
                        issue["user_role"] = "reporter_only"  # force skip
                    elif tid in include_ids:
                        issue["user_role"] = "assignee_active"  # force include

                # --debug-roles: print role table and stop before generation.
                if debug_roles:
                    live.stop()
                    from rich.table import Table as RichTable

                    role_table = RichTable(title=f"Issue roles for {label}", border_style="cyan")
                    role_table.add_column("Ticket", style="cyan")
                    role_table.add_column("Role", style="bold")
                    role_table.add_column("Assignee")
                    role_table.add_column("Recent comments", justify="right")
                    role_table.add_column("Summary")
                    for issue in prepared_data["issues"]:
                        role = issue.get("user_role", "unknown")
                        role_color = {
                            "reporter_only": "red",
                            "watcher": "red",
                            "assignee_active": "green",
                            "assignee_quiet": "yellow",
                            "contributor": "cyan",
                            "contributor_handed_off": "magenta",
                        }.get(role, "white")
                        role_table.add_row(
                            issue.get("id", "?"),
                            f"[{role_color}]{role}[/{role_color}]",
                            issue.get("assignee") or "—",
                            str(issue.get("user_recent_comment_count", "?")),
                            (issue.get("summary") or "")[:60],
                        )
                    console.print(role_table)
                    continue

                if prepared_data["total_issues"] == 0:
                    live.stop()
                    console.print(f"[yellow]No issues with activity in the last {weeks} weeks for {label}.[/yellow]\n")
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
                            audience=audience,
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

            console.print(f"\n[dim]Generated from {prepared_data['total_issues']} issues over {weeks} weeks[/dim]")
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
