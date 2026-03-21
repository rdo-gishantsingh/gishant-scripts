"""FFmpeg conversion wrapper with preset support.

Provides the FFmpegConverter class for converting media files using
FFmpeg with preset configurations or custom arguments.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from gishant_scripts.media.presets import PresetType, get_preset


class FFmpegConverter:
    """FFmpeg conversion wrapper with preset support."""

    def __init__(self):
        """Initialize the converter and verify ffmpeg is available."""
        if not shutil.which("ffmpeg"):
            msg = "ffmpeg not found in PATH. Please install ffmpeg first."
            raise RuntimeError(msg)

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        preset: PresetType | None = None,
        custom_args: list[str] | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Convert a media file using a preset or custom arguments.

        Args:
            input_path: Path to input file
            output_path: Path to output file (auto-generated if None)
            preset: Preset name to use
            custom_args: Custom FFmpeg arguments (overrides preset)
            overwrite: Overwrite output file if it exists

        Returns:
            Path to output file

        Raises:
            FileNotFoundError: If input file doesn't exist
            RuntimeError: If conversion fails
            ValueError: If neither preset nor custom_args provided

        """
        input_file = Path(input_path)
        if not input_file.exists():
            msg = f"Input file not found: {input_path}"
            raise FileNotFoundError(msg)

        # Determine arguments
        if custom_args:
            ffmpeg_args = custom_args
            extension = output_path.suffix if output_path else ".mp4"
        elif preset:
            preset_config = get_preset(preset)
            ffmpeg_args = preset_config.to_ffmpeg_args()
            extension = f".{preset_config.extension}"
        else:
            msg = "Either preset or custom_args must be provided"
            raise ValueError(msg)

        # Determine output path
        if output_path:
            output_file = Path(output_path)
        else:
            output_file = input_file.with_suffix(extension)
            if preset:
                output_file = input_file.parent / f"{input_file.stem}_{preset}{extension}"

        # Check if output exists
        if output_file.exists() and not overwrite:
            msg = f"Output file already exists: {output_file}. Use overwrite=True to replace."
            raise FileExistsError(msg)

        # Build command
        cmd = ["ffmpeg"]
        if overwrite:
            cmd.append("-y")
        cmd.extend(["-i", str(input_file)])
        cmd.extend(ffmpeg_args)
        cmd.append(str(output_file))

        # Run conversion
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return output_file
        except subprocess.CalledProcessError as err:
            error_msg = f"FFmpeg conversion failed:\n{err.stderr}"
            raise RuntimeError(error_msg) from err

    def convert_with_progress(
        self,
        input_path: str | Path,
        output_path: str | Path | None = None,
        preset: PresetType | None = None,
        custom_args: list[str] | None = None,
        overwrite: bool = False,
        console: Console | None = None,
    ) -> Path:
        """Convert a media file with Rich progress bar.

        Args:
            input_path: Path to input file
            output_path: Path to output file (auto-generated if None)
            preset: Preset name to use
            custom_args: Custom FFmpeg arguments (overrides preset)
            overwrite: Overwrite output file if it exists
            console: Rich console for output (creates new if None)

        Returns:
            Path to output file

        Raises:
            FileNotFoundError: If input file doesn't exist
            RuntimeError: If conversion fails
            ValueError: If neither preset nor custom_args provided

        """
        if console is None:
            console = Console()

        input_file = Path(input_path)
        if not input_file.exists():
            msg = f"Input file not found: {input_path}"
            raise FileNotFoundError(msg)

        # Determine arguments and output path (same logic as convert())
        if custom_args:
            ffmpeg_args = custom_args
            extension = output_path.suffix if output_path else ".mp4"
        elif preset:
            preset_config = get_preset(preset)
            ffmpeg_args = preset_config.to_ffmpeg_args()
            extension = f".{preset_config.extension}"
        else:
            msg = "Either preset or custom_args must be provided"
            raise ValueError(msg)

        if output_path:
            output_file = Path(output_path)
        else:
            output_file = input_file.with_suffix(extension)
            if preset:
                output_file = input_file.parent / f"{input_file.stem}_{preset}{extension}"

        if output_file.exists() and not overwrite:
            msg = f"Output file already exists: {output_file}. Use overwrite=True to replace."
            raise FileExistsError(msg)

        # Build command
        cmd = ["ffmpeg"]
        if overwrite:
            cmd.append("-y")
        cmd.extend(["-i", str(input_file)])
        cmd.extend(ffmpeg_args)
        # Add progress output for parsing
        cmd.extend(["-progress", "pipe:1"])
        cmd.append(str(output_file))

        # Run conversion with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Converting {input_file.name}...",
                total=100,
            )

            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                # Parse progress from ffmpeg output
                duration = None
                for line in process.stdout:
                    if "duration=" in line:
                        try:
                            # Parse duration in microseconds
                            dur_str = line.split("duration=")[1].strip()
                            duration = float(dur_str) / 1_000_000  # Convert to seconds
                        except (ValueError, IndexError):
                            pass
                    elif "out_time_us=" in line and duration:
                        try:
                            # Parse current time in microseconds
                            time_str = line.split("out_time_us=")[1].strip()
                            current_time = float(time_str) / 1_000_000
                            percentage = min(100, (current_time / duration) * 100)
                            progress.update(task, completed=percentage)
                        except (ValueError, IndexError, ZeroDivisionError):
                            pass

                process.wait()

                if process.returncode != 0:
                    stderr = process.stderr.read() if process.stderr else "Unknown error"
                    error_msg = f"FFmpeg conversion failed:\n{stderr}"
                    raise RuntimeError(error_msg)

                progress.update(task, completed=100)
                return output_file

            except subprocess.CalledProcessError as err:
                error_msg = f"FFmpeg conversion failed:\n{err.stderr}"
                raise RuntimeError(error_msg) from err

    def get_info(self, input_path: str | Path) -> dict:
        """Get media file information using ffprobe.

        Args:
            input_path: Path to media file

        Returns:
            Dictionary with file information

        Raises:
            FileNotFoundError: If input file doesn't exist
            RuntimeError: If ffprobe fails

        """
        input_file = Path(input_path)
        if not input_file.exists():
            msg = f"Input file not found: {input_path}"
            raise FileNotFoundError(msg)

        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(input_file),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            import json

            return json.loads(result.stdout)
        except subprocess.CalledProcessError as err:
            error_msg = f"FFprobe failed:\n{err.stderr}"
            raise RuntimeError(error_msg) from err
        except json.JSONDecodeError as err:
            error_msg = f"Failed to parse ffprobe output: {err}"
            raise RuntimeError(error_msg) from err
