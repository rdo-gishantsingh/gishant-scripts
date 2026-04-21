"""Generate the PowerShell script used by :class:`WindowsSshRunner`.

The produced ``.ps1`` is piped over ``ssh <host> "pwsh -NoProfile -NonInteractive
-Command -"`` to the Windows diagnostic box. It:

1. Best-effort maps the NAS drives (Z:, P:) via ``map_drives.cmd``.
2. Exports every AYON/Kitsu env var as a literal PowerShell string.
3. Launches ``UnrealEditor-Cmd`` headless with ``-ExecutePythonScript``.
4. Tees combined stdout/stderr to the given log file and exits with the
   Unreal exit code.
"""

from __future__ import annotations

_DEFAULT_UE_BINARY = r"C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
_DEFAULT_MAP_DRIVES = r"C:\Users\gisi\.rdo\map_drives.cmd"


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build(
    script_path_windows: str,
    uproject_path_windows: str,
    env: dict[str, str],
    output_log_path_windows: str,
    ue_binary: str = _DEFAULT_UE_BINARY,
    map_drives_cmd: str = _DEFAULT_MAP_DRIVES,
) -> str:
    lines: list[str] = [
        "$ErrorActionPreference = 'Stop'",
        "",
        "# 1. Best-effort NAS drive mapping for SSH Session 0.",
        f"if (Test-Path {_ps_single_quote(map_drives_cmd)}) {{ cmd /c {_ps_single_quote(map_drives_cmd)} | Out-Host }}",
        "",
        "# 2. AYON / Kitsu environment.",
    ]
    for key in sorted(env):
        lines.append(f"$env:{key} = {_ps_single_quote(env[key])}")

    lines.extend(
        [
            "",
            "# 2.5 Augment PYTHONPATH from Windows dependency packages at runtime.",
            "$candidateRaw = $env:AYON_LAUNCHER_STORAGE_CANDIDATES",
            "if ([string]::IsNullOrWhiteSpace($candidateRaw)) { $candidateRaw = $env:AYON_LAUNCHER_STORAGE_DIR }",
            "$candidateRaw.Split('|') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object {",
            "  $depRoot = Join-Path $_ 'dependency_packages'",
            "  if (Test-Path $depRoot) {",
            "    Get-ChildItem -Path $depRoot -Directory -Filter '*.zip' | ForEach-Object {",
            "      $deps = Join-Path $_.FullName 'dependencies'",
            "      if (Test-Path $deps) { $env:PYTHONPATH = \"$deps;$env:PYTHONPATH\" }",
            "      $runtime = Join-Path $_.FullName 'runtime'",
            "      if (Test-Path $runtime) { $env:PYTHONPATH = \"$runtime;$env:PYTHONPATH\" }",
            "    }",
            "  }",
            "}",
            "",
            "# 3. Launch Unreal headless, tee combined output to log.",
            (
                f"& {_ps_single_quote(ue_binary)} "
                f"{_ps_single_quote(uproject_path_windows)} "
                "-NullRHI "
                f"-ExecutePythonScript={_ps_single_quote(script_path_windows)} "
                "-stdout -FullStdOutLogOutput -Unattended 2>&1 | "
                f"Tee-Object -FilePath {_ps_single_quote(output_log_path_windows)} -Append"
            ),
            "$unrealExit = $LASTEXITCODE",
            "",
            "exit $unrealExit",
        ],
    )

    return "\n".join(lines) + "\n"
