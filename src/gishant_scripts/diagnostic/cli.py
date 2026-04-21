"""CLI entry point for running diagnostic scripts inside Maya and Unreal.

Maya supports dual execution modes:
- local Linux execution when running on the office Linux host
- WSL/other-hop execution via SSH to the Linux host

Unreal executes via SSH to the Windows host. The ``pipeline`` subcommand
runs Maya and Unreal in parallel via a thread pool.
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console

from gishant_scripts.diagnostic import test_server_guard

if TYPE_CHECKING:
    from gishant_scripts.diagnostic.maya_runner import DiagnosticRun

app = typer.Typer(
    name="dcc-run",
    help="Run diagnostic scripts inside Maya (Linux local/SSH) or Unreal (Windows via SSH).",
    no_args_is_help=True,
)
console = Console()

_STATUS_COLORS: dict[str, str] = {"pass": "green", "fail": "red", "error": "yellow"}
_STATUS_EXIT_CODES: dict[str, int] = {"pass": 0, "fail": 1, "error": 2}
GUARD_REFUSED_EXIT = 3


def _print_run(run: DiagnosticRun) -> None:
    """Pretty-print a single DiagnosticRun."""
    payload = {
        "status": run.status,
        "dcc": run.dcc,
        "exit_code": run.exit_code,
        "result_path": str(run.result_path) if run.result_path else None,
        "log_path": str(run.log_path),
        "result": run.result,
    }
    colour = _STATUS_COLORS.get(run.status, "white")
    console.rule(f"[bold {colour}]{run.dcc.upper()} — {run.status.upper()}[/]")
    console.print_json(json.dumps(payload, indent=2, default=str))


@app.command()
def maya(
    project: Annotated[str, typer.Option("--project", help="AYON project name.")],
    folder: Annotated[str, typer.Option("--folder", help="AYON folder path.")],
    script: Annotated[str, typer.Option("--script", help="Linux path to diagnostic script.")],
    bundle: Annotated[str | None, typer.Option("--bundle", help="AYON bundle name.")] = None,
    workdir: Annotated[str | None, typer.Option("--workdir", help="AYON workdir (linux).")] = None,
    site_id: Annotated[str | None, typer.Option("--site-id", help="AYON site id.")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Timeout seconds.")] = 300,
) -> None:
    """Run a Maya diagnostic script on the Linux box."""
    from gishant_scripts.diagnostic.maya_runner import run_maya

    try:
        run = run_maya(
            script_path_linux=script,
            project_name=project,
            folder_path=folder,
            bundle_name=bundle,
            site_id=site_id,
            workdir=workdir,
            timeout_s=timeout,
        )
    except test_server_guard.TestServerConfigError as exc:
        console.print(f"[bold red]Test-server guard refused:[/] {exc}")
        raise SystemExit(GUARD_REFUSED_EXIT) from None

    _print_run(run)
    raise SystemExit(_STATUS_EXIT_CODES.get(run.status, 2))


@app.command()
def unreal(
    project: Annotated[str, typer.Option("--project", help="AYON project name.")],
    folder: Annotated[str, typer.Option("--folder", help="AYON folder path.")],
    script: Annotated[str, typer.Option("--script", help="Linux path to diagnostic script.")],
    uproject: Annotated[str, typer.Option("--uproject", help="Linux or drive-letter path to .uproject.")],
    bundle: Annotated[str | None, typer.Option("--bundle", help="AYON bundle name.")] = None,
    workdir: Annotated[str | None, typer.Option("--workdir", help="AYON workdir.")] = None,
    site_id: Annotated[str | None, typer.Option("--site-id", help="AYON site id.")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Timeout seconds.")] = 600,
) -> None:
    """Run an Unreal diagnostic script on the Windows box."""
    from gishant_scripts.diagnostic.unreal_runner import run_unreal

    try:
        run = run_unreal(
            script_path_linux=script,
            project_name=project,
            folder_path=folder,
            uproject_path=uproject,
            bundle_name=bundle,
            site_id=site_id,
            workdir=workdir,
            timeout_s=timeout,
        )
    except test_server_guard.TestServerConfigError as exc:
        console.print(f"[bold red]Test-server guard refused:[/] {exc}")
        raise SystemExit(GUARD_REFUSED_EXIT) from None

    _print_run(run)
    raise SystemExit(_STATUS_EXIT_CODES.get(run.status, 2))


@app.command()
def pipeline(
    project: Annotated[str, typer.Option("--project", help="AYON project name.")],
    folder: Annotated[str, typer.Option("--folder", help="AYON folder path.")],
    maya_script: Annotated[str, typer.Option("--maya-script", help="Linux path to Maya script.")],
    unreal_script: Annotated[str, typer.Option("--unreal-script", help="Linux path to Unreal script.")],
    uproject: Annotated[str, typer.Option("--uproject", help="Linux or drive-letter .uproject path.")],
    bundle: Annotated[str | None, typer.Option("--bundle", help="AYON bundle name.")] = None,
    workdir: Annotated[str | None, typer.Option("--workdir", help="AYON workdir.")] = None,
    site_id: Annotated[str | None, typer.Option("--site-id", help="AYON site id.")] = None,
    timeout: Annotated[int, typer.Option("--timeout", help="Per-DCC timeout seconds.")] = 600,
) -> None:
    """Run Maya and Unreal diagnostics in parallel and report both results."""
    from gishant_scripts.diagnostic.maya_runner import run_maya
    from gishant_scripts.diagnostic.unreal_runner import run_unreal

    def _maya() -> DiagnosticRun:
        return run_maya(
            script_path_linux=maya_script,
            project_name=project,
            folder_path=folder,
            bundle_name=bundle,
            site_id=site_id,
            workdir=workdir,
            timeout_s=timeout,
        )

    def _unreal() -> DiagnosticRun:
        return run_unreal(
            script_path_linux=unreal_script,
            project_name=project,
            folder_path=folder,
            uproject_path=uproject,
            bundle_name=bundle,
            site_id=site_id,
            workdir=workdir,
            timeout_s=timeout,
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            maya_future = pool.submit(_maya)
            unreal_future = pool.submit(_unreal)
            maya_run = maya_future.result()
            unreal_run = unreal_future.result()
    except test_server_guard.TestServerConfigError as exc:
        console.print(f"[bold red]Test-server guard refused:[/] {exc}")
        raise SystemExit(GUARD_REFUSED_EXIT) from None

    _print_run(maya_run)
    _print_run(unreal_run)

    console.rule("[bold]Summary[/bold]")
    for run in (maya_run, unreal_run):
        tag = "[" + _STATUS_COLORS.get(run.status, "white") + "]" + run.status.upper() + "[/]"
        console.print("  " + run.dcc + ": " + tag)

    overall = max(
        _STATUS_EXIT_CODES.get(maya_run.status, 2),
        _STATUS_EXIT_CODES.get(unreal_run.status, 2),
    )
    sys.exit(overall)


def main() -> None:
    """Entry point for the ``dcc-run`` console script."""
    app()


if __name__ == "__main__":
    app()
