"""Git helpers — status, worktree creation/removal, branch operations."""

from __future__ import annotations

import subprocess
from pathlib import Path

from gishant_scripts.task_workspace.ui import console


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)  # noqa: S603


def get_repo_status(repo_path: Path) -> tuple[str, bool, bool]:
    """Return ``(current_branch, is_dirty, is_detached)`` for a repo."""
    head_r = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    if head_r.returncode != 0:
        return ("unknown", False, False)

    raw = head_r.stdout.strip()
    is_detached = raw == "HEAD"

    if is_detached:
        sha_r = _run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_path)
        branch = sha_r.stdout.strip() if sha_r.returncode == 0 else "HEAD"
    else:
        branch = raw

    dirty_r = _run(["git", "status", "--porcelain"], cwd=repo_path)
    is_dirty = bool(dirty_r.stdout.strip()) if dirty_r.returncode == 0 else False

    return (branch, is_dirty, is_detached)


def get_default_branch(repo_path: Path) -> str:
    """Return the default branch name for *repo_path* (``main``, ``master``, …)."""
    r = _run(["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_path)
    if r.returncode == 0:
        return r.stdout.strip().split("/")[-1]
    for candidate in ("main", "master", "develop"):
        if _run(["git", "rev-parse", "--verify", candidate], cwd=repo_path).returncode == 0:
            return candidate
    return "main"


def list_local_branches(repo_path: Path) -> list[str]:
    """Return all local branch names for *repo_path*, sorted alphabetically."""
    r = _run(
        ["git", "branch", "--list", "--format=%(refname:short)"],
        cwd=repo_path,
    )
    if r.returncode != 0:
        return []
    return sorted(line.strip() for line in r.stdout.splitlines() if line.strip())


def list_worktree_branches(repo_path: Path) -> dict[str, str]:
    """Return ``{branch: worktree_path}`` for every checked-out worktree of *repo_path*.

    The main worktree is included. Detached-HEAD worktrees are omitted.
    """
    r = _run(["git", "worktree", "list", "--porcelain"], cwd=repo_path)
    if r.returncode != 0:
        return {}

    result: dict[str, str] = {}
    wt_path = ""
    for line in r.stdout.splitlines():
        if line.startswith("worktree "):
            wt_path = line[len("worktree "):]
        elif line.startswith("branch "):
            branch = line[len("branch "):].replace("refs/heads/", "")
            result[branch] = wt_path
        elif line == "":
            wt_path = ""

    return result


def branch_exists_remote(repo_path: Path, branch: str) -> bool:
    r = _run(["git", "ls-remote", "--heads", "origin", branch], cwd=repo_path)
    return bool(r.stdout.strip())


def branch_exists_local(repo_path: Path, branch: str) -> bool:
    return _run(["git", "rev-parse", "--verify", branch], cwd=repo_path).returncode == 0


def create_worktree(
    repo_path: Path,
    worktree_path: Path,
    branch: str,
    *,
    base_branch: str | None = None,
    dry_run: bool = False,
) -> Path | None:
    """Create a git worktree at *worktree_path* on *branch*.

    Args:
        repo_path: Path to the source git repository.
        worktree_path: Path where the worktree should be created.
        branch: Branch name for the worktree.
        base_branch: Branch to create from when *branch* doesn't exist yet.
            Defaults to the repo's default branch (main/master).
        dry_run: If True, print what would happen without doing it.
    """
    if worktree_path.exists():
        console.print(f"  [yellow]⚠  Already exists, skipping:[/] {worktree_path.name}")
        return worktree_path

    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    if branch_exists_local(repo_path, branch):
        cmd = ["git", "worktree", "add", str(worktree_path), branch]
        strategy = "existing local branch"
    elif branch_exists_remote(repo_path, branch):
        cmd = ["git", "worktree", "add", "--track", "-b", branch, str(worktree_path), f"origin/{branch}"]
        strategy = "tracking remote"
    else:
        start = base_branch or get_default_branch(repo_path)
        cmd = ["git", "worktree", "add", "-b", branch, str(worktree_path), start]
        strategy = f"new branch from [cyan]{start}[/]"

    console.print(f"  [dim]$ {' '.join(str(c) for c in cmd)}[/]")

    if dry_run:
        console.print(f"  [green]✔  [DRY RUN][/] Would create worktree ({strategy})")
        return worktree_path

    result = _run(cmd, cwd=repo_path)
    if result.returncode != 0:
        console.print(f"  [red]✖  Failed:[/] {result.stderr.strip()}")
        return None

    console.print(f"  [green]✔  Created[/] ({strategy})")
    return worktree_path


def _switch_to_branch(repo_path: Path, branch: str) -> bool:
    """Switch repo to *branch*, creating a local tracking branch if needed."""
    sw = _run(["git", "switch", branch], cwd=repo_path)
    if sw.returncode == 0:
        return True
    track = _run(["git", "switch", "--track", "-c", branch, f"origin/{branch}"], cwd=repo_path)
    return track.returncode == 0


def migrate_checked_out_branch_to_worktree(
    repo_path: Path,
    worktree_path: Path,
    branch: str,
    default_branch: str,
    repo_label: str,
    issue_slug: str,
    *,
    dry_run: bool = False,
) -> Path | None:
    """Move an existing checked-out branch (and optional dirty state) into a worktree."""
    current_branch, is_dirty, is_detached = get_repo_status(repo_path)
    if is_detached:
        console.print(f"  [red]✖  Cannot migrate detached HEAD for {repo_label} automatically.[/]")
        return None

    if current_branch != branch:
        return create_worktree(repo_path, worktree_path, branch, dry_run=dry_run)

    if dry_run:
        console.print(f"  [dim]$ git -C {repo_path} switch {default_branch}[/]")
        if is_dirty:
            console.print("  [dim]$ git stash push -u -m <adopt-migration> && git stash pop in worktree[/]")
        console.print(f"  [dim]$ git worktree add {worktree_path} {branch}[/]")
        console.print("  [green]✔  [DRY RUN][/] Would migrate checked-out branch into worktree")
        return worktree_path

    stash_ref: str | None = None
    stash_msg = f"new-task-adopt:{issue_slug}:{repo_path.name}"

    if is_dirty:
        stash_push = _run(["git", "stash", "push", "-u", "-m", stash_msg], cwd=repo_path)
        if stash_push.returncode != 0:
            console.print(f"  [red]✖  Failed to stash changes:[/] {stash_push.stderr.strip()}")
            return None

        stash_list = _run(["git", "stash", "list", "--format=%gd:%s"], cwd=repo_path)
        if stash_list.returncode == 0:
            for line in stash_list.stdout.splitlines():
                if stash_msg in line:
                    stash_ref = line.split(":", 1)[0]
                    break

    if not _switch_to_branch(repo_path, default_branch):
        console.print(f"  [red]✖  Failed switching source repo to {default_branch} before migration.[/]")
        return None

    created = create_worktree(repo_path, worktree_path, branch, dry_run=False)
    if created is None:
        return None

    if stash_ref:
        apply_stash = _run(["git", "stash", "pop", stash_ref], cwd=worktree_path)
        if apply_stash.returncode != 0:
            console.print(
                f"  [yellow]⚠  Worktree created but stash apply had conflicts:[/] {apply_stash.stderr.strip()}"
            )
            console.print(f"     Resolve manually in [cyan]{worktree_path}[/]. Stash ref: [cyan]{stash_ref}[/]")
        else:
            console.print("  [green]✔  Restored uncommitted changes in worktree[/]")

    return created
