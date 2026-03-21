"""Docker Compose utility functions for database operations."""

from __future__ import annotations

import ipaddress
import subprocess
import time
from pathlib import Path
from typing import Literal

from rich.console import Console

console = Console(stderr=True)

BackupFormat = Literal["custom", "gzip", "sql"]


class DockerComposeError(Exception):
    """Exception raised when docker compose commands fail."""


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
        raise DockerComposeError("docker compose not found. Please install Docker with Compose plugin.") from err


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
            f"Docker compose command failed: {' '.join(cmd)}\nExit code: {err.returncode}\nstderr: {err.stderr}"
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


def ensure_service_running(compose_file: Path, service: str, wait_seconds: int = 5) -> None:
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


def copy_to_container(compose_file: Path, service: str, local_path: Path, container_path: str) -> None:
    """Copy a file to a container.

    Args:
        compose_file: Path to docker-compose.yml file
        service: Service name to copy file to
        local_path: Local file path to copy
        container_path: Destination path in container

    Raises:
        DockerComposeError: If copy fails

    """
    docker_compose_cmd(compose_file, ["cp", str(local_path), f"{service}:{container_path}"])


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
    if suffix == ".gz":
        return "gzip"
    return "sql"


def get_service_ip(compose_file: Path, service: str) -> str | None:
    """Get the IP address of a docker compose service.

    Args:
        compose_file: Path to docker-compose.yml file
        service: Service name

    Returns:
        IP address of the service, or None if not found

    """
    try:
        # Get the container name from docker compose
        result = docker_compose_cmd(
            compose_file,
            ["ps", "-q", service],
            check=False,
        )
        if not result.stdout or not result.stdout.strip():
            return None

        container_id = result.stdout.strip()
        if not container_id:
            return None

        # Get the IP address of the container
        ip_result = subprocess.run(
            ["docker", "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", container_id],
            capture_output=True,
            text=True,
            check=False,
        )

        ip = ip_result.stdout.strip()
        return ip or None
    except Exception:
        return None


def is_local_ip(ip: str) -> bool:
    """Check if an IP address is local (localhost or private network).

    Args:
        ip: IP address to check

    Returns:
        True if the IP is local, False otherwise

    """
    if not ip:
        return False

    try:
        ip_obj = ipaddress.ip_address(ip)
        # Check if it's localhost
        if ip_obj.is_loopback:
            return True
        # Check if it's a private network address
        if ip_obj.is_private:
            return True
        # Check if it's link-local
        if ip_obj.is_link_local:
            return True
        return False
    except ValueError:
        return False


def is_local_database_host(host: str) -> bool:
    """Check if a database host is local (localhost, docker service name, or private IP).

    Args:
        host: Database hostname or IP address

    Returns:
        True if the host is local, False otherwise

    """
    if not host:
        return False

    # Common local database service names in docker-compose
    local_service_names = ["db", "postgres", "postgresql", "localhost", "127.0.0.1", "::1"]
    if host.lower() in local_service_names:
        return True

    # Check if it's a local IP address
    if is_local_ip(host):
        return True

    # Check if it's a docker service name (no dots, typically lowercase)
    # Docker service names are usually simple identifiers
    if "." not in host and not any(c.isupper() for c in host):
        # Could be a docker service name, but we can't be 100% sure
        # For safety, we'll be conservative and allow it if it looks like a service name
        # But we should warn the user
        return True

    return False


def validate_database_is_local(compose_file: Path, db_service: str = "db") -> tuple[bool, str]:
    """Validate that the database service is local and not pointing to a remote database.

    Args:
        compose_file: Path to docker-compose.yml file
        db_service: Name of the database service

    Returns:
        Tuple of (is_local, message) where is_local is True if database is local

    """
    # Check 1: Get database service IP
    db_ip = get_service_ip(compose_file, db_service)
    if db_ip:
        if not is_local_ip(db_ip):
            return (False, f"Database service IP ({db_ip}) is not local! This may be a remote/production database.")
    else:
        # Service might not be running, but we can still check the configuration
        pass

    # Check 2: Validate database connection strings in environment variables
    # Read docker-compose.yml to check for database connection URLs
    try:
        import yaml

        with open(compose_file) as f:
            compose_data = yaml.safe_load(f)

        if not compose_data or not isinstance(compose_data, dict):
            return (True, "Could not parse docker-compose.yml")

        # Check all services for database connection environment variables
        services = compose_data.get("services", {})
        if not isinstance(services, dict):
            return (True, "No services found in docker-compose.yml")

        for service_name, service_config in services.items():
            env_vars = service_config.get("environment", [])
            env_dict = {}

            # Convert environment variables to dict format
            if isinstance(env_vars, list):
                for env_var in env_vars:
                    if isinstance(env_var, str) and "=" in env_var:
                        key, value = env_var.split("=", 1)
                        env_dict[key] = value
            elif isinstance(env_vars, dict):
                env_dict = env_vars
            else:
                continue

            # Check for database connection strings
            db_connection_keys = [
                "POSTGRES_URL",
                "DATABASE_URL",
                "DB_HOST",
                "DB_URL",
                "AYON_POSTGRES_URL",
                "DB_CONNECTION",
            ]

            for key in db_connection_keys:
                if key not in env_dict:
                    continue

                value = env_dict[key]
                if not value:
                    continue

                # Handle environment variable substitution like ${VAR:-default}
                # For now, we'll check the default value or the pattern
                value_str = str(value)

                # Parse connection string
                if "://" in value_str:
                    # URL format: postgres://user:pass@host:port/db
                    # Handle ${VAR:-default} syntax
                    if "${" in value_str and ":-" in value_str:
                        # Extract default value from ${VAR:-default}
                        default_start = value_str.find(":-") + 2
                        default_end = value_str.find("}", default_start)
                        if default_end != -1:
                            value_str = value_str[default_start:default_end]

                    try:
                        from urllib.parse import urlparse

                        parsed = urlparse(value_str)
                        db_host = parsed.hostname
                        if db_host and not is_local_database_host(db_host):
                            return (
                                False,
                                f"Service '{service_name}' has {key} pointing to remote host: {db_host}",
                            )
                    except Exception:
                        pass
                elif key == "DB_HOST":
                    # Direct hostname format: DB_HOST=hostname
                    # Handle ${VAR:-default} syntax
                    if "${" in value_str and ":-" in value_str:
                        default_start = value_str.find(":-") + 2
                        default_end = value_str.find("}", default_start)
                        if default_end != -1:
                            value_str = value_str[default_start:default_end]

                    db_host = value_str.strip()
                    if db_host and not is_local_database_host(db_host):
                        return (
                            False,
                            f"Service '{service_name}' has DB_HOST pointing to remote host: {db_host}",
                        )

    except Exception:
        # If we can't parse, assume it's okay (might be using external config)
        pass

    return (True, "Database is configured to use local services")


