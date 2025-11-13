"""Common utilities for AYON bundle operations.

This module provides shared functionality for analyzing and syncing AYON bundles,
including connection management, data fetching, and comparison operations.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

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


class AYONConnectionError(Exception):
    """Raised when AYON connection fails."""

    pass


class BundleNotFoundError(Exception):
    """Raised when a bundle is not found."""

    pass


# ============================================================================
# Connection and Configuration
# ============================================================================


def setup_ayon_connection(console: Console) -> None:
    """
    Set up AYON connection using rdo-ayon-utils or environment variables.

    Args:
        console: Rich console for displaying messages

    Raises:
        AYONConnectionError: If connection setup fails
    """
    if ayon_api is None:
        raise AYONConnectionError("ayon-python-api not installed. Install it with: uv pip install ayon-python-api")

    # Try using rdo-ayon-utils first
    if ayon_utils is not None:
        try:
            console.print("[dim]Connecting to AYON using rdo-ayon-utils...[/dim]")
            ayon_utils.set_connection()
            server_url = ayon_api.get_base_url()
            console.print(f"[green]✓ Connected to AYON server: {server_url}[/green]")
            return
        except Exception as err:
            console.print(f"[yellow]Warning: rdo-ayon-utils connection failed: {err}[/yellow]")

    # Fallback to environment variables
    server_url = os.getenv("AYON_SERVER_URL")
    api_key = os.getenv("AYON_API_KEY")

    if not server_url or not api_key:
        raise AYONConnectionError(
            "AYON connection not configured. Please set AYON_SERVER_URL and AYON_API_KEY environment variables."
        )

    try:
        os.environ["AYON_SERVER_URL"] = server_url
        os.environ["AYON_API_KEY"] = api_key

        if not ayon_api.is_connection_created():
            ayon_api.init()

        console.print(f"[green]✓ Connected to AYON server: {server_url}[/green]")
    except Exception as err:
        raise AYONConnectionError(f"Failed to connect to AYON server: {err}") from err


# ============================================================================
# Bundle Operations
# ============================================================================


def fetch_all_bundles(console: Console) -> dict[str, Any]:
    """
    Fetch all bundles from AYON server.

    Args:
        console: Rich console for displaying messages

    Returns:
        Dictionary containing bundles data with keys:
        - bundles: List of bundle dicts
        - productionBundle: Production bundle name
        - stagingBundle: Staging bundle name
        - devBundle: Dev bundle name

    Raises:
        AYONConnectionError: If fetching bundles fails
    """
    try:
        console.print("[dim]Fetching bundles from AYON server...[/dim]")
        bundles_data = ayon_api.get_bundles()
        console.print(f"[green]✓ Found {len(bundles_data.get('bundles', []))} bundles[/green]")
        return bundles_data
    except Exception as err:
        raise AYONConnectionError(f"Failed to fetch bundles: {err}") from err


def get_bundle_by_name(bundles_data: dict[str, Any], bundle_name: str) -> dict[str, Any]:
    """
    Get a specific bundle by name.

    Args:
        bundles_data: Bundles data from fetch_all_bundles()
        bundle_name: Name of the bundle to retrieve

    Returns:
        Bundle dictionary

    Raises:
        BundleNotFoundError: If bundle not found
    """
    bundles = bundles_data.get("bundles", [])
    for bundle in bundles:
        if bundle["name"] == bundle_name:
            return bundle

    raise BundleNotFoundError(f"Bundle '{bundle_name}' not found")


def get_bundle_settings(bundle_name: str, console: Console) -> dict[str, Any]:
    """
    Get all settings for a bundle including addon settings.

    Args:
        bundle_name: Name of the bundle
        console: Rich console for displaying messages

    Returns:
        Dictionary containing all bundle settings

    Raises:
        AYONConnectionError: If fetching settings fails
    """
    try:
        console.print(f"[dim]Fetching settings for bundle '{bundle_name}'...[/dim]")

        # Get addon settings (studio-level settings for this bundle)
        settings = ayon_api.get_addons_studio_settings(bundle_name=bundle_name)

        console.print(f"[green]✓ Retrieved settings for {len(settings)} addons[/green]")
        return settings
    except Exception as err:
        raise AYONConnectionError(f"Failed to fetch bundle settings: {err}") from err


def get_project_settings(bundle_name: str, project_name: str, console: Console) -> dict[str, Any]:
    """
    Get project-specific settings overrides for a bundle.

    Args:
        bundle_name: Name of the bundle
        project_name: Name of the project
        console: Rich console for displaying messages

    Returns:
        Dictionary containing project-specific settings

    Raises:
        AYONConnectionError: If fetching settings fails
    """
    try:
        console.print(f"[dim]Fetching project settings for '{project_name}' in bundle '{bundle_name}'...[/dim]")

        # Get project-specific addon settings
        settings = ayon_api.get_addons_project_settings(project_name=project_name, bundle_name=bundle_name)

        console.print(f"[green]✓ Retrieved project settings for {len(settings)} addons[/green]")
        return settings
    except Exception as err:
        raise AYONConnectionError(f"Failed to fetch project settings: {err}") from err


def get_project_anatomy(project_name: str, console: Console) -> dict[str, Any]:
    """
    Get project anatomy configuration.

    Args:
        project_name: Name of the project
        console: Rich console for displaying messages

    Returns:
        Dictionary containing project anatomy

    Raises:
        AYONConnectionError: If fetching anatomy fails
    """
    try:
        console.print(f"[dim]Fetching anatomy for project '{project_name}'...[/dim]")

        anatomy = ayon_api.get_project(project_name).get("anatomy", {})

        console.print(f"[green]✓ Retrieved anatomy for '{project_name}'[/green]")
        return anatomy
    except Exception as err:
        raise AYONConnectionError(f"Failed to fetch project anatomy: {err}") from err


def get_all_projects(console: Console) -> list[dict[str, Any]]:
    """
    Get list of all projects.

    Args:
        console: Rich console for displaying messages

    Returns:
        List of project dictionaries

    Raises:
        AYONConnectionError: If fetching projects fails
    """
    try:
        console.print("[dim]Fetching projects from AYON server...[/dim]")
        projects = list(ayon_api.get_projects())
        console.print(f"[green]✓ Found {len(projects)} projects[/green]")
        return projects
    except Exception as err:
        raise AYONConnectionError(f"Failed to fetch projects: {err}") from err


# ============================================================================
# Settings Comparison
# ============================================================================


def flatten_dict(
    data: dict[str, Any],
    parent_key: str = "",
    sep: str = ".",
    max_depth: int | None = None,
    current_depth: int = 0,
) -> dict[str, Any]:
    """
    Flatten a nested dictionary into dot-notation keys.

    Args:
        data: Dictionary to flatten
        parent_key: Parent key prefix
        sep: Separator for nested keys
        max_depth: Maximum depth to flatten (None for unlimited)
        current_depth: Current depth level

    Returns:
        Flattened dictionary
    """
    items = []

    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key

        if max_depth is not None and current_depth >= max_depth:
            items.append((new_key, value))
        elif isinstance(value, dict) and value:
            items.extend(
                flatten_dict(
                    value,
                    new_key,
                    sep=sep,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                ).items()
            )
        else:
            items.append((new_key, value))

    return dict(items)


def compare_settings(
    bundle1_data: dict[str, Any],
    bundle1_settings: dict[str, Any],
    bundle2_data: dict[str, Any],
    bundle2_settings: dict[str, Any],
    bundle1_project_settings: dict[str, Any] | None = None,
    bundle2_project_settings: dict[str, Any] | None = None,
    anatomy1: dict[str, Any] | None = None,
    anatomy2: dict[str, Any] | None = None,
    max_depth: int | None = None,
) -> dict[str, Any]:
    """
    Compare settings between two bundles.

    Args:
        bundle1_data: First bundle metadata
        bundle1_settings: First bundle studio settings
        bundle2_data: Second bundle metadata
        bundle2_settings: Second bundle studio settings
        bundle1_project_settings: First bundle project settings (optional)
        bundle2_project_settings: Second bundle project settings (optional)
        anatomy1: First project anatomy (optional)
        anatomy2: Second project anatomy (optional)
        max_depth: Maximum depth for comparison

    Returns:
        Dictionary with comparison results
    """
    comparison = {
        "metadata": {
            "bundle1": {
                "name": bundle1_data["name"],
                "installerVersion": bundle1_data.get("installerVersion"),
                "isProduction": bundle1_data.get("isProduction", False),
                "isStaging": bundle1_data.get("isStaging", False),
                "isDev": bundle1_data.get("isDev", False),
                "createdAt": bundle1_data.get("createdAt"),
                "updatedAt": bundle1_data.get("updatedAt"),
            },
            "bundle2": {
                "name": bundle2_data["name"],
                "installerVersion": bundle2_data.get("installerVersion"),
                "isProduction": bundle2_data.get("isProduction", False),
                "isStaging": bundle2_data.get("isStaging", False),
                "isDev": bundle2_data.get("isDev", False),
                "createdAt": bundle2_data.get("createdAt"),
                "updatedAt": bundle2_data.get("updatedAt"),
            },
        },
        "addons": {
            "bundle1": bundle1_data.get("addons", {}),
            "bundle2": bundle2_data.get("addons", {}),
        },
        "dependencies": {
            "bundle1": bundle1_data.get("dependencyPackages", {}),
            "bundle2": bundle2_data.get("dependencyPackages", {}),
        },
        "settings": {
            "bundle1": flatten_dict(bundle1_settings, max_depth=max_depth),
            "bundle2": flatten_dict(bundle2_settings, max_depth=max_depth),
        },
    }

    # Add project settings if provided
    if bundle1_project_settings is not None and bundle2_project_settings is not None:
        comparison["project_settings"] = {
            "bundle1": flatten_dict(bundle1_project_settings, max_depth=max_depth),
            "bundle2": flatten_dict(bundle2_project_settings, max_depth=max_depth),
        }

    # Add anatomy if provided
    if anatomy1 is not None and anatomy2 is not None:
        comparison["anatomy"] = {
            "bundle1": flatten_dict(anatomy1, max_depth=max_depth),
            "bundle2": flatten_dict(anatomy2, max_depth=max_depth),
        }

    return comparison


def get_differences(
    comparison: dict[str, Any], only_diff: bool = False, addon_filter: list[str] | None = None
) -> dict[str, list[dict[str, Any]]]:
    """
    Extract differences from comparison results.

    Args:
        comparison: Comparison results from compare_settings()
        only_diff: If True, only include differences; if False, include all settings
        addon_filter: Optional list of addon names to filter results

    Returns:
        Dictionary with lists of differences for each category
    """
    differences = {
        "metadata": [],
        "addons": [],
        "dependencies": [],
        "settings": [],
        "project_settings": [],
        "anatomy": [],
    }

    # Metadata differences
    for key in comparison["metadata"]["bundle1"].keys():
        val1 = comparison["metadata"]["bundle1"][key]
        val2 = comparison["metadata"]["bundle2"][key]

        if not only_diff or val1 != val2:
            differences["metadata"].append(
                {"key": key, "bundle1": val1, "bundle2": val2, "status": "changed" if val1 != val2 else "same"}
            )

    # Addon version differences
    all_addons = set(comparison["addons"]["bundle1"].keys()) | set(comparison["addons"]["bundle2"].keys())

    # Apply addon filter if specified
    if addon_filter:
        all_addons = {addon for addon in all_addons if addon in addon_filter}

    for addon in sorted(all_addons):
        val1 = comparison["addons"]["bundle1"].get(addon, "Not installed")
        val2 = comparison["addons"]["bundle2"].get(addon, "Not installed")

        if not only_diff or val1 != val2:
            status = "same"
            if val1 == "Not installed":
                status = "only_in_bundle2"
            elif val2 == "Not installed":
                status = "only_in_bundle1"
            elif val1 != val2:
                status = "changed"

            differences["addons"].append({"key": addon, "bundle1": val1, "bundle2": val2, "status": status})

    # Dependency differences
    all_platforms = set(comparison["dependencies"]["bundle1"].keys()) | set(
        comparison["dependencies"]["bundle2"].keys()
    )
    for platform in sorted(all_platforms):
        val1 = comparison["dependencies"]["bundle1"].get(platform, {})
        val2 = comparison["dependencies"]["bundle2"].get(platform, {})

        if not only_diff or val1 != val2:
            status = "same"
            if not val1:
                status = "only_in_bundle2"
            elif not val2:
                status = "only_in_bundle1"
            elif val1 != val2:
                status = "changed"

            differences["dependencies"].append(
                {"key": platform, "bundle1": json.dumps(val1), "bundle2": json.dumps(val2), "status": status}
            )

    # Settings differences
    all_keys = set(comparison["settings"]["bundle1"].keys()) | set(comparison["settings"]["bundle2"].keys())

    # Apply addon filter if specified
    if addon_filter:
        all_keys = {
            key for key in all_keys
            if any(key.startswith(f"{addon}.") or key == addon for addon in addon_filter)
        }

    for key in sorted(all_keys):
        val1 = comparison["settings"]["bundle1"].get(key, "Not set")
        val2 = comparison["settings"]["bundle2"].get(key, "Not set")

        if not only_diff or val1 != val2:
            status = "same"
            if val1 == "Not set":
                status = "only_in_bundle2"
            elif val2 == "Not set":
                status = "only_in_bundle1"
            elif val1 != val2:
                status = "changed"

            differences["settings"].append({"key": key, "bundle1": val1, "bundle2": val2, "status": status})

    # Project settings differences (if present)
    if "project_settings" in comparison:
        all_keys = set(comparison["project_settings"]["bundle1"].keys()) | set(
            comparison["project_settings"]["bundle2"].keys()
        )

        # Apply addon filter if specified
        if addon_filter:
            all_keys = {
                key for key in all_keys
                if any(key.startswith(f"{addon}.") or key == addon for addon in addon_filter)
            }

        for key in sorted(all_keys):
            val1 = comparison["project_settings"]["bundle1"].get(key, "Not set")
            val2 = comparison["project_settings"]["bundle2"].get(key, "Not set")

            if not only_diff or val1 != val2:
                status = "same"
                if val1 == "Not set":
                    status = "only_in_bundle2"
                elif val2 == "Not set":
                    status = "only_in_bundle1"
                elif val1 != val2:
                    status = "changed"

                differences["project_settings"].append(
                    {"key": key, "bundle1": val1, "bundle2": val2, "status": status}
                )

    # Anatomy differences (if present)
    if "anatomy" in comparison:
        all_keys = set(comparison["anatomy"]["bundle1"].keys()) | set(comparison["anatomy"]["bundle2"].keys())
        for key in sorted(all_keys):
            val1 = comparison["anatomy"]["bundle1"].get(key, "Not set")
            val2 = comparison["anatomy"]["bundle2"].get(key, "Not set")

            if not only_diff or val1 != val2:
                status = "same"
                if val1 == "Not set":
                    status = "only_in_bundle2"
                elif val2 == "Not set":
                    status = "only_in_bundle1"
                elif val1 != val2:
                    status = "changed"

                differences["anatomy"].append({"key": key, "bundle1": val1, "bundle2": val2, "status": status})

    return differences


# ============================================================================
# Interactive Selection
# ============================================================================


def interactive_bundle_selection(bundles_data: dict[str, Any], console: Console) -> tuple[str, str]:
    """
    Interactively select two bundles for comparison.

    Args:
        bundles_data: Bundles data from fetch_all_bundles()
        console: Rich console for display

    Returns:
        Tuple of (bundle1_name, bundle2_name)
    """
    bundles = bundles_data.get("bundles", [])
    production = bundles_data.get("productionBundle")
    staging = bundles_data.get("stagingBundle")
    dev = bundles_data.get("devBundle")

    # Display available bundles
    console.print("\n[bold cyan]Available Bundles:[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Bundle Name", style="yellow")
    table.add_column("Flags", style="green")
    table.add_column("Installer", style="blue")
    table.add_column("Addons", style="magenta")

    bundle_names = []
    for idx, bundle in enumerate(bundles, 1):
        name = bundle["name"]
        bundle_names.append(name)

        flags = []
        if name == production:
            flags.append("PROD")
        if name == staging:
            flags.append("STAGING")
        if name == dev:
            flags.append("DEV")

        flags_str = ", ".join(flags) if flags else "-"
        installer = bundle.get("installerVersion", "N/A")
        addon_count = len(bundle.get("addons", {}))

        table.add_row(str(idx), name, flags_str, installer, str(addon_count))

    console.print(table)
    console.print()

    # Select first bundle
    while True:
        choice = Prompt.ask("Select first bundle (number or name)", default="1")

        if choice.isdigit() and 1 <= int(choice) <= len(bundle_names):
            bundle1_name = bundle_names[int(choice) - 1]
            break
        elif choice in bundle_names:
            bundle1_name = choice
            break
        else:
            console.print(f"[red]Invalid choice. Please enter a number 1-{len(bundle_names)} or a bundle name.[/red]")

    console.print(f"[green]✓ Selected first bundle: {bundle1_name}[/green]\n")

    # Select second bundle
    while True:
        choice = Prompt.ask("Select second bundle (number or name)", default="2")

        if choice.isdigit() and 1 <= int(choice) <= len(bundle_names):
            bundle2_name = bundle_names[int(choice) - 1]
            if bundle2_name == bundle1_name:
                console.print("[red]Please select a different bundle for comparison.[/red]")
                continue
            break
        elif choice in bundle_names:
            bundle2_name = choice
            if bundle2_name == bundle1_name:
                console.print("[red]Please select a different bundle for comparison.[/red]")
                continue
            break
        else:
            console.print(f"[red]Invalid choice. Please enter a number 1-{len(bundle_names)} or a bundle name.[/red]")

    console.print(f"[green]✓ Selected second bundle: {bundle2_name}[/green]\n")
    return bundle1_name, bundle2_name


def interactive_project_selection(projects: list[dict[str, Any]], console: Console) -> str | None:
    """
    Interactively select a project for comparison.

    Args:
        projects: List of projects from get_all_projects()
        console: Rich console for display

    Returns:
        Project name or None to skip project comparison
    """
    console.print("\n[bold cyan]Project Selection:[/bold cyan]\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Project Name", style="yellow")
    table.add_column("Code", style="green")

    project_names = []
    for idx, project in enumerate(projects, 1):
        name = project["name"]
        project_names.append(name)
        code = project.get("code", "N/A")
        table.add_row(str(idx), name, code)

    console.print(table)
    console.print()

    while True:
        choice = Prompt.ask(
            "Select project (number/name) or press Enter to skip",
            default="",
        )

        if not choice:
            console.print("[yellow]Skipping project-specific comparison[/yellow]\n")
            return None

        if choice.isdigit() and 1 <= int(choice) <= len(project_names):
            project_name = project_names[int(choice) - 1]
            break
        elif choice in project_names:
            project_name = choice
            break
        else:
            console.print(f"[red]Invalid choice. Please enter a number 1-{len(project_names)} or a project name.[/red]")

    console.print(f"\n[green]✓ Selected project: {project_name}[/green]\n")
    return project_name
