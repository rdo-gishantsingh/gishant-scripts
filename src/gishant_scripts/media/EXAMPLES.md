# FFmpeg Convert - Quick Examples

## Installation

```bash
cd /home/gisi/dev/repos/gishant-scripts
uv pip install -e .
```

## Basic Usage Examples

### 1. List Available Presets

```bash
ffmpeg-convert presets
```

Output:
```
                                 Available FFmpeg Presets
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Preset          ┃ Output ┃ Description                                                 ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ web-video       │ .mp4   │ H.264 video optimized for web (balanced quality/size)       │
│ web-video-hq    │ .mp4   │ High quality H.264 video for web                            │
│ archive         │ .mp4   │ High quality archival format (H.265/HEVC for space savings) │
│ mobile          │ .mp4   │ Mobile-optimized video (smaller file size, 720p)            │
│ mobile-vertical │ .mp4   │ Vertical video for mobile/social (9:16 aspect, 720x1280)    │
│ gif             │ .gif   │ Animated GIF with optimized palette                         │
│ audio-reduce    │ .mp3   │ Reduce audio file size (128k MP3)                           │
│ audio-podcast   │ .mp3   │ Podcast-optimized audio (mono, 64k)                         │
│ thumbnail       │ .jpg   │ Extract video thumbnail (JPEG, first frame)                 │
│ preview         │ .mp4   │ Quick preview (low quality, small size)                     │
└─────────────────┴────────┴─────────────────────────────────────────────────────────────┘
```

### 2. Convert Video for Web

```bash
# Basic conversion
ffmpeg-convert convert input.mov -p web-video

# With custom output path
ffmpeg-convert convert input.mov -o output.mp4 -p web-video

# High quality web video
ffmpeg-convert convert input.mov -p web-video-hq -y
```

### 3. Create Animated GIF

```bash
ffmpeg-convert convert funny-video.mp4 -p gif
```

### 4. Mobile Video

```bash
# Standard mobile
ffmpeg-convert convert video.mp4 -p mobile

# Vertical/portrait for social media
ffmpeg-convert convert landscape.mp4 -p mobile-vertical
```

### 5. Get File Information

```bash
# Human-readable format
ffmpeg-convert info video.mp4

# JSON output
ffmpeg-convert info video.mp4 --json
```

Example output:
```
File: video.mp4

Format Information:
  Format: mov,mp4,m4a,3gp,3g2,mj2
  Duration: 120.50s
  Size: 45.23 MB
  Bitrate: 3000 kbps

Stream 0 (video):
  Codec: h264
  Resolution: 1920x1080
  FPS: 30.0
```

### 6. Interactive Mode

```bash
ffmpeg-convert interactive input.mov
```

Interactive session:
```
FFmpeg Interactive Converter

Input file: input.mov

                                 Available FFmpeg Presets
┏━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ Preset          ┃ Output ┃ Description                                                 ┃
┡━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ web-video       │ .mp4   │ H.264 video optimized for web (balanced quality/size)       │
│ 2 │ web-video-hq    │ .mp4   │ High quality H.264 video for web                            │
...
└───┴─────────────────┴────────┴─────────────────────────────────────────────────────────────┘

Select preset [1-10]: 1

Selected: web-video

⠹ Converting input.mov... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:05

✓ Conversion complete: input_web-video.mp4
```

### 7. Audio Conversion

```bash
# Reduce file size
ffmpeg-convert convert large-audio.wav -p audio-reduce

# Optimize for podcast
ffmpeg-convert convert interview.mp3 -p audio-podcast
```

### 8. Extract Thumbnail

```bash
ffmpeg-convert convert video.mp4 -p thumbnail
```

### 9. Create Preview

```bash
# Quick low-quality preview
ffmpeg-convert convert long-video.mp4 -p preview
```

## Advanced Usage

### With Progress Bar (Default)

```bash
ffmpeg-convert convert input.mov -p web-video
# Shows: ⠹ Converting input.mov... ━━━━━━━━━━ 45% 0:00:23
```

### Without Progress Bar

```bash
ffmpeg-convert convert input.mov -p web-video --no-progress
```

### Overwrite Existing Files

```bash
ffmpeg-convert convert input.mov -p web-video -y
# or
ffmpeg-convert convert input.mov -p web-video --overwrite
```

## Programmatic Usage

```python
from gishant_scripts.media.ffmpeg_convert import FFmpegConverter
from rich.console import Console

# Create converter
converter = FFmpegConverter()

# Simple conversion
output = converter.convert(
    "input.mov",
    preset="web-video",
    overwrite=True
)
print(f"Output: {output}")

# With progress bar
console = Console()
output = converter.convert_with_progress(
    "input.mov",
    preset="web-video-hq",
    console=console
)

# Get file info
info = converter.get_info("video.mp4")
print(f"Duration: {info['format']['duration']}s")
```

## Tips

1. **Use interactive mode** when unsure which preset to use
2. **Check file info** before conversion to understand source quality
3. **Use preview preset** to quickly test conversions before committing to high quality
4. **Archive preset** uses H.265 which produces smaller files but takes longer to encode
5. **Mobile presets** significantly reduce file size for sharing

## Common Workflows

### Social Media Workflow
```bash
# 1. Check original video
ffmpeg-convert info raw-video.mp4

# 2. Create vertical version for stories
ffmpeg-convert convert raw-video.mp4 -p mobile-vertical

# 3. Create GIF for previews
ffmpeg-convert convert raw-video.mp4 -p gif
```

### Podcast Workflow
```bash
# 1. Check audio quality
ffmpeg-convert info raw-audio.wav

# 2. Convert to podcast format
ffmpeg-convert convert raw-audio.wav -p audio-podcast

# 3. Verify output
ffmpeg-convert info raw-audio.mp3
```

### Web Publishing Workflow
```bash
# 1. High quality version
ffmpeg-convert convert source.mov -p web-video-hq -o video-hq.mp4

# 2. Mobile version
ffmpeg-convert convert source.mov -p mobile -o video-mobile.mp4

# 3. Thumbnail
ffmpeg-convert convert source.mov -p thumbnail -o poster.jpg

# 4. Preview/trailer
ffmpeg-convert convert source.mov -p preview -o preview.mp4
```
