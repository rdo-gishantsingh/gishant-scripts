import json

import ayon_api


def fetch_all_product_types() -> list[dict]:
    """
    Fetch all product types from the AYON server.

    Returns:
        List of product type dictionaries
    """
    try:
        # Get all product types from server
        product_types = ayon_api.get_product_types()
        print(f"Found {len(product_types)} product types on server")
        return product_types
    except Exception as e:
        print(f"Error fetching product types: {e}")
        return []


def fetch_product_types_by_project(project_name: str) -> list[dict]:
    """
    Fetch product types specific to a project.

    Args:
        project_name: Name of the project

    Returns:
        List of product type dictionaries for the project
    """
    try:
        # Get project-specific product types
        project_product_types = ayon_api.get_project_product_types(project_name)
        print(f"Found {len(project_product_types)} product types for project '{project_name}'")
        return project_product_types
    except Exception as e:
        print(f"Error fetching product types for project '{project_name}': {e}")
        return []


def fetch_product_type_names() -> list[str]:
    """
    Fetch just the names of all product types.

    Returns:
        List of product type names
    """
    try:
        # Get product type names only
        product_type_names = ayon_api.get_product_type_names()
        print(f"Product type names: {product_type_names}")
        return product_type_names
    except Exception as e:
        print(f"Error fetching product type names: {e}")
        return []


def analyze_product_usage(project_name: str | None = None) -> dict:
    """
    Analyze how product types are being used across projects or within a specific project.

    Args:
        project_name: Optional project name to analyze. If None, analyzes all projects.

    Returns:
        Dictionary with usage statistics
    """
    usage_stats = {"product_types": {}, "projects_analyzed": [], "total_products": 0}

    try:
        if project_name:
            # Analyze specific project
            projects = [project_name]
        else:
            # Analyze all projects
            all_projects = ayon_api.get_projects()
            projects = [p["name"] for p in all_projects]

        usage_stats["projects_analyzed"] = projects

        for proj_name in projects:
            print(f"\nAnalyzing project: {proj_name}")

            try:
                # Get all products in the project
                products = ayon_api.get_products(proj_name)

                for product in products:
                    product_type = product.get("productType", "unknown")

                    if product_type not in usage_stats["product_types"]:
                        usage_stats["product_types"][product_type] = {
                            "count": 0,
                            "projects": set(),
                            "examples": [],
                        }

                    usage_stats["product_types"][product_type]["count"] += 1
                    usage_stats["product_types"][product_type]["projects"].add(proj_name)

                    # Store some examples
                    if len(usage_stats["product_types"][product_type]["examples"]) < 3:
                        usage_stats["product_types"][product_type]["examples"].append(
                            {
                                "project": proj_name,
                                "product_name": product["name"],
                                "folder_id": product.get("folderId"),
                            }
                        )

                usage_stats["total_products"] += len(products)
                print(f"  - Found {len(products)} products")

            except Exception as e:
                print(f"  - Error analyzing project '{proj_name}': {e}")
                continue

        # Convert sets to lists for JSON serialization
        for product_type in usage_stats["product_types"]:
            usage_stats["product_types"][product_type]["projects"] = list(
                usage_stats["product_types"][product_type]["projects"]
            )

        return usage_stats

    except Exception as e:
        print(f"Error in usage analysis: {e}")
        return usage_stats


def display_product_types_summary(product_types: list[dict]):
    """
    Display a formatted summary of product types.

    Args:
        product_types: List of product type dictionaries
    """
    if not product_types:
        print("No product types found.")
        return

    print(f"\n{'=' * 60}")
    print(f"PRODUCT TYPES SUMMARY ({len(product_types)} total)")
    print(f"{'=' * 60}")

    for i, product_type in enumerate(product_types, 1):
        name = product_type.get("name", "Unknown")
        icon = product_type.get("icon", "📦")
        color = product_type.get("color", "#888888")

        print(f"{i:2d}. {icon} {name}")
        print(f"    Color: {color}")

        # Show additional fields if they exist
        for key, value in product_type.items():
            if key not in ["name", "icon", "color"]:
                print(f"    {key}: {value}")
        print()


