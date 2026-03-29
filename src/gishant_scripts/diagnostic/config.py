"""Central configuration for diagnostic infrastructure (Maya on Linux, Unreal on Windows).

Both runners execute LOCALLY on their target OS.  Agent-deck sessions SSH
directly into the correct machine — no cross-machine SSH hops.

All hardcoded defaults can be overridden via environment variables.
"""

from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Path mapping between Linux and Windows mount points
# ---------------------------------------------------------------------------

PATH_MAP_LINUX_TO_WIN: dict[str, str] = {
    "/projects/": "P:\\",
    "/tech/": "Z:\\",
}

PATH_MAP_WIN_TO_LINUX: dict[str, str] = {v: k for k, v in PATH_MAP_LINUX_TO_WIN.items()}

# UNC paths for contexts where mapped drives are unavailable
_NAS_HOST = os.getenv("NAS_HOSTNAME", "rdoshyd")
PATH_MAP_LINUX_TO_UNC: dict[str, str] = {
    "/projects/": f"\\\\{_NAS_HOST}\\projects\\",
    "/tech/": f"\\\\{_NAS_HOST}\\tech\\",
}


# ---------------------------------------------------------------------------
# Config dataclasses — every field is overridable via env var
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinuxConfig:
    """Paths and settings for the Linux (Maya) side."""

    maya_bin: str = field(
        default_factory=lambda: os.getenv("MAYA_BIN", "/usr/autodesk/maya2025/bin/maya"),
    )
    ayon_launcher: str = field(
        default_factory=lambda: os.getenv(
            "AYON_LAUNCHER_PATH", "/tech/apps/rocky9.5/ayon/launcher/AYON-1.4.2-linux-rocky9/ayon"
        ),
    )
    ayon_server_url: str = field(
        default_factory=lambda: os.getenv("AYON_SERVER_URL", "http://localhost:5000"),
    )
    ayon_storage_dir: pathlib.Path = field(
        default_factory=lambda: pathlib.Path(
            os.getenv(
                "AYON_STORAGE_DIR",
                str(pathlib.Path.home() / ".local/share/ayon-launcher-local"),
            )
        ),
    )
    diagnostic_base: str = field(
        default_factory=lambda: os.getenv("DIAGNOSTIC_BASE_DIR", "/tech/users/gisi/dev/_diagnostic"),
    )


@dataclass(frozen=True)
class WindowsConfig:
    """Paths and settings for the Windows (Unreal) side.

    No ``ssh_host`` — the Unreal runner executes locally on Windows.
    Agent-deck sessions SSH directly into the Windows machine.
    """

    unreal_bin: str = field(
        default_factory=lambda: os.getenv(
            "UNREAL_BIN", r"C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
        ),
    )
    ayon_launcher: str = field(
        default_factory=lambda: os.getenv(
            "AYON_LAUNCHER_PATH_WIN", r"C:\Program Files\Ynput\AYON 1.4.2\ayon_console.exe"
        ),
    )
    ayon_server_url: str = field(
        default_factory=lambda: os.getenv("AYON_SERVER_URL_WIN", "http://10.1.69.24:5000"),
    )
    ayon_storage_dir: str = field(
        default_factory=lambda: os.getenv(
            "AYON_STORAGE_DIR_WIN",
            r"C:\Users\gisi\AppData\Local\Ynput\AYON",
        ),
    )
    diagnostic_base: str = field(
        default_factory=lambda: os.getenv("DIAGNOSTIC_BASE_DIR_WIN", r"Z:\users\gisi\dev\_diagnostic"),
    )
    diagnostic_base_unc: str = field(
        default_factory=lambda: os.getenv(
            "DIAGNOSTIC_BASE_UNC", rf"\\{os.getenv('NAS_HOSTNAME', 'rdoshyd')}\tech\users\gisi\dev\_diagnostic"
        ),
    )


# Singleton instances
LINUX = LinuxConfig()
WINDOWS = WindowsConfig()


# ---------------------------------------------------------------------------
# Path conversion helpers
# ---------------------------------------------------------------------------


def linux_to_windows_path(path: str, *, unc: bool = False) -> str:
    r"""Convert a Linux path to its Windows equivalent.

    Args:
        path: Linux filesystem path.
        unc: If True, use UNC paths (``\\\\<NAS_HOST>\\tech\\``) instead of
            drive letters (``Z:\\``). Needed when mapped drives are
            unavailable.

    """
    path_map = PATH_MAP_LINUX_TO_UNC if unc else PATH_MAP_LINUX_TO_WIN
    for linux_prefix, win_prefix in path_map.items():
        if path.startswith(linux_prefix):
            return win_prefix + path[len(linux_prefix):].replace("/", "\\")
    return path


def windows_to_linux_path(path: str) -> str:
    """Convert a Windows path to its Linux equivalent using PATH_MAP."""
    for win_prefix, linux_prefix in PATH_MAP_WIN_TO_LINUX.items():
        if path.startswith(win_prefix):
            return linux_prefix + path[len(win_prefix):].replace("\\", "/")
    return path


def get_results_dir(issue_name: str) -> pathlib.Path:
    """Return the results directory for a given issue, creating it if needed.

    OS-aware: uses the Linux diagnostic base on Linux, and the Windows
    diagnostic base (drive-letter path) on Windows.
    """
    if sys.platform == "win32":
        # Drive letters (Z:) may not be mapped; prefer UNC for reliability.
        base = pathlib.Path(WINDOWS.diagnostic_base_unc)
    else:
        base = pathlib.Path(LINUX.diagnostic_base)

    results_dir = base / "issues" / issue_name / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir
