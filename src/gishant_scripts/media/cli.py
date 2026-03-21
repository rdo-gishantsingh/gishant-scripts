"""Typer CLI commands for FFmpeg media conversion.

Provides the command-line interface for converting media files
using presets, displaying file info, and interactive mode.
"""

from __future__ import annotations

import enum
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from gishant_scripts.media.converter import FFmpegConverter
from gishant_scripts.media.presets import PRESETS


def _parse_frame_rate(rate_str: str) -> str:
    """Safely parse ffprobe frame rate string like '30/1' or '24000/1001'."""
    parts = rate_str.split("/")
    if len(parts) == 2:
        try:
            return f"{int(parts[0]) / int(parts[1]):.2f}"
        except (ValueError, ZeroDivisionError):
            return rate_str
    return rate_str


class CLIPreset(enum.StrEnum):
    """All presets available in the CLI."""

    web_video = "web-video"
    web_video_hq = "web-video-hq"
    archive = "archive"
    mobile = "mobile"
    mobile_vertical = "mobile-vertical"
    gif = "gif"
    audio_reduce = "audio-reduce"
    audio_podcast = "audio-podcast"
    thumbnail = "thumbnail"
    preview = "preview"


cli = typer.Typer(
    name="ffmpeg-convert",
    help="FFmpeg media conversion tool with presets.\n\nConvert video and audio files using optimized presets or custom FFmpeg arguments.",
    no_args_is_help=True,
)

_console = Console()


@cli.command()
def convert(
    input_file: Annotated[Path, typer.Argument(exists=True, help="Input media file")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (auto-generated if not specified)"),
    ] = None,
    preset: Annotated[
        CLIPreset | None,
        typer.Option("--preset", "-p", help="Conversion preset to use"),
    ] = None,
    overwrite: Annotated[
        bool,
        typer.Option("--overwrite", "-y", help="Overwrite output file if it exists"),
    ] = False,
    no_progress: Annotated[
        bool,
        typer.Option("--no-progress", help="Disable progress bar"),
    ] = False,
) -> None:
    """Convert a media file using a preset.

    Examples:
        ffmpeg-convert convert input.mov -p web-video
        ffmpeg-convert convert input.mov -o output.mp4 -p web-video-hq
        ffmpeg-convert convert video.mp4 -p gif

    """
    if not preset:
        _console.print("[red]Error: --preset is required[/red]")
        _console.print("Use 'ffmpeg-convert presets' to see available presets")
        sys.exit(1)

    try:
        converter = FFmpegConverter()

        if no_progress:
            output_file = converter.convert(
                input_file,
                output,
                preset=preset.value,
                overwrite=overwrite,
            )
        else:
            output_file = converter.convert_with_progress(
                input_file,
                output,
                preset=preset.value,
                overwrite=overwrite,
                console=_console,
            )

        _console.print(f"[green]✓[/green] Conversion complete: {output_file}")

    except FileExistsError as err:
        _console.print(f"[red]Error:[/red] {err}")
        _console.print("Use --overwrite to replace existing file")
        sys.exit(1)
    except RuntimeError as err:
        _console.print(f"[red]Error:[/red] {err}")
        sys.exit(1)
    except Exception as err:
        _console.print(f"[red]Unexpected error:[/red] {err}")
        sys.exit(1)


@cli.command()
def presets() -> None:
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

    _console.print(table)
    _console.print("\n[dim]Use 'ffmpeg-convert convert INPUT -p PRESET' to convert a file[/dim]")


@cli.command()
def info(
    input_file: Annotated[Path, typer.Argument(exists=True, help="Input media file")],
    output_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Display media file information.

    Shows codec, resolution, duration, bitrate, and other metadata.

    Examples:
        ffmpeg-convert info video.mp4
        ffmpeg-convert info video.mp4 --json

    """
    try:
        converter = FFmpegConverter()
        file_info = converter.get_info(input_file)

        if output_json:
            _console.print_json(data=file_info)
        else:
            # Display formatted info
            _console.print(f"\n[bold cyan]File:[/bold cyan] {input_file}\n")

            # Format info
            format_info = file_info.get("format", {})
            _console.print("[bold]Format Information:[/bold]")
            _console.print(f"  Format: {format_info.get('format_name', 'N/A')}")
            _console.print(f"  Duration: {float(format_info.get('duration', 0)):.2f}s")
            _console.print(f"  Size: {int(format_info.get('size', 0)) / 1024 / 1024:.2f} MB")
            _console.print(f"  Bitrate: {int(format_info.get('bit_rate', 0)) / 1000:.0f} kbps")

            # Stream info
            streams = file_info.get("streams", [])
            for idx, stream in enumerate(streams):
                _console.print(f"\n[bold]Stream {idx} ({stream.get('codec_type', 'unknown')}):[/bold]")
                _console.print(f"  Codec: {stream.get('codec_name', 'N/A')}")
                if stream.get("codec_type") == "video":
                    _console.print(f"  Resolution: {stream.get('width', 'N/A')}x{stream.get('height', 'N/A')}")
                    fps = _parse_frame_rate(stream.get("r_frame_rate", "0/1"))
                    _console.print(f"  FPS: {fps}")
                elif stream.get("codec_type") == "audio":
                    _console.print(f"  Sample Rate: {stream.get('sample_rate', 'N/A')} Hz")
                    _console.print(f"  Channels: {stream.get('channels', 'N/A')}")

    except RuntimeError as err:
        _console.print(f"[red]Error:[/red] {err}")
        sys.exit(1)
    except Exception as err:
        _console.print(f"[red]Unexpected error:[/red] {err}")
        sys.exit(1)


@cli.command()
def interactive(
    input_file: Annotated[Path, typer.Argument(exists=True, help="Input media file")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file path (auto-generated if not specified)"),
    ] = None,
) -> None:
    """Interactive mode with preset selection.

    Guides you through selecting a preset and configuring conversion options.

    Example:
        ffmpeg-convert interactive video.mov

    """
    _console.print("[bold cyan]FFmpeg Interactive Converter[/bold cyan]\n")
    _console.print(f"Input file: [green]{input_file}[/green]\n")

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

    _console.print(table)
    _console.print()

    # Prompt for preset selection
    while True:
        choice = Prompt.ask(
            "Select preset",
            choices=[str(i) for i in range(1, len(preset_list) + 1)],
        )
        preset_name = preset_list[int(choice) - 1][0]
        break

    _console.print(f"\nSelected: [green]{preset_name}[/green]\n")

    # Confirm overwrite if needed
    overwrite = False
    if output and Path(output).exists():
        overwrite = Confirm.ask(f"Output file {output} exists. Overwrite?")
        if not overwrite:
            _console.print("[yellow]Cancelled[/yellow]")
            return

    # Perform conversion
    try:
        converter = FFmpegConverter()
        output_file = converter.convert_with_progress(
            input_file,
            output,
            preset=preset_name,
            overwrite=overwrite,
            console=_console,
        )
        _console.print(f"\n[green]✓[/green] Conversion complete: {output_file}")

    except Exception as err:
        _console.print(f"\n[red]Error:[/red] {err}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
