"""Bidirectional migration between VS Code ``.code-workspace`` and Zed project format."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gishant_scripts.task_workspace.config import TaskWorkspaceConfig

from gishant_scripts.task_workspace.workspace_builder import read_workspace_file, write_workspace_file
from gishant_scripts.task_workspace.zed_builder import (
    build_zed_settings,
    read_zed_launch_script_paths,
    read_zed_settings,
    write_zed_launch_script,
    write_zed_settings,
)


def vscode_to_zed(ws_file: Path, config: TaskWorkspaceConfig) -> tuple[Path, Path]:
    """Migrate a VS Code ``.code-workspace`` file to Zed project format.

    Reads the workspace file and produces two output files:

    - ``.zed/settings.json`` in the worktree root directory — contains Zed-equivalent
      settings (pyright ``extraPaths``, font family, tab size, file exclusions, …).
    - ``{slug}_open_in_zed.sh`` in the workspaces directory — executable bash script
      that opens all workspace folders in Zed.

    Args:
        ws_file: Path to the source ``.code-workspace`` file.
        config: Global task-workspace configuration.

    Returns:
        ``(zed_settings_path, launch_script_path)`` — paths to the two generated files.

    """
    ws_data = read_workspace_file(ws_file)
    meta = ws_data.get("__meta__", {})
    slug = meta.get("slug") or ws_file.stem

    folders: list[dict] = ws_data.get("folders", [])
    vscode_settings: dict = ws_data.get("settings", {})

    zed_settings = build_zed_settings(folders, vscode_settings)
    folder_paths = [f["path"] for f in folders]

    settings_path = write_zed_settings(slug, zed_settings, config)
    launch_path = write_zed_launch_script(slug, folder_paths, config)

    return settings_path, launch_path


def zed_to_vscode(slug: str, config: TaskWorkspaceConfig) -> Path:
    """Migrate a Zed project back to a VS Code ``.code-workspace`` file.

    Reads the ``.zed/settings.json`` and ``{slug}_open_in_zed.sh`` for the given slug
    and reconstructs a workspace dict that is written as a ``.code-workspace`` file.

    The generated file intentionally omits the VS Code template settings (editor theme,
    extensions, …) that are not stored in Zed format.  Run ``task-workspace sync-settings``
    afterwards to re-apply the full template.

    Args:
        slug: Issue slug that identifies both the worktree root directory and the launch script.
        config: Global task-workspace configuration.

    Returns:
        Path to the generated ``.code-workspace`` file.

    Raises:
        FileNotFoundError: If neither the ``.zed/settings.json`` nor the launch script
            exist for ``slug``.

    """
    zed_settings = read_zed_settings(slug, config)
    folder_paths = read_zed_launch_script_paths(slug, config)

    settings_path = config.worktrees_dir / slug / ".zed" / "settings.json"
    launch_path = config.workspaces_dir / f"{slug}_open_in_zed.sh"

    if not zed_settings and not folder_paths:
        msg = f"No Zed files found for slug '{slug}'. Expected {settings_path} or {launch_path}."
        raise FileNotFoundError(msg)

    # Reconstruct folders from launch script paths (dir name becomes display name)
    folders: list[dict] = [{"name": Path(p).name, "path": p} for p in folder_paths]

    # Reverse-map Zed settings → VS Code settings
    vscode_settings: dict = {}

    pyright_extra = (
        zed_settings.get("lsp", {})
        .get("pyright", {})
        .get("settings", {})
        .get("python", {})
        .get("analysis", {})
        .get("extraPaths", [])
    )
    if pyright_extra:
        # Populate all three VS Code keys that map to the same Zed source
        vscode_settings["python.analysis.extraPaths"] = pyright_extra
        vscode_settings["python.autoComplete.extraPaths"] = pyright_extra
        vscode_settings["cursorpyright.analysis.extraPaths"] = pyright_extra

    font_family = zed_settings.get("ui_font_family") or zed_settings.get("buffer_font_family")
    if font_family:
        vscode_settings["editor.fontFamily"] = font_family

    font_size = zed_settings.get("buffer_font_size")
    if font_size is not None:
        vscode_settings["editor.fontSize"] = font_size

    tab_size = zed_settings.get("tab_size")
    if tab_size is not None:
        vscode_settings["editor.tabSize"] = tab_size

    file_scan = zed_settings.get("file_scan_exclusions")
    if file_scan and isinstance(file_scan, list):
        vscode_settings["files.exclude"] = dict.fromkeys(file_scan, True)

    ws_dict: dict = {
        "__meta__": {
            "generator": "gishant task-workspace (migrated from zed)",
            "slug": slug,
            "adopted": [],
            "worktrees": [Path(p).name for p in folder_paths],
            "template_hash": "",
        },
        "folders": folders,
        "settings": vscode_settings,
    }

    return write_workspace_file(slug, ws_dict, config)
