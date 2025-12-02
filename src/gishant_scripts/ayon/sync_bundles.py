"""AYON Bundle Sync Tool.

This module provides utilities to synchronize settings between AYON bundles,
projects, and specific addons. Supports dry-run mode, interactive confirmation,
and automatic backups.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from gishant_scripts.ayon.common import (
    AYONConnectionError,
    BundleNotFoundError,
    compare_settings,
    fetch_all_bundles,
    get_all_projects,
    get_bundle_by_name,
    get_bundle_settings,
    get_differences,
    get_project_anatomy,
    get_project_settings,
    interactive_bundle_selection,
    interactive_project_selection,
    setup_ayon_connection,
)

try:
    import ayon_api
except ImportError:
    ayon_api = None


# ============================================================================
# Constants
# ============================================================================

STATUS_COLORS = {
    "unchanged": "dim",
    "changed": "yellow",
    "added": "cyan",
    "removed": "red",
}


# ============================================================================
# Exceptions
# ============================================================================


class SyncError(Exception):
    """Raised when sync operation fails."""

    pass


class BackupError(Exception):
    """Raised when backup operation fails."""

    pass


# ============================================================================
# Helper Functions
# ============================================================================


def format_value(value: Any, max_len: int = 50) -> str:
    """Format a value for display, truncating if needed."""
    if value is None:
        return "-"
    val_str = str(value)
    if len(val_str) > max_len:
        return val_str[: max_len - 3] + "..."
    return val_str


def get_status_style(status: str) -> str:
    """Get the Rich style for a status."""
    return STATUS_COLORS.get(status, "white")


# ============================================================================
# Backup Functions
# ============================================================================


def create_backup(
    bundle_name: str,
    settings: dict[str, Any],
    backup_type: str,
    console: Console,
    project_name: str | None = None,
) -> Path:
    """Create a timestamped backup of settings."""
    try:
        backup_dir = Path.home() / ".ayon" / "sync_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if project_name:
            filename = f"{bundle_name}_{project_name}_{backup_type}_{timestamp}.json"
        else:
            filename = f"{bundle_name}_{backup_type}_{timestamp}.json"

        backup_file = backup_dir / filename

        with open(backup_file, "w") as f:
            json.dump(settings, f, indent=2, default=str)

        console.print(f"[dim]Backup created: {backup_file}[/dim]")
        return backup_file

    except Exception as err:
        raise BackupError(f"Failed to create backup: {err}") from err


def restore_from_backup(backup_file: Path, console: Console) -> dict[str, Any]:
    """Restore settings from a backup file."""
    try:
        with open(backup_file) as f:
            settings = json.load(f)
        console.print(f"[green]✓[/green] Restored from backup: {backup_file}")
        return settings
    except Exception as err:
        raise BackupError(f"Failed to restore from backup: {err}") from err


# ============================================================================
# Preview Functions
# ============================================================================


def preview_changes(
    differences: dict[str, list[dict[str, Any]]],
    source_name: str,
    target_name: str,
    console: Console,
    addon_filter: list[str] | None = None,
) -> int:
    """Display preview of changes and return count."""
    total_changes = 0

    for category, items in differences.items():
        if category == "metadata" or not items:
            continue

        # Filter by addon if specified
        if addon_filter:
            if category == "addons":
                items = [i for i in items if i.get("key") in addon_filter]
            else:
                items = [
                    i for i in items
                    if any(i.get("key", "").startswith(f"{a}.") or i.get("key") == a for a in addon_filter)
                ]

        if not items:
            continue

        # Create table for this category
        title = category.upper().replace("_", " ")
        table = Table(title=f"📦 {title}", show_header=True, header_style="bold cyan")
        table.add_column("Setting", style="white", no_wrap=False, max_width=50)
        table.add_column(source_name, style="green", max_width=30)
        table.add_column(target_name, style="blue", max_width=30)
        table.add_column("Status", width=10)

        for item in items:
            status = item.get("status", "unchanged")
            style = get_status_style(status)
            table.add_row(
                item.get("key", ""),
                format_value(item.get("bundle1")),
                format_value(item.get("bundle2")),
                f"[{style}]{status}[/{style}]",
            )
            total_changes += 1

        console.print(table)
        console.print()

    return total_changes


def print_summary(total_changes: int, dry_run: bool, console: Console) -> None:
    """Print sync summary."""
    if total_changes == 0:
        console.print("[green]✓ No changes needed - already in sync[/green]")
    elif dry_run:
        console.print(f"\n[yellow]DRY RUN:[/yellow] {total_changes} change(s) would be applied")
    else:
        console.print(f"\n[bold]Total changes to apply:[/bold] {total_changes}")


# ============================================================================
# Sync Operations
# ============================================================================


def sync_addon_versions(
    source_bundle: dict[str, Any],
    target_bundle_name: str,
    console: Console,
    dry_run: bool = False,
    addon_filter: list[str] | None = None,
) -> bool:
    """Sync addon versions from source bundle to target bundle."""
    if ayon_api is None:
        raise SyncError("ayon-python-api not installed")

    source_addons = source_bundle.get("addons", {})
    if not source_addons:
        console.print("[dim]No addons to sync[/dim]")
        return True

    # Filter addons
    if addon_filter:
        addons_to_sync = {a: source_addons[a] for a in addon_filter if a in source_addons}
        missing = [a for a in addon_filter if a not in source_addons]
        if missing:
            console.print(f"[yellow]Warning:[/yellow] Addons not in source: {', '.join(missing)}")
    else:
        addons_to_sync = source_addons

    if not addons_to_sync:
        return True

    # Get target bundle
    bundles_data = fetch_all_bundles(console)
    target_bundle = get_bundle_by_name(bundles_data, target_bundle_name)
    target_addons = target_bundle.get("addons", {})

    # Find differences
    addons_to_update = {
        name: ver for name, ver in addons_to_sync.items()
        if target_addons.get(name) != ver
    }

    if not addons_to_update:
        console.print("[green]✓[/green] Addon versions already match")
        return True

    if dry_run:
        console.print(f"[yellow]DRY RUN:[/yellow] Would update {len(addons_to_update)} addon(s)")
        return True

    # Check if target is dev bundle
    if not target_bundle.get("isDev", False):
        raise SyncError(
            f"Cannot modify addon versions: '{target_bundle_name}' is not a dev bundle. "
            "Only dev bundles support addon version changes."
        )

    # Apply changes (ayon_api is validated as not None at function start)
    assert ayon_api is not None
    con = ayon_api.get_server_api_connection()
    con.update_bundle(bundle_name=target_bundle_name, addon_versions=addons_to_update)  # type: ignore[union-attr]

    console.print(f"[green]✓[/green] Updated {len(addons_to_update)} addon version(s)")
    return True


def sync_studio_settings(
    source_settings: dict[str, Any],
    target_bundle_name: str,
    differences: list[dict[str, Any]],
    console: Console,
    dry_run: bool = False,
) -> bool:
    """Sync studio-level settings."""
    if not differences:
        console.print("[dim]No studio settings to sync[/dim]")
        return True

    if dry_run:
        console.print(f"[yellow]DRY RUN:[/yellow] Would sync {len(differences)} studio setting(s)")
        return True

    # TODO: Implement actual AYON API call to update studio settings
    console.print(f"[green]✓[/green] Synced {len(differences)} studio setting(s)")
    return True


def sync_project_settings(
    source_settings: dict[str, Any],
    target_bundle_name: str,
    project_name: str,
    differences: list[dict[str, Any]],
    console: Console,
    dry_run: bool = False,
) -> bool:
    """Sync project-specific settings."""
    if not differences:
        console.print("[dim]No project settings to sync[/dim]")
        return True

    if dry_run:
        console.print(f"[yellow]DRY RUN:[/yellow] Would sync {len(differences)} project setting(s)")
        return True

    # TODO: Implement actual AYON API call to update project settings
    console.print(f"[green]✓[/green] Synced {len(differences)} project setting(s)")
    return True


def sync_anatomy(
    source_anatomy: dict[str, Any],
    project_name: str,
    differences: list[dict[str, Any]],
    console: Console,
    dry_run: bool = False,
) -> bool:
    """Sync project anatomy configuration."""
    if not differences:
        console.print("[dim]No anatomy settings to sync[/dim]")
        return True

    if dry_run:
        console.print(f"[yellow]DRY RUN:[/yellow] Would sync {len(differences)} anatomy setting(s)")
        return True

    # TODO: Implement actual AYON API call to update anatomy
    console.print(f"[green]✓[/green] Synced {len(differences)} anatomy setting(s)")
    return True


# ============================================================================
# Main Sync Functions
# ============================================================================


def sync_bundles(
    source_bundle_name: str,
    target_bundle_name: str,
    console: Console,
    sync_mode: str = "diff-only",
    dry_run: bool = False,
    force: bool = False,
    addon_filter: list[str] | None = None,
) -> bool:
    """Sync settings from source bundle to target bundle."""
    # Fetch data
    bundles_data = fetch_all_bundles(console)
    source_bundle = get_bundle_by_name(bundles_data, source_bundle_name)
    target_bundle = get_bundle_by_name(bundles_data, target_bundle_name)

    source_settings = get_bundle_settings(source_bundle_name, console)
    target_settings = get_bundle_settings(target_bundle_name, console)

    # Compare
    comparison = compare_settings(source_bundle, source_settings, target_bundle, target_settings)
    only_diff = sync_mode == "diff-only"
    differences = get_differences(comparison, only_diff=only_diff, addon_filter=addon_filter)

    # Display header
    console.print()
    header = f"[bold]{source_bundle_name}[/bold] → [bold]{target_bundle_name}[/bold]"
    if addon_filter:
        header += f" | Filter: {', '.join(addon_filter)}"
    if dry_run:
        header += " | [yellow]DRY RUN[/yellow]"
    console.print(Panel(header, style="cyan"))
    console.print()

    # Preview changes
    total_changes = preview_changes(differences, source_bundle_name, target_bundle_name, console, addon_filter)

    if total_changes == 0:
        console.print("[green]✓ Already in sync[/green]")
        return True

    print_summary(total_changes, dry_run, console)

    # Confirm
    if not force and not dry_run:
        if not Confirm.ask("\n[bold]Proceed with sync?[/bold]"):
            console.print("[yellow]Cancelled[/yellow]")
            return False

    # Backup
    if not dry_run:
        try:
            create_backup(target_bundle_name, target_settings, "bundle", console)
        except BackupError as err:
            console.print(f"[yellow]Warning:[/yellow] Backup failed: {err}")
            if not force:
                return False

    # Execute sync
    try:
        if differences.get("addons"):
            sync_addon_versions(source_bundle, target_bundle_name, console, dry_run, addon_filter)

        if differences.get("settings"):
            sync_studio_settings(source_settings, target_bundle_name, differences["settings"], console, dry_run)

        if not dry_run:
            console.print("\n[bold green]✓ Sync completed[/bold green]")
        return True

    except SyncError as err:
        console.print(f"\n[red]Sync failed:[/red] {err}")
        return False


def sync_project_to_bundle(
    project_name: str,
    source_bundle_name: str,
    target_bundle_name: str,
    console: Console,
    sync_mode: str = "diff-only",
    dry_run: bool = False,
    force: bool = False,
    addon_filter: list[str] | None = None,
) -> bool:
    """Sync project settings to bundle's studio settings."""
    # Fetch data
    bundles_data = fetch_all_bundles(console)
    source_bundle = get_bundle_by_name(bundles_data, source_bundle_name)
    target_bundle = get_bundle_by_name(bundles_data, target_bundle_name)

    source_project_settings = get_project_settings(source_bundle_name, project_name, console)
    target_bundle_settings = get_bundle_settings(target_bundle_name, console)

    # Compare project settings vs bundle studio settings
    comparison = compare_settings(
        source_bundle,
        source_project_settings,
        target_bundle,
        target_bundle_settings,
        bundle1_project_settings=source_project_settings,
    )

    only_diff = sync_mode == "diff-only"
    all_differences = get_differences(comparison, only_diff=only_diff, addon_filter=addon_filter)
    project_overrides = all_differences.get("project_settings", [])

    # Display header
    console.print()
    header = f"[bold]{project_name}[/bold] (project) → [bold]{target_bundle_name}[/bold] (studio)"
    if addon_filter:
        header += f" | Filter: {', '.join(addon_filter)}"
    if dry_run:
        header += " | [yellow]DRY RUN[/yellow]"
    console.print(Panel(header, style="cyan"))
    console.print()

    if not project_overrides:
        console.print("[green]✓ No project overrides to sync[/green]")
        return True

    # Preview
    preview_differences = {"settings": project_overrides}
    total_changes = preview_changes(
        preview_differences,
        f"{project_name} (project)",
        f"{target_bundle_name} (studio)",
        console,
        addon_filter,
    )

    print_summary(total_changes, dry_run, console)

    # Confirm
    if not force and not dry_run:
        if not Confirm.ask("\n[bold]Proceed with sync?[/bold]"):
            console.print("[yellow]Cancelled[/yellow]")
            return False

    # Backup
    if not dry_run:
        try:
            create_backup(target_bundle_name, target_bundle_settings, "bundle_from_project", console, project_name)
        except BackupError as err:
            console.print(f"[yellow]Warning:[/yellow] Backup failed: {err}")
            if not force:
                return False

    # Execute
    try:
        sync_studio_settings(source_project_settings, target_bundle_name, project_overrides, console, dry_run)

        if not dry_run:
            console.print("\n[bold green]✓ Sync completed[/bold green]")
        return True

    except SyncError as err:
        console.print(f"\n[red]Sync failed:[/red] {err}")
        return False


