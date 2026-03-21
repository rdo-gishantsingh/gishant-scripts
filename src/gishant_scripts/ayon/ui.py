"""Interactive TUI selection functions for AYON operations.

Provides Rich-based interactive prompts for selecting bundles and projects
from the AYON server.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table


def interactive_bundle_selection(bundles_data: dict[str, Any], console: Console) -> tuple[str, str]:
    """Interactively select two bundles for comparison.

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
        if choice in bundle_names:
            bundle1_name = choice
            break
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
        if choice in bundle_names:
            bundle2_name = choice
            if bundle2_name == bundle1_name:
                console.print("[red]Please select a different bundle for comparison.[/red]")
                continue
            break
        console.print(f"[red]Invalid choice. Please enter a number 1-{len(bundle_names)} or a bundle name.[/red]")

    console.print(f"[green]✓ Selected second bundle: {bundle2_name}[/green]\n")
    return bundle1_name, bundle2_name


def interactive_project_selection(projects: list[dict[str, Any]], console: Console) -> str | None:
    """Interactively select a project for comparison.

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
        if choice in project_names:
            project_name = choice
            break
        console.print(f"[red]Invalid choice. Please enter a number 1-{len(project_names)} or a project name.[/red]")

    console.print(f"\n[green]✓ Selected project: {project_name}[/green]\n")
    return project_name
