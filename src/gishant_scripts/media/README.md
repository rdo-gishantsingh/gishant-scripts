# FFmpeg Media Converter

A powerful FFmpeg wrapper with preset configurations, Rich TUI, and interactive mode for easy media conversion.

## Features

- 🎬 **10+ Quality Presets** - Optimized configurations for common use cases
- 🎨 **Rich TUI** - Beautiful progress bars and styled output
- 🖱️ **Interactive Mode** - Guided preset selection
- 📊 **Media Info** - Detailed file information display
- ⚡ **Fast & Easy** - Simple CLI with sensible defaults

## Installation

```bash
# Install the package
pip install -e .

# Or with uv (recommended)
uv pip install -e .
```

## Quick Start

```bash
# Convert video for web
ffmpeg-convert convert input.mov -p web-video

# Interactive mode - guided conversion
ffmpeg-convert interactive video.mp4

# Show all available presets
ffmpeg-convert presets

# Get file information
ffmpeg-convert info video.mp4
```

## Available Presets

| Preset | Output | Description |
|--------|--------|-------------|
| `web-video` | `.mp4` | H.264 video optimized for web (balanced quality/size) |
| `web-video-hq` | `.mp4` | High quality H.264 video for web |
| `archive` | `.mp4` | High quality archival format (H.265/HEVC for space savings) |
| `mobile` | `.mp4` | Mobile-optimized video (smaller file size, 720p) |
| `mobile-vertical` | `.mp4` | Vertical video for mobile/social (9:16 aspect, 720x1280) |
| `gif` | `.gif` | Animated GIF with optimized palette |
| `audio-reduce` | `.mp3` | Reduce audio file size (128k MP3) |
| `audio-podcast` | `.mp3` | Podcast-optimized audio (mono, 64k) |
| `thumbnail` | `.jpg` | Extract video thumbnail (JPEG, first frame) |
| `preview` | `.mp4` | Quick preview (low quality, small size) |

## Usage Examples

### Basic Conversion

```bash
# Convert to web-optimized video
ffmpeg-convert convert input.mov -p web-video

# Convert with custom output path
ffmpeg-convert convert input.mov -o output.mp4 -p web-video-hq

# Overwrite existing file
ffmpeg-convert convert input.mov -p web-video -y
```

### Create Social Media Content

```bash
# Create animated GIF from video
ffmpeg-convert convert funny-cat.mp4 -p gif

# Create vertical mobile video
ffmpeg-convert convert landscape.mov -p mobile-vertical

# Extract thumbnail
ffmpeg-convert convert video.mp4 -p thumbnail
```

### Audio Processing

```bash
# Reduce audio file size
ffmpeg-convert convert podcast.wav -p audio-reduce

# Optimize for podcast distribution
ffmpeg-convert convert interview.mp3 -p audio-podcast
```

### File Information

```bash
# Show detailed media info
ffmpeg-convert info video.mp4

# Output as JSON
ffmpeg-convert info video.mp4 --json
```

### Interactive Mode

```bash
# Launch interactive preset selector
ffmpeg-convert interactive input.mov

# Interactive with custom output
ffmpeg-convert interactive input.mov -o custom_output.mp4
```

The interactive mode will:
1. Display all available presets in a table
2. Let you select a preset by number
3. Confirm overwrite if output file exists
4. Show a progress bar during conversion

### Advanced Options

```bash
# Disable progress bar
ffmpeg-convert convert input.mov -p web-video --no-progress

# Get help for any command
ffmpeg-convert convert --help
ffmpeg-convert --help
```

## Programmatic Usage

You can also use the FFmpeg converter in your Python code:

```python
from pathlib import Path
from gishant_scripts.media.ffmpeg_convert import FFmpegConverter

# Create converter instance
converter = FFmpegConverter()

# Basic conversion
output = converter.convert(
    input_path="input.mov",
    preset="web-video",
    overwrite=True
)

# Conversion with progress bar
from rich.console import Console
console = Console()

output = converter.convert_with_progress(
    input_path="input.mov",
    preset="web-video-hq",
    console=console
)

# Get file information
info = converter.get_info("video.mp4")
print(f"Duration: {info['format']['duration']}s")
print(f"Codec: {info['streams'][0]['codec_name']}")

# Use custom FFmpeg arguments
output = converter.convert(
    input_path="input.mov",
    output_path="output.mp4",
    custom_args=[
        "-c:v", "libx264",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "128k"
    ]
)
```

