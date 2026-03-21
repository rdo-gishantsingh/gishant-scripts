"""Run Python diagnostic scripts inside Maya batch mode on Linux with AYON context."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

from gishant_scripts.diagnostic.config import LINUX
from gishant_scripts.diagnostic.models import DiagnosticResult

logger = logging.getLogger(__name__)


def _create_mel_wrapper(script_path: Path) -> Path:
    """Create a temporary MEL script that calls ``exec(open(...).read())``.

    Using ``maya -script wrapper.mel`` avoids shell quote-escaping issues
    that break ``maya -batch -command "python(\"exec(...)\")"`` on Linux.
    """
    mel_file = script_path.parent / f"_runner_{script_path.stem}.mel"
    # Set __file__ before exec() so the diagnostic script can use it
    mel_content = f"python(\"__file__ = '{script_path}'; exec(open('{script_path}').read())\");\n"
    mel_file.write_text(mel_content, encoding="utf-8")
    return mel_file


def _stream_pipe_to_log(pipe, log_file: Path, collected: list[str]) -> None:
    """Read lines from a subprocess pipe, append to a log file, and collect."""
    with open(log_file, "a", encoding="utf-8") as f:
        for line in pipe:
            f.write(line)
            f.flush()
            collected.append(line)


def run_maya_script(
    script_path: str | Path,
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
    timeout: int = 300,
) -> DiagnosticResult:
    """Run a Python script inside ``maya -batch`` with AYON context.

    Output is streamed in real-time to a log file at
    ``<issue_dir>/results/maya_output.log`` so progress can be monitored
    while the process runs.

    Args:
        script_path: Absolute path to the diagnostic Python script.
        project_name: AYON project name.
        folder_path: AYON folder path (e.g. ``"/shots/sh010"``).
        task_name: Optional AYON task name.
        timeout: Maximum seconds to wait for ``maya -batch`` before killing it.

    Returns:
        A populated :class:`DiagnosticResult`. On timeout or crash the
        ``status`` field will be ``"error"``.

    """
    script_path = Path(script_path).resolve()
    script_dir = script_path.parent
    issue_name = script_dir.name
    results_dir = script_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    result_file = results_dir / "maya_result.json"
    log_file = results_dir / "maya_output.log"

    # Clear previous log
    log_file.write_text("", encoding="utf-8")

    # ------------------------------------------------------------------
    # Resolve AYON environment variables
    # ------------------------------------------------------------------
    from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

    ayon_env = resolve_ayon_env(
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
    )

    # ------------------------------------------------------------------
    # Build the maya -batch command using a MEL wrapper file
    # to avoid shell quote-escaping issues with python("exec(...)")
    # ------------------------------------------------------------------
    mel_wrapper = _create_mel_wrapper(script_path)
    cmd = [
        LINUX.maya_bin,
        "-batch",
        "-script",
        str(mel_wrapper),
    ]

    # Ensure UTF-8 locale — Maya on Linux defaults to ASCII under
    # some AYON env setups, causing UnicodeDecodeError on FBX reads.
    ayon_env["LANG"] = "C.UTF-8"
    ayon_env["LC_ALL"] = "C.UTF-8"

    # Add gishant-scripts src to PYTHONPATH so Maya's Python can import
    # gishant_scripts. Placed AFTER existing paths so Maya's own packages
    # (numpy, PySide6, etc.) take precedence over venv versions.
    _repo = Path(__file__).resolve().parents[3]
    _site_pkgs = _repo / ".venv" / "lib" / "python3.11" / "site-packages"
    _src = _repo / "src"
    existing_pythonpath = ayon_env.get("PYTHONPATH", "")
    ayon_env["PYTHONPATH"] = ":".join(filter(None, [existing_pythonpath, str(_src), str(_site_pkgs)]))

    logger.info(
        "Launching mayabatch for issue=%s  project=%s  folder=%s  log=%s",
        issue_name,
        project_name,
        folder_path,
        log_file,
    )

    # ------------------------------------------------------------------
    # Run the subprocess with streaming output to log file
    # ------------------------------------------------------------------
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            cmd,
            env=ayon_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Stream stdout and stderr to log file in background threads
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
        returncode = proc.returncode

    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)
        mel_wrapper.unlink(missing_ok=True)
        raw = "".join(stdout_lines) + "".join(stderr_lines)
        logger.error("mayabatch timed out after %s seconds for issue=%s", timeout, issue_name)
        return DiagnosticResult(
            status="error",
            dcc="maya",
            issue=issue_name,
            timestamp=datetime.now(tz=UTC).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=[f"mayabatch timed out after {timeout}s"],
            raw_output=raw,
        )
    except Exception as exc:
        mel_wrapper.unlink(missing_ok=True)
        logger.exception("mayabatch failed to launch for issue=%s", issue_name)
        return DiagnosticResult(
            status="error",
            dcc="maya",
            issue=issue_name,
            timestamp=datetime.now(tz=UTC).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=[str(exc)],
            raw_output="",
        )

    # Clean up the temporary MEL wrapper
    mel_wrapper.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Parse the result JSON written by the diagnostic script
    # ------------------------------------------------------------------
    if result_file.exists():
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
            return DiagnosticResult(
                status=data.get("status", "error"),
                dcc="maya",
                issue=data.get("issue", issue_name),
                timestamp=data.get("timestamp", datetime.now(tz=UTC).isoformat()),
                context=data.get("context", {}),
                findings=data.get("findings", {}),
                errors=data.get("errors", []),
                raw_output=raw_output,
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("Failed to parse result JSON for issue=%s: %s", issue_name, exc)
            return DiagnosticResult(
                status="error",
                dcc="maya",
                issue=issue_name,
                timestamp=datetime.now(tz=UTC).isoformat(),
                context={"project": project_name, "folder": folder_path, "task": task_name},
                findings={},
                errors=[f"Result JSON parse error: {exc}"],
                raw_output=raw_output,
            )

    # No result file produced -- treat as error
    errors = [f"No result file produced at {result_file}"]
    if returncode != 0:
        errors.append(f"mayabatch exited with code {returncode}")

    logger.warning("No result file found for issue=%s, returncode=%s", issue_name, returncode)
    return DiagnosticResult(
        status="error",
        dcc="maya",
        issue=issue_name,
        timestamp=datetime.now(tz=UTC).isoformat(),
        context={"project": project_name, "folder": folder_path, "task": task_name},
        findings={},
        errors=errors,
        raw_output=raw_output,
    )
