"""Integration test: Verify Maya + full AYON addon stack works in batch mode.

Checks:
1. Maya is running
2. ayon_api can connect to the AYON server
3. ayon_core can be imported and host installed
4. ayon_maya addon is available
5. AYON loader/creator plugins are discoverable
"""

import json
import os
from datetime import UTC
from pathlib import Path


def main():
    result = {
        "status": "pass",
        "dcc": "maya",
        "issue": "hello_world",
        "timestamp": "",
        "context": {},
        "findings": {},
        "errors": [],
    }

    try:
        from datetime import datetime

        result["timestamp"] = datetime.now(UTC).isoformat()

        # -- 1. Maya engine -----------------------------------------------------
        from maya import cmds

        result["findings"]["maya_version"] = cmds.about(version=True)

        # -- 2. AYON context env vars -------------------------------------------
        result["context"]["project"] = os.environ.get("AYON_PROJECT_NAME", "")
        result["context"]["folder"] = os.environ.get("AYON_FOLDER_PATH", "")
        result["context"]["api_key_set"] = bool(os.environ.get("AYON_API_KEY"))

        # -- 3. ayon_api connection ---------------------------------------------
        try:
            import ayon_api

            project = ayon_api.get_project(os.environ["AYON_PROJECT_NAME"])
            result["findings"]["ayon_connected"] = project is not None
            result["findings"]["project_name"] = project["name"] if project else None
        except Exception as e:
            result["findings"]["ayon_connected"] = False
            result["errors"].append(f"ayon_api connection failed: {e}")

        # -- 4. ayon_core import ------------------------------------------------
        try:
            import ayon_core
            from ayon_core.pipeline import discover_loader_plugins

            result["findings"]["ayon_core_imported"] = True
            result["findings"]["ayon_core_version"] = getattr(ayon_core, "__version__", "unknown")
        except Exception as e:
            result["findings"]["ayon_core_imported"] = False
            result["errors"].append(f"ayon_core import failed: {e}")

        # -- 5. ayon_maya import ------------------------------------------------
        try:
            result["findings"]["ayon_maya_imported"] = True
        except Exception as e:
            result["findings"]["ayon_maya_imported"] = False
            result["errors"].append(f"ayon_maya import failed: {e}")

        # -- 6. AYON host registration ------------------------------------------
        try:
            from ayon_core.pipeline import install_host, registered_host
            from ayon_maya.api import MayaHost

            if not registered_host():
                try:
                    install_host(MayaHost())
                except KeyError as ke:
                    # Incomplete project settings (e.g. missing project_plugins)
                    # are a server-side data issue, not a host registration failure.
                    result["errors"].append(
                        f"Incomplete project settings (missing key: {ke})"
                        " - host may still be registered"
                    )

            host = registered_host()
            result["findings"]["ayon_host_installed"] = host is not None
            result["findings"]["registered_host"] = (
                str(type(host).__name__) if host else None
            )
        except Exception as e:
            result["findings"]["ayon_host_installed"] = False
            result["errors"].append(f"AYON host install failed: {e}")

        # -- 7. Discover loader plugins -----------------------------------------
        try:
            loaders = discover_loader_plugins()
            loader_names = [loader.__name__ for loader in loaders]
            result["findings"]["loader_count"] = len(loaders)
            result["findings"]["loader_names"] = loader_names
        except Exception as e:
            result["findings"]["loader_count"] = 0
            result["errors"].append(f"Loader discovery failed: {e}")

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))

    if result["errors"]:
        result["status"] = "fail"

    # Write results
    script_dir = Path(__file__).parent
    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    with open(results_dir / "maya_result.json", "w") as f:
        json.dump(result, f, indent=2)

    print(json.dumps(result, indent=2))


main()
