"""FFmpeg conversion utilities with preset configurations.

Thin re-export module that preserves the entry point
``gishant_scripts.media.ffmpeg_convert:cli`` referenced in pyproject.toml.

Actual implementations live in:
- ``gishant_scripts.media.presets`` -- preset definitions
- ``gishant_scripts.media.converter`` -- FFmpegConverter class
- ``gishant_scripts.media.cli`` -- Typer CLI commands
"""

from __future__ import annotations

from gishant_scripts.media.cli import cli
from gishant_scripts.media.converter import FFmpegConverter
from gishant_scripts.media.presets import (
    PRESETS,
    ConversionPreset,
    PresetType,
    get_all_presets,
    get_preset,
)

__all__ = [
    "PRESETS",
    "ConversionPreset",
    "FFmpegConverter",
    "PresetType",
    "cli",
    "get_all_presets",
    "get_preset",
]

if __name__ == "__main__":
    cli()
