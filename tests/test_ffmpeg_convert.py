"""Tests for FFmpeg converter functionality."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from gishant_scripts.media.ffmpeg_convert import (
    PRESETS,
    FFmpegConverter,
    cli,
    get_all_presets,
    get_preset,
)


@pytest.fixture
def sample_video_path(tmp_path):
    """Create a sample video file path for testing."""
    video_file = tmp_path / "test_video.mp4"
    video_file.touch()
    return video_file


@pytest.fixture
def converter():
    """Create an FFmpegConverter instance."""
    with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        return FFmpegConverter()


class TestPresets:
    """Test preset functionality."""

    def test_get_preset_valid(self):
        """Test getting a valid preset."""
        preset = get_preset("web-video")
        assert preset.name == "web-video"
        assert preset.extension == "mp4"
        assert preset.video_codec == "libx264"

    def test_get_preset_invalid(self):
        """Test getting an invalid preset raises KeyError."""
        with pytest.raises(KeyError):
            get_preset("invalid-preset")

    def test_get_all_presets(self):
        """Test getting all presets returns a copy."""
        presets = get_all_presets()
        assert len(presets) == len(PRESETS)
        assert presets is not PRESETS  # Should be a copy

    def test_preset_to_ffmpeg_args(self):
        """Test converting preset to FFmpeg arguments."""
        preset = get_preset("web-video")
        args = preset.to_ffmpeg_args()

        assert "-c:v" in args
        assert "libx264" in args
        assert "-c:a" in args
        assert "aac" in args
        assert "-crf" in args
        assert "23" in args

    def test_all_presets_have_required_fields(self):
        """Test all presets have required fields."""
        for preset_name, preset in PRESETS.items():
            assert preset.name == preset_name
            assert preset.description
            assert preset.extension


class TestFFmpegConverter:
    """Test FFmpegConverter class."""

    def test_init_no_ffmpeg(self):
        """Test initialization fails when ffmpeg not found."""
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                FFmpegConverter()

    def test_init_with_ffmpeg(self):
        """Test initialization succeeds when ffmpeg is found."""
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            converter = FFmpegConverter()
            assert converter is not None

    def test_convert_file_not_found(self, converter):
        """Test conversion fails when input file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            converter.convert("nonexistent.mp4", preset="web-video")

    def test_convert_no_preset_no_args(self, converter, sample_video_path):
        """Test conversion fails without preset or custom args."""
        with pytest.raises(ValueError, match="Either preset or custom_args"):
            converter.convert(sample_video_path)

    def test_convert_output_exists_no_overwrite(self, converter, sample_video_path, tmp_path):
        """Test conversion fails when output exists and overwrite=False."""
        output = tmp_path / "output.mp4"
        output.touch()

        with pytest.raises(FileExistsError, match="already exists"):
            converter.convert(sample_video_path, output, preset="web-video")

    @patch("subprocess.run")
    def test_convert_success_with_preset(self, mock_run, converter, sample_video_path, tmp_path):
        """Test successful conversion with preset."""
        mock_run.return_value = Mock(returncode=0)
        output = tmp_path / "output.mp4"

        result = converter.convert(
            sample_video_path,
            output,
            preset="web-video",
            overwrite=True,
        )

        assert result == output
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "ffmpeg" in call_args
        assert "-y" in call_args
        assert str(sample_video_path) in call_args
        assert str(output) in call_args

    @patch("subprocess.run")
    def test_convert_success_with_custom_args(self, mock_run, converter, sample_video_path, tmp_path):
        """Test successful conversion with custom arguments."""
        mock_run.return_value = Mock(returncode=0)
        output = tmp_path / "output.mp4"

        result = converter.convert(
            sample_video_path,
            output,
            custom_args=["-c:v", "libx264", "-crf", "20"],
            overwrite=True,
        )

        assert result == output
        call_args = mock_run.call_args[0][0]
        assert "-c:v" in call_args
        assert "libx264" in call_args

    @patch("subprocess.run")
    def test_convert_ffmpeg_failure(self, mock_run, converter, sample_video_path, tmp_path):
        """Test conversion handles FFmpeg failure."""
        mock_run.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["ffmpeg"], stderr="FFmpeg error message"
        )
        output = tmp_path / "output.mp4"

        with pytest.raises(RuntimeError, match="FFmpeg conversion failed"):
            converter.convert(sample_video_path, output, preset="web-video", overwrite=True)

    @patch("subprocess.run")
    def test_get_info_success(self, mock_run, converter, sample_video_path):
        """Test getting file info successfully."""
        mock_info = {
            "format": {"duration": "120.5", "size": "10485760", "bit_rate": "696320"},
            "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080}],
        }
        mock_run.return_value = Mock(returncode=0, stdout=json.dumps(mock_info))

        result = converter.get_info(sample_video_path)

        assert result == mock_info
        assert result["format"]["duration"] == "120.5"
        assert result["streams"][0]["codec_name"] == "h264"

    @patch("subprocess.run")
    def test_get_info_ffprobe_failure(self, mock_run, converter, sample_video_path):
        """Test get_info handles ffprobe failure."""
        mock_run.side_effect = subprocess.CalledProcessError(returncode=1, cmd=["ffprobe"], stderr="FFprobe error")

        with pytest.raises(RuntimeError, match="FFprobe failed"):
            converter.get_info(sample_video_path)

    @patch("subprocess.Popen")
    def test_convert_with_progress(self, mock_popen, converter, sample_video_path, tmp_path):
        """Test conversion with progress bar."""
        # Mock ffmpeg process
        mock_process = Mock()
        mock_process.stdout = [
            "duration=1000000\n",
            "out_time_us=500000\n",
            "out_time_us=1000000\n",
        ]
        mock_process.wait.return_value = None
        mock_process.returncode = 0
        mock_process.stderr = None
        mock_popen.return_value = mock_process

        output = tmp_path / "output.mp4"

        from rich.console import Console

        console = Console()

        result = converter.convert_with_progress(
            sample_video_path,
            output,
            preset="web-video",
            overwrite=True,
            console=console,
        )

        assert result == output
        mock_popen.assert_called_once()


