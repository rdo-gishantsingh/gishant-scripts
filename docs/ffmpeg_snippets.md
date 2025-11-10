### Compress video for github PR

```bash
ffmpeg -i "video.mp4" -vf "scale=1280:720" -c:v libx264 -preset medium -crf 28 -c:a aac -b:a 128k "video_resized.mp4"