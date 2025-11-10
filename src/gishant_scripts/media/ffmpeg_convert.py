"""FFmpeg conversion utilities with preset configurations."""

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
