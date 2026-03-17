"""Command-line interface for gishant-scripts."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from gishant_scripts.common.logging import setup_logging

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
# Sub-app Registration
# ============================================================================

try:
    from gishant_scripts.youtrack.cli import app as youtrack_app

    app.add_typer(youtrack_app, name="youtrack")
except ImportError:
    pass

try:
    from gishant_scripts.github.cli import app as github_app

    app.add_typer(github_app, name="github")
except ImportError:
    pass

try:
    from gishant_scripts.media.ffmpeg_convert import cli as media_app

    app.add_typer(media_app, name="media")
except ImportError:
    pass

try:
    from gishant_scripts.ayon.cli import app as ayon_app
    from gishant_scripts.kitsu.cli import app as kitsu_app

    app.add_typer(ayon_app, name="ayon")
    app.add_typer(kitsu_app, name="kitsu")
except ImportError:
    pass

try:
    from gishant_scripts.bookstack.cli import app as bookstack_app

    app.add_typer(bookstack_app, name="bookstack")
except ImportError:
    pass

try:
    from gishant_scripts.task_workspace import app as task_workspace_app

    app.add_typer(task_workspace_app, name="task-workspace")
except ImportError:
    pass


def main() -> None:
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
