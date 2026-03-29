"""Zed project format generation and parsing."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gishant_scripts.task_workspace.config import TaskWorkspaceConfig

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_WORKSPACE_FOLDER_RE = re.compile(r"^\$\{workspaceFolder:([^}]+)\}/(.+)$")


def resolve_extra_paths(extra_paths: list[str], folder_map: dict[str, str]) -> list[str]:
    """Resolve VS Code ``${workspaceFolder:name}/sub`` entries to absolute paths.

    Args:
        extra_paths: List of paths possibly containing ``${workspaceFolder:name}/sub`` entries.
        folder_map: Mapping of ``{display_name: absolute_folder_path}``.

    Returns:
        Deduplicated list of absolute paths with workspaceFolder variables substituted.
        Entries whose folder name is not in ``folder_map`` are silently skipped.

    """
    resolved: list[str] = []
    seen: set[str] = set()

    for p in extra_paths:
        m = _WORKSPACE_FOLDER_RE.match(p)
        if m:
            name, sub = m.group(1), m.group(2)
            folder_root = folder_map.get(name)
            if folder_root:
                abs_path = str(Path(folder_root) / sub)
                if abs_path not in seen:
                    resolved.append(abs_path)
                    seen.add(abs_path)
        elif p not in seen:
            resolved.append(p)
            seen.add(p)

    return resolved


# ---------------------------------------------------------------------------
# Settings generation
# ---------------------------------------------------------------------------


def build_zed_settings(folders: list[dict], vscode_settings: dict) -> dict:
    """Build a Zed ``settings.json`` dict from VS Code workspace data.

    Only project-level settings are included (valid in .zed/settings.json).
    User-level settings like fonts and themes belong in ~/.config/zed/settings.json
    and are intentionally excluded here to avoid spurious warnings.

    Maps VS Code settings keys to their Zed equivalents:

    - ``python.analysis.extraPaths`` -> ``lsp.pyright.settings.python.analysis.extraPaths``
    - ``editor.tabSize``             -> ``tab_size``
    - ``editor.formatOnSave``        -> ``format_on_save``
    - ``files.exclude`` patterns     -> ``file_scan_exclusions``

    Args:
        folders: VS Code workspace folder list - each entry has at least ``name`` and ``path``.
        vscode_settings: The ``settings`` dict from a ``.code-workspace`` file.

    Returns:
        Zed settings dict suitable for writing to ``.zed/settings.json``.

    """
    folder_map: dict[str, str] = {f["name"]: f["path"] for f in folders}
    zed: dict = {}

    # -- extraPaths -> lsp.pyright --
    # All three VS Code keys map to the same Zed location; use the first non-empty one.
    extra_paths: list[str] = []
    for key in ("python.analysis.extraPaths", "python.autoComplete.extraPaths", "cursorpyright.analysis.extraPaths"):
        val = vscode_settings.get(key)
        if val:
            extra_paths = val
            break

    if extra_paths:
        resolved = resolve_extra_paths(extra_paths, folder_map)
        if resolved:
            zed["lsp"] = {
                "pyright": {
                    "settings": {
                        "python": {
                            "analysis": {
                                "extraPaths": resolved,
                            },
                        },
                    },
                },
            }

    # -- Tab size --
    tab_size = vscode_settings.get("editor.tabSize")
    if tab_size is not None:
        zed["tab_size"] = tab_size

    # -- Format on save --
    # Zed accepts "on" or "off" at project level (not a dict like VS Code).
    format_on_save = vscode_settings.get("editor.formatOnSave")
    if format_on_save is not None:
        zed["format_on_save"] = "on" if format_on_save else "off"

    # -- File exclusions --
    # VS Code: {"**/.git": true, "**/__pycache__": true}  ->  Zed: ["**/.git", ...]
    files_exclude = vscode_settings.get("files.exclude")
    if files_exclude and isinstance(files_exclude, dict):
        exclusions = [pattern for pattern, enabled in files_exclude.items() if enabled]
        if exclusions:
            zed["file_scan_exclusions"] = exclusions

    return zed


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def write_zed_settings(slug: str, zed_settings: dict, config: TaskWorkspaceConfig) -> Path:
    """Write Zed ``settings.json`` to the worktree root ``.zed`` directory.

    Args:
        slug: Issue slug (must match the worktree root dir name under ``config.worktrees_dir``).
        zed_settings: Settings dict to serialise as JSON.
        config: Global task-workspace configuration.

    Returns:
        Path to the written ``settings.json`` file.

    """
    zed_dir = config.worktrees_dir / slug / ".zed"
    zed_dir.mkdir(parents=True, exist_ok=True)
    out_path = zed_dir / "settings.json"
    out_path.write_text(json.dumps(zed_settings, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def write_zed_launch_script(slug: str, folder_paths: list[str], config: TaskWorkspaceConfig) -> Path:
    """Write a bash script that opens all workspace folders in Zed.

    The script is written to ``config.workspaces_dir / "{slug}_open_in_zed.sh"``
    and made executable.

    Args:
        slug: Issue slug used as part of the script filename.
        folder_paths: Ordered list of absolute directory paths to pass to ``zed``.
        config: Global task-workspace configuration.

    Returns:
        Path to the written launch script.

    """
    header = ["#!/usr/bin/env bash", f"# Open all repos in Zed for task: {slug}"]

    if len(folder_paths) <= 1:
        cmd_line = "zed " + (folder_paths[0] if folder_paths else "")
        body = [cmd_line.strip()]
    else:
        args = " \\\n  ".join(folder_paths)
        body = [f"zed \\\n  {args}"]

    content = "\n".join(header + body) + "\n"

    out_path = config.workspaces_dir / f"{slug}_open_in_zed.sh"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    out_path.chmod(out_path.stat().st_mode | 0o111)  # make executable
    return out_path


def read_zed_settings(slug: str, config: TaskWorkspaceConfig) -> dict:
    """Read the Zed ``settings.json`` for a given slug.

    Args:
        slug: Issue slug.
        config: Global task-workspace configuration.

    Returns:
        Parsed settings dict, or an empty dict if the file does not exist.

    """
    settings_path = config.worktrees_dir / slug / ".zed" / "settings.json"
    if not settings_path.exists():
        return {}
    return json.loads(settings_path.read_text(encoding="utf-8"))


def read_zed_launch_script_paths(slug: str, config: TaskWorkspaceConfig) -> list[str]:
    r"""Parse folder paths from a Zed launch script generated by this tool.

    Handles both single-line (``zed /path``) and multi-line (``zed \`` continuation)
    forms produced by :func:`write_zed_launch_script`.

    Args:
        slug: Issue slug.
        config: Global task-workspace configuration.

    Returns:
        List of absolute folder paths extracted from the script, or an empty list
        if the script does not exist or contains no ``zed`` command.

    """
    script_path = config.workspaces_dir / f"{slug}_open_in_zed.sh"
    if not script_path.exists():
        return []

    # Join continuation lines so we can parse the zed command as a single line
    content = script_path.read_text(encoding="utf-8").replace("\\\n", " ")

    for line in content.splitlines():
        parts = line.strip().split()
        if parts and parts[0] == "zed":
            return [str(Path(p).expanduser()) for p in parts[1:] if p]

    return []
