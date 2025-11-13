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
    print("\n" + "=" * 80)
    print("🔍 AYON Nuke Render Output Diagnostics")
    print("=" * 80 + "\n")

    # Display AYON architecture explanation
    print("=" * 80)
    print("AYON Nuke Render Architecture:")
    print("  ✓ Correct: Render instances are Group nodes containing Write nodes inside")
    print("  ✗ Wrong: Standalone Write nodes at root level (not managed by AYON)")
    print("=" * 80 + "\n")

    # Get AYON context
    context_info = display_ayon_context()

    # Get publish instances
    instances = get_publish_instances()

    issues_found = []

    # Get Write nodes inside AYON instances (properly managed)
    instance_write_nodes = get_write_nodes_inside_instances(instances)

    # Get all Write nodes at root level (potentially standalone)
    root_write_nodes = [node for node in nuke.allNodes() if node.Class() == "Write"]

    # Total Write nodes
    total_writes = len(root_write_nodes) + len(instance_write_nodes)

    if total_writes == 0:
        print("❌ No Write nodes found in the script!")
        print("This means no render outputs are configured.\n")
        return

    # Show summary
    print("Write Nodes Summary:")
    print(f"  • Root-level Write nodes: {len(root_write_nodes)}")
    print(f"  • Write nodes inside AYON instances: {len(instance_write_nodes)}")
    print(f"  • Total: {total_writes}\n")

    # Warning if standalone Write nodes detected
    if len(root_write_nodes) > 0:
        print("⚠️  WARNING: Standalone Write nodes detected!")
        print("Root-level Write nodes are NOT managed by AYON and won't be published.")
        print("Proper workflow: Create render instances via AYON Publisher\n")

    # Display publish instances
    display_publish_instances()

    # Analyze root-level Write nodes (standalone - incorrect workflow)
    if len(root_write_nodes) > 0:
        print("Root-Level Write Nodes (Standalone - NOT managed by AYON):\n")
        for idx, write_node in enumerate(root_write_nodes, 1):
            analyze_write_node(
                write_node,
                idx,
                issues_found,
                context_info,
                instances,
                is_inside_instance=False,
                parent_instance=None,
            )

    # Analyze Write nodes inside instances (correct workflow)
    if len(instance_write_nodes) > 0:
        print("Write Nodes Inside AYON Instances (Properly Managed):\n")
        for idx, (write_node, instance) in enumerate(instance_write_nodes.items(), len(root_write_nodes) + 1):
            analyze_write_node(
                write_node,
                idx,
                issues_found,
                context_info,
                instances,
                is_inside_instance=True,
                parent_instance=instance,
            )

    # Display summary
    display_summary(issues_found, total_writes)

    # Check AYON settings
    display_ayon_settings(issues_found)

    # Display publish instances
    display_publish_instances()


def get_write_nodes_inside_instances(instances):
    """Get Write nodes that exist inside AYON render instance Group nodes.

    In AYON Nuke, render instances are Group nodes that contain Write nodes inside them.
    This is the proper AYON workflow. Write nodes at root level are standalone and
    NOT managed by the AYON pipeline.

    Args:
        instances: List of AYON instances from get_publish_instances()

    Returns:
        dict: Mapping of {write_node: instance_data}
    """
    instance_write_nodes = {}

    print("Checking for Write nodes inside AYON instances...")

    for instance in instances:
        instance_node = instance.get("node")
        if not instance_node:
            continue

        # AYON render instances are Group nodes
        if instance_node.Class() == "Group":
            print(f"  Checking Group: {instance_node.name()}")
            try:
                # Switch context to inside the Group
                with instance_node:
                    write_nodes = nuke.allNodes("Write")
                    print(f"    ✓ Found {len(write_nodes)} Write node(s) inside Group")
                    for write_node in write_nodes:
                        instance_write_nodes[write_node] = instance
                        print(f"      - {write_node.name()}")
            except Exception as err:
                print(f"    ✗ Error checking Group: {err}")

    print()
    return instance_write_nodes


def display_ayon_context():
    """Display AYON context information."""
    print("🎬 AYON Context Information\n")

    context = get_ayon_context()

    if "error" in context:
        print(f"⚠ Could not retrieve AYON context: {context['error']}")
        print("This is normal if running outside AYON workfile\n")
        return None

    # Display context information
    print(f"Project: {context.get('project_name', 'N/A')}")

    folder = context.get("folder_entity")
    if folder:
        print(f"Folder: {folder.get('name', 'N/A')}")
        print(f"Folder Path: {folder.get('path', 'N/A')}")

    task = context.get("task_entity")
    if task:
        print(f"Task: {task.get('name', 'N/A')}")
        print(f"Task Type: {task.get('taskType', 'N/A')}")

    print()

    return context