def get_service_hostname_and_port(compose_file: Path, service: str) -> tuple[str | None, int | None]:
    """Get the hostname and port of a docker compose service from ports mapping.

    Args:
        compose_file: Path to docker-compose.yml file
        service: Service name

    Returns:
        Tuple of (hostname, port) or (None, None) if not found

    """
    try:
        # First try to get port from running container
        result = docker_compose_cmd(
            compose_file,
            ["ps", "-q", service],
            check=False,
        )
        if result.stdout and result.stdout.strip():
            container_id = result.stdout.strip()
            if container_id:
                # Get port mapping from running container
                port_result = subprocess.run(
                    [
                        "docker",
                        "inspect",
                        "-f",
                        "{{range $p, $conf := .NetworkSettings.Ports}}{{$p}} {{end}}",
                        container_id,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

                ports = port_result.stdout.strip()
                if ports:
                    # Parse the first port (format: "5000/tcp" or "5000:5000/tcp")
                    port_parts = ports.split()[0].split("/")[0]
                    if ":" in port_parts:
                        # Format: "host_port:container_port"
                        host_port = int(port_parts.split(":")[0])
                    else:
                        # Format: "container_port"
                        host_port = int(port_parts)
                    return ("localhost", host_port)

        # Fallback: Try to read port from docker-compose.yml file
        try:
            import yaml

            with open(compose_file) as f:
                compose_data = yaml.safe_load(f)
                if not compose_data or not isinstance(compose_data, dict):
                    return (None, None)
                services = compose_data.get("services", {})
                if not isinstance(services, dict) or service not in services:
                    return (None, None)
                service_config = services[service]
                if not isinstance(service_config, dict):
                    return (None, None)
                ports = service_config.get("ports", [])
                if ports:
                    # Parse first port mapping
                    # Format can be:
                    # - "5000:5000" (string)
                    # - "5000:5000/tcp" (string with protocol)
                    # - "${VAR:-5000}:5000" (string with env var)
                    # - {"published": 5000, "target": 5000} (dict)
                    port_mapping = ports[0]
                    if isinstance(port_mapping, str):
                        # String format: "5000:5000" or "${VAR:-5000}:5000"
                        # Split by colon, but be careful with ${VAR:-default} syntax
                        # First check if it's an env var with default
                        if "${" in port_mapping and ":-" in port_mapping:
                            # Format: "${VAR:-default}:container_port"
                            # Extract the part before the first colon that's not part of ${...}
                            # Find the colon that separates host:container (after the closing })
                            closing_brace = port_mapping.find("}")
                            if closing_brace != -1:
                                # Everything before the colon after the closing brace is the host port part
                                remaining = port_mapping[closing_brace + 1 :]
                                if ":" in remaining:
                                    # Extract default value from ${VAR:-default}
                                    default_start = port_mapping.find(":-") + 2
                                    default_end = port_mapping.find("}", default_start)
                                    if default_end != -1:
                                        default_val = port_mapping[default_start:default_end]
                                        try:
                                            host_port = int(default_val)
                                            return ("localhost", host_port)
                                        except ValueError:
                                            return (None, None)
                        else:
                            # Plain format: "5000:5000" or "5000:5000/tcp"
                            host_port_str = port_mapping.split(":")[0].split("/")[0]
                            try:
                                host_port = int(host_port_str)
                                return ("localhost", host_port)
                            except ValueError:
                                return (None, None)
                    elif isinstance(port_mapping, dict):
                        # Dict format: {"published": 5000, "target": 5000}
                        if "published" in port_mapping:
                            try:
                                host_port = int(port_mapping["published"])
                                return ("localhost", host_port)
                            except (ValueError, TypeError):
                                return (None, None)
        except Exception:
            # Silently fail - service might not have ports or yaml might not be available
            return (None, None)

        return (None, None)
    except Exception:
        return (None, None)
