"""AYON settings comparison and diff utilities.

Provides functions for flattening nested dictionaries, comparing bundle settings,
and extracting structured differences between two bundles.
"""

from __future__ import annotations

from typing import Any


def flatten_dict(
    data: dict[str, Any],
    parent_key: str = "",
    sep: str = ".",
    max_depth: int | None = None,
    current_depth: int = 0,
) -> dict[str, Any]:
    """Flatten a nested dictionary into dot-notation keys.

    Args:
        data: Dictionary to flatten
        parent_key: Parent key prefix
        sep: Separator for nested keys
        max_depth: Maximum depth to flatten (None for unlimited)
        current_depth: Current depth level

    Returns:
        Flattened dictionary

    """
    items = []

    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key

        if max_depth is not None and current_depth >= max_depth:
            items.append((new_key, value))
        elif isinstance(value, dict) and value:
            items.extend(
                flatten_dict(
                    value,
                    new_key,
                    sep=sep,
                    max_depth=max_depth,
                    current_depth=current_depth + 1,
                ).items()
            )
        else:
            items.append((new_key, value))

    return dict(items)


def compare_settings(
    bundle1_data: dict[str, Any],
    bundle1_settings: dict[str, Any],
    bundle2_data: dict[str, Any],
    bundle2_settings: dict[str, Any],
    bundle1_project_settings: dict[str, Any] | None = None,
    bundle2_project_settings: dict[str, Any] | None = None,
    anatomy1: dict[str, Any] | None = None,
    anatomy2: dict[str, Any] | None = None,
    max_depth: int | None = None,
) -> dict[str, Any]:
    """Compare settings between two bundles.

    Args:
        bundle1_data: First bundle metadata
        bundle1_settings: First bundle studio settings
        bundle2_data: Second bundle metadata
        bundle2_settings: Second bundle studio settings
        bundle1_project_settings: First bundle project settings (optional)
        bundle2_project_settings: Second bundle project settings (optional)
        anatomy1: First project anatomy (optional)
        anatomy2: Second project anatomy (optional)
        max_depth: Maximum depth for comparison

    Returns:
        Dictionary with comparison results

    """
    comparison = {
        "metadata": {
            "bundle1": {
                "name": bundle1_data["name"],
                "installerVersion": bundle1_data.get("installerVersion"),
                "isProduction": bundle1_data.get("isProduction", False),
                "isStaging": bundle1_data.get("isStaging", False),
                "isDev": bundle1_data.get("isDev", False),
                "createdAt": bundle1_data.get("createdAt"),
                "updatedAt": bundle1_data.get("updatedAt"),
            },
            "bundle2": {
                "name": bundle2_data["name"],
                "installerVersion": bundle2_data.get("installerVersion"),
                "isProduction": bundle2_data.get("isProduction", False),
                "isStaging": bundle2_data.get("isStaging", False),
                "isDev": bundle2_data.get("isDev", False),
                "createdAt": bundle2_data.get("createdAt"),
                "updatedAt": bundle2_data.get("updatedAt"),
            },
        },
        "addons": {
            "bundle1": bundle1_data.get("addons", {}),
            "bundle2": bundle2_data.get("addons", {}),
        },
        "dependencies": {
            "bundle1": bundle1_data.get("dependencyPackages", {}),
            "bundle2": bundle2_data.get("dependencyPackages", {}),
        },
        "settings": {
            "bundle1": flatten_dict(bundle1_settings, max_depth=max_depth),
            "bundle2": flatten_dict(bundle2_settings, max_depth=max_depth),
        },
    }

    # Add project settings if provided
    if bundle1_project_settings is not None and bundle2_project_settings is not None:
        comparison["project_settings"] = {
            "bundle1": flatten_dict(bundle1_project_settings, max_depth=max_depth),
            "bundle2": flatten_dict(bundle2_project_settings, max_depth=max_depth),
        }

    # Add anatomy if provided
    if anatomy1 is not None and anatomy2 is not None:
        comparison["anatomy"] = {
            "bundle1": flatten_dict(anatomy1, max_depth=max_depth),
            "bundle2": flatten_dict(anatomy2, max_depth=max_depth),
        }

    return comparison


