"""Task workspace CLI — new, adopt, modify, cleanup commands."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import questionary
import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from gishant_scripts.task_workspace.config import load_config
from gishant_scripts.task_workspace.git_ops import (
    create_worktree,
    get_default_branch,
    get_repo_status,
    list_local_branches,
    list_worktree_branches,
    migrate_checked_out_branch_to_worktree,
)
from gishant_scripts.task_workspace.repo_discovery import discover_repos
from gishant_scripts.task_workspace.ui import Q_STYLE, console, open_workspace_in_code, slugify, table_repo_name
from gishant_scripts.task_workspace.workspace_builder import (
    _strip_jsonc,
    build_task_workspace,
    compute_template_hash,
    load_workspace_template,
    read_workspace_meta,
    sync_workspace_settings,
    write_workspace_file,
)

app = typer.Typer(
    name="task-workspace",
    help="RDO Dev — Task Workspace Generator",
    rich_markup_mode="rich",
    no_args_is_help=True,
)


# ============================================================================
# Template drift detection
# ============================================================================


def _check_template_drift(config) -> None:
    """Check if the template has changed and prompt to sync stale workspaces."""
    current_hash = compute_template_hash()

    task_files = sorted(config.workspaces_dir.glob("*.code-workspace"))
    task_files = [f for f in task_files if f.stem != "rdo-dev"]

    if not task_files:
        return

    stale = [f for f in task_files if read_workspace_meta(f).get("template_hash") != current_hash]

    if not stale:
        return

    console.print(f"\n[yellow]⚠  Workspace template has changed — {len(stale)} workspace(s) are out of date.[/]")

    proceed = questionary.confirm(f"Update {len(stale)} workspace(s) now?", default=True, style=Q_STYLE).ask()

    if not proceed:
        console.print("[dim]Skipped. Run [cyan]task-workspace sync-settings[/] later.[/]\n")
        return

    template = load_workspace_template()
    for ws_file in stale:
        sync_workspace_settings(ws_file, template, current_hash)
        console.print(f"  [green]✔[/]  {ws_file.stem}")
    console.print()


# ============================================================================
# Base-branch selection helper
# ============================================================================


def _ask_base_branch(repo_name: str, branch_name: str, repo_path: Path) -> str | None:
    """Ask the user which branch to base *branch_name* off for *repo_name*.

    Presents all local branches, annotating any that are currently checked out
    in a worktree.  Returns ``None`` to use the repo's default branch.
    """
    default_b = get_default_branch(repo_path)
    all_branches = list_local_branches(repo_path)
    in_worktree = list_worktree_branches(repo_path)  # {branch: wt_path}

    choices: list[questionary.Choice] = [
        questionary.Choice(f"Default branch ({default_b})", value=None),
    ]
    for b in all_branches:
        if b == default_b:
            continue  # already covered by the first option
        label = b
        if b in in_worktree:
            wt_name = Path(in_worktree[b]).name
            label = f"{b}  [dim](worktree: {wt_name})[/]"
        choices.append(questionary.Choice(label, value=b))

    return questionary.select(
        f"Base '{branch_name}' for '{repo_name}' off:",
        choices=choices,
        style=Q_STYLE,
    ).ask()


# ============================================================================
# new command
# ============================================================================


@app.command()
def new(
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Preview without creating anything."),
) -> None:
    """[bold cyan]Interactive wizard[/] — create fresh worktrees + a VS Code workspace for a new issue.

    Each selected repo gets a new worktree on a shared branch name. Use [bold]adopt[/] instead
    if your repos are already checked out on their own WIP branches.
    """
    config = load_config()
    _check_template_drift(config)

    console.print(
        Panel.fit(
            "[bold cyan]RDO Dev — New Task Workspace[/]\n[dim]Creates git worktrees + a VS Code task workspace.[/]",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    with console.status("[dim]Scanning repositories…[/]"):
        repos = discover_repos(config)

    if not repos:
        console.print("[red]✖  No git repos found.[/]")
        raise typer.Exit(1)

    console.print(f"[dim]  Found {len(repos)} repositories.[/]\n")

    raw_issue = questionary.text(
        "Issue / ticket / branch name:",
        instruction="e.g. issue-123-kitsu-sync",
        style=Q_STYLE,
    ).ask()

    if not raw_issue:
        console.print("[red]Aborted.[/]")
        raise typer.Exit(1)

    issue_slug = slugify(raw_issue)
    if issue_slug != raw_issue:
        console.print(f"[dim]  Normalised → {issue_slug}[/]")

    raw_branch = questionary.text(
        "Branch name:",
        instruction=f"Press Enter to use '{issue_slug}'",
        style=Q_STYLE,
    ).ask()

    branch_name = raw_branch.strip() if raw_branch and raw_branch.strip() else issue_slug
    console.print(f"[dim]  Branch → {branch_name}[/]\n")

    chosen_names: list[str] = questionary.checkbox(
        "Select repositories for this task:",
        choices=list(repos.keys()),
        instruction="(↑↓ navigate  ·  Space to toggle  ·  Ctrl+A select all  ·  Enter confirm)",
        style=Q_STYLE,
    ).ask()

    if not chosen_names:
        console.print("[red]✖  No repos selected. Aborting.[/]")
        raise typer.Exit(1)

    selected_repos = {name: repos[name] for name in chosen_names}

    # Ask base branch per repo
    console.print()
    base_branches: dict[str, str | None] = {
        name: _ask_base_branch(name, branch_name, repos[name]) for name in chosen_names
    }

    console.print()
    table = Table(box=box.ROUNDED, border_style="dim", header_style="bold cyan", show_header=True)
    table.add_column("Setting", style="dim", no_wrap=True)
    table.add_column("Value")
    table.add_row("Issue slug", f"[bold]{issue_slug}[/]")
    table.add_row("Branch", f"[cyan]{branch_name}[/]")
    table.add_row("Repos selected", str(len(selected_repos)))
    for name in chosen_names:
        base = base_branches[name]
        base_label = f" [dim](from {base})[/]" if base else ""
        table.add_row("", f"[dim]• {table_repo_name(name)}[/]{base_label}")
    table.add_row(
        "Workspace file",
        f"[dim]{config.workspaces_dir / f'{issue_slug}.code-workspace'}[/]",
    )
    table.add_row("Worktrees root", f"[dim]{config.worktrees_dir / issue_slug}[/]")
    if dry_run:
        table.add_row("Mode", "[yellow bold]DRY RUN[/]")
    console.print(table)
    console.print()

    if not dry_run:
        proceed: bool = questionary.confirm("Looks good — proceed?", default=True, style=Q_STYLE).ask()
        if not proceed:
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(0)

    issue_wt_root = config.worktrees_dir / issue_slug
    worktree_paths: dict[str, Path] = {}

    console.print(f"\n[bold]Creating worktrees[/] in [cyan]{issue_wt_root}[/]\n")

    for display_name, repo_path in selected_repos.items():
        console.print(f"[bold]{display_name}[/]")
        wt_path = issue_wt_root / repo_path.name
        result = create_worktree(
            repo_path,
            wt_path,
            branch_name,
            base_branch=base_branches[display_name],
            dry_run=dry_run,
        )
        if result:
            worktree_paths[display_name] = result
        console.print()

    ws_dict = build_task_workspace(issue_slug, selected_repos, worktree_paths, config, adopted_repos=set())

    if dry_run:
        console.print(
            Panel(
                "[yellow]DRY RUN complete — nothing was written.[/]\nRun without [cyan]--dry-run[/] to apply.",
                border_style="yellow",
            )
        )
        return

    ws_file = write_workspace_file(issue_slug, ws_dict, config)
    console.print(f"[green]✔  Workspace file:[/] {ws_file}")

    open_now: bool = questionary.confirm("Open in VS Code now?", default=True, style=Q_STYLE).ask()
    if open_now:
        open_workspace_in_code(ws_file)

    console.print(
        Panel.fit(
            f"[bold green]Task '{issue_slug}' is ready![/]\n\n"
            f"[dim]Workspace :[/]  {ws_file}\n"
            f"[dim]Worktrees :[/]  {issue_wt_root}\n\n"
            "[dim]When done:[/]  "
            "[cyan]gishant task-workspace cleanup[/]",
            border_style="green",
            padding=(0, 2),
        )
    )


# ============================================================================
# adopt command
# ============================================================================


@app.command()
def adopt(
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Preview without creating anything."),
) -> None:
    """[bold cyan]Adopt existing WIP checkouts[/] into a VS Code task workspace.

    Use this when your repos are already checked out on feature branches (with or
    without uncommitted changes). The command migrates selected repositories into
    [bold]worktrees[/] so you can stop working from the main [dim]repos/[/] directories.
    """
    config = load_config()
    _check_template_drift(config)

    console.print(
        Panel.fit(
            "[bold cyan]RDO Dev — Adopt WIP Workspace[/]\n"
            "[dim]Builds a VS Code workspace around your existing checked-out branches.[/]",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    with console.status("[dim]Scanning repositories…[/]"):
        repos = discover_repos(config)
        statuses: dict[str, tuple[str, bool, bool]] = {name: get_repo_status(path) for name, path in repos.items()}

    if not repos:
        console.print("[red]✖  No git repos found.[/]")
        raise typer.Exit(1)

    # Status table
    status_table = Table(
        box=box.SIMPLE,
        border_style="dim",
        header_style="bold cyan",
        show_header=True,
        pad_edge=False,
    )
    status_table.add_column("Repository", style="bold", no_wrap=True)
    status_table.add_column("Branch", no_wrap=True)
    status_table.add_column("Status", no_wrap=True)

    default_branches: dict[str, str] = {}
    for name, path in repos.items():
        default_branches[name] = get_default_branch(path)

    for name, (branch, is_dirty, is_detached) in statuses.items():
        default_b = default_branches[name]
        on_default = branch == default_b and not is_detached

        branch_display = f"[dim]{branch}[/]" if on_default else f"[cyan]{branch}[/]"
        if is_detached:
            branch_display = f"[yellow](detached) {branch}[/]"

        if is_dirty:
            status_display = "[red]● dirty[/]"
        elif not on_default:
            status_display = "[green]✔ clean[/] [dim](WIP)[/]"
        else:
            status_display = "[dim]✔ on default[/]"

        status_table.add_row(table_repo_name(name), branch_display, status_display)

    console.print(status_table)
    console.print()

    chosen_names: list[str] = questionary.checkbox(
        "Select repositories for this task:",
        choices=list(repos.keys()),
        instruction="(↑↓ navigate  ·  Space to toggle  ·  Ctrl+A select all  ·  Enter confirm)",
        style=Q_STYLE,
    ).ask()

    if not chosen_names:
        console.print("[red]✖  No repos selected. Aborting.[/]")
        raise typer.Exit(1)

    selected_repos = {name: repos[name] for name in chosen_names}

    raw_slug = questionary.text(
        "Task slug / name:",
        instruction="e.g. USER-319  (used as the workspace filename)",
        style=Q_STYLE,
    ).ask()

    if not raw_slug:
        console.print("[red]Aborted.[/]")
        raise typer.Exit(1)

    issue_slug = slugify(raw_slug)
    if issue_slug != raw_slug:
        console.print(f"[dim]  Normalised → {issue_slug}[/]")

    # Determine target branch per repo
    worktree_paths: dict[str, Path] = {}
    target_branch_repos: dict[str, str] = {}
    base_branches: dict[str, str | None] = {}
    migrate_checked_out_repos: set[str] = set()

    for name in chosen_names:
        branch, is_dirty, is_detached = statuses[name]
        default_b = default_branches[name]
        on_default = branch == default_b and not is_detached

        if is_detached:
            raw_detached_branch = questionary.text(
                f"[{name}] is detached at [yellow]{branch}[/]. Branch name for worktree:",
                instruction=f"Press Enter to use '{issue_slug}'",
                style=Q_STYLE,
            ).ask()
            target_branch = (
                raw_detached_branch.strip() if raw_detached_branch and raw_detached_branch.strip() else issue_slug
            )
            target_branch_repos[name] = target_branch
            base_branches[name] = None
        elif not on_default or is_dirty:
            target_branch_repos[name] = branch
            base_branches[name] = None
            migrate_checked_out_repos.add(name)
        else:
            raw_new_branch = questionary.text(
                f"[{name}] is on [cyan]{branch}[/] (clean). New branch name:",
                instruction=f"Press Enter to use '{issue_slug}'",
                style=Q_STYLE,
            ).ask()
            new_branch = raw_new_branch.strip() if raw_new_branch and raw_new_branch.strip() else issue_slug
            target_branch_repos[name] = new_branch
            base_branches[name] = _ask_base_branch(name, new_branch, repos[name])

    # Strategy summary
    console.print()
    summary = Table(box=box.ROUNDED, border_style="dim", header_style="bold cyan", show_header=True)
    summary.add_column("Repository", no_wrap=True)
    summary.add_column("Branch", no_wrap=True)
    summary.add_column("Strategy")

    for name in chosen_names:
        branch, is_dirty, _ = statuses[name]
        dirty_tag = " [red]●[/]" if is_dirty else ""
        if name in migrate_checked_out_repos:
            summary.add_row(
                table_repo_name(name),
                f"[cyan]{branch}[/]{dirty_tag}",
                "[green]migrate[/] [dim](move current branch into worktree)[/]",
            )
        else:
            new_b = target_branch_repos.get(name, issue_slug)
            base = base_branches.get(name)
            base_label = f" [dim]from {base}[/]" if base else ""
            summary.add_row(
                table_repo_name(name),
                f"[cyan]{new_b}[/]{base_label}",
                "[blue]new worktree[/]",
            )

    summary.add_row(
        "[dim]workspace file[/]",
        "",
        f"[dim]{config.workspaces_dir / f'{issue_slug}.code-workspace'}[/]",
    )
    if dry_run:
        summary.add_row("mode", "", "[yellow bold]DRY RUN[/]")
    console.print(summary)
    console.print()

    if not dry_run:
        proceed: bool = questionary.confirm("Looks good — proceed?", default=True, style=Q_STYLE).ask()
        if not proceed:
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(0)

    # Create/migrate worktrees
    issue_wt_root = config.worktrees_dir / issue_slug
    console.print(f"\n[bold]Creating worktrees[/] in [cyan]{issue_wt_root}[/]\n")
    for name in chosen_names:
        repo_path = repos[name]
        target_branch = target_branch_repos[name]
        wt_path = issue_wt_root / repo_path.name
        console.print(f"[bold]{name}[/]")

        if name in migrate_checked_out_repos:
            result = migrate_checked_out_branch_to_worktree(
                repo_path=repo_path,
                worktree_path=wt_path,
                branch=target_branch,
                default_branch=default_branches[name],
                repo_label=name,
                issue_slug=issue_slug,
                dry_run=dry_run,
            )
        else:
            result = create_worktree(
                repo_path,
                wt_path,
                target_branch,
                base_branch=base_branches.get(name),
                dry_run=dry_run,
            )

        if result:
            worktree_paths[name] = result
        console.print()

    failed_names = [name for name in chosen_names if name not in worktree_paths]
    if failed_names:
        console.print("\n[red]✖  Some worktrees failed; workspace file was not created.[/]")
        for name in failed_names:
            console.print(f"  [red]•[/] {table_repo_name(name)}")
        console.print("\n[dim]Fix the failing repos (or re-run with fewer selections), then run adopt again.[/]")
        raise typer.Exit(1)

    ws_dict = build_task_workspace(issue_slug, selected_repos, worktree_paths, config, adopted_repos=set())

    if dry_run:
        console.print(
            Panel(
                "[yellow]DRY RUN complete — nothing was written.[/]\nRun without [cyan]--dry-run[/] to apply.",
                border_style="yellow",
            )
        )
        return

    ws_file = write_workspace_file(issue_slug, ws_dict, config)
    console.print(f"[green]✔  Workspace file:[/] {ws_file}")

    open_now: bool = questionary.confirm("Open in VS Code now?", default=True, style=Q_STYLE).ask()
    if open_now:
        open_workspace_in_code(ws_file)

    migrated_count = len(migrate_checked_out_repos)
    worktree_count = len(chosen_names)
    console.print(
        Panel.fit(
            f"[bold green]Task '{issue_slug}' is ready![/]\n\n"
            f"[dim]Workspace :[/]  {ws_file}\n"
            f"[dim]Migrated  :[/]  {migrated_count} repo(s) — branch moved from repos/ to worktrees/\n"
            f"[dim]Worktrees :[/]  {worktree_count} repo(s) — workspace points only to worktrees/\n\n"
            "[dim]When done:[/]  "
            "[cyan]gishant task-workspace cleanup[/]",
            border_style="green",
            padding=(0, 2),
        )
    )


# ============================================================================
# modify command
# ============================================================================


@app.command()
def modify(
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Preview without creating anything."),
) -> None:
    """[bold cyan]Add or remove repositories[/] from an existing task workspace."""
    config = load_config()
    _check_template_drift(config)

    console.print(
        Panel.fit(
            "[bold cyan]RDO Dev — Modify Task Workspace[/]\n[dim]Add or remove repositories from an existing task.[/]",
            border_style="cyan",
            padding=(0, 2),
        )
    )

    task_files = {f.stem: f for f in config.workspaces_dir.glob("*.code-workspace")}
    # Exclude the master workspace
    task_files.pop("rdo-dev", None)

    if not task_files:
        console.print("[dim]No task workspaces found.[/]")
        raise typer.Exit(0)

    slug: str = questionary.select(
        "Select task to modify:",
        choices=sorted(task_files.keys()),
        style=Q_STYLE,
    ).ask()

    if not slug:
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(0)

    ws_file = task_files[slug]
    ws_data = json.loads(_strip_jsonc(ws_file.read_text(encoding="utf-8")))
    meta = ws_data.get("__meta__", {})
    current_folders = ws_data.get("folders", [])
    current_repo_names = [f["name"] for f in current_folders]

    with console.status("[dim]Scanning repositories…[/]"):
        all_repos = discover_repos(config)

    choices = [questionary.Choice(name, checked=name in current_repo_names) for name in all_repos]

    chosen_names: list[str] = questionary.checkbox(
        f"Select repositories for task '{slug}':",
        choices=choices,
        instruction="(↑↓ navigate  ·  Space to toggle  ·  Ctrl+A select all  ·  Enter confirm)",
        style=Q_STYLE,
    ).ask()

    if chosen_names is None:
        console.print("[red]Aborted.[/]")
        raise typer.Exit(1)

    to_add = [n for n in chosen_names if n not in current_repo_names]
    to_remove = [n for n in current_repo_names if n not in chosen_names]

    if not to_add and not to_remove:
        console.print("[dim]No changes selected.[/]")
        raise typer.Exit(0)

    # Branch name for additions — always the task slug for consistency
    branch_name = meta.get("slug", slug)

    # Ask per-repo base branch for each addition
    base_branches: dict[str, str | None] = {
        name: _ask_base_branch(name, branch_name, all_repos[name]) for name in to_add
    }

    # Summary
    console.print()
    summary = Table(box=box.ROUNDED, border_style="dim", header_style="bold cyan", show_header=True)
    summary.add_column("Change", no_wrap=True)
    summary.add_column("Repository")
    summary.add_column("Type/Branch")

    for name in to_add:
        base = base_branches.get(name)
        base_label = f"[dim]from {base}[/]" if base else "[dim]from default[/]"
        summary.add_row("[green]+ ADD[/]", f"[bold]{name}[/]", f"[cyan]{branch_name}[/] {base_label}")
    for name in to_remove:
        strategy = "[red]remove worktree[/]" if name in meta.get("worktrees", []) else "[yellow]remove folder[/]"
        summary.add_row("[red]- REMOVE[/]", f"[dim]{name}[/]", strategy)

    if dry_run:
        summary.add_row("Mode", "[yellow bold]DRY RUN[/]", "")
    console.print(summary)
    console.print()

    if not dry_run:
        proceed: bool = questionary.confirm("Apply changes?", default=True, style=Q_STYLE).ask()
        if not proceed:
            console.print("[dim]Aborted.[/]")
            raise typer.Exit(0)

    # Execute removals
    issue_wt_root = config.worktrees_dir / slug
    for name in to_remove:
        if name in meta.get("worktrees", []):
            wt_path = None
            for f in current_folders:
                if f["name"] == name:
                    wt_path = Path(f["path"])
                    break

            if wt_path and wt_path.exists():
                source_repo = config.repos_dir / wt_path.name
                if source_repo.exists():
                    if dry_run:
                        console.print(f"  [green]✔  [DRY RUN][/] Would remove worktree: {name}")
                    else:
                        console.print(f"[red]Removing worktree:[/] {name}")
                        r = subprocess.run(
                            ["git", "worktree", "remove", "--force", str(wt_path)],
                            cwd=source_repo,
                            capture_output=True,
                            text=True,
                        )
                        if r.returncode != 0:
                            console.print(f"  [yellow]⚠  Failed:[/] {r.stderr.strip()}")
                        else:
                            console.print("  [green]✔  Removed[/]")
                else:
                    console.print(f"  [yellow]⚠  Source repo not found for '{name}', skipping worktree removal.[/]")

    # Execute additions
    worktree_paths: dict[str, Path] = {}
    for f in current_folders:
        if f["name"] in chosen_names:
            worktree_paths[f["name"]] = Path(f["path"])

    failed_additions: list[str] = []
    for name in to_add:
        console.print(f"[green]Adding repo:[/] [bold]{name}[/]")
        repo_path = all_repos[name]
        wt_path = issue_wt_root / repo_path.name
        result = create_worktree(
            repo_path,
            wt_path,
            branch_name,
            base_branch=base_branches.get(name),
            dry_run=dry_run,
        )
        if result:
            worktree_paths[name] = result
        else:
            failed_additions.append(name)

    if failed_additions:
        console.print("\n[red]✖  Some repos could not be added (worktree creation failed):[/]")
        for name in failed_additions:
            console.print(f"  [red]•[/] {table_repo_name(name)}")
        console.print("[dim]These repos will not be included in the workspace.[/]\n")

    # Build updated workspace — exclude repos whose worktree creation failed
    effective_chosen = [n for n in chosen_names if n not in failed_additions]
    selected_repos = {name: all_repos[name] for name in effective_chosen if name in all_repos}

    current_adopted = set(meta.get("adopted", []))
    new_adopted = {n for n in current_adopted if n in chosen_names}

    ws_dict = build_task_workspace(slug, selected_repos, worktree_paths, config, adopted_repos=new_adopted)

    if not dry_run:
        write_workspace_file(slug, ws_dict, config)
        console.print(f"\n[bold green]Updated workspace file![/] {ws_file.name}\n")
    else:
        console.print("\n[yellow bold]DRY RUN[/] — no changes saved.\n")


# ============================================================================
# cleanup command
# ============================================================================


@app.command()
def cleanup() -> None:
    """[bold red]Remove[/] a task workspace file and unregister its git worktrees.

    Adopted repos (existing checkouts) are never touched — only worktrees that
    were created by [bold]new[/] or [bold]adopt[/] are removed.
    """
    config = load_config()
    _check_template_drift(config)

    console.print(
        Panel.fit(
            "[bold red]RDO Dev — Cleanup Task[/]\n[dim]Unregisters git worktrees and removes the workspace file.[/]",
            border_style="red",
            padding=(0, 2),
        )
    )

    task_files = {f.stem: f for f in config.workspaces_dir.glob("*.code-workspace")}
    wt_dirs = {d.name: d for d in config.worktrees_dir.iterdir() if d.is_dir()} if config.worktrees_dir.exists() else {}

    task_files.pop("rdo-dev", None)

    all_slugs = sorted(set(task_files) | set(wt_dirs))

    if not all_slugs:
        console.print("[dim]No task workspaces or worktree directories found.[/]")
        raise typer.Exit(0)

    slug: str = questionary.select(
        "Select task to clean up:",
        choices=all_slugs,
        style=Q_STYLE,
    ).ask()

    if not slug:
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(0)

    ws_file = task_files.get(slug)
    wt_dir = wt_dirs.get(slug)

    meta = read_workspace_meta(ws_file) if ws_file else {}
    adopted_names: set[str] = set(meta.get("adopted", []))
    if adopted_names:
        console.print(
            "\n[dim]  Adopted repos (will not be touched):[/] "
            + ", ".join(f"[cyan]{n}[/]" for n in sorted(adopted_names))
        )

    console.print()
    if ws_file:
        console.print(f"  [dim]Workspace :[/] {ws_file}")
    if wt_dir:
        console.print(f"  [dim]Worktrees :[/] {wt_dir}")
    console.print()

    confirm: bool = questionary.confirm(f"Remove task '{slug}'?", default=False, style=Q_STYLE).ask()

    if not confirm:
        console.print("[dim]Aborted.[/]")
        raise typer.Exit(0)

    # Remove worktrees via git
    if wt_dir and wt_dir.exists():
        console.print("\n[bold]Removing worktrees…[/]\n")
        for repo_wt in sorted(wt_dir.iterdir()):
            if not repo_wt.is_dir():
                continue

            if repo_wt.name in adopted_names:
                console.print(f"  [dim]⊙  Skipping adopted:[/] {repo_wt.name}")
                continue

            source_repo = config.repos_dir / repo_wt.name
            if source_repo.exists():
                r = subprocess.run(
                    ["git", "worktree", "remove", "--force", str(repo_wt)],
                    cwd=source_repo,
                    capture_output=True,
                    text=True,
                )
                if r.returncode == 0:
                    console.print(f"  [green]✔  Removed:[/] {repo_wt.name}")
                else:
                    console.print(f"  [yellow]⚠  Failed for {repo_wt.name}:[/] {r.stderr.strip()}")
                    console.print(f"     Run [cyan]git worktree prune[/] in {source_repo} manually.")
            else:
                console.print(f"  [yellow]⚠  Source repo not found for '{repo_wt.name}', skipping.[/]")

        try:
            wt_dir.rmdir()
            console.print(f"  [green]✔  Removed directory:[/] {wt_dir}")
        except OSError:
            console.print(f"  [yellow]⚠  {wt_dir} not empty — check for leftover files.[/]")

    # Remove workspace file
    if ws_file and ws_file.exists():
        ws_file.unlink()
        console.print(f"\n[green]✔  Removed workspace file:[/] {ws_file.name}")

    console.print(f"\n[bold green]Done.[/] Task '{slug}' cleaned up.\n")


# ============================================================================
# sync-settings command
# ============================================================================


@app.command(name="sync-settings")
def sync_settings() -> None:
    """[bold cyan]Sync workspace settings[/] from the master template to all task workspaces.

    Re-applies settings and extensions from [bold]workspace_settings.yaml[/] to every
    existing task workspace. Dynamic paths (extraPaths, per-folder interpreters)
    are preserved.
    """
    config = load_config()

    template = load_workspace_template()
    current_hash = compute_template_hash()

    task_files = sorted(config.workspaces_dir.glob("*.code-workspace"))
    task_files = [f for f in task_files if f.stem != "rdo-dev"]

    if not task_files:
        console.print("[dim]No task workspaces found.[/]")
        raise typer.Exit(0)

    stale = []
    for ws_file in task_files:
        meta = read_workspace_meta(ws_file)
        if meta.get("template_hash") != current_hash:
            stale.append(ws_file)

    if not stale:
        console.print("[green]All workspaces are up to date.[/]")
        return

    console.print(f"[cyan]{len(stale)}[/] workspace(s) need updating:\n")
    for ws_file in stale:
        console.print(f"  [dim]•[/] {ws_file.stem}")
    console.print()

    proceed: bool = questionary.confirm(f"Update {len(stale)} workspace(s)?", default=True, style=Q_STYLE).ask()

    if not proceed:
        console.print("[dim]Skipped.[/]")
        return

    for ws_file in stale:
        sync_workspace_settings(ws_file, template, current_hash)
        console.print(f"  [green]✔[/]  {ws_file.stem}")

    console.print(f"\n[bold green]Updated {len(stale)} workspace(s).[/]")


# ============================================================================
# Entry point (standalone)
# ============================================================================


def typer_main() -> None:
    """Standalone entry point for the ``task-workspace`` script."""
    app()
