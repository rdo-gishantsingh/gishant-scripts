"""Unreal diagnostic facade.

Orchestrates the test-server guard, AYON context env, issue-dir conventions,
and hand-off to ``WindowsSshRunner``. All SSH/subprocess work lives in
``ssh_runner``; this module is a thin, testable composition layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from gishant_scripts.diagnostic import path_mapper, result_fetcher, ssh_runner, test_server_guard
from gishant_scripts.diagnostic.maya_runner import DIAGNOSTIC_BASE_LINUX, DiagnosticRun


def _build_context_env(
    project_name: str,
    folder_path: str,
    bundle_name: str | None,
    app_name: str,
    site_id: str | None,
    workdir: str | None,
) -> dict[str, str]:
    """Return the AYON context env vars the diagnostic script expects."""
    env: dict[str, str] = {
        "AYON_PROJECT_NAME": project_name,
        "AYON_FOLDER_PATH": folder_path,
        "AYON_APP_NAME": app_name,
        "AYON_HEADLESS_MODE": "1",
    }
    if bundle_name:
        env["AYON_BUNDLE_NAME"] = bundle_name
    if site_id:
        env["AYON_SITE_ID"] = site_id
    if workdir:
        env["AYON_WORKDIR"] = workdir
    return env


def run_unreal(
    script_path_linux: str,
    project_name: str,
    folder_path: str,
    *,
    uproject_path: str,
    issue_name: str | None = None,
    bundle_name: str | None = None,
    app_name: str = "unreal/5-5",
    site_id: str | None = None,
    workdir: str | None = None,
    timeout_s: int = 600,
    runner: ssh_runner.WindowsSshRunner | None = None,
    fetch: object = result_fetcher.fetch_result,
    guard: object = test_server_guard.resolve_and_validate_test_env,
) -> DiagnosticRun:
    """Run an Unreal diagnostic script on the Windows box.

    ``uproject_path`` may be a Linux NAS path (auto-converted to Z:/P:) or a
    Windows drive-letter path; passed through to :mod:`path_mapper` if it
    begins with ``/``.

    ``runner``, ``fetch``, ``guard`` are injected for testability.
    """
    runner = runner or ssh_runner.WindowsSshRunner()
    issue = issue_name or Path(script_path_linux).parent.name
    issue_dir_linux = f"{DIAGNOSTIC_BASE_LINUX}/issues/{issue}"
    result_path_linux = f"{issue_dir_linux}/results/unreal_result.json"

    uproject_drive = path_mapper.linux_to_drive(uproject_path) if uproject_path.startswith("/") else uproject_path

    local_cache = Path.home() / ".cache" / "gishant-diagnostic" / issue
    live_log = local_cache / "unreal.log"

    test_env = guard("windows")
    ctx_env = _build_context_env(
        project_name=project_name,
        folder_path=folder_path,
        bundle_name=bundle_name,
        app_name=app_name,
        site_id=site_id,
        workdir=workdir,
    )
    full_env = {**test_env, **ctx_env}

    exit_code = runner.run(
        script_path_linux=script_path_linux,
        uproject_drive=uproject_drive,
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
