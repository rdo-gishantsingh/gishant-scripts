"""Generate the bash preamble used by :class:`LinuxSshRunner`.

The preamble exports AYON environment variables, activates the canonical venv
on the NAS, and leaves the shell ``cd``'d into the repo root so relative
imports resolve predictably. The final invocation (``maya -batch ...``) is
concatenated by the caller.
"""

from __future__ import annotations

import shlex

DEFAULT_REPO_PATH = "/tech/users/gisi/dev/repos/gishant-scripts"
DEFAULT_VENV_ACTIVATE = f"{DEFAULT_REPO_PATH}/.venv/bin/activate"


def _env_exports(env: dict[str, str]) -> list[str]:
    """Return a list of ``export KEY=VALUE`` statements with safe shell quoting."""
    return [f"export {key}={shlex.quote(value)}" for key, value in sorted(env.items())]


def build_preamble(
    env: dict[str, str],
    repo_path: str = DEFAULT_REPO_PATH,
    venv_activate: str = DEFAULT_VENV_ACTIVATE,
) -> str:
    """Build the bash preamble for a Linux SSH diagnostic run.

    Args:
        env: Environment variables to export (AYON_*, QT_*, etc.).
        repo_path: Absolute path to the gishant-scripts checkout on the target.
        venv_activate: Absolute path to the venv's ``bin/activate`` script.

    Returns:
        A multi-line bash string ready to prepend to the command of interest,
        joined with ``&&`` by the caller.

    """
    parts: list[str] = [
        "set -e",
        *_env_exports(env),
        f"cd {shlex.quote(repo_path)}",
        f"source {shlex.quote(venv_activate)}",
    ]
    return " && ".join(parts)


def build_full_command(
    env: dict[str, str],
    command: str,
    repo_path: str = DEFAULT_REPO_PATH,
    venv_activate: str = DEFAULT_VENV_ACTIVATE,
) -> str:
    """Return a full bash command string: preamble + ``&&`` + *command*."""
    preamble = build_preamble(env=env, repo_path=repo_path, venv_activate=venv_activate)
    return f"{preamble} && {command}"
