#!/usr/bin/env python
"""Demonstration script showing Kitsu integration linking queries.

This script demonstrates how to use the kitsu_linking data stored on AYON
versions to:
1. Trace version lineage (workfile -> render -> review)
2. Find versions by Kitsu task ID
3. Find versions by Kitsu revision ID (when uploaded)

Usage:
    python docs/kitsu_integration_demo.py <project_name>

Example:
    python docs/kitsu_integration_demo.py my_project

Requirements:
    - rdo_ayon_utils module must be in PYTHONPATH
    - AYON server must be accessible
"""

import sys

import ayon_api

# Import utility to set up AYON connection
try:
    from rdo_ayon_utils import ayon_utils
except ImportError:
    print("ERROR: rdo_ayon_utils module not found in PYTHONPATH")
    print("Please ensure /home/gisi/dev/repos/rdo-ayon-utils/python is in PYTHONPATH")
    sys.exit(1)


def trace_version_lineage(project_name: str, version_id: str) -> list[dict]:
    """Trace back through version lineage to find original source.

    Args:
        project_name: AYON project name
        version_id: Starting version ID

    Returns:
        Chain of versions from source to current
    """
    lineage = []
    current_id = version_id
    visited = set()  # Prevent infinite loops

    while current_id and current_id not in visited:
        visited.add(current_id)
        version = ayon_api.get_version_by_id(project_name, current_id)
        lineage.insert(0, version)  # Add to beginning

        # Check for source version
        linking_data = version.get("data", {}).get("kitsu_linking", {})
        current_id = linking_data.get("source_version_id")

    return lineage


def find_version_by_kitsu_revision(project_name: str, kitsu_revision_id: str) -> dict | None:
    """Find AYON version linked to a Kitsu revision.

    Args:
        project_name: AYON project name
        kitsu_revision_id: Kitsu revision ID

    Returns:
        AYON version entity or None
    """
    # Query all versions with linking data
    versions = ayon_api.get_versions(project_name, fields=["id", "version", "productId", "data"])

    for version in versions:
        linking_data = version.get("data", {}).get("kitsu_linking", {})
        if linking_data.get("kitsu_revision_id") == kitsu_revision_id:
            return version

    return None


def get_versions_for_kitsu_task(project_name: str, kitsu_task_id: str) -> list[dict]:
    """Get all AYON versions linked to a Kitsu task.

    Args:
        project_name: AYON project name
        kitsu_task_id: Kitsu task ID

    Returns:
        AYON versions for this task
    """
    versions = ayon_api.get_versions(project_name, fields=["id", "version", "productId", "data"])

    task_versions = []
    for version in versions:
        linking_data = version.get("data", {}).get("kitsu_linking", {})
        if linking_data.get("kitsu_task_id") == kitsu_task_id:
            task_versions.append(version)

    return task_versions


def get_product_name(project_name: str, product_id: str) -> str:
    """Get product name from ID."""
    try:
        product = ayon_api.get_product_by_id(project_name, product_id)
        return product.get("name", "unknown")
    except Exception:
        return "unknown"


def demo_trace_lineage(project_name: str, version_id: str):
    """Demonstrate version lineage tracing."""
    print(f"\n{'=' * 60}")
    print("DEMO 1: Trace Version Lineage")
    print(f"{'=' * 60}")

    chain = trace_version_lineage(project_name, version_id)

    print(f"\nVersion Lineage Chain (Total: {len(chain)} versions):")
    print("-" * 60)

    for i, version in enumerate(chain, 1):
        product_name = get_product_name(project_name, version["productId"])
        version_num = version["version"]
        linking = version.get("data", {}).get("kitsu_linking", {})

        print(f"\n{i}. {product_name} v{version_num:03d}")
        print(f"   ID: {version['id']}")

        if linking:
            if "source_version_id" in linking:
                print(f"   ↳ Created from: {linking['source_version_id']}")
            if "kitsu_task_id" in linking:
                print(f"   ↳ Kitsu Task: {linking['kitsu_task_id']}")
            if "ayon_version_url" in linking:
                print(f"   ↳ URL: {linking['ayon_version_url']}")


