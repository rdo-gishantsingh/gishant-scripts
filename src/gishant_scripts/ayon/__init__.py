"""AYON integration utilities for gishant-scripts."""

from __future__ import annotations

__all__: list[str] = []

try:
    from gishant_scripts.ayon.analyze_bundles import analyze_bundles_cli

    __all__.append("analyze_bundles_cli")
except ImportError:
    pass
