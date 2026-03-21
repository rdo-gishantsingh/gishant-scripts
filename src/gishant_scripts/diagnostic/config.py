"""Central configuration for diagnostic infrastructure (Maya on Linux, Unreal on Windows)."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Path mapping between Linux and Windows mount points
# ---------------------------------------------------------------------------

PATH_MAP_LINUX_TO_WIN: dict[str, str] = {
    "/projects/": "P:\\",
    "/tech/": "Z:\\",
}

PATH_MAP_WIN_TO_LINUX: dict[str, str] = {v: k for k, v in PATH_MAP_LINUX_TO_WIN.items()}

# UNC paths for SSH sessions where mapped drives are unavailable
PATH_MAP_LINUX_TO_UNC: dict[str, str] = {
    "/projects/": "\\\\rdoshyd\\projects\\",
    "/tech/": "\\\\rdoshyd\\tech\\",
}


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinuxConfig:
    """Paths and settings for the Linux (Maya) side."""

    maya_bin: str = "/usr/autodesk/maya2025/bin/maya"
    ayon_launcher: str = "/tech/apps/rocky9.5/ayon/launcher/AYON-1.4.2-linux-rocky9/ayon"
    ayon_server_url: str = "http://localhost:5000"
    ayon_storage_dir: pathlib.Path = field(
        default_factory=lambda: pathlib.Path.home() / ".local/share/ayon-launcher-local",
    )
    diagnostic_base: str = "/tech/users/gisi/dev/_diagnostic"


@dataclass(frozen=True)
class WindowsConfig:
    """Paths and settings for the Windows (Unreal) side."""

    ssh_host: str = "gisi@10.1.68.205"
    unreal_bin: str = r"C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
    ayon_launcher: str = r"C:\Program Files\Ynput\AYON 1.4.2\ayon_console.exe"
    ayon_server_url: str = "http://10.1.69.24:5000"
    ayon_storage_dir: str = r"%USERPROFILE%\.local\share\ayon-launcher-local"
    diagnostic_base: str = r"Z:\users\gisi\dev\_diagnostic"


# Singleton instances
LINUX = LinuxConfig()
WINDOWS = WindowsConfig()


# ---------------------------------------------------------------------------
# Path conversion helpers
# ---------------------------------------------------------------------------


def linux_to_windows_path(path: str, *, unc: bool = False) -> str:
    """Convert a Linux path to its Windows equivalent.

    Args:
        path: Linux filesystem path.
        unc: If True, use UNC paths (``\\\\rdoshyd\\tech\\``) instead of
            drive letters (``Z:\\``). Needed in SSH sessions where mapped
            drives are unavailable.
    """
    path_map = PATH_MAP_LINUX_TO_UNC if unc else PATH_MAP_LINUX_TO_WIN
    for linux_prefix, win_prefix in path_map.items():
        if path.startswith(linux_prefix):
            return win_prefix + path[len(linux_prefix) :].replace("/", "\\")
    return path


def windows_to_linux_path(path: str) -> str:
    """Convert a Windows path to its Linux equivalent using PATH_MAP."""
    for win_prefix, linux_prefix in PATH_MAP_WIN_TO_LINUX.items():
        if path.startswith(win_prefix):
            return linux_prefix + path[len(win_prefix) :].replace("\\", "/")
    return path


def get_results_dir(issue_name: str) -> pathlib.Path:
    """Return the results directory for a given issue, creating it if needed."""
    results_dir = pathlib.Path(LINUX.diagnostic_base) / "issues" / issue_name / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir
