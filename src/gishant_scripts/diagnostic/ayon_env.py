"""Resolve AYON environment variables from the local launcher storage.

Reads ``~/.local/share/ayon-launcher-local/`` to discover addon paths and
builds an env-var dict suitable for passing to ``subprocess.run(env=…)``.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import sys
from pathlib import Path

from gishant_scripts.diagnostic.config import (
    LINUX,
    WINDOWS,
    linux_to_windows_path,
)
from gishant_scripts.diagnostic.test_server_guard import (
    resolve_and_validate_test_env,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ADDONS_JSON = "addons.json"

# Project root and venv paths — resolved once at import time.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]  # …/gishant-scripts
_SRC = _PROJECT_ROOT / "src"
_SITE_PKGS = _PROJECT_ROOT / ".venv" / "lib" / "python3.11" / "site-packages"
_WIN_VENV_SITE_PKGS = r"C:\Users\gisi\.venvs\gishant-scripts\Lib\site-packages"
_WIN_SYS_SITE_PKGS = r"C:\Users\gisi\AppData\Local\Programs\Python\Python311\Lib\site-packages"


def _dedupe_keep_order(values: list[str]) -> list[str]:
    """Return a de-duplicated list preserving first occurrence order."""
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def _windows_storage_candidates(config_storage_dir: str) -> list[str]:
    """Return candidate Windows launcher storage dirs in preferred order.

    We prefer launcher-local/prod locations because they contain addon and
    dependency payloads on the Windows host used by Unreal diagnostics.
    """
    user = os.getenv("USERNAME", "gisi")
    local_appdata = os.getenv("LOCALAPPDATA", rf"C:\Users\{user}\AppData\Local")
    ynput_base = pathlib.PureWindowsPath(local_appdata) / "Ynput"

    candidates = [
        str(ynput_base / "ayon-launcher-local"),
        str(ynput_base / "ayon-launcher-prod"),
        config_storage_dir,
        str(ynput_base / "AYON"),
    ]
    return _dedupe_keep_order(candidates)


def _read_site_id(is_windows: bool) -> str:
    """Read the AYON site ID from the launcher storage dir."""
    storage = _launcher_storage_dir()
    site_id_file = storage / "site_id"
    if site_id_file.exists():
        return site_id_file.read_text(encoding="utf-8").strip()
    return ""


def _launcher_storage_dir() -> Path:
    """Return the AYON Launcher local storage directory for the current OS."""
    if sys.platform == "win32":
        return Path(WINDOWS.ayon_storage_dir)
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


def _load_api_key_from_dotenv() -> str:
    """Search candidate .env paths for AYON_TEST_API_KEY.

    On Linux: ``~/.rdo/.env``.
    On Windows: ``~/.rdo/.env`` first (works if a symlink exists), then the
    NAS UNC path as fallback.
    """
    candidates = [Path.home() / ".rdo" / ".env"]
    if sys.platform == "win32":
        _nas = os.getenv("NAS_HOSTNAME", "rdoshyd")
        candidates.append(Path(rf"\\{_nas}\tech\users\gisi\.rdo\.env"))

    for env_path in candidates:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = raw_line.strip()
            if stripped.startswith("AYON_TEST_API_KEY="):
                return stripped.split("=", 1)[1].strip().strip('"')
    return ""


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

    # Always source diagnostic credentials from ~/.rdo/.env TEST variables.
    # Intentionally resolve for linux because this file is guaranteed to exist
    # on the office Linux box where diagnostics are orchestrated.
    test_env = resolve_and_validate_test_env("linux")
    test_server_url = test_env["AYON_SERVER_URL"]
    test_api_key = test_env["AYON_API_KEY"]

    # -- Collect addon PYTHONPATH entries ------------------------------------
    addon_paths = list_all_addon_paths()
    python_paths: list[str] = []

    if is_windows:
        win_storage_candidates = _windows_storage_candidates(str(WINDOWS.ayon_storage_dir))

        # Windows has its own addon storage — use addon folder names from
        # the manifest but prefix with the Windows storage base path.
        for _addon_name, addon_dir in sorted(addon_paths.items()):
            folder_name = addon_dir.name  # e.g. "core_1.6.7+dev.rdo.4"
            for storage_dir in win_storage_candidates:
                win_addons_base = str(pathlib.PureWindowsPath(storage_dir) / "addons")
                addon_path = f"{win_addons_base}\\{folder_name}"
                python_paths.append(addon_path)
                # Add vendor/python subdirs (contains qargparse, scriptsmenu, etc.)
                if _addon_name == "core":
                    python_paths.append(f"{addon_path}\\ayon_core\\vendor\\python")
    else:
        # Prepend the maya addon's startup dir so Maya batch executes
        # userSetup.py before processing the diagnostic script.
        # This mirrors what the AYON launcher does via add_implementation_envs.
        _maya_addon = addon_paths.get("maya")
        if _maya_addon:
            _startup = _maya_addon / "ayon_maya" / "startup"
            if _startup.is_dir():
                python_paths.insert(0, str(_startup))
        for _addon_name, addon_dir in sorted(addon_paths.items()):
            python_paths.append(str(addon_dir))
            if _addon_name == "core":
                vendor_path = addon_dir / "ayon_core" / "vendor" / "python"
                if vendor_path.is_dir():
                    python_paths.append(str(vendor_path))

    # -- Dependency packages (bundled third-party libs like clique, semver) --
    # Always scan from the Linux storage (we're running on Linux), but convert
    # paths to Windows format when the target is Windows.
    dep_packages_dir = LINUX.ayon_storage_dir / "dependency_packages"
    if dep_packages_dir.is_dir():
        if is_windows:
            for storage_dir in win_storage_candidates:
                win_dep_base = str(pathlib.PureWindowsPath(storage_dir) / "dependency_packages")
                for dep_zip in sorted(dep_packages_dir.glob("*.zip")):
                    python_paths.extend(
                        f"{win_dep_base}\\{dep_zip.name}\\{subdir}" for subdir in ("dependencies", "runtime")
                    )
        else:
            for dep_zip in sorted(dep_packages_dir.glob("*.zip")):
                python_paths.extend(str(dep_zip / subdir) for subdir in ("dependencies", "runtime"))

    # -- gishant-scripts src + venv paths (ayon_api, test helpers, etc.) -----
    if is_windows:
        win_src = linux_to_windows_path(str(_SRC), unc=True)
        win_site_pkgs = linux_to_windows_path(str(_SITE_PKGS), unc=True)
        python_paths.extend([_WIN_SYS_SITE_PKGS, win_src, win_site_pkgs, _WIN_VENV_SITE_PKGS])
    else:
        python_paths.extend([str(_SRC), str(_SITE_PKGS)])
    python_paths = _dedupe_keep_order(python_paths)

    # -- Storage dir --------------------------------------------------------
    storage_dir = str(LINUX.ayon_storage_dir)
    if is_windows:
        storage_dir = _windows_storage_candidates(str(config.ayon_storage_dir))[0]

    # -- Load API key from RDO shared credentials ----------------------------
    api_key = test_api_key

    # -- Resolve active bundle name -----------------------------------------
    bundle_name = ""
    try:
        import ayon_api as _ayon_api

        _prev_url = os.environ.get("AYON_SERVER_URL")
        _prev_key = os.environ.get("AYON_API_KEY")
        os.environ["AYON_SERVER_URL"] = test_server_url
        os.environ["AYON_API_KEY"] = api_key
        bundles_payload = _ayon_api.get_bundles() or {}
        production_bundle = bundles_payload.get("productionBundle")
        staging_bundle = bundles_payload.get("stagingBundle")
        all_bundle_names = [
            bundle.get("name")
            for bundle in bundles_payload.get("bundles", [])
            if bundle.get("name")
        ]

        # Preserve explicit override if user set AYON_BUNDLE_NAME manually.
        explicit_bundle = os.environ.get("AYON_BUNDLE_NAME")
        if explicit_bundle:
            bundle_name = explicit_bundle

        # Pick the best bundle for diagnostics:
        # - must have non-empty core + host settings
        # - prefer bundles that also define rdo_kitsu.server when addon is present
        target_addon = "maya" if not is_windows else "unreal"
        has_kitsu_addon = "rdo_kitsu" in addon_paths
        candidates = [
            c
            for c in (bundle_name, production_bundle, staging_bundle, *all_bundle_names)
            if c
        ]
        deduped_candidates = list(dict.fromkeys(candidates))
        best_candidate = ""
        best_score = -1
        settings_variant = os.getenv("AYON_DEFAULT_SETTINGS_VARIANT", "production")
        for candidate in deduped_candidates:
            response = _ayon_api.get(
                f"settings?bundle_name={candidate}&variant={settings_variant}&project_name={project_name}"
            )
            if response.status_code != 200:
                continue

            addon_settings = {
                addon.get("name"): addon.get("settings") or {}
                for addon in response.data.get("addons", [])
            }
            core_settings = addon_settings.get("core") or {}
            host_settings = addon_settings.get(target_addon) or {}
            if not (core_settings and host_settings):
                continue

            score = 2
            if has_kitsu_addon:
                kitsu_settings = addon_settings.get("rdo_kitsu") or {}
                if "server" in kitsu_settings:
                    score += 1
                else:
                    score -= 1

            if score > best_score:
                best_score = score
                best_candidate = candidate

            # Good enough: explicit or production/staging candidate with max score.
            if score >= 3 and candidate in {explicit_bundle, production_bundle, staging_bundle}:
                best_candidate = candidate
                break

        if best_candidate:
            bundle_name = best_candidate

        # Last-resort fallback to production bundle if everything is empty.
        if not bundle_name:
            bundle_name = production_bundle or staging_bundle or ""

        # Restore original env
        if _prev_url is not None:
            os.environ["AYON_SERVER_URL"] = _prev_url
        if _prev_key is not None:
            os.environ["AYON_API_KEY"] = _prev_key
    except Exception:
        logger.debug("Failed to resolve AYON bundle name", exc_info=True)

    # -- Build env dict -----------------------------------------------------
    env: dict[str, str] = {
        "AYON_SERVER_URL": test_server_url,
        "AYON_API_KEY": api_key,
        "AYON_BUNDLE_NAME": bundle_name,
        "AYON_PROJECT_NAME": project_name,
        "AYON_FOLDER_PATH": folder_path,
        "AYON_UNREAL_VERSION": "5.5" if is_windows else "",
        "AYON_MAYA_VERSION": "2025" if not is_windows else "",
        "AYON_SITE_ID": _read_site_id(is_windows),
        "AYON_WORKDIR": str(Path(LINUX.diagnostic_base) / "_workdir")
        if not is_windows
        else r"C:\Users\gisi\.ayon_diagnostic_workdir",
        "AYON_APP_NAME": "maya/2025" if not is_windows else "unreal/5.5",
        "PYTHONPATH": path_sep.join(python_paths),
        "AYON_LAUNCHER_STORAGE_DIR": storage_dir,
        "AYON_LAUNCHER_LOCAL_DIR": storage_dir,
        "AYON_LAUNCHER_STORAGE_CANDIDATES": "|".join(_windows_storage_candidates(str(config.ayon_storage_dir)))
        if is_windows
        else storage_dir,
        # Qt offscreen mode — prevents headless crashes when AYON imports
        # qtawesome/qtpy in environments without a display (e.g. UE -NullRHI).
        "QT_QPA_PLATFORM": "offscreen",
        "AYON_HEADLESS_MODE": "1",
    }

    if task_name is not None:
        env["AYON_TASK_NAME"] = task_name

    return env
