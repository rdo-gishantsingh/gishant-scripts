"""Core function to fetch representation using AYON API.

This module provides a generic function to fetch representations for any product
in a given folder, with automatic folder path resolution.
"""

from typing import Optional, Dict, Any

try:
    import ayon_api
except ImportError:
    ayon_api = None


def get_representation(
    project_name: str,
    folder_path: str,
    product_name: str,
    representation_name: str = "wav",
) -> Optional[Dict[str, Any]]:
    """
    Fetches the latest representation for a given product in a folder.

    Args:
        project_name: The project name
        folder_path: The folder path (can be partial, will be resolved automatically)
        product_name: The product name (e.g., "audioMain", "layoutMain")
        representation_name: The representation name (default: "wav")

    Returns:
        The full representation dictionary, or None if not found

    Raises:
        ImportError: If ayon_api is not installed
        RuntimeError: If AYON connection is not established
    """
    if ayon_api is None:
        raise ImportError("ayon-python-api not installed. Install it with: pip install ayon-python-api")

    if not ayon_api.is_connection_created():
        raise RuntimeError("AYON connection not established. Call setup_ayon_connection() first.")

    # Get folder entity - try the provided path first
    folder = ayon_api.get_folder_by_path(project_name, folder_path, fields=["id", "name", "path"])

    # If not found, try to find by folder name (last part of path)
    if not folder:
        folder_name = folder_path.split("/")[-1]
        all_folders = list(
            ayon_api.get_folders(
                project_name,
                folder_names=[folder_name],
                fields=["id", "name", "path"],
            )
        )

        if len(all_folders) == 1:
            # Found exactly one match, use it
            folder = all_folders[0]
        elif len(all_folders) > 1:
            # Multiple matches - try to find one that matches the path pattern
            matching_folder = None
            for f in all_folders:
                full_path = f.get("path", "")
                # Check if the provided path is a suffix of the full path
                if full_path.endswith(folder_path) or folder_path in full_path:
                    matching_folder = f
                    break

            if matching_folder:
                folder = matching_folder
            else:
                # Return None if no match found - let CLI handle the error message
                return None
        else:
            # No folders found
            return None

    if not folder:
        return None

    # Get product
    product = ayon_api.get_product_by_name(
        project_name,
        product_name,
        folder["id"],
        fields=["id", "name"],
    )
    if not product:
        return None

    # Get latest version
    last_version = ayon_api.get_last_version_by_product_id(
        project_name,
        product["id"],
        active=True,
        fields=["id", "version"],
    )
    if not last_version:
        return None

    # Get representation with all fields including attrib, files, and data
    # Explicitly request files and data to ensure they're included
    representations = ayon_api.get_representations(
        project_name,
        version_ids=[last_version["id"]],
        representation_names=[representation_name],
        fields=None,  # Get all fields including attrib, files, and data
    )
    representations = list(representations)

    if len(representations) == 0:
        return None
    elif len(representations) > 1:
        raise ValueError(f"Multiple '{representation_name}' representations found for version {last_version['id']}")
    else:
        return representations[0]