def analyze_write_node(
    write_node, idx, issues_found, context_info, instances, is_inside_instance=False, parent_instance=None
):
    """Analyze a single Write node for potential issues.

    Args:
        write_node: The Nuke Write node to analyze
        idx: Index number for display
        issues_found: List to append issues to
        context_info: AYON context information
        instances: List of AYON instances
        is_inside_instance: Whether this Write is inside a render instance Group
        parent_instance: The instance data if inside a Group
    """
    node_name = write_node.name()

    # Different title based on whether it's managed by AYON
    print("-" * 80)
    if is_inside_instance and parent_instance:
        parent_name = parent_instance.get("node_name", "Unknown")
        print(f"Write Node #{idx}: {node_name} (inside {parent_name})")
    else:
        print(f"Write Node #{idx}: {node_name} (standalone)")
    print("-" * 80)

    # Get file output path
    file_knob = write_node.knob("file")
    if file_knob:
        file_path = file_knob.value()
        file_ext = file_path.split(".")[-1].lower() if "." in file_path else "unknown"

        # Shorten path for display
        display_path = file_path
        if len(file_path) > 80:
            display_path = "..." + file_path[-77:]

        print(f"Output Path: {display_path}")
        print(f"File Extension: {file_ext.upper()}")

        # Check if it's EXR
        if file_ext == "exr":
            print("EXR Output: Yes [✓ Good]")
        else:
            print(f"EXR Output: No (using {file_ext.upper()}) [⚠ Issue]")
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
        print(f"File Type Knob: {file_type}")

    # Check colorspace
    colorspace_knob = write_node.knob("colorspace")
    if colorspace_knob:
        colorspace = colorspace_knob.value()
        print(f"Colorspace: {colorspace}")

    # Determine AYON management status
    print("\n--- AYON Management ---")

    if is_inside_instance and parent_instance:
        # This Write is properly managed by AYON
        product_name = parent_instance.get("product_name", "N/A")
        product_type = parent_instance.get("product_type", "N/A")
        instance_node_name = parent_instance.get("node_name", "N/A")

        print("Pipeline Status: ✓ Managed by AYON [✓ Correct]")
        print(f"Parent Instance: {instance_node_name} [✓]")
        print(f"Product Name: {product_name}")
        print(f"Product Type: {product_type}")

        # Families
        families = parent_instance.get("families", [])
        print(f"Families: {', '.join(families) if families else 'None'}")

        # Active status
        active = parent_instance.get("active", True)
        status_msg = "[✓]" if active else "[✗ Disabled]"
        print(f"Active: {active} {status_msg}")

        # Variant
        variant = parent_instance.get("variant", "N/A")
        print(f"Variant: {variant}")

    else:
        # This is a standalone Write node - NOT managed by AYON
        print("Pipeline Status: ⚠️ Standalone (NOT managed by AYON) [✗ Issue]")
        print("Workflow Issue: Not created via AYON Publisher [✗ Wrong]")
        print("Publishing: Will NOT be published to AYON [✗ Issue]")

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
            print(f"Views: {views} [Multiple views detected]")

    print()


def display_ayon_settings(issues_found):
    """Display AYON settings related to review extraction."""
    print("⚙️ AYON Project Settings Analysis\n")

    settings = get_ayon_settings()

    if "error" in settings:
        print(f"⚠ Could not retrieve AYON settings: {settings['error']}")
        print("This is normal if running outside AYON context\n")
        return

    print(f"✓ Connected to project: {settings['project_name']}")

    # Analyze Extract Review Intermediates settings
    review_intermediates = settings.get("extract_review_intermediates", {})
    enabled = review_intermediates.get("enabled", False)

    print(f"✓ Extract Review Intermediates: {'Enabled' if enabled else 'Disabled'}\n")

    if not enabled:
        print("⚠ Extract Review Intermediates is disabled - no MOV files will be created\n")
        return

    # Display output configurations
    outputs = review_intermediates.get("outputs", [])
    print(f"Configured review outputs: {len(outputs)}\n")

    if len(outputs) > 1:
        print("⚠ Multiple review output profiles detected!")
        print("This might be causing duplicate MOV files if filters overlap\n")
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
        # Display output profiles
        print("=" * 80)
        print("Review Output Profiles:")
        print("=" * 80)
        for output in outputs:
            output_filter = output.get("filter", {})
            product_types = output_filter.get("product_types", [])
            task_types = output_filter.get("task_types", [])
            product_names = output_filter.get("product_names", [])

            # Check if this output matches render products
            matches_render = "render" in product_types or not product_types

            name = output.get("name", "unnamed")
            if matches_render:
                name = f"*** {name} ***"

            print(f"\nName: {name}")
            print(f"Extension: {output.get('extension', '?')}")
            print(f"Publish: {'✓' if output.get('publish', False) else '✗'}")
            print(f"Product Types: {', '.join(product_types) if product_types else 'all'}")
            print(f"Task Types: {', '.join(task_types) if task_types else 'all'}")
            print(f"Product Names: {', '.join(product_names) if product_names else 'all'}")

        print("=" * 80)
        print()

        # Check for duplicate output configurations
        render_outputs = [
            o
            for o in outputs
            if not o.get("filter", {}).get("product_types") or "render" in o.get("filter", {}).get("product_types", [])
        ]

        if len(render_outputs) > 1:
            print(f"⚠ Found {len(render_outputs)} outputs that match 'render' product type!")
            print("This will create multiple MOV files for each render\n")

            # Show which outputs match
            print("Duplicate Output Detection:")
            for output in render_outputs:
                output_filter = output.get("filter", {})
                print(f"  Output: {output.get('name', 'unnamed')}")

                if output_filter.get("product_names"):
                    print(f"    Product Names: {', '.join(output_filter['product_names'])}")
                else:
                    print("    No product name filter - matches ALL")

            print()