def display_usage_analysis(usage_stats: dict):
    """
    Display formatted usage analysis.

    Args:
        usage_stats: Dictionary with usage statistics
    """
    print(f"\n{'=' * 60}")
    print("PRODUCT TYPE USAGE ANALYSIS")
    print(f"{'=' * 60}")
    print(f"Projects analyzed: {len(usage_stats['projects_analyzed'])}")
    print(f"Total products: {usage_stats['total_products']}")
    print(f"Unique product types: {len(usage_stats['product_types'])}")

    if not usage_stats["product_types"]:
        print("No product types found in usage analysis.")
        return

    # Sort by usage count
    sorted_types = sorted(usage_stats["product_types"].items(), key=lambda x: x[1]["count"], reverse=True)

    print("\nProduct types by usage:")
    print(f"{'Rank':<4} {'Type':<20} {'Count':<8} {'Projects':<10} {'Examples'}")
    print("-" * 80)

    for rank, (product_type, stats) in enumerate(sorted_types, 1):
        project_count = len(stats["projects"])
        examples = ", ".join([ex["product_name"] for ex in stats["examples"][:2]])
        if len(stats["examples"]) > 2:
            examples += "..."

        print(f"{rank:<4} {product_type:<20} {stats['count']:<8} {project_count:<10} {examples}")


def export_to_json(data: dict, filename: str):
    """
    Export data to JSON file.

    Args:
        data: Dictionary to export
        filename: Output filename
    """
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Data exported to: {filename}")
    except Exception as e:
        print(f"Error exporting to JSON: {e}")


def main():
    """Main function to demonstrate product type fetching."""

    print("AYON Product Types Fetcher")
    print("=" * 40)

    # Check connection
    if not ayon_api.is_connection_created():
        print("Creating connection to AYON server...")
        try:
            # This will use environment variables or default settings
            ayon_api.create_connection()
            print("✓ Connected to AYON server")
        except Exception as e:
            print(f"✗ Failed to connect to AYON server: {e}")
            return

    # Get server info
    try:
        server_info = ayon_api.get_info()
        print(f"Server version: {server_info.get('version', 'Unknown')}")
        print(f"Server URL: {ayon_api.get_base_url()}")
    except Exception as e:
        print(f"Could not get server info: {e}")

    print("\n" + "=" * 40)

    # 1. Fetch all product types from server
    print("1. Fetching all product types from server...")
    all_product_types = fetch_all_product_types()
    display_product_types_summary(all_product_types)

    # 2. Fetch product type names only
    print("\n2. Fetching product type names...")
    product_type_names = fetch_product_type_names()

    # 3. Get available projects
    try:
        projects = ayon_api.get_projects()
        if projects:
            print(f"\n3. Available projects: {[p['name'] for p in projects[:5]]}")

            # Analyze first project as example
            if len(projects) > 0:
                example_project = projects[0]["name"]
                print(f"\n4. Fetching product types for project '{example_project}'...")
                project_product_types = fetch_product_types_by_project(example_project)

                if project_product_types:
                    print("Project-specific product types:")
                    for pt in project_product_types[:10]:  # Show first 10
                        print(f"  - {pt.get('name', 'Unknown')}")
    except Exception as e:
        print(f"Error fetching projects: {e}")

    # 4. Analyze product usage across projects
    print("\n5. Analyzing product type usage...")
    usage_stats = analyze_product_usage()
    display_usage_analysis(usage_stats)

    # 5. Export results
    export_data = {
        "all_product_types": all_product_types,
        "product_type_names": product_type_names,
        "usage_analysis": usage_stats,
        "timestamp": ayon_api.get_server_version(),  # Use server version as timestamp
    }

    export_to_json(export_data, "ayon_product_types_analysis.json")

    print(f"\n{'=' * 60}")
    print("Analysis complete!")
    print("Summary:")
    print(f"  - Total product types on server: {len(all_product_types)}")
    print(f"  - Product type names: {len(product_type_names)}")
    print(f"  - Projects analyzed: {len(usage_stats.get('projects_analyzed', []))}")
    print(f"  - Total products found: {usage_stats.get('total_products', 0)}")
    print("  - Results exported to: ayon_product_types_analysis.json")


if __name__ == "__main__":
    main()
