"""SSH/local runners for the diagnostic dispatcher.

Two thin classes, one per target OS:

* ``LinuxSshRunner`` -- composes a bash preamble via ``bash_builder`` and then
  runs either locally (``bash -s``) or remotely over SSH based on
  ``GISHANT_DIAGNOSTIC_MAYA_MODE`` and host IP detection.
* ``WindowsSshRunner`` -- composes a PowerShell script via ``ps1_builder``,
  pipes it over SSH to the Windows diagnostic box, and launches
  ``UnrealEditor-Cmd`` via ``pwsh -NoProfile -NonInteractive -Command -``.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Literal

from gishant_scripts.diagnostic import bash_builder, path_mapper, ps1_builder

LINUX_HOST = "gisi@10.1.69.24"
WINDOWS_HOST = "gisi@10.1.69.122"
LINUX_HOST_IP = "10.1.69.24"
REPO_PATH_LINUX = "/tech/users/gisi/dev/repos/gishant-scripts"
DEFAULT_UE_BINARY = r"C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"


def _tee_stream(stream: IO[str], log_fh: IO[str], prefix: str) -> None:
    try:
        for line in iter(stream.readline, ""):
            log_fh.write(line)
            log_fh.flush()
            sys.stdout.write(prefix + " " + line)
            sys.stdout.flush()
    finally:
        stream.close()


def _run_with_tee(argv: list[str], stdin_payload: str, live_log_local: Path, prefix: str, timeout_s: int) -> int:
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
        tee = threading.Thread(target=_tee_stream, args=(proc.stdout, log_fh, prefix), daemon=True)
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


def _local_ipv4_addresses() -> set[str]:
    ips: set[str] = set()
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET)
        for info in infos:
            ip = info[4][0]
            if ip:
                ips.add(ip)
    except OSError:
        pass

    # Best-effort default route probe to capture the active source address.
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            ip = probe.getsockname()[0]
            if ip:
                ips.add(ip)
    except OSError:
        pass

    ips.add("127.0.0.1")
    return ips


def resolve_linux_exec_mode(host_ip: str = LINUX_HOST_IP) -> Literal["local", "ssh"]:
    """Pick Linux execution mode for Maya diagnostics.

    Modes:
    - local: run bash directly on this machine
    - ssh: SSH to the Linux host and run remotely

    Override with GISHANT_DIAGNOSTIC_MAYA_MODE={local|ssh|auto}.
    """
    forced = os.getenv("GISHANT_DIAGNOSTIC_MAYA_MODE", "auto").strip().lower()
    if forced in {"local", "ssh"}:
        return forced

    local_ips = _local_ipv4_addresses()
    return "local" if host_ip in local_ips else "ssh"


@dataclass(frozen=True)
class LinuxSshRunner:
    host: str = LINUX_HOST

    def run(self, script_path_linux: str, env: dict[str, str], issue_dir_linux: str, timeout_s: int, live_log_local: Path, maya_bin: str = "/usr/autodesk/maya2025/bin/maya") -> int:
        preamble = bash_builder.build_preamble(env=env, repo_path=REPO_PATH_LINUX)
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
        mode = resolve_linux_exec_mode()
        argv = ["bash", "-s"] if mode == "local" else ["ssh", "-o", "BatchMode=yes", self.host, "bash -s"]
        return _run_with_tee(argv, remote_script, live_log_local, "[maya]", timeout_s)


@dataclass(frozen=True)
class WindowsSshRunner:
    host: str = WINDOWS_HOST

    def run(self, script_path_linux: str, uproject_drive: str, env: dict[str, str], issue_dir_linux: str, timeout_s: int, live_log_local: Path, ue_binary: str = DEFAULT_UE_BINARY) -> int:
        script_path_windows = path_mapper.linux_to_drive(script_path_linux)
        issue_trimmed = issue_dir_linux.rstrip("/")
        output_log_linux = issue_trimmed + "/results/unreal_output.log"
        output_log_path_windows = path_mapper.linux_to_drive(output_log_linux)
        ps1_body = ps1_builder.build(
            script_path_windows=script_path_windows,
            uproject_path_windows=uproject_drive,
            env=env,
            output_log_path_windows=output_log_path_windows,
            ue_binary=ue_binary,
        )
        argv = ["ssh", "-o", "BatchMode=yes", self.host, "pwsh -NoProfile -NonInteractive -Command -"]
        return _run_with_tee(argv, ps1_body, live_log_local, "[unreal]", timeout_s)
