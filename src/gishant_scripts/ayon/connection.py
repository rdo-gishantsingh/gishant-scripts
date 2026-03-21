"""AYON connection setup and configuration utilities.

Provides functions for establishing and validating connections to the AYON server,
including support for multiple environments (production, dev, UAT, local).
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console

from gishant_scripts._core.config import AppConfig

try:
    import ayon_api
except ImportError:
    ayon_api = None


class AYONConnectionError(Exception):
    """Raised when AYON connection fails."""


def setup_ayon_connection(
    console: Console,
    env_file: Path | None = None,
    use_local: bool = False,
    use_dev: bool = False,
    use_uat: bool = False,
) -> None:
    """Set up AYON connection using configuration from .env file or environment variables.

    Args:
        console: Rich console for displaying messages
        env_file: Optional path to .env file
        use_local: Use local environment variables (AYON_SERVER_URL_LOCAL, AYON_API_KEY_LOCAL)
        use_dev: Use dev environment variables (AYON_SERVER_URL_DEV, AYON_API_KEY_DEV)
        use_uat: Use UAT environment variables (AYON_SERVER_URL_UAT, AYON_API_KEY_UAT)

    Raises:
        AYONConnectionError: If connection setup fails

    """
    if ayon_api is None:
        raise AYONConnectionError("ayon-python-api not installed. Install it with: uv pip install ayon-python-api")

    # Determine environment
    if use_local:
        ayon_environment = "local"
    elif use_dev:
        ayon_environment = "dev"
    elif use_uat:
        ayon_environment = "uat"
    else:
        ayon_environment = "production"

    # Load configuration (loads .env file automatically)
    config = AppConfig(env_file=env_file, ayon_environment=ayon_environment)
    ayon_config = config.ayon

    # Validate AYON configuration
    errors = ayon_config.validate()
    if errors:
        error_messages = [f"{field}: {msg}" for field, msg in errors.items()]
        suffix = "_LOCAL" if use_local else "_DEV" if use_dev else "_UAT" if use_uat else ""
        raise AYONConnectionError(
            "AYON configuration missing:\n  - " + "\n  - ".join(error_messages) + "\n\n"
            f"Please set AYON_SERVER_URL{suffix} and AYON_API_KEY{suffix} in your .env file or environment."
        )

    try:
        env_label = f" ({ayon_environment})" if ayon_environment != "production" else ""
        console.print(f"[dim]Connecting to AYON{env_label}...[/dim]")

        # Set environment variables for ayon_api (validated above, so values are not None)
        assert ayon_config.server_url is not None
        assert ayon_config.api_key is not None
        os.environ["AYON_SERVER_URL"] = ayon_config.server_url
        os.environ["AYON_API_KEY"] = ayon_config.api_key

        if not ayon_api.is_connection_created():
            ayon_api.create_connection()

        console.print(f"[green]✓ Connected to AYON server{env_label}: {ayon_config.server_url}[/green]")
    except Exception as err:
        raise AYONConnectionError(f"Failed to connect to AYON server: {err}") from err
