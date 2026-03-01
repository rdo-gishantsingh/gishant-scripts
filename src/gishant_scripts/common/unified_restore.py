"""Unified database restore functionality for parallel Ayon and Kitsu restores."""

import multiprocessing
import shutil
import tempfile
from dataclasses import dataclass
from multiprocessing import Queue
from pathlib import Path
from typing import Literal

from rich.console import Console

from gishant_scripts.common.db_restore import RestoreConfig, RestoreError, restore_database
from gishant_scripts.common.docker_utils import DockerComposeError

console = Console()


@dataclass
class RestoreResult:
    """Result of a database restore operation."""

    database: Literal["ayon", "kitsu"]
    success: bool
    error: str | None = None
    backup_file: Path | None = None


def find_latest_backup(directory: Path, recursive: bool = False) -> Path | None:
    """Find the latest backup file in a directory.

    Args:
        directory: Directory to search in
        recursive: Whether to search recursively in subdirectories

    Returns:
        Path to latest backup file, or None if not found
    """
    if not directory.exists():
        return None

    backup_extensions = [".dump", ".backup", ".gz", ".sql"]
    latest_file: Path | None = None
    latest_mtime = 0.0

    if recursive:
        # Search recursively
        for ext in backup_extensions:
            for backup_file in directory.rglob(f"*{ext}"):
                if backup_file.is_file():
                    mtime = backup_file.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest_file = backup_file
    else:
        # Search only in the directory itself
        for ext in backup_extensions:
            for backup_file in directory.glob(f"*{ext}"):
                if backup_file.is_file():
                    mtime = backup_file.stat().st_mtime
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest_file = backup_file

    return latest_file


