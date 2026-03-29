"""Bidirectional migration between VS Code ``.code-workspace`` and Zed project formats.

Public API surface for the migration commands. Delegates to the lower-level
helpers in ``migrator`` and ``zed_builder``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gishant_scripts.task_workspace.config import TaskWorkspaceConfig

from gishant_scripts.task_workspace.migrator import vscode_to_zed, zed_to_vscode


def migrate_to_zed(ws_file: Path, config: TaskWorkspaceConfig) -> tuple[Path, Path]:
    """Convert a VS Code ``.code-workspace`` file to Zed project format.

    Reads the workspace file and generates two output files:

    * ``.zed/settings.json`` inside the worktree root — pyright ``extraPaths``
      and editor settings mapped to their Zed equivalents.
    * ``{slug}_open_in_zed.sh`` in the workspaces directory — executable bash
      script that opens all workspace folders in Zed.

    Args:
        ws_file: Path to the source ``.code-workspace`` file.
        config: Global task-workspace configuration.

    Returns:
        Tuple of ``(zed_settings_path, launch_script_path)``.

    """
    return vscode_to_zed(ws_file, config)


def migrate_to_vscode(issue_slug: str, config: TaskWorkspaceConfig) -> Path:
    """Convert a Zed project back to a VS Code ``.code-workspace`` file.

    Reads ``.zed/settings.json`` and ``{slug}_open_in_zed.sh`` for the given
    slug and reconstructs a ``.code-workspace`` file.  Run
    ``task-workspace sync-settings`` afterwards to re-apply the full VS Code
    template (extensions, theme, …) that are not stored in Zed format.

    Args:
        issue_slug: Task slug identifying the Zed workspace.
        config: Global task-workspace configuration.

    Returns:
        Path to the generated ``.code-workspace`` file.

    Raises:
        FileNotFoundError: If no Zed files exist for the given slug.

    """
    return zed_to_vscode(issue_slug, config)