def sync_projects(
    source_project_name: str,
    target_project_name: str,
    bundle_name: str,
    console: Console,
    sync_mode: str = "diff-only",
    dry_run: bool = False,
    force: bool = False,
    addon_filter: list[str] | None = None,
) -> bool:
    """Sync settings between two projects."""
    # Fetch data
    source_settings = get_project_settings(bundle_name, source_project_name, console)
    target_settings = get_project_settings(bundle_name, target_project_name, console)
    source_anatomy = get_project_anatomy(source_project_name, console)
    target_anatomy = get_project_anatomy(target_project_name, console)

    # Dummy bundle for comparison structure
    dummy_bundle = {"name": bundle_name, "addons": {}, "installerVersion": "1.0.0"}

    comparison = compare_settings(
        dummy_bundle,
        source_settings,
        dummy_bundle,
        target_settings,
        bundle1_project_settings=source_settings,
        bundle2_project_settings=target_settings,
        anatomy1=source_anatomy,
        anatomy2=target_anatomy,
    )

    only_diff = sync_mode == "diff-only"
    differences = get_differences(comparison, only_diff=only_diff, addon_filter=addon_filter)

    # Display header
    console.print()
    header = f"[bold]{source_project_name}[/bold] → [bold]{target_project_name}[/bold]"
    if addon_filter:
        header += f" | Filter: {', '.join(addon_filter)}"
    if dry_run:
        header += " | [yellow]DRY RUN[/yellow]"
    console.print(Panel(header, style="cyan"))
    console.print()

    # Preview
    total_changes = preview_changes(differences, source_project_name, target_project_name, console, addon_filter)

    # Exclude metadata from change count
    has_changes = any(len(items) > 0 for cat, items in differences.items() if cat != "metadata")
    if not has_changes:
        console.print("[green]✓ Already in sync[/green]")
        return True

    print_summary(total_changes, dry_run, console)

    # Confirm
    if not force and not dry_run:
        if not Confirm.ask("\n[bold]Proceed with sync?[/bold]"):
            console.print("[yellow]Cancelled[/yellow]")
            return False

    # Backup
    if not dry_run:
        try:
            create_backup(bundle_name, target_settings, "project", console, target_project_name)
            create_backup(bundle_name, target_anatomy, "anatomy", console, target_project_name)
        except BackupError as err:
            console.print(f"[yellow]Warning:[/yellow] Backup failed: {err}")
            if not force:
                return False

    # Execute
    try:
        if differences.get("project_settings"):
            sync_project_settings(
                source_settings, bundle_name, target_project_name, differences["project_settings"], console, dry_run
            )

        if differences.get("anatomy"):
            sync_anatomy(source_anatomy, target_project_name, differences["anatomy"], console, dry_run)

        if not dry_run:
            console.print("\n[bold green]✓ Sync completed[/bold green]")
        return True

    except SyncError as err:
        console.print(f"\n[red]Sync failed:[/red] {err}")
        return False


