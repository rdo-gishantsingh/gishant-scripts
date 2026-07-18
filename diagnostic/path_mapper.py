"""Strict path conversion between Linux NAS paths, Windows UNC, and Windows drive letters.

Covers only the two paths that matter for the diagnostic infrastructure:

- ``/tech``     <-> ``\\\\rdoshyd\\tech``     <-> ``Z:\\``
- ``/projects`` <-> ``\\\\rdoshyd\\projects`` <-> ``P:\\``

Every conversion here is strict: unmappable paths raise
:class:`PathMappingError` instead of silently returning the input untouched.
Callers never get a half-converted path that Unreal or Maya will later reject.
"""

from __future__ import annotations

import os
from typing import Final

_NAS_HOST: Final[str] = os.getenv("NAS_HOSTNAME", "rdoshyd")

_LINUX_TO_DRIVE: Final[dict[str, str]] = {
    "/tech/": "Z:\\",
    "/projects/": "P:\\",
}

_LINUX_TO_UNC: Final[dict[str, str]] = {
    "/tech/": f"\\\\{_NAS_HOST}\\tech\\",
    "/projects/": f"\\\\{_NAS_HOST}\\projects\\",
}

_DRIVE_TO_LINUX: Final[dict[str, str]] = {v: k for k, v in _LINUX_TO_DRIVE.items()}
_UNC_TO_LINUX: Final[dict[str, str]] = {v: k for k, v in _LINUX_TO_UNC.items()}


class PathMappingError(ValueError):
    """Raised when a path cannot be mapped between Linux and Windows."""


def _normalise_linux(path: str) -> str:
    """Collapse backslashes to forward slashes; do not otherwise transform."""
    return path.replace("\\", "/")


def _normalise_windows(path: str) -> str:
    """Collapse forward slashes to backslashes; do not otherwise transform."""
    return path.replace("/", "\\")


def linux_to_drive(path: str) -> str:
    """Return the Windows drive-letter equivalent of a Linux NAS path.

    Only accepts paths rooted at ``/tech`` or ``/projects``.

    Raises:
        PathMappingError: If *path* is not rooted at a known NAS mount.

    """
    norm = _normalise_linux(path)
    # Ensure the prefix check treats ``/tech`` the same as ``/tech/``.
    candidate = norm if norm.endswith("/") else norm + "/"
    for linux_prefix, drive_prefix in _LINUX_TO_DRIVE.items():
        if candidate.startswith(linux_prefix):
            remainder = norm[len(linux_prefix.rstrip("/")) :].lstrip("/").rstrip("/")
            if not remainder:
                return drive_prefix
            return drive_prefix + remainder.replace("/", "\\")
    msg = f"Path not under a known NAS mount (/tech, /projects): {path!r}"
    raise PathMappingError(msg)


def linux_to_unc(path: str) -> str:
    """Return the Windows UNC equivalent of a Linux NAS path.

    Raises:
        PathMappingError: If *path* is not rooted at a known NAS mount.

    """
    norm = _normalise_linux(path)
    candidate = norm if norm.endswith("/") else norm + "/"
    for linux_prefix, unc_prefix in _LINUX_TO_UNC.items():
        if candidate.startswith(linux_prefix):
            remainder = norm[len(linux_prefix.rstrip("/")) :].lstrip("/").rstrip("/")
            if not remainder:
                return unc_prefix.rstrip("\\")
            return unc_prefix + remainder.replace("/", "\\")
    msg = f"Path not under a known NAS mount (/tech, /projects): {path!r}"
    raise PathMappingError(msg)


def drive_to_linux(path: str) -> str:
    """Return the Linux equivalent of a Windows drive-letter path.

    Raises:
        PathMappingError: If *path* is not under a known drive letter mapping.

    """
    norm = _normalise_windows(path)
    for drive_prefix, linux_prefix in _DRIVE_TO_LINUX.items():
        if norm.startswith(drive_prefix):
            remainder = norm[len(drive_prefix) :]
            return (linux_prefix + remainder.replace("\\", "/")).rstrip("/") or linux_prefix.rstrip("/")
    msg = f"Path not under a known Windows drive mapping (Z:, P:): {path!r}"
    raise PathMappingError(msg)


def unc_to_linux(path: str) -> str:
    """Return the Linux equivalent of a Windows UNC path.

    Raises:
        PathMappingError: If *path* is not under a known UNC mapping.

    """
    norm = _normalise_windows(path)
    for unc_prefix, linux_prefix in _UNC_TO_LINUX.items():
        if norm.startswith(unc_prefix):
            remainder = norm[len(unc_prefix) :]
            return (linux_prefix + remainder.replace("\\", "/")).rstrip("/") or linux_prefix.rstrip("/")
    msg = f"Path not under a known UNC mapping: {path!r}"
    raise PathMappingError(msg)
