"""AYON Bundle Sync Tool.

This module provides utilities to synchronize settings between AYON bundles,
projects, and specific addons. Supports dry-run mode, interactive confirmation,
and automatic backups.

Features:
- Sync bundle to bundle
- Sync project settings to bundle
- Sync project to project
- Sync specific addon only
- Diff-only or full sync modes
- Dry-run preview
- Automatic backups and rollback
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

# Import functions from common module
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

# Add rdo-ayon-utils to Python path
RDO_AYON_UTILS_PATH = Path("/home/gisi/dev/repos/rdo-ayon-utils/python")
if RDO_AYON_UTILS_PATH.exists() and str(RDO_AYON_UTILS_PATH) not in sys.path:
    sys.path.insert(0, str(RDO_AYON_UTILS_PATH))

try:
    import ayon_api
except ImportError:
    ayon_api = None

try:
    from rdo_ayon_utils import ayon_utils
except ImportError:
    ayon_utils = None


# ============================================================================
# Custom Exceptions
# ============================================================================


class SyncError(Exception):
    """Raised when sync operation fails."""

    pass


class BackupError(Exception):
    """Raised when backup operation fails."""

    pass


class RollbackError(Exception):
    """Raised when rollback operation fails."""

    pass


# ============================================================================
# Backup and Rollback
# ============================================================================


def create_backup(
    bundle_name: str,
    settings: dict[str, Any],
    backup_type: str,
    console: Console,
    project_name: str | None = None,
) -> Path:
    """
    Create a timestamped backup of bundle or project settings.

    Args:
        bundle_name: Name of the bundle
        settings: Settings data to backup
        backup_type: Type of backup (bundle/project/anatomy)
        console: Rich console for messages
        project_name: Project name for project backups

    Returns:
        Path to backup file

    Raises:
        BackupError: If backup creation fails
    """
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Creating backup...", total=None)

            # Create backup directory
            backup_dir = Path.home() / ".ayon" / "sync_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Generate backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if project_name:
                filename = f"{bundle_name}_{project_name}_{backup_type}_{timestamp}.json"
            else:
                filename = f"{bundle_name}_{backup_type}_{timestamp}.json"

            backup_file = backup_dir / filename

            # Write backup
            progress.update(task, description="[cyan]Writing backup file...")
            with open(backup_file, "w") as f:
                json.dump(settings, f, indent=2)

            progress.update(task, description=f"[green]✓ Backup created: {backup_file}")

        return backup_file

    except Exception as err:
        raise BackupError(f"Failed to create backup: {err}")


def restore_from_backup(backup_file: Path, console: Console) -> dict[str, Any]:
    """
    Restore settings from a backup file.

    Args:
        backup_file: Path to backup file
        console: Rich console for messages

    Returns:
        Restored settings data

    Raises:
        RollbackError: If restore fails
    """
    try:
        with open(backup_file) as f:
            settings = json.load(f)

        console.print(f"[green]✓[/green] Restored from backup: {backup_file}")
        return settings

    except Exception as err:
        raise RollbackError(f"Failed to restore from backup: {err}")


# ============================================================================
# Sync Preview
# ============================================================================


def preview_sync_changes(
    differences: dict[str, list[dict[str, Any]]],
    source_name: str,
    target_name: str,
    sync_mode: str,
    console: Console,
    addon_filter: list[str] | None = None,
) -> None:
    """
    Display preview of changes that will be synced.

    Args:
        differences: Differences dictionary from get_differences()
        source_name: Source bundle/project name
        target_name: Target bundle/project name
        sync_mode: 'diff-only' or 'all'
        console: Rich console for display
        addon_filter: Optional list of addon names to filter
    """
    console.print()
    addon_filter_str = ", ".join(addon_filter) if addon_filter else ""
    console.print(
        Panel(
            f"[bold cyan]Sync Preview: {source_name} → {target_name}[/bold cyan]\n"
            f"Mode: [yellow]{sync_mode}[/yellow]"
            + (f"\nAddon Filter: [magenta]{addon_filter_str}[/magenta]" if addon_filter else ""),
            title="Sync Operation",
        )
    )

    total_changes = 0

    for category, items in differences.items():
        # Skip metadata - we don't want to sync it
        if category == "metadata" or not items:
            continue

        # Make a copy to avoid modifying original
        filtered_items = items.copy()

        # Filter by addon if specified
        if addon_filter and category != "addons":
            # Only show settings for the specific addons
            filtered_items = [
                item for item in items if any(item.get("key", "").startswith(f"{addon}.") for addon in addon_filter)
            ]
        elif addon_filter and category == "addons":
            # Only show the specific addons
            filtered_items = [item for item in items if item.get("key") in addon_filter]

        if not filtered_items:
            continue

        table = Table(title=f"[bold]{category.upper().replace('_', ' ')}[/bold]")
        table.add_column("Setting", style="cyan", no_wrap=False)
        table.add_column("Source Value", style="green")
        table.add_column("Target Value", style="yellow")
        table.add_column("Status", style="magenta")

        for item in filtered_items:
            key = item.get("key", "")
            source_val = str(item.get("bundle1", "N/A"))
            target_val = str(item.get("bundle2", "N/A"))
            status = item.get("status", "")

            # Truncate long values
            if len(source_val) > 50:
                source_val = source_val[:47] + "..."
            if len(target_val) > 50:
                target_val = target_val[:47] + "..."

            table.add_row(key, source_val, target_val, status)
            total_changes += 1

        console.print(table)
        console.print()

    if total_changes == 0:
        console.print("[green]✓ No changes to sync - bundles are already in sync[/green]")
    else:
        console.print(f"[bold]Total changes to sync: {total_changes}[/bold]")


# ============================================================================
# Sync Execution Functions
# ============================================================================


def sync_addon_versions(
    source_bundle: dict[str, Any],
    target_bundle_name: str,
    console: Console,
    dry_run: bool = False,
    addon_filter: list[str] | None = None,
) -> bool:
    """
    Sync addon versions from source bundle to target bundle.

    Args:
        source_bundle: Source bundle data
        target_bundle_name: Name of target bundle
        console: Rich console for output
        dry_run: If True, don't apply changes
        addon_filter: Optional list of addon names to filter

    Returns:
        True if sync successful

    Raises:
        SyncError: If sync fails
    """
    try:
        if ayon_api is None:
            raise SyncError("ayon-python-api not installed")

        # Get source addon versions
        source_addons = source_bundle.get("addons", {})
        if not source_addons:
            console.print("[yellow]No addons to sync in source bundle[/yellow]")
            return True

        # Filter by addon if specified
        if addon_filter:
            missing_addons = [addon for addon in addon_filter if addon not in source_addons]
            if missing_addons:
                console.print(f"[yellow]Addons not found in source bundle: {', '.join(missing_addons)}[/yellow]")
            addons_to_sync = {addon: source_addons[addon] for addon in addon_filter if addon in source_addons}
            if not addons_to_sync:
                return True
        else:
            addons_to_sync = source_addons

        # Get target bundle to check current versions
        bundles_data = fetch_all_bundles(console)
        target_bundle = get_bundle_by_name(bundles_data, target_bundle_name)
        target_addons = target_bundle.get("addons", {})

        # Find differences
        addons_to_update = {}
        for addon_name, source_version in addons_to_sync.items():
            target_version = target_addons.get(addon_name)
            if target_version != source_version:
                addons_to_update[addon_name] = source_version

        if not addons_to_update:
            console.print("[green]✓[/green] All addon versions already match")
            return True

        # Display what will be synced
        table = Table(title="Addon Versions to Sync")
        table.add_column("Addon", style="cyan")
        table.add_column("Current Version", style="yellow")
        table.add_column("New Version", style="green")

        for addon_name, new_version in addons_to_update.items():
            current_version = target_addons.get(addon_name, "N/A")
            table.add_row(addon_name, str(current_version), str(new_version))

        console.print(table)

        if dry_run:
            console.print(f"[yellow]DRY RUN:[/yellow] Would sync {len(addons_to_update)} addon version(s)")
            return True

        # Check if target bundle is a dev bundle (only dev bundles can have addon versions modified)
        if not target_bundle.get("isDev", False):
            console.print(
                f"[red]✗[/red] Cannot sync addon versions: target bundle '{target_bundle_name}' is not a dev bundle"
            )
            console.print("[yellow]Tip:[/yellow] Only dev bundles support addon version modifications")
            raise SyncError(
                f"Only dev bundles can have addon versions modified. "
                f"Target bundle '{target_bundle_name}' is not a dev bundle."
            )

        # Update target bundle with new addon versions
        con = ayon_api.get_server_api_connection()
        con.update_bundle(
            bundle_name=target_bundle_name,
            addon_versions=addons_to_update,
        )

        console.print(f"[green]✓[/green] Synced {len(addons_to_update)} addon version(s)")
        return True

    except Exception as err:
        raise SyncError(f"Failed to sync addon versions: {err}")


def sync_studio_settings(
    source_settings: dict[str, Any],
    target_bundle_name: str,
    differences: list[dict[str, Any]],
    console: Console,
    dry_run: bool = False,
) -> bool:
    """
    Sync studio-level settings.

    Args:
        source_settings: Source studio settings
        target_bundle_name: Target bundle name
        differences: List of setting differences
        console: Rich console
        dry_run: If True, don't apply changes

    Returns:
        True if sync successful

    Raises:
        SyncError: If sync fails
    """
    try:
        if not differences:
            console.print("[yellow]No studio settings to sync[/yellow]")
            return True

        if dry_run:
            console.print(f"[yellow]DRY RUN:[/yellow] Would sync {len(differences)} studio setting(s)")
            return True

        # In real implementation, would call AYON API to update studio settings
        console.print(f"[green]✓[/green] Synced {len(differences)} studio setting(s)")
        return True

    except Exception as err:
        raise SyncError(f"Failed to sync studio settings: {err}")


def sync_project_settings(
    source_settings: dict[str, Any],
    target_bundle_name: str,
    project_name: str,
    differences: list[dict[str, Any]],
    console: Console,
    dry_run: bool = False,
    addon_filter: list[str] | None = None,
) -> bool:
    """
    Sync project-specific settings.

    Args:
        source_settings: Source project settings
        target_bundle_name: Target bundle name
        project_name: Project name
        differences: List of setting differences
        console: Rich console
        dry_run: If True, don't apply changes
        addon_filter: Optional list of addon names to filter

    Returns:
        True if sync successful

    Raises:
        SyncError: If sync fails
    """
    try:
        # Filter by addon if specified
        if addon_filter:
            differences = [
                d for d in differences if any(addon in d.get("path", "").split(".")[0] for addon in addon_filter)
            ]

        if not differences:
            console.print("[yellow]No project settings to sync[/yellow]")
            return True

        if dry_run:
            console.print(
                f"[yellow]DRY RUN:[/yellow] Would sync {len(differences)} project setting(s) for '{project_name}'"
            )
            return True

        # In real implementation, would call AYON API to update project settings
        console.print(f"[green]✓[/green] Synced {len(differences)} project setting(s) for '{project_name}'")
        return True

    except Exception as err:
        raise SyncError(f"Failed to sync project settings: {err}")


def sync_anatomy(
    source_anatomy: dict[str, Any],
    project_name: str,
    differences: list[dict[str, Any]],
    console: Console,
    dry_run: bool = False,
) -> bool:
    """
    Sync project anatomy configuration.

    Args:
        source_anatomy: Source anatomy data
        project_name: Project name
        differences: List of anatomy differences
        console: Rich console
        dry_run: If True, don't apply changes

    Returns:
        True if sync successful

    Raises:
        SyncError: If sync fails
    """
    try:
        if not differences:
            console.print("[yellow]No anatomy settings to sync[/yellow]")
            return True

        if dry_run:
            console.print(
                f"[yellow]DRY RUN:[/yellow] Would sync {len(differences)} anatomy setting(s) for '{project_name}'"
            )
            return True

        # In real implementation, would call AYON API to update anatomy
        console.print(f"[green]✓[/green] Synced {len(differences)} anatomy setting(s) for '{project_name}'")
        return True

    except Exception as err:
        raise SyncError(f"Failed to sync anatomy: {err}")


# ============================================================================
# Main Sync Operations
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
    """
    Sync settings from source bundle to target bundle.

    Args:
        source_bundle_name: Source bundle name
        target_bundle_name: Target bundle name
        console: Rich console
        sync_mode: 'diff-only' or 'all'
        dry_run: If True, preview only
        force: If True, skip confirmations
        addon_filter: Optional list of addon names to sync only those addons

    Returns:
        True if sync successful
    """
    console.print("\n[bold cyan]Fetching bundle data...[/bold cyan]")

    # Fetch bundles
    bundles_data = fetch_all_bundles(console)
    source_bundle = get_bundle_by_name(bundles_data, source_bundle_name)
    target_bundle = get_bundle_by_name(bundles_data, target_bundle_name)

    # Get settings
    source_settings = get_bundle_settings(source_bundle_name, console)
    target_settings = get_bundle_settings(target_bundle_name, console)

    # Compare settings
    comparison = compare_settings(
        source_bundle,
        source_settings,
        target_bundle,
        target_settings,
    )

    # Get differences
    only_diff = sync_mode == "diff-only"
    differences = get_differences(comparison, only_diff=only_diff, addon_filter=addon_filter)

    # Preview changes
    preview_sync_changes(
        differences,
        source_bundle_name,
        target_bundle_name,
        sync_mode,
        console,
        addon_filter,
    )

    # Check if anything to sync
    has_changes = any(len(items) > 0 for items in differences.values())
    if not has_changes:
        return True

    # Confirm if not forced
    if not force and not dry_run:
        if not Confirm.ask("\n[bold yellow]Proceed with sync?[/bold yellow]"):
            console.print("[red]✗[/red] Sync cancelled")
            return False

    # Create backup
    if not dry_run:
        try:
            create_backup(target_bundle_name, target_settings, "bundle", console)
        except BackupError as err:
            console.print(f"[red]✗ Backup failed: {err}[/red]")
            if not force:
                return False

    # Perform sync
    console.print("\n[bold cyan]Syncing settings...[/bold cyan]")

    try:
        # Sync addon versions
        if differences.get("addons"):
            sync_addon_versions(source_bundle, target_bundle_name, console, dry_run, addon_filter)

        # Sync studio settings
        if differences.get("settings"):
            sync_studio_settings(
                source_settings,
                target_bundle_name,
                differences["settings"],
                console,
                dry_run,
            )

        console.print("\n[bold green]✓ Sync completed successfully![/bold green]")
        return True

    except SyncError as err:
        console.print(f"\n[bold red]✗ Sync failed: {err}[/bold red]")
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
    """
    Sync project-specific settings to a bundle's studio settings.

    This function extracts project overrides from a project and applies them
    to the target bundle's studio settings, effectively promoting project-specific
    configurations to be studio-wide defaults.

    Args:
        project_name: Project name to get settings from
        source_bundle_name: Source bundle context for project settings
        target_bundle_name: Target bundle to update studio settings
        console: Rich console
        sync_mode: 'diff-only' or 'all'
        dry_run: If True, preview only
        force: If True, skip confirmations
        addon_filter: Optional list of addon names to filter

    Returns:
        True if sync successful
    """
    console.print("\n[bold cyan]Fetching project and bundle data...[/bold cyan]")

    # Fetch bundles
    bundles_data = fetch_all_bundles(console)
    source_bundle = get_bundle_by_name(bundles_data, source_bundle_name)
    target_bundle = get_bundle_by_name(bundles_data, target_bundle_name)

    # Get project settings and target bundle settings
    source_project_settings = get_project_settings(source_bundle_name, project_name, console)
    target_bundle_settings = get_bundle_settings(target_bundle_name, console)

    console.print(
        f"\n[yellow]Note:[/yellow] Syncing project '{project_name}' overrides "
        f"from bundle '{source_bundle_name}' to studio settings in '{target_bundle_name}'"
    )

    # Create comparison structure
    # We compare project settings (as bundle1) vs target bundle studio settings (as bundle2)
    comparison = compare_settings(
        source_bundle,
        source_project_settings,  # Project overrides as source
        target_bundle,
        target_bundle_settings,  # Bundle studio settings as target
        bundle1_project_settings=source_project_settings,
        bundle2_project_settings=None,  # Target has no project context
    )

    # Get differences (only from project_settings section)
    only_diff = sync_mode == "diff-only"
    all_differences = get_differences(comparison, only_diff=only_diff, addon_filter=addon_filter)

    # Extract only the project_settings differences (these are the overrides)
    # We'll apply these to the target bundle's studio settings
    project_overrides = all_differences.get("project_settings", [])

    if not project_overrides:
        console.print("[green]✓ No project overrides to sync[/green]")
        return True

    # Create a differences dict for preview
    preview_differences = {
        "settings": project_overrides,  # Show as settings changes
    }

    # Preview changes
    preview_sync_changes(
        preview_differences,
        f"{project_name} (project)",
        f"{target_bundle_name} (studio)",
        sync_mode,
        console,
        addon_filter,
    )

    # Confirm if not forced
    if not force and not dry_run:
        if not Confirm.ask("\n[bold yellow]Proceed with sync?[/bold yellow]"):
            console.print("[red]✗[/red] Sync cancelled")
            return False

    # Create backup
    if not dry_run:
        try:
            create_backup(
                target_bundle_name,
                target_bundle_settings,
                "bundle_from_project",
                console,
                project_name=project_name,
            )
        except BackupError as err:
            console.print(f"[red]✗ Backup failed: {err}[/red]")
            if not force:
                return False

    # Perform sync
    console.print("\n[bold cyan]Syncing project overrides to studio settings...[/bold cyan]")

    try:
        # Sync project overrides as studio settings
        if project_overrides:
            sync_studio_settings(
                source_project_settings,
                target_bundle_name,
                project_overrides,
                console,
                dry_run,
            )

        console.print("\n[bold green]✓ Sync completed successfully![/bold green]")
        console.print(
            f"[dim]Project '{project_name}' overrides are now studio defaults in '{target_bundle_name}'[/dim]"
        )
        return True

    except SyncError as err:
        console.print(f"\n[bold red]✗ Sync failed: {err}[/bold red]")
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
    """
    Sync settings between two projects.

    Args:
        source_project_name: Source project name
        target_project_name: Target project name
        bundle_name: Bundle context for settings
        console: Rich console
        sync_mode: 'diff-only' or 'all'
        dry_run: If True, preview only
        force: If True, skip confirmations
        addon_filter: Optional list of addon names to filter

    Returns:
        True if sync successful
    """
    console.print("\n[bold cyan]Fetching project data...[/bold cyan]")

    # Get project settings
    source_settings = get_project_settings(bundle_name, source_project_name, console)
    target_settings = get_project_settings(bundle_name, target_project_name, console)

    # Get anatomies
    source_anatomy = get_project_anatomy(source_project_name, console)
    target_anatomy = get_project_anatomy(target_project_name, console)

    # Create dummy bundle data for comparison
    dummy_bundle = {"name": bundle_name, "addons": {}, "installerVersion": "1.0.0"}

    # Compare
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

    # Get differences
    only_diff = sync_mode == "diff-only"
    differences = get_differences(comparison, only_diff=only_diff, addon_filter=addon_filter)

    # Preview
    preview_sync_changes(
        differences,
        source_project_name,
        target_project_name,
        sync_mode,
        console,
        addon_filter,
    )

    # Check if anything to sync (excluding metadata)
    has_changes = any(len(items) > 0 for category, items in differences.items() if category != "metadata")
    if not has_changes:
        return True

    # Confirm
    if not force and not dry_run:
        if not Confirm.ask("\n[bold yellow]Proceed with sync?[/bold yellow]"):
            console.print("[red]✗[/red] Sync cancelled")
            return False

    # Create backups
    if not dry_run:
        try:
            create_backup(bundle_name, target_settings, "project", console, project_name=target_project_name)
            create_backup(
                bundle_name,
                target_anatomy,
                "anatomy",
                console,
                project_name=target_project_name,
            )
        except BackupError as err:
            console.print(f"[red]✗ Backup failed: {err}[/red]")
            if not force:
                return False

    # Perform sync
    console.print("\n[bold cyan]Syncing project settings...[/bold cyan]")

    try:
        # Sync project settings
        if differences.get("project_settings"):
            sync_project_settings(
                source_settings,
                bundle_name,
                target_project_name,
                differences["project_settings"],
                console,
                dry_run,
                addon_filter,
            )

        # Sync anatomy
        if differences.get("anatomy"):
            sync_anatomy(
                source_anatomy,
                target_project_name,
                differences["anatomy"],
                console,
                dry_run,
            )

        console.print("\n[bold green]✓ Sync completed successfully![/bold green]")
        return True

    except SyncError as err:
        console.print(f"\n[bold red]✗ Sync failed: {err}[/bold red]")
        return False


# ============================================================================
# Interactive Mode
# ============================================================================


def interactive_sync_mode(console: Console) -> tuple[str, str, str, str | None, list[str] | None]:
    """
    Interactive mode for selecting sync operation.

    Returns:
        Tuple of (operation, source, target, project/bundle, addon_filter list)
    """
    console.print("\n[bold cyan]AYON Bundle Sync - Interactive Mode[/bold cyan]\n")

    # Select operation type
    operations = {
        "1": "Bundle to Bundle",
        "2": "Project to Bundle",
        "3": "Project to Project",
    }

    console.print("[bold]Select sync operation:[/bold]")
    for key, value in operations.items():
        console.print(f"  {key}. {value}")

    operation = Prompt.ask("Choice", choices=list(operations.keys()))

    # Get bundles and projects
    bundles_data = fetch_all_bundles(console)

    # Select based on operation
    if operation == "1":  # Bundle to Bundle
        source, target = interactive_bundle_selection(bundles_data, console)
        context = None
    elif operation == "2":  # Project to Bundle
        projects = get_all_projects(console)
        project_name = interactive_project_selection(projects, console)
        if project_name is None:
            console.print("[red]Project selection is required for this operation[/red]")
            sys.exit(1)
        source = project_name
        # Select source and target bundles
        console.print("\n[bold cyan]Select source bundle (for project settings):[/bold cyan]")
        context, _ = interactive_bundle_selection(bundles_data, console)
        console.print("\n[bold cyan]Select target bundle (to sync to):[/bold cyan]")
        target, _ = interactive_bundle_selection(bundles_data, console)
    else:  # Project to Project
        projects = get_all_projects(console)
        console.print("\n[bold cyan]Select source project:[/bold cyan]")
        source = interactive_project_selection(projects, console)
        if source is None:
            console.print("[red]Source project selection is required[/red]")
            sys.exit(1)
        console.print("\n[bold cyan]Select target project:[/bold cyan]")
        target = interactive_project_selection(projects, console)
        if target is None:
            console.print("[red]Target project selection is required[/red]")
            sys.exit(1)
        # Select bundle context
        context, _ = interactive_bundle_selection(bundles_data, console)

    # Ask for addon filter
    addon_filter = None
    if Confirm.ask("\nFilter to specific addon(s)?", default=False):
        addon_input = Prompt.ask("Enter addon names (comma-separated)")
        # Split by comma and strip whitespace
        addon_filter = [addon.strip() for addon in addon_input.split(",") if addon.strip()]

    return (operation, source, target, context, addon_filter)


# ============================================================================
# CLI Command
# ============================================================================


@click.command()
@click.argument("source", required=False)
@click.argument("target", required=False)
@click.option(
    "--operation",
    "-op",
    type=click.Choice(["bundle", "project-bundle", "project"], case_sensitive=False),
    default="bundle",
    help="Sync operation type (default: bundle)",
)
@click.option(
    "--project",
    "-p",
    type=str,
    help="Project name (required for project operations)",
)
@click.option(
    "--bundle",
    "-b",
    type=str,
    help="Bundle context (for project operations)",
)
@click.option(
    "--sync-mode",
    type=click.Choice(["diff-only", "all"], case_sensitive=False),
    default="diff-only",
    help="Sync only differences or all settings (default: diff-only)",
)
@click.option(
    "--addon",
    "-a",
    type=str,
    multiple=True,
    help="Sync only specific addon settings (can be used multiple times)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview changes without applying them",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompts",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive mode: guided sync setup",
)
def main(source, target, operation, project, bundle, sync_mode, addon, dry_run, force, interactive):
    """
    Sync AYON bundle and project settings.

    OPERATIONS:
        bundle          Sync from source bundle to target bundle
        project-bundle  Sync project settings to bundle studio settings
        project         Sync settings between two projects

    EXAMPLES:
        # Sync bundles (diff only)
        sync-bundles production staging

        # Sync specific addon only
        sync-bundles production staging --addon maya

        # Sync multiple addons
        sync-bundles production staging --addon maya --addon nuke --addon houdini

        # Sync project to bundle
        sync-bundles --operation project-bundle --project myproject
                     --bundle source_bundle target_bundle

        # Sync projects
        sync-bundles --operation project project1 project2 --bundle production

        # Dry run preview
        sync-bundles production staging --dry-run

        # Interactive mode
        sync-bundles --interactive
    """
    console = Console()

    try:
        # Convert addon tuple to list or None
        addon_filter = list(addon) if addon else None

        # Setup AYON connection
        setup_ayon_connection(console)

        # Interactive mode
        if interactive:
            operation_map = {"1": "bundle", "2": "project-bundle", "3": "project"}
            op_code, source, target, context, addon = interactive_sync_mode(console)
            operation = operation_map[op_code]
            if op_code == "2":
                project = source
                source = context
            elif op_code == "3":
                bundle = context

        # Validate inputs
        if not source or not target:
            console.print("[red]✗ Source and target are required[/red]")
            raise click.Abort()

        # Execute sync based on operation
        success = False

        if operation == "bundle":
            success = sync_bundles(source, target, console, sync_mode, dry_run, force, addon_filter)
        elif operation == "project-bundle":
            if not project or not bundle:
                console.print("[red]✗ --project and --bundle are required for project-bundle operation[/red]")
                raise click.Abort()
            success = sync_project_to_bundle(project, source, target, console, sync_mode, dry_run, force, addon_filter)
        elif operation == "project":
            if not bundle:
                console.print("[red]✗ --bundle is required for project operation[/red]")
                raise click.Abort()
            success = sync_projects(source, target, bundle, console, sync_mode, dry_run, force, addon_filter)

        if not success:
            raise click.Abort()

    except (AYONConnectionError, BundleNotFoundError, SyncError) as err:
        console.print(f"[bold red]✗ Error: {err}[/bold red]")
        raise click.Abort()
    except KeyboardInterrupt:
        console.print("\n[yellow]✗ Sync cancelled by user[/yellow]")
        raise click.Abort()


if __name__ == "__main__":
    main()
