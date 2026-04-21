"""SSH-based runners for the diagnostic dispatcher.

Two thin classes, one per target OS:

* ``LinuxSshRunner`` -- composes a bash preamble via ``bash_builder``, pipes
  it over SSH to the Linux diagnostic box, and launches Maya in batch mode.
* ``WindowsSshRunner`` -- composes a PowerShell script via ``ps1_builder``,
  pipes it over SSH to the Windows diagnostic box, and launches
  ``UnrealEditor-Cmd`` via ``pwsh -NoProfile -NonInteractive -Command -``.

Both runners stream combined stdout/stderr through a local tee thread into
``live_log_local`` while also writing to stdout with a per-runner prefix
(``[maya]`` / ``[unreal]``). Parallel pipeline output stays readable.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from gishant_scripts.diagnostic import bash_builder, path_mapper, ps1_builder

LINUX_HOST = "gisi@10.1.69.24"
WINDOWS_HOST = "gisi@10.1.69.122"
REPO_PATH_LINUX = "/tech/users/gisi/dev/repos/gishant-scripts"
DEFAULT_UE_BINARY = r"C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"


def _tee_stream(stream: IO[str], log_fh: IO[str], prefix: str) -> None:
    """Read stream line-by-line, writing to both log_fh and stdout with prefix."""
    try:
        for line in iter(stream.readline, ""):
            log_fh.write(line)
            log_fh.flush()
            sys.stdout.write(prefix + " " + line)
            sys.stdout.flush()
    finally:
        stream.close()


def _run_with_tee(
    argv: list[str],
    stdin_payload: str,
    live_log_local: Path,
    prefix: str,
    timeout_s: int,
) -> int:
    """Spawn argv, feed stdin_payload, tee output, enforce timeout_s."""
    live_log_local.parent.mkdir(parents=True, exist_ok=True)
    with live_log_local.open("w", encoding="utf-8") as log_fh, subprocess.Popen(
        argv,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as proc:
        assert proc.stdin is not None
        assert proc.stdout is not None

        proc.stdin.write(stdin_payload)
        proc.stdin.close()

        tee = threading.Thread(
            target=_tee_stream,
            args=(proc.stdout, log_fh, prefix),
            daemon=True,
        )
        tee.start()

        try:
            return proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            tee.join(timeout=2)
            return 124
        finally:
            tee.join(timeout=2)


@dataclass(frozen=True)
class LinuxSshRunner:
    """SSH runner targeting the Linux diagnostic box (Maya)."""

    host: str = LINUX_HOST

    def run(
        self,
        script_path_linux: str,
        env: dict[str, str],
        issue_dir_linux: str,  # noqa: ARG002
        timeout_s: int,
        live_log_local: Path,
        maya_bin: str = "/usr/autodesk/maya2025/bin/maya",
    ) -> int:
        """Run a Maya-batch diagnostic on the Linux target.

        Builds the full bash payload locally, pipes it into
        ``ssh <host> bash -s``. Uses a MEL wrapper written via here-doc to
        avoid the known quote-escaping issues with ``maya -batch -command``.
        """
        preamble = bash_builder.build_preamble(env=env, repo_path=REPO_PATH_LINUX)

        # MEL body: set __file__ then exec the script. Single quotes around
        # the path are safe: script_path_linux is a NAS path chosen by us.
        mel_body = (
            'python("__file__ = \'' + script_path_linux + "'; "
            "exec(open('" + script_path_linux + "').read())\");\n"
        )

        remote_script = (
            preamble + "\n"
            'MEL_FILE="$(mktemp --suffix=.mel)"\n'
            "cat > \"$MEL_FILE\" <<'__MEL_EOF__'\n"
            + mel_body
            + "__MEL_EOF__\n"
            '"' + maya_bin + '" -batch -script "$MEL_FILE"\n'
            "_rc=$?\n"
            'rm -f "$MEL_FILE"\n'
            "exit $_rc\n"
        )

        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            self.host,
            "bash -s",
        ]
        return _run_with_tee(argv, remote_script, live_log_local, "[maya]", timeout_s)


@dataclass(frozen=True)
class WindowsSshRunner:
    """SSH runner targeting the Windows diagnostic box (Unreal)."""

    host: str = WINDOWS_HOST

    def run(
        self,
        script_path_linux: str,
        uproject_drive: str,
        env: dict[str, str],
        issue_dir_linux: str,
        timeout_s: int,
        live_log_local: Path,
        ue_binary: str = DEFAULT_UE_BINARY,
    ) -> int:
        """Run an Unreal-headless diagnostic on the Windows target.

        Converts Linux NAS paths to drive-letter form, builds the ``.ps1``
        via ``ps1_builder``, and pipes it over SSH as stdin to
        ``pwsh -NoProfile -NonInteractive -Command -``. pwsh is never
        invoked locally; script content is never inline-escaped in SSH args.
        """
        script_drive = path_mapper.linux_to_drive(script_path_linux)
        issue_trimmed = issue_dir_linux.rstrip("/")
        output_log_linux = issue_trimmed + "/results/unreal_output.log"
        output_log_drive = path_mapper.linux_to_drive(output_log_linux)

        ps1_body = ps1_builder.build(
            script_drive=script_drive,
            uproject_drive=uproject_drive,
            env=env,
            output_log_drive=output_log_drive,
            ue_binary=ue_binary,
        )

        # Persist locally for debugging; also used nowhere else.
        tmp_dir = Path(tempfile.gettempdir())
        tmp_ps1 = tmp_dir / ("unreal_runner_" + uuid.uuid4().hex + ".ps1")
        tmp_ps1.write_text(ps1_body, encoding="utf-8")

        argv = [
            "ssh",
            "-o",
            "BatchMode=yes",
            self.host,
            "pwsh -NoProfile -NonInteractive -Command -",
        ]
        return _run_with_tee(argv, ps1_body, live_log_local, "[unreal]", timeout_s)
