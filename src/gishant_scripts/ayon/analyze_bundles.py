"""AYON Bundle Analysis Tool.

This module provides comprehensive utilities to compare settings between two AYON bundles,
including studio settings, project-specific overrides, and anatomy configurations.
Displays differences in Rich TUI format with table and tree views.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

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

# Import common utilities
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

# ============================================================================
# Unique Display and Export Functions
# ============================================================================
# All common functions (connection, bundle operations, comparison) have been
# moved to gishant_scripts.ayon.common module


# ============================================================================
# Rich TUI Display
# ============================================================================


def render_table_view(
    differences: dict[str, list[dict[str, Any]]],
    bundle1_name: str,
    bundle2_name: str,
    console: Console,
) -> None:
    """
    Render comparison results in table view.

    Args:
        differences: Differences from get_differences()
        bundle1_name: Name of first bundle
        bundle2_name: Name of second bundle
        console: Rich console for display
    """

    def create_table(title: str, show_status: bool = True) -> Table:
        """Create a table with standard columns."""
        table = Table(title=title, show_header=True, header_style="bold cyan")
        table.add_column("Setting", style="yellow", no_wrap=False)
        table.add_column(bundle1_name, style="green")
        table.add_column(bundle2_name, style="blue")
        if show_status:
            table.add_column("Status", style="magenta")
        return table

    # Metadata table
    if differences["metadata"]:
        meta_table = create_table("📋 Bundle Metadata")
        for item in differences["metadata"]:
            status_style = "green" if item["status"] == "unchanged" else "red"
            meta_table.add_row(
                item["key"],
                str(item["bundle1"]),
                str(item["bundle2"]),
                f"[{status_style}]{item['status']}[/{status_style}]",
            )
        console.print(meta_table)
        console.print()

    # Addons table
    if differences["addons"]:
        addons_table = create_table("🔌 Addon Versions")
        for item in differences["addons"]:
            status_color = {
                "unchanged": "green",
                "changed": "yellow",
                "added": "cyan",
                "removed": "red",
            }.get(item["status"], "white")

            addons_table.add_row(
                item["key"],
                str(item["bundle1"] or "-"),
                str(item["bundle2"] or "-"),
                f"[{status_color}]{item['status']}[/{status_color}]",
            )
        console.print(addons_table)
        console.print()

    # Dependencies table
    if differences["dependencies"]:
        deps_table = create_table("📦 Dependency Packages")
        for item in differences["dependencies"]:
            status_color = {
                "unchanged": "green",
                "changed": "yellow",
                "added": "cyan",
                "removed": "red",
            }.get(item["status"], "white")

            deps_table.add_row(
                item["key"],
                str(item["bundle1"] or "-"),
                str(item["bundle2"] or "-"),
                f"[{status_color}]{item['status']}[/{status_color}]",
            )
        console.print(deps_table)
        console.print()

    # Settings table
    if differences["settings"]:
        settings_table = create_table("⚙️  Studio Settings")
        for item in differences["settings"]:
            status_color = {
                "unchanged": "green",
                "changed": "yellow",
                "added": "cyan",
                "removed": "red",
            }.get(item["status"], "white")

            # Truncate long values
            val1_str = str(item["bundle1"] or "-")
            val2_str = str(item["bundle2"] or "-")
            if len(val1_str) > 50:
                val1_str = val1_str[:47] + "..."
            if len(val2_str) > 50:
                val2_str = val2_str[:47] + "..."

            settings_table.add_row(
                item["key"],
                val1_str,
                val2_str,
                f"[{status_color}]{item['status']}[/{status_color}]",
            )
        console.print(settings_table)
        console.print()

    # Project settings table
    if differences["project_settings"]:
        project_table = create_table("🎯 Project-Specific Settings")
        for item in differences["project_settings"]:
            status_color = {
                "unchanged": "green",
                "changed": "yellow",
                "added": "cyan",
                "removed": "red",
            }.get(item["status"], "white")

            val1_str = str(item["bundle1"] or "-")
            val2_str = str(item["bundle2"] or "-")
            if len(val1_str) > 50:
                val1_str = val1_str[:47] + "..."
            if len(val2_str) > 50:
                val2_str = val2_str[:47] + "..."

            project_table.add_row(
                item["key"],
                val1_str,
                val2_str,
                f"[{status_color}]{item['status']}[/{status_color}]",
            )
        console.print(project_table)
        console.print()

    # Anatomy table
    if differences["anatomy"]:
        anatomy_table = create_table("🏗️  Project Anatomy")
        for item in differences["anatomy"]:
            status_color = {
                "unchanged": "green",
                "changed": "yellow",
                "added": "cyan",
                "removed": "red",
            }.get(item["status"], "white")

            val1_str = str(item["bundle1"] or "-")
            val2_str = str(item["bundle2"] or "-")
            if len(val1_str) > 50:
                val1_str = val1_str[:47] + "..."
            if len(val2_str) > 50:
                val2_str = val2_str[:47] + "..."

            anatomy_table.add_row(
                item["key"],
                val1_str,
                val2_str,
                f"[{status_color}]{item['status']}[/{status_color}]",
            )
        console.print(anatomy_table)
        console.print()


def render_tree_view(
    comparison: dict[str, Any],
    bundle1_name: str,
    bundle2_name: str,
    only_diff: bool,
    console: Console,
) -> None:
    """
    Render comparison results in hierarchical tree view.

    Args:
        comparison: Comparison results from compare_settings()
        bundle1_name: Name of first bundle
        bundle2_name: Name of second bundle
        only_diff: If True, only show differences
        console: Rich console for display
    """
    root = Tree(f"[bold cyan]Bundle Comparison: {bundle1_name} vs {bundle2_name}[/bold cyan]")

    # Metadata tree
    meta_branch = root.add("[bold yellow]📋 Metadata[/bold yellow]")
    for key, val1 in comparison["metadata"]["bundle1"].items():
        val2 = comparison["metadata"]["bundle2"].get(key)
        if only_diff and val1 == val2:
            continue

        if val1 == val2:
            meta_branch.add(f"[green]{key}: {val1}[/green]")
        else:
            item_branch = meta_branch.add(f"[red]{key}[/red]")
            item_branch.add(f"[green]{bundle1_name}: {val1}[/green]")
            item_branch.add(f"[blue]{bundle2_name}: {val2}[/blue]")

    # Addons tree
    addons_branch = root.add("[bold yellow]🔌 Addon Versions[/bold yellow]")
    all_addons = set(comparison["addons"]["bundle1"].keys()) | set(comparison["addons"]["bundle2"].keys())
    for addon in sorted(all_addons):
        val1 = comparison["addons"]["bundle1"].get(addon)
        val2 = comparison["addons"]["bundle2"].get(addon)

        if only_diff and val1 == val2:
            continue

        if val1 is None:
            addons_branch.add(f"[cyan]{addon}: - → {val2} (added)[/cyan]")
        elif val2 is None:
            addons_branch.add(f"[red]{addon}: {val1} → - (removed)[/red]")
        elif val1 == val2:
            addons_branch.add(f"[green]{addon}: {val1}[/green]")
        else:
            addons_branch.add(f"[yellow]{addon}: {val1} → {val2}[/yellow]")

    # Dependencies tree
    deps_branch = root.add("[bold yellow]📦 Dependencies[/bold yellow]")
    all_platforms = set(comparison["dependencies"]["bundle1"].keys()) | set(
        comparison["dependencies"]["bundle2"].keys()
    )
    for platform in sorted(all_platforms):
        val1 = comparison["dependencies"]["bundle1"].get(platform)
        val2 = comparison["dependencies"]["bundle2"].get(platform)

        if only_diff and val1 == val2:
            continue

        if val1 is None:
            deps_branch.add(f"[cyan]{platform}: - → {val2} (added)[/cyan]")
        elif val2 is None:
            deps_branch.add(f"[red]{platform}: {val1} → - (removed)[/red]")
        elif val1 == val2:
            deps_branch.add(f"[green]{platform}: {val1}[/green]")
        else:
            deps_branch.add(f"[yellow]{platform}: {val1} → {val2}[/yellow]")

    # Settings tree (grouped by addon)
    settings_branch = root.add("[bold yellow]⚙️  Studio Settings[/bold yellow]")

    # Group settings by addon (first part before dot)
    settings_by_addon: dict[str, list[tuple[str, Any, Any]]] = {}
    all_keys = set(comparison["settings"]["bundle1"].keys()) | set(comparison["settings"]["bundle2"].keys())

    for key in all_keys:
        val1 = comparison["settings"]["bundle1"].get(key)
        val2 = comparison["settings"]["bundle2"].get(key)

        if only_diff and val1 == val2:
            continue

        addon = key.split(".")[0] if "." in key else key
        if addon not in settings_by_addon:
            settings_by_addon[addon] = []
        settings_by_addon[addon].append((key, val1, val2))

    # Render grouped settings
    for addon in sorted(settings_by_addon.keys()):
        addon_branch = settings_branch.add(f"[bold magenta]{addon}[/bold magenta]")
        for key, val1, val2 in settings_by_addon[addon]:
            if val1 is None:
                addon_branch.add(f"[cyan]{key}: - → {val2} (added)[/cyan]")
            elif val2 is None:
                addon_branch.add(f"[red]{key}: {val1} → - (removed)[/red]")
            elif val1 == val2:
                addon_branch.add(f"[green]{key}: {val1}[/green]")
            else:
                # Truncate long values
                val1_str = str(val1)
                val2_str = str(val2)
                if len(val1_str) > 50:
                    val1_str = val1_str[:47] + "..."
                if len(val2_str) > 50:
                    val2_str = val2_str[:47] + "..."
                addon_branch.add(f"[yellow]{key}: {val1_str} → {val2_str}[/yellow]")

    # Project settings tree (if present)
    if "project_settings" in comparison:
        project_branch = root.add("[bold yellow]🎯 Project Settings[/bold yellow]")
        project_by_addon: dict[str, list[tuple[str, Any, Any]]] = {}
        all_keys = set(comparison["project_settings"]["bundle1"].keys()) | set(
            comparison["project_settings"]["bundle2"].keys()
        )

        for key in all_keys:
            val1 = comparison["project_settings"]["bundle1"].get(key)
            val2 = comparison["project_settings"]["bundle2"].get(key)

            if only_diff and val1 == val2:
                continue

            addon = key.split(".")[0] if "." in key else key
            if addon not in project_by_addon:
                project_by_addon[addon] = []
            project_by_addon[addon].append((key, val1, val2))

        for addon in sorted(project_by_addon.keys()):
            addon_branch = project_branch.add(f"[bold magenta]{addon}[/bold magenta]")
            for key, val1, val2 in project_by_addon[addon]:
                if val1 is None:
                    addon_branch.add(f"[cyan]{key}: - → {val2} (added)[/cyan]")
                elif val2 is None:
                    addon_branch.add(f"[red]{key}: {val1} → - (removed)[/red]")
                elif val1 == val2:
                    addon_branch.add(f"[green]{key}: {val1}[/green]")
                else:
                    val1_str = str(val1)
                    val2_str = str(val2)
                    if len(val1_str) > 50:
                        val1_str = val1_str[:47] + "..."
                    if len(val2_str) > 50:
                        val2_str = val2_str[:47] + "..."
                    addon_branch.add(f"[yellow]{key}: {val1_str} → {val2_str}[/yellow]")

    # Anatomy tree (if present)
    if "anatomy" in comparison:
        anatomy_branch = root.add("[bold yellow]🏗️  Project Anatomy[/bold yellow]")
        all_keys = set(comparison["anatomy"]["bundle1"].keys()) | set(comparison["anatomy"]["bundle2"].keys())

        for key in sorted(all_keys):
            val1 = comparison["anatomy"]["bundle1"].get(key)
            val2 = comparison["anatomy"]["bundle2"].get(key)

            if only_diff and val1 == val2:
                continue

            if val1 is None:
                anatomy_branch.add(f"[cyan]{key}: - → {val2} (added)[/cyan]")
            elif val2 is None:
                anatomy_branch.add(f"[red]{key}: {val1} → - (removed)[/red]")
            elif val1 == val2:
                anatomy_branch.add(f"[green]{key}: {val1}[/green]")
            else:
                val1_str = str(val1)
                val2_str = str(val2)
                if len(val1_str) > 50:
                    val1_str = val1_str[:47] + "..."
                if len(val2_str) > 50:
                    val2_str = val2_str[:47] + "..."
                anatomy_branch.add(f"[yellow]{key}: {val1_str} → {val2_str}[/yellow]")

    console.print(root)


# ============================================================================
# Export Functions
# ============================================================================


def export_to_json(comparison: dict[str, Any], differences: dict[str, Any], output_file: Path) -> None:
    """
    Export comparison results to JSON file.

    Args:
        comparison: Full comparison results
        differences: Differences extracted from comparison
        output_file: Output file path
    """
    export_data = {
        "comparison": comparison,
        "differences": differences,
        "timestamp": datetime.now().isoformat(),
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)


def export_to_markdown(
    differences: dict[str, list[dict[str, Any]]],
    bundle1_name: str,
    bundle2_name: str,
    output_file: Path,
    project_name: str | None = None,
) -> None:
    """
    Export comparison results to Markdown file.

    Args:
        differences: Differences from get_differences()
        bundle1_name: Name of first bundle
        bundle2_name: Name of second bundle
        output_file: Output file path
        project_name: Project name if comparing project-specific settings
    """
    title = f"Bundle Comparison: {bundle1_name} vs {bundle2_name}"
    if project_name:
        title += f" (Project: {project_name})"

    lines = [
        f"# {title}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    # Metadata section
    if differences["metadata"]:
        lines.extend(
            [
                "## 📋 Bundle Metadata",
                "",
                f"| Setting | {bundle1_name} | {bundle2_name} | Status |",
                "|---------|---------|---------|--------|",
            ]
        )
        for item in differences["metadata"]:
            lines.append(f"| {item['key']} | {item['bundle1']} | {item['bundle2']} | {item['status']} |")
        lines.append("")

    # Addons section
    if differences["addons"]:
        lines.extend(
            [
                "## 🔌 Addon Versions",
                "",
                f"| Addon | {bundle1_name} | {bundle2_name} | Status |",
                "|-------|---------|---------|--------|",
            ]
        )
        for item in differences["addons"]:
            val1 = item["bundle1"] or "-"
            val2 = item["bundle2"] or "-"
            lines.append(f"| {item['key']} | {val1} | {val2} | {item['status']} |")
        lines.append("")

    # Dependencies section
    if differences["dependencies"]:
        lines.extend(
            [
                "## 📦 Dependency Packages",
                "",
                f"| Platform | {bundle1_name} | {bundle2_name} | Status |",
                "|----------|---------|---------|--------|",
            ]
        )
        for item in differences["dependencies"]:
            val1 = item["bundle1"] or "-"
            val2 = item["bundle2"] or "-"
            lines.append(f"| {item['key']} | {val1} | {val2} | {item['status']} |")
        lines.append("")

    # Settings section
    if differences["settings"]:
        lines.extend(
            [
                "## ⚙️  Studio Settings",
                "",
                f"| Setting | {bundle1_name} | {bundle2_name} | Status |",
                "|---------|---------|---------|--------|",
            ]
        )
        for item in differences["settings"]:
            val1 = str(item["bundle1"] or "-").replace("|", "\\|")
            val2 = str(item["bundle2"] or "-").replace("|", "\\|")
            lines.append(f"| {item['key']} | {val1} | {val2} | {item['status']} |")
        lines.append("")

    # Project settings section
    if differences.get("project_settings"):
        lines.extend(
            [
                "## 🎯 Project-Specific Settings",
                "",
                f"| Setting | {bundle1_name} | {bundle2_name} | Status |",
                "|---------|---------|---------|--------|",
            ]
        )
        for item in differences["project_settings"]:
            val1 = str(item["bundle1"] or "-").replace("|", "\\|")
            val2 = str(item["bundle2"] or "-").replace("|", "\\|")
            lines.append(f"| {item['key']} | {val1} | {val2} | {item['status']} |")
        lines.append("")

    # Anatomy section
    if differences.get("anatomy"):
        lines.extend(
            [
                "## 🏗️  Project Anatomy",
                "",
                f"| Setting | {bundle1_name} | {bundle2_name} | Status |",
                "|---------|---------|---------|--------|",
            ]
        )
        for item in differences["anatomy"]:
            val1 = str(item["bundle1"] or "-").replace("|", "\\|")
            val2 = str(item["bundle2"] or "-").replace("|", "\\|")
            lines.append(f"| {item['key']} | {val1} | {val2} | {item['status']} |")
        lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================================
# Interactive Bundle Selection
# ============================================================================


# ============================================================================
# CLI Command
# ============================================================================


# ============================================================================
# CLI Command
# ============================================================================


@click.command()
@click.argument("bundle1", required=False)
@click.argument("bundle2", required=False)
@click.option(
    "--only-diff",
    is_flag=True,
    help="Show only differences (exclude unchanged settings)",
)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum depth for nested settings comparison (default: unlimited)",
)
@click.option(
    "--view",
    type=click.Choice(["table", "tree", "both"], case_sensitive=False),
    default="both",
    help="Display view mode (default: both)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Export comparison to file (JSON or Markdown based on extension)",
)
@click.option(
    "--project",
    "-p",
    type=str,
    default=None,
    help="Project name for project-specific comparison (interactive if not specified)",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive mode: select bundles and project from list",
)
def analyze_bundles_cli(bundle1, bundle2, only_diff, max_depth, view, output, project, interactive):
    """
    Analyze and compare AYON bundles comprehensively.

    Fetches and compares all settings including addon versions, studio configurations,
    project-specific overrides, anatomy settings, and dependency packages between
    two AYON bundles.

    Arguments:
        BUNDLE1: Name of the first bundle (interactive if not specified)
        BUNDLE2: Name of the second bundle (interactive if not specified)

    Examples:

        # Interactive mode - select everything interactively
        gishant analyze-bundles

        # Compare two specific bundles with project
        gishant analyze-bundles dev_bundle staging_bundle --project Bollywoof

        # Show only differences in table view
        gishant analyze-bundles dev staging --only-diff --view table

        # Export comprehensive comparison to JSON
        gishant analyze-bundles dev staging --project Bollywoof --output analysis.json

        # Export to Markdown with tree view
        gishant analyze-bundles dev staging --view tree --output report.md

        # Limit comparison depth to 3 levels
        gishant analyze-bundles dev staging --max-depth 3
    """
    console = Console()

    try:
        # Display header
        console.print(
            Panel.fit(
                "[bold cyan]AYON Bundle Analysis Tool[/bold cyan]\nComprehensive comparison of AYON bundles including studio and project-specific settings",
                border_style="cyan",
            )
        )
        console.print()

        # Setup connection
        setup_ayon_connection(console)
        console.print()

        # Fetch all bundles
        bundles_data = fetch_all_bundles(console)
        console.print()

        # Determine bundle names
        if interactive or not bundle1 or not bundle2:
            bundle1_name, bundle2_name = interactive_bundle_selection(bundles_data, console)
        else:
            bundle1_name = bundle1
            bundle2_name = bundle2
            console.print(f"[green]✓ Using bundles: {bundle1_name} vs {bundle2_name}[/green]\n")

        # Get bundle data
        try:
            bundle1_data = get_bundle_by_name(bundles_data, bundle1_name)
            bundle2_data = get_bundle_by_name(bundles_data, bundle2_name)
        except BundleNotFoundError as err:
            console.print(f"[red]❌ {err}[/red]")
            console.print("\nAvailable bundles:")
            for bundle in bundles_data.get("bundles", []):
                console.print(f"  • {bundle['name']}")
            sys.exit(1)

        # Get bundle settings
        bundle1_settings = get_bundle_settings(bundle1_name, console)
        bundle2_settings = get_bundle_settings(bundle2_name, console)
        console.print()

        # Determine project for comparison
        project_name = None
        bundle1_project_settings = None
        bundle2_project_settings = None
        anatomy1 = None
        anatomy2 = None

        if interactive or not project:
            # Interactive project selection
            projects = get_all_projects(console)
            console.print()
            project_name = interactive_project_selection(projects, console)
        else:
            project_name = project
            console.print(f"[green]✓ Using project: {project_name}[/green]\n")

        # Get project-specific data if project selected
        if project_name:
            try:
                bundle1_project_settings = get_project_settings(bundle1_name, project_name, console)
                bundle2_project_settings = get_project_settings(bundle2_name, project_name, console)
                anatomy1 = get_project_anatomy(project_name, console)
                anatomy2 = get_project_anatomy(project_name, console)  # Same for both bundles
                console.print()
            except AYONConnectionError as err:
                console.print(f"[yellow]⚠ Warning: Could not fetch project data: {err}[/yellow]")
                console.print("[yellow]Continuing with studio-level comparison only[/yellow]\n")
                project_name = None

        # Compare settings
        console.print("[dim]Comparing settings...[/dim]")
        comparison = compare_settings(
            bundle1_data,
            bundle1_settings,
            bundle2_data,
            bundle2_settings,
            bundle1_project_settings=bundle1_project_settings,
            bundle2_project_settings=bundle2_project_settings,
            anatomy1=anatomy1,
            anatomy2=anatomy2,
            max_depth=max_depth,
        )

        differences = get_differences(comparison, only_diff=only_diff)
        console.print("[green]✓ Comparison complete[/green]\n")

        # Display results
        console.print("=" * 80)
        result_title = f"[bold green]ANALYSIS RESULTS[/bold green]\n{bundle1_name} vs {bundle2_name}"
        if project_name:
            result_title += f"\nProject: {project_name}"
        console.print(
            Panel.fit(
                result_title,
                border_style="green",
            )
        )
        console.print("=" * 80)
        console.print()

        if view in ("table", "both"):
            render_table_view(differences, bundle1_name, bundle2_name, console)

        if view in ("tree", "both"):
            render_tree_view(comparison, bundle1_name, bundle2_name, only_diff, console)

        # Export if requested
        if output:
            if output.suffix.lower() == ".json":
                export_to_json(comparison, differences, output)
                console.print(f"[green]✓ Exported to JSON: {output}[/green]")
            elif output.suffix.lower() in (".md", ".markdown"):
                export_to_markdown(differences, bundle1_name, bundle2_name, output, project_name=project_name)
                console.print(f"[green]✓ Exported to Markdown: {output}[/green]")
            else:
                console.print(f"[yellow]⚠ Unknown extension '{output.suffix}', exporting as JSON[/yellow]")
                export_to_json(comparison, differences, output)
                console.print(f"[green]✓ Exported to: {output}[/green]")

        # Summary
        console.print("\n" + "=" * 80)
        total_diffs = sum(
            1 for category in differences.values() for item in category if item.get("status") not in ("unchanged", None)
        )
        if only_diff:
            console.print(f"[yellow]Showing {total_diffs} differences[/yellow]")
        else:
            total_items = sum(len(category) for category in differences.values())
            console.print(f"[yellow]Showing {total_items} items ({total_diffs} differences)[/yellow]")

        if max_depth:
            console.print(f"[dim]Comparison depth limited to {max_depth} levels[/dim]")

    except AYONConnectionError as err:
        console.print(f"\n[bold red]❌ Connection Error:[/bold red] {err}")
        console.print("\n[yellow]Please ensure:[/yellow]")
        console.print("  1. AYON server is running and accessible")
        console.print("  2. AYON_SERVER_URL and AYON_API_KEY are set in your .env file")
        console.print("  3. rdo-ayon-utils is available at /home/gisi/dev/repos/rdo-ayon-utils")
        sys.exit(1)

    except BundleNotFoundError as err:
        console.print(f"\n[bold red]❌ Bundle Error:[/bold red] {err}")
        sys.exit(1)

    except KeyboardInterrupt:
        console.print("\n\n[yellow]⚠ Operation cancelled by user[/yellow]")
        sys.exit(130)

    except Exception as err:
        console.print(f"\n[bold red]❌ Unexpected Error:[/bold red] {err}")
        console.print("\n[dim]Enable verbose mode for more details[/dim]")
        import traceback

        console.print(f"\n[dim]{traceback.format_exc()}[/dim]")
        sys.exit(1)


if __name__ == "__main__":
    analyze_bundles_cli()
