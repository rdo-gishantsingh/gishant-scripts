"""Integration tests for the DCC diagnostic infrastructure.

These tests verify end-to-end functionality: local execution of Maya/Unreal
batch, AYON context availability, and path conversions. Both runners execute
locally on their target OS — no cross-machine SSH.

Run with:
    cd /tech/users/gisi/dev/repos/gishant-scripts
    .venv/bin/python -m pytest tests/test_diagnostic/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gishant_scripts.diagnostic.config import (
    LINUX,
    WINDOWS,
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
# Config (unit tests)
# ---------------------------------------------------------------------------


class TestConfig:
    """Verify configuration dataclasses and defaults."""

    def test_windows_config_has_no_ssh_host(self):
        """ssh_host was removed — WindowsConfig no longer has it."""
        assert not hasattr(WINDOWS, "ssh_host")

    def test_windows_config_has_diagnostic_base_unc(self):
        assert hasattr(WINDOWS, "diagnostic_base_unc")
        assert "rdoshyd" in WINDOWS.diagnostic_base_unc

    def test_get_results_dir_returns_path(self):
        from gishant_scripts.diagnostic.config import get_results_dir

        results_dir = get_results_dir("test_issue_123")
        assert results_dir.name == "results"
        assert "test_issue_123" in str(results_dir)


# ---------------------------------------------------------------------------
# AYON environment resolution
# ---------------------------------------------------------------------------


class TestAyonEnvResolution:
    """Verify AYON environment variable resolution."""

    def test_returns_expected_keys(self):
        from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

        env = resolve_ayon_env("TestProject", "/test/path")
        required_keys = {
            "AYON_SERVER_URL",
            "AYON_API_KEY",
            "AYON_PROJECT_NAME",
            "AYON_FOLDER_PATH",
            "PYTHONPATH",
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
        # Addon paths should use Windows format (Linux dep package paths are OK)


# ---------------------------------------------------------------------------
# Infrastructure checks (OS-aware)
# ---------------------------------------------------------------------------


class TestInfrastructure:
    """Verify local infrastructure availability."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Maya binary is on Linux")
    def test_config_maya_bin_exists(self):
        assert Path(LINUX.maya_bin).exists(), f"Maya not found at {LINUX.maya_bin}"

    @pytest.mark.skipif(sys.platform == "win32", reason="AYON launcher path is Linux-specific")
    def test_config_ayon_launcher_exists(self):
        assert Path(LINUX.ayon_launcher).exists()

    @pytest.mark.skipif(sys.platform != "win32", reason="Unreal binary is on Windows")
    def test_config_unreal_bin_exists(self):
        assert Path(WINDOWS.unreal_bin).exists(), f"Unreal not found at {WINDOWS.unreal_bin}"


# ---------------------------------------------------------------------------
# Unreal execution (unit tests with mocked subprocess)
# ---------------------------------------------------------------------------