def demo_find_by_kitsu_task(project_name: str, kitsu_task_id: str):
    """Demonstrate finding versions by Kitsu task ID."""
    print(f"\n{'=' * 60}")
    print("DEMO 2: Find Versions by Kitsu Task")
    print(f"{'=' * 60}")

    versions = get_versions_for_kitsu_task(project_name, kitsu_task_id)

    print(f"\nFound {len(versions)} version(s) for Kitsu task: {kitsu_task_id}")
    print("-" * 60)

    for version in versions:
        product_name = get_product_name(project_name, version["productId"])
        version_num = version["version"]
        linking = version.get("data", {}).get("kitsu_linking", {})

        print(f"\n• {product_name} v{version_num:03d}")
        print(f"  ID: {version['id']}")
        if linking.get("ayon_version_url"):
            print(f"  URL: {linking['ayon_version_url']}")


def demo_find_by_kitsu_revision(project_name: str, kitsu_revision_id: str):
    """Demonstrate finding version by Kitsu revision ID."""
    print(f"\n{'=' * 60}")
    print("DEMO 3: Find Version by Kitsu Revision")
    print(f"{'=' * 60}")

    version = find_version_by_kitsu_revision(project_name, kitsu_revision_id)

    if version:
        product_name = get_product_name(project_name, version["productId"])
        version_num = version["version"]
        linking = version.get("data", {}).get("kitsu_linking", {})

        print(f"\nFound AYON version linked to Kitsu revision: {kitsu_revision_id}")
        print("-" * 60)
        print(f"\nProduct: {product_name} v{version_num:03d}")
        print(f"ID: {version['id']}")

        if linking.get("ayon_version_url"):
            print(f"URL: {linking['ayon_version_url']}")

        # Trace back to source
        print("\nTracing back to original source...")
        chain = trace_version_lineage(project_name, version["id"])
        print(f"Complete lineage: {len(chain)} versions in chain")

        for i, v in enumerate(chain, 1):
            prod = get_product_name(project_name, v["productId"])
            print(f"  {i}. {prod} v{v['version']:03d}")
    else:
        print(f"\nNo AYON version found for Kitsu revision: {kitsu_revision_id}")


def list_versions_with_linking(project_name: str, max_results: int = 10):
    """List recent versions that have Kitsu linking data."""
    print(f"\n{'=' * 60}")
    print("DEMO 4: List Recent Versions with Kitsu Linking")
    print(f"{'=' * 60}")

    versions = ayon_api.get_versions(project_name, fields=["id", "version", "productId", "data", "createdAt"])

    # Filter versions with kitsu_linking
    linked_versions = [v for v in versions if v.get("data", {}).get("kitsu_linking")]

    # Sort by creation date (newest first)
    linked_versions.sort(key=lambda v: v.get("createdAt", ""), reverse=True)

    print(f"\nFound {len(linked_versions)} version(s) with Kitsu linking data")
    print(f"Showing first {min(max_results, len(linked_versions))} results:")
    print("-" * 60)

    for version in linked_versions[:max_results]:
        product_name = get_product_name(project_name, version["productId"])
        version_num = version["version"]
        linking = version.get("data", {}).get("kitsu_linking", {})

        print(f"\n• {product_name} v{version_num:03d}")
        print(f"  ID: {version['id']}")
        print(f"  Created: {version.get('createdAt', 'unknown')}")

        if linking.get("kitsu_task_id"):
            print(f"  Kitsu Task: {linking['kitsu_task_id']}")
        if linking.get("source_version_id"):
            print(f"  Source Version: {linking['source_version_id']}")
        if linking.get("kitsu_revision_id"):
            print(f"  Kitsu Revision: {linking['kitsu_revision_id']}")


