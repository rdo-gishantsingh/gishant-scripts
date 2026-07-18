"""Install rdo_kitsu 0.3.3 on the LOCAL AYON and create a dev bundle cloning the current
production add-on set with rdo_kitsu pinned to 0.3.3.

The dev bundle is named after the staging bundle and owned by the active user.

Idempotent:
  - skips the addon upload if the version is already installed,
  - recreates the dev bundle each run (delete + create) so re-runs converge.

Targets 10.1.69.24 only. Uses the admin key from ayon-server/.env (never a prod key).
"""
from __future__ import annotations

import sys
from pathlib import Path

import ayon_api

AYON_URL = "http://10.1.69.24:5000"
ADDON_NAME = "rdo_kitsu"
ADDON_VERSION = "0.3.3"
PACKAGE_ZIP = Path("/home/gisi/dev/repos/rdo-ayon-kitsu/package/rdo_kitsu-0.3.3.zip")
DEV_USER = "gisi"
# The new dev bundle is named <staging bundle>_<user>_local. Since staging bundles
# are dated, the name changes each restore, so prior ones are cleaned up per run.
BUNDLE_SUFFIX = f"_{DEV_USER}_local"


def die(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def installed_versions() -> list[str]:
    for addon in ayon_api.get_addons_info()["addons"]:
        if addon["name"] == ADDON_NAME:
            return sorted(addon.get("versions", {}))
    return []


def main() -> None:
    con = ayon_api.get_server_api_connection()
    if con is None or not con.get_base_url().startswith(AYON_URL):
        die(f"Not connected to {AYON_URL} (got {con and con.get_base_url()})")

    me = ayon_api.get_user()
    print(f"connected to {AYON_URL} as {me.get('name')} (admin={me.get('data',{}).get('isAdmin')})")

    # 1. Upload the addon zip (idempotent).
    if ADDON_VERSION in installed_versions():
        print(f"{ADDON_NAME} {ADDON_VERSION} already installed - skipping upload")
    else:
        if not PACKAGE_ZIP.is_file():
            die(f"package zip not found: {PACKAGE_ZIP}")
        print(f"uploading {PACKAGE_ZIP.name} ...")
        ayon_api.upload_addon_zip(str(PACKAGE_ZIP))
        # A newly uploaded addon dir is only registered after AYON reloads its addon
        # library. trigger_server_restart is AYON's own graceful reload (what the UI
        # does post-upload) -- not a docker restart.
        import time
        print("triggering AYON addon reload (graceful) ...")
        ayon_api.trigger_server_restart()
        for _ in range(60):
            time.sleep(2)
            try:
                if ADDON_VERSION in installed_versions():
                    break
            except Exception:  # noqa: S112 - server briefly unavailable during reload
                continue
        else:
            die(f"{ADDON_NAME} {ADDON_VERSION} did not register after upload+reload")
        print(f"{ADDON_NAME} {ADDON_VERSION} installed")

    # 2. Clone the current STAGING bundle's addon set, override rdo_kitsu.
    bundles = ayon_api.get_bundles()
    base = next((b for b in bundles["bundles"] if b.get("isStaging")), None)
    if base is None:
        die("no staging bundle found to clone")
    dev_bundle_name = base["name"] + BUNDLE_SUFFIX
    print(f"cloning staging bundle: {base['name']} (installer {base.get('installerVersion')}) -> {dev_bundle_name}")

    addons = dict(base.get("addons", {}))
    addons = {k: v for k, v in addons.items() if v}   # drop null-versioned addons
    addons[ADDON_NAME] = ADDON_VERSION

    # The staging bundle references addon versions that may not be installed locally (dev
    # builds of core/maya/etc.). A bundle fails validation if a referenced version is not
    # active, and dropping a required addon (e.g. core) breaks its dependents. So: keep the
    # exact version when installed, else substitute the latest locally-installed version of
    # that addon, and only drop an addon that is not installed at all.
    installed = {a["name"]: sorted(a.get("versions", {})) for a in ayon_api.get_addons_info()["addons"]}
    resolved, dropped, subbed = {}, [], []
    for name, ver in addons.items():
        avail = installed.get(name, [])
        if ver in avail:
            resolved[name] = ver
        elif avail:
            resolved[name] = avail[-1]
            subbed.append(f"{name} {ver}->{avail[-1]}")
        else:
            dropped.append(f"{name} {ver}")
    if subbed:
        print(f"substituting locally-installed versions: {', '.join(subbed)}")
    if dropped:
        print(f"dropping addons not installed at all: {', '.join(dropped)}")
    addons = resolved

    # 3. (Re)create the dev bundle. Remove any prior <...>_<user>_local dev bundles so
    #    re-runs and the changing staging date do not leave stale bundles behind.
    for b in bundles["bundles"]:
        if b["name"].endswith(BUNDLE_SUFFIX):
            print(f"deleting old dev bundle {b['name']}")
            ayon_api.delete_bundle(b["name"])

    print(f"creating dev bundle {dev_bundle_name} with rdo_kitsu={ADDON_VERSION} ({len(addons)} addons)")
    ayon_api.create_bundle(
        name=dev_bundle_name,
        addon_versions=addons,
        installer_version=base.get("installerVersion"),
        is_dev=True,
        dev_active_user=DEV_USER,
    )

    # verify
    after = ayon_api.get_bundles()
    dev = next((b for b in after["bundles"] if b["name"] == dev_bundle_name), None)
    if dev is None:
        die("dev bundle not found after create")
    print(f"dev bundle created: isDev={dev.get('isDev')} activeUser={dev.get('activeUser')} "
          f"rdo_kitsu={dev['addons'].get(ADDON_NAME)}")
    # Machine-readable line: the orchestrator captures this to target the settings variant.
    print(f"BUNDLE_NAME={dev_bundle_name}")
    print("OK")


if __name__ == "__main__":
    main()
