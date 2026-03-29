"""CLI entry point for running diagnostic scripts inside Maya and Unreal."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console

if TYPE_CHECKING:
    from gishant_scripts.diagnostic.models import DiagnosticResult

app = typer.Typer(
    name="dcc-run",
    help="Run diagnostic scripts inside Maya (Linux) or Unreal (Windows), both locally.",
    no_args_is_help=True,
)
console = Console()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STATUS_COLORS: dict[str, str] = {
    "pass": "green",
    "fail": "red",
    "error": "yellow",
}

_STATUS_EXIT_CODES: dict[str, int] = {
    "pass": 0,
    "fail": 1,
    "error": 2,
}


def _print_result(result: DiagnosticResult) -> None:
    """Pretty-print a DiagnosticResult as coloured JSON and exit with the right code."""
    payload = {
        "status": result.status,
        "dcc": result.dcc,
        "issue": result.issue,
        "timestamp": result.timestamp,
        "context": result.context,
        "findings": result.findings,
        "errors": result.errors,
    }
    colour = _STATUS_COLORS.get(result.status, "white")
    console.print_json(json.dumps(payload, indent=2, default=str), highlight=True, style=colour)
    raise SystemExit(_STATUS_EXIT_CODES.get(result.status, 2))


# ---------------------------------------------------------------------------
# maya
# ---------------------------------------------------------------------------


@app.command()
def maya(
    project: Annotated[str, typer.Option("--project", help="AYON project name.")],
    folder: Annotated[str, typer.Option("--folder", help="AYON folder path.")],
    script: Annotated[Path, typer.Option("--script", help="Path to the Python diagnostic script.")],
    task: Annotated[str | None, typer.Option("--task", help="AYON task name.")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Process timeout in seconds.")] = 300,
) -> None:
    """Run a diagnostic script inside Maya batch on the local Linux machine."""
    from gishant_scripts.diagnostic.launcher_runner import run_maya

    result = run_maya(
        script_path=script,
        project_name=project,
        folder_path=folder,
        task_name=task,
        timeout=timeout,
    )
    _print_result(result)


# ---------------------------------------------------------------------------
# unreal
# ---------------------------------------------------------------------------


@app.command()
def unreal(
    project: Annotated[str, typer.Option("--project", help="AYON project name.")],
    folder: Annotated[str, typer.Option("--folder", help="AYON folder path.")],
    script: Annotated[Path, typer.Option("--script", help="Path to the Python diagnostic script.")],
    task: Annotated[str | None, typer.Option("--task", help="AYON task name.")] = None,
    unreal_project: Annotated[
        str | None, typer.Option("--unreal-project", help="Path to .uproject file (Windows path).")
    ] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Process timeout in seconds.")] = 600,
) -> None:
    """Run a diagnostic script inside Unreal Engine locally on Windows."""
    from gishant_scripts.diagnostic.launcher_runner import run_unreal

    result = run_unreal(
        script_path=script,
        project_name=project,
        folder_path=folder,
        task_name=task,
        unreal_project=unreal_project,
        timeout=timeout,
    )
    _print_result(result)


# ---------------------------------------------------------------------------
# pipeline (maya + unreal in sequence)
# ---------------------------------------------------------------------------


@app.command()
def pipeline(
    project: Annotated[str, typer.Option("--project", help="AYON project name.")],
    folder: Annotated[str, typer.Option("--folder", help="AYON folder path.")],
    maya_script: Annotated[Path, typer.Option("--maya-script", help="Path to the Maya diagnostic script.")],
    unreal_script: Annotated[Path, typer.Option("--unreal-script", help="Path to the Unreal diagnostic script.")],
    task: Annotated[str | None, typer.Option("--task", help="AYON task name.")] = None,
    unreal_project: Annotated[
        str | None, typer.Option("--unreal-project", help="Path to .uproject file (Windows path).")
    ] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Per-DCC timeout in seconds.")] = 600,
) -> None:
    """Run Maya then Unreal diagnostic scripts in sequence, reporting both results."""
    from gishant_scripts.diagnostic.launcher_runner import run_maya, run_unreal

    results: list[dict] = []
    overall_exit = 0

    # -- Maya ---------------------------------------------------------------
    console.rule("[bold]Maya diagnostic[/bold]")
    maya_result = run_maya(
        script_path=maya_script,
        project_name=project,
        folder_path=folder,
        task_name=task,
        timeout=timeout,
    )

    maya_payload = {
        "status": maya_result.status,
        "dcc": maya_result.dcc,
        "issue": maya_result.issue,
        "timestamp": maya_result.timestamp,
        "context": maya_result.context,
        "findings": maya_result.findings,
        "errors": maya_result.errors,
    }
    colour = _STATUS_COLORS.get(maya_result.status, "white")
    console.print_json(json.dumps(maya_payload, indent=2, default=str), highlight=True, style=colour)
    results.append(maya_payload)
    overall_exit = max(overall_exit, _STATUS_EXIT_CODES.get(maya_result.status, 2))

    # -- Unreal -------------------------------------------------------------
    console.rule("[bold]Unreal diagnostic[/bold]")
    unreal_result = run_unreal(
        script_path=unreal_script,
        project_name=project,
        folder_path=folder,
        task_name=task,
        unreal_project=unreal_project,
        timeout=timeout,
    )

    unreal_payload = {
        "status": unreal_result.status,
        "dcc": unreal_result.dcc,
        "issue": unreal_result.issue,
        "timestamp": unreal_result.timestamp,
        "context": unreal_result.context,
        "findings": unreal_result.findings,
        "errors": unreal_result.errors,
    }
    colour = _STATUS_COLORS.get(unreal_result.status, "white")
    console.print_json(json.dumps(unreal_payload, indent=2, default=str), highlight=True, style=colour)
    results.append(unreal_payload)
    overall_exit = max(overall_exit, _STATUS_EXIT_CODES.get(unreal_result.status, 2))

    # -- Summary ------------------------------------------------------------
    console.rule("[bold]Summary[/bold]")
    for r in results:
        tag = "[" + _STATUS_COLORS.get(r["status"], "white") + "]" + r["status"].upper() + "[/]"
        console.print("  " + r["dcc"] + ": " + tag)

    sys.exit(overall_exit)


def main() -> None:
    """Entry point for the ``dcc-run`` console script."""
    app()
