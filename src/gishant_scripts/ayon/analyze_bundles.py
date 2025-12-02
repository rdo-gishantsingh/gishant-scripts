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
# Constants
# ============================================================================

STATUS_COLORS = {
    "unchanged": "dim",
    "changed": "yellow",
    "added": "cyan",
    "removed": "red",
}


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
# Rich TUI Display
# ============================================================================


def render_table_view(
    differences: dict[str, list[dict[str, Any]]],
    bundle1_name: str,
    bundle2_name: str,
    console: Console,
) -> None:
    """Render comparison results in table view."""

    def render_section(title: str, items: list[dict[str, Any]]) -> None:
        """Render a single section as a table."""
        if not items:
            return

        table = Table(title=title, show_header=True, header_style="bold cyan", title_style="bold")
        table.add_column("Setting", style="white", no_wrap=False, max_width=50)
        table.add_column(bundle1_name, style="green", max_width=35)
        table.add_column(bundle2_name, style="blue", max_width=35)
        table.add_column("Status", width=10)

        for item in items:
            status = item["status"]
            style = get_status_style(status)
            table.add_row(
                item["key"],
                format_value(item["bundle1"]),
                format_value(item["bundle2"]),
                f"[{style}]{status}[/{style}]",
            )

        console.print(table)
        console.print()

    render_section("📋 Bundle Metadata", differences.get("metadata", []))
    render_section("🔌 Addon Versions", differences.get("addons", []))
    render_section("📦 Dependency Packages", differences.get("dependencies", []))
    render_section("⚙️  Studio Settings", differences.get("settings", []))
    render_section("🎯 Project Settings", differences.get("project_settings", []))
    render_section("🏗️  Anatomy", differences.get("anatomy", []))


def render_tree_view(
    comparison: dict[str, Any],
    bundle1_name: str,
    bundle2_name: str,
    only_diff: bool,
    console: Console,
) -> None:
    """Render comparison results in hierarchical tree view."""
    root = Tree(f"[bold cyan]Bundle Comparison: {bundle1_name} vs {bundle2_name}[/bold cyan]")

    def add_diff_item(branch: Tree, key: str, val1: Any, val2: Any) -> None:
        """Add a difference item to a tree branch."""
        if val1 is None:
            branch.add(f"[cyan]+ {key}: {val2}[/cyan]")
        elif val2 is None:
            branch.add(f"[red]- {key}: {val1}[/red]")
        elif val1 == val2:
            branch.add(f"[dim]{key}: {val1}[/dim]")
        else:
            v1 = format_value(val1)
            v2 = format_value(val2)
            branch.add(f"[yellow]~ {key}: {v1} → {v2}[/yellow]")

    def add_section(
        title: str,
        data1: dict[str, Any],
        data2: dict[str, Any],
        group_by_prefix: bool = False,
    ) -> None:
        """Add a section to the tree."""
        all_keys = set(data1.keys()) | set(data2.keys())
        if not all_keys:
            return

        # Filter if only_diff
        if only_diff:
            all_keys = {k for k in all_keys if data1.get(k) != data2.get(k)}
            if not all_keys:
                return

        branch = root.add(f"[bold yellow]{title}[/bold yellow]")

        if group_by_prefix:
            # Group by addon (first part before dot)
            groups: dict[str, list[str]] = {}
            for key in sorted(all_keys):
                prefix = key.split(".")[0] if "." in key else key
                groups.setdefault(prefix, []).append(key)

            for prefix in sorted(groups.keys()):
                sub_branch = branch.add(f"[magenta]{prefix}[/magenta]")
                for key in groups[prefix]:
                    val1 = data1.get(key)
                    val2 = data2.get(key)
                    if not only_diff or val1 != val2:
                        add_diff_item(sub_branch, key, val1, val2)
        else:
            for key in sorted(all_keys):
                val1 = data1.get(key)
                val2 = data2.get(key)
                if not only_diff or val1 != val2:
                    add_diff_item(branch, key, val1, val2)

    # Render sections
    add_section("📋 Metadata", comparison["metadata"]["bundle1"], comparison["metadata"]["bundle2"])
    add_section("🔌 Addons", comparison["addons"]["bundle1"], comparison["addons"]["bundle2"])
    add_section("📦 Dependencies", comparison["dependencies"]["bundle1"], comparison["dependencies"]["bundle2"])
    add_section("⚙️  Studio Settings", comparison["settings"]["bundle1"], comparison["settings"]["bundle2"], group_by_prefix=True)

    if "project_settings" in comparison:
        add_section(
            "🎯 Project Settings",
            comparison["project_settings"]["bundle1"],
            comparison["project_settings"]["bundle2"],
            group_by_prefix=True,
        )

    if "anatomy" in comparison:
        add_section("🏗️  Anatomy", comparison["anatomy"]["bundle1"], comparison["anatomy"]["bundle2"])

    console.print(root)


