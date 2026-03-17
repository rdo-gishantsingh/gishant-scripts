"""Task workspace configuration — dataclass + YAML loading with env-var overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

import yaml


@dataclass
class TaskWorkspaceConfig:
    """All settings needed by the task workspace tool."""

    repos_dir: Path
    worktrees_dir: Path
    workspaces_dir: Path

    deny_list: list[str] = field(default_factory=list)
    display_names: dict[str, str] = field(default_factory=dict)
    extra_paths: dict[str, list[str]] = field(default_factory=dict)
    own_venv: list[str] = field(default_factory=list)
    global_extra_paths: list[str] = field(default_factory=list)


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (mutates *base*)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def load_config() -> TaskWorkspaceConfig:
    """Build a :class:`TaskWorkspaceConfig` from packaged defaults + user overrides + env vars."""
    # 1. Load packaged defaults
    pkg = resources.files("gishant_scripts.task_workspace")
    default_text = (pkg / "config_default.yaml").read_text(encoding="utf-8")
    data: dict = yaml.safe_load(default_text)

    # 2. Deep-merge user override (if it exists)
    user_file = Path("~/.config/gishant/task_workspace.yaml").expanduser()
    if user_file.is_file():
        user_data = yaml.safe_load(user_file.read_text(encoding="utf-8")) or {}
        _deep_merge(data, user_data)

    # 3. Env-var overrides for paths
    paths = data.get("paths", {})
    env_map = {
        "TASK_WS_REPOS_DIR": "repos_dir",
        "TASK_WS_WORKTREES_DIR": "worktrees_dir",
        "TASK_WS_WORKSPACES_DIR": "workspaces_dir",
    }
    for env_key, path_key in env_map.items():
        val = os.environ.get(env_key)
        if val:
            paths[path_key] = val

    # 4. Expand ~ in global_extra_paths
    raw_global = data.get("global_extra_paths", [])
    expanded_global = [str(_expand(p)) for p in raw_global]

    return TaskWorkspaceConfig(
        repos_dir=_expand(paths.get("repos_dir", "~/dev/repos")),
        worktrees_dir=_expand(paths.get("worktrees_dir", "~/dev/worktrees")),
        workspaces_dir=_expand(paths.get("workspaces_dir", "~/dev/workspaces")),
        deny_list=data.get("deny_list", []),
        display_names=data.get("display_names", {}),
        extra_paths=data.get("extra_paths", {}),
        own_venv=data.get("own_venv", []),
        global_extra_paths=expanded_global,
    )
