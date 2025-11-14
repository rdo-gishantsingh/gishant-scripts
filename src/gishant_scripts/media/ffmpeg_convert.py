"""FFmpeg conversion utilities with preset configurations.

Provides both a programmatic API and a CLI for converting media files
using FFmpeg with predefined quality presets and custom configurations.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import click
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

PresetType = Literal[
    "web-video",
    "web-video-hq",
    "archive",
    "mobile",
    "mobile-vertical",
    "gif",
    "audio-reduce",
    "audio-podcast",
    "thumbnail",
    "preview",
]


@dataclass
class ConversionPreset:
    """FFmpeg conversion preset configuration."""

    name: str
    description: str
    extension: str
    video_codec: str | None = None
    audio_codec: str | None = None
    video_bitrate: str | None = None
    audio_bitrate: str | None = None
    resolution: str | None = None
    framerate: int | None = None
    crf: int | None = None
    pixel_format: str | None = None
    extra_args: list[str] | None = None

    def to_ffmpeg_args(self) -> list[str]:
        """Convert preset to FFmpeg command arguments."""
        args = []

        if self.video_codec:
            args.extend(["-c:v", self.video_codec])

        if self.audio_codec:
            args.extend(["-c:a", self.audio_codec])

        if self.video_bitrate:
            args.extend(["-b:v", self.video_bitrate])

        if self.audio_bitrate:
            args.extend(["-b:a", self.audio_bitrate])

        if self.resolution:
            args.extend(["-vf", f"scale={self.resolution}"])

        if self.framerate:
            args.extend(["-r", str(self.framerate)])

        if self.crf is not None:
            args.extend(["-crf", str(self.crf)])

        if self.pixel_format:
            args.extend(["-pix_fmt", self.pixel_format])

        if self.extra_args:
            args.extend(self.extra_args)

        return args


# Preset configurations
PRESETS: dict[PresetType, ConversionPreset] = {
    "web-video": ConversionPreset(
        name="web-video",
        description="H.264 video optimized for web (balanced quality/size)",
        extension="mp4",
        video_codec="libx264",
        audio_codec="aac",
        audio_bitrate="128k",
        crf=23,
        pixel_format="yuv420p",
        extra_args=["-preset", "medium", "-movflags", "+faststart"],
    ),
    "web-video-hq": ConversionPreset(
        name="web-video-hq",
        description="High quality H.264 video for web",
        extension="mp4",
        video_codec="libx264",
        audio_codec="aac",
        audio_bitrate="192k",
        crf=18,
        pixel_format="yuv420p",
        extra_args=["-preset", "slow", "-movflags", "+faststart"],
    ),
    "archive": ConversionPreset(
        name="archive",
        description="High quality archival format (H.265/HEVC for space savings)",
        extension="mp4",
        video_codec="libx265",
        audio_codec="aac",
        audio_bitrate="192k",
        crf=20,
        extra_args=["-preset", "medium", "-tag:v", "hvc1"],
    ),
    "mobile": ConversionPreset(
        name="mobile",
        description="Mobile-optimized video (smaller file size, 720p)",
        extension="mp4",
        video_codec="libx264",
        audio_codec="aac",
        resolution="1280:720",
        audio_bitrate="96k",
        crf=28,
        pixel_format="yuv420p",
        extra_args=["-preset", "fast", "-movflags", "+faststart"],
    ),
    "mobile-vertical": ConversionPreset(
        name="mobile-vertical",
        description="Vertical video for mobile/social (9:16 aspect, 720x1280)",
        extension="mp4",
        video_codec="libx264",
        audio_codec="aac",
        resolution="720:1280",
        audio_bitrate="96k",
        crf=28,
        pixel_format="yuv420p",
        extra_args=["-preset", "fast", "-movflags", "+faststart"],
    ),
    "gif": ConversionPreset(
        name="gif",
        description="Animated GIF with optimized palette",
        extension="gif",
        framerate=15,
        resolution="480:-1",
        extra_args=[
            "-vf",
            "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
        ],
    ),
    "audio-reduce": ConversionPreset(
        name="audio-reduce",
        description="Reduce audio file size (128k MP3)",
        extension="mp3",
        audio_codec="libmp3lame",
        audio_bitrate="128k",
        extra_args=["-q:a", "2"],
    ),
    "audio-podcast": ConversionPreset(
        name="audio-podcast",
        description="Podcast-optimized audio (mono, 64k)",
        extension="mp3",
        audio_codec="libmp3lame",
        audio_bitrate="64k",
        extra_args=["-ac", "1", "-q:a", "2"],
    ),
    "thumbnail": ConversionPreset(
        name="thumbnail",
        description="Extract video thumbnail (JPEG, first frame)",
        extension="jpg",
        video_codec="mjpeg",
        extra_args=["-vframes", "1", "-q:v", "2"],
    ),
    "preview": ConversionPreset(
        name="preview",
        description="Quick preview (low quality, small size)",
        extension="mp4",
        video_codec="libx264",
        audio_codec="aac",
        resolution="640:360",
        audio_bitrate="64k",
        crf=32,
        framerate=24,
        extra_args=["-preset", "veryfast"],
    ),
}


def get_preset(name: PresetType) -> ConversionPreset:
    """Get a conversion preset by name.

    Args:
        name: Name of the preset

    Returns:
        ConversionPreset configuration

    Raises:
        KeyError: If preset name is not found
    """
    return PRESETS[name]


def get_all_presets() -> dict[PresetType, ConversionPreset]:
    """Get all available conversion presets.

    Returns:
        Dictionary of all presets
    """
    return PRESETS.copy()


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


# ============================================================================
# CLI Implementation
# ============================================================================

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """FFmpeg media conversion tool with presets.

    Convert video and audio files using optimized presets or custom FFmpeg arguments.
    """
    pass


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (auto-generated if not specified)",
)
@click.option(
    "-p",
    "--preset",
    type=click.Choice(
        [
            "web-video",
            "web-video-hq",
            "archive",
            "mobile",
            "mobile-vertical",
            "gif",
            "audio-reduce",
            "audio-podcast",
            "thumbnail",
            "preview",
        ]
    ),
    help="Conversion preset to use",
)
@click.option(
    "-y",
    "--overwrite",
    is_flag=True,
    help="Overwrite output file if it exists",
)
@click.option(
    "--no-progress",
    is_flag=True,
    help="Disable progress bar",
)
def convert(input_file, output, preset, overwrite, no_progress):
    """Convert a media file using a preset.

    Examples:

        \b
        # Convert to web-optimized video
        ffmpeg-convert convert input.mov -p web-video

        \b
        # Convert with custom output path
        ffmpeg-convert convert input.mov -o output.mp4 -p web-video-hq

        \b
        # Create animated GIF
        ffmpeg-convert convert video.mp4 -p gif
    """
    if not preset:
        console.print("[red]Error: --preset is required[/red]")
        console.print("Use 'ffmpeg-convert presets' to see available presets")
        sys.exit(1)

    try:
        converter = FFmpegConverter()

        if no_progress:
            output_file = converter.convert(
                input_file,
                output,
                preset=preset,
                overwrite=overwrite,
            )
        else:
            output_file = converter.convert_with_progress(
                input_file,
                output,
                preset=preset,
                overwrite=overwrite,
                console=console,
            )

        console.print(f"[green]✓[/green] Conversion complete: {output_file}")

    except FileExistsError as err:
        console.print(f"[red]Error:[/red] {err}")
        console.print("Use --overwrite to replace existing file")
        sys.exit(1)
    except RuntimeError as err:
        console.print(f"[red]Error:[/red] {err}")
        sys.exit(1)
    except Exception as err:
        console.print(f"[red]Unexpected error:[/red] {err}")
        sys.exit(1)


@cli.command()
def presets():
    """List all available conversion presets."""
    table = Table(title="Available FFmpeg Presets", show_header=True, header_style="bold cyan")
    table.add_column("Preset", style="green", no_wrap=True)
    table.add_column("Output", style="yellow")
    table.add_column("Description", style="white")

    for preset_name, preset_config in PRESETS.items():
        table.add_row(
            preset_name,
            f".{preset_config.extension}",
            preset_config.description,
        )

    console.print(table)
    console.print(
        "\n[dim]Use 'ffmpeg-convert convert INPUT -p PRESET' to convert a file[/dim]"
    )


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
def info(input_file, output_json):
    """Display media file information.

    Shows codec, resolution, duration, bitrate, and other metadata.

    Examples:

        \b
        # Show file info
        ffmpeg-convert info video.mp4

        \b
        # Output as JSON
        ffmpeg-convert info video.mp4 --json
    """
    try:
        converter = FFmpegConverter()
        file_info = converter.get_info(input_file)

        if output_json:
            console.print_json(data=file_info)
        else:
            # Display formatted info
            console.print(f"\n[bold cyan]File:[/bold cyan] {input_file}\n")

            # Format info
            format_info = file_info.get("format", {})
            console.print("[bold]Format Information:[/bold]")
            console.print(f"  Format: {format_info.get('format_name', 'N/A')}")
            console.print(f"  Duration: {float(format_info.get('duration', 0)):.2f}s")
            console.print(f"  Size: {int(format_info.get('size', 0)) / 1024 / 1024:.2f} MB")
            console.print(
                f"  Bitrate: {int(format_info.get('bit_rate', 0)) / 1000:.0f} kbps"
            )

            # Stream info
            streams = file_info.get("streams", [])
            for idx, stream in enumerate(streams):
                console.print(f"\n[bold]Stream {idx} ({stream.get('codec_type', 'unknown')}):[/bold]")
                console.print(f"  Codec: {stream.get('codec_name', 'N/A')}")
                if stream.get("codec_type") == "video":
                    console.print(f"  Resolution: {stream.get('width', 'N/A')}x{stream.get('height', 'N/A')}")
                    console.print(f"  FPS: {eval(stream.get('r_frame_rate', '0/1'))}")
                elif stream.get("codec_type") == "audio":
                    console.print(f"  Sample Rate: {stream.get('sample_rate', 'N/A')} Hz")
                    console.print(f"  Channels: {stream.get('channels', 'N/A')}")

    except RuntimeError as err:
        console.print(f"[red]Error:[/red] {err}")
        sys.exit(1)
    except Exception as err:
        console.print(f"[red]Unexpected error:[/red] {err}")
        sys.exit(1)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output file path (auto-generated if not specified)",
)
def interactive(input_file, output):
    """Interactive mode with preset selection.

    Guides you through selecting a preset and configuring conversion options.

    Example:

        \b
        ffmpeg-convert interactive video.mov
    """
    console.print("[bold cyan]FFmpeg Interactive Converter[/bold cyan]\n")
    console.print(f"Input file: [green]{input_file}[/green]\n")

    # Display preset options in a table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim")
    table.add_column("Preset", style="green")
    table.add_column("Output", style="yellow")
    table.add_column("Description", style="white")

    preset_list = list(PRESETS.items())
    for idx, (preset_name, preset_config) in enumerate(preset_list, 1):
        table.add_row(
            str(idx),
            preset_name,
            f".{preset_config.extension}",
            preset_config.description,
        )

    console.print(table)
    console.print()

    # Prompt for preset selection
    while True:
        choice = Prompt.ask(
            "Select preset",
            choices=[str(i) for i in range(1, len(preset_list) + 1)],
        )
        preset_name = preset_list[int(choice) - 1][0]
        break

    console.print(f"\nSelected: [green]{preset_name}[/green]\n")

    # Confirm overwrite if needed
    overwrite = False
    if output and Path(output).exists():
        overwrite = Confirm.ask(f"Output file {output} exists. Overwrite?")
        if not overwrite:
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Perform conversion
    try:
        converter = FFmpegConverter()
        output_file = converter.convert_with_progress(
            input_file,
            output,
            preset=preset_name,
            overwrite=overwrite,
            console=console,
        )
        console.print(f"\n[green]✓[/green] Conversion complete: {output_file}")

    except Exception as err:
        console.print(f"\n[red]Error:[/red] {err}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
