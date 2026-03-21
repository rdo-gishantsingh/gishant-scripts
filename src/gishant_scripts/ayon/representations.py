"""CLI command for fetching representations using AYON API.

This module provides a typer command with rich UI for fetching and displaying
representations.
"""

import json
import os
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from typing import Literal

from gishant_scripts.ayon.common import AYONConnectionError, setup_ayon_connection
from gishant_scripts.ayon.get_representation import get_representation

try:
    import ayon_api
except ImportError:
    ayon_api = None

try:
    from ayon_core.pipeline import Anatomy
    from ayon_core.pipeline.load import (
        get_representation_path_with_anatomy,
        InvalidRepresentationContext,
    )

    AYON_CORE_AVAILABLE = True
except ImportError:
    AYON_CORE_AVAILABLE = False
    Anatomy = None
    get_representation_path_with_anatomy = None
    InvalidRepresentationContext = None

console = Console()


def _resolve_representation_path(representation, project_name, debug=False):
    """Resolve representation path using AYON anatomy.

    Args:
        representation: The representation dict from AYON API
        project_name: Project name for anatomy resolution
        debug: If True, print debug information

    Returns:
        str: Resolved file path, or fallback to hardcoded path if resolution fails
    """
    if not AYON_CORE_AVAILABLE or Anatomy is None or get_representation_path_with_anatomy is None:
        # Fallback to hardcoded path if ayon_core is not available
        if debug:
            console.print("[yellow]DEBUG: ayon_core not available, using hardcoded path[/yellow]")
        return representation.get("attrib", {}).get("path", "N/A")

    try:
        anatomy = Anatomy(project_name)
        work_root = str(anatomy.roots.get("work"))

        if debug:
            console.print(f"[cyan]DEBUG: Work root from anatomy: {work_root}[/cyan]")
            console.print(f"[cyan]DEBUG: Anatomy roots type: {type(anatomy.roots)}[/cyan]")
            console.print(f"[cyan]DEBUG: Anatomy roots value: {anatomy.roots}[/cyan]")

        # Try to resolve using template first
        try:
            resolved_path = get_representation_path_with_anatomy(representation, anatomy)
            resolved_path_str = str(resolved_path).replace("\\", "/")
            if debug:
                console.print(f"[cyan]DEBUG: Template resolution result: {resolved_path_str}[/cyan]")
        except Exception as template_error:
            # If template resolution fails, use hardcoded path
            if debug:
                console.print(f"[yellow]DEBUG: Template resolution failed: {template_error}[/yellow]")
            resolved_path_str = representation.get("attrib", {}).get("path", "N/A")
            if debug:
                console.print(f"[cyan]DEBUG: Using hardcoded path: {resolved_path_str}[/cyan]")

        # Replace any root prefix with the actual work root
        if resolved_path_str != "N/A" and work_root:
            if debug:
                console.print(f"[cyan]DEBUG: Before root replacement: {resolved_path_str}[/cyan]")
                console.print(f"[cyan]DEBUG: Work root to use: {work_root}[/cyan]")

            # Check if path starts with any known root value from anatomy
            roots = anatomy.roots
            if isinstance(roots, dict):
                # Multi-root setup: check all root values
                if debug:
                    console.print(f"[cyan]DEBUG: Multi-root setup detected, checking {len(roots)} roots[/cyan]")
                for root_name, root_item in roots.items():
                    root_value = str(root_item)
                    if debug:
                        console.print(f"[cyan]DEBUG: Checking root '{root_name}': {root_value}[/cyan]")
                    if root_value and resolved_path_str.startswith(root_value):
                        # Replace with work root
                        if debug:
                            console.print(
                                f"[cyan]DEBUG: Found matching root '{root_name}', replacing {root_value} with {work_root}[/cyan]"
                            )
                        resolved_path_str = resolved_path_str.replace(root_value, work_root, 1)
                        break
            else:
                # Single root setup: check the root value directly
                root_value = str(roots)
                if debug:
                    console.print(f"[cyan]DEBUG: Single root setup, root value: {root_value}[/cyan]")
                if root_value and resolved_path_str.startswith(root_value):
                    if debug:
                        console.print(
                            f"[cyan]DEBUG: Found matching root, replacing {root_value} with {work_root}[/cyan]"
                        )
                    resolved_path_str = resolved_path_str.replace(root_value, work_root, 1)

            # If path still doesn't start with work root, try to detect and replace root prefix
            # This handles cases like /shows, /projects, etc.
            if not resolved_path_str.startswith(work_root) and resolved_path_str.startswith("/"):
                if debug:
                    console.print(
                        f"[cyan]DEBUG: Path doesn't start with work root, attempting prefix replacement[/cyan]"
                    )
                # Extract first path segment (e.g., /shows, /projects)
                path_parts = resolved_path_str.split("/", 2)
                if len(path_parts) >= 2:
                    root_prefix = "/" + path_parts[1]  # e.g., "/shows"
                    if debug:
                        console.print(f"[cyan]DEBUG: Detected root prefix: {root_prefix}[/cyan]")
                        console.print(f"[cyan]DEBUG: Replacing {root_prefix} with {work_root}[/cyan]")
                    # Replace first path segment with work root
                    resolved_path_str = resolved_path_str.replace(root_prefix, work_root, 1)

            if debug:
                console.print(f"[cyan]DEBUG: After root replacement: {resolved_path_str}[/cyan]")

        return resolved_path_str
    except Exception as e:
        if debug:
            console.print(f"[red]DEBUG: Exception in path resolution: {e}[/red]")
            import traceback

            console.print(f"[red]DEBUG: Traceback: {traceback.format_exc()}[/red]")

        # Fallback: try to manually resolve hardcoded path
        hardcoded_path = representation.get("attrib", {}).get("path", "N/A")
        if hardcoded_path != "N/A":
            try:
                anatomy = Anatomy(project_name)
                work_root = str(anatomy.roots.get("work"))
                if debug:
                    console.print(f"[cyan]DEBUG: Fallback - work root: {work_root}[/cyan]")
                    console.print(f"[cyan]DEBUG: Fallback - hardcoded path: {hardcoded_path}[/cyan]")
                if work_root and hardcoded_path.startswith("/"):
                    # Try to replace root prefix
                    path_parts = hardcoded_path.split("/", 2)
                    if len(path_parts) >= 2:
                        root_prefix = "/" + path_parts[1]
                        if debug:
                            console.print(f"[cyan]DEBUG: Fallback - replacing {root_prefix} with {work_root}[/cyan]")
                        return hardcoded_path.replace(root_prefix, work_root, 1)
            except Exception as fallback_error:
                if debug:
                    console.print(f"[yellow]DEBUG: Fallback resolution failed: {fallback_error}[/yellow]")

        # Final fallback to hardcoded path
        if hardcoded_path == "N/A":
            console.print(f"[yellow]Warning: Could not resolve path: {e}[/yellow]")
        return hardcoded_path