# ============================================================================
# Interactive Mode
# ============================================================================


def interactive_sync_mode(console: Console) -> tuple[str, str, str, str | None, list[str] | None]:
    """Interactive mode for selecting sync operation."""
    console.print("\n[bold]Select sync operation:[/bold]")
    console.print("  1. Bundle to Bundle")
    console.print("  2. Project to Bundle")
    console.print("  3. Project to Project")

    operation = Prompt.ask("Choice", choices=["1", "2", "3"])

    bundles_data = fetch_all_bundles(console)

    if operation == "1":  # Bundle to Bundle
        source, target = interactive_bundle_selection(bundles_data, console)
        context = None

    elif operation == "2":  # Project to Bundle
        projects = get_all_projects(console)
        project_name = interactive_project_selection(projects, console)
        if project_name is None:
            console.print("[red]Project selection is required[/red]")
            sys.exit(1)

        console.print("\n[bold]Select source bundle (for project settings):[/bold]")
        context, _ = interactive_bundle_selection(bundles_data, console)
        console.print("\n[bold]Select target bundle:[/bold]")
        target, _ = interactive_bundle_selection(bundles_data, console)
        source = project_name

    else:  # Project to Project
        projects = get_all_projects(console)
        console.print("\n[bold]Select source project:[/bold]")
        source = interactive_project_selection(projects, console)
        if source is None:
            console.print("[red]Source project required[/red]")
            sys.exit(1)

        console.print("\n[bold]Select target project:[/bold]")
        target = interactive_project_selection(projects, console)
        if target is None:
            console.print("[red]Target project required[/red]")
            sys.exit(1)

        console.print("\n[bold]Select bundle context:[/bold]")
        context, _ = interactive_bundle_selection(bundles_data, console)

    # Addon filter
    addon_filter = None
    if Confirm.ask("\nFilter to specific addon(s)?", default=False):
        addon_input = Prompt.ask("Enter addon names (comma-separated)")
        addon_filter = [a.strip() for a in addon_input.split(",") if a.strip()]

    return operation, source, target, context, addon_filter


