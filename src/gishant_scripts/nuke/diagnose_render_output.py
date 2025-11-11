"""Diagnostic script to identify render output issues in Nuke.

This script diagnoses issues with:
1. Duplicate MOV files being created
2. Missing EXR sequence outputs

Run this in Nuke's Script Editor to check the current setup.

Usage:
    In Nuke Script Editor, run:
    >>> import sys
    >>> sys.path.insert(0, "/home/gisi/dev/repos/gishant-scripts/src")
    >>> from gishant_scripts.nuke.diagnose_render_output import diagnose_render_setup
    >>> diagnose_render_setup()
"""

import json

import nuke
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree


def get_ayon_context():
    """Get AYON context information from the current Nuke session."""
    try:
        from ayon_core.pipeline import (
            get_current_context,
            get_current_project_name,
        )

        # Try importing folder/task entity getters (may not exist in all versions)
        try:
            from ayon_core.pipeline import (
                get_current_folder_entity,
                get_current_task_entity,
            )

            folder_entity = get_current_folder_entity()
            task_entity = get_current_task_entity()
        except ImportError:
            # Fallback: extract from full context
            full_context = get_current_context()
            folder_entity = full_context.get("folder_entity")
            task_entity = full_context.get("task_entity")

        context = {
            "project_name": get_current_project_name(),
            "folder_entity": folder_entity,
            "task_entity": task_entity,
            "full_context": get_current_context(),
        }
        return context
    except Exception as err:
        return {"error": str(err)}


def get_ayon_settings():
    """Get AYON project settings for Nuke publish plugins."""
    try:
        from ayon_core.pipeline import get_current_project_name
        from ayon_core.settings import get_project_settings

        project_name = get_current_project_name()
        if not project_name:
            return {"error": "No active AYON project"}

        settings = get_project_settings(project_name)
        nuke_settings = settings.get("nuke", {})
        publish_settings = nuke_settings.get("publish", {})

        return {
            "project_name": project_name,
            "extract_review_intermediates": publish_settings.get("ExtractReviewIntermediates", {}),
            "extract_render_local": publish_settings.get("ExtractRenderLocal", {}),
            "extract_review": publish_settings.get("ExtractReview", {}),
            "create_write_render": nuke_settings.get("create", {}).get("CreateWriteRender", {}),
        }
    except Exception as err:
        return {"error": str(err)}


def get_publish_instances():
    """Get all publish instances from the current Nuke script using AYON API."""
    try:
        from ayon_nuke.api import list_instances

        # Use AYON's native list_instances function
        ayon_instances = list_instances()

        instances = []
        for node, instance_data in ayon_instances:
            instances.append(
                {
                    "node": node,
                    "node_name": node.name(),
                    "node_class": node.Class(),
                    "creator": instance_data.get("creator"),
                    "creator_identifier": instance_data.get("creator_identifier"),
                    "product_type": instance_data.get("productType"),
                    "product_name": instance_data.get("productName"),
                    "families": instance_data.get("families", []),
                    "active": instance_data.get("active", True),
                    "variant": instance_data.get("variant"),
                    "data": instance_data,
                }
            )
        return instances
    except Exception as err:
        return {"error": str(err)}


