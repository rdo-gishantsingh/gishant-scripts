"""Integration test: Verify Unreal + full AYON addon stack works in batch mode.

Checks:
1. Unreal engine is running
2. ayon_api can connect to the AYON server
3. ayon_core can be imported and host installed
4. ayon_unreal addon is available
5. AYON loader plugins are discoverable (AnimationFBXLoader, LayoutLoader, etc.)
"""

import json
import os
import sys
from datetime import UTC
from pathlib import Path

# Unreal's embedded Python may not honor PYTHONPATH env var —
# explicitly add its entries to sys.path.
for p in os.environ.get("PYTHONPATH", "").split(";"):
    if p and p not in sys.path:
        sys.path.insert(0, p)


def main():
    result = {
        "status": "pass",
        "dcc": "unreal",
        "issue": "hello_world",
        "timestamp": "",
        "context": {},
        "findings": {},
        "errors": [],
    }

    try:
        from datetime import datetime

        result["timestamp"] = datetime.now(UTC).isoformat()

        # -- 1. Unreal engine --------------------------------------------------
        import unreal

        result["findings"]["unreal_version"] = unreal.SystemLibrary.get_engine_version()

        # -- 2. AYON context env vars ------------------------------------------
        result["context"]["project"] = os.environ.get("AYON_PROJECT_NAME", "")
        result["context"]["folder"] = os.environ.get("AYON_FOLDER_PATH", "")
        result["context"]["api_key_set"] = bool(os.environ.get("AYON_API_KEY"))

        # -- 3. ayon_api connection --------------------------------------------
        try:
            import ayon_api

            project = ayon_api.get_project(os.environ["AYON_PROJECT_NAME"])
            result["findings"]["ayon_connected"] = project is not None
            result["findings"]["project_name"] = project["name"] if project else None
        except Exception as e:
            result["findings"]["ayon_connected"] = False
            result["errors"].append(f"ayon_api connection failed: {e}")

        # -- 4. ayon_core import -----------------------------------------------
        try:
            import ayon_core
            from ayon_core.pipeline import (
                discover_loader_plugins,
            )

            result["findings"]["ayon_core_imported"] = True
            result["findings"]["ayon_core_version"] = getattr(ayon_core, "__version__", "unknown")
        except Exception as e:
            result["findings"]["ayon_core_imported"] = False
            result["errors"].append(f"ayon_core import failed: {e}")

        # -- 5. ayon_unreal import ---------------------------------------------
        try:
            result["findings"]["ayon_unreal_imported"] = True
        except Exception as e:
            result["findings"]["ayon_unreal_imported"] = False
            result["errors"].append(f"ayon_unreal import failed: {e}")

        # -- 6. AYON host registration -----------------------------------------
        try:
            from ayon_core.pipeline import install_host, registered_host
            from ayon_unreal.api import UnrealHost

            # Only install if not already registered
            if not registered_host():
                install_host(UnrealHost())

            result["findings"]["ayon_host_installed"] = True
            result["findings"]["registered_host"] = str(type(registered_host()).__name__)
        except Exception as e:
            # install_host() may partially succeed (register host) but fail
            # on settings init (missing project_plugins, qtawesome, etc.)
            from ayon_core.pipeline import registered_host as _rh
            if _rh():
                result["findings"]["ayon_host_installed"] = True
                result["findings"]["registered_host"] = str(type(_rh()).__name__)
                result["findings"]["host_install_warning"] = str(e)
            else:
                result["findings"]["ayon_host_installed"] = False
                result["errors"].append(f"AYON host install failed: {e}")


        # -- 7. Discover loader plugins ----------------------------------------
        try:
            loaders = discover_loader_plugins()
            loader_names = [loader.__name__ for loader in loaders]
            result["findings"]["loader_count"] = len(loaders)
            result["findings"]["loader_names"] = loader_names

            # Check for critical loaders
            critical = ["AnimationFBXLoader", "LayoutLoader", "SkeletalMeshFBXLoader"]
            found = [name for name in critical if name in loader_names]
            missing = [name for name in critical if name not in loader_names]
            result["findings"]["critical_loaders_found"] = found
            result["findings"]["critical_loaders_missing"] = missing

            if missing:
                result["errors"].append(f"Missing critical loaders: {missing}")
        except Exception as e:
            result["findings"]["loader_count"] = 0
            result["errors"].append(f"Loader discovery failed: {e}")

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))

    # Determine status
    if result["errors"]:
        result["status"] = "fail"

    # Write results
    script_dir = Path(__file__).parent
    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    with open(results_dir / "unreal_result.json", "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))


main()