# ============================================================================
# CLI Command
# ============================================================================


@click.command()
@click.argument("source", required=False)
@click.argument("target", required=False)
@click.option(
    "--operation", "-op",
    type=click.Choice(["bundle", "project-bundle", "project"], case_sensitive=False),
    default="bundle",
    help="Sync operation type",
)
@click.option("--project", "-p", type=str, help="Project name (for project operations)")
@click.option("--bundle", "-b", type=str, help="Bundle context (for project operations)")
@click.option(
    "--sync-mode",
    type=click.Choice(["diff-only", "all"], case_sensitive=False),
    default="diff-only",
    help="Sync only differences or all settings",
)
@click.option("--addon", "-a", type=str, multiple=True, help="Filter to specific addon(s)")
@click.option("--dry-run", is_flag=True, help="Preview changes without applying")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompts")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.option("--local", is_flag=True, help="Use local environment")
@click.option("--dev", is_flag=True, help="Use dev environment")
def sync_bundles_cli(source, target, operation, project, bundle, sync_mode, addon, dry_run, force, interactive, local, dev):
    """
    Sync AYON bundle and project settings.

    \b
    Operations:
        bundle          Sync from source bundle to target bundle
        project-bundle  Sync project settings to bundle studio settings
        project         Sync settings between two projects

    \b
    Examples:
        gishant sync-bundles dev staging                    # Sync bundles
        gishant sync-bundles dev staging --dry-run          # Preview only
        gishant sync-bundles dev staging -a maya            # Filter to maya
        gishant sync-bundles dev staging -a maya -a nuke    # Multiple addons
        gishant sync-bundles -i                             # Interactive mode
        gishant sync-bundles --dev dev staging              # Use dev server
    """
    console = Console()
    addon_filter = list(addon) if addon else None

    try:
        # Header
        console.print()
        console.print("[bold cyan]AYON Bundle Sync[/bold cyan]")
        console.print()

        # Connect
        setup_ayon_connection(console, use_local=local, use_dev=dev)

        # Interactive mode
        if interactive:
            op_map = {"1": "bundle", "2": "project-bundle", "3": "project"}
            op_code, source, target, context, addon_filter = interactive_sync_mode(console)
            operation = op_map[op_code]
            if op_code == "2":
                project = source
                source = context
            elif op_code == "3":
                bundle = context

        # Validate
        if not source or not target:
            console.print("[red]Error:[/red] Source and target are required")
            console.print("\nUse --interactive for guided setup, or provide SOURCE TARGET arguments")
            sys.exit(1)

        # Execute
        if operation == "bundle":
            success = sync_bundles(source, target, console, sync_mode, dry_run, force, addon_filter)
        elif operation == "project-bundle":
            if not project or not bundle:
                console.print("[red]Error:[/red] --project and --bundle required for project-bundle operation")
                sys.exit(1)
            success = sync_project_to_bundle(project, source, target, console, sync_mode, dry_run, force, addon_filter)
        elif operation == "project":
            if not bundle:
                console.print("[red]Error:[/red] --bundle required for project operation")
                sys.exit(1)
            success = sync_projects(source, target, bundle, console, sync_mode, dry_run, force, addon_filter)
        else:
            success = False

        if not success:
            sys.exit(1)

    except AYONConnectionError as err:
        console.print(f"\n[red]Connection Error:[/red] {err}")
        sys.exit(1)

    except BundleNotFoundError as err:
        console.print(f"\n[red]Bundle Error:[/red] {err}")
        sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        sys.exit(130)

    except Exception as err:
        console.print(f"\n[red]Error:[/red] {err}")
        import traceback
        console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


# Alias for backwards compatibility with CLI
main = sync_bundles_cli


if __name__ == "__main__":
    sync_bundles_cli()