def diagnose_render_setup():
    """Diagnose render output configuration in current Nuke script."""
    console = Console()

    console.print("\n[bold cyan]🔍 AYON Nuke Render Output Diagnostics[/bold cyan]\n")

    # Display AYON architecture explanation
    console.print("[dim]" + "=" * 80 + "[/dim]")
    console.print("[bold]AYON Nuke Render Architecture:[/bold]")
    console.print("  [green]✓ Correct:[/green] Render instances are Group nodes containing Write nodes inside")
    console.print("  [red]✗ Wrong:[/red] Standalone Write nodes at root level (not managed by AYON)")
    console.print("[dim]" + "=" * 80 + "[/dim]\n")

    # Get AYON context
    context_info = display_ayon_context(console)

    # Get publish instances
    instances = get_publish_instances()

    issues_found = []

    # Get Write nodes inside AYON instances (properly managed)
    instance_write_nodes = get_write_nodes_inside_instances(instances, console)

    # Get all Write nodes at root level (potentially standalone)
    root_write_nodes = [node for node in nuke.allNodes() if node.Class() == "Write"]

    # Total Write nodes
    total_writes = len(root_write_nodes) + len(instance_write_nodes)

    if total_writes == 0:
        console.print("[red]❌ No Write nodes found in the script![/red]")
        console.print("[dim]This means no render outputs are configured.[/dim]\n")
        return

    # Show summary
    console.print("[cyan]Write Nodes Summary:[/cyan]")
    console.print(f"  • Root-level Write nodes: {len(root_write_nodes)}")
    console.print(f"  • Write nodes inside AYON instances: {len(instance_write_nodes)}")
    console.print(f"  • Total: {total_writes}\n")

    # Warning if standalone Write nodes detected
    if len(root_write_nodes) > 0:
        console.print("[bold red]⚠️  WARNING: Standalone Write nodes detected![/bold red]")
        console.print("[yellow]Root-level Write nodes are NOT managed by AYON and won't be published.[/yellow]")
        console.print("[yellow]Proper workflow: Create render instances via AYON Publisher[/yellow]\n")

    # Display publish instances
    display_publish_instances(console)

    # Analyze root-level Write nodes (standalone - incorrect workflow)
    if len(root_write_nodes) > 0:
        console.print("[bold yellow]Root-Level Write Nodes (Standalone - NOT managed by AYON):[/bold yellow]\n")
        for idx, write_node in enumerate(root_write_nodes, 1):
            analyze_write_node(
                write_node,
                idx,
                console,
                issues_found,
                context_info,
                instances,
                is_inside_instance=False,
                parent_instance=None,
            )

    # Analyze Write nodes inside instances (correct workflow)
    if len(instance_write_nodes) > 0:
        console.print("[bold green]Write Nodes Inside AYON Instances (Properly Managed):[/bold green]\n")
        for idx, (write_node, instance) in enumerate(instance_write_nodes.items(), len(root_write_nodes) + 1):
            analyze_write_node(
                write_node,
                idx,
                console,
                issues_found,
                context_info,
                instances,
                is_inside_instance=True,
                parent_instance=instance,
            )

    # Display summary
    display_summary(console, issues_found, total_writes)

    # Check AYON settings
    display_ayon_settings(console, issues_found)

    # Display publish instances
    display_publish_instances(console)


def get_write_nodes_inside_instances(instances, console):
    """Get Write nodes that exist inside AYON render instance Group nodes.

    In AYON Nuke, render instances are Group nodes that contain Write nodes inside them.
    This is the proper AYON workflow. Write nodes at root level are standalone and
    NOT managed by the AYON pipeline.

    Args:
        instances: List of AYON instances from get_publish_instances()
        console: Rich console for output

    Returns:
        dict: Mapping of {write_node: instance_data}
    """
    instance_write_nodes = {}

    console.print("[cyan]Checking for Write nodes inside AYON instances...[/cyan]")

    for instance in instances:
        instance_node = instance.get("node")
        if not instance_node:
            continue

        # AYON render instances are Group nodes
        if instance_node.Class() == "Group":
            console.print(f"  [cyan]Checking Group: {instance_node.name()}[/cyan]")
            try:
                # Switch context to inside the Group
                with instance_node:
                    write_nodes = nuke.allNodes("Write")
                    console.print(f"    [green]✓ Found {len(write_nodes)} Write node(s) inside Group[/green]")
                    for write_node in write_nodes:
                        instance_write_nodes[write_node] = instance
                        console.print(f"      - {write_node.name()}")
            except Exception as e:
                console.print(f"    [red]✗ Error checking Group: {e}[/red]")

    console.print()
    return instance_write_nodes


def display_ayon_context(console):
    """Display AYON context information."""
    console.print("[bold]🎬 AYON Context Information[/bold]\n")

    context = get_ayon_context()

    if "error" in context:
        console.print(f"[yellow]⚠ Could not retrieve AYON context: {context['error']}[/yellow]")
        console.print("[dim]This is normal if running outside AYON workfile[/dim]\n")
        return None

    context_table = Table(box=box.SIMPLE, show_header=False)
    context_table.add_column("Property", style="cyan")
    context_table.add_column("Value", style="yellow")

    context_table.add_row("Project", context.get("project_name", "N/A"))

    folder = context.get("folder_entity")
    if folder:
        context_table.add_row("Folder", folder.get("name", "N/A"))
        context_table.add_row("Folder Path", folder.get("path", "N/A"))

    task = context.get("task_entity")
    if task:
        context_table.add_row("Task", task.get("name", "N/A"))
        context_table.add_row("Task Type", task.get("taskType", "N/A"))

    console.print(context_table)
    console.print()

    return context


