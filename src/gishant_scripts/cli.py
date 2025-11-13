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


@cli.command(name="youtrack-summary")
@click.option(
    "--weeks",
    type=int,
    required=True,
    help="Number of weeks to look back for issues",
)
@click.option(
    "--model",
    type=click.Choice(
        ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash-exp"],
        case_sensitive=False,
    ),
    default="gemini-2.5-flash",
    help="Gemini model to use for generation",
)
@click.option(
    "--save-to-file",
    type=click.Path(path_type=Path),
    help="Save output to specified file",
)
@click.option(
    "--max-issues",
    type=int,
    default=100,
    help="Maximum number of issues to fetch",
)
@click.pass_context
def youtrack_summary(ctx, weeks, model, save_to_file, max_issues):
    """
    Generate work summary from YouTrack issues using Gemini AI.

    Fetches issues where you are involved (assigned or commented) from the last N weeks
    and generates a structured summary with Done/Current Work/Pending/Blockers sections.

    Requires:
        - YOUTRACK_URL in environment
        - YOUTRACK_API_TOKEN in environment
        - GOOGLE_AI_API_KEY in environment

    Examples:

        # Generate summary for last 4 weeks
        gishant youtrack-summary --weeks 4

        # Use a different model
        gishant youtrack-summary --weeks 2 --model gemini-2.5-pro

        # Save to file
        gishant youtrack-summary --weeks 4 --save-to-file my_summary.txt
    """
    logger = ctx.obj["logger"]
    output_dir = ctx.obj["output_dir"]
    console = Console()

    logger.info(f"Generating YouTrack work summary for last {weeks} weeks...")

    try:
        from rich.panel import Panel

        from gishant_scripts.youtrack.fetch_issues import YouTrackIssuesFetcher
        from gishant_scripts.youtrack.generate_work_summary import (
            filter_issues_by_time,
            generate_work_summary_with_gemini,
            prepare_issues_for_summary,
        )

        console.print(
            Panel.fit(
                f"[bold cyan]YouTrack Work Summary Generator[/bold cyan]\n"
                f"Time period: Last {weeks} weeks\n"
                f"Model: {model}",
                border_style="cyan",
            )
        )

        # Load configuration
        config_file = ctx.obj.get("config_file")
        config = AppConfig(env_file=config_file) if config_file else AppConfig()
        config.require_valid("youtrack", "google_ai")

        # Initialize YouTrack fetcher
        console.print("\n[cyan]Step 1: Connecting to YouTrack...[/cyan]")
        fetcher = YouTrackIssuesFetcher(
            base_url=config.youtrack.url,
            token=config.youtrack.api_token,
        )

        # Fetch issues
        console.print(f"[cyan]Step 2: Fetching issues (max {max_issues})...[/cyan]")
        issues = fetcher.fetch_issues_with_details(max_results=max_issues)

        if not issues:
            console.print("[yellow]No issues found where you are involved.[/yellow]")
            return

        console.print(f"[green]✓ Found {len(issues)} total issues[/green]")

        # Filter by time
        console.print(f"\n[cyan]Step 3: Filtering issues from last {weeks} weeks...[/cyan]")
        filtered_issues = filter_issues_by_time(issues, weeks)

        if not filtered_issues:
            console.print(f"[yellow]No issues updated in the last {weeks} weeks.[/yellow]")
            return

        # Prepare data for Gemini
        console.print("[cyan]Step 4: Preparing data for Gemini...[/cyan]")
        prepared_data = prepare_issues_for_summary(filtered_issues, weeks)

        if prepared_data["total_issues"] == 0:
            console.print(f"[yellow]No issues with activity in the last {weeks} weeks.[/yellow]")
            return

        # Generate summary with Gemini
        console.print("\n[cyan]Step 5: Generating work summary with Gemini...[/cyan]")
        summary = generate_work_summary_with_gemini(
            data=prepared_data,
            api_key=config.google_ai.api_key,
            model=model,
        )

        # Display results
        console.print("\n" + "=" * 80)
        console.print(Panel.fit("[bold green]WORK SUMMARY GENERATED[/bold green]", border_style="green"))
        console.print("=" * 80 + "\n")
        console.print(summary)
        console.print("\n" + "=" * 80)

        # Save to file if requested
        if save_to_file:
            if not save_to_file.is_absolute():
                save_to_file = output_dir / save_to_file

            with open(save_to_file, "w", encoding="utf-8") as f:
                f.write(summary)
            console.print(f"\n[green]✓ Saved to: {save_to_file}[/green]")

        # Summary stats
        console.print(f"\n[dim]Generated from {prepared_data['total_issues']} issues over {weeks} weeks[/dim]")
        console.print(f"[dim]Model: {model}[/dim]")

        logger.info("✓ Work summary generated successfully")

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Configuration Error:[/bold red] {e}")
        console.print("\n[yellow]Please ensure the following are set in your .env file:[/yellow]")
        console.print("  - YOUTRACK_URL")
        console.print("  - YOUTRACK_API_TOKEN")
        console.print("  - GOOGLE_AI_API_KEY")
        sys.exit(1)

    except Exception as e:
        logger.exception("Error generating YouTrack work summary")
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


