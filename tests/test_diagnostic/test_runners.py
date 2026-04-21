"""Unit tests for the SSH-based diagnostic runners.

All tests here are pure Python: path mapping, bash/ps1 string assembly,
result fetching (mocked subprocess), runners (mocked Popen), and the thin
facade layer (mocked ssh_runner + fetch). Integration tests that actually
SSH into the office boxes are a separate concern, marked ``integration``
and skipped by default.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gishant_scripts.diagnostic import (
    bash_builder,
    path_mapper,
    ps1_builder,
    result_fetcher,
    ssh_runner,
)
from gishant_scripts.diagnostic.maya_runner import DiagnosticRun, run_maya
from gishant_scripts.diagnostic.unreal_runner import run_unreal

# ---------------------------------------------------------------------------
# path_mapper
# ---------------------------------------------------------------------------


class TestPathMapper:
    """Bidirectional Linux <-> Windows path conversions, strict."""

    def test_linux_to_drive_tech(self):
        assert path_mapper.linux_to_drive("/tech/users/gisi") == "Z:\\users\\gisi"

    def test_linux_to_drive_projects(self):
        assert path_mapper.linux_to_drive("/projects/Barbie") == "P:\\Barbie"

    def test_linux_to_drive_trailing_slash(self):
        # Trailing slash should not change the mapping.
        assert path_mapper.linux_to_drive("/tech/users/gisi/") == "Z:\\users\\gisi"

    def test_linux_to_drive_root_only(self):
        assert path_mapper.linux_to_drive("/tech").startswith("Z:\\")

    def test_linux_to_drive_mixed_separators(self):
        # Backslashes in a Linux-style path should still convert cleanly.
        assert path_mapper.linux_to_drive("/tech/users\\gisi") == "Z:\\users\\gisi"

    def test_linux_to_drive_unmappable_raises(self):
        with pytest.raises(path_mapper.PathMappingError):
            path_mapper.linux_to_drive("/home/user")

    def test_linux_to_unc(self):
        assert path_mapper.linux_to_unc("/tech/users") == "\\\\rdoshyd\\tech\\users"

    def test_linux_to_unc_projects(self):
        assert path_mapper.linux_to_unc("/projects/foo") == "\\\\rdoshyd\\projects\\foo"

    def test_linux_to_unc_unmappable_raises(self):
        with pytest.raises(path_mapper.PathMappingError):
            path_mapper.linux_to_unc("/home/user")

    def test_drive_to_linux(self):
        assert path_mapper.drive_to_linux("Z:\\users\\gisi") == "/tech/users/gisi"

    def test_drive_to_linux_forward_slashes(self):
        assert path_mapper.drive_to_linux("Z:/users/gisi") == "/tech/users/gisi"

    def test_drive_to_linux_unmappable_raises(self):
        with pytest.raises(path_mapper.PathMappingError):
            path_mapper.drive_to_linux("D:\\stuff")

    def test_unc_to_linux(self):
        assert path_mapper.unc_to_linux("\\\\rdoshyd\\tech\\users") == "/tech/users"

    def test_unc_to_linux_unmappable_raises(self):
        with pytest.raises(path_mapper.PathMappingError):
            path_mapper.unc_to_linux("\\\\other\\share\\foo")


# ---------------------------------------------------------------------------
# bash_builder
# ---------------------------------------------------------------------------


class TestBashBuilder:
    """Bash preamble contains the required exports and activations."""

    def test_contains_set_e(self):
        out = bash_builder.build_preamble({"AYON_API_KEY": "k"})
        assert "set -e" in out

    def test_exports_sorted(self):
        out = bash_builder.build_preamble({"B_VAR": "2", "A_VAR": "1"})
        assert out.index("A_VAR") < out.index("B_VAR")

    def test_single_quote_escaping(self):
        # shlex.quote handles single quotes safely.
        out = bash_builder.build_preamble({"FOO": "value with 'quote'"})
        assert "FOO=" in out
        # shlex.quote wraps and escapes; the raw bare string should not appear
        # unquoted.
        assert "value with 'quote'" not in out.replace(r"'\''", "|ESC|")

    def test_cd_and_source(self):
        out = bash_builder.build_preamble(
            {"AYON_API_KEY": "k"},
            repo_path="/tech/users/gisi/dev/repos/gishant-scripts",
        )
        assert "cd /tech/users/gisi/dev/repos/gishant-scripts" in out
        assert "source /tech/users/gisi/dev/repos/gishant-scripts/.venv/bin/activate" in out


# ---------------------------------------------------------------------------
# ps1_builder
# ---------------------------------------------------------------------------


class TestPs1Builder:
    """PowerShell script assembly for the Windows runner."""

    def _sample(self, env=None) -> str:
        env = env or {
            "AYON_SERVER_URL": "http://localhost:5000",
            "AYON_API_KEY": "abc",
            "AYON_PROJECT_NAME": "P",
        }
        return ps1_builder.build(
            script_drive="Z:\\script.py",
            uproject_drive="P:\\x.uproject",
            env=env,
            output_log_drive="Z:\\log.txt",
        )

    def test_contains_map_drives(self):
        out = self._sample()
        assert "map_drives.cmd" in out

    def test_contains_env_exports(self):
        out = self._sample()
        assert "$env:AYON_SERVER_URL = 'http://localhost:5000'" in out
        assert "$env:AYON_API_KEY = 'abc'" in out
        assert "$env:AYON_PROJECT_NAME = 'P'" in out

    def test_contains_unreal_launch_with_nullrhi(self):
        out = self._sample()
        assert "UnrealEditor-Cmd.exe" in out
        assert "-NullRHI" in out
        assert "-ExecutePythonScript='Z:\\script.py'" in out

    def test_contains_exit_last_exit_code(self):
        out = self._sample()
        assert "$unrealExit = $LASTEXITCODE" in out
        assert "exit $unrealExit" in out

    def test_single_quote_in_value_is_doubled(self):
        out = self._sample({"FOO": "has'quote"})
        assert "$env:FOO = 'has''quote'" in out

    def test_tee_object_to_log(self):
        out = self._sample()
        assert "Tee-Object" in out
        assert "'Z:\\log.txt'" in out


# ---------------------------------------------------------------------------
# result_fetcher
# ---------------------------------------------------------------------------


class TestResultFetcher:
    """Result JSON pulled via ssh + cat, with validation."""

    def test_happy_path(self, tmp_path):
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = '{"status": "pass", "dcc": "maya"}'
        fake.stderr = ""
        with patch("gishant_scripts.diagnostic.result_fetcher.subprocess.run", return_value=fake):
            out = result_fetcher.fetch_result("gisi@host", "/tech/x/result.json", tmp_path)
        assert out.read_text(encoding="utf-8") == fake.stdout
        assert out.name == "result.json"

    def test_nonzero_exit_raises_not_found(self, tmp_path):
        fake = MagicMock()
        fake.returncode = 1
        fake.stdout = ""
        fake.stderr = "no such file"
        with (
            patch("gishant_scripts.diagnostic.result_fetcher.subprocess.run", return_value=fake),
            pytest.raises(result_fetcher.ResultNotFoundError),
        ):
            result_fetcher.fetch_result("gisi@host", "/tech/x/result.json", tmp_path)

    def test_empty_stdout_raises_not_found(self, tmp_path):
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = ""
        fake.stderr = ""
        with (
            patch("gishant_scripts.diagnostic.result_fetcher.subprocess.run", return_value=fake),
            pytest.raises(result_fetcher.ResultNotFoundError),
        ):
            result_fetcher.fetch_result("gisi@host", "/tech/x/result.json", tmp_path)

    def test_malformed_json_raises_malformed(self, tmp_path):
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = "not json {["
        fake.stderr = ""
        with (
            patch("gishant_scripts.diagnostic.result_fetcher.subprocess.run", return_value=fake),
            pytest.raises(result_fetcher.ResultMalformedError),
        ):
            result_fetcher.fetch_result("gisi@host", "/tech/x/result.json", tmp_path)


# ---------------------------------------------------------------------------
# ssh_runner — regression: never invokes pwsh locally
# ---------------------------------------------------------------------------


class TestSshRunner:
    """Outbound argv must be ssh; pwsh only appears as a remote argument."""

    def _stub_popen(self, returncode=0):
        fake_proc = MagicMock()
        fake_stdin = MagicMock()
        fake_stdout = MagicMock()
        fake_stdout.readline = MagicMock(side_effect=[""])
        fake_proc.stdin = fake_stdin
        fake_proc.stdout = fake_stdout
        fake_proc.wait = MagicMock(return_value=returncode)
        fake_proc.__enter__ = MagicMock(return_value=fake_proc)
        fake_proc.__exit__ = MagicMock(return_value=False)
        return fake_proc

    def test_linux_runner_invokes_ssh_bash_s(self, tmp_path):
        fake = self._stub_popen()
        with patch("gishant_scripts.diagnostic.ssh_runner.subprocess.Popen", return_value=fake) as popen_mock:
            runner = ssh_runner.LinuxSshRunner()
            rc = runner.run(
                script_path_linux="/tech/users/gisi/dev/_diagnostic/issues/X/script.py",
                env={"AYON_SERVER_URL": "http://localhost:5000", "AYON_API_KEY": "k"},
                issue_dir_linux="/tech/users/gisi/dev/_diagnostic/issues/X",
                timeout_s=30,
                live_log_local=tmp_path / "maya.log",
            )
        assert rc == 0
        argv = popen_mock.call_args[0][0]
        assert argv[0] == "ssh"
        assert "gisi@10.1.69.24" in argv
        assert argv[-1] == "bash -s"
        # Regression guard: Linux runner must NOT be local pwsh.
        assert argv[0] != "pwsh"
        # Payload piped via stdin, not argv.
        payload = fake.stdin.write.call_args[0][0]
        assert "maya" in payload
        assert "source " in payload

    def test_windows_runner_invokes_ssh_pwsh_remote_not_local_pwsh(self, tmp_path):
        """REGRESSION: the local-pwsh bug must never return — argv[0] is ssh."""
        fake = self._stub_popen()
        with patch("gishant_scripts.diagnostic.ssh_runner.subprocess.Popen", return_value=fake) as popen_mock:
            runner = ssh_runner.WindowsSshRunner()
            rc = runner.run(
                script_path_linux="/tech/users/gisi/dev/_diagnostic/issues/X/script.py",
                uproject_drive="P:\\x.uproject",
                env={"AYON_SERVER_URL": "http://localhost:5000", "AYON_API_KEY": "k"},
                issue_dir_linux="/tech/users/gisi/dev/_diagnostic/issues/X",
                timeout_s=30,
                live_log_local=tmp_path / "unreal.log",
            )
        assert rc == 0
        argv = popen_mock.call_args[0][0]
        # Regression guard for the local-pwsh bug.
        assert argv[0] == "ssh", f"argv[0] must be 'ssh', got {argv[0]!r}"
        assert argv[0] != "pwsh"
        assert "gisi@10.1.69.122" in argv
        # Remote command runs pwsh in stdin-pipe mode.
        assert argv[-1] == "pwsh -NoProfile -NonInteractive -Command -"
        # Payload piped via stdin.
        payload = fake.stdin.write.call_args[0][0]
        assert "$env:AYON_SERVER_URL" in payload
        assert "UnrealEditor-Cmd.exe" in payload


# ---------------------------------------------------------------------------
# maya_runner / unreal_runner facades
# ---------------------------------------------------------------------------


class TestMayaRunnerFacade:
    """Verify the thin facade composes env, issue dir, and delegates correctly."""

    def test_assembles_env_and_delegates(self, tmp_path):  # noqa: ARG002
        fake_runner = MagicMock()
        fake_runner.host = "gisi@10.1.69.24"
        fake_runner.run = MagicMock(return_value=0)

        captured_env: dict = {}

        def capture_run(**kwargs):
            captured_env.update(kwargs["env"])
            return 0

        fake_runner.run.side_effect = capture_run

        def fake_fetch(host, remote_path, cache):  # noqa: ARG001
            cache.mkdir(parents=True, exist_ok=True)
            p = cache / Path(remote_path).name
            p.write_text(json.dumps({"status": "pass"}))
            return p

        def fake_guard(target):  # noqa: ARG001
            return {"AYON_SERVER_URL": "http://localhost:5000", "AYON_API_KEY": "k"}

        run = run_maya(
            script_path_linux="/tech/users/gisi/dev/_diagnostic/issues/X/script.py",
            project_name="P",
            folder_path="/ep01/sh010",
            bundle_name="my_bundle",
            workdir="/tech/work",
            site_id="site-a",
            runner=fake_runner,
            fetch=fake_fetch,
            guard=fake_guard,
        )

        assert isinstance(run, DiagnosticRun)
        assert run.status == "pass"
        assert run.dcc == "maya"
        assert run.exit_code == 0
        # Env composition
        assert captured_env["AYON_SERVER_URL"] == "http://localhost:5000"
        assert captured_env["AYON_API_KEY"] == "k"
        assert captured_env["AYON_PROJECT_NAME"] == "P"
        assert captured_env["AYON_FOLDER_PATH"] == "/ep01/sh010"
        assert captured_env["AYON_BUNDLE_NAME"] == "my_bundle"
        assert captured_env["AYON_WORKDIR"] == "/tech/work"
        assert captured_env["AYON_SITE_ID"] == "site-a"

    def test_guard_exception_propagates(self):
        from gishant_scripts.diagnostic.test_server_guard import TestServerConfigError

        def bad_guard(target):  # noqa: ARG001
            raise TestServerConfigError("prod URL detected")

        with pytest.raises(TestServerConfigError):
            run_maya(
                script_path_linux="/tech/x/issues/Y/script.py",
                project_name="P",
                folder_path="/f",
                runner=MagicMock(host="h", run=MagicMock(return_value=0)),
                guard=bad_guard,
            )


class TestUnrealRunnerFacade:
    """Verify uproject conversion + env composition for Unreal."""

    def test_uproject_linux_to_drive(self):
        fake_runner = MagicMock()
        fake_runner.host = "gisi@10.1.69.122"
        captured: dict = {}

        def capture_run(**kwargs):
            captured.update(kwargs)
            return 0

        fake_runner.run.side_effect = capture_run

        def fake_fetch(host, remote_path, cache):  # noqa: ARG001
            cache.mkdir(parents=True, exist_ok=True)
            p = cache / Path(remote_path).name
            p.write_text(json.dumps({"status": "pass"}))
            return p

        def fake_guard(target):  # noqa: ARG001
            return {"AYON_SERVER_URL": "http://10.1.69.24:5000", "AYON_API_KEY": "k"}

        run = run_unreal(
            script_path_linux="/tech/users/gisi/dev/_diagnostic/issues/X/script.py",
            project_name="P",
            folder_path="/f",
            uproject_path="/projects/Barbie/Barbie.uproject",
            bundle_name="b",
            runner=fake_runner,
            fetch=fake_fetch,
            guard=fake_guard,
        )
        assert run.status == "pass"
        assert run.dcc == "unreal"
        assert captured["uproject_drive"] == "P:\\Barbie\\Barbie.uproject"
        assert captured["env"]["AYON_BUNDLE_NAME"] == "b"

    def test_uproject_drive_passthrough(self):
        fake_runner = MagicMock()
        fake_runner.host = "gisi@10.1.69.122"
        captured: dict = {}

        def capture_run(**kwargs):
            captured.update(kwargs)
            return 0

        fake_runner.run.side_effect = capture_run

        def fake_fetch(host, remote_path, cache):  # noqa: ARG001
            cache.mkdir(parents=True, exist_ok=True)
            p = cache / Path(remote_path).name
            p.write_text(json.dumps({"status": "fail"}))
            return p

        def fake_guard(target):  # noqa: ARG001
            return {"AYON_SERVER_URL": "http://localhost:5000", "AYON_API_KEY": "k"}

        run = run_unreal(
            script_path_linux="/tech/x/issues/Y/s.py",
            project_name="P",
            folder_path="/f",
            uproject_path="P:\\already\\drive.uproject",
            runner=fake_runner,
            fetch=fake_fetch,
            guard=fake_guard,
        )
        assert captured["uproject_drive"] == "P:\\already\\drive.uproject"
        assert run.status == "fail"
