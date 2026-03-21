"""AYON bundle fetching and management utilities.

Provides functions for retrieving bundles, bundle settings, project settings,
project anatomy, and project lists from the AYON server.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console

from gishant_scripts.ayon.connection import AYONConnectionError

try:
    import ayon_api
except ImportError:
    ayon_api = None


class BundleNotFoundError(Exception):
    """Raised when a bundle is not found."""


def fetch_all_bundles(console: Console) -> dict[str, Any]:
    """Fetch all bundles from AYON server.

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
    """Get a specific bundle by name.

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
    """Get all settings for a bundle including addon settings.

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
    """Get project-specific settings overrides for a bundle.

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
    """Get project anatomy configuration.

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
    """Get list of all projects.

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
