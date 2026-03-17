"""Run Python diagnostic scripts inside Maya batch mode on Linux with AYON context."""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from gishant_scripts.diagnostic.config import LINUX
from gishant_scripts.diagnostic.models import DiagnosticResult

logger = logging.getLogger(__name__)

# On Linux, Maya batch mode is: maya -batch -command "python(\"exec(...)\")"
_MAYA_PYTHON_CMD = "python(\"exec(open('{script_path}').read())\")"


def run_maya_script(
    script_path: str | Path,
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
    timeout: int = 300,
) -> DiagnosticResult:
    """Run a Python script inside ``maya -batch`` with AYON context.

    The script is expected to write its results to a JSON file using
    :func:`gishant_scripts.diagnostic.result_writer.write_result`. After
    ``maya`` exits, this function reads and parses that JSON file into a
    :class:`DiagnosticResult`.

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
    result_file = script_dir / "results" / "maya_result.json"

    # ------------------------------------------------------------------
    # Resolve AYON environment variables
    # ------------------------------------------------------------------
    from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env  # noqa: PLC0415

    ayon_env = resolve_ayon_env(
        project_name=project_name,
        folder_path=folder_path,
        task_name=task_name,
    )

    # ------------------------------------------------------------------
    # Build the maya -batch command
    # ------------------------------------------------------------------
    maya_cmd = _MAYA_PYTHON_CMD.format(script_path=script_path)
    cmd = [
        LINUX.maya_bin,
        "-batch",
        "-command",
        maya_cmd,
    ]

    logger.info(
        "Launching mayabatch for issue=%s  project=%s  folder=%s",
        issue_name,
        project_name,
        folder_path,
    )

    # ------------------------------------------------------------------
    # Run the subprocess
    # ------------------------------------------------------------------
    try:
        proc = subprocess.run(
            cmd,
            env=ayon_env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw_output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"").decode("utf-8", errors="replace") + (
            exc.stderr or b""
        ).decode("utf-8", errors="replace")
        logger.error("mayabatch timed out after %s seconds for issue=%s", timeout, issue_name)
        return DiagnosticResult(
            status="error",
            dcc="maya",
            issue=issue_name,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=[f"mayabatch timed out after {timeout}s"],
            raw_output=raw,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("mayabatch failed to launch for issue=%s", issue_name)
        return DiagnosticResult(
            status="error",
            dcc="maya",
            issue=issue_name,
            timestamp=datetime.now(tz=timezone.utc).isoformat(),
            context={"project": project_name, "folder": folder_path, "task": task_name},
            findings={},
            errors=[str(exc)],
            raw_output="",
        )

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
                timestamp=data.get("timestamp", datetime.now(tz=timezone.utc).isoformat()),
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
                timestamp=datetime.now(tz=timezone.utc).isoformat(),
                context={"project": project_name, "folder": folder_path, "task": task_name},
                findings={},
                errors=[f"Result JSON parse error: {exc}"],
                raw_output=raw_output,
            )

    # No result file produced -- treat as error
    errors = [f"No result file produced at {result_file}"]
    if proc.returncode != 0:
        errors.append(f"mayabatch exited with code {proc.returncode}")

    logger.warning("No result file found for issue=%s, returncode=%s", issue_name, proc.returncode)
    return DiagnosticResult(
        status="error",
        dcc="maya",
        issue=issue_name,
        timestamp=datetime.now(tz=timezone.utc).isoformat(),
        context={"project": project_name, "folder": folder_path, "task": task_name},
        findings={},
        errors=errors,
        raw_output=raw_output,
    )