# ============================================================================
# AYON Bundle Comparison Commands
# ============================================================================


@cli.command(name="analyze-bundles")
@click.argument("bundle1", required=False)
@click.argument("bundle2", required=False)
@click.option(
    "--only-diff",
    is_flag=True,
    help="Show only differences (exclude unchanged settings)",
)
@click.option(
    "--max-depth",
    type=int,
    default=None,
    help="Maximum depth for nested settings comparison (default: unlimited)",
)
@click.option(
    "--view",
    type=click.Choice(["table", "tree", "both"], case_sensitive=False),
    default="both",
    help="Display view mode (default: both)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Export comparison to file (JSON or Markdown based on extension)",
)
@click.option(
    "--project",
    "-p",
    type=str,
    default=None,
    help="Project name for project-specific comparison (interactive if not specified)",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive mode: select bundles and project from list",
)
@click.pass_context
def analyze_bundles_cli(ctx, bundle1, bundle2, only_diff, max_depth, view, output, project, interactive):
    """
    Compare settings between two AYON bundles.

    Fetches and compares all settings including addon versions, configurations,
    dependency packages, and metadata between two AYON bundles.

    Arguments:
        BUNDLE1: Name of the first bundle (optional in interactive mode)
        BUNDLE2: Name of the second bundle (optional in interactive mode)

    Examples:

        # Interactive mode - select bundles from list
        gishant analyze-bundles --interactive

        # Compare two specific bundles
        gishant analyze-bundles production_v1 staging_v2

        # Show only differences in table view
        gishant analyze-bundles prod staging --only-diff --view table

        # Export comparison to JSON
        gishant analyze-bundles prod staging --output comparison.json

        # Export to Markdown with tree view
        gishant analyze-bundles prod staging --view tree --output report.md

        # Limit comparison depth to 3 levels
        gishant analyze-bundles prod staging --max-depth 3

    Requires:
        - AYON server running and accessible
        - AYON_SERVER_URL and AYON_API_KEY in .env file
        - Or rdo-ayon-utils available with configured connection
    """
    logger = ctx.obj["logger"]

    try:
        # Import the standalone function and pass through arguments
        # We need to invoke it directly since it's already a Click command
        from click.testing import CliRunner

        from gishant_scripts.ayon.analyze_bundles import analyze_bundles_cli

        runner = CliRunner()

        # Build arguments list
        args = []
        if bundle1:
            args.append(bundle1)
        if bundle2:
            args.append(bundle2)
        if only_diff:
            args.append("--only-diff")
        if max_depth:
            args.extend(["--max-depth", str(max_depth)])
        if view != "both":
            args.extend(["--view", view])
        if output:
            args.extend(["--output", str(output)])
        if project:
            args.extend(["--project", project])
        if interactive:
            args.append("--interactive")

        # Run the command
        result = runner.invoke(analyze_bundles_cli, args, catch_exceptions=False)
        sys.exit(result.exit_code)

    except ImportError as e:
        logger.error(f"Import error: {e}")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Import Error:[/bold red] {e}")
        console.print("\n[yellow]Please ensure ayon-python-api is installed:[/yellow]")
        console.print("  uv pip install ayon-python-api")
        sys.exit(1)

    except Exception as e:
        logger.exception("Error running analyze-bundles command")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


