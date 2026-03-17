"""Run Python diagnostic scripts inside Unreal Engine on a remote Windows machine via SSH."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env
from gishant_scripts.diagnostic.config import WINDOWS, linux_to_windows_path
from gishant_scripts.diagnostic.models import DiagnosticResult

logger = logging.getLogger(__name__)

_SSH_HOST = WINDOWS.ssh_host
_UNREAL_BIN = WINDOWS.unreal_bin


def check_ssh_connectivity() -> bool:
    """Quick check that SSH to Windows machine works."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", _SSH_HOST, "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and "ok" in result.stdout


def _build_powershell_command(
    win_script_path: str,
    ayon_env: dict[str, str],
    unreal_project: str | None = None,
) -> str:
    """Build a PowerShell command that sets env vars and launches Unreal."""
    env_lines = [f"$env:{key} = '{value}'" for key, value in sorted(ayon_env.items())]

    unreal_args = []
    if unreal_project:
        unreal_args.append(f"'{unreal_project}'")
    unreal_args.append(f"-ExecutePythonScript=\"{win_script_path}\"")

    args_str = " ".join(unreal_args)
    unreal_line = f"& '{_UNREAL_BIN}' {args_str} -stdout -FullStdOutLogOutput -Unattended -NullRHI"

    parts = [*env_lines, unreal_line]
    return "; ".join(parts)


def run_unreal_script(
    script_path: str | Path,
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
    unreal_project: str | None = None,
    timeout: int = 600,
) -> DiagnosticResult:
    """Run a Python script inside UnrealEditor-Cmd on Windows via SSH.

    Args:
        script_path: Path to the .py script (Linux path, will be converted to Windows).
        project_name: AYON project name.
        folder_path: AYON folder path.
        task_name: Optional AYON task name.
        unreal_project: Path to .uproject file (Windows path). If None, runs without a project.
        timeout: SSH command timeout in seconds.
    """
    script_path = Path(script_path).resolve()
    issue_name = script_path.parent.name

    if not script_path.exists():
        return DiagnosticResult(
            status="error",
            dcc="unreal",
            issue=issue_name,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            context={"project": project_name, "folder": folder_path},
            findings={},
            errors=[f"Script not found: {script_path}"],
            raw_output="",
        )

    win_script_path = linux_to_windows_path(str(script_path))
    logger.info("Linux script path: %s -> Windows: %s", script_path, win_script_path)

    ayon_env = resolve_ayon_env(
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
        target="windows",
    )

    ps_command = _build_powershell_command(win_script_path, ayon_env, unreal_project)
    logger.debug("PowerShell command: %s", ps_command)

    ssh_command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        _SSH_HOST,
        f'powershell -NoProfile -Command "{ps_command}"',
    ]

    logger.info("Executing SSH command (timeout=%ds) ...", timeout)
    try:
        proc = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw_output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"").decode("utf-8", errors="replace") + (
            exc.stderr or b""
        ).decode("utf-8", errors="replace")
        logger.error("SSH command timed out after %ss for issue=%s", timeout, issue_name)
        return DiagnosticResult(
            status="error",
            dcc="unreal",
            issue=issue_name,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=[f"SSH command timed out after {timeout}s"],
            raw_output=raw,
        )
    except OSError as exc:
        logger.exception("Failed to execute SSH for issue=%s", issue_name)
        return DiagnosticResult(
            status="error",
            dcc="unreal",
            issue=issue_name,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=[f"Failed to execute SSH: {exc}"],
            raw_output="",
        )

    logger.info("SSH returncode: %s", proc.returncode)
    if proc.stdout:
        logger.debug("SSH stdout (last 2000 chars):\n%s", proc.stdout[-2000:])
    if proc.stderr:
        logger.debug("SSH stderr (last 2000 chars):\n%s", proc.stderr[-2000:])

    # Read the results JSON written by the diagnostic script on the shared path.
    results_json = script_path.parent / "results" / "unreal_result.json"
    if not results_json.exists():
        errors = [
            f"Result file not found at {results_json}",
            f"SSH returncode={proc.returncode}",
        ]
        if proc.stderr:
            errors.append(f"stderr (last 500 chars): {proc.stderr[-500:]}")
        return DiagnosticResult(
            status="error",
            dcc="unreal",
            issue=issue_name,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=errors,
            raw_output=raw_output,
        )

    try:
        data = json.loads(results_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to parse result JSON for issue=%s: %s", issue_name, exc)
        return DiagnosticResult(
            status="error",
            dcc="unreal",
            issue=issue_name,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=[f"Result JSON parse error: {exc}"],
            raw_output=raw_output,
        )

    return DiagnosticResult(
        status=data.get("status", "error"),
        dcc="unreal",
        issue=data.get("issue", issue_name),
        timestamp=data.get("timestamp", datetime.now(tz=timezone.utc).isoformat()),
        context=data.get("context", {}),
        findings=data.get("findings", {}),
        errors=data.get("errors", []),
        raw_output=raw_output,
    )