def analyze_write_node(
    write_node, idx, console, issues_found, context_info, instances, is_inside_instance=False, parent_instance=None
):
    """Analyze a single Write node for potential issues.

    Args:
        write_node: The Nuke Write node to analyze
        idx: Index number for display
        console: Rich console for output
        issues_found: List to append issues to
        context_info: AYON context information
        instances: List of AYON instances
        is_inside_instance: Whether this Write is inside a render instance Group
        parent_instance: The instance data if inside a Group
    """
    node_name = write_node.name()

    # Different title based on whether it's managed by AYON
    if is_inside_instance and parent_instance:
        parent_name = parent_instance.get("node_name", "Unknown")
        title = f"Write Node #{idx}: [green]{node_name}[/green] (inside {parent_name})"
        title_style = "bold green"
    else:
        title = f"Write Node #{idx}: [yellow]{node_name}[/yellow] (standalone)"
        title_style = "bold yellow"

    # Create table for this node
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style=title_style,
    )
    table.add_column("Property", style="cyan", width=20)
    table.add_column("Value", style="yellow", width=50)
    table.add_column("Status", style="white", width=20)

    # Get file output path
    file_knob = write_node.knob("file")
    if file_knob:
        file_path = file_knob.value()
        file_ext = file_path.split(".")[-1].lower() if "." in file_path else "unknown"

        # Shorten path for display
        display_path = file_path
        if len(file_path) > 80:
            display_path = "..." + file_path[-77:]

        table.add_row("Output Path", display_path, "")
        table.add_row("File Extension", file_ext.upper(), "")

        # Check if it's EXR
        if file_ext == "exr":
            table.add_row("EXR Output", "Yes", "[green]✓ Good[/green]")
        else:
            table.add_row(
                "EXR Output",
                f"No (using {file_ext.upper()})",
                "[red]⚠ Issue[/red]",
            )
            issues_found.append(
                {
                    "node": node_name,
                    "type": "wrong_format",
                    "detail": f"Write node outputs {file_ext.upper()} instead of EXR",
                    "severity": "high",
                    "recommendation": "Change file extension to .exr in Write node file path",
                }
            )

    # Check file type
    file_type_knob = write_node.knob("file_type")
    if file_type_knob:
        file_type = file_type_knob.value()
        table.add_row("File Type Knob", file_type, "")

    # Check colorspace
    colorspace_knob = write_node.knob("colorspace")
    if colorspace_knob:
        colorspace = colorspace_knob.value()
        table.add_row("Colorspace", colorspace, "")

    # Determine AYON management status
    table.add_row("--- AYON Management ---", "---", "---")

    if is_inside_instance and parent_instance:
        # This Write is properly managed by AYON
        product_name = parent_instance.get("product_name", "N/A")
        product_type = parent_instance.get("product_type", "N/A")
        instance_node_name = parent_instance.get("node_name", "N/A")

        table.add_row("Pipeline Status", "✓ Managed by AYON", "[green]✓ Correct[/green]")
        table.add_row("Parent Instance", instance_node_name, "[green]✓[/green]")
        table.add_row("Product Name", product_name, "")
        table.add_row("Product Type", product_type, "")

        # Families
        families = parent_instance.get("families", [])
        table.add_row("Families", ", ".join(families) if families else "None", "")

        # Active status
        active = parent_instance.get("active", True)
        table.add_row(
            "Active",
            str(active),
            "[green]✓[/green]" if active else "[red]✗ Disabled[/red]",
        )

        # Variant
        variant = parent_instance.get("variant", "N/A")
        table.add_row("Variant", variant, "")

    else:
        # This is a standalone Write node - NOT managed by AYON
        table.add_row("Pipeline Status", "⚠️ Standalone (NOT managed by AYON)", "[red]✗ Issue[/red]")
        table.add_row("Workflow Issue", "Not created via AYON Publisher", "[red]✗ Wrong[/red]")
        table.add_row("Publishing", "Will NOT be published to AYON", "[red]✗ Issue[/red]")

        # Add to issues list
        issues_found.append(
            {
                "node": node_name,
                "type": "pipeline_workflow",
                "detail": f"Write node '{node_name}' is standalone (not managed by AYON pipeline)",
                "severity": "HIGH",
                "recommendation": (
                    f"This Write node '{node_name}' was created manually and is not part of the AYON pipeline. "
                    "Outputs will NOT be published to AYON. "
                    "\n\nCorrect workflow: "
                    "\n1. Delete this standalone Write node"
                    "\n2. Use AYON Publisher to create render instances (Create → Publish → Write Render)"
                    "\n3. AYON will create a Group node containing a managed Write node inside"
                ),
            }
        )

    # Check for multiple outputs
    views_knob = write_node.knob("views")
    if views_knob:
        views = views_knob.value()
        if views and views != "main":
            table.add_row("Views", views, "[yellow]Multiple views detected[/yellow]")

    console.print(table)
    console.print()