def get_differences(
    comparison: dict[str, Any], only_diff: bool = False, addon_filter: list[str] | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Extract differences from comparison results.

    Args:
        comparison: Comparison results from compare_settings()
        only_diff: If True, only include differences; if False, include all settings
        addon_filter: Optional list of addon names to filter results

    Returns:
        Dictionary with lists of differences for each category

    """
    differences = {
        "metadata": [],
        "addons": [],
        "dependencies": [],
        "settings": [],
        "project_settings": [],
        "anatomy": [],
    }

    # Metadata differences
    for key in comparison["metadata"]["bundle1"].keys():
        val1 = comparison["metadata"]["bundle1"][key]
        val2 = comparison["metadata"]["bundle2"][key]

        if not only_diff or val1 != val2:
            differences["metadata"].append(
                {"key": key, "bundle1": val1, "bundle2": val2, "status": "changed" if val1 != val2 else "unchanged"}
            )

    # Addon version differences
    all_addons = set(comparison["addons"]["bundle1"].keys()) | set(comparison["addons"]["bundle2"].keys())

    # Apply addon filter if specified
    if addon_filter:
        all_addons = {addon for addon in all_addons if addon in addon_filter}

    for addon in sorted(all_addons):
        val1 = comparison["addons"]["bundle1"].get(addon)
        val2 = comparison["addons"]["bundle2"].get(addon)

        if not only_diff or val1 != val2:
            status = "unchanged"
            if val1 is None:
                status = "added"
            elif val2 is None:
                status = "removed"
            elif val1 != val2:
                status = "changed"

            differences["addons"].append({"key": addon, "bundle1": val1, "bundle2": val2, "status": status})

    # Dependency differences
    all_platforms = set(comparison["dependencies"]["bundle1"].keys()) | set(
        comparison["dependencies"]["bundle2"].keys()
    )
    for platform in sorted(all_platforms):
        val1 = comparison["dependencies"]["bundle1"].get(platform)
        val2 = comparison["dependencies"]["bundle2"].get(platform)

        if not only_diff or val1 != val2:
            status = "unchanged"
            if val1 is None:
                status = "added"
            elif val2 is None:
                status = "removed"
            elif val1 != val2:
                status = "changed"

            differences["dependencies"].append({"key": platform, "bundle1": val1, "bundle2": val2, "status": status})

    # Settings differences
    all_keys = set(comparison["settings"]["bundle1"].keys()) | set(comparison["settings"]["bundle2"].keys())

    # Apply addon filter if specified
    if addon_filter:
        all_keys = {
            key for key in all_keys if any(key.startswith(f"{addon}.") or key == addon for addon in addon_filter)
        }

    for key in sorted(all_keys):
        val1 = comparison["settings"]["bundle1"].get(key)
        val2 = comparison["settings"]["bundle2"].get(key)

        if not only_diff or val1 != val2:
            status = "unchanged"
            if val1 is None:
                status = "added"
            elif val2 is None:
                status = "removed"
            elif val1 != val2:
                status = "changed"

            differences["settings"].append({"key": key, "bundle1": val1, "bundle2": val2, "status": status})

    # Project settings differences (if present)
    if "project_settings" in comparison:
        all_keys = set(comparison["project_settings"]["bundle1"].keys()) | set(
            comparison["project_settings"]["bundle2"].keys()
        )

        # Apply addon filter if specified
        if addon_filter:
            all_keys = {
                key for key in all_keys if any(key.startswith(f"{addon}.") or key == addon for addon in addon_filter)
            }

        for key in sorted(all_keys):
            val1 = comparison["project_settings"]["bundle1"].get(key)
            val2 = comparison["project_settings"]["bundle2"].get(key)

            if not only_diff or val1 != val2:
                status = "unchanged"
                if val1 is None:
                    status = "added"
                elif val2 is None:
                    status = "removed"
                elif val1 != val2:
                    status = "changed"

                differences["project_settings"].append({"key": key, "bundle1": val1, "bundle2": val2, "status": status})

    # Anatomy differences (if present)
    if "anatomy" in comparison:
        all_keys = set(comparison["anatomy"]["bundle1"].keys()) | set(comparison["anatomy"]["bundle2"].keys())
        for key in sorted(all_keys):
            val1 = comparison["anatomy"]["bundle1"].get(key)
            val2 = comparison["anatomy"]["bundle2"].get(key)

            if not only_diff or val1 != val2:
                status = "unchanged"
                if val1 is None:
                    status = "added"
                elif val2 is None:
                    status = "removed"
                elif val1 != val2:
                    status = "changed"

                differences["anatomy"].append({"key": key, "bundle1": val1, "bundle2": val2, "status": status})

    return differences
