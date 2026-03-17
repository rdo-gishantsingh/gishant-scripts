"""Repository discovery — scan repos dir for git repositories, apply deny-list."""

from __future__ import annotations

from pathlib import Path

from gishant_scripts.task_workspace.config import TaskWorkspaceConfig


def discover_repos(config: TaskWorkspaceConfig) -> dict[str, Path]:
    """Scan *config.repos_dir* for git repositories, returning ``{display_name: path}``.

    Directories in *config.deny_list* are excluded.  Display names come from
    *config.display_names*; directories without an explicit mapping use their
    directory name as-is.
    """
    repos: dict[str, Path] = {}

    if not config.repos_dir.is_dir():
        return repos

    for entry in sorted(config.repos_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in config.deny_list:
            continue
        if not (entry / ".git").exists():
            continue

        display_name = config.display_names.get(entry.name, entry.name)
        repos[display_name] = entry

    return dict(sorted(repos.items()))