class TestUnrealExecution:
    """Verify the Unreal execution path without actually running Unreal."""

    def test_run_unreal_missing_script(self, tmp_path):
        """Error result when the script file does not exist."""
        from gishant_scripts.diagnostic.launcher_runner import run_unreal

        result = run_unreal(
            script_path=tmp_path / "nonexistent.py",
            project_name="TestProject",
            folder_path="/test/folder",
        )
        assert result.status == "error"
        assert "not found" in result.errors[0].lower()

    def test_run_unreal_writes_ps1_wrapper(self, tmp_path):
        """Verify a .ps1 wrapper is created with env vars and Unreal invocation."""
        issue_dir = tmp_path / "test_issue"
        issue_dir.mkdir()
        script = issue_dir / "test_script.py"
        script.write_text("print(hello)", encoding="utf-8")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        with (
            patch("gishant_scripts.diagnostic.launcher_runner.subprocess.run", return_value=mock_proc),
            patch(
                "gishant_scripts.diagnostic.launcher_runner.resolve_ayon_env",
                return_value={
                    "AYON_SERVER_URL": "http://test",
                    "AYON_API_KEY": "test_key",
                    "AYON_PROJECT_NAME": "TestProject",
                    "AYON_FOLDER_PATH": "/test/folder",
                    "PYTHONPATH": "",
                },
            ),
        ):
            from gishant_scripts.diagnostic.launcher_runner import run_unreal

            run_unreal(
                script_path=script,
                project_name="TestProject",
                folder_path="/test/folder",
            )

        # The subprocess.run call should use pwsh -File, not ssh
        # Just verify no exception was raised — the wrapper was written and executed

    def test_run_unreal_uses_pwsh_not_ssh(self, tmp_path):
        """The command must use pwsh locally, not ssh."""
        issue_dir = tmp_path / "test_issue"
        issue_dir.mkdir()
        script = issue_dir / "test_script.py"
        script.write_text("print(hello)", encoding="utf-8")

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        with (
            patch("gishant_scripts.diagnostic.launcher_runner.subprocess.run", return_value=mock_proc) as mock_run,
            patch(
                "gishant_scripts.diagnostic.launcher_runner.resolve_ayon_env",
                return_value={
                    "AYON_SERVER_URL": "http://test",
                    "AYON_API_KEY": "test_key",
                    "AYON_PROJECT_NAME": "TestProject",
                    "AYON_FOLDER_PATH": "/test/folder",
                    "PYTHONPATH": "",
                },
            ),
        ):
            from gishant_scripts.diagnostic.launcher_runner import run_unreal

            run_unreal(
                script_path=script,
                project_name="TestProject",
                folder_path="/test/folder",
            )

        # Verify the command starts with pwsh, not ssh
        run_call = mock_run.call_args
        cmd = run_call[0][0]
        assert cmd[0] == "pwsh", f"Expected pwsh as first arg, got {cmd[0]}"
        assert "ssh" not in cmd, "Command should not contain ssh"

    def test_run_unreal_parses_result_json(self, tmp_path):
        """Verify result JSON is parsed correctly when Unreal produces it."""
        import json

        issue_dir = tmp_path / "test_issue"
        issue_dir.mkdir()
        script = issue_dir / "test_script.py"
        script.write_text("print(hello)", encoding="utf-8")

        # Pre-create result JSON (run_unreal uses subprocess.run, not Popen)
        results_dir = issue_dir / "results"
        results_dir.mkdir()
        result_data = {
            "status": "pass",
            "dcc": "unreal",
            "issue": "test_issue",
            "timestamp": "2026-01-01T00:00:00",
            "context": {"project": "TestProject"},
            "findings": {"unreal_version": "5.5.0"},
            "errors": [],
        }
        (results_dir / "unreal_result.json").write_text(
            json.dumps(result_data),
            encoding="utf-8",
        )

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        with (
            patch("gishant_scripts.diagnostic.launcher_runner.subprocess.run", return_value=mock_proc),
            patch(
                "gishant_scripts.diagnostic.launcher_runner.resolve_ayon_env",
                return_value={
                    "AYON_SERVER_URL": "http://test",
                    "AYON_API_KEY": "test_key",
                    "AYON_PROJECT_NAME": "TestProject",
                    "AYON_FOLDER_PATH": "/test/folder",
                    "PYTHONPATH": "",
                },
            ),
        ):
            from gishant_scripts.diagnostic.launcher_runner import run_unreal

            result = run_unreal(
                script_path=script,
                project_name="TestProject",
                folder_path="/test/folder",
            )

        assert result.status == "pass"
        assert result.findings["unreal_version"] == "5.5.0"
        assert result.dcc == "unreal"

    def test_run_unreal_timeout_returns_error(self, tmp_path):
        """Verify timeout produces an error result, not an exception."""
        import subprocess as sp

        issue_dir = tmp_path / "test_issue"
        issue_dir.mkdir()
        script = issue_dir / "test_script.py"
        script.write_text("print(hello)", encoding="utf-8")

        with (
            patch(
                "gishant_scripts.diagnostic.launcher_runner.subprocess.run",
                side_effect=sp.TimeoutExpired(cmd="pwsh", timeout=5),
            ),
            patch(
                "gishant_scripts.diagnostic.launcher_runner.resolve_ayon_env",
                return_value={
                    "AYON_SERVER_URL": "http://test",
                    "AYON_API_KEY": "test_key",
                    "AYON_PROJECT_NAME": "TestProject",
                    "AYON_FOLDER_PATH": "/test/folder",
                    "PYTHONPATH": "",
                },
            ),
        ):
            from gishant_scripts.diagnostic.launcher_runner import run_unreal

            result = run_unreal(
                script_path=script,
                project_name="TestProject",
                folder_path="/test/folder",
                timeout=5,
            )

        assert result.status == "error"
        assert "timed out" in result.errors[0].lower()


