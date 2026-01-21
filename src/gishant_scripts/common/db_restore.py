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


def restore_gzip_format(
    config: RestoreConfig,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> None:
    """Restore database from gzip format (.gz, .sql.gz) using gzip + psql.

    Args:
        config: Restore configuration
        progress_callback: Optional callback(current, total, message) for progress updates

    Raises:
        RestoreError: If restore fails
    """
    import gzip

    file_size = config.backup_file.stat().st_size

    if progress_callback:
        msg = "Starting restore (skipping thumbnails)..." if config.skip_thumbnails else "Starting restore..."
        progress_callback(0, 100, msg)

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

    psql_proc = subprocess.Popen(
        psql_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=config.compose_file.parent,
    )

    stdin = psql_proc.stdin
    assert stdin is not None  # for type checker

    try:
        last_pct = 0
        skipped_rows = 0
        in_copy_block = False  # Track if we're inside a COPY data block

        with open(config.backup_file, "rb") as compressed_file:
            with gzip.open(compressed_file, "rt", encoding="utf-8", errors="replace") as gz_text:
                # Use buffered reading for line-by-line processing when filtering
                if config.skip_thumbnails:
                    for line in gz_text:
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
                        stdin.write(line.encode("utf-8"))

                        if progress_callback:
                            compressed_bytes_read = compressed_file.tell()
                            if file_size > 0:
                                pct = min(int((compressed_bytes_read / file_size) * 100), 99)
                                if pct > last_pct:
                                    last_pct = pct
                                    mb_read = compressed_bytes_read // (1024 * 1024)
                                    mb_total = file_size // (1024 * 1024)
                                    skip_info = f", skipped {skipped_rows} rows" if skipped_rows else ""
                                    progress_callback(pct, 100, f"Restoring ({mb_read}/{mb_total} MB{skip_info})...")
                else:
                    # No filtering - read in chunks for speed
                    chunk_size = 1024 * 1024  # 1MB
                    while True:
                        chunk = gz_text.read(chunk_size)
                        if not chunk:
                            break

                        stdin.write(chunk.encode("utf-8"))
                        stdin.flush()

                        if progress_callback:
                            compressed_bytes_read = compressed_file.tell()
                            if file_size > 0:
                                pct = min(int((compressed_bytes_read / file_size) * 100), 99)
                                if pct > last_pct:
                                    last_pct = pct
                                    mb_read = compressed_bytes_read // (1024 * 1024)
                                    mb_total = file_size // (1024 * 1024)
                                    progress_callback(pct, 100, f"Restoring ({mb_read}/{mb_total} MB)...")

        # Close stdin after all data is written
        stdin.close()

        # Wait for psql to finish
        stdout, stderr = psql_proc.communicate()

        if psql_proc.returncode != 0:
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
            if stderr_text:
                console.print(f"[dim]{stderr_text}[/dim]")

        if progress_callback:
            if config.skip_thumbnails and skipped_rows > 0:
                console.print(f"[dim]Skipped {skipped_rows:,} thumbnail rows[/dim]")
            progress_callback(100, 100, "Complete")

    except BrokenPipeError:
        psql_proc.kill()
        raise RestoreError("psql process terminated unexpectedly")
    except Exception as err:
        psql_proc.kill()
        raise RestoreError(f"Failed to restore from gzip format: {err}") from err


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
