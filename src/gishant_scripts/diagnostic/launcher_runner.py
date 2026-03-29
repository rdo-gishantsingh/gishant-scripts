"""Run diagnostic scripts inside DCCs with the AYON Launcher environment.

Reproduces the environment the AYON Launcher sets for artists, then launches
the DCC binary directly.  This is the only execution mode —.

Both runners execute LOCALLY on their target OS.  Agent-deck sessions SSH
directly into the correct machine — no cross-machine SSH hops.

Limitations
-----------
The AYON Launcher (1.4.x) does **not** expose a CLI subcommand to launch a DCC
with a script in headless mode.  It validates server credentials before doing
anything and expects ``AYON_API_KEY`` in headless mode
(``AYON_HEADLESS_MODE=1``).  There is no ``--launch maya --script foo.py``
style interface.

**Best-effort strategy used here:**

1. Set the same env vars the launcher would set (``AYON_SERVER_URL``,
   ``AYON_LAUNCHER_STORAGE_DIR``, ``AYON_LAUNCHER_LOCAL_DIR``, project/folder
   context).
2. Point ``AYON_HEADLESS_MODE=1`` so Qt UI code is skipped where possible.
3. Launch the DCC binary directly (``mayabatch`` / ``UnrealEditor-Cmd``), but
   with the launcher binary's directory prepended to ``PATH`` so that any child
   process that shells out to ``ayon`` (or ``ayon_console.exe``) will find the
   real launcher.
4. Addon Python paths are resolved from the launcher's local storage, identical
   to what the launcher itself reads at startup.

This gives ~95% fidelity to a real artist launch.  The remaining 5% (dynamic
bundle resolution from the server, per-app environment overrides stored in AYON
settings) would require either a future launcher CLI or direct use of the
``ayon_api`` to replicate.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env
from gishant_scripts.diagnostic.config import LINUX, WINDOWS, linux_to_windows_path
from gishant_scripts.diagnostic.models import DiagnosticResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LINUX_LAUNCHER = LINUX.ayon_launcher
_LINUX_LAUNCHER_DIR = str(Path(_LINUX_LAUNCHER).parent)

_WIN_LAUNCHER = WINDOWS.ayon_launcher
_WIN_LAUNCHER_DIR = str(Path(WINDOWS.ayon_launcher).parent)


def _create_mel_wrapper(script_path: Path) -> Path:
    """Create a temporary MEL script that calls ``exec(open(...).read())``.

    Using ``maya -script wrapper.mel`` avoids shell quote-escaping issues
    that break ``maya -batch -command`` on Linux.
    """
    mel_file = script_path.parent / f"_runner_{script_path.stem}.mel"
    mel_content = f"python(\"__file__ = '{script_path}'; exec(open('{script_path}').read())\");\n"
    mel_file.write_text(mel_content, encoding="utf-8")
    return mel_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_launcher_env_linux(
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
) -> dict[str, str]:
    """Build an environment dict that mimics what the AYON Launcher sets on Linux.

    Starts from the current process environment (so ``PATH``, ``HOME``, etc.
    are inherited), then layers on AYON-specific variables.
    """
    # Start from current env so Maya can find system libs, fonts, etc.
    env = dict(os.environ)

    # Overlay AYON context resolved from the launcher's addon storage.
    ayon_vars = resolve_ayon_env(
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
        target="linux",
    )
    env.update(ayon_vars)

    # Headless mode — prevents Qt UI popups inside the launcher's own code
    # if any addon internally imports launcher utilities.
    env["AYON_HEADLESS_MODE"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"

    # Prepend the launcher directory to PATH so child processes can find the
    # ``ayon`` binary (some addons shell out to it).
    current_path = env.get("PATH", "")
    env["PATH"] = _LINUX_LAUNCHER_DIR + ":" + current_path

    return env


def _parse_result_file(
    result_file: Path,
    dcc: str,
    issue_name: str,
    raw_output: str,
    project_name: str,
    folder_path: str,
    task_name: str | None,
) -> DiagnosticResult:
    """Read and parse the result JSON file written by the diagnostic script."""
    if result_file.exists():
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
            return DiagnosticResult(
                status=data.get("status", "error"),
                dcc=dcc,
                issue=data.get("issue", issue_name),
                timestamp=data.get("timestamp", datetime.now(tz=UTC).isoformat()),
                context=data.get("context", {}),
                findings=data.get("findings", {}),
                errors=data.get("errors", []),
                raw_output=raw_output,
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.exception("Failed to parse result JSON for issue=%s", issue_name)
            return DiagnosticResult(
                status="error",
                dcc=dcc,
                issue=issue_name,
                timestamp=datetime.now(tz=UTC).isoformat(),
                context={"project": project_name, "folder": folder_path, "task": task_name},
                findings={},
                errors=["Result JSON parse error: " + str(exc)],
                raw_output=raw_output,
            )

    return DiagnosticResult(
        status="error",
        dcc=dcc,
        issue=issue_name,
        timestamp=datetime.now(tz=UTC).isoformat(),
        context={"project": project_name, "folder": folder_path, "task": task_name},
        findings={},
        errors=["No result file produced at " + str(result_file)],
        raw_output=raw_output,
    )


def _error_result(
    dcc: str,
    issue_name: str,
    project_name: str,
    folder_path: str,
    task_name: str | None,
    errors: list[str],
    raw_output: str = "",
) -> DiagnosticResult:
    """Create an error DiagnosticResult with standard fields."""
    return DiagnosticResult(
        status="error",
        dcc=dcc,
        issue=issue_name,
        timestamp=datetime.now(tz=UTC).isoformat(),
        context={"project": project_name, "folder": folder_path, "task": task_name},
        findings={},
        errors=errors,
        raw_output=raw_output,
    )


# ---------------------------------------------------------------------------
# Maya via Launcher
# ---------------------------------------------------------------------------


def run_maya(
    script_path: str | Path,
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
    timeout: int = 300,
) -> DiagnosticResult:
    """Launch Maya via AYON Launcher for exact artist-environment reproduction.

    This sets the same environment the AYON Launcher would configure
    (server URL, addon paths, project context, headless flags) and then
    invokes ``mayabatch`` directly.  The launcher binary directory is on
    ``PATH`` so addons that shell out to ``ayon`` will find it.

    .. note::

        The AYON Launcher 1.4.x lacks a headless "launch DCC with script"
        CLI.  This function approximates the launcher's environment as
        closely as possible without that feature.

    Args:
        script_path: Absolute path to the diagnostic Python script.
        project_name: AYON project name.
        folder_path: AYON folder path (e.g. ``"/shots/sh010"``).
        task_name: Optional AYON task name.
        timeout: Maximum seconds to wait for ``mayabatch`` before killing it.

    Returns:
        A populated :class:`DiagnosticResult`. On timeout or crash the
        ``status`` field will be ``"error"``.

    """
    script_path = Path(script_path).resolve()
    issue_name = script_path.parent.name
    result_file = script_path.parent / "results" / "maya_result.json"

    # Build environment that mirrors the launcher's setup.
    env = _build_launcher_env_linux(
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
    )

    # Build maya -batch command using a MEL wrapper file
    # to avoid shell quote-escaping issues with python("exec(...)").
    mel_wrapper = _create_mel_wrapper(script_path)
    cmd = [LINUX.maya_bin, "-batch", "-script", str(mel_wrapper)]

    logger.info(
        "Launching mayabatch for issue=%s  project=%s  folder=%s",
        issue_name,
        project_name,
        folder_path,
    )

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw_output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"").decode("utf-8", errors="replace") + (exc.stderr or b"").decode(
            "utf-8", errors="replace"
        )
        mel_wrapper.unlink(missing_ok=True)
        logger.exception("mayabatch timed out after %s seconds for issue=%s", timeout, issue_name)
        return _error_result(
            dcc="maya",
            issue_name=issue_name,
            project_name=project_name,
            folder_path=folder_path,
            task_name=task_name,
            errors=["mayabatch timed out after " + str(timeout) + "s"],
            raw_output=raw,
        )
    except Exception as exc:
        mel_wrapper.unlink(missing_ok=True)
        logger.exception("mayabatch failed to launch for issue=%s", issue_name)
        return _error_result(
            dcc="maya",
            issue_name=issue_name,
            project_name=project_name,
            folder_path=folder_path,
            task_name=task_name,
            errors=[str(exc)],
        )

    mel_wrapper.unlink(missing_ok=True)

    if proc.returncode != 0:
        logger.warning(
            "mayabatch exited with code %s for issue=%s",
            proc.returncode,
            issue_name,
        )

    return _parse_result_file(
        result_file=result_file,
        dcc="maya",
        issue_name=issue_name,
        raw_output=raw_output,
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
    )


# ---------------------------------------------------------------------------
# Unreal via Launcher (local Windows execution)
# ---------------------------------------------------------------------------


def _build_ps1_launcher_content(
    win_script_path: str,
    ayon_env: dict[str, str],
    unreal_project: str | None = None,
) -> str:
    """Build PowerShell content that mimics the AYON Launcher's environment on Windows.

    Sets all AYON env vars, prepends the launcher directory to ``PATH``,
    enables headless mode, then invokes ``UnrealEditor-Cmd``.
    """
    lines: list[str] = []

    # Set each AYON env var.
    for key, value in sorted(ayon_env.items()):
        lines.append("$env:" + key + " = '" + value + "'")

    # Enable headless mode.
    lines.append("$env:AYON_HEADLESS_MODE = '1'")

    # Prepend the launcher directory to PATH so addons can find ayon_console.exe.
    lines.append("$env:PATH = '" + _WIN_LAUNCHER_DIR + ";' + $env:PATH")

    # Build Unreal command.
    unreal_bin = WINDOWS.unreal_bin
    unreal_args: list[str] = []
    if unreal_project:
        unreal_args.append("'" + unreal_project + "'")
    unreal_args.append("-ExecutePythonScript='" + win_script_path + "'")
    unreal_args.append("-stdout -FullStdOutLogOutput -Unattended -NullRHI")

    args_str = " ".join(unreal_args)
    lines.append('& "' + unreal_bin + '" ' + args_str)

    return "\n".join(lines)


def run_unreal(
    script_path: str | Path,
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
    unreal_project: str | None = None,
    timeout: int = 600,
) -> DiagnosticResult:
    """Launch Unreal via AYON Launcher locally on Windows for exact artist-environment reproduction.

    Sets the AYON Launcher environment (server URL, addon paths, project
    context, headless flags) via a PowerShell wrapper script, then invokes
    ``UnrealEditor-Cmd`` directly.  The launcher binary directory is
    prepended to ``PATH`` so addons that invoke ``ayon_console.exe`` will
    find it.

    .. note::

        The AYON Launcher 1.4.x lacks a headless "launch DCC with script"
        CLI.  This function approximates the launcher's environment as
        closely as possible without that feature.

    Args:
        script_path: Path to the ``.py`` script.  Linux NAS paths are
            auto-converted to Windows format.
        project_name: AYON project name.
        folder_path: AYON folder path.
        task_name: Optional AYON task name.
        unreal_project: Windows path to ``.uproject`` file.  If ``None``,
            Unreal runs without a project.
        timeout: Process timeout in seconds.

    Returns:
        A populated :class:`DiagnosticResult`. On timeout or failure the
        ``status`` field will be ``"error"``.

    """
    script_path = Path(script_path).resolve()
    issue_name = script_path.parent.name
    result_file = script_path.parent / "results" / "unreal_result.json"

    if not script_path.exists():
        return _error_result(
            dcc="unreal",
            issue_name=issue_name,
            project_name=project_name,
            folder_path=folder_path,
            task_name=task_name,
            errors=["Script not found: " + str(script_path)],
        )

    win_script_path = linux_to_windows_path(str(script_path))
    logger.info("Script path: %s -> Windows: %s", script_path, win_script_path)

    # Resolve AYON env vars targeting Windows.
    ayon_env = resolve_ayon_env(
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
        target="windows",
    )

    # Write a .ps1 wrapper to the issue dir and execute locally.
    ps1_wrapper = script_path.parent / "_run_unreal_launcher.ps1"
    ps1_content = _build_ps1_launcher_content(
        win_script_path=win_script_path,
        ayon_env=ayon_env,
        unreal_project=unreal_project,
    )
    ps1_wrapper.write_text(ps1_content, encoding="utf-8")
    logger.debug("Wrote PowerShell launcher wrapper: %s", ps1_wrapper)

    cmd = ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(ps1_wrapper)]

    logger.info(
        "Executing Unreal (via-launcher mode, timeout=%ds) for issue=%s",
        timeout,
        issue_name,
    )

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw_output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"").decode("utf-8", errors="replace") + (exc.stderr or b"").decode(
            "utf-8", errors="replace"
        )
        logger.exception(
            "Unreal process timed out after %s seconds for issue=%s",
            timeout,
            issue_name,
        )
        ps1_wrapper.unlink(missing_ok=True)
        return _error_result(
            dcc="unreal",
            issue_name=issue_name,
            project_name=project_name,
            folder_path=folder_path,
            task_name=task_name,
            errors=["Unreal process timed out after " + str(timeout) + "s"],
            raw_output=raw,
        )
    except OSError as exc:
        logger.exception("Failed to execute Unreal for issue=%s", issue_name)
        ps1_wrapper.unlink(missing_ok=True)
        return _error_result(
            dcc="unreal",
            issue_name=issue_name,
            project_name=project_name,
            folder_path=folder_path,
            task_name=task_name,
            errors=["Failed to execute Unreal: " + str(exc)],
        )

    ps1_wrapper.unlink(missing_ok=True)

    logger.info("Unreal returncode: %s", proc.returncode)
    if proc.stdout:
        logger.debug("stdout (last 2000 chars):\n%s", proc.stdout[-2000:])
    if proc.stderr:
        logger.debug("stderr (last 2000 chars):\n%s", proc.stderr[-2000:])

    return _parse_result_file(
        result_file=result_file,
        dcc="unreal",
        issue_name=issue_name,
        raw_output=raw_output,
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
    )
