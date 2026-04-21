"""Bulk-remove test projects from Kitsu and/or AYON by name prefix.

Safety rules:
- Prefix must be non-empty and start with an underscore.
- Every candidate project name is double-checked with ``startswith(prefix)``
  before deletion.
- Production access requires an explicit ``--env prod`` flag plus
  an interactive confirmation (or ``--yes`` to bypass).

Kitsu quirk: ``gazu.project.remove_project(force=True)`` returns HTTP 400
unless the project status is first set to "Closed". We close the project
before attempting deletion.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

_log = logging.getLogger(__name__)

# Default .env location for RDO credentials.
_RDO_ENV_PATH = Path.home() / ".rdo" / ".env"

# Valid values for --server.
_SERVER_KITSU = "kitsu"
_SERVER_AYON = "ayon"
_SERVER_BOTH = "both"
_VALID_SERVERS = frozenset({_SERVER_KITSU, _SERVER_AYON, _SERVER_BOTH})

# Valid values for --env.
_ENV_TEST = "test"
_ENV_PROD = "prod"
_VALID_ENVS = frozenset({_ENV_TEST, _ENV_PROD})


def validate_prefix(prefix: str) -> None:
    """Validate *prefix* against the safety rules.

    Raises ``typer.Exit(code=1)`` if the prefix is empty or does not start
    with an underscore. We never allow wildcard or loose prefixes because
    this command can delete many projects at once.

    Args:
        prefix: The project-name prefix to validate.

    """
    if not prefix:
        _log.error("Empty prefix is not allowed.")
        raise typer.Exit(code=1)
    if not prefix.startswith("_"):
        _log.error("Prefix %r must start with an underscore.", prefix)
        raise typer.Exit(code=1)


def _get_kitsu_creds(env: str) -> tuple[str | None, str | None]:
    """Return ``(host, token)`` for Kitsu in the requested *env*."""
    load_dotenv(_RDO_ENV_PATH)
    if env == _ENV_TEST:
        return (
            os.environ.get("RDO_KITSU_TEST_HOST"),
            os.environ.get("RDO_KITSU_TEST_API_TOKEN"),
        )
    return (
        os.environ.get("RDO_KITSU_HOST"),
        os.environ.get("RDO_KITSU_API_TOKEN"),
    )


def _get_ayon_creds(env: str) -> tuple[str | None, str | None]:
    """Return ``(server_url, api_key)`` for AYON in the requested *env*."""
    load_dotenv(_RDO_ENV_PATH)
    if env == _ENV_TEST:
        return (
            os.environ.get("AYON_TEST_SERVER_URL"),
            os.environ.get("AYON_TEST_API_KEY"),
        )
    return (
        os.environ.get("AYON_SERVER_URL"),
        os.environ.get("AYON_API_KEY"),
    )


def _remove_kitsu_project_safely(project: dict) -> None:
    """Close then force-remove a Kitsu project.

    ``remove_project(force=True)`` returns HTTP 400 unless the project
    status is "Closed" first. This helper handles both steps.
    """
    import gazu

    closed_status = gazu.project.get_project_status_by_name("Closed")
    if not closed_status:
        msg = "Kitsu 'Closed' project status not found on server."
        raise RuntimeError(msg)

    project["project_status_id"] = closed_status["id"]
    gazu.project.update_project(project)
    gazu.project.remove_project(project, force=True)


def _remove_kitsu_projects(
    prefix: str,
    env: str,
    *,
    dry_run: bool,
    console: Console,
) -> None:
    """Remove Kitsu projects whose names start with *prefix*."""
    import gazu

    host, token = _get_kitsu_creds(env)
    if not host or not token:
        expected = (
            "RDO_KITSU_TEST_HOST / RDO_KITSU_TEST_API_TOKEN"
            if env == _ENV_TEST
            else "RDO_KITSU_HOST / RDO_KITSU_API_TOKEN"
        )
        _log.error("Kitsu credentials missing. Expected: %s", expected)
        raise typer.Exit(code=1)

    gazu.set_host(host + "/api")
    gazu.set_token(token)

    _log.info("Kitsu: connected to %s (env=%s)", host, env)

    all_projects = gazu.project.all_projects()
    candidates = [p for p in all_projects if p.get("name", "").startswith(prefix)]
    _log.info("Kitsu: %d project(s) match prefix %r", len(candidates), prefix)

    for project in candidates:
        name = project.get("name", "")
        # Double-check: we only delete names that truly start with the prefix.
        if not name.startswith(prefix):
            _log.warning("Kitsu: skipping %s -- does not start with %r", name, prefix)
            continue

        if dry_run:
            console.print(f"[yellow]DRY-RUN[/] Kitsu: would remove project {name}")
            _log.info("Kitsu: dry-run match %s (id=%s)", name, project.get("id"))
            continue

        _log.info("Kitsu: removing project %s (id=%s)", name, project.get("id"))
        try:
            _remove_kitsu_project_safely(project)
        except Exception as exc:  # gazu raises varied HTTP exception types
            _log.warning("Kitsu: failed to remove %s -- %s", name, exc)
            console.print(f"[red]FAIL[/] Kitsu: {name} -- {exc}")
        else:
            _log.info("Kitsu: removed %s", name)
            console.print(f"[green]OK[/] Kitsu: removed {name}")


def _remove_ayon_projects(
    prefix: str,
    env: str,
    *,
    dry_run: bool,
    console: Console,
) -> None:
    """Remove AYON projects whose names start with *prefix*."""
    import ayon_api

    server_url, api_key = _get_ayon_creds(env)
    if not server_url or not api_key:
        expected = "AYON_TEST_SERVER_URL / AYON_TEST_API_KEY" if env == _ENV_TEST else "AYON_SERVER_URL / AYON_API_KEY"
        _log.error("AYON credentials missing. Expected: %s", expected)
        raise typer.Exit(code=1)

    os.environ["AYON_SERVER_URL"] = server_url
    os.environ["AYON_API_KEY"] = api_key
    if not ayon_api.is_connection_created():
        ayon_api.create_connection()

    _log.info("AYON: connected to %s (env=%s)", server_url, env)

    all_projects = list(ayon_api.get_projects(fields=["name"]))
    candidates = [p for p in all_projects if p.get("name", "").startswith(prefix)]
    _log.info("AYON: %d project(s) match prefix %r", len(candidates), prefix)

    for project in candidates:
        name = project.get("name", "")
        # Double-check: we only delete names that truly start with the prefix.
        if not name.startswith(prefix):
            _log.warning("AYON: skipping %s -- does not start with %r", name, prefix)
            continue

        if dry_run:
            console.print(f"[yellow]DRY-RUN[/] AYON: would remove project {name}")
            _log.info("AYON: dry-run match %s", name)
            continue

        _log.info("AYON: removing project %s", name)
        try:
            ayon_api.delete_project(name)
        except Exception as exc:  # ayon_api raises varied HTTP exception types
            _log.warning("AYON: failed to remove %s -- %s", name, exc)
            console.print(f"[red]FAIL[/] AYON: {name} -- {exc}")
        else:
            _log.info("AYON: removed %s", name)
            console.print(f"[green]OK[/] AYON: removed {name}")


def remove_projects(
    *,
    prefix: str,
    server: str,
    env: str,
    dry_run: bool,
    yes: bool,
    console: Console | None = None,
) -> None:
    """Bulk-remove test projects from Kitsu and/or AYON by name prefix.

    This is the programmatic entry point; the Typer command is a thin
    wrapper around it.

    Args:
        prefix: Project-name prefix. Must start with ``_``.
        server: One of ``kitsu``, ``ayon``, ``both``.
        env: One of ``test`` (default), ``prod``.
        dry_run: If True, list matches without deleting.
        yes: If True, skip the production confirmation prompt.
        console: Optional Rich console for user output.

    """
    console = console or Console()

    validate_prefix(prefix)

    if server not in _VALID_SERVERS:
        _log.error("Invalid --server %r. Must be one of: %s", server, ", ".join(sorted(_VALID_SERVERS)))
        raise typer.Exit(code=1)

    if env not in _VALID_ENVS:
        _log.error("Invalid --env %r. Must be one of: %s", env, ", ".join(sorted(_VALID_ENVS)))
        raise typer.Exit(code=1)

    if env == _ENV_PROD and not yes:
        console.print(
            "[bold red]WARNING:[/] You are about to delete projects from PRODUCTION "
            f"with prefix {prefix!r} on {server}.",
        )
        if not typer.confirm("Continue?"):
            _log.info("Aborted by user.")
            raise typer.Exit(code=0)

    _log.info(
        "remove-projects: prefix=%s server=%s env=%s dry_run=%s",
        prefix,
        server,
        env,
        dry_run,
    )

    if server in (_SERVER_KITSU, _SERVER_BOTH):
        _remove_kitsu_projects(prefix, env, dry_run=dry_run, console=console)
    if server in (_SERVER_AYON, _SERVER_BOTH):
        _remove_ayon_projects(prefix, env, dry_run=dry_run, console=console)
