"""Core database restore functionality."""

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

from gishant_scripts.common.docker_utils import (
    copy_to_container,
    detect_backup_format,
    docker_compose_cmd,
    ensure_service_running,
    exec_in_service,
    start_services,
    stop_services,
)

console = Console()


class RestoreError(Exception):
    """Exception raised during database restore operations."""

    pass


# Tables to skip when filtering thumbnails (common patterns)
THUMBNAIL_TABLES = {
    "thumbnails",
    "thumbnail",
    "project_thumbnails",
    "public.thumbnails",
    "public.thumbnail",
}


@dataclass
class RestoreConfig:
    """Configuration for database restore operation.

    Attributes:
        compose_file: Path to docker-compose.yml file
        backup_file: Path to backup file to restore
        db_service: Name of database service in compose
        app_services: List of application service names
        db_user: Database user name
        db_name: Database name
        run_schema_upgrade: Whether to run schema upgrade after restore
        schema_upgrade_service: Service to run schema upgrade in (if applicable)
        skip_thumbnails: Whether to skip thumbnail data during restore
    """

    compose_file: Path
    backup_file: Path
    db_service: str
    app_services: list[str]
    db_user: str
    db_name: str
    run_schema_upgrade: bool = False
    schema_upgrade_service: str | None = None
    skip_thumbnails: bool = False


def terminate_db_connections(config: RestoreConfig) -> None:
    """Terminate all active connections to the database.

    Args:
        config: Restore configuration

    Raises:
        RestoreError: If connection termination fails
    """
    sql = (
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{config.db_name}' AND pid <> pg_backend_pid();"
    )

    try:
        exec_in_service(
            config.compose_file,
            config.db_service,
            ["psql", "-U", config.db_user, "-d", "postgres", "-c", sql],
            check=False,  # Don't fail if no connections to terminate
        )
    except Exception as err:
        # Log warning but don't fail - there might be no connections
        console.print(f"[dim]Note: {err}[/dim]")


def drop_and_recreate_db(config: RestoreConfig) -> None:
    """Drop and recreate the database.

    Args:
        config: Restore configuration

    Raises:
        RestoreError: If database operations fail
    """
    try:
        # Drop database
        exec_in_service(
            config.compose_file,
            config.db_service,
            [
                "psql",
                "-U",
                config.db_user,
                "-d",
                "postgres",
                "-c",
                f"DROP DATABASE IF EXISTS {config.db_name};",
            ],
        )

        # Create database
        exec_in_service(
            config.compose_file,
            config.db_service,
            [
                "psql",
                "-U",
                config.db_user,
                "-d",
                "postgres",
                "-c",
                f"CREATE DATABASE {config.db_name};",
            ],
        )
    except Exception as err:
        raise RestoreError(f"Failed to recreate database: {err}") from err


