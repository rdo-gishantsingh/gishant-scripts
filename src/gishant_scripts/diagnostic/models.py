"""Shared data models for diagnostic infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiagnosticResult:
    """Structured result from a diagnostic script run inside a DCC (Maya, Unreal, etc.)."""

    status: str  # "pass", "fail", "error"
    dcc: str  # "maya" or "unreal"
    issue: str  # extracted from script path's parent dir name
    timestamp: str  # ISO 8601 format
    context: dict  # project, folder, fps, etc.
    findings: dict  # free-form diagnostic data produced by the script
    errors: list[str] = field(default_factory=list)  # any errors encountered
    raw_output: str = ""  # full stdout/stderr from the process
