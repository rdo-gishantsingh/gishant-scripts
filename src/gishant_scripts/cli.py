"""Command-line interface for gishant-scripts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from gishant_scripts._core.logging import setup_logging

app = typer.Typer(
    name="gishant",
    help=(
        "Gishant Scripts - Pipeline automation utilities.\n\n"
        "Sub-commands are organized by domain:\n\n"
        "Examples:\n"
        "    gishant youtrack fetch\n"
        "    gishant youtrack summary --weeks 4\n"
        "    gishant github fetch-prs --limit 50\n"
        "    gishant media convert input.mov -p web-video\n"
        "    gishant bookstack search 'query'\n"
        "    gishant task-workspace new PIPE-123"
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", exists=True, help="Path to .env configuration file"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose output (DEBUG level)"),
    ] = False,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", file_okay=False, help="Directory for output files (default: current directory)"),
    ] = None,
) -> None:
    """Global callback that sets up logging and shared state."""
    ctx.ensure_object(dict)

    log_level = logging.DEBUG if verbose else logging.INFO
    logger = setup_logging("gishant_scripts", level=log_level)
    ctx.obj["logger"] = logger

    if config:
        ctx.obj["config_file"] = config

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx.obj["output_dir"] = output_dir
    else:
        ctx.obj["output_dir"] = Path.cwd()

    logger.debug("Output directory: %s", ctx.obj["output_dir"])


# ============================================================================
# Sub-app Registration — each block silently skips if deps are missing
# ============================================================================

_logger = logging.getLogger(__name__)


def _register_subapp(name: str, import_fn: callable) -> None:
    """Try to register a sub-app, logging on failure instead of silently swallowing."""
    try:
        import_fn()
    except ImportError:
        _logger.debug("Sub-app %r not available (missing dependencies)", name)


def _reg_youtrack() -> None:
    from gishant_scripts.youtrack.cli import app as youtrack_app

    app.add_typer(youtrack_app, name="youtrack")


def _reg_github() -> None:
    from gishant_scripts.github.cli import app as github_app

    app.add_typer(github_app, name="github")


def _reg_media() -> None:
    from gishant_scripts.media.ffmpeg_convert import cli as media_app

    app.add_typer(media_app, name="media")


def _reg_ayon_kitsu() -> None:
    from gishant_scripts.ayon.cli import app as ayon_app
    from gishant_scripts.kitsu.cli import app as kitsu_app

    app.add_typer(ayon_app, name="ayon")
    app.add_typer(kitsu_app, name="kitsu")


def _reg_bookstack() -> None:
    from gishant_scripts.bookstack.cli import app as bookstack_app

    app.add_typer(bookstack_app, name="bookstack")


def _reg_task_workspace() -> None:
    from gishant_scripts.task_workspace import app as task_workspace_app

    app.add_typer(task_workspace_app, name="task-workspace")


def _reg_youtrack_summary() -> None:
    from gishant_scripts.youtrack.generate_work_summary import main as youtrack_summary_main

    app.command(name="youtrack-summary")(youtrack_summary_main)


_register_subapp("youtrack", _reg_youtrack)
_register_subapp("github", _reg_github)
_register_subapp("media", _reg_media)
_register_subapp("ayon+kitsu", _reg_ayon_kitsu)
_register_subapp("bookstack", _reg_bookstack)
_register_subapp("task-workspace", _reg_task_workspace)
_register_subapp("youtrack-summary", _reg_youtrack_summary)


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
