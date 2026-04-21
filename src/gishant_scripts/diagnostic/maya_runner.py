"""Maya diagnostic facade.

Orchestrates the test-server guard, AYON context env, issue-dir conventions,
and hand-off to ``LinuxSshRunner``. All SSH/subprocess work lives in
``ssh_runner``; this module is a thin, testable composition layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gishant_scripts.diagnostic import result_fetcher, ssh_runner, test_server_guard

DIAGNOSTIC_BASE_LINUX = "/tech/users/gisi/dev/_diagnostic"


@dataclass(frozen=True)
class DiagnosticRun:
    """Structured result of a single runner invocation."""

    status: Literal["pass", "fail", "error"]
    dcc: Literal["maya", "unreal"]
    exit_code: int
    result: dict | None
    result_path: Path | None
    log_path: Path


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
        "QT_QPA_PLATFORM": "offscreen",
    }
    if bundle_name:
        env["AYON_BUNDLE_NAME"] = bundle_name
    if site_id:
        env["AYON_SITE_ID"] = site_id
    if workdir:
        env["AYON_WORKDIR"] = workdir
    return env


def run_maya(
    script_path_linux: str,
    project_name: str,
    folder_path: str,
    *,
    issue_name: str | None = None,
    bundle_name: str | None = None,
    app_name: str = "maya/2025",
    site_id: str | None = None,
    workdir: str | None = None,
    timeout_s: int = 300,
    runner: ssh_runner.LinuxSshRunner | None = None,
    fetch: object = result_fetcher.fetch_result,
    guard: object = test_server_guard.resolve_and_validate_test_env,
) -> DiagnosticRun:
    """Run a Maya diagnostic script on the Linux box.

    ``runner``, ``fetch``, ``guard`` are injected for testability. In
    production they default to the real SSH runner, SSH-fetched result, and
    test-server guard respectively.
    """
    runner = runner or ssh_runner.LinuxSshRunner()
    issue = issue_name or Path(script_path_linux).parent.name
    issue_dir_linux = f"{DIAGNOSTIC_BASE_LINUX}/issues/{issue}"
    result_path_linux = f"{issue_dir_linux}/results/maya_result.json"

    local_cache = Path.home() / ".cache" / "gishant-diagnostic" / issue
    live_log = local_cache / "maya.log"

    test_env = guard("linux")
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
        env=full_env,
        issue_dir_linux=issue_dir_linux,
        timeout_s=timeout_s,
        live_log_local=live_log,
    )

    result_local: Path | None = None
    result_payload: dict | None = None
    status: Literal["pass", "fail", "error"] = "error"

    if exit_code == 0:
        try:
            result_local = fetch(runner.host, result_path_linux, local_cache)
            result_payload = json.loads(result_local.read_text(encoding="utf-8"))
            raw_status = result_payload.get("status", "error")
            status = raw_status if raw_status in ("pass", "fail", "error") else "error"
        except result_fetcher.ResultFetchError:
            status = "error"
    else:
        # Best-effort fetch even on non-zero; diagnostic scripts sometimes
        # write result JSON before failing.
        try:
            result_local = fetch(runner.host, result_path_linux, local_cache)
            result_payload = json.loads(result_local.read_text(encoding="utf-8"))
            raw_status = result_payload.get("status", "fail")
            status = raw_status if raw_status in ("pass", "fail", "error") else "fail"
        except result_fetcher.ResultFetchError:
            status = "error"

    return DiagnosticRun(
        status=status,
        dcc="maya",
        exit_code=exit_code,
        result=result_payload,
        result_path=result_local,
        log_path=live_log,
    )