def display_ayon_settings(console, issues_found):
    """Display AYON settings related to review extraction."""
    console.print("[bold]⚙️ AYON Project Settings Analysis[/bold]\n")

    settings = get_ayon_settings()

    if "error" in settings:
        console.print(f"[yellow]⚠ Could not retrieve AYON settings: {settings['error']}[/yellow]")
        console.print("[dim]This is normal if running outside AYON context[/dim]\n")
        return

    console.print(f"[green]✓ Connected to project:[/green] {settings['project_name']}")

    # Analyze Extract Review Intermediates settings
    review_intermediates = settings.get("extract_review_intermediates", {})
    enabled = review_intermediates.get("enabled", False)

    console.print(f"[green]✓ Extract Review Intermediates:[/green] {'Enabled' if enabled else 'Disabled'}\n")

    if not enabled:
        console.print("[yellow]⚠ Extract Review Intermediates is disabled - no MOV files will be created[/yellow]\n")
        return

    # Display output configurations
    outputs = review_intermediates.get("outputs", [])
    console.print(f"[cyan]Configured review outputs: {len(outputs)}[/cyan]\n")

    if len(outputs) > 1:
        console.print("[yellow]⚠ Multiple review output profiles detected![/yellow]")
        console.print("[dim]This might be causing duplicate MOV files if filters overlap[/dim]\n")
        issues_found.append(
            {
                "node": "Settings",
                "type": "multiple_outputs",
                "detail": f"{len(outputs)} output profiles configured",
                "severity": "medium",
                "recommendation": "Review output filters to ensure they don't overlap",
            }
        )

    if outputs:
        # Create detailed output table
        outputs_table = Table(
            title="Review Output Profiles",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan",
        )
        outputs_table.add_column("Name", style="cyan")
        outputs_table.add_column("Extension", style="yellow")
        outputs_table.add_column("Publish", style="green")
        outputs_table.add_column("Product Types", style="white")
        outputs_table.add_column("Task Types", style="white")
        outputs_table.add_column("Product Names", style="magenta")

        for output in outputs:
            output_filter = output.get("filter", {})
            product_types = output_filter.get("product_types", [])
            task_types = output_filter.get("task_types", [])
            product_names = output_filter.get("product_names", [])

            # Check if this output matches render products
            matches_render = "render" in product_types or not product_types

            name_style = ("[bold]" if matches_render else "") + output.get("name", "unnamed")

            outputs_table.add_row(
                name_style,
                output.get("extension", "?"),
                "✓" if output.get("publish", False) else "✗",
                ", ".join(product_types) if product_types else "[dim]all[/dim]",
                ", ".join(task_types) if task_types else "[dim]all[/dim]",
                ", ".join(product_names) if product_names else "[dim]all[/dim]",
            )

        console.print(outputs_table)
        console.print()

        # Check for duplicate output configurations
        render_outputs = [
            o
            for o in outputs
            if not o.get("filter", {}).get("product_types") or "render" in o.get("filter", {}).get("product_types", [])
        ]

        if len(render_outputs) > 1:
            console.print(f"[red]⚠ Found {len(render_outputs)} outputs that match 'render' product type![/red]")
            console.print("[dim]This will create multiple MOV files for each render[/dim]\n")

            # Show which outputs match
            duplicate_tree = Tree("[bold red]Duplicate Output Detection[/bold red]")
            for output in render_outputs:
                output_node = duplicate_tree.add(f"[yellow]Output: {output.get('name', 'unnamed')}[/yellow]")
                output_filter = output.get("filter", {})

                if output_filter.get("product_names"):
                    output_node.add(f"Product Names: {', '.join(output_filter['product_names'])}")
                else:
                    output_node.add("[red]No product name filter - matches ALL[/red]")

            console.print(duplicate_tree)
            console.print()


