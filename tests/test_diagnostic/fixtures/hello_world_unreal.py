"""Minimal Unreal diagnostic script -- verifies Unreal Engine + AYON context works."""

import json
import os
import sys
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
        from datetime import datetime, timezone

        result["timestamp"] = datetime.now(timezone.utc).isoformat()

        # Test Unreal is working
        import unreal

        result["findings"]["unreal_version"] = unreal.SystemLibrary.get_engine_version()

        # Test AYON context
        result["context"]["project"] = os.environ.get("AYON_PROJECT_NAME", "")
        result["context"]["folder"] = os.environ.get("AYON_FOLDER_PATH", "")

        try:
            import ayon_api

            project = ayon_api.get_project(os.environ["AYON_PROJECT_NAME"])
            result["findings"]["ayon_connected"] = project is not None
            result["findings"]["project_name"] = project["name"] if project else None
        except Exception as e:
            result["findings"]["ayon_connected"] = False
            result["errors"].append(f"AYON connection failed: {e}")

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e))

    # Write results
    script_dir = Path(__file__).parent
    results_dir = script_dir / "results"
    results_dir.mkdir(exist_ok=True)
    with open(results_dir / "unreal_result.json", "w") as f:
        json.dump(result, f, indent=2)

    # Also print to stdout for capture
    print(json.dumps(result, indent=2))


main()