# ============================================================================
# Summary
# ============================================================================


def print_summary(differences: dict[str, list[dict[str, Any]]], only_diff: bool, console: Console) -> None:
    """Print a summary of the comparison."""
    counts = {"unchanged": 0, "changed": 0, "added": 0, "removed": 0}

    for items in differences.values():
        for item in items:
            status = item.get("status", "unchanged")
            counts[status] = counts.get(status, 0) + 1

    total = sum(counts.values())
    diff_count = counts["changed"] + counts["added"] + counts["removed"]

    parts = []
    if counts["changed"]:
        parts.append(f"[yellow]{counts['changed']} changed[/yellow]")
    if counts["added"]:
        parts.append(f"[cyan]{counts['added']} added[/cyan]")
    if counts["removed"]:
        parts.append(f"[red]{counts['removed']} removed[/red]")
    if counts["unchanged"] and not only_diff:
        parts.append(f"[dim]{counts['unchanged']} unchanged[/dim]")

    summary = ", ".join(parts) if parts else "[dim]No differences[/dim]"

    if only_diff:
        console.print(f"\n[bold]Summary:[/bold] {diff_count} differences found")
    else:
        console.print(f"\n[bold]Summary:[/bold] {total} items compared, {diff_count} differences")
    console.print(f"  {summary}")


# ============================================================================
# Export Functions
# ============================================================================


def export_to_json(comparison: dict[str, Any], differences: dict[str, Any], output_file: Path) -> None:
    """Export comparison results to JSON file."""
    export_data = {
        "comparison": comparison,
        "differences": differences,
        "timestamp": datetime.now().isoformat(),
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)


def export_to_markdown(
    differences: dict[str, list[dict[str, Any]]],
    bundle1_name: str,
    bundle2_name: str,
    output_file: Path,
    project_name: str | None = None,
) -> None:
    """Export comparison results to Markdown file."""
    title = f"Bundle Comparison: {bundle1_name} vs {bundle2_name}"
    if project_name:
        title += f" (Project: {project_name})"

    lines = [
        f"# {title}",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]

    sections = [
        ("📋 Bundle Metadata", "metadata"),
        ("🔌 Addon Versions", "addons"),
        ("📦 Dependency Packages", "dependencies"),
        ("⚙️  Studio Settings", "settings"),
        ("🎯 Project Settings", "project_settings"),
        ("🏗️  Anatomy", "anatomy"),
    ]

    for section_title, key in sections:
        items = differences.get(key, [])
        if not items:
            continue

        lines.extend([
            f"## {section_title}",
            "",
            f"| Setting | {bundle1_name} | {bundle2_name} | Status |",
            "|---------|---------|---------|--------|",
        ])

        for item in items:
            val1 = str(item["bundle1"] if item["bundle1"] is not None else "-").replace("|", "\\|")
            val2 = str(item["bundle2"] if item["bundle2"] is not None else "-").replace("|", "\\|")
            lines.append(f"| {item['key']} | {val1} | {val2} | {item['status']} |")

        lines.append("")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================================
# CLI Command
# ============================================================================


