"""Helper for diagnostic scripts running inside Maya/Unreal to write their results.

Usage from inside a DCC script::

    from gishant_scripts.diagnostic.result_writer import write_result

    write_result(
        script_path=__file__,
        dcc="maya",
        status="pass",
        context={"project": "MyProject", "folder": "/shots/sh010", "fps": 24.0},
        findings={"frame_count": 120, "missing_textures": []},
    )
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def write_result(
    script_path: str,
    dcc: str,
    status: str,
    context: dict,
    findings: dict,
    errors: list[str] | None = None,
) -> None:
    """Write diagnostic results JSON.

    Called from inside Maya/Unreal scripts. The output file is written to
    ``{script_parent}/results/{dcc}_result.json``, creating the ``results``
    directory if it does not already exist.

    Args:
        script_path: ``__file__`` of the calling diagnostic script.
        dcc: DCC identifier, e.g. ``"maya"`` or ``"unreal"``.
        status: One of ``"pass"``, ``"fail"``, ``"error"``.
        context: Contextual information (project, folder, fps, etc.).
        findings: Free-form diagnostic data produced by the script.
        errors: Optional list of error messages encountered during the run.

    """
    script_dir = Path(script_path).resolve().parent
    results_dir = script_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": status,
        "dcc": dcc,
        "issue": script_dir.name,
        "timestamp": datetime.now(tz=UTC).isoformat(),
        "context": context,
        "findings": findings,
        "errors": errors or [],
    }

    output_path = results_dir / f"{dcc}_result.json"
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