def display_publish_instances(console):
    """Display all publish instances found in the Nuke script."""
    console.print("[bold]📦 Publish Instances in Nuke Script[/bold]\n")

    instances_data = get_publish_instances()

    if isinstance(instances_data, dict) and "error" in instances_data:
        console.print(f"[yellow]⚠ Could not retrieve instances: {instances_data['error']}[/yellow]\n")
        return

    if not instances_data:
        console.print("[yellow]No AYON publish instances found in script[/yellow]\n")
        return

    console.print(f"[green]✓ Found {len(instances_data)} publish instance(s)[/green]\n")

    # Create instances table
    instances_table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    instances_table.add_column("Node", style="cyan", width=25)
    instances_table.add_column("Product Type", style="yellow", width=15)
    instances_table.add_column("Product Name", style="green", width=30)
    instances_table.add_column("Families", style="white", width=20)
    instances_table.add_column("Active", style="white", width=10)

    for instance in instances_data:
        active_status = "[green]✓[/green]" if instance.get("active") else "[red]✗[/red]"
        families_str = ", ".join(instance.get("families", []))

        # Highlight render instances
        node_name = instance.get("node_name", "N/A")
        if instance.get("product_type") == "render":
            node_name = f"[bold]{node_name}[/bold]"

        instances_table.add_row(
            node_name,
            instance.get("product_type", "N/A"),
            instance.get("product_name", "N/A"),
            families_str or "[dim]none[/dim]",
            active_status,
        )

    console.print(instances_table)
    console.print()

    # Show detailed data for render instances
    render_instances = [i for i in instances_data if i.get("product_type") == "render"]
    if render_instances:
        console.print(f"[bold cyan]Detailed Render Instance Data ({len(render_instances)} found)[/bold cyan]\n")

        for instance in render_instances:
            instance_panel = Panel(
                Syntax(
                    json.dumps(instance.get("data", {}), indent=2, default=str),
                    "json",
                    theme="monokai",
                ),
                title=f"[cyan]{instance.get('node_name', 'N/A')}[/cyan]",
                border_style="cyan",
            )
            console.print(instance_panel)


def display_summary(console, issues_found, write_node_count):
    """Display summary of findings."""
    console.print("[bold]📊 Diagnostic Summary[/bold]\n")

    if not issues_found:
        console.print(
            Panel(
                "[green]✓ No issues detected with Write node configuration![/green]",
                title="Result",
                border_style="green",
            )
        )
        return

    # Categorize issues
    high_severity = [i for i in issues_found if i["severity"] == "high"]
    medium_severity = [i for i in issues_found if i["severity"] == "medium"]

    # Create issues table
    issues_table = Table(
        title="Issues Found",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold red",
    )
    issues_table.add_column("Node", style="cyan")
    issues_table.add_column("Issue Type", style="yellow")
    issues_table.add_column("Details", style="white")
    issues_table.add_column("Severity", style="red")

    for issue in issues_found:
        severity_color = "red" if issue["severity"] == "high" else "yellow"
        issues_table.add_row(
            issue["node"],
            issue["type"].replace("_", " ").title(),
            issue["detail"],
            f"[{severity_color}]{issue['severity'].upper()}[/{severity_color}]",
        )

    console.print(issues_table)
    console.print()

    # Recommendations
    console.print("[bold]💡 Recommendations:[/bold]\n")

    if high_severity:
        console.print("[red]High Priority Issues:[/red]")
        for issue in high_severity:
            console.print(f"  • [red]✗[/red] {issue['node']}: {issue['detail']}")
            console.print(f"    [dim]→ {issue['recommendation']}[/dim]")
        console.print()

    if medium_severity:
        console.print("[yellow]Medium Priority Issues:[/yellow]")
        for issue in medium_severity:
            console.print(f"  • [yellow]⚠[/yellow] {issue['node']}: {issue['detail']}")
            console.print(f"    [dim]→ {issue['recommendation']}[/dim]")
        console.print()

    # General recommendations
    console.print("[bold cyan]Correct Workflow:[/bold cyan]")
    console.print("  1. Write node → Output EXR sequence (frames)")
    console.print("  2. AYON Extract Review Intermediates → Generate MOV for review")
    console.print("  3. Both EXR and MOV get published to AYON")
    console.print()

    console.print("[bold cyan]To Fix Duplicate MOVs:[/bold cyan]")
    console.print("  • Open AYON Settings → Nuke → Publish Plugins → Extract Review Intermediates")
    console.print("  • Check 'outputs' array for duplicate configurations")
    console.print("  • Ensure each output has specific product_names filter")
    console.print("  • Remove outputs with overlapping filters")
    console.print()


if __name__ == "__main__":
    # If running in Nuke
    try:
        diagnose_render_setup()
    except ImportError:
        print("This script should be run inside Nuke with AYON loaded.")