@cli.command(name="sync-bundles")
@click.argument("source", required=False)
@click.argument("target", required=False)
@click.option(
    "--operation",
    "-op",
    type=click.Choice(["bundle", "project-bundle", "project"], case_sensitive=False),
    default="bundle",
    help="Sync operation type (default: bundle)",
)
@click.option(
    "--project",
    "-p",
    type=str,
    help="Project name (required for project operations)",
)
@click.option(
    "--bundle",
    "-b",
    type=str,
    help="Bundle context (for project operations)",
)
@click.option(
    "--sync-mode",
    type=click.Choice(["diff-only", "all"], case_sensitive=False),
    default="diff-only",
    help="Sync only differences or all settings (default: diff-only)",
)
@click.option(
    "--addon",
    "-a",
    type=str,
    help="Sync only specific addon settings",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview changes without applying them",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompts",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive mode: guided sync setup",
)
@click.pass_context
def sync_bundles_cli(ctx, source, target, operation, project, bundle, sync_mode, addon, dry_run, force, interactive):
    """
    Sync AYON bundle and project settings.

    Synchronize settings between bundles, projects, or specific addons with
    safety features including dry-run preview, automatic backups, and rollback.

    Arguments:
        SOURCE: Source bundle or project name (optional in interactive mode)
        TARGET: Target bundle or project name (optional in interactive mode)

    OPERATIONS:
        bundle          Sync from source bundle to target bundle
        project-bundle  Sync project settings to bundle studio settings
        project         Sync settings between two projects

    Examples:

        # Sync bundles (diff only)
        gishant sync-bundles production staging

        # Sync specific addon only
        gishant sync-bundles production staging --addon maya

        # Sync all settings (not just differences)
        gishant sync-bundles production staging --sync-mode all

        # Dry run preview
        gishant sync-bundles production staging --dry-run

        # Sync project to bundle
        gishant sync-bundles --operation project-bundle --project myproject \\
                             --bundle source_bundle target_bundle

        # Sync projects
        gishant sync-bundles --operation project project1 project2 --bundle production

        # Interactive mode
        gishant sync-bundles --interactive

        # Force without confirmation
        gishant sync-bundles production staging --force

    Safety Features:
        - Automatic backups before sync (stored in ~/.ayon/sync_backups/)
        - Dry-run mode to preview changes
        - Interactive confirmation prompts
        - Rollback capability from backups

    Requires:
        - AYON server running and accessible
        - AYON_SERVER_URL and AYON_API_KEY in .env file
        - Or rdo-ayon-utils available with configured connection
    """
    logger = ctx.obj["logger"]

    try:
        # Import the standalone function and pass through arguments
        from click.testing import CliRunner

        from gishant_scripts.ayon.sync_bundles import main as sync_main

        runner = CliRunner()

        # Build arguments list
        args = []
        if source:
            args.append(source)
        if target:
            args.append(target)
        if operation:
            args.extend(["--operation", operation])
        if project:
            args.extend(["--project", project])
        if bundle:
            args.extend(["--bundle", bundle])
        if sync_mode:
            args.extend(["--sync-mode", sync_mode])
        if addon:
            args.extend(["--addon", addon])
        if dry_run:
            args.append("--dry-run")
        if force:
            args.append("--force")
        if interactive:
            args.append("--interactive")

        # Run the command
        result = runner.invoke(sync_main, args, catch_exceptions=False)
        sys.exit(result.exit_code)

    except ImportError as e:
        logger.error(f"Import error: {e}")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Import Error:[/bold red] {e}")
        console.print("\n[yellow]Please ensure ayon-python-api is installed:[/yellow]")
        console.print("  uv pip install ayon-python-api")
        sys.exit(1)

    except Exception as e:
        logger.exception("Error running sync-bundles command")
        console = Console(stderr=True)
        console.print(f"\n[bold red]❌ Error:[/bold red] {e}")
        sys.exit(1)


def main():
    """Entry point for CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
