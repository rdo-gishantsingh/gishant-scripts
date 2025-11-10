"""Utility script for inspecting AYON bundle metadata.

The script connects to an AYON server using the ayon-python-api package
and prints details about every available bundle in a human-friendly layout.
Connection details are read from the standard AYON environment variables, but
can be overridden through the command-line options.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import ayon_api
import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

console = Console()
logger = logging.getLogger("check_bundles")


def configure_logging(verbose: bool) -> None:
    """Configure the root logger."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def apply_credentials(
    server_url: str | None,
    api_key: str | None,
    username: str | None,
    password: str | None,
) -> None:
    """Override AYON connection credentials using CLI arguments."""
    if server_url:
        os.environ["AYON_SERVER_URL"] = server_url
    if api_key:
        os.environ["AYON_API_KEY"] = api_key
    if username:
        os.environ["AYON_USERNAME"] = username
    if password:
        os.environ["AYON_PASSWORD"] = password


def fetch_bundles() -> dict[str, Any]:
    """Retrieve bundle payload from the AYON server."""
    logger.debug("Requesting bundle list from AYON API.")
    return ayon_api.get_bundles()


def filter_bundles(
    bundles: list[dict[str, Any]],
    filter_production: bool,
    filter_staging: bool,
    filter_dev: bool,
    filter_name: str | None,
) -> list[dict[str, Any]]:
    """Filter bundles based on criteria."""
    filtered = bundles

    # Apply type filters
    if filter_production or filter_staging or filter_dev:
        filtered = [
            b
            for b in filtered
            if (filter_production and b.get("isProduction"))
            or (filter_staging and b.get("isStaging"))
            or (filter_dev and b.get("isDev"))
        ]

    # Apply name filter
    if filter_name:
        filter_lower = filter_name.lower()
        filtered = [b for b in filtered if filter_lower in b.get("name", "").lower()]

    return filtered


def sort_bundles(
    bundles: list[dict[str, Any]],
    sort_by: str,
    reverse: bool,
) -> list[dict[str, Any]]:
    """Sort bundles by specified field."""
    if sort_by == "name":
        key_func = lambda b: b.get("name", "").lower()
    elif sort_by == "created":
        key_func = lambda b: b.get("createdAt", "")
    elif sort_by == "updated":
        key_func = lambda b: b.get("updatedAt", "")
    else:
        key_func = lambda b: b.get("name", "").lower()

    return sorted(bundles, key=key_func, reverse=reverse)


def format_flag(value: Any) -> str:
    """Convert boolean-like values to yes/no markers."""
    if isinstance(value, bool):
        return "[green]Yes[/green]" if value else "[dim]No[/dim]"
    if value is None:
        return "[dim]—[/dim]"
    return str(value)


def get_bundle_status_emoji(bundle: dict[str, Any]) -> str:
    """Return an emoji representing bundle status."""
    if bundle.get("isProduction"):
        return "🟢"
    if bundle.get("isStaging"):
        return "🟡"
    if bundle.get("isDev"):
        return "🔵"
    return "⚪"


