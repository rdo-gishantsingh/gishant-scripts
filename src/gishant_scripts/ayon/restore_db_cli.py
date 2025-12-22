"""AYON database restore CLI."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from gishant_scripts.common.db_restore import RestoreConfig, RestoreError, restore_database
from gishant_scripts.common.docker_utils import DockerComposeError, check_docker_compose

app = typer.Typer(
    help="AYON database restore utility",
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
        "ayon",
        "--db-user",
        help="Database user name",
    ),
    db_name: str = typer.Option(
        "ayon",
        "--db-name",
        help="Database name",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
    skip_thumbnails: bool = typer.Option(
        False,
        "--skip-thumbnails",
        help="Skip thumbnail data during restore (significantly reduces restore time)",
    ),
) -> None:
    """Restore AYON database from a backup file.

    This command will:
    1. Stop AYON server and worker services
    2. Recreate the database (all existing data will be lost)
    3. Restore from the backup file
    4. Restart AYON services

    Supported backup formats:
    - Custom format: .dump, .backup (uses pg_restore)
    - Gzip format: .gz (uses zcat | psql)
    - Plain SQL: .sql (uses psql)

    Examples:
        # Restore from a backup file (will prompt for confirmation)
        restore-ayon-db /path/to/backup.dump

        # Restore with auto-confirmation
        restore-ayon-db /path/to/backup.dump --yes

        # Restore with custom docker-compose.yml location
        restore-ayon-db /path/to/backup.dump -f /path/to/docker-compose.yml
    """
    # Show header
    skip_info = "[red](skipping thumbnails)[/red]" if skip_thumbnails else ""
    console.print(
        Panel(
            f"[bold cyan]AYON Database Restore[/bold cyan] {skip_info}\n\n"
            f"Backup file: [green]{backup_file}[/green]\n"
            f"Database: [yellow]{db_name}[/yellow] (user: {db_user})\n"
            f"Service: [yellow]{db_service}[/yellow]",
            title="⚙️  Configuration",
            border_style="cyan",
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
        # Look for docker-compose.yml in ayon-server directory
        script_dir = Path(__file__).parent
        compose_file = script_dir / "ayon-server" / "docker-compose.yml"

        if not compose_file.exists():
            console.print(
                "[red]✗ Could not find docker-compose.yml. Please specify path with --compose-file[/red]"
            )
            raise typer.Exit(code=1)

    # Confirm action
    if not yes:
        warning_items = [
            "  • Stop AYON server and worker services",
            "  • Drop and recreate the database",
            f"  • Restore from: {backup_file.name}",
        ]
        if skip_thumbnails:
            warning_items.append("  • [yellow]Skip thumbnail data[/yellow] (faster restore)")
        warning_items.append("  • Restart AYON services")

        console.print(
            Panel(
                "[bold yellow]WARNING: This will:[/bold yellow]\n\n"
                + "\n".join(warning_items)
                + "\n\n[bold red]All existing data in the database will be permanently lost![/bold red]",
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
        app_services=["server", "worker"],
        db_user=db_user,
        db_name=db_name,
        run_schema_upgrade=False,  # AYON doesn't have schema upgrade step
        schema_upgrade_service=None,
        skip_thumbnails=skip_thumbnails,
    )

    # Execute restore
    try:
        console.print()
        restore_database(config)
        console.print()
        console.print(
            Panel(
                "[bold green]✓ Database restore completed successfully![/bold green]\n\n"
                "AYON server and worker services have been restarted.",
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
