"""Command-line interface for gishant-scripts."""

import sys
from pathlib import Path

import click
from rich.console import Console

from gishant_scripts.common.config import AppConfig
from gishant_scripts.common.errors import ConfigurationError
from gishant_scripts.common.logging import setup_logging


@click.group()
@click.option(
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to .env configuration file",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output (DEBUG level)")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    help="Directory for output files (default: current directory)",
)
@click.pass_context
def cli(ctx, config, verbose, output_dir):
    """
    Gishant Scripts - Pipeline automation utilities.

    This tool provides commands for fetching issues, pull requests,
    and generating management reports.

    Configuration:
        Set up your .env file with required credentials:
        - YOUTRACK_URL and YOUTRACK_API_TOKEN
        - GOOGLE_AI_API_KEY (for report generation)
        - GITHUB_TOKEN (optional, can use gh CLI)

    Examples:
        # Fetch YouTrack issues
        gishant fetch-youtrack

        # Generate management report
        gishant generate-report

        # Fetch GitHub PRs with custom output directory
        gishant fetch-github --output-dir ./reports

        # Run with verbose logging
        gishant -v fetch-youtrack
    """
    # Ensure ctx.obj exists
    ctx.ensure_object(dict)

    # Setup logging
    import logging

    log_level = logging.DEBUG if verbose else logging.INFO
    logger = setup_logging("gishant_scripts", level=log_level)
    ctx.obj["logger"] = logger

    # Store config file path
    if config:
        ctx.obj["config_file"] = config

    # Store output directory
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        ctx.obj["output_dir"] = output_dir
    else:
        ctx.obj["output_dir"] = Path.cwd()

    logger.debug(f"Output directory: {ctx.obj['output_dir']}")


