"""Generate the PowerShell script used by :class:`WindowsSshRunner`.

The produced ``.ps1`` is piped over ``ssh <host> "pwsh -NoProfile -NonInteractive
-Command -"`` to the Windows diagnostic box. It:

1. Maps the NAS drives (Z:, P:) via ``map_drives.cmd`` — required for Unreal
   which resolves drive letters, not UNC paths.
2. Exports every AYON/Kitsu env var as a literal PowerShell string
   (single-quoted, no interpolation; embedded single quotes doubled).
3. Launches ``UnrealEditor-Cmd`` with ``-NullRHI`` headless and
   ``-ExecutePythonScript`` pointing at the supplied diagnostic script.
4. Tees combined stdout/stderr to the given log file and exits with the
   Unreal exit code.
"""

from __future__ import annotations

_DEFAULT_UE_BINARY = r"C:\Program Files\Epic Games\UE_5.5\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
_DEFAULT_MAP_DRIVES = r"C:\Users\gisi\.rdo\map_drives.cmd"


def _ps_single_quote(value: str) -> str:
    """Return *value* wrapped in PowerShell single quotes, doubling any embedded ``'``.

    PowerShell single-quoted strings are literal (no ``$`` interpolation, no
    backtick escapes) except that a literal single quote must be written as
    ``''``.
    """
    return "'" + value.replace("'", "''") + "'"


def build(
    script_drive: str,
    uproject_drive: str,
    env: dict[str, str],
    output_log_drive: str,
    ue_binary: str = _DEFAULT_UE_BINARY,
    map_drives_cmd: str = _DEFAULT_MAP_DRIVES,
) -> str:
    """Build a PowerShell script string ready to pipe over SSH.

    Args:
        script_drive: Windows drive-letter path to the Python diagnostic script
            (e.g. ``Z:\\users\\gisi\\dev\\_diagnostic\\issues\\X\\script.py``).
        uproject_drive: Windows drive-letter path to the ``.uproject``.
        env: AYON/Kitsu environment variables. Exported verbatim.
        output_log_drive: Windows drive-letter path for the combined
            stdout/stderr log file.
        ue_binary: Absolute Windows path to ``UnrealEditor-Cmd.exe``.
        map_drives_cmd: Absolute Windows path to ``map_drives.cmd``.

    Returns:
        A PowerShell script as a single string (LF line endings).

    """
    lines: list[str] = [
        "$ErrorActionPreference = 'Stop'",
        "",
        "# 1. Map NAS drives (Z:, P:) for this session.",
        f"cmd /c {_ps_single_quote(map_drives_cmd)}",
        "if ($LASTEXITCODE -ne 0) { Write-Error \"drive mapping failed (exit $LASTEXITCODE)\"; exit 2 }",
        "",
        "# 2. AYON / Kitsu environment.",
    ]
    for key in sorted(env):
        value = env[key]
        lines.append(f"$env:{key} = {_ps_single_quote(value)}")

    lines.extend(
        [
            "",
            "# 3. Launch Unreal headless, tee combined output to log.",
            (
                f"& {_ps_single_quote(ue_binary)} "
                f"{_ps_single_quote(uproject_drive)} "
                "-NullRHI "
                f"-ExecutePythonScript={_ps_single_quote(script_drive)} "
                "-stdout -FullStdOutLogOutput -Unattended 2>&1 | "
                f"Tee-Object -FilePath {_ps_single_quote(output_log_drive)} -Append"
            ),
            "$unrealExit = $LASTEXITCODE",
            "",
            "exit $unrealExit",
        ],
    )

    return "\n".join(lines) + "\n"
