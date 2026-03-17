"""Workspace file construction — template loading, extraPaths generation, write/read."""

from __future__ import annotations

import hashlib
import json
import re
from importlib import resources
from pathlib import Path

import yaml

from gishant_scripts.task_workspace.config import TaskWorkspaceConfig

# ---------------------------------------------------------------------------
# JSONC helpers (workspace files use // comments and trailing commas)
# ---------------------------------------------------------------------------


def _strip_jsonc(text: str) -> str:
    """Strip block comments, line comments, and trailing commas from JSONC text."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r'(?<!:)//[^\n]*', "", text)
    text = re.sub(r",\s*(?=[}\]])", "", text)
    return text


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------


def load_workspace_template() -> dict:
    """Load the static workspace-settings YAML template and return as a dict."""
    pkg = resources.files("gishant_scripts.task_workspace") / "templates"
    raw = (pkg / "workspace_settings.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(raw)


def compute_template_hash() -> str:
    """Compute a truncated SHA-256 hash of the workspace settings template."""
    pkg = resources.files("gishant_scripts.task_workspace") / "templates"
    raw = (pkg / "workspace_settings.yaml").read_text(encoding="utf-8")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Dynamic extraPaths
# ---------------------------------------------------------------------------


def generate_extra_paths(
    selected_repos: dict[str, Path],
    config: TaskWorkspaceConfig,
    *,
    display_name_for: dict[str, str] | None = None,
) -> list[str]:
    """Build the ``extraPaths`` list for the selected repos.

    Args:
        selected_repos: ``{display_name: repo_path}`` for repos in the workspace.
        config: Global task-workspace configuration.
        display_name_for: Optional ``{dir_name: display_name}`` reverse lookup.
            Built automatically when *None*.

    Returns:
        Ordered list of ``${workspaceFolder:<name>}/<sub>`` strings plus
        *config.global_extra_paths*.
    """
    if display_name_for is None:
        display_name_for = {path.name: name for name, path in selected_repos.items()}

    paths: list[str] = []

    for display_name, repo_path in selected_repos.items():
        dir_name = repo_path.name
        sub_paths = config.extra_paths.get(dir_name, [])
        for sub in sub_paths:
            paths.append(f"${{workspaceFolder:{display_name}}}/{sub}")

    paths.extend(config.global_extra_paths)
    return paths


# ---------------------------------------------------------------------------
# Workspace dict construction
# ---------------------------------------------------------------------------


def build_task_workspace(
    issue_slug: str,
    selected_repos: dict[str, Path],
    worktree_paths: dict[str, Path],
    config: TaskWorkspaceConfig,
    *,
    adopted_repos: set[str] | None = None,
) -> dict:
    """Build the workspace dict for a task.

    Args:
        issue_slug: Normalised slug used as the workspace filename stem.
        selected_repos: ``{display_name: original_repo_path}``.
        worktree_paths: ``{display_name: actual_path}`` — may be a worktree dir
            or the original repo dir (for adopted repos).
        config: Global task-workspace configuration.
        adopted_repos: Display names that are adopted (existing checkouts).
    """
    adopted_repos = adopted_repos or set()

    # -- Folders --
    folders: list[dict] = []
    for display_name, original_path in selected_repos.items():
        actual_path = worktree_paths.get(display_name, original_path)
        folder: dict = {"name": display_name, "path": str(actual_path)}

        # Per-folder interpreter for own-venv repos
        if original_path.name in config.own_venv:
            folder["settings"] = {
                "python.defaultInterpreterPath": f"${{workspaceFolder:{display_name}}}/.venv/bin/python",
            }

        folders.append(folder)

    # -- Settings from template --
    template = load_workspace_template()

    # Pull extensions out (top-level key, not inside settings)
    extensions = template.pop("extensions", None)

    settings: dict = dict(template)

    # Inject dynamic extraPaths — build from worktree display names
    wt_repos = {name: worktree_paths.get(name, path) for name, path in selected_repos.items()}
    extra = generate_extra_paths(wt_repos, config)

    settings["python.analysis.extraPaths"] = extra
    settings["python.autoComplete.extraPaths"] = extra
    settings["cursorpyright.analysis.extraPaths"] = extra

    # -- Meta --
    worktree_names = [n for n in selected_repos if n not in adopted_repos]

    workspace_dict: dict = {
        "__meta__": {
            "generator": "gishant task-workspace",
            "slug": issue_slug,
            "adopted": sorted(adopted_repos),
            "worktrees": sorted(worktree_names),
            "template_hash": compute_template_hash(),
        },
        "folders": folders,
        "settings": settings,
    }

    if extensions:
        workspace_dict["extensions"] = extensions

    return workspace_dict


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def write_workspace_file(issue_slug: str, ws_dict: dict, config: TaskWorkspaceConfig) -> Path:
    """Write the workspace dict as JSON to the workspaces directory."""
    out_path = config.workspaces_dir / f"{issue_slug}.code-workspace"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ws_dict, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def read_workspace_file(ws_file: Path) -> dict:
    """Read and parse a ``.code-workspace`` file (handles JSONC)."""
    return json.loads(_strip_jsonc(ws_file.read_text(encoding="utf-8")))


def read_workspace_meta(ws_file: Path) -> dict:
    """Read ``__meta__`` from a workspace file; return empty dict if absent or unreadable."""
    try:
        return read_workspace_file(ws_file).get("__meta__", {})
    except Exception:  # noqa: BLE001
        return {}


# ---------------------------------------------------------------------------
# Settings sync
# ---------------------------------------------------------------------------

DYNAMIC_SETTINGS_KEYS = [
    "python.analysis.extraPaths",
    "python.autoComplete.extraPaths",
    "cursorpyright.analysis.extraPaths",
]


def sync_workspace_settings(ws_file: Path, template: dict, template_hash: str) -> bool:
    """Sync template settings+extensions into an existing workspace file.

    Merge strategy: template wins (overwrites matching keys),
    but dynamic keys and workspace-only keys are preserved.

    Returns True if the file was modified.
    """
    ws_data = read_workspace_file(ws_file)
    current_settings = ws_data.get("settings", {})

    # Save dynamic values before merge
    saved_dynamic = {key: current_settings[key] for key in DYNAMIC_SETTINGS_KEYS if key in current_settings}

    # Separate extensions from template (top-level key, not inside settings)
    template_copy = dict(template)
    template_extensions = template_copy.pop("extensions", None)

    # Merge: template settings on top of current settings (template wins)
    merged_settings = {**current_settings, **template_copy}

    # Restore dynamic keys
    for key, value in saved_dynamic.items():
        merged_settings[key] = value

    ws_data["settings"] = merged_settings

    # Merge extensions (template wins on shared keys, preserve workspace-only keys)
    if template_extensions:
        current_extensions = ws_data.get("extensions", {})
        ws_data["extensions"] = {**current_extensions, **template_extensions}

    # Update template hash in __meta__
    meta = ws_data.setdefault("__meta__", {})
    meta["template_hash"] = template_hash

    ws_file.write_text(json.dumps(ws_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return True