def display_tree_format(
    payload: dict[str, Any],
    bundles: list[dict[str, Any]],
    show_dev_paths: bool,
) -> None:
    """Display bundles in tree format using rich."""
    # Display summary panel
    summary_items = []
    if "productionBundle" in payload:
        summary_items.append(f"Production: [bold]{payload['productionBundle'] or '—'}[/bold]")
    if "stagingBundle" in payload:
        summary_items.append(f"Staging: [bold]{payload['stagingBundle'] or '—'}[/bold]")
    if "devBundle" in payload:
        summary_items.append(f"Development: [bold]{payload['devBundle'] or '—'}[/bold]")

    if summary_items:
        console.print(
            Panel(
                "\n".join(summary_items),
                title="[bold cyan]Active Bundles[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
            )
        )
        console.print()

    if not bundles:
        console.print("[yellow]No bundles match the specified filters.[/yellow]")
        return

    # Display bundles as tree
    tree = Tree(f"[bold]Found {len(bundles)} bundle{'s' if len(bundles) != 1 else ''}[/bold]")

    for bundle in bundles:
        emoji = get_bundle_status_emoji(bundle)
        name = bundle.get("name", "<unnamed>")
        bundle_node = tree.add(f"{emoji} [bold cyan]{name}[/bold cyan]")

        # Metadata
        meta_node = bundle_node.add("[bold]Metadata[/bold]")
        meta_node.add(f"Production: {format_flag(bundle.get('isProduction'))}")
        meta_node.add(f"Staging: {format_flag(bundle.get('isStaging'))}")
        meta_node.add(f"Development: {format_flag(bundle.get('isDev'))}")

        if bundle.get("installerVersion"):
            meta_node.add(f"Installer: [yellow]{bundle['installerVersion']}[/yellow]")
        if bundle.get("activeUser"):
            meta_node.add(f"Active dev user: [magenta]{bundle['activeUser']}[/magenta]")
        if bundle.get("createdAt"):
            meta_node.add(f"Created: [dim]{bundle['createdAt']}[/dim]")
        if bundle.get("updatedAt"):
            meta_node.add(f"Updated: [dim]{bundle['updatedAt']}[/dim]")

        # Addons
        addons = bundle.get("addons") or {}
        if addons:
            addon_node = bundle_node.add(f"[bold]Addons[/bold] ({len(addons)})")
            dev_info = bundle.get("addonDevelopment") or {}

            for addon_name in sorted(addons):
                version = addons[addon_name]
                addon_dev = dev_info.get(addon_name, {})

                suffix_parts = []
                if addon_dev.get("enabled"):
                    suffix_parts.append("[blue]dev enabled[/blue]")
                if show_dev_paths and addon_dev.get("path"):
                    suffix_parts.append(f"[dim]{addon_dev['path']}[/dim]")

                suffix = f" ({' | '.join(suffix_parts)})" if suffix_parts else ""
                addon_node.add(f"[green]{addon_name}[/green]: {version}{suffix}")
        else:
            bundle_node.add("[dim]Addons: none[/dim]")

        # Dependencies
        deps = bundle.get("dependencyPackages") or {}
        if deps:
            dep_node = bundle_node.add(f"[bold]Dependencies[/bold] ({len(deps)})")
            for platform in sorted(deps):
                package = deps[platform] or "—"
                dep_node.add(f"{platform}: [yellow]{package}[/yellow]")
        else:
            bundle_node.add("[dim]Dependencies: none[/dim]")

    console.print(tree)


def display_table_format(
    payload: dict[str, Any],
    bundles: list[dict[str, Any]],
    show_dev_paths: bool,
) -> None:
    """Display bundles in table format using rich."""
    if not bundles:
        console.print("[yellow]No bundles match the specified filters.[/yellow]")
        return

    table = Table(
        title=f"[bold]AYON Bundles ({len(bundles)})[/bold]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Status", justify="center", style="bold", width=6)
    table.add_column("Name", style="cyan")
    table.add_column("Addons", justify="right")
    table.add_column("Installer", style="yellow")
    table.add_column("Prod", justify="center", width=5)
    table.add_column("Stg", justify="center", width=4)
    table.add_column("Dev", justify="center", width=4)

    for bundle in bundles:
        emoji = get_bundle_status_emoji(bundle)
        name = bundle.get("name", "<unnamed>")
        addons = bundle.get("addons") or {}
        addon_count = str(len(addons))
        installer = bundle.get("installerVersion") or "—"

        is_prod = "✓" if bundle.get("isProduction") else ""
        is_stg = "✓" if bundle.get("isStaging") else ""
        is_dev = "✓" if bundle.get("isDev") else ""

        table.add_row(emoji, name, addon_count, installer, is_prod, is_stg, is_dev)

    console.print(table)