class TestCLI:
    """Test CLI commands."""

    def test_cli_help(self):
        """Test CLI help message."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "FFmpeg media conversion tool" in result.output

    def test_cli_version(self):
        """Test CLI version."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_presets_command(self):
        """Test presets command."""
        runner = CliRunner()
        result = runner.invoke(cli, ["presets"])
        assert result.exit_code == 0
        assert "web-video" in result.output
        assert "archive" in result.output
        assert "gif" in result.output

    @patch("gishant_scripts.media.ffmpeg_convert.FFmpegConverter")
    def test_convert_command_success(self, mock_converter_class, tmp_path):
        """Test convert command success."""
        # Create test input file
        input_file = tmp_path / "input.mp4"
        input_file.touch()
        output_file = tmp_path / "output.mp4"

        # Mock converter
        mock_converter = Mock()
        mock_converter.convert_with_progress.return_value = output_file
        mock_converter_class.return_value = mock_converter

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["convert", str(input_file), "-p", "web-video", "-o", str(output_file)],
        )

        assert result.exit_code == 0
        assert "Conversion complete" in result.output
        mock_converter.convert_with_progress.assert_called_once()

    def test_convert_command_missing_preset(self, tmp_path):
        """Test convert command fails without preset."""
        input_file = tmp_path / "input.mp4"
        input_file.touch()

        runner = CliRunner()
        result = runner.invoke(cli, ["convert", str(input_file)])

        assert result.exit_code == 1
        assert "preset is required" in result.output

    def test_convert_command_file_not_found(self):
        """Test convert command with non-existent file."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["convert", "nonexistent.mp4", "-p", "web-video"],
        )

        assert result.exit_code == 2  # Click's file not found error

    @patch("gishant_scripts.media.ffmpeg_convert.FFmpegConverter")
    def test_info_command_success(self, mock_converter_class, tmp_path):
        """Test info command success."""
        input_file = tmp_path / "input.mp4"
        input_file.touch()

        mock_info = {
            "format": {"format_name": "mov,mp4", "duration": "120.5", "size": "10485760", "bit_rate": "696320"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080, "r_frame_rate": "30/1"}
            ],
        }

        mock_converter = Mock()
        mock_converter.get_info.return_value = mock_info
        mock_converter_class.return_value = mock_converter

        runner = CliRunner()
        result = runner.invoke(cli, ["info", str(input_file)])

        assert result.exit_code == 0
        assert "Format Information" in result.output
        assert "h264" in result.output

    @patch("gishant_scripts.media.ffmpeg_convert.FFmpegConverter")
    def test_info_command_json_output(self, mock_converter_class, tmp_path):
        """Test info command with JSON output."""
        input_file = tmp_path / "input.mp4"
        input_file.touch()

        mock_info = {"format": {"duration": "120.5"}}
        mock_converter = Mock()
        mock_converter.get_info.return_value = mock_info
        mock_converter_class.return_value = mock_converter

        runner = CliRunner()
        result = runner.invoke(cli, ["info", str(input_file), "--json"])

        assert result.exit_code == 0
        # Should contain JSON output
        assert "duration" in result.output

    @patch("gishant_scripts.media.ffmpeg_convert.FFmpegConverter")
    @patch("gishant_scripts.media.ffmpeg_convert.Prompt.ask")
    def test_interactive_command(self, mock_prompt, mock_converter_class, tmp_path):
        """Test interactive command."""
        input_file = tmp_path / "input.mp4"
        input_file.touch()
        output_file = tmp_path / "output.mp4"

        # Mock user selecting preset 1 (web-video)
        mock_prompt.return_value = "1"

        mock_converter = Mock()
        mock_converter.convert_with_progress.return_value = output_file
        mock_converter_class.return_value = mock_converter

        runner = CliRunner()
        result = runner.invoke(cli, ["interactive", str(input_file)])

        assert result.exit_code == 0
        assert "Conversion complete" in result.output
        mock_converter.convert_with_progress.assert_called_once()


class TestIntegration:
    """Integration tests (require ffmpeg installed)."""

    @pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="FFmpeg not installed")
    def test_real_conversion_dry_run(self, tmp_path):
        """Test with real ffmpeg (creates tiny test file)."""
        # Create a tiny test video using ffmpeg
        input_file = tmp_path / "test_input.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-f",
                "lavfi",
                "-i",
                "testsrc=duration=1:size=320x240:rate=1",
                "-pix_fmt",
                "yuv420p",
                str(input_file),
            ],
            capture_output=True,
            check=True,
        )

        # Test actual conversion
        converter = FFmpegConverter()
        output = converter.convert(
            input_file,
            preset="preview",
            overwrite=True,
        )

        assert output.exists()
        assert output.stat().st_size > 0
