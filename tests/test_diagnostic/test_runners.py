"""Integration tests for the DCC diagnostic infrastructure.

These tests verify end-to-end functionality: SSH connectivity, drive mapping,
Maya/Unreal batch execution, and AYON context availability. They require
the actual infrastructure to be running (AYON server, Maya, Unreal via SSH).

Run with:
    cd /tech/users/gisi/dev/repos/gishant-scripts
    .venv/bin/python -m pytest tests/test_diagnostic/ -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gishant_scripts.diagnostic.config import (
    LINUX,
    linux_to_windows_path,
    windows_to_linux_path,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
AYON_PROJECT = "Barbie_Nutcracker"
AYON_FOLDER = "/episodes/ep01/bncro_01_0072/bncro_01_0072_0030"


# ---------------------------------------------------------------------------
# Path mapping (unit tests — no external dependencies)
# ---------------------------------------------------------------------------


class TestPathMapping:
    """Verify bidirectional path conversion between Linux and Windows."""

    def test_linux_to_windows_projects(self):
        assert linux_to_windows_path("/projects/foo") == "P:\\foo"

    def test_linux_to_windows_tech(self):
        assert linux_to_windows_path("/tech/bar") == "Z:\\bar"

    def test_linux_to_windows_unc(self):
        assert linux_to_windows_path("/tech/bar", unc=True) == "\\\\rdoshyd\\tech\\bar"

    def test_linux_to_windows_unc_projects(self):
        assert linux_to_windows_path("/projects/foo", unc=True) == "\\\\rdoshyd\\projects\\foo"

    def test_linux_to_windows_unmapped(self):
        assert linux_to_windows_path("/home/user/file") == "/home/user/file"

    def test_windows_to_linux_p_drive(self):
        assert windows_to_linux_path("P:\\Barbie") == "/projects/Barbie"

    def test_windows_to_linux_z_drive(self):
        assert windows_to_linux_path("Z:\\users") == "/tech/users"

    def test_roundtrip_linux(self):
        original = "/projects/Barbie_Nutcracker/episodes/ep01"
        assert windows_to_linux_path(linux_to_windows_path(original)) == original


# ---------------------------------------------------------------------------
# AYON environment resolution
# ---------------------------------------------------------------------------


class TestAyonEnvResolution:
    """Verify AYON environment variable resolution."""

    def test_returns_expected_keys(self):
        from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

        env = resolve_ayon_env("TestProject", "/test/path")
        required_keys = {
            "AYON_SERVER_URL", "AYON_API_KEY", "AYON_PROJECT_NAME",
            "AYON_FOLDER_PATH", "PYTHONPATH",
        }
        assert required_keys.issubset(env.keys())

    def test_api_key_loaded(self):
        from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

        env = resolve_ayon_env("TestProject", "/test/path")
        assert env["AYON_API_KEY"], "AYON_API_KEY should not be empty"

    def test_windows_addon_paths_use_c_drive(self):
        from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

        env = resolve_ayon_env("TestProject", "/test/path", target="windows")
        pythonpath = env["PYTHONPATH"]
        assert "C:\\Users" in pythonpath
        assert "/home/" not in pythonpath


# ---------------------------------------------------------------------------
# Infrastructure checks
# ---------------------------------------------------------------------------


class TestInfrastructure:
    """Verify SSH connectivity and drive access on the Windows machine."""

    def test_config_maya_bin_exists(self):
        assert Path(LINUX.maya_bin).exists(), f"Maya not found at {LINUX.maya_bin}"

    def test_config_ayon_launcher_exists(self):
        assert Path(LINUX.ayon_launcher).exists()

    def test_ssh_connectivity(self):
        from gishant_scripts.diagnostic.unreal_runner import check_ssh_connectivity

        assert check_ssh_connectivity(), "SSH to Windows machine failed"

    def test_windows_drive_access(self):
        from gishant_scripts.diagnostic.unreal_runner import check_drive_access

        assert check_drive_access(), "Network drive mapping on Windows failed"


# ---------------------------------------------------------------------------
# Maya integration
# ---------------------------------------------------------------------------


class TestMayaIntegration:
    """End-to-end Maya batch execution with AYON context."""

    @pytest.fixture(autouse=True)
    def _cleanup_results(self):
        result_file = FIXTURES_DIR / "results" / "maya_result.json"
        result_file.unlink(missing_ok=True)
        yield
        result_file.unlink(missing_ok=True)

    def test_maya_hello_world(self):
        from gishant_scripts.diagnostic.maya_runner import run_maya_script

        result = run_maya_script(
            script_path=str(FIXTURES_DIR / "hello_world_maya.py"),
            project_name=AYON_PROJECT,
            folder_path=AYON_FOLDER,
            timeout=120,
        )
        assert result.status == "pass", f"Maya failed: {result.errors}"
        assert result.findings.get("maya_version"), "Maya version not reported"

    def test_maya_ayon_connected(self):
        from gishant_scripts.diagnostic.maya_runner import run_maya_script

        result = run_maya_script(
            script_path=str(FIXTURES_DIR / "hello_world_maya.py"),
            project_name=AYON_PROJECT,
            folder_path=AYON_FOLDER,
            timeout=120,
        )
        assert result.findings.get("ayon_connected"), f"AYON not connected: {result.errors}"
        assert result.findings.get("project_name") == AYON_PROJECT


# ---------------------------------------------------------------------------
# Unreal integration
# ---------------------------------------------------------------------------


class TestUnrealIntegration:
    """End-to-end Unreal batch execution with full AYON addon stack."""

    @pytest.fixture(autouse=True)
    def _cleanup_results(self):
        result_file = FIXTURES_DIR / "results" / "unreal_result.json"
        result_file.unlink(missing_ok=True)
        yield
        result_file.unlink(missing_ok=True)

    @pytest.fixture()
    def unreal_result(self):
        """Run the Unreal hello world once and return the result."""
        from gishant_scripts.diagnostic.unreal_runner import run_unreal_script

        return run_unreal_script(
            script_path=str(FIXTURES_DIR / "hello_world_unreal.py"),
            project_name=AYON_PROJECT,
            folder_path=AYON_FOLDER,
            timeout=180,
        )

    def test_unreal_engine_runs(self, unreal_result):
        assert unreal_result.findings.get("unreal_version"), (
            f"UE version not reported: {unreal_result.errors}"
        )

    def test_ayon_api_connected(self, unreal_result):
        assert unreal_result.findings.get("ayon_connected"), (
            f"ayon_api not connected: {unreal_result.errors}"
        )
        assert unreal_result.findings.get("project_name") == AYON_PROJECT

    def test_ayon_core_imported(self, unreal_result):
        assert unreal_result.findings.get("ayon_core_imported"), (
            f"ayon_core import failed: {unreal_result.errors}"
        )

    def test_ayon_unreal_imported(self, unreal_result):
        assert unreal_result.findings.get("ayon_unreal_imported"), (
            f"ayon_unreal import failed: {unreal_result.errors}"
        )

    def test_ayon_host_installed(self, unreal_result):
        assert unreal_result.findings.get("ayon_host_installed"), (
            f"AYON host install failed: {unreal_result.errors}"
        )

    def test_critical_loaders_discovered(self, unreal_result):
        missing = unreal_result.findings.get("critical_loaders_missing", [])
        assert not missing, f"Missing critical loaders: {missing}"
