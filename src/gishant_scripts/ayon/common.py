"""Common utilities for AYON bundle operations.

This module re-exports all public symbols from the focused sub-modules
(connection, bundles, diff, ui) so that existing imports such as
``from gishant_scripts.ayon.common import setup_ayon_connection`` continue
to work without modification.
"""

from __future__ import annotations

from gishant_scripts.ayon.bundles import (
    BundleNotFoundError,
    fetch_all_bundles,
    get_all_projects,
    get_bundle_by_name,
    get_bundle_settings,
    get_project_anatomy,
    get_project_settings,
)
from gishant_scripts.ayon.connection import (
    AYONConnectionError,
    setup_ayon_connection,
)
from gishant_scripts.ayon.diff import (
    compare_settings,
    flatten_dict,
    get_differences,
)
from gishant_scripts.ayon.ui import (
    interactive_bundle_selection,
    interactive_project_selection,
)

__all__ = [
    # connection
    "AYONConnectionError",
    "setup_ayon_connection",
    # bundles
    "BundleNotFoundError",
    "fetch_all_bundles",
    "get_all_projects",
    "get_bundle_by_name",
    "get_bundle_settings",
    "get_project_anatomy",
    "get_project_settings",
    # diff
    "compare_settings",
    "flatten_dict",
    "get_differences",
    # ui
    "interactive_bundle_selection",
    "interactive_project_selection",
]
