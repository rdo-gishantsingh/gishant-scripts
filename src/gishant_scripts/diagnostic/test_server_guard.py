"""Resolve and validate AYON / Kitsu TEST server credentials from a target box.

Project-wide rule: diagnostic runs **must always** target the test servers,
never production. This module is the single choke-point where that rule is
enforced in code. Every runner must call
:func:`resolve_and_validate_test_env` before composing the preamble or ``.ps1``
handed off to the DCC.

The guard:

1. Reads ``~/.rdo/.env`` from the target box (not from the WSL dispatcher).
2. Picks the test-server keys (``AYON_TEST_SERVER_URL`` / ``AYON_TEST_API_KEY``
   and optional Kitsu equivalents).
3. Hard-fails on missing keys.
4. Rejects any URL that doesn't contain one of ``localhost``, ``10.1.69.24``,
   or ``127.0.0.1`` — this is the whitelist.
5. Returns a dict already renamed to the production key names
   (``AYON_SERVER_URL`` / ``AYON_API_KEY`` / ``RDO_KITSU_HOST`` /
   ``RDO_KITSU_API_TOKEN``) so the caller can inject it directly into the DCC
   environment without any further renaming.

The ``_reader`` hook lets tests inject a fake ``~/.rdo/.env`` body without
touching SSH.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import Callable, Final, Literal

Target = Literal["linux", "windows"]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WHITELIST_TOKENS: Final[tuple[str, ...]] = ("localhost", "10.1.69.24", "127.0.0.1")

# Target-box SSH hosts. Kept here (not in config) because the guard must work
# even when the rest of the config module fails to import for any reason.
_TARGET_HOSTS: Final[dict[Target, str]] = {
    "linux": "gisi@10.1.69.24",
    "windows": "gisi@10.1.69.122",
}


class TestServerConfigError(RuntimeError):
    """Raised when test-server credentials are missing or point at production."""

    # Prevent pytest from trying to collect this class as a test container.
    __test__ = False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_env_file(body: str) -> dict[str, str]:
    """Parse a dotenv-style string into a ``{key: value}`` dict.

    Ignores blank lines and ``#`` comments. Strips surrounding single or double
    quotes from values. Values containing ``=`` are preserved intact.
    """
    result: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip a single layer of matching quotes.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def _default_ssh_reader(target: Target) -> str:
    """Default reader: ``ssh <target> "cat ~/.rdo/.env"``.

    Uses ``cat`` even on Windows (Git Bash / OpenSSH for Windows both ship it
    in practice, and pwsh inside cmd.exe OpenSSH produces mangled output for
    backslash paths — see tools notes). The target's ``~`` is resolved
    server-side by the login shell.
    """
    host = _TARGET_HOSTS[target]
    if target == "windows":
        # On Windows, the default shell for SSH is pwsh 7 per the Forge adapter.
        # Use Get-Content with the user profile; it handles backslash paths.
        cmd = ["ssh", "-o", "BatchMode=yes", host, "pwsh", "-NoProfile", "-NonInteractive", "-Command",
               "Get-Content -Raw $HOME\\.rdo\\.env"]
    else:
        cmd = ["ssh", "-o", "BatchMode=yes", host, "cat ~/.rdo/.env"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    if proc.returncode != 0:
        msg = (
            f"Failed to read ~/.rdo/.env from {host} "
            f"(exit {proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
        raise TestServerConfigError(msg)
    return proc.stdout


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _validate_url(url: str, var_name: str) -> None:
    """Raise :class:`TestServerConfigError` unless *url* is on the whitelist."""
    if not url:
        msg = f"{var_name} is missing or empty; refusing to run diagnostic"
        raise TestServerConfigError(msg)
    if not any(token in url for token in _WHITELIST_TOKENS):
        msg = (
            f"refusing to run diagnostic against non-test server "
            f"({var_name}={url!r}); allowed tokens: {_WHITELIST_TOKENS}"
        )
        raise TestServerConfigError(msg)


def resolve_and_validate_test_env(
    target: Target,
    reader: Callable[[Target], str] = _default_ssh_reader,
) -> dict[str, str]:
    """Resolve AYON (and optionally Kitsu) test-server env for *target*.

    Args:
        target: Either ``"linux"`` or ``"windows"`` — picks which target box's
            ``~/.rdo/.env`` to read.
        reader: Callable that returns the raw content of the target's
            ``~/.rdo/.env``. Defaults to an SSH-based reader; injectable for
            tests.

    Returns:
        A dict with these keys, ready to inject into the DCC environment:

        - ``AYON_SERVER_URL``     (always; renamed from ``AYON_TEST_SERVER_URL``)
        - ``AYON_API_KEY``        (always; renamed from ``AYON_TEST_API_KEY``)
        - ``RDO_KITSU_HOST``      (only if ``RDO_KITSU_TEST_HOST`` is set)
        - ``RDO_KITSU_API_TOKEN`` (only if ``RDO_KITSU_TEST_API_TOKEN`` is set)

    Raises:
        TestServerConfigError: If required AYON keys are missing, or any
            resolved URL does not contain a whitelisted token
            (``localhost``, ``10.1.69.24``, ``127.0.0.1``).

    """
    body = reader(target)
    parsed = _parse_env_file(body)

    ayon_url = parsed.get("AYON_TEST_SERVER_URL", "").strip()
    ayon_key = parsed.get("AYON_TEST_API_KEY", "").strip()

    _validate_url(ayon_url, "AYON_TEST_SERVER_URL")
    if not ayon_key:
        msg = "AYON_TEST_API_KEY is missing or empty; refusing to run diagnostic"
        raise TestServerConfigError(msg)

    resolved: dict[str, str] = {
        "AYON_SERVER_URL": ayon_url,
        "AYON_API_KEY": ayon_key,
    }

    kitsu_host = parsed.get("RDO_KITSU_TEST_HOST", "").strip()
    kitsu_token = parsed.get("RDO_KITSU_TEST_API_TOKEN", "").strip()
    if kitsu_host or kitsu_token:
        # If either is set, both must be, and the host must pass the whitelist.
        if not kitsu_host:
            msg = "RDO_KITSU_TEST_API_TOKEN set but RDO_KITSU_TEST_HOST missing"
            raise TestServerConfigError(msg)
        if not kitsu_token:
            msg = "RDO_KITSU_TEST_HOST set but RDO_KITSU_TEST_API_TOKEN missing"
            raise TestServerConfigError(msg)
        _validate_url(kitsu_host, "RDO_KITSU_TEST_HOST")
        resolved["RDO_KITSU_HOST"] = kitsu_host
        resolved["RDO_KITSU_API_TOKEN"] = kitsu_token

    return resolved


# Keep linter happy when shlex is used by downstream runners only.
_ = shlex