def display_compact_format(
    payload: dict[str, Any],
    bundles: list[dict[str, Any]],
    show_dev_paths: bool,
) -> None:
    """Display bundles in compact format."""
    # Summary
    summary_parts = []
    if "productionBundle" in payload:
        prod = payload["productionBundle"] or "—"
        summary_parts.append(f"[green]Prod:[/green] {prod}")
    if "stagingBundle" in payload:
        stg = payload["stagingBundle"] or "—"
        summary_parts.append(f"[yellow]Stg:[/yellow] {stg}")

    if summary_parts:
        console.print(" | ".join(summary_parts))
        console.print()

    if not bundles:
        console.print("[yellow]No bundles match the specified filters.[/yellow]")
        return

    console.print(f"[bold]Found {len(bundles)} bundle{'s' if len(bundles) != 1 else ''}:[/bold]\n")

    for bundle in bundles:
        emoji = get_bundle_status_emoji(bundle)
        name = bundle.get("name", "<unnamed>")
        addons = bundle.get("addons") or {}
        addon_count = len(addons)

        flags = []
        if bundle.get("isProduction"):
            flags.append("[green]prod[/green]")
        if bundle.get("isStaging"):
            flags.append("[yellow]stg[/yellow]")
        if bundle.get("isDev"):
            flags.append("[blue]dev[/blue]")

        flag_str = f" [{', '.join(flags)}]" if flags else ""

        console.print(
            f"{emoji} [bold cyan]{name}[/bold cyan]{flag_str} — {addon_count} addon{'s' if addon_count != 1 else ''}"
        )


@click.command()
@click.option(
    "--server-url",
    envvar="AYON_SERVER_URL",
    help="AYON server URL.",
)
@click.option(
    "--api-key",
    envvar="AYON_API_KEY",
    help="AYON API key.",
)
@click.option(
    "--username",
    envvar="AYON_USERNAME",
    help="AYON username.",
)
@click.option(
    "--password",
    envvar="AYON_PASSWORD",
    help="AYON password.",
)
@click.option(
    "--show-dev-paths",
    is_flag=True,
    help="Include development addon paths when available.",
)
@click.option(
    "--filter-production",
    is_flag=True,
    help="Show only production bundles.",
)
@click.option(
    "--filter-staging",
    is_flag=True,
    help="Show only staging bundles.",
)
@click.option(
    "--filter-dev",
    is_flag=True,
    help="Show only development bundles.",
)
@click.option(
    "--filter-name",
    help="Filter bundles by name (case-insensitive substring match).",
)
@click.option(
    "--sort-by",
    type=click.Choice(["name", "created", "updated"], case_sensitive=False),
    default="name",
    help="Sort bundles by field.",
)
@click.option(
    "--reverse",
    is_flag=True,
    help="Reverse sort order.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["tree", "table", "compact"], case_sensitive=False),
    default="tree",
    help="Output format style.",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable debug logging.",
)
def main(
    server_url: str | None,
    api_key: str | None,
    username: str | None,
    password: str | None,
    show_dev_paths: bool,
    filter_production: bool,
    filter_staging: bool,
    filter_dev: bool,
    filter_name: str | None,
    sort_by: str,
    reverse: bool,
    output_format: str,
    verbose: bool,
) -> None:
    """Fetch and display AYON bundle information with filtering and sorting."""
    configure_logging(verbose)
    apply_credentials(server_url, api_key, username, password)

    try:
        payload = fetch_bundles()
    except Exception as err:
        console.print(f"[bold red]Error:[/bold red] Failed to fetch bundles: {err}")
        sys.exit(1)

    bundles = filter_bundles(
        payload.get("bundles", []),
        filter_production,
        filter_staging,
        filter_dev,
        filter_name,
    )

    bundles = sort_bundles(bundles, sort_by, reverse)

    if output_format == "tree":
        display_tree_format(payload, bundles, show_dev_paths)
    elif output_format == "table":
        display_table_format(payload, bundles, show_dev_paths)
    else:
        display_compact_format(payload, bundles, show_dev_paths)


if __name__ == "__main__":
    main()