def copy_backup_to_local(backup_file: Path, temp_dir: Path) -> Path:
    """Copy backup file to a local temporary directory.

    Args:
        backup_file: Source backup file path
        temp_dir: Temporary directory to copy to

    Returns:
        Path to the copied backup file
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    local_backup = temp_dir / backup_file.name

    console.print(f"[cyan]Copying {backup_file.name} to local temporary directory...[/cyan]")
    shutil.copy2(backup_file, local_backup)
    size_mb = local_backup.stat().st_size / (1024 * 1024)
    console.print(f"[green]✓[/green] Copied {backup_file.name} ({size_mb:.1f} MB)")

    return local_backup


def restore_worker(
    database: Literal["ayon", "kitsu"],
    backup_file: Path,
    config: RestoreConfig,
    result_queue: Queue,
    original_backup_path: Path | None = None,
) -> None:
    """Worker function to restore a database in a separate process.

    Args:
        database: Database name ("ayon" or "kitsu")
        backup_file: Path to backup file (local copy)
        config: Restore configuration
        result_queue: Queue to send results to
        original_backup_path: Original backup file path (for reporting)
    """
    try:
        # Update config with the backup file
        config.backup_file = backup_file

        # Execute restore
        restore_database(config)

        result_queue.put(
            RestoreResult(
                database=database,
                success=True,
                backup_file=original_backup_path or backup_file,
            )
        )
    except (RestoreError, DockerComposeError) as err:
        result_queue.put(
            RestoreResult(
                database=database,
                success=False,
                error=str(err),
                backup_file=original_backup_path or backup_file,
            )
        )
    except Exception as err:
        result_queue.put(
            RestoreResult(
                database=database,
                success=False,
                error=f"Unexpected error: {err}",
                backup_file=original_backup_path or backup_file,
            )
        )


def unified_restore(
    ayon_backup_dir: Path,
    kitsu_backup_dir: Path,
    ayon_config: RestoreConfig | None = None,
    kitsu_config: RestoreConfig | None = None,
    restore_ayon: bool = True,
    restore_kitsu: bool = True,
    copy_to_local: bool = True,
) -> tuple[RestoreResult, RestoreResult]:
    """Restore Ayon and/or Kitsu databases in parallel.

    Args:
        ayon_backup_dir: Directory to search for Ayon backups
        kitsu_backup_dir: Directory to search for Kitsu backups
        ayon_config: Ayon restore configuration (auto-detected if None)
        kitsu_config: Kitsu restore configuration (auto-detected if None)
        restore_ayon: Whether to restore Ayon database
        restore_kitsu: Whether to restore Kitsu database
        copy_to_local: Whether to copy backups to local temp directory first

    Returns:
        Tuple of (ayon_result, kitsu_result)
    """
    # Find latest backups
    console.print("[cyan]Searching for latest backups...[/cyan]")
    ayon_backup: Path | None = None
    kitsu_backup: Path | None = None

    if restore_ayon:
        ayon_backup = find_latest_backup(ayon_backup_dir, recursive=False)
        if ayon_backup is None:
            console.print(f"[yellow]⚠ No Ayon backup found in {ayon_backup_dir}[/yellow]")
        else:
            size_mb = ayon_backup.stat().st_size / (1024 * 1024)
            console.print(f"[green]✓[/green] Found Ayon backup: {ayon_backup.name} ({size_mb:.1f} MB)")

    if restore_kitsu:
        kitsu_backup = find_latest_backup(kitsu_backup_dir, recursive=True)
        if kitsu_backup is None:
            console.print(f"[yellow]⚠ No Kitsu backup found in {kitsu_backup_dir}[/yellow]")
        else:
            size_mb = kitsu_backup.stat().st_size / (1024 * 1024)
            console.print(f"[green]✓[/green] Found Kitsu backup: {kitsu_backup.name} ({size_mb:.1f} MB)")

    # Create temporary directory for local backups if needed
    temp_dir: Path | None = None
    ayon_local_backup: Path | None = None
    kitsu_local_backup: Path | None = None

    if copy_to_local:
        temp_dir = Path(tempfile.mkdtemp(prefix="db_restore_"))
        console.print(f"[cyan]Using temporary directory: {temp_dir}[/cyan]")

        if ayon_backup is not None:
            ayon_local_backup = copy_backup_to_local(ayon_backup, temp_dir)

        if kitsu_backup is not None:
            kitsu_local_backup = copy_backup_to_local(kitsu_backup, temp_dir)

    # Auto-detect configs if not provided
    if ayon_config is None:
        script_dir = Path(__file__).parent.parent / "ayon"
        compose_file = script_dir / "ayon-server" / "docker-compose.yml"

        if not compose_file.exists():
            raise RestoreError(f"Could not find Ayon docker-compose.yml at {compose_file}")

        ayon_config = RestoreConfig(
            compose_file=compose_file,
            backup_file=ayon_backup or Path("/dev/null"),  # Will be updated in worker
            db_service="db",
            app_services=["server", "worker"],
            db_user="ayon",
            db_name="ayon",
            run_schema_upgrade=False,
            schema_upgrade_service=None,
        )

    if kitsu_config is None:
        script_dir = Path(__file__).parent.parent / "kitsu"
        compose_file = script_dir / "kitsu-server" / "docker-compose.yml"

        if not compose_file.exists():
            raise RestoreError(f"Could not find Kitsu docker-compose.yml at {compose_file}")

        kitsu_config = RestoreConfig(
            compose_file=compose_file,
            backup_file=kitsu_backup or Path("/dev/null"),  # Will be updated in worker
            db_service="db",
            app_services=["zou", "kitsu"],
            db_user="zou",
            db_name="zoudb",
            run_schema_upgrade=True,
            schema_upgrade_service="zou",
        )

    # Use local backups if copied, otherwise use original
    ayon_restore_file = ayon_local_backup if ayon_local_backup else ayon_backup
    kitsu_restore_file = kitsu_local_backup if kitsu_local_backup else kitsu_backup

    # Create result queue
    result_queue: Queue = multiprocessing.Queue()

    # Start restore processes
    processes = []

    if ayon_restore_file is not None:
        ayon_process = multiprocessing.Process(
            target=restore_worker,
            args=("ayon", ayon_restore_file, ayon_config, result_queue, ayon_backup),
        )
        ayon_process.start()
        processes.append(("ayon", ayon_process))

    if kitsu_restore_file is not None:
        kitsu_process = multiprocessing.Process(
            target=restore_worker,
            args=("kitsu", kitsu_restore_file, kitsu_config, result_queue, kitsu_backup),
        )
        kitsu_process.start()
        processes.append(("kitsu", kitsu_process))

    # Wait for all processes to complete and collect results
    results: dict[str, RestoreResult] = {}
    for db_name, process in processes:
        process.join()
        # Get result from queue
        result = result_queue.get()
        results[db_name] = result

    # Clean up temporary directory
    if temp_dir and temp_dir.exists():
        try:
            console.print("[cyan]Cleaning up temporary directory...[/cyan]")
            shutil.rmtree(temp_dir)
            console.print("[green]✓[/green] Temporary files cleaned up")
        except Exception as err:
            console.print(f"[yellow]⚠ Warning: Could not clean up temporary directory {temp_dir}: {err}[/yellow]")

    # Create default results for databases that weren't restored
    ayon_result = results.get(
        "ayon",
        RestoreResult(database="ayon", success=False, error="No backup found or restore skipped", backup_file=None),
    )
    kitsu_result = results.get(
        "kitsu",
        RestoreResult(database="kitsu", success=False, error="No backup found or restore skipped", backup_file=None),
    )

    return ayon_result, kitsu_result