def display_publish_instances():
    """Display all publish instances found in the Nuke script."""
    print("📦 Publish Instances in Nuke Script\n")

    instances_data = get_publish_instances()

    if isinstance(instances_data, dict) and "error" in instances_data:
        print(f"⚠ Could not retrieve instances: {instances_data['error']}\n")
        return

    if not instances_data:
        print("No AYON publish instances found in script\n")
        return

    print(f"✓ Found {len(instances_data)} publish instance(s)\n")

    # Display instances
    print("=" * 80)
    print(f"{'Node':<25} {'Product Type':<15} {'Product Name':<30} {'Families':<20} Active")
    print("-" * 80)

    for instance in instances_data:
        active_status = "✓" if instance.get("active") else "✗"
        families_str = ", ".join(instance.get("families", []))

        # Get node name
        node_name = instance.get("node_name", "N/A")
        if instance.get("product_type") == "render":
            node_name = f"*** {node_name}"

        print(f"{node_name:<25} {instance.get('product_type', 'N/A'):<15} {instance.get('product_name', 'N/A'):<30} {families_str or 'none':<20} {active_status}")

    print("=" * 80)
    print()

    # Show detailed data for render instances
    render_instances = [i for i in instances_data if i.get("product_type") == "render"]
    if render_instances:
        print(f"Detailed Render Instance Data ({len(render_instances)} found)\n")

        for instance in render_instances:
            # Format JSON as plain text for Nuke Script Editor compatibility
            json_data = json.dumps(instance.get("data", {}), indent=2, default=str)

            print(f"\nInstance: {instance.get('node_name', 'N/A')}")
            print("-" * 80)
            print(json_data)
            print("-" * 80 + "\n")


def display_summary(issues_found, write_node_count):
    """Display summary of findings."""
    print("📊 Diagnostic Summary\n")

    if not issues_found:
        print("=" * 80)
        print("✓ No issues detected with Write node configuration!")
        print("=" * 80 + "\n")
        return

    # Categorize issues
    high_severity = [i for i in issues_found if i["severity"] == "high"]
    medium_severity = [i for i in issues_found if i["severity"] == "medium"]

    # Display issues
    print("Issues Found:")
    print("=" * 80)
    print(f"{'Node':<25} {'Issue Type':<20} {'Details':<30} Severity")
    print("-" * 80)

    for issue in issues_found:
        issue_type = issue["type"].replace("_", " ").title()
        print(f"{issue['node']:<25} {issue_type:<20} {issue['detail']:<30} {issue['severity'].upper()}")

    print("=" * 80)
    print()

    # Recommendations
    print("💡 Recommendations:\n")

    if high_severity:
        print("High Priority Issues:")
        for issue in high_severity:
            print(f"  • ✗ {issue['node']}: {issue['detail']}")
            print(f"    → {issue['recommendation']}")
        print()

    if medium_severity:
        print("Medium Priority Issues:")
        for issue in medium_severity:
            print(f"  • ⚠ {issue['node']}: {issue['detail']}")
            print(f"    → {issue['recommendation']}")
        print()

    # General recommendations
    print("Correct Workflow:")
    print("  1. Write node → Output EXR sequence (frames)")
    print("  2. AYON Extract Review Intermediates → Generate MOV for review")
    print("  3. Both EXR and MOV get published to AYON")
    print()

    print("To Fix Duplicate MOVs:")
    print("  • Open AYON Settings → Nuke → Publish Plugins → Extract Review Intermediates")
    print("  • Check 'outputs' array for duplicate configurations")
    print("  • Ensure each output has specific product_names filter")
    print("  • Remove outputs with overlapping filters")
    print()


if __name__ == "__main__":
    # If running in Nuke
    try:
        diagnose_render_setup()
    except ImportError:
        print("This script should be run inside Nuke with AYON loaded.")