@click.command()
@click.argument("bundle1", required=False)
@click.argument("bundle2", required=False)
@click.option("--only-diff", is_flag=True, help="Show only differences")
@click.option("--max-depth", type=int, default=None, help="Maximum depth for nested settings comparison")
@click.option(
    "--view",
    type=click.Choice(["table", "tree", "both"], case_sensitive=False),
    default="table",
    help="Display view mode (default: table)",
)
@click.option("--output", "-o", type=click.Path(path_type=Path), help="Export to file (JSON or Markdown)")
@click.option("--project", "-p", type=str, default=None, help="Project name for project-specific comparison")
@click.option("--addon", "-a", type=str, multiple=True, help="Filter to specific addon(s)")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode: select bundles and project from list")
@click.option("--local", is_flag=True, help="Use local environment")
@click.option("--dev", is_flag=True, help="Use dev environment")
def analyze_bundles_cli(bundle1, bundle2, only_diff, max_depth, view, output, project, addon, interactive, local, dev):
    """
    Compare two AYON bundles.

    Compares addon versions, studio settings, project settings, and anatomy
    between two bundles.

    \b
    Examples:
        gishant analyze-bundles                          # Interactive mode
        gishant analyze-bundles dev staging              # Compare specific bundles
        gishant analyze-bundles dev staging --only-diff  # Show only differences
        gishant analyze-bundles dev staging -p Project   # Include project settings
        gishant analyze-bundles dev staging -a maya      # Filter to maya addon
        gishant analyze-bundles dev staging -o diff.md   # Export to markdown
    """
    console = Console()
    addon_filter = list(addon) if addon else None

    try:
        # Header
        console.print()
        console.print("[bold cyan]AYON Bundle Analyzer[/bold cyan]")
        console.print()

        # Connect
        setup_ayon_connection(console, use_local=local, use_dev=dev)

        # Fetch bundles
        bundles_data = fetch_all_bundles(console)

        # Select bundles
        if interactive or not bundle1 or not bundle2:
            bundle1_name, bundle2_name = interactive_bundle_selection(bundles_data, console)
        else:
            bundle1_name, bundle2_name = bundle1, bundle2

        # Validate bundles exist
        try:
            bundle1_data = get_bundle_by_name(bundles_data, bundle1_name)
            bundle2_data = get_bundle_by_name(bundles_data, bundle2_name)
        except BundleNotFoundError as err:
            console.print(f"\n[red]Error:[/red] {err}")
            console.print("\nAvailable bundles:")
            for b in bundles_data.get("bundles", []):
                console.print(f"  • {b['name']}")
            sys.exit(1)

        # Fetch settings
        bundle1_settings = get_bundle_settings(bundle1_name, console)
        bundle2_settings = get_bundle_settings(bundle2_name, console)

        # Project settings (optional)
        project_name = None
        bundle1_project_settings = None
        bundle2_project_settings = None
        anatomy1 = anatomy2 = None

        if interactive or project:
            if interactive and not project:
                projects = get_all_projects(console)
                project_name = interactive_project_selection(projects, console)
            else:
                project_name = project

            if project_name:
                try:
                    bundle1_project_settings = get_project_settings(bundle1_name, project_name, console)
                    bundle2_project_settings = get_project_settings(bundle2_name, project_name, console)
                    anatomy1 = get_project_anatomy(project_name, console)
                    anatomy2 = get_project_anatomy(project_name, console)
                except AYONConnectionError as err:
                    console.print(f"[yellow]Warning:[/yellow] Could not fetch project data: {err}")
                    project_name = None

        # Compare
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
        differences = get_differences(comparison, only_diff=only_diff, addon_filter=addon_filter)

        # Display header
        console.print()
        header_parts = [f"[bold]{bundle1_name}[/bold] vs [bold]{bundle2_name}[/bold]"]
        if project_name:
            header_parts.append(f"Project: {project_name}")
        if addon_filter:
            header_parts.append(f"Filter: {', '.join(addon_filter)}")

        console.print(Panel(" | ".join(header_parts), style="green"))
        console.print()

        # Render results
        if view in ("table", "both"):
            render_table_view(differences, bundle1_name, bundle2_name, console)

        if view in ("tree", "both"):
            render_tree_view(comparison, bundle1_name, bundle2_name, only_diff, console)

        # Summary
        print_summary(differences, only_diff, console)

        # Export
        if output:
            if output.suffix.lower() == ".json":
                export_to_json(comparison, differences, output)
            elif output.suffix.lower() in (".md", ".markdown"):
                export_to_markdown(differences, bundle1_name, bundle2_name, output, project_name=project_name)
            else:
                export_to_json(comparison, differences, output)
            console.print(f"\n[green]✓[/green] Exported to {output}")

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


if __name__ == "__main__":
    analyze_bundles_cli()
