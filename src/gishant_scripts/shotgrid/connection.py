"""Shotgrid connection setup and configuration utilities.

Provides functions for establishing and validating connections to the Shotgrid server.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from gishant_scripts._core.config import AppConfig

try:
    import shotgun_api3
except ImportError:
    shotgun_api3 = None


class ShotgridConnectionError(Exception):
    """Raised when Shotgrid connection fails."""


def setup_shotgrid_connection(
    console: Console,
    env_file: Path | None = None,
):
    """Set up Shotgrid connection using configuration from .env file or environment variables.

    Args:
        console: Rich console for displaying messages.
        env_file: Optional path to .env file.

    Returns:
        An authenticated Shotgun instance.

    Raises:
        ShotgridConnectionError: If connection setup fails.

    """
    if shotgun_api3 is None:
        raise ShotgridConnectionError(
            "shotgun_api3 not installed. Install it with: uv pip install shotgun_api3"
        )

    config = AppConfig(env_file=env_file)
    sg_config = config.shotgrid

    errors = sg_config.validate()
    if errors:
        error_messages = [f"{field}: {msg}" for field, msg in errors.items()]
        raise ShotgridConnectionError(
            "Shotgrid configuration missing:\n  - " + "\n  - ".join(error_messages)
            + "\n\nPlease set SHOTGRID_SERVER_URL, SHOTGRID_SCRIPT, and SHOTGRID_API_KEY in your .env file."
        )

    try:
        console.print("[dim]Connecting to Shotgrid...[/dim]")
        assert sg_config.server_url is not None
        assert sg_config.script_name is not None
        assert sg_config.api_key is not None

        sg = shotgun_api3.Shotgun(
            sg_config.server_url,
            script_name=sg_config.script_name,
            api_key=sg_config.api_key,
        )
        console.print(f"[green]✓ Connected to Shotgrid: {sg_config.server_url}[/green]")
        return sg
    except Exception as err:
        raise ShotgridConnectionError(f"Failed to connect to Shotgrid: {err}") from err
