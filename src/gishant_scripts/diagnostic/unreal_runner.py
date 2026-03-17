"""Run Python diagnostic scripts inside Unreal Engine on a remote Windows machine via SSH.

Launches UnrealEditor-Cmd on the Windows machine via SSH. Network drives
are mapped at the start of each SSH session using credentials from
``~/.rdo/.env`` (OpenSSH on Windows doesn't inherit interactive session
drive mappings).
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from gishant_scripts.diagnostic.config import WINDOWS, linux_to_windows_path
from gishant_scripts.diagnostic.models import DiagnosticResult

logger = logging.getLogger(__name__)

_SSH_HOST = WINDOWS.ssh_host
_SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
_UNREAL_BIN = WINDOWS.unreal_bin

# gishant-scripts paths for PYTHONPATH injection
_REPO = Path("/tech/users/gisi/dev/repos/gishant-scripts")
_SITE_PKGS = _REPO / ".venv" / "lib" / "python3.11" / "site-packages"
_SRC = _REPO / "src"


# ---------------------------------------------------------------------------
# Drive mapping
# ---------------------------------------------------------------------------

def _read_drive_credentials() -> tuple[str, str, list[tuple[str, str]]]:
    """Read Windows domain credentials and drive mappings from ``~/.rdo/.env``.

    Returns:
        (domain_user, domain_pass, [(drive_letter, unc_path), ...])
    """
    env_path = Path.home() / ".rdo" / ".env"
    domain_user = ""
    domain_pass = ""
    drive_maps: list[tuple[str, str]] = []

    if not env_path.exists():
        return domain_user, domain_pass, drive_maps

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("WIN_DOMAIN_USER="):
            domain_user = line.split("=", 1)[1].strip()
        elif line.startswith("WIN_DOMAIN_PASS="):
            domain_pass = line.split("=", 1)[1].strip()
        elif line.startswith("WIN_DRIVE_MAPS="):
            raw = line.split("=", 1)[1].strip()
            for pair in raw.split(","):
                parts = pair.split(":", 1)
                if len(parts) == 2:
                    drive_maps.append((parts[0] + ":", parts[1].replace("\\\\", "\\")))

    return domain_user, domain_pass, drive_maps


def _build_drive_map_commands() -> str:
    """Build ``net use`` commands to map network drives in the SSH session.

    Returns a ``cmd /c`` command string that maps all configured drives.
    Each ``net use`` is chained with ``&`` (unconditional) so that already-
    mapped drives don't block subsequent mappings.
    """
    domain_user, domain_pass, drive_maps = _read_drive_credentials()
    if not drive_maps or not domain_user:
        return ""

    cmds = []
    for drive_letter, unc_path in drive_maps:
        cmds.append(
            f"net use {drive_letter} {unc_path} /user:{domain_user} {domain_pass} /persistent:no >nul 2>&1"
        )
    # Use & (not &&) so failure on one drive doesn't block the rest
    return " & ".join(cmds)


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------


def check_ssh_connectivity() -> bool:
    """Quick check that SSH to the Windows machine works."""
    try:
        result = subprocess.run(
            ["ssh", *_SSH_OPTS, _SSH_HOST, "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and "ok" in result.stdout


def check_drive_access() -> bool:
    """Check that network drives are accessible from the SSH session."""
    drive_cmd = _build_drive_map_commands()
    if not drive_cmd:
        return False
    test_cmd = f"{drive_cmd} && dir Z: >nul 2>&1 && dir P: >nul 2>&1 && echo ok"
    try:
        result = subprocess.run(
            ["ssh", *_SSH_OPTS, _SSH_HOST, f"cmd /c \"{test_cmd}\""],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return "ok" in result.stdout


# ---------------------------------------------------------------------------
# Streaming log helper
# ---------------------------------------------------------------------------


def _stream_pipe_to_log(pipe, log_file: Path, collected: list[str]) -> None:  # noqa: ANN001
    """Read lines from a subprocess pipe, append to a log file, and collect."""
    with open(log_file, "a", encoding="utf-8") as f:
        for line in pipe:
            f.write(line)
            f.flush()
            collected.append(line)


# ---------------------------------------------------------------------------
# Error result factory
# ---------------------------------------------------------------------------


def _error_result(
    issue_name: str,
    project_name: str,
    folder_path: str,
    task_name: str | None,
    errors: list[str],
    raw_output: str = "",
) -> DiagnosticResult:
    """Create an error DiagnosticResult with common fields."""
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


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_unreal_script(
    script_path: str | Path,
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
    timeout: int = 600,
    unreal_project: str | None = None,
) -> DiagnosticResult:
    """Run a Python script inside UnrealEditor-Cmd on Windows via SSH.

    Network drives are mapped automatically at the start of the SSH session.
    Output is streamed to ``<issue_dir>/results/unreal_output.log``.

    Args:
        script_path: Path to the .py script (Linux path, auto-converted to Windows).
        project_name: AYON project name.
        folder_path: AYON folder path.
        task_name: Optional AYON task name.
        timeout: SSH command timeout in seconds.
        unreal_project: Path to .uproject file (Windows path).
    """
    script_path = Path(script_path).resolve()
    issue_name = script_path.parent.name
    results_dir = script_path.parent / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / "unreal_output.log"
    result_json = results_dir / "unreal_result.json"

    # Clear previous outputs
    log_file.write_text("", encoding="utf-8")
    if result_json.exists():
        result_json.unlink()

    if not script_path.exists():
        return _error_result(
            issue_name, project_name, folder_path, task_name,
            [f"Script not found: {script_path}"],
        )

    # Use UNC paths for Unreal arguments — Session 0 (SSH) doesn't have
    # mapped drive letters, and UE resolves paths before drives are mapped.
    win_script_path = linux_to_windows_path(str(script_path), unc=True)
    logger.info("Linux script path: %s -> Windows UNC: %s", script_path, win_script_path)

    # ------------------------------------------------------------------
    # Resolve AYON environment variables
    # ------------------------------------------------------------------
    from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env  # noqa: PLC0415

    ayon_env = resolve_ayon_env(
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
        target="windows",
    )
    ayon_env["LANG"] = "C.UTF-8"
    ayon_env["LC_ALL"] = "C.UTF-8"

    # Append gishant-scripts paths + Windows system Python site-packages
    # (for ayon_api) to the addon PYTHONPATH.
    existing_pythonpath = ayon_env.get("PYTHONPATH", "")
    win_src = linux_to_windows_path(str(_SRC), unc=True)
    win_site_pkgs = linux_to_windows_path(str(_SITE_PKGS), unc=True)
    # Windows system Python site-packages (has ayon_api installed via pip)
    win_sys_site_pkgs = r"C:\Users\gisi\AppData\Local\Programs\Python\Python311\Lib\site-packages"
    ayon_env["PYTHONPATH"] = ";".join(
        filter(None, [existing_pythonpath, win_sys_site_pkgs, win_src, win_site_pkgs]),
    )

    # ------------------------------------------------------------------
    # Build the SSH command
    # ------------------------------------------------------------------

    # Write a .ps1 wrapper script to the shared path — this avoids all
    # quote-escaping issues when passing complex commands via SSH.
    ps1_wrapper = script_path.parent / "_run_unreal.ps1"
    env_lines = [f"$env:{key} = '{value}'" for key, value in sorted(ayon_env.items())]
    unreal_args = []
    if unreal_project:
        # Convert project path to UNC if it uses a drive letter that maps
        # to a known Linux path, otherwise use as-is (already a Windows path)
        ue_project_path = unreal_project
        unreal_args.append(f'"{ue_project_path}"')
    unreal_args.append(f'-ExecutePythonScript="{win_script_path}"')
    unreal_args.append("-stdout -FullStdOutLogOutput -Unattended -NullRHI")
    unreal_line = f'& "{_UNREAL_BIN}" {" ".join(unreal_args)}'

    ps1_content = "\n".join([*env_lines, unreal_line])
    ps1_wrapper.write_text(ps1_content, encoding="utf-8")
    # Use UNC for the .ps1 path itself since SSH session runs it
    win_ps1_path = linux_to_windows_path(str(ps1_wrapper), unc=True)
    logger.debug("Wrote PowerShell wrapper: %s -> %s", ps1_wrapper, win_ps1_path)

    # Map drives via cmd first, then pipe the .ps1 content to PowerShell.
    # This avoids all quote-escaping issues with -File paths over SSH.
    drive_cmds = _build_drive_map_commands()

    # Prepend drive mapping to the .ps1 content as inline cmd calls
    if drive_cmds:
        # Use cmd /c to map drives, then launch PowerShell with stdin
        ssh_command = [
            "ssh", *_SSH_OPTS, _SSH_HOST,
            f'cmd /c "{drive_cmds} && powershell -NoProfile -ExecutionPolicy Bypass -Command -"',
        ]
    else:
        ssh_command = [
            "ssh", *_SSH_OPTS, _SSH_HOST,
            "powershell -NoProfile -ExecutionPolicy Bypass -Command -",
        ]

    logger.info(
        "Running Unreal diagnostic: issue=%s  project=%s  folder=%s  log=%s",
        issue_name, project_name, folder_path, log_file,
    )

    # ------------------------------------------------------------------
    # Run with streaming output
    # ------------------------------------------------------------------
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            ssh_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send the .ps1 content via stdin and close
        proc.stdin.write(ps1_content)
        proc.stdin.close()

        stdout_thread = threading.Thread(
            target=_stream_pipe_to_log,
            args=(proc.stdout, log_file, stdout_lines),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_stream_pipe_to_log,
            args=(proc.stderr, log_file, stderr_lines),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        proc.wait(timeout=timeout)
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        raw_output = "".join(stdout_lines) + "".join(stderr_lines)

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        raw = "".join(stdout_lines) + "".join(stderr_lines)
        logger.error("SSH timed out after %ss for issue=%s", timeout, issue_name)
        return _error_result(
            issue_name, project_name, folder_path, task_name,
            [f"SSH timed out after {timeout}s"], raw,
        )
    except OSError as exc:
        ps1_wrapper.unlink(missing_ok=True)
        logger.exception("Failed to execute SSH for issue=%s", issue_name)
        return _error_result(
            issue_name, project_name, folder_path, task_name,
            [f"Failed to execute SSH: {exc}"],
        )

    # Clean up the .ps1 wrapper
    ps1_wrapper.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Parse result JSON
    # ------------------------------------------------------------------
    if not result_json.exists():
        errors = [f"Result file not found at {result_json}"]
        if proc.returncode != 0:
            errors.append(f"SSH exited with code {proc.returncode}")
        logger.warning("No result file for issue=%s, returncode=%s", issue_name, proc.returncode)
        return _error_result(
            issue_name, project_name, folder_path, task_name, errors, raw_output,
        )

    try:
        data = json.loads(result_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to parse result JSON for issue=%s: %s", issue_name, exc)
        return _error_result(
            issue_name, project_name, folder_path, task_name,
            [f"Result JSON parse error: {exc}"], raw_output,
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
