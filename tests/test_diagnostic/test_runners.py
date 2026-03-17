"""Tests for the diagnostic runner infrastructure."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gishant_scripts.diagnostic.config import (
    LINUX,
    WINDOWS,
    get_results_dir,
    linux_to_windows_path,
    windows_to_linux_path,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Unit tests (no external dependencies)
# ---------------------------------------------------------------------------


class TestConfigLinuxPaths:
    """Verify that configured Linux paths actually exist on disk."""

    @pytest.mark.integration
    def test_maya_bin_exists(self) -> None:
        assert Path(LINUX.maya_bin).exists(), f"Maya binary not found at {LINUX.maya_bin}"

    def test_ayon_launcher_exists(self) -> None:
        assert Path(LINUX.ayon_launcher).exists(), f"AYON launcher not found at {LINUX.ayon_launcher}"


class TestPathMapping:
    """Unit tests for Linux <-> Windows path conversion."""

    def test_linux_to_windows_projects(self) -> None:
        assert linux_to_windows_path("/projects/MyProject/scenes/file.ma") == "P:\\MyProject\\scenes\\file.ma"

    def test_linux_to_windows_tech(self) -> None:
        assert linux_to_windows_path("/tech/users/gisi/dev/test.py") == "Z:\\users\\gisi\\dev\\test.py"

    def test_linux_to_windows_unmapped(self) -> None:
        """Paths that don't match any prefix should be returned unchanged."""
        original = "/home/user/file.txt"
        assert linux_to_windows_path(original) == original

    def test_windows_to_linux_p_drive(self) -> None:
        assert windows_to_linux_path("P:\\MyProject\\scenes\\file.ma") == "/projects/MyProject/scenes/file.ma"

    def test_windows_to_linux_z_drive(self) -> None:
        assert windows_to_linux_path("Z:\\users\\gisi\\dev\\test.py") == "/tech/users/gisi/dev/test.py"

    def test_windows_to_linux_unmapped(self) -> None:
        """Paths that don't match any prefix should be returned unchanged."""
        original = "C:\\Program Files\\app.exe"
        assert windows_to_linux_path(original) == original

    def test_roundtrip_linux(self) -> None:
        original = "/projects/MyProject/scenes/file.ma"
        assert windows_to_linux_path(linux_to_windows_path(original)) == original

    def test_roundtrip_windows(self) -> None:
        original = "P:\\MyProject\\scenes\\file.ma"
        assert linux_to_windows_path(windows_to_linux_path(original)) == original


class TestAyonEnvResolution:
    """Verify resolve_ayon_env returns expected keys."""

    def test_returns_expected_keys(self) -> None:
        from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

        env = resolve_ayon_env(project_name="TestProject", folder_path="/assets/hero")
        expected_keys = {
            "AYON_SERVER_URL",
            "AYON_PROJECT_NAME",
            "AYON_FOLDER_PATH",
            "PYTHONPATH",
            "AYON_LAUNCHER_STORAGE_DIR",
            "AYON_LAUNCHER_LOCAL_DIR",
        }
        assert expected_keys.issubset(env.keys()), f"Missing keys: {expected_keys - env.keys()}"

    def test_task_name_included_when_provided(self) -> None:
        from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

        env = resolve_ayon_env(project_name="TestProject", folder_path="/assets/hero", task_name="modeling")
        assert env["AYON_TASK_NAME"] == "modeling"

    def test_task_name_absent_when_none(self) -> None:
        from gishant_scripts.diagnostic.ayon_env import resolve_ayon_env

        env = resolve_ayon_env(project_name="TestProject", folder_path="/assets/hero")
        assert "AYON_TASK_NAME" not in env


class TestResultsDirCreation:
    """Verify get_results_dir creates the directory."""

    def test_creates_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Redirect diagnostic_base to a temp directory so we don't touch real disk
        monkeypatch.setattr(
            "gishant_scripts.diagnostic.config.LINUX",
            LINUX.__class__(diagnostic_base=str(tmp_path / "diagnostic")),
        )
        results_dir = get_results_dir("test_issue_123")
        assert results_dir.is_dir()
        assert results_dir == tmp_path / "diagnostic" / "issues" / "test_issue_123" / "results"


# ---------------------------------------------------------------------------
# Integration tests (require SSH, Maya, or Unreal)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSSHConnectivity:
    """Verify SSH to the Windows machine works."""

    def test_ssh_echo(self) -> None:
        from gishant_scripts.diagnostic.unreal_runner import check_ssh_connectivity

        assert check_ssh_connectivity(), (
            f"SSH connectivity check failed for {WINDOWS.ssh_host}. "
            "Ensure key-based auth is configured and the machine is reachable."
        )

    def test_ssh_raw_echo(self) -> None:
        """Verify raw SSH echo returns 'ok'."""
        result = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", WINDOWS.ssh_host, "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "ok" in result.stdout


@pytest.mark.integration
class TestMayaHelloWorld:
    """Run the hello_world_maya.py fixture through maya_runner."""

    def test_run(self) -> None:
        from gishant_scripts.diagnostic.maya_runner import run_maya_script

        script = FIXTURES_DIR / "hello_world_maya.py"
        result = run_maya_script(
            script_path=script,
            project_name="TestProject",
            folder_path="/assets/hero",
        )
        assert result.status in {"pass", "fail", "error"}, f"Unexpected status: {result.status}"
        assert result.dcc == "maya"


@pytest.mark.integration
class TestUnrealHelloWorld:
    """Run the hello_world_unreal.py fixture through unreal_runner."""

    def test_run(self) -> None:
        from gishant_scripts.diagnostic.unreal_runner import run_unreal_script

        script = FIXTURES_DIR / "hello_world_unreal.py"
        result = run_unreal_script(
            script_path=script,
            project_name="TestProject",
            folder_path="/assets/hero",
        )
        assert result.status in {"pass", "fail", "error"}, f"Unexpected status: {result.status}"
        assert result.dcc == "unreal"