@cli.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output JSON file path (default: my_youtrack_issues.json)",
)
@click.pass_context
def fetch_youtrack(ctx, output):
    """
    Fetch YouTrack issues where you are involved.

    Retrieves all issues where you are assigned, mentioned in comments,
    or have provided input. Saves results to JSON file.

    Requires:
        - YOUTRACK_URL in environment
        - YOUTRACK_API_TOKEN in environment
    """
    logger = ctx.obj["logger"]
    output_dir = ctx.obj["output_dir"]
    console = Console()

    logger.info("Fetching YouTrack issues...")

    try:
        # Load configuration
        config = AppConfig()
        config.require_valid("youtrack")

        # Import and run fetcher
        from gishant_scripts.youtrack.fetch_issues import IssuesFetcher

        # Determine output file
        if output:
            output_file = output
        else:
            output_file = output_dir / "my_youtrack_issues.json"

        # Create fetcher and fetch issues
        fetcher = IssuesFetcher(config.youtrack.url, config.youtrack.api_token)
        issues = fetcher.fetch_all_issues()

        # Save to file
        import json

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ Fetched {len(issues)} issues")
        logger.info(f"✓ Saved to: {output_file}")
        console.print(f"\n[bold green]✅ Success![/bold green] Saved {len(issues)} issues to {output_file}")

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Configuration Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("Error fetching YouTrack issues")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output JSON file path (default: my_github_prs.json)",
)
@click.option(
    "--days",
    "-d",
    type=int,
    default=90,
    help="Number of days to look back (default: 90)",
)
@click.pass_context
def fetch_github(ctx, output, days):
    """
    Fetch GitHub pull requests using gh CLI.

    Retrieves recent PRs from GitHub using the gh command-line tool.
    This command requires gh CLI to be installed and authenticated.

    Install gh CLI:
        https://cli.github.com/

    Authenticate:
        gh auth login
    """
    logger = ctx.obj["logger"]
    output_dir = ctx.obj["output_dir"]
    console = Console()

    logger.info("Fetching GitHub pull requests...")

    try:
        # Import and run fetcher
        from gishant_scripts.github.fetch_prs import fetch_prs

        # Determine output file
        if output:
            output_file = output
        else:
            output_file = output_dir / "my_github_prs.json"

        # Fetch PRs
        prs = fetch_prs(days=days)

        # Save to file
        import json

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(prs, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ Fetched {len(prs)} pull requests")
        logger.info(f"✓ Saved to: {output_file}")
        console.print(f"\n[bold green]✅ Success![/bold green] Saved {len(prs)} PRs to {output_file}")

    except Exception as e:
        logger.exception("Error fetching GitHub PRs")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--issues-file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to YouTrack issues JSON file (default: my_youtrack_issues.json)",
)
@click.option(
    "--prs-file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to GitHub PRs JSON file (default: my_github_prs.json)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file path (default: management_report_<date>.txt)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["email", "bullet"], case_sensitive=False),
    help="Output format (email or bullet points)",
)
@click.option(
    "--model",
    type=click.Choice(
        ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"],
        case_sensitive=False,
    ),
    help="Gemini model to use",
)
@click.option(
    "--non-interactive",
    is_flag=True,
    help="Run without interactive prompts (requires --format and --model)",
)
@click.pass_context
def generate_report(ctx, issues_file, prs_file, output, output_format, model, non_interactive):
    """
    Generate professional management report using Google AI.

    Creates a formatted report from YouTrack issues and GitHub PRs
    using Google Gemini AI.

    Requires:
        - GOOGLE_AI_API_KEY in environment
        - my_youtrack_issues.json (run fetch-youtrack first)
        - my_github_prs.json (optional, run fetch-github)

    Examples:
        # Interactive mode (prompts for format and model)
        gishant generate-report

        # Non-interactive mode
        gishant generate-report --format email --model gemini-2.0-flash-exp --non-interactive

        # Custom input files
        gishant generate-report --issues-file ./data/issues.json --prs-file ./data/prs.json
    """
    logger = ctx.obj["logger"]
    output_dir = ctx.obj["output_dir"]
    console = Console()

    logger.info("Generating management report...")

    try:
        # Check for required configuration
        config = AppConfig()
        config.require_valid("google_ai")

        # Import report generator
        from gishant_scripts.utils.generate_report import (
            generate_email_with_gemini,
            prepare_summary_data,
            save_email_draft,
            select_model,
            select_output_format,
        )

        # Determine input files
        if not issues_file:
            issues_file = output_dir / "my_youtrack_issues.json"

        if not issues_file.exists():
            logger.error(f"Issues file not found: {issues_file}")
            console = Console(stderr=True)
            console.print(
                f"\n[bold red]❌ Error:[/bold red] {issues_file} not found!\nPlease run 'gishant fetch-youtrack' first."
            )
            sys.exit(1)

        # Load data
        import json

        console.print(f"\n[cyan]📂 Reading YouTrack issues from {issues_file.name}...[/cyan]")
        with open(issues_file, encoding="utf-8") as f:
            issues = json.load(f)

        logger.info(f"✓ Loaded {len(issues)} YouTrack issues")

        # Load GitHub PRs if file exists
        prs = []
        if prs_file:
            pr_path = prs_file
        else:
            pr_path = output_dir / "my_github_prs.json"

        if pr_path.exists():
            console.print(f"[cyan]📂 Reading GitHub PRs from {pr_path.name}...[/cyan]")
            with open(pr_path, encoding="utf-8") as f:
                prs = json.load(f)
            logger.info(f"✓ Loaded {len(prs)} GitHub pull requests")

        # Prepare summary data
        summary_data = prepare_summary_data(issues, prs)

        # Select format and model
        if non_interactive:
            if not output_format or not model:
                console = Console(stderr=True)
                console.print("\n[bold red]❌ Error:[/bold red] --non-interactive requires both --format and --model")
                sys.exit(1)
            selected_format = output_format
            selected_model = model
        else:
            # Interactive mode
            if not output_format:
                selected_format = select_output_format()
            else:
                selected_format = output_format

            if not model:
                selected_model = select_model()
            else:
                selected_model = model

        # Generate report
        logger.info(f"Generating {selected_format} report using {selected_model}...")

        # Type guard: api_key should never be None here due to config.require_valid("google_ai")
        if not config.google_ai.api_key:
            raise ConfigurationError("Google AI API key is not configured")

        email_content = generate_email_with_gemini(
            summary_data, config.google_ai.api_key, selected_model, selected_format
        )

        # Save report
        if output:
            output_file = output
        else:
            output_file = save_email_draft(email_content)

        logger.info(f"✓ Saved report to: {output_file}")
        console.print(f"\n[bold green]✅ Success![/bold green] Report saved to {output_file}")
        console.print(f"[dim]📊 Based on {len(issues)} YouTrack issues[/dim]")
        if prs:
            console.print(f"[dim]📊 Based on {len(prs)} GitHub pull requests[/dim]")

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Configuration Error:[/bold red] {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("Error generating report")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.option(
    "--issues-file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to YouTrack issues JSON file (default: my_youtrack_issues.json)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file path (default: work_summary_<date>.txt)",
)
@click.pass_context
def generate_summary(ctx, issues_file, output):
    """
    Generate work summary from YouTrack issues.

    Creates a categorized summary of work contributions without using AI.
    This is a simpler alternative to generate-report.

    Requires:
        - my_youtrack_issues.json (run fetch-youtrack first)
    """
    logger = ctx.obj["logger"]
    output_dir = ctx.obj["output_dir"]
    console = Console()

    logger.info("Generating work summary...")

    try:
        # Import summary generator
        from gishant_scripts.utils.generate_work_summary import (
            WorkSummaryEmailGenerator,
        )

        # Determine input file
        if not issues_file:
            issues_file = output_dir / "my_youtrack_issues.json"

        if not issues_file.exists():
            logger.error(f"Issues file not found: {issues_file}")
            console = Console(stderr=True)
            console.print(
                f"\n[bold red]❌ Error:[/bold red] {issues_file} not found!\nPlease run 'gishant fetch-youtrack' first."
            )
            sys.exit(1)

        console.print(f"\n[cyan]📂 Reading data from {issues_file.name}...[/cyan]")

        # Generate summary
        generator = WorkSummaryEmailGenerator(str(issues_file))
        summary = generator.generate_email()

        # Determine output file
        if output:
            output_file = output
        else:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = output_dir / f"work_summary_{timestamp}.txt"

        # Save summary
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(summary)

        logger.info(f"✓ Saved summary to: {output_file}")
        console.print(f"\n[bold green]✅ Success![/bold green] Summary saved to {output_file}")

    except Exception as e:
        logger.exception("Error generating summary")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


# ============================================================================
# FFmpeg Media Conversion Commands
# ============================================================================


@cli.command(name="ffmpeg-video")
@click.argument("input-file", type=click.Path(exists=True, path_type=Path))
@click.argument("output-file", type=click.Path(path_type=Path), required=False)
@click.option(
    "--preset",
    "-p",
    type=click.Choice(
        [
            "web-video",
            "web-video-hq",
            "archive",
            "mobile",
            "mobile-vertical",
            "gif",
            "preview",
        ],
        case_sensitive=False,
    ),
    default="web-video",
    help="Conversion preset to use (default: web-video)",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite output file if it exists",
)
@click.pass_context
def ffmpeg_video(ctx, input_file, output_file, preset, overwrite):
    """
    Convert video files using FFmpeg presets.

    Convert video files to various formats optimized for different use cases.
    Output file is auto-generated if not specified (adds preset suffix).

    Presets:
        web-video       - H.264 optimized for web (balanced quality/size)
        web-video-hq    - High quality H.264 for web
        archive         - H.265/HEVC for archival (space-efficient)
        mobile          - 720p optimized for mobile devices
        mobile-vertical - 720x1280 (9:16) for social media
        gif             - Animated GIF with optimized palette
        preview         - Low quality quick preview (360p)

    Examples:
        # Convert to web-optimized video
        gishant ffmpeg-video video.mov

        # High quality archival conversion
        gishant ffmpeg-video video.mov --preset archive

        # Mobile-optimized with custom output
        gishant ffmpeg-video video.mp4 mobile_version.mp4 --preset mobile

        # Create animated GIF
        gishant ffmpeg-video clip.mp4 --preset gif

    Requires:
        FFmpeg must be installed and available in PATH
    """
    logger = ctx.obj["logger"]

    try:
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn

        from gishant_scripts.media import FFmpegConverter

        console = Console()
        converter = FFmpegConverter()

        # Show conversion info
        console.print("\n[bold cyan]Converting video file[/bold cyan]")
        console.print(f"Input:  [green]{input_file}[/green]")
        console.print(f"Preset: [yellow]{preset}[/yellow]")

        # Perform conversion with progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Converting...", total=None)

            try:
                output_path = converter.convert(
                    input_path=input_file,
                    output_path=output_file,
                    preset=preset,
                    overwrite=overwrite,
                )
                progress.update(task, description="✓ Conversion complete")
            except FileExistsError:
                console = Console(stderr=True)
                console.print("\n[red]❌ Error: Output file already exists![/red]")
                console.print("Use [yellow]--overwrite[/yellow] flag to replace it.")
                sys.exit(1)
            except RuntimeError as e:
                console = Console(stderr=True)
                console.print(f"\n[red]❌ Error: {e}[/red]")
                sys.exit(1)

        console.print(f"Output: [green]{output_path}[/green]")
        console.print("\n[bold green]✅ Success![/bold green]")

        logger.info(f"Converted {input_file} -> {output_path} (preset: {preset})")

    except Exception as e:
        logger.exception("Error converting video")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


@cli.command(name="ffmpeg-audio")
@click.argument("input-file", type=click.Path(exists=True, path_type=Path))
@click.argument("output-file", type=click.Path(path_type=Path), required=False)
@click.option(
    "--preset",
    "-p",
    type=click.Choice(["audio-reduce", "audio-podcast"], case_sensitive=False),
    default="audio-reduce",
    help="Audio conversion preset (default: audio-reduce)",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite output file if it exists",
)
@click.pass_context
def ffmpeg_audio(ctx, input_file, output_file, preset, overwrite):
    """
    Convert or compress audio files using FFmpeg presets.

    Extract and convert audio from video files or compress audio files.
    Output file is auto-generated if not specified (adds preset suffix).

    Presets:
        audio-reduce   - Reduce audio file size (128k MP3)
        audio-podcast  - Podcast-optimized (mono, 64k MP3)

    Examples:
        # Reduce audio file size
        gishant ffmpeg-audio audio.wav

        # Extract and compress audio from video
        gishant ffmpeg-audio video.mp4 audio.mp3 --preset audio-reduce

        # Create podcast-optimized audio
        gishant ffmpeg-audio recording.wav --preset audio-podcast

    Requires:
        FFmpeg must be installed and available in PATH
    """
    logger = ctx.obj["logger"]

    try:
        from rich.console import Console
        from rich.progress import Progress, SpinnerColumn, TextColumn

        from gishant_scripts.media import FFmpegConverter

        console = Console()
        converter = FFmpegConverter()

        # Show conversion info
        console.print("\n[bold cyan]Converting audio file[/bold cyan]")
        console.print(f"Input:  [green]{input_file}[/green]")
        console.print(f"Preset: [yellow]{preset}[/yellow]")

        # Perform conversion with progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Converting...", total=None)

            try:
                output_path = converter.convert(
                    input_path=input_file,
                    output_path=output_file,
                    preset=preset,
                    overwrite=overwrite,
                )
                progress.update(task, description="✓ Conversion complete")
            except FileExistsError:
                console.print("\n[red]❌ Error: Output file already exists![/red]")
                console.print("Use [yellow]--overwrite[/yellow] flag to replace it.")
                sys.exit(1)
            except RuntimeError as e:
                console.print(f"\n[red]❌ Error: {e}[/red]")
                sys.exit(1)

        console.print(f"Output: [green]{output_path}[/green]")
        console.print("\n[bold green]✅ Success![/bold green]")

        logger.info(f"Converted {input_file} -> {output_path} (preset: {preset})")

    except Exception as e:
        logger.exception("Error converting audio")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


@cli.command(name="list-ffmpeg-presets")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "json", "simple"], case_sensitive=False),
    default="table",
    help="Output format (default: table)",
)
@click.pass_context
def list_ffmpeg_presets(ctx, format):
    """
    List all available FFmpeg conversion presets.

    Display information about all available conversion presets including
    their descriptions, codecs, and quality settings.

    Examples:
        # Show presets in table format
        gishant list-ffmpeg-presets

        # Show presets as JSON
        gishant list-ffmpeg-presets --format json

        # Show simple list
        gishant list-ffmpeg-presets --format simple
    """
    logger = ctx.obj["logger"]

    try:
        from gishant_scripts.media import get_all_presets

        presets = get_all_presets()

        if format == "json":
            import json

            # Convert presets to JSON-serializable format
            presets_data = {
                name: {
                    "name": preset.name,
                    "description": preset.description,
                    "extension": preset.extension,
                    "video_codec": preset.video_codec,
                    "audio_codec": preset.audio_codec,
                    "video_bitrate": preset.video_bitrate,
                    "audio_bitrate": preset.audio_bitrate,
                    "resolution": preset.resolution,
                    "framerate": preset.framerate,
                    "crf": preset.crf,
                }
                for name, preset in presets.items()
            }
            click.echo(json.dumps(presets_data, indent=2))

        elif format == "simple":
            from rich.console import Console

            console = Console()
            console.print("\n[bold cyan]Available Presets:[/bold cyan]\n")
            for name, preset in presets.items():
                console.print(f"  [yellow]{name:20}[/yellow] - {preset.description}")
            console.print()

        else:  # table format
            from rich.console import Console
            from rich.table import Table

            console = Console()
            table = Table(title="FFmpeg Conversion Presets", show_header=True, header_style="bold cyan")
            table.add_column("Preset", style="yellow", no_wrap=True)
            table.add_column("Description", style="white")
            table.add_column("Format", style="green")
            table.add_column("Video Codec", style="blue")
            table.add_column("Audio Codec", style="magenta")

            for name, preset in presets.items():
                table.add_row(
                    name,
                    preset.description,
                    preset.extension,
                    preset.video_codec or "-",
                    preset.audio_codec or "-",
                )

            console.print()
            console.print(table)
            console.print()
            console.print("[dim]Use 'gishant ffmpeg-video --preset <name>' to convert files[/dim]")
            console.print()

        logger.debug(f"Listed {len(presets)} presets in {format} format")

    except Exception as e:
        logger.exception("Error listing presets")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


def main():
    """Entry point for CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
