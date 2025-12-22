"""Docker Compose utility functions for database operations."""

import subprocess
import time
from pathlib import Path
from typing import Literal

from rich.console import Console

console = Console(stderr=True)

BackupFormat = Literal["custom", "gzip", "sql"]


class DockerComposeError(Exception):
    """Exception raised when docker compose commands fail."""

    pass


def check_docker_compose() -> None:
    """Check if docker compose is available.

    Raises:
        DockerComposeError: If docker compose is not found
    """
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        raise DockerComposeError(
            "docker compose not found. Please install Docker with Compose plugin."
        ) from err


def docker_compose_cmd(
    compose_file: Path,
    command: list[str],
    capture_output: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Execute a docker compose command.

    Args:
        compose_file: Path to docker-compose.yml file
        command: Docker compose command and arguments (e.g., ["stop", "zou"])
        capture_output: Whether to capture stdout/stderr
        check: Whether to raise exception on non-zero exit code

    Returns:
        CompletedProcess instance with command results

    Raises:
        DockerComposeError: If command fails and check=True
    """
    if not compose_file.exists():
        raise DockerComposeError(f"Docker compose file not found: {compose_file}")

    cmd = ["docker", "compose", "-f", str(compose_file)] + command

    try:
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=check,
            cwd=compose_file.parent,
        )
    except subprocess.CalledProcessError as err:
        raise DockerComposeError(
            f"Docker compose command failed: {' '.join(cmd)}\n"
            f"Exit code: {err.returncode}\n"
            f"stderr: {err.stderr}"
        ) from err


def stop_services(compose_file: Path, services: list[str]) -> None:
    """Stop specified docker compose services.

    Args:
        compose_file: Path to docker-compose.yml file
        services: List of service names to stop

    Raises:
        DockerComposeError: If stop command fails
    """
    try:
        docker_compose_cmd(compose_file, ["stop"] + services, check=False)
    except DockerComposeError as err:
        # Log but don't fail if services are already stopped
        console.print(f"[dim]Note: {err}[/dim]")


def start_services(compose_file: Path, services: list[str]) -> None:
    """Start specified docker compose services.

    Args:
        compose_file: Path to docker-compose.yml file
        services: List of service names to start

    Raises:
        DockerComposeError: If start command fails
    """
    docker_compose_cmd(compose_file, ["start"] + services)


def ensure_service_running(
    compose_file: Path, service: str, wait_seconds: int = 5
) -> None:
    """Ensure a service is running, starting it if necessary.

    Args:
        compose_file: Path to docker-compose.yml file
        service: Service name to ensure is running
        wait_seconds: Seconds to wait after starting service

    Raises:
        DockerComposeError: If service cannot be started
    """
    start_services(compose_file, [service])
    time.sleep(wait_seconds)


def exec_in_service(
    compose_file: Path,
    service: str,
    command: list[str],
    stdin: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Execute a command in a running service container.

    Args:
        compose_file: Path to docker-compose.yml file
        service: Service name to execute command in
        command: Command and arguments to execute
        stdin: Optional string to send to command stdin
        check: Whether to raise exception on non-zero exit code

    Returns:
        CompletedProcess instance with command results

    Raises:
        DockerComposeError: If command fails and check=True
    """
    exec_cmd = ["exec", "-T", service] + command

    if stdin:
        # Pipe stdin to the command
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file)] + exec_cmd,
            input=stdin,
            capture_output=True,
            text=True,
            check=check,
            cwd=compose_file.parent,
        )
    else:
        result = docker_compose_cmd(compose_file, exec_cmd, check=check)

    return result


def copy_to_container(
    compose_file: Path, service: str, local_path: Path, container_path: str
) -> None:
    """Copy a file to a container.

    Args:
        compose_file: Path to docker-compose.yml file
        service: Service name to copy file to
        local_path: Local file path to copy
        container_path: Destination path in container

    Raises:
        DockerComposeError: If copy fails
    """
    docker_compose_cmd(
        compose_file, ["cp", str(local_path), f"{service}:{container_path}"]
    )


def detect_backup_format(backup_file: Path) -> BackupFormat:
    """Detect backup file format from extension.

    Args:
        backup_file: Path to backup file

    Returns:
        Backup format type: 'custom', 'gzip', or 'sql'
    """
    suffix = backup_file.suffix.lower()

    if suffix in [".dump", ".backup"]:
        return "custom"
    elif suffix == ".gz":
        return "gzip"
    else:
        return "sql"
