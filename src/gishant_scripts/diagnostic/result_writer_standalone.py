"""Standalone result writer for diagnostic scripts running inside Maya/Unreal.

This module has ZERO dependencies beyond the Python stdlib so it can be
imported safely inside Maya/Unreal's Python interpreter without triggering
package-level imports that require pip-installed packages (e.g. dotenv).

Usage from inside a DCC script::

    import sys
    sys.path.insert(0, "<path-to-repo>/src/gishant_scripts/diagnostic")
    from result_writer_standalone import write_result

    write_result(
        script_path=__file__,
        dcc="maya",
        status="pass",
        context={"project": "MyProject", "folder": "/shots/sh010"},
        findings={"frame_count": 120},
    )
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_result(
    script_path: str,
    dcc: str,
    status: str,
    context: dict,
    findings: dict,
    errors: list | None = None,
) -> None:
    """Write diagnostic results JSON to ``{script_parent}/results/{dcc}_result.json``."""
    script_dir = Path(script_path).resolve().parent
    results_dir = script_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "status": status,
        "dcc": dcc,
        "issue": script_dir.name,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "context": context,
        "findings": findings,
        "errors": errors or [],
    }

    output_path = results_dir / f"{dcc}_result.json"
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
