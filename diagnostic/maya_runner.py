"""Maya diagnostic facade.

Orchestrates the test-server guard, AYON context env, issue-dir conventions,
and hand-off to ``LinuxSshRunner``. All SSH/subprocess work lives in
``ssh_runner``; this module is a thin, testable composition layer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from diagnostic import ayon_env, result_fetcher, ssh_runner, test_server_guard

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
    env_resolver: Callable[..., dict[str, str]] = ayon_env.resolve_ayon_env,
) -> DiagnosticRun:
    """Run a Maya diagnostic script on the Linux box.

    ``runner``, ``fetch``, ``guard``, and ``env_resolver`` are injected for
    testability. In production they default to the real runner, result fetcher,
    test-server guard, and AYON env resolver.
    """
    runner = runner or ssh_runner.LinuxSshRunner()
    issue = issue_name or Path(script_path_linux).parent.name
    issue_dir_linux = f"{DIAGNOSTIC_BASE_LINUX}/issues/{issue}"
    result_path_linux = f"{issue_dir_linux}/results/maya_result.json"

    local_cache = Path.home() / ".cache" / "gishant-diagnostic" / issue
    live_log = local_cache / "maya.log"

    full_env = env_resolver(
        project_name=project_name,
        folder_path=folder_path,
        task_name=None,
        target="linux",
    )
    if bundle_name is not None:
        full_env["AYON_BUNDLE_NAME"] = bundle_name
    if app_name is not None:
        full_env["AYON_APP_NAME"] = app_name
    if site_id is not None:
        full_env["AYON_SITE_ID"] = site_id
    if workdir is not None:
        full_env["AYON_WORKDIR"] = workdir

    # Guard remains the policy choke-point for test-only credentials.
    full_env.update(guard("linux"))

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
