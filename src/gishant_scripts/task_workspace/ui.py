"""Shared UI helpers — Rich console, questionary style, slug/table utils, VS Code launcher."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from questionary import Style as QStyle
from rich.console import Console

# ---------------------------------------------------------------------------
# Questionary style — One Dark palette
# ---------------------------------------------------------------------------

Q_STYLE = QStyle(
    [
        ("qmark", "fg:#61AFEF bold"),
        ("question", "fg:#ABB2BF bold"),
        ("answer", "fg:#98C379 bold"),
        ("pointer", "fg:#E5C07B bold"),
        ("highlighted", "fg:#E5C07B bold"),
        ("selected", "fg:#98C379"),
        ("separator", "fg:#5C6370"),
        ("instruction", "fg:#5C6370 italic"),
        ("text", "fg:#ABB2BF"),
        ("disabled", "fg:#5C6370 italic"),
    ]
)

# ---------------------------------------------------------------------------
# Rich console (shared across all modules)
# ---------------------------------------------------------------------------

console = Console()

# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def slugify(raw: str) -> str:
    """Normalise a free-form string into a filesystem/branch-safe slug."""
    slug = re.sub(r"[^\w\-]", "-", raw.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)


def table_repo_name(display_name: str) -> str:
    """Strip leading emoji/icon prefix for stable Rich-table alignment."""
    return re.sub(r"^\s*[^\w]+", "", display_name).strip()


# ---------------------------------------------------------------------------
# VS Code launcher
# ---------------------------------------------------------------------------


def _code_executable() -> str | None:
    """Return path to VS Code CLI, or ``None`` if not found."""
    exe = os.environ.get("VSCODE_BIN")
    if exe and os.path.isfile(exe):
        return exe
    exe = shutil.which("code")
    if exe:
        return exe
    if sys.platform == "darwin":
        app = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
        if os.path.isfile(app):
            return app
    return None


def open_workspace_in_code(ws_file: Path) -> None:
    """Launch VS Code with the given workspace file. No-op if VS Code not found."""
    exe = _code_executable()
    if exe:
        subprocess.Popen([exe, str(ws_file)], start_new_session=True)  # noqa: S603
    else:
        console.print(
            "[yellow]VS Code not found in PATH.[/] Open the workspace manually:\n  [cyan]"
            f"{ws_file}[/]\n"
            "[dim]Tip: use Command Palette → \"Shell Command: Install 'code' command in PATH\".[/]"
        )
