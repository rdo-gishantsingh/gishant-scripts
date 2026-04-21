"""Fetch a diagnostic result JSON file from the target box.

For Linux-targeted runs the CLI executes on the office Linux machine itself,
so result JSON files can be read directly from the NAS path. For Windows-
targeted runs we still fall back to ``ssh <host> "cat <path>"`` and cache
that payload locally.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path


class ResultFetchError(RuntimeError):
    """Base class for errors raised by :mod:`result_fetcher`."""


class ResultNotFoundError(ResultFetchError):
    """Raised when the remote result file is missing or empty."""


class ResultMalformedError(ResultFetchError):
    """Raised when the fetched payload is not parseable JSON."""


def _validate_json_payload(payload: str, source: str) -> None:
    if not payload.strip():
        raise ResultNotFoundError(f"result file is empty: {source}")
    try:
        json.loads(payload)
    except json.JSONDecodeError as exc:
        snippet = payload[:200].replace("\n", "\\n")
        msg = f"result file is not valid JSON ({exc}); first 200 bytes: {snippet!r}"
        raise ResultMalformedError(msg) from exc


def fetch_result(
    ssh_host: str,
    remote_path_linux: str,
    local_cache_dir: Path,
) -> Path:
    """Fetch a result JSON file and cache it locally.

    Args:
        ssh_host: SSH target (e.g. ``"gisi@10.1.69.24"``).
        remote_path_linux: Absolute Linux-style path on the target box.
        local_cache_dir: Local directory to write the cached copy into.
            Created if missing.

    Returns:
        Path to the local cache file.

    Raises:
        ResultNotFoundError: If the result file is missing or empty.
        ResultMalformedError: If the payload is not valid JSON.
    """
    local_cache_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_cache_dir / Path(remote_path_linux).name

    remote_path = Path(remote_path_linux)
    if remote_path.exists():
        payload = remote_path.read_text(encoding="utf-8")
        _validate_json_payload(payload, str(remote_path))
        local_path.write_text(payload, encoding="utf-8")
        return local_path

    cmd = ["ssh", "-o", "BatchMode=yes", ssh_host, f"cat {shlex.quote(remote_path_linux)}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)

    if proc.returncode != 0:
        msg = (
            f"failed to fetch {remote_path_linux!r} from {ssh_host} "
            f"(exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
        raise ResultNotFoundError(msg)

    payload = proc.stdout
    _validate_json_payload(payload, f"{ssh_host}:{remote_path_linux}")
    local_path.write_text(payload, encoding="utf-8")
    return local_path