def _format_representation_as_dict(
    representation, project_name, folder_path, product_name, representation_name, version_info=None, resolved_path=None
):
    """Format representation data as a structured dictionary.

    Args:
        representation: The representation dict from AYON API
        project_name: Project name
        folder_path: Folder path
        product_name: Product name
        representation_name: Representation name
        version_info: Optional version number
        resolved_path: Optional resolved file path

    Returns:
        dict: Formatted representation data
    """
    # Extract all fields
    representation_id = representation.get("id", "N/A")
    attrib = representation.get("attrib", {})
    context = representation.get("context") or {}
    data = representation.get("data")
    files = representation.get("files")
    status = representation.get("status")
    tags = representation.get("tags") or []

    # Normalize data
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        data = {"value": data}

    # Normalize files
    if files is None:
        files = []
    elif not isinstance(files, list):
        files = [files] if files else []

    # Format files list
    formatted_files = []
    for file_info in files:
        if isinstance(file_info, str):
            formatted_files.append({"path": file_info})
        elif isinstance(file_info, dict):
            formatted_files.append(
                {
                    "path": file_info.get("path", file_info.get("name", "N/A")),
                    "name": file_info.get(
                        "name", os.path.basename(file_info.get("path", "")) if file_info.get("path") else "N/A"
                    ),
                    "size": file_info.get("size"),
                    "id": file_info.get("id"),
                }
            )
        else:
            formatted_files.append({"value": str(file_info)})

    # Build structured dictionary
    result = {
        "id": representation_id,
        "project": project_name,
        "folder": folder_path,
        "product": product_name,
        "representation": representation_name,
        "version": version_info if version_info else representation.get("versionId", "N/A"),
        "status": status,
        "tags": tags if tags else [],
        "attributes": {k: v for k, v in attrib.items()} if attrib else {},
        "context": context if context else {},
        "data": data if data else {},
        "files": formatted_files if formatted_files else [],
    }

    # Add resolved path if available
    if resolved_path and resolved_path != "N/A":
        result["resolved_path"] = resolved_path
        hardcoded_path = attrib.get("path")
        if hardcoded_path and hardcoded_path != resolved_path:
            result["hardcoded_path"] = hardcoded_path

    return result


