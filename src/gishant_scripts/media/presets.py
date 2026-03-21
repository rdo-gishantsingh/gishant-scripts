"""FFmpeg conversion preset definitions.

Contains the ConversionPreset dataclass, the PRESETS dictionary mapping
preset names to their configurations, and helper functions for accessing them.
"""

from __future__ import annotations

from dataclasses import dataclass
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
