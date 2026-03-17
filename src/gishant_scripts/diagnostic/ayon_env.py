"""Resolve AYON environment variables from the local launcher storage.

Reads ``~/.local/share/ayon-launcher-local/`` to discover addon paths and
builds an env-var dict suitable for passing to ``subprocess.run(env=…)``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from gishant_scripts.diagnostic.config import LINUX, WINDOWS, linux_to_windows_path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ADDONS_JSON = "addons.json"


def _launcher_storage_dir() -> Path:
    """Return the AYON Launcher local storage directory."""
    return LINUX.ayon_storage_dir


def _addons_dir() -> Path:
    """Return the directory that contains all distributed addon folders."""
    return _launcher_storage_dir() / "addons"


def _read_addons_manifest() -> dict[str, dict[str, dict]]:
    """Parse ``addons/addons.json`` and return the full manifest.

    Structure::

        {
            "<addon_name>": {
                "<version>": {
                    "source": {...},
                    "checksum": "...",
                    "distributed_dt": "2026-03-01 23:14:14"
                },
                ...
            },
            ...
        }
    """
    manifest_path = _addons_dir() / _ADDONS_JSON
    if not manifest_path.exists():
        logger.warning("Addons manifest not found at %s", manifest_path)
        return {}

    with manifest_path.open() as fh:
        return json.load(fh)


def _latest_version_for_addon(
    addon_name: str,
    manifest: dict[str, dict[str, dict]] | None = None,
) -> str | None:
    """Return the most-recently distributed version string for *addon_name*.

    Uses ``distributed_dt`` from the manifest to determine recency — this
    reflects the last version the AYON server pushed to this workstation.
    """
    if manifest is None:
        manifest = _read_addons_manifest()

    versions = manifest.get(addon_name)
    if not versions:
        return None

    # Pick the version with the newest distributed_dt timestamp.
    return max(versions, key=lambda v: versions[v].get("distributed_dt", ""))


def _addon_folder_name(addon_name: str, version: str) -> str:
    """Build the on-disk folder name for an addon, e.g. ``maya_0.4.17+dev.rdo.6``."""
    return f"{addon_name}_{version}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_addon_path(addon_name: str) -> Path | None:
    """Find an addon's code directory in the launcher storage.

    Returns the path to the addon folder (e.g.
    ``~/.local/share/ayon-launcher-local/addons/maya_0.4.17+dev.rdo.6``)
    or ``None`` if the addon is not present.
    """
    manifest = _read_addons_manifest()
    version = _latest_version_for_addon(addon_name, manifest)
    if version is None:
        logger.debug("Addon %r not found in manifest", addon_name)
        return None

    folder = _addons_dir() / _addon_folder_name(addon_name, version)
    if not folder.is_dir():
        logger.warning(
            "Addon %r version %s listed in manifest but directory missing: %s",
            addon_name,
            version,
            folder,
        )
        return None

    return folder


def list_all_addon_paths() -> dict[str, Path]:
    """Return a mapping of ``{addon_name: path}`` for every addon at its latest version."""
    manifest = _read_addons_manifest()
    paths: dict[str, Path] = {}
    for addon_name in manifest:
        version = _latest_version_for_addon(addon_name, manifest)
        if version is None:
            continue
        folder = _addons_dir() / _addon_folder_name(addon_name, version)
        if folder.is_dir():
            paths[addon_name] = folder
    return paths


def resolve_ayon_env(
    project_name: str,
    folder_path: str,
    task_name: str | None = None,
    target: str = "linux",
) -> dict[str, str]:
    """Return a dict of env vars ready to pass to ``subprocess.run(env=…)``.

    Parameters
    ----------
    project_name:
        The AYON project name (e.g. ``"MyProject"``).
    folder_path:
        The AYON folder path (e.g. ``"/assets/hero/modeling"``).
    task_name:
        Optional AYON task name.
    target:
        ``"linux"`` or ``"windows"``.  Controls path separators and the
        ``AYON_SERVER_URL`` value.

    Returns
    -------
    dict[str, str]
        Environment variables including ``AYON_SERVER_URL``,
        ``AYON_PROJECT_NAME``, ``PYTHONPATH``, etc.
    """
    is_windows = target.lower() == "windows"
    path_sep = ";" if is_windows else ":"
    config = WINDOWS if is_windows else LINUX

    # -- Collect addon PYTHONPATH entries ------------------------------------
    addon_paths = list_all_addon_paths()
    python_paths: list[str] = []
    for _addon_name, addon_dir in sorted(addon_paths.items()):
        path_str = str(addon_dir)
        if is_windows:
            path_str = linux_to_windows_path(path_str)
        python_paths.append(path_str)

    # -- Storage dir --------------------------------------------------------
    storage_dir = str(LINUX.ayon_storage_dir)
    if is_windows:
        storage_dir = str(config.ayon_storage_dir)

    # -- Build env dict -----------------------------------------------------
    env: dict[str, str] = {
        "AYON_SERVER_URL": config.ayon_server_url,
        "AYON_PROJECT_NAME": project_name,
        "AYON_FOLDER_PATH": folder_path,
        "PYTHONPATH": path_sep.join(python_paths),
        "AYON_LAUNCHER_STORAGE_DIR": storage_dir,
        "AYON_LAUNCHER_LOCAL_DIR": storage_dir,
    }

    if task_name is not None:
        env["AYON_TASK_NAME"] = task_name

    return env
