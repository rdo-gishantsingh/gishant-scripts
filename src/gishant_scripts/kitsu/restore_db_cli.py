"""Kitsu database restore CLI."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from gishant_scripts.common.db_restore import RestoreConfig, RestoreError, restore_database
from gishant_scripts.common.docker_utils import DockerComposeError, check_docker_compose

app = typer.Typer(
    help="Kitsu database restore utility",
    no_args_is_help=True,
)
console = Console()


@app.command()
def restore(
    backup_file: Path = typer.Argument(
        ...,
        help="Path to backup file (.dump, .backup, .gz, or .sql)",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
    ),
    compose_file: Path = typer.Option(
        None,
        "--compose-file",
        "-f",
        help="Path to docker-compose.yml (default: auto-detect from script location)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    db_service: str = typer.Option(
        "db",
        "--db-service",
        help="Database service name in docker-compose.yml",
    ),
    db_user: str = typer.Option(
        "zou",
        "--db-user",
        help="Database user name",
    ),
    db_name: str = typer.Option(
        "zoudb",
        "--db-name",
        help="Database name",
    ),
    skip_schema_upgrade: bool = typer.Option(
        False,
        "--skip-schema-upgrade",
        help="Skip database schema upgrade step",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Restore Kitsu database from a backup file.

    This command will:
    1. Stop Kitsu application and frontend services
    2. Recreate the database (all existing data will be lost)
    3. Restore from the backup file
    4. Upgrade database schema (unless --skip-schema-upgrade is used)
    5. Restart Kitsu services

    Supported backup formats:
    - Custom format: .dump, .backup (uses pg_restore)
    - Gzip format: .gz (uses zcat | psql)
    - Plain SQL: .sql (uses psql)

    Examples:
        # Restore from a backup file (will prompt for confirmation)
        restore-kitsu-db /path/to/backup.dump

        # Restore with auto-confirmation
        restore-kitsu-db /path/to/backup.dump --yes

        # Restore without schema upgrade
        restore-kitsu-db /path/to/backup.dump --skip-schema-upgrade

        # Restore with custom docker-compose.yml location
        restore-kitsu-db /path/to/backup.dump -f /path/to/docker-compose.yml
    """
    # Show header
    console.print(
        Panel(
            "[bold magenta]Kitsu Database Restore[/bold magenta]\n\n"
            f"Backup file: [green]{backup_file}[/green]\n"
            f"Database: [yellow]{db_name}[/yellow] (user: {db_user})\n"
            f"Service: [yellow]{db_service}[/yellow]\n"
            f"Schema upgrade: [{'yellow' if skip_schema_upgrade else 'green'}]"
            f"{'Disabled' if skip_schema_upgrade else 'Enabled'}[/{'yellow' if skip_schema_upgrade else 'green'}]",
            title="🎬 Configuration",
            border_style="magenta",
        )
    )

    # Check Docker
    try:
        check_docker_compose()
    except DockerComposeError as err:
        console.print(f"[red]✗ {err}[/red]")
        raise typer.Exit(code=1) from err

    # Auto-detect compose file if not provided
    if compose_file is None:
        # Look for docker-compose.yml in kitsu-server directory
        script_dir = Path(__file__).parent
        compose_file = script_dir / "kitsu-server" / "docker-compose.yml"

        if not compose_file.exists():
            console.print(
                "[red]✗ Could not find docker-compose.yml. Please specify path with --compose-file[/red]"
            )
            raise typer.Exit(code=1)

    # Confirm action
    if not yes:
        upgrade_info = (
            ""
            if skip_schema_upgrade
            else "  • Upgrade database schema\n"
        )
        console.print(
            Panel(
                "[bold yellow]WARNING: This will:[/bold yellow]\n\n"
                "  • Stop Kitsu application and frontend services\n"
                "  • Drop and recreate the database\n"
                f"  • Restore from: {backup_file.name}\n"
                f"{upgrade_info}"
                "  • Restart Kitsu services\n\n"
                "[bold red]All existing data in the database will be permanently lost![/bold red]",
                title="⚠️  Confirmation Required",
                border_style="red",
            )
        )
        response = typer.confirm("Do you want to continue?")
        if not response:
            console.print("[yellow]Restore cancelled.[/yellow]")
            raise typer.Exit(code=0)

    # Create restore configuration
    config = RestoreConfig(
        compose_file=compose_file,
        backup_file=backup_file,
        db_service=db_service,
        app_services=["zou", "kitsu"],
        db_user=db_user,
        db_name=db_name,
        run_schema_upgrade=not skip_schema_upgrade,
        schema_upgrade_service="zou" if not skip_schema_upgrade else None,
    )

    # Execute restore
    try:
        console.print()
        restore_database(config)
        console.print()
        console.print(
            Panel(
                "[bold green]✓ Database restore completed successfully![/bold green]\n\n"
                "Kitsu application and frontend services have been restarted.",
                title="✨ Success",
                border_style="green",
            )
        )
    except (RestoreError, DockerComposeError) as err:
        console.print()
        console.print(
            Panel(
                f"[bold red]✗ Restore failed:[/bold red]\n\n{err}",
                title="❌ Error",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from err


if __name__ == "__main__":
    app()
