"""Unreal diagnostic facade.

Orchestrates the test-server guard, AYON context env, issue-dir conventions,
and hand-off to ``WindowsSshRunner``. Unreal execution is SSH-only for this
workflow: the current machine invokes SSH, then Windows runs Unreal headless.
All SSH/subprocess work lives in ``ssh_runner``; this module is a thin,
testable composition layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Literal

from gishant_scripts.diagnostic import ayon_env, path_mapper, result_fetcher, ssh_runner, test_server_guard
from gishant_scripts.diagnostic.maya_runner import DIAGNOSTIC_BASE_LINUX, DiagnosticRun


def _ensure_unreal_ssh_runner(runner: object) -> None:
    """Reject non-SSH Unreal execution in this workflow."""
    host = getattr(runner, "host", None)
    if host != ssh_runner.WINDOWS_HOST:
        raise ValueError(
            f"Unreal diagnostics are SSH-only and must target {ssh_runner.WINDOWS_HOST}; got {host!r}."
        )


def run_unreal(
    script_path_linux: str,
    project_name: str,
    folder_path: str,
    *,
    uproject_path: str,
    issue_name: str | None = None,
    bundle_name: str | None = None,
    app_name: str = "unreal/5.5",
    site_id: str | None = None,
    workdir: str | None = None,
    timeout_s: int = 600,
    runner: ssh_runner.WindowsSshRunner | None = None,
    fetch: object = result_fetcher.fetch_result,
    guard: object = test_server_guard.resolve_and_validate_test_env,
    env_resolver: Callable[..., dict[str, str]] = ayon_env.resolve_ayon_env,
) -> DiagnosticRun:
    """Run an Unreal diagnostic script on Windows via SSH."""
    runner = runner or ssh_runner.WindowsSshRunner()
    _ensure_unreal_ssh_runner(runner)
    issue = issue_name or Path(script_path_linux).parent.name
    issue_dir_linux = f"{DIAGNOSTIC_BASE_LINUX}/issues/{issue}"
    result_path_linux = f"{issue_dir_linux}/results/unreal_result.json"

    if uproject_path.startswith("/"):
        uproject_windows = path_mapper.linux_to_drive(uproject_path)
    else:
        uproject_windows = uproject_path

    local_cache = Path.home() / ".cache" / "gishant-diagnostic" / issue
    live_log = local_cache / "unreal.log"

    full_env = env_resolver(
        project_name=project_name,
        folder_path=folder_path,
        task_name=None,
        target="windows",
    )
    if bundle_name is not None:
        full_env["AYON_BUNDLE_NAME"] = bundle_name
    if app_name is not None:
        full_env["AYON_APP_NAME"] = app_name
    if site_id is not None:
        full_env["AYON_SITE_ID"] = site_id
    if workdir is not None:
        full_env["AYON_WORKDIR"] = workdir

    full_env.update(guard("windows"))

    exit_code = runner.run(
        script_path_linux=script_path_linux,
        uproject_drive=uproject_windows,
        env=full_env,
        issue_dir_linux=issue_dir_linux,
        timeout_s=timeout_s,
        live_log_local=live_log,
    )

    result_local: Path | None = None
    result_payload: dict | None = None
    status: Literal["pass", "fail", "error"] = "error"

    try:
        result_local = fetch(runner.host, result_path_linux, local_cache)
        result_payload = json.loads(result_local.read_text(encoding="utf-8"))
        raw_status = result_payload.get("status", "error")
        if exit_code == 0:
            status = raw_status if raw_status in ("pass", "fail", "error") else "error"
        else:
            status = raw_status if raw_status in ("pass", "fail", "error") else "fail"
    except result_fetcher.ResultFetchError:
        status = "error"

    return DiagnosticRun(
        status=status,
        dcc="unreal",
        exit_code=exit_code,
        result=result_payload,
        result_path=result_local,
        log_path=live_log,
    )