def main():
    """Main demo function."""
    if len(sys.argv) < 2:
        print("Usage: python kitsu_integration_demo.py <project_name> [folder_path] [product_name] [version_num]")
        print("\nExamples:")
        print("  # List all versions with linking data")
        print("  python kitsu_integration_demo.py Bollywoof")
        print("")
        print("  # Inspect specific version")
        print("  python kitsu_integration_demo.py Bollywoof /assets/character/chartest/modeling reviewMain 26")
        print("\nOptional environment variables:")
        print("  DEMO_VERSION_ID - Version ID to trace lineage")
        print("  DEMO_KITSU_TASK_ID - Kitsu task ID to search")
        print("  DEMO_KITSU_REVISION_ID - Kitsu revision ID to find")
        sys.exit(1)

    project_name = sys.argv[1]
    folder_path = sys.argv[2] if len(sys.argv) > 2 else None
    product_name = sys.argv[3] if len(sys.argv) > 3 else None
    version_num = int(sys.argv[4]) if len(sys.argv) > 4 else None

    # Initialize AYON connection
    print("\nInitializing AYON connection...")
    try:
        ayon_utils.set_connection()
        server_url = ayon_api.get_base_url()
        print(f"✓ Connected to AYON server: {server_url}")
    except Exception as e:
        print(f"✗ Failed to connect to AYON server: {e}")
        print("\nPlease ensure:")
        print("  1. AYON server is running")
        print("  2. rdo_ayon_utils is in PYTHONPATH")
        print("  3. AYON credentials are configured")
        sys.exit(1)

    print(f"\n{'#' * 60}")
    print(f"# Kitsu Integration Demo - Project: {project_name}")
    print(f"{'#' * 60}")

    # If specific version requested, show its details
    if folder_path and product_name and version_num:
        try:
            print(f"\n{'=' * 60}")
            print("DEMO: Inspect Specific Version")
            print(f"{'=' * 60}")

            print(f"\nQuerying: {folder_path} / {product_name} v{version_num:03d}")

            # First get the folder
            folder = ayon_api.get_folder_by_path(project_name, folder_path)
            if not folder:
                print("⚠ Folder not found")
                sys.exit(1)

            # Then get the product
            products = ayon_api.get_products(project_name, folder_ids=[folder["id"]], product_names=[product_name])
            product = next((p for p in products if p["name"] == product_name), None)
            if not product:
                print("⚠ Product not found")
                sys.exit(1)

            # Finally get the version
            version = ayon_api.get_version_by_name(project_name, version=version_num, product_id=product["id"])

            if not version:
                print("⚠ Version not found")
            else:
                linking = version.get("data", {}).get("kitsu_linking", {})

                print("\n✓ Found Version:")
                print(f"   ID: {version['id']}")
                print(f"   Version: v{version['version']:03d}")
                print(f"   Created: {version.get('createdAt', 'unknown')}")

                if linking:
                    print("\n" + "=" * 60)
                    print("Kitsu Integration Data - What We Can Track")
                    print("=" * 60)

                    # Show what questions we can answer
                    print("\n1️⃣  AYON to Kitsu Link:")
                    kitsu_task = linking.get("kitsu_task_id", "N/A")
                    print(f"   ✓ Kitsu Task ID: {kitsu_task}")
                    if kitsu_task != "N/A":
                        print(f"   → Can query Kitsu API for task: {kitsu_task}")
                        print("   → Can find all AYON versions for this Kitsu task")

                    print("\n2️⃣  Deep Link to AYON:")
                    ayon_url = linking.get("ayon_version_url", "N/A")
                    if ayon_url != "N/A":
                        print(f"   ✓ AYON URL: {ayon_url}")
                        print("   → Clickable link for navigating from Kitsu comments/UI to AYON")
                    else:
                        print("   ✗ No AYON URL stored")

                    print("\n3️⃣  Version Lineage Tracking:")
                    source_ver = linking.get("source_version_id")
                    if source_ver:
                        print(f"   ✓ Source Version ID: {source_ver}")
                        print("   → This version was created from another version")
                        print("\n   🔗 Tracing back to original workfile...")
                        try:
                            chain = trace_version_lineage(project_name, version["id"])
                            print(f"   → Found {len(chain)} version(s) in chain:")
                            for i, v in enumerate(chain, 1):
                                prod_name = get_product_name(project_name, v["productId"])
                                print(f"      {i}. {prod_name} v{v['version']:03d}")
                        except Exception as e:
                            print(f"   ✗ Error tracing: {e}")
                    else:
                        print("   ℹ️  Source Version ID: Not set")
                        print("   → This is likely the original workfile (not derived from another version)")
                        print("   → To enable lineage tracking:")
                        print("      • DCC publishers must set instance.data['sourceVersionId']")
                        print("      • Example: Render should reference the workfile it came from")

                    print("\n4️⃣  Kitsu Revision Link:")
                    kitsu_rev = linking.get("kitsu_revision_id")
                    if kitsu_rev:
                        print(f"   ✓ Kitsu Revision ID: {kitsu_rev}")
                        print("   → Can query: 'Which AYON version is Kitsu revision XYZ?'")
                    else:
                        print("   ℹ️  Kitsu Revision ID: Not set")
                        print("   → Set when this version is uploaded to Kitsu")
                        print("   → Enables reverse lookup: Kitsu revision → AYON version")

                    print("\n5️⃣  Additional Metadata:")
                    if linking.get("product_info"):
                        prod_info = linking["product_info"]
                        print(f"   • Product: {prod_info.get('name')} ({prod_info.get('type')})")
                    if linking.get("timestamp"):
                        print(f"   • Published: {linking.get('timestamp')}")

                    # Summary of capabilities
                    print("\n" + "=" * 60)
                    print("What This Enables")
                    print("=" * 60)
                    print("\n✓ Track which scene made which render:")
                    print("  → Set sourceVersionId when publishing render from workfile")
                    print("  → Query version chain: review → render → workfile")

                    print("\n✓ Track which render made which movie:")
                    print("  → Set sourceVersionId when creating review from render")
                    print("  → Trace full pipeline: review → render → workfile")

                    print("\n✓ Link AYON movie to Kitsu revision:")
                    print("  → kitsu_task_id links to Kitsu task (stored now ✓)")
                    print("  → kitsu_revision_id links to uploaded revision (set by upload process)")
                    print("  → Query both directions: AYON ↔ Kitsu")

                else:
                    print("\n⚠ No Kitsu linking data found for this version")
                    print("   Ensure Kitsu integration is enabled in project settings")

        except Exception as e:
            print(f"\n✗ Error inspecting version: {e}")
            import traceback

            traceback.print_exc()
    else:
        # Demo 4: List recent versions
        try:
            print(f"\n{'=' * 60}")
            print("DEMO: List Recent Versions with Kitsu Linking")
            print(f"{'=' * 60}")
            print("\nNote: This may take a while for large projects...")
            list_versions_with_linking(project_name, max_results=10)
        except Exception as e:
            print(f"\n✗ Error listing versions: {e}")
            import traceback

            traceback.print_exc()

    # Demo 1: Trace lineage (if version ID provided)
    import os

    version_id = os.getenv("DEMO_VERSION_ID")
    if version_id:
        try:
            demo_trace_lineage(project_name, version_id)
        except Exception as e:
            print(f"\nError tracing lineage: {e}")

    # Demo 2: Find by Kitsu task (if task ID provided)
    kitsu_task_id = os.getenv("DEMO_KITSU_TASK_ID")
    if kitsu_task_id:
        try:
            demo_find_by_kitsu_task(project_name, kitsu_task_id)
        except Exception as e:
            print(f"\nError finding by task: {e}")

    # Demo 3: Find by Kitsu revision (if revision ID provided)
    kitsu_revision_id = os.getenv("DEMO_KITSU_REVISION_ID")
    if kitsu_revision_id:
        try:
            demo_find_by_kitsu_revision(project_name, kitsu_revision_id)
        except Exception as e:
            print(f"\nError finding by revision: {e}")

    print(f"\n{'#' * 60}")
    print("# Demo Complete")
    print(f"{'#' * 60}\n")


if __name__ == "__main__":
    main()