def restore_custom_format(
    config: RestoreConfig,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    """Restore database from custom format (.dump/.backup) using pg_restore.

    Args:
        config: Restore configuration
        progress_callback: Optional callback(current, total, message) for progress updates

    Raises:
        RestoreError: If restore fails
    """
    container_path = "/tmp/restore.dump"

    try:
        # Step 1: Copy backup file to container (this is the slow part)
        if progress_callback:
            progress_callback(0, 100, "Copying backup to container...")

        copy_to_container(
            config.compose_file,
            config.db_service,
            config.backup_file,
            container_path,
        )

        if progress_callback:
            progress_callback(30, 100, "Running pg_restore...")

        # Step 2: Run pg_restore with streaming output to track progress
        cmd = [
            "docker",
            "compose",
            "-f",
            str(config.compose_file),
            "exec",
            "-T",
            config.db_service,
            "pg_restore",
            "-U",
            config.db_user,
            "-d",
            config.db_name,
            "-v",
            "--no-owner",
            "--no-acl",
            container_path,
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=config.compose_file.parent,
        )

        # Track progress by counting pg_restore output lines
        table_count = 0
        stderr = process.stderr
        assert stderr is not None  # for type checker
        while True:
            line = stderr.readline()
            if not line and process.poll() is not None:
                break
            if line:
                # pg_restore outputs progress to stderr
                if "processing data" in line.lower():
                    table_count += 1
                    if progress_callback:
                        # Estimate progress between 30-90%
                        estimated = min(30 + table_count, 90)
                        progress_callback(estimated, 100, f"Restoring tables ({table_count})...")

        process.wait()

        if progress_callback:
            progress_callback(95, 100, "Cleaning up...")

        # Cleanup
        exec_in_service(
            config.compose_file,
            config.db_service,
            ["rm", container_path],
            check=False,
        )

        if progress_callback:
            progress_callback(100, 100, "Complete")

    except Exception as err:
        raise RestoreError(f"Failed to restore from custom format: {err}") from err


def _is_thumbnail_line(line: str) -> bool:
    """Check if a SQL line is a COPY or INSERT for a thumbnail table.

    Args:
        line: SQL line to check

    Returns:
        True if this line starts a thumbnail data section
    """
    line_lower = line.lower().strip()

    # Check for COPY statements (PostgreSQL dump format)
    if line_lower.startswith("copy "):
        for table in THUMBNAIL_TABLES:
            if f"copy {table} " in line_lower or f"copy {table}(" in line_lower:
                return True

    # Check for INSERT statements
    if line_lower.startswith("insert into "):
        for table in THUMBNAIL_TABLES:
            if f"insert into {table} " in line_lower or f"insert into {table}(" in line_lower:
                return True

    return False


def _filter_thumbnails_from_gzip(
    input_file: Path,
    output_file: Path,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> int:
    """Filter thumbnail data from a gzipped SQL file and write to a new gzipped file.

    Args:
        input_file: Path to input gzipped SQL file
        output_file: Path to output gzipped SQL file (will be created)
        progress_callback: Optional callback(current, total, message) for progress updates

    Returns:
        Number of thumbnail rows skipped

    Raises:
        RestoreError: If filtering fails
    """
    import gzip

    file_size = input_file.stat().st_size
    skipped_rows = 0
    in_copy_block = False
    bytes_read = 0

    try:
        if progress_callback:
            progress_callback(0, 100, "Filtering thumbnails from backup...")

        with gzip.open(input_file, "rt", encoding="utf-8", errors="replace") as gz_input:
            with gzip.open(output_file, "wt", encoding="utf-8") as gz_output:
                for line in gz_input:
                    bytes_read += len(line.encode("utf-8"))

                    # Check if we're exiting a COPY block
                    if in_copy_block:
                        if line.strip() == "\\.":
                            # End of COPY block - skip the terminator too
                            in_copy_block = False
                            skipped_rows += 1
                            continue
                        # Skip data rows in thumbnail COPY block
                        skipped_rows += 1
                        continue

                    # Check if this line starts a thumbnail COPY/INSERT
                    if _is_thumbnail_line(line):
                        if line.lower().strip().startswith("copy "):
                            # COPY block - skip until \.
                            in_copy_block = True
                        skipped_rows += 1
                        continue

                    # Write non-thumbnail lines
                    gz_output.write(line)

                    # Update progress periodically
                    if progress_callback and bytes_read % (10 * 1024 * 1024) == 0:  # Every ~10MB
                        if file_size > 0:
                            pct = min(int((bytes_read / (file_size * 5)) * 100), 90)  # Estimate
                            mb_read = bytes_read // (1024 * 1024)
                            skip_info = f", skipped {skipped_rows} rows" if skipped_rows else ""
                            progress_callback(pct, 100, f"Filtering ({mb_read} MB{skip_info})...")

        if progress_callback:
            progress_callback(100, 100, f"Filtered {skipped_rows:,} thumbnail rows")

        return skipped_rows

    except Exception as err:
        raise RestoreError(f"Failed to filter thumbnails: {err}") from err


def restore_gzip_format(
    config: RestoreConfig,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    """Restore database from gzip format (.gz, .sql.gz) using zcat/gunzip + psql.

    Args:
        config: Restore configuration
        progress_callback: Optional callback(current, total, message) for progress updates

    Raises:
        RestoreError: If restore fails
    """
    import shutil
    import tempfile

    file_size = config.backup_file.stat().st_size

    if progress_callback:
        msg = "Starting restore (skipping thumbnails)..." if config.skip_thumbnails else "Starting restore..."
        progress_callback(0, 100, msg)

    # If thumbnails need to be filtered, create a cleaned temporary file first
    restore_file = config.backup_file
    temp_file = None
    skipped_rows = 0

    if config.skip_thumbnails:
        # Create temporary file for filtered SQL
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sql.gz",
            delete=False,
            dir=config.backup_file.parent,
        )
        temp_file.close()
        temp_path = Path(temp_file.name)

        try:
            # Filter thumbnails into temporary file
            def filter_progress(current: int, total: int, message: str) -> None:
                """Update progress for filtering step (0-50% of total)."""
                if progress_callback:
                    progress_callback(current // 2, 100, message)

            skipped_rows = _filter_thumbnails_from_gzip(
                config.backup_file,
                temp_path,
                progress_callback=filter_progress,
            )

            restore_file = temp_path
            if progress_callback:
                console.print(f"[dim]Skipped {skipped_rows:,} thumbnail rows[/dim]")
                progress_callback(50, 100, "Starting restore from filtered backup...")

        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            raise

    # Use subprocess pipeline approach (like the shell script) for restore
    # Check if zcat is available (preferred), otherwise use gunzip -c
    zcat_cmd = shutil.which("zcat") or shutil.which("gunzip")
    if zcat_cmd:
        # Use the found command with appropriate flags
        if zcat_cmd.endswith("gunzip"):
            decompress_cmd = [zcat_cmd, "-c", str(restore_file)]
        else:
            decompress_cmd = [zcat_cmd, str(restore_file)]
    else:
        # Fallback: use Python gzip as subprocess
        import sys
        decompress_cmd = [
            sys.executable,
            "-c",
            "import gzip, sys; sys.stdout.buffer.write(gzip.open(sys.argv[1], 'rb').read())",
            str(restore_file),
        ]

    psql_cmd = [
        "docker",
        "compose",
        "-f",
        str(config.compose_file),
        "exec",
        "-T",
        config.db_service,
        "psql",
        "-U",
        config.db_user,
        "-d",
        config.db_name,
    ]

    try:
        if progress_callback and not config.skip_thumbnails:
            progress_callback(20, 100, "Decompressing and restoring...")
        elif progress_callback:
            progress_callback(60, 100, "Decompressing and restoring...")

        # Create pipeline: decompress | psql
        decompress_proc = subprocess.Popen(
            decompress_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        psql_proc = subprocess.Popen(
            psql_cmd,
            stdin=decompress_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=config.compose_file.parent,
        )

        # Close decompress stdout in psql process to allow decompress to receive SIGPIPE
        decompress_proc.stdout.close()

        # Wait for both processes
        if progress_callback:
            progress_callback(70, 100, "Restoring...")

        stdout, stderr = psql_proc.communicate()
        decompress_stderr = decompress_proc.communicate()[1]

        # Check decompress process (ignore errors if psql closed pipe early)
        if decompress_proc.returncode not in (0, None, -15):  # 0=success, None=running, -15=SIGTERM
            decompress_err = decompress_stderr.decode("utf-8", errors="replace") if decompress_stderr else ""
            if decompress_err and "broken pipe" not in decompress_err.lower():
                console.print(f"[dim]Decompress warning: {decompress_err}[/dim]")

        if psql_proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
            if stderr_text:
                console.print(f"[dim]{stderr_text}[/dim]")
            raise RestoreError(f"psql failed with return code {psql_proc.returncode}")

        if progress_callback:
            progress_callback(100, 100, "Complete")

    except Exception as err:
        raise RestoreError(f"Failed to restore from gzip format: {err}") from err
    finally:
        # Clean up temporary file if it was created
        if temp_file and Path(temp_file.name).exists():
            try:
                Path(temp_file.name).unlink()
            except Exception:
                pass  # Ignore cleanup errors


def restore_sql_format(
    config: RestoreConfig,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    """Restore database from plain SQL format using psql.

    Args:
        config: Restore configuration
        progress_callback: Optional callback(current, total, message) for progress updates

    Raises:
        RestoreError: If restore fails
    """
    file_size = config.backup_file.stat().st_size

    try:
        if progress_callback:
            progress_callback(0, 100, "Starting restore...")

        # Start psql process
        psql_cmd = [
            "docker",
            "compose",
            "-f",
            str(config.compose_file),
            "exec",
            "-T",
            config.db_service,
            "psql",
            "-U",
            config.db_user,
            "-d",
            config.db_name,
        ]

        chunk_size = 1024 * 1024  # 1MB chunks
        bytes_read = 0

        with open(config.backup_file, encoding="utf-8") as sql_file:
            psql_proc = subprocess.Popen(
                psql_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=config.compose_file.parent,
            )

            stdin = psql_proc.stdin
            assert stdin is not None  # for type checker
            try:
                while True:
                    chunk = sql_file.read(chunk_size)
                    if not chunk:
                        break

                    stdin.write(chunk)
                    bytes_read += len(chunk.encode("utf-8"))

                    if progress_callback and file_size > 0:
                        pct = min(int((bytes_read / file_size) * 100), 99)
                        progress_callback(pct, 100, f"Restoring ({bytes_read // (1024 * 1024)} MB)...")

                stdin.close()
                stdout, stderr = psql_proc.communicate()

                if psql_proc.returncode != 0 and stderr:
                    console.print(f"[dim]{stderr}[/dim]")

            except BrokenPipeError:
                psql_proc.kill()
                raise RestoreError("psql process terminated unexpectedly")

        if progress_callback:
            progress_callback(100, 100, "Complete")

    except Exception as err:
        raise RestoreError(f"Failed to restore from SQL format: {err}") from err


def run_schema_upgrade(config: RestoreConfig) -> None:
    """Run database schema upgrade after restore.

    Args:
        config: Restore configuration

    Raises:
        RestoreError: If schema upgrade fails
    """
    if not config.schema_upgrade_service:
        raise RestoreError("Schema upgrade requested but no service specified")

    try:
        docker_compose_cmd(
            config.compose_file,
            ["run", "--rm", config.schema_upgrade_service, "zou", "upgrade-db"],
            check=False,  # Allow to continue if upgrade not needed
        )
    except Exception as err:
        console.print(f"[yellow]Warning: Schema upgrade had issues: {err}[/yellow]")


def _run_step(description: str, action: Callable[[], None]) -> None:
    """Run a step with spinner that becomes checkmark on completion.

    Args:
        description: Step description
        action: Callable to execute
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
        transient=True,  # Clear spinner when done
    ) as progress:
        progress.add_task(description, total=None)
        action()
    console.print(f"[green]✓[/green] {description.rstrip('...')}")


def restore_database(config: RestoreConfig) -> None:
    """Restore database from backup file with progress feedback.

    Args:
        config: Restore configuration

    Raises:
        RestoreError: If restore fails at any step
    """
    if not config.backup_file.exists():
        raise RestoreError(f"Backup file not found: {config.backup_file}")

    backup_format = detect_backup_format(config.backup_file)
    file_size = config.backup_file.stat().st_size
    size_mb = file_size / (1024 * 1024)

    # Step 1: Stop application services
    _run_step(
        f"Stopping {', '.join(config.app_services)}...",
        lambda: stop_services(config.compose_file, config.app_services),
    )

    # Step 2: Ensure database is running
    _run_step(
        f"Starting database {config.db_service}...",
        lambda: ensure_service_running(config.compose_file, config.db_service),
    )

    # Step 3: Terminate connections
    _run_step(
        "Terminating active connections...",
        lambda: terminate_db_connections(config),
    )

    # Step 4: Drop and recreate database
    _run_step(
        "Recreating database...",
        lambda: drop_and_recreate_db(config),
    )

    # Step 5: Restore from backup with progress bar
    restore_desc = f"Restoring {config.backup_file.name} ({size_mb:.1f} MB)"

    with Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"{restore_desc}...", total=100)

        def update_progress(current: int, total: int, message: str) -> None:
            """Update progress bar with current progress."""
            progress.update(task, completed=current, total=total, description=f"{restore_desc}: {message}")

        if backup_format == "custom":
            restore_custom_format(config, progress_callback=update_progress)
        elif backup_format == "gzip":
            restore_gzip_format(config, progress_callback=update_progress)
        else:
            restore_sql_format(config, progress_callback=update_progress)

        progress.update(task, completed=100, total=100)

    console.print(f"[green]✓[/green] {restore_desc}")

    # Step 6: Run schema upgrade (if configured)
    if config.run_schema_upgrade:
        _run_step(
            "Upgrading database schema...",
            lambda: run_schema_upgrade(config),
        )

    # Step 7: Start application services
    _run_step(
        f"Starting {', '.join(config.app_services)}...",
        lambda: start_services(config.compose_file, config.app_services),
    )
