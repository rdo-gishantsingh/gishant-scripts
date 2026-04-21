"""Unit tests for AYON environment resolution helpers."""

from __future__ import annotations

from pathlib import Path

from gishant_scripts.diagnostic import ayon_env


def test_windows_storage_candidates_prefers_launcher_local():
    candidates = ayon_env._windows_storage_candidates(r"C:\Users\gisi\AppData\Local\Ynput\AYON")
    assert candidates[0].endswith(r"Ynput\ayon-launcher-local")
    assert any(c.endswith(r"Ynput\ayon-launcher-prod") for c in candidates)
    assert any(c.endswith(r"Ynput\AYON") for c in candidates)


def test_resolve_ayon_env_windows_builds_launcher_local_addon_paths(monkeypatch):
    monkeypatch.setattr(
        ayon_env,
        "list_all_addon_paths",
        lambda: {
            "core": Path("/tech/fake/addons/core_1.2.3"),
            "unreal": Path("/tech/fake/addons/unreal_0.9.1"),
        },
    )
    monkeypatch.setattr(
        ayon_env,
        "resolve_and_validate_test_env",
        lambda _target: {"AYON_SERVER_URL": "http://10.1.69.24:5000", "AYON_API_KEY": "test-key"},
    )

    env = ayon_env.resolve_ayon_env(project_name="P", folder_path="/f", target="windows")

    pythonpath = env["PYTHONPATH"]
    assert r"C:\Users\gisi\AppData\Local\Ynput\ayon-launcher-local\addons\core_1.2.3" in pythonpath
    assert (
        r"C:\Users\gisi\AppData\Local\Ynput\ayon-launcher-local\addons\core_1.2.3\ayon_core\vendor\python"
        in pythonpath
    )
    assert r"C:\Users\gisi\AppData\Local\Ynput\ayon-launcher-local\addons\unreal_0.9.1" in pythonpath
    assert env["AYON_SERVER_URL"] == "http://10.1.69.24:5000"
    assert env["AYON_API_KEY"] == "test-key"
    assert env["AYON_LAUNCHER_STORAGE_DIR"].endswith(r"Ynput\ayon-launcher-local")
    assert r"Ynput\ayon-launcher-prod" in env["AYON_LAUNCHER_STORAGE_CANDIDATES"]