## Preset Details

### Web Video Presets

**web-video** - Balanced quality and file size
- Codec: H.264 (libx264)
- Audio: AAC 128k
- CRF: 23 (good quality)
- Optimized for web playback

**web-video-hq** - High quality for important content
- Codec: H.264 (libx264)
- Audio: AAC 192k
- CRF: 18 (high quality)
- Slower encoding for better quality

### Archive Preset

**archive** - Long-term storage with space efficiency
- Codec: H.265/HEVC (libx265)
- Audio: AAC 192k
- CRF: 20 (high quality)
- ~50% smaller than H.264 at same quality

### Mobile Presets

**mobile** - Standard mobile optimization
- Resolution: 1280x720
- Codec: H.264 (libx264)
- Audio: AAC 96k
- CRF: 28 (smaller files)

**mobile-vertical** - For social media stories/reels
- Resolution: 720x1280 (9:16 aspect ratio)
- Codec: H.264 (libx264)
- Audio: AAC 96k
- Optimized for vertical viewing

### Animation Preset

**gif** - Animated GIF creation
- Framerate: 15 fps
- Max width: 480px
- Optimized palette for best quality
- Good for short clips and reactions

### Audio Presets

**audio-reduce** - General audio compression
- Format: MP3
- Bitrate: 128k
- Good balance for music and speech

**audio-podcast** - Podcast optimization
- Format: MP3
- Bitrate: 64k mono
- Optimized for voice content
- Smallest file size for speech

### Utility Presets

**thumbnail** - Extract single frame
- Format: JPEG
- Extracts first frame
- High quality (q:v 2)

**preview** - Quick low-quality preview
- Resolution: 640x360
- CRF: 32 (low quality)
- Framerate: 24 fps
- Very fast encoding

## Requirements

- Python 3.11+
- FFmpeg installed and available in PATH
- Rich library for TUI
- Click library for CLI

### Installing FFmpeg

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows (Chocolatey):**
```bash
choco install ffmpeg
```

## Error Handling

The tool provides clear error messages:

```bash
# File not found
$ ffmpeg-convert convert missing.mp4 -p web-video
Error: Input file not found: missing.mp4

# Output exists without overwrite
$ ffmpeg-convert convert input.mov -p web-video
Error: Output file already exists: input_web-video.mp4. Use overwrite=True to replace.
Use --overwrite to replace existing file

# Missing preset
$ ffmpeg-convert convert input.mov
Error: --preset is required
Use 'ffmpeg-convert presets' to see available presets

# FFmpeg not installed
$ ffmpeg-convert convert input.mov -p web-video
Error: ffmpeg not found in PATH. Please install ffmpeg first.
```

## Tips & Best Practices

1. **Choose the right preset:**
   - `web-video` for general web use
   - `archive` for long-term storage
   - `mobile` for mobile devices
   - `gif` for short animations

2. **File size vs quality:**
   - CRF 18-23: High quality (larger files)
   - CRF 23-28: Good quality (balanced)
   - CRF 28+: Lower quality (smaller files)

3. **Use interactive mode** when unsure about presets

4. **Check file info** before conversion to understand source quality

5. **Enable overwrite** (`-y`) only when you're sure

## CLI Reference

### Commands

- `convert` - Convert a media file using a preset
- `presets` - List all available conversion presets
- `info` - Display media file information
- `interactive` - Interactive mode with preset selection

### Global Options

- `--version` - Show version and exit
- `--help` - Show help message

### Convert Options

- `-o, --output PATH` - Output file path (auto-generated if not specified)
- `-p, --preset PRESET` - Conversion preset to use (required)
- `-y, --overwrite` - Overwrite output file if it exists
- `--no-progress` - Disable progress bar

### Info Options

- `--json` - Output as JSON

## Contributing

Found a bug or want to add a preset? Contributions welcome!

## License

See main repository license.
