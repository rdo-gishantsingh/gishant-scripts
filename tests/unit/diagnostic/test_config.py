"""Unit tests for diagnostic config path conversion and env var overrides."""

from __future__ import annotations

import pytest


class TestLinuxToWindowsPath:
    """Tests for linux_to_windows_path() with drive letters and UNC paths."""

    def test_projects_path_drive_letter(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/projects/foo/bar/scene.ma")
        assert result == "P:\\foo\\bar\\scene.ma"

    def test_tech_path_drive_letter(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/tech/users/gisi/dev/test.py")
        assert result == "Z:\\users\\gisi\\dev\\test.py"

    def test_projects_path_unc(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/projects/foo/bar/scene.ma", unc=True)
        assert result.startswith("\\\\")
        assert "\\projects\\foo\\bar\\scene.ma" in result

    def test_tech_path_unc(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/tech/users/gisi/file.txt", unc=True)
        assert result.startswith("\\\\")
        assert "\\tech\\users\\gisi\\file.txt" in result

    def test_unmapped_path_returns_unchanged(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/home/user/file.txt")
        assert result == "/home/user/file.txt"

    def test_unc_unmapped_path_returns_unchanged(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/home/user/file.txt", unc=True)
        assert result == "/home/user/file.txt"

    def test_projects_root_drive_letter(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/projects/")
        assert result == "P:\\"

    def test_tech_root_drive_letter(self) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path

        result = linux_to_windows_path("/tech/")
        assert result == "Z:\\"


class TestWindowsToLinuxPath:
    """Tests for windows_to_linux_path()."""

    def test_p_drive_to_projects(self) -> None:
        from gishant_scripts.diagnostic.config import windows_to_linux_path

        result = windows_to_linux_path("P:\\foo\\bar\\scene.ma")
        assert result == "/projects/foo/bar/scene.ma"

    def test_z_drive_to_tech(self) -> None:
        from gishant_scripts.diagnostic.config import windows_to_linux_path

        result = windows_to_linux_path("Z:\\users\\gisi\\dev\\test.py")
        assert result == "/tech/users/gisi/dev/test.py"

    def test_unmapped_path_returns_unchanged(self) -> None:
        from gishant_scripts.diagnostic.config import windows_to_linux_path

        result = windows_to_linux_path("C:\\Users\\gisi\\Desktop\\file.txt")
        assert result == "C:\\Users\\gisi\\Desktop\\file.txt"

    def test_p_drive_root(self) -> None:
        from gishant_scripts.diagnostic.config import windows_to_linux_path

        result = windows_to_linux_path("P:\\")
        assert result == "/projects/"

    def test_z_drive_root(self) -> None:
        from gishant_scripts.diagnostic.config import windows_to_linux_path

        result = windows_to_linux_path("Z:\\")
        assert result == "/tech/"


class TestRoundtripConversion:
    """Verify that converting Linux -> Windows -> Linux returns the original path."""

    @pytest.mark.parametrize(
        "linux_path",
        [
            "/projects/show/shot/scene.ma",
            "/tech/apps/maya2025/bin/maya",
            "/projects/deep/nested/path/to/file.exr",
        ],
    )
    def test_roundtrip_drive_letter(self, linux_path: str) -> None:
        from gishant_scripts.diagnostic.config import linux_to_windows_path, windows_to_linux_path

        win_path = linux_to_windows_path(linux_path)
        result = windows_to_linux_path(win_path)
        assert result == linux_path


class TestEnvVarOverrides:
    """Test that LinuxConfig and WindowsConfig respect environment variables."""

    def test_linux_maya_bin_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MAYA_BIN", "/custom/maya/bin/maya")
        from gishant_scripts.diagnostic.config import LinuxConfig

        cfg = LinuxConfig()
        assert cfg.maya_bin == "/custom/maya/bin/maya"

    def test_linux_ayon_launcher_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AYON_LAUNCHER_PATH", "/custom/ayon/launcher")
        from gishant_scripts.diagnostic.config import LinuxConfig

        cfg = LinuxConfig()
        assert cfg.ayon_launcher == "/custom/ayon/launcher"

    def test_linux_ayon_server_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AYON_SERVER_URL", "http://custom:9999")
        from gishant_scripts.diagnostic.config import LinuxConfig

        cfg = LinuxConfig()
        assert cfg.ayon_server_url == "http://custom:9999"

    def test_linux_diagnostic_base_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIAGNOSTIC_BASE_DIR", "/tmp/diag")
        from gishant_scripts.diagnostic.config import LinuxConfig

        cfg = LinuxConfig()
        assert cfg.diagnostic_base == "/tmp/diag"

    def test_windows_ssh_host_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIAGNOSTIC_SSH_HOST", "user@10.0.0.1")
        from gishant_scripts.diagnostic.config import WindowsConfig

        cfg = WindowsConfig()
        assert cfg.ssh_host == "user@10.0.0.1"

    def test_windows_unreal_bin_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UNREAL_BIN", r"D:\UE\Editor.exe")
        from gishant_scripts.diagnostic.config import WindowsConfig

        cfg = WindowsConfig()
        assert cfg.unreal_bin == r"D:\UE\Editor.exe"

    def test_windows_ayon_server_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AYON_SERVER_URL_WIN", "http://win-server:5000")
        from gishant_scripts.diagnostic.config import WindowsConfig

        cfg = WindowsConfig()
        assert cfg.ayon_server_url == "http://win-server:5000"


class TestNasHostnameOverride:
    """Test that NAS_HOSTNAME env var affects UNC path generation.

    Note: PATH_MAP_LINUX_TO_UNC is built at module import time, so we must
    reload the module to pick up the env var change.
    """

    def test_custom_nas_hostname(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        monkeypatch.setenv("NAS_HOSTNAME", "customnas")

        import gishant_scripts.diagnostic.config as config_mod

        importlib.reload(config_mod)

        result = config_mod.linux_to_windows_path("/projects/foo/bar.ma", unc=True)
        assert result.startswith("\\\\customnas\\")
        assert "\\projects\\foo\\bar.ma" in result

    def test_default_nas_hostname(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        monkeypatch.delenv("NAS_HOSTNAME", raising=False)

        import gishant_scripts.diagnostic.config as config_mod

        importlib.reload(config_mod)

        result = config_mod.linux_to_windows_path("/tech/file.txt", unc=True)
        assert result.startswith("\\\\rdoshyd\\")