def _print_dict_formatted(data_dict):
    """Print dictionary in a nicely formatted way using rich."""
    console.print("\n[bold cyan]Representation Data:[/bold cyan]\n")

    def _print_dict(d, indent=0, prefix=""):
        """Recursively print dictionary with indentation."""
        indent_str = "  " * indent
        for key, value in d.items():
            if isinstance(value, dict):
                console.print(f"{indent_str}[cyan]{key}:[/cyan]")
                _print_dict(value, indent + 1)
            elif isinstance(value, list):
                console.print(f"{indent_str}[cyan]{key}:[/cyan]")
                if not value:
                    console.print(f"{indent_str}  [dim](empty list)[/dim]")
                else:
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            console.print(f"{indent_str}  [yellow][{i}]:[/yellow]")
                            _print_dict(item, indent + 2)
                        else:
                            console.print(f"{indent_str}  [yellow][{i}]:[/yellow] {item}")
            else:
                value_str = str(value) if value is not None else "[dim]None[/dim]"
                console.print(f"{indent_str}[cyan]{key}:[/cyan] {value_str}")

    _print_dict(data_dict)


def get_representation_cli(
    project_name: str = typer.Argument(..., help="Project name"),
    folder_path: str = typer.Argument(..., help="Folder path (can be partial)"),
    product_name: str = typer.Argument(..., help="Product name (e.g., audioMain)"),
    representation_name: str = typer.Option("wav", "--rep", "-r", help="Representation name"),
    local: bool = typer.Option(
        False, "--local", help="Use local environment (AYON_SERVER_URL_LOCAL, AYON_API_KEY_LOCAL)"
    ),
    dev: bool = typer.Option(False, "--dev", help="Use dev environment (AYON_SERVER_URL_DEV, AYON_API_KEY_DEV)"),
    format: Literal["table", "dict"] = typer.Option(
        "table", "--format", "-f", help="Output format: 'table' (default) or 'dict' (formatted dictionary)"
    ),
    path_only: bool = typer.Option(False, "--path-only", "-p", help="Output only the resolved file path"),
    debug: bool = typer.Option(False, "--debug", help="Print debug information for path resolution"),
):
    """Get representation for a product in a folder."""
    try:
        # Setup connection
        setup_ayon_connection(console, use_local=local, use_dev=dev)

        # Get representation
        console.print(f"[dim]Fetching representation...[/dim]")
        representation = get_representation(
            project_name,
            folder_path,
            product_name,
            representation_name,
        )

        if not representation:
            # Try to provide helpful error messages
            console.print(f"[red]✗ Representation not found[/red]")
            console.print(f"\n[dim]Project:[/dim] {project_name}")
            console.print(f"[dim]Folder:[/dim] {folder_path}")
            console.print(f"[dim]Product:[/dim] {product_name}")
            console.print(f"[dim]Representation:[/dim] {representation_name}")

            # Try to get folder to show available products
            if ayon_api is not None:
                try:
                    folder = ayon_api.get_folder_by_path(project_name, folder_path, fields=["id", "name", "path"])

                    # If folder not found, try by name
                    if not folder:
                        folder_name = folder_path.split("/")[-1]
                        folders = list(
                            ayon_api.get_folders(
                                project_name,
                                folder_names=[folder_name],
                                fields=["id", "name", "path"],
                            )
                        )
                        if len(folders) == 1:
                            folder = folders[0]
                        elif len(folders) > 1:
                            console.print(f"\n[yellow]Found {len(folders)} folders with name '{folder_name}':[/yellow]")
                            table = Table(show_header=True, header_style="bold magenta")
                            table.add_column("Path", style="cyan")
                            table.add_column("Name", style="green")
                            for f in folders:
                                table.add_row(f.get("path", "N/A"), f.get("name", "N/A"))
                            console.print(table)
                            console.print(f"[yellow]Please use the full folder path.[/yellow]")
                            raise typer.Exit(code=1)

                    if folder:
                        # List available products
                        products = list(
                            ayon_api.get_products(
                                project_name,
                                folder_ids=[folder["id"]],
                                fields=["name", "productType"],
                            )
                        )
                        if products:
                            console.print(
                                f"\n[yellow]Available products in folder '{folder.get('path', 'N/A')}':[/yellow]"
                            )
                            table = Table(show_header=True, header_style="bold magenta")
                            table.add_column("Name", style="cyan")
                            table.add_column("Type", style="green")
                            for p in products:
                                table.add_row(
                                    p.get("name", "N/A"),
                                    p.get("productType", "N/A"),
                                )
                            console.print(table)
                        else:
                            console.print(f"[yellow]No products found in folder.[/yellow]")
                except Exception as e:
                    console.print(f"[dim]Could not fetch folder details: {e}[/dim]")

            raise typer.Exit(code=1)

        # Get additional info for display
        representation_id = representation.get("id", "N/A")
        attrib = representation.get("attrib", {})
        version_id = representation.get("versionId", "N/A")
        version_info = None
        if ayon_api is not None:
            try:
                version = ayon_api.get_version_by_id(project_name, version_id, fields=["version"])
                if version:
                    version_info = version.get("version", "N/A")
            except Exception:
                pass

        # If path-only mode requested, resolve and print path, then exit
        if path_only:
            resolved_path = _resolve_representation_path(representation, project_name, debug=debug)
            if resolved_path and resolved_path != "N/A":
                print(resolved_path)
                return
            else:
                console.print(f"[red]Error: Could not resolve representation path[/red]")
                raise typer.Exit(code=1)

        # Resolve path for display (needed for both dict and table formats)
        resolved_path = _resolve_representation_path(representation, project_name, debug=debug)

        # If dict format requested, print and exit
        if format == "dict":
            formatted_dict = _format_representation_as_dict(
                representation,
                project_name,
                folder_path,
                product_name,
                representation_name,
                version_info,
                resolved_path,
            )
            _print_dict_formatted(formatted_dict)
            return

        # Otherwise, use table format (default)
        # Display representation info
        # Create summary panel
        summary_text = f"[cyan]ID:[/cyan] {representation_id}\n"
        summary_text += f"[cyan]Product:[/cyan] {product_name}\n"
        summary_text += f"[cyan]Folder:[/cyan] {folder_path}\n"
        if version_info:
            summary_text += f"[cyan]Version:[/cyan] {version_info}\n"
        summary_text += f"[cyan]Representation:[/cyan] {representation_name}"

        console.print("\n")
        console.print(
            Panel(
                summary_text,
                title="[bold green]✓ Representation Found[/bold green]",
                border_style="green",
            )
        )

        # Use already resolved path from above
        hardcoded_path = attrib.get("path", "N/A")

        # Display attributes in table format
        # Filter out None values or show them dimmed
        non_none_attrib = {k: v for k, v in attrib.items() if v is not None}
        all_attrib = attrib if attrib else {}

        if all_attrib:
            console.print("\n[bold]Representation Attributes:[/bold]")
            # Create table for attributes
            attr_table = Table(show_header=True, header_style="bold magenta", show_lines=False)
            attr_table.add_column("Attribute", style="cyan", width=25, no_wrap=True)
            attr_table.add_column("Value", style="green", overflow="fold", width=None)

            # Show non-None attributes first, then None attributes
            # Sort for better readability
            for key in sorted(all_attrib.keys()):
                value = all_attrib[key]
                # Format None values
                if value is None:
                    value_str = "[dim]None[/dim]"
                else:
                    value_str = str(value)
                attr_table.add_row(key, value_str)

            console.print(attr_table)

            # Show summary if many None values
            if len(non_none_attrib) < len(all_attrib):
                console.print(
                    f"\n[dim]Note: {len(all_attrib) - len(non_none_attrib)} attributes are not set (None)[/dim]"
                )
        else:
            console.print("\n[yellow]No attributes found.[/yellow]")

        # Display resolved path separately
        if resolved_path and resolved_path != "N/A":
            console.print("\n[bold]Resolved Path:[/bold]")
            console.print(f"[green]{resolved_path}[/green]")
            if hardcoded_path != "N/A" and hardcoded_path != resolved_path:
                console.print(f"\n[dim]Note: Hardcoded path (from attrib) differs: {hardcoded_path}[/dim]")
        elif hardcoded_path != "N/A":
            console.print("\n[bold]Path:[/bold]")
            console.print(f"[yellow]{hardcoded_path}[/yellow]")
            console.print("[dim]Note: Using hardcoded path (path resolution unavailable or failed)[/dim]")

        # Also show other representation fields that might be useful
        context = representation.get("context") or {}
        data = representation.get("data")
        files = representation.get("files")
        status = representation.get("status")
        tags = representation.get("tags") or []

        # Normalize data - ensure it's a dict or None
        if data is None:
            data = {}
        elif not isinstance(data, dict):
            # If data is not a dict, wrap it
            data = {"value": data}

        # Normalize files - ensure it's a list or None
        if files is None:
            files = []
        elif not isinstance(files, list):
            # If files is not a list, try to convert it
            files = [files] if files else []

        # Show context if it has data
        if context:
            console.print("\n[bold]Context:[/bold]")
            ctx_table = Table(show_header=True, header_style="bold magenta", show_lines=False)
            ctx_table.add_column("Key", style="cyan", width=25, no_wrap=True)
            ctx_table.add_column("Value", style="green", overflow="fold", width=None)
            for key in sorted(context.keys()):
                value = context[key]
                ctx_table.add_row(key, str(value) if value is not None else "[dim]None[/dim]")
            console.print(ctx_table)

        # Show data table (always show, even if empty)
        console.print("\n[bold]Data:[/bold]")
        data_table = Table(show_header=True, header_style="bold magenta", show_lines=False)
        data_table.add_column("Key", style="cyan", width=25, no_wrap=True)
        data_table.add_column("Value", style="green", overflow="fold", width=None)
        if data and isinstance(data, dict) and len(data) > 0:
            for key in sorted(data.keys()):
                value = data[key]
                data_table.add_row(key, str(value) if value is not None else "[dim]None[/dim]")
        else:
            data_table.add_row("[dim]No data[/dim]", "[dim]Empty[/dim]")
        console.print(data_table)

        # Show files table (always show, even if empty)
        files_count = len(files) if files else 0
        console.print(f"\n[bold]Files ({files_count}):[/bold]")
        files_table = Table(show_header=True, header_style="bold magenta", show_lines=False)
        files_table.add_column("Path", style="cyan", overflow="fold", width=None)
        files_table.add_column("Size", style="green", width=15)
        files_table.add_column("Name", style="yellow", width=20)
        files_table.add_column("ID", style="dim", width=15)

        if files and len(files) > 0:
            for file_info in files:
                # Handle different file formats
                if isinstance(file_info, str):
                    # If file_info is just a string (path)
                    path = file_info
                    size_str = "[dim]N/A[/dim]"
                    name = os.path.basename(path) if path else "N/A"
                    file_id = "[dim]N/A[/dim]"
                elif isinstance(file_info, dict):
                    # If file_info is a dict with path, size, name, id
                    path = file_info.get("path", file_info.get("name", "N/A"))
                    size = file_info.get("size")
                    size_str = f"{size:,} bytes" if size is not None else "[dim]N/A[/dim]"
                    name = file_info.get("name", os.path.basename(path) if path else "N/A")
                    file_id = file_info.get("id", "[dim]N/A[/dim]")
                else:
                    # Fallback for unexpected types
                    path = str(file_info)
                    size_str = "[dim]N/A[/dim]"
                    name = "[dim]N/A[/dim]"
                    file_id = "[dim]N/A[/dim]"

                files_table.add_row(path, size_str, name, file_id)
        else:
            files_table.add_row("[dim]No files[/dim]", "[dim]Empty[/dim]", "[dim]-[/dim]", "[dim]-[/dim]")
        console.print(files_table)

        # Show status and tags
        if status or tags:
            info_parts = []
            if status:
                info_parts.append(f"[cyan]Status:[/cyan] {status}")
            if tags:
                info_parts.append(f"[cyan]Tags:[/cyan] {', '.join(tags) if tags else 'None'}")
            if info_parts:
                console.print(f"\n{' | '.join(info_parts)}")

    except AYONConnectionError as e:
        console.print(f"[red]Connection Error: {e}[/red]")
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(code=1)