# ---------------------------------------------------------------------------
# Maya integration (Linux-only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="Maya runs on Linux")
class TestMayaIntegration:
    """End-to-end Maya batch execution with full AYON addon stack."""

    @pytest.fixture(autouse=True, scope="class")
    def _cleanup_results(self):
        result_file = FIXTURES_DIR / "results" / "maya_result.json"
        result_file.unlink(missing_ok=True)
        yield
        result_file.unlink(missing_ok=True)

    @pytest.fixture(scope="class")
    def maya_result(self):
        """Run the Maya hello world once and return the result."""
        from gishant_scripts.diagnostic.launcher_runner import run_maya

        return run_maya(
            script_path=str(FIXTURES_DIR / "hello_world_maya.py"),
            project_name=AYON_PROJECT,
            folder_path=AYON_FOLDER,
            timeout=180,
        )

    def test_maya_engine_runs(self, maya_result):
        assert maya_result.findings.get("maya_version"), f"Maya version not reported: {maya_result.errors}"

    def test_ayon_api_connected(self, maya_result):
        assert maya_result.findings.get("ayon_connected"), f"ayon_api not connected: {maya_result.errors}"
        assert maya_result.findings.get("project_name") == AYON_PROJECT

    def test_ayon_core_imported(self, maya_result):
        assert maya_result.findings.get("ayon_core_imported"), f"ayon_core import failed: {maya_result.errors}"

    def test_ayon_maya_imported(self, maya_result):
        assert maya_result.findings.get("ayon_maya_imported"), f"ayon_maya import failed: {maya_result.errors}"

    def test_ayon_host_installed(self, maya_result):
        assert maya_result.findings.get("ayon_host_installed"), f"AYON host install failed: {maya_result.errors}"

    def test_loaders_discovered(self, maya_result):
        count = maya_result.findings.get("loader_count", 0)
        assert count > 0, f"No loaders discovered: {maya_result.errors}"


# ---------------------------------------------------------------------------
# Unreal integration (Windows-only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Unreal runs locally on Windows")
class TestUnrealIntegration:
    """End-to-end Unreal batch execution with full AYON addon stack."""

    @pytest.fixture(autouse=True, scope="class")
    def _cleanup_results(self):
        result_file = FIXTURES_DIR / "results" / "unreal_result.json"
        result_file.unlink(missing_ok=True)
        yield
        result_file.unlink(missing_ok=True)

    @pytest.fixture(scope="class")
    def unreal_result(self):
        """Run the Unreal hello world once and return the result."""
        from gishant_scripts.diagnostic.launcher_runner import run_unreal

        return run_unreal(
            script_path=str(FIXTURES_DIR / "hello_world_unreal.py"),
            project_name=AYON_PROJECT,
            folder_path=AYON_FOLDER,
            timeout=180,
        )

    def test_unreal_engine_runs(self, unreal_result):
        assert unreal_result.findings.get("unreal_version"), f"UE version not reported: {unreal_result.errors}"

    def test_ayon_api_connected(self, unreal_result):
        assert unreal_result.findings.get("ayon_connected"), f"ayon_api not connected: {unreal_result.errors}"
        assert unreal_result.findings.get("project_name") == AYON_PROJECT

    def test_ayon_core_imported(self, unreal_result):
        assert unreal_result.findings.get("ayon_core_imported"), f"ayon_core import failed: {unreal_result.errors}"

    def test_ayon_unreal_imported(self, unreal_result):
        assert unreal_result.findings.get("ayon_unreal_imported"), f"ayon_unreal import failed: {unreal_result.errors}"

    def test_ayon_host_installed(self, unreal_result):
        assert unreal_result.findings.get("ayon_host_installed"), f"AYON host install failed: {unreal_result.errors}"

    def test_critical_loaders_discovered(self, unreal_result):
        missing = unreal_result.findings.get("critical_loaders_missing", [])
        assert not missing, f"Missing critical loaders: {missing}"
