"""Unified database restore CLI for Ayon and Kitsu."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from gishant_scripts.common.docker_utils import (
    DockerComposeError,
    check_docker_compose,
    get_service_hostname_and_port,
    get_service_ip,
    is_local_ip,
    validate_database_is_local,
)
from gishant_scripts.common.unified_restore import unified_restore

app = typer.Typer(
    help="Unified database restore utility for Ayon and Kitsu",
    no_args_is_help=True,
)
console = Console()

# Default backup directories
DEFAULT_AYON_BACKUP_DIR = Path("/tech/backups/database/ayon/daily/")
DEFAULT_KITSU_BACKUP_DIR = Path("/tech/backups/database/kitsu/")


@app.command()
def restore(
    ayon_backup_dir: Path = typer.Option(
        DEFAULT_AYON_BACKUP_DIR,
        "--ayon-backup-dir",
        help="Directory to search for Ayon backups",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    kitsu_backup_dir: Path = typer.Option(
        DEFAULT_KITSU_BACKUP_DIR,
        "--kitsu-backup-dir",
        help="Directory to search for Kitsu backups (searched recursively)",
        exists=True,
        file_okay=False,
        dir_okay=True,
    ),
    only_ayon: bool = typer.Option(
        False,
        "--only-ayon",
        help="Restore only Ayon database",
    ),
    only_kitsu: bool = typer.Option(
        False,
        "--only-kitsu",
        help="Restore only Kitsu database",
    ),
    no_copy: bool = typer.Option(
        False,
        "--no-copy",
        help="Restore directly from backup files without copying to local first (not recommended)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
) -> None:
    """Restore Ayon and/or Kitsu databases from latest backups.

    This command will:
    1. Find the latest backup files in the specified directories
    2. Copy backups to local temporary directory (to keep originals safe)
    3. Stop application services for selected databases
    4. Restore databases in parallel
    5. Restart all services
    6. Clean up temporary files

    Examples:
        # Restore both from default locations (will prompt for confirmation)
        restore-databases restore

        # Restore only Ayon with auto-confirmation
        restore-databases restore --only-ayon --yes

        # Restore only Kitsu
        restore-databases restore --only-kitsu

        # Restore from custom backup directories
        restore-databases restore --ayon-backup-dir /path/to/ayon --kitsu-backup-dir /path/to/kitsu
    """
    # Validate options
    if only_ayon and only_kitsu:
        console.print("[red]✗ Cannot use --only-ayon and --only-kitsu together[/red]")
        raise typer.Exit(code=1)

    # Determine which databases to restore
    if only_ayon:
        restore_ayon = True
        restore_kitsu = False
    elif only_kitsu:
        restore_ayon = False
        restore_kitsu = True
    else:
        # Default: restore both
        restore_ayon = True
        restore_kitsu = True
    # Check Docker
    try:
        check_docker_compose()
    except DockerComposeError as err:
        console.print(f"[red]✗ {err}[/red]")
        raise typer.Exit(code=1) from err

    # Get compose file paths and server information
    ayon_compose_file: Path | None = None
    kitsu_compose_file: Path | None = None
    ayon_server_info: str = "Not configured"
    kitsu_server_info: str = "Not configured"

    if restore_ayon:
        script_dir = Path(__file__).parent.parent / "ayon"
        ayon_compose_file = script_dir / "ayon-server" / "docker-compose.yml"
        if ayon_compose_file.exists():
            # Validate database is local (not production/remote)
            db_is_local, db_message = validate_database_is_local(ayon_compose_file, "db")
            if not db_is_local:
                console.print(f"[red]✗ {db_message}[/red]")
                console.print("[red]This script only targets local databases. Aborting for safety.[/red]")
                raise typer.Exit(code=1)

            # Get server IP and port
            server_host, server_port = get_service_hostname_and_port(ayon_compose_file, "server")
            server_ip = get_service_ip(ayon_compose_file, "server")

            # Get database IP for display
            db_ip = get_service_ip(ayon_compose_file, "db")

            # Validate it's local if IP is found
            if server_ip and not is_local_ip(server_ip):
                console.print(
                    f"[red]✗ Ayon server IP ({server_ip}) is not local! This script only targets local servers.[/red]"
                )
                raise typer.Exit(code=1)

            # Build server info string
            if server_host and server_port:
                ayon_server_info = f"{server_host}:{server_port}"
                if server_ip:
                    ayon_server_info += f" (IP: {server_ip})"
            elif server_port:
                ayon_server_info = f"localhost:{server_port}"
                if server_ip:
                    ayon_server_info += f" (IP: {server_ip})"
            elif server_ip:
                ayon_server_info = f"IP: {server_ip}"
            else:
                # Service might not be running, but we can still show the compose file location
                ayon_server_info = "localhost (service may not be running)"

            # Add database info
            if db_ip:
                ayon_server_info += f" | Database: local (IP: {db_ip})"
            else:
                ayon_server_info += " | Database: local"

    if restore_kitsu:
        script_dir = Path(__file__).parent.parent / "kitsu"
        kitsu_compose_file = script_dir / "kitsu-server" / "docker-compose.yml"
        if kitsu_compose_file.exists():
            # Validate database is local (not production/remote)
            db_is_local, db_message = validate_database_is_local(kitsu_compose_file, "db")
            if not db_is_local:
                console.print(f"[red]✗ {db_message}[/red]")
                console.print("[red]This script only targets local databases. Aborting for safety.[/red]")
                raise typer.Exit(code=1)

            # Get zou service IP and port (zou is the backend service)
            zou_host, zou_port = get_service_hostname_and_port(kitsu_compose_file, "zou")
            zou_ip = get_service_ip(kitsu_compose_file, "zou")

            # Get database IP for display
            db_ip = get_service_ip(kitsu_compose_file, "db")

            # Validate it's local if IP is found
            if zou_ip and not is_local_ip(zou_ip):
                console.print(
                    f"[red]✗ Kitsu server IP ({zou_ip}) is not local! This script only targets local servers.[/red]"
                )
                raise typer.Exit(code=1)

            # Build server info string
            if zou_host and zou_port:
                kitsu_server_info = f"{zou_host}:{zou_port}"
                if zou_ip:
                    kitsu_server_info += f" (IP: {zou_ip})"
            elif zou_port:
                kitsu_server_info = f"localhost:{zou_port}"
                if zou_ip:
                    kitsu_server_info += f" (IP: {zou_ip})"
            elif zou_ip:
                kitsu_server_info = f"IP: {zou_ip}"
            else:
                # Service might not be running, but we can still show the compose file location
                kitsu_server_info = "localhost (service may not be running)"

            # Add database info
            if db_ip:
                kitsu_server_info += f" | Database: local (IP: {db_ip})"
            else:
                kitsu_server_info += " | Database: local"

    # Build configuration message
    databases_to_restore = []
    if restore_ayon:
        databases_to_restore.append("Ayon")
    if restore_kitsu:
        databases_to_restore.append("Kitsu")

    config_msg = "[bold cyan]Unified Database Restore[/bold cyan]\n\n"
    if restore_ayon:
        config_msg += f"Ayon backup directory: [green]{ayon_backup_dir}[/green]\n"
        config_msg += f"Ayon server: [yellow]{ayon_server_info}[/yellow]\n"
    if restore_kitsu:
        config_msg += f"Kitsu backup directory: [green]{kitsu_backup_dir}[/green]\n"
        config_msg += f"Kitsu server: [yellow]{kitsu_server_info}[/yellow]\n"
    config_msg += f"\nDatabases to restore: [yellow]{', '.join(databases_to_restore)}[/yellow]"
    if not no_copy:
        config_msg += "\n[cyan]Backups will be copied to local temp directory first[/cyan]"

    # Show header
    console.print(
        Panel(
            config_msg,
            title="⚙️  Configuration",
            border_style="cyan",
        )
    )

    # Confirm action
    if not yes:
        warning_items = []
        if restore_ayon:
            warning_items.append(f"  • Target Ayon server: [yellow]{ayon_server_info}[/yellow]")
            warning_items.append("  • Stop AYON server and worker services")
            warning_items.append("  • Drop and recreate Ayon database")
        if restore_kitsu:
            warning_items.append(f"  • Target Kitsu server: [yellow]{kitsu_server_info}[/yellow]")
            warning_items.append("  • Stop Kitsu application and frontend services")
            warning_items.append("  • Drop and recreate Kitsu database")
        warning_items.append("  • Restore from latest backup files")
        if not no_copy:
            warning_items.append("  • Copy backups to local temp directory (originals will be preserved)")
        warning_items.append("  • Restart all services")

        warning_text = "[bold yellow]WARNING: This will:[/bold yellow]\n\n"
        warning_text += "\n".join(warning_items)
        warning_text += "\n\n[bold red]All existing data in the selected databases will be permanently lost![/bold red]"

        console.print(
            Panel(
                warning_text,
                title="⚠️  Confirmation Required",
                border_style="red",
            )
        )
        response = typer.confirm("Do you want to continue?")
        if not response:
            console.print("[yellow]Restore cancelled.[/yellow]")
            raise typer.Exit(code=0)

    # Execute unified restore
    try:
        console.print()
        ayon_result, kitsu_result = unified_restore(
            ayon_backup_dir=ayon_backup_dir,
            kitsu_backup_dir=kitsu_backup_dir,
            restore_ayon=restore_ayon,
            restore_kitsu=restore_kitsu,
            copy_to_local=not no_copy,
        )

        # Display results
        console.print()
        results_parts = []

        if restore_ayon:
            if ayon_result.backup_file:
                if ayon_result.success:
                    results_parts.append(f"[green]✓ Ayon:[/green] Restored from {ayon_result.backup_file.name}")
                else:
                    results_parts.append(f"[red]✗ Ayon:[/red] Failed - {ayon_result.error}")
            else:
                results_parts.append("[yellow]⚠ Ayon:[/yellow] No backup found, skipped")

        if restore_kitsu:
            if kitsu_result.backup_file:
                if kitsu_result.success:
                    results_parts.append(f"[green]✓ Kitsu:[/green] Restored from {kitsu_result.backup_file.name}")
                else:
                    results_parts.append(f"[red]✗ Kitsu:[/red] Failed - {kitsu_result.error}")
            else:
                results_parts.append("[yellow]⚠ Kitsu:[/yellow] No backup found, skipped")

        # Determine overall success
        ayon_ok = not restore_ayon or (ayon_result.success or ayon_result.backup_file is None)
        kitsu_ok = not restore_kitsu or (kitsu_result.success or kitsu_result.backup_file is None)
        all_success = ayon_ok and kitsu_ok

        if all_success:
            console.print(
                Panel(
                    "[bold green]✓ Database restore completed successfully![/bold green]\n\n" + "\n".join(results_parts),
                    title="✨ Success",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel(
                    "[bold red]✗ Some restores failed:[/bold red]\n\n" + "\n".join(results_parts),
                    title="❌ Error",
                    border_style="red",
                )
            )
            raise typer.Exit(code=1)

    except (DockerComposeError, Exception) as err:
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
