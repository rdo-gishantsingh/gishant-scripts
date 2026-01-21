#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
import time
from typing import Any

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

# Try to import yaml
try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Please run with 'uv run --with pyyaml ...'")
    sys.exit(1)

console = Console()
app = typer.Typer()


def run_command(
    command: list[str], shell: bool = False, check: bool = True, sudo: bool = False
) -> subprocess.CompletedProcess:
    """Run a command, optionally with sudo."""
    if sudo and os.geteuid() != 0:
        command = ["sudo"] + command

    cmd_str = " ".join(command)
    console.print(f"[dim]Running: {cmd_str}[/dim]")

    try:
        result = subprocess.run(command, check=check, shell=shell, capture_output=True, text=True)
        return result
    except subprocess.CalledProcessError as e:
        console.print(f"[bold red]Error running command:[/bold red] {cmd_str}")
        console.print(f"[red]Stderr:[/red] {e.stderr}")
        console.print(f"[red]Stdout:[/red] {e.stdout}")
        raise


def ensure_sudo():
    """Ensure the script has sudo privileges."""
    if os.geteuid() != 0:
        console.print("[yellow]This script requires sudo privileges.[/yellow]")
        try:
            subprocess.check_call(["sudo", "-v"])
        except subprocess.CalledProcessError:
            console.print("[bold red]Sudo authentication failed. Exiting.[/bold red]")
            raise typer.Exit(1)


def find_free_port(start_port: int, max_port: int = 6000) -> int:
    """Find a free port starting from start_port."""
    import socket

    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free ports found.")


def resolve_to_ipv4(host: str) -> tuple[str, bool, list[str]]:
    """
    Resolve hostname to IPv4 address using robust methods.

    This function explicitly requests IPv4 addresses only to avoid issues
    with IPv6 connectivity in Docker containers or systems without proper
    IPv6 routing.

    Args:
        host: Hostname or IP address to resolve

    Returns:
        Tuple of (resolved_address, is_ipv4, ipv6_addresses_if_any)
        - resolved_address: The IPv4 address or original hostname if resolution fails
        - is_ipv4: True if the resolved_address is a valid IPv4 address
        - ipv6_addresses_if_any: List of IPv6 addresses found (for diagnostics)
    """
    import socket

    ipv6_addresses: list[str] = []

    # Check if already an IPv4 address
    try:
        socket.inet_aton(host)
        # Verify it's IPv4 (not IPv6 - IPv6 contains colons)
        if ":" not in host:
            console.print(f"[green]Host '{host}' is already an IPv4 address.[/green]")
            return host, True, []
    except OSError:
        pass

    # Check if it's an IPv6 address
    try:
        socket.inet_pton(socket.AF_INET6, host)
        console.print(f"[yellow]Warning: '{host}' is an IPv6 address. This may cause connectivity issues.[/yellow]")
        return host, False, [host]
    except OSError:
        pass

    # Try explicit IPv4 resolution using getaddrinfo with AF_INET
    ipv4_addr = None
    try:
        # Force IPv4 only (AF_INET)
        addrinfo = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM)
        if addrinfo:
            ipv4_addr = addrinfo[0][4][0]
            console.print(f"[green]Resolved '{host}' to IPv4: {ipv4_addr}[/green]")
    except socket.gaierror as e:
        console.print(f"[yellow]IPv4 resolution via getaddrinfo failed: {e}[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Unexpected error during IPv4 resolution: {e}[/yellow]")

    # Check if IPv6 addresses exist (for diagnostics/warning)
    try:
        addrinfo_v6 = socket.getaddrinfo(host, None, socket.AF_INET6, socket.SOCK_STREAM)
        if addrinfo_v6:
            ipv6_addresses = list(set(info[4][0] for info in addrinfo_v6))
            if ipv6_addresses:
                console.print(
                    f"[yellow]Note: '{host}' also has IPv6 addresses: {', '.join(ipv6_addresses[:3])}[/yellow]"
                )
                if not ipv4_addr:
                    console.print(
                        "[bold yellow]Warning: No IPv4 address found but IPv6 exists. "
                        "This may cause 'Network is unreachable' errors in Docker![/bold yellow]"
                    )
    except Exception:
        pass

    if ipv4_addr:
        return ipv4_addr, True, ipv6_addresses

    # Fallback: try gethostbyname (which typically returns IPv4)
    try:
        fallback_ip = socket.gethostbyname(host)
        if ":" not in fallback_ip:  # Verify it's IPv4
            console.print(f"[green]Resolved '{host}' to IPv4 (fallback): {fallback_ip}[/green]")
            return fallback_ip, True, ipv6_addresses
    except socket.gaierror as e:
        console.print(f"[red]Fallback IPv4 resolution also failed: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected error during fallback resolution: {e}[/red]")

    # Could not resolve to IPv4
    console.print(f"[bold red]Could not resolve '{host}' to an IPv4 address.[/bold red]")
    console.print("[dim]Tip: You can manually specify an IPv4 address using --host <ip_address>[/dim]")

    return host, False, ipv6_addresses


def is_valid_ipv4(address: str) -> bool:
    """Check if a string is a valid IPv4 address."""
    import socket

    try:
        socket.inet_aton(address)
        return ":" not in address  # Ensure it's not IPv6
    except OSError:
        return False


def perform_cleanup():
    """Completely remove existing Postal installation."""
    console.print(Panel("Cleaning up existing installation...", style="bold red"))

    # Try to stop postal services first if binary exists
    if shutil.which("postal"):
        console.print("Stopping Postal services...")
        try:
            run_command(["postal", "stop"], sudo=True, check=False)
        except Exception:
            pass

    # Remove containers managed by this script explicitly
    containers = ["postal-mariadb", "postal-caddy"]
    console.print("Removing containers...")
    for container in containers:
        run_command(["docker", "rm", "-f", container], sudo=True, check=False)

    # Remove directories
    paths = [
        "/opt/postal/config",
        "/opt/postal/caddy-data",
        "/opt/postal/install",  # The repo itself
        "/usr/bin/postal",  # The symlink
    ]

    for path in paths:
        if os.path.exists(path):
            console.print(f"Removing {path}...")
            run_command(["rm", "-rf", path], sudo=True)

    console.print("[green]Cleanup complete. Starting fresh.[/green]")


def check_and_cleanup(force: bool):
    """Check for existing install and prompt for cleanup."""
    indicators = [
        os.path.exists("/opt/postal/config/postal.yml"),
        os.path.exists("/usr/bin/postal"),
        # check for our containers by name
        shutil.which("docker")
        and subprocess.run(
            ["docker", "ps", "-a", "-q", "-f", "name=postal-mariadb"], capture_output=True
        ).stdout.strip(),
        shutil.which("docker")
        and subprocess.run(["docker", "ps", "-a", "-q", "-f", "name=postal-caddy"], capture_output=True).stdout.strip(),
    ]

    if any(indicators):
        console.print(Panel("[yellow]Existing Postal components detected.[/yellow]", style="yellow"))
        if force:
            perform_cleanup()
        else:
            if Confirm.ask(
                "Do you want to [bold red]WIPE[/bold red] the existing installation and start fresh?", default=False
            ):
                perform_cleanup()
            else:
                console.print(
                    "[dim]Proceeding with existing components (skipping creation steps if resources exist)...[/dim]"
                )


def check_system_requirements():
    """Check basic system requirements."""
    console.print(Panel("Checking System Requirements", style="bold blue"))

    # Check RAM
    total_ram_gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024.0**3)
    console.print(f"Detected RAM: [bold]{total_ram_gb:.2f} GB[/bold]")
    if total_ram_gb < 3.5:
        console.print("[yellow]Warning: Postal recommends at least 4GB of RAM.[/yellow]")
        if not Confirm.ask("Do you want to continue anyway?", default=True):
            raise typer.Exit()


def install_system_utils():
    """Install git, curl, jq if missing."""
    console.print(Panel("Installing System Utilities", style="bold blue"))

    utils = ["git", "curl", "jq"]
    to_install = [u for u in utils if not shutil.which(u)]

    if to_install:
        console.print(f"Installing missing utilities: {', '.join(to_install)}")
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True
        ) as progress:
            progress.add_task(description="Installing...", total=None)
            # Detect OS package manager
            if shutil.which("apt"):
                run_command(["apt", "update"], sudo=True)
                run_command(["apt", "install", "-y"] + to_install, sudo=True)
            elif shutil.which("yum"):
                run_command(["yum", "install", "-y"] + to_install, sudo=True)
            elif shutil.which("dnf"):
                run_command(["dnf", "install", "-y"] + to_install, sudo=True)
            else:
                console.print(
                    "[bold red]Could not detect package manager. Please install git, curl, jq manually.[/bold red]"
                )
                raise typer.Exit(1)
        console.print("[green]System utilities installed.[/green]")
    else:
        console.print("[green]All system utilities checked.[/green]")


def check_docker():
    """Check if docker and docker compose are installed."""
    console.print(Panel("Checking components...", style="bold blue"))

    if not shutil.which("docker"):
        console.print("[bold red]Docker is not installed.[/bold red]")
        console.print("Please install Docker first: https://docs.docker.com/engine/install/")
        raise typer.Exit(1)

    try:
        run_command(["docker", "compose", "version"], check=True)
        console.print("[green]Docker and Docker Compose are available.[/green]")
    except subprocess.CalledProcessError:
        console.print("[bold red]Docker Compose plugin 'docker compose' is not available.[/bold red]")
        raise typer.Exit(1)


def setup_postal_repo():
    """Clone postal installation repo and link binary."""
    console.print(Panel("Setting up Postal Repository", style="bold blue"))

    if os.path.exists("/opt/postal/install"):
        console.print("/opt/postal/install already exists. Skipping clone.")
    else:
        run_command(["git", "clone", "https://github.com/postalserver/install", "/opt/postal/install"], sudo=True)

    if not os.path.exists("/usr/bin/postal"):
        run_command(["ln", "-s", "/opt/postal/install/bin/postal", "/usr/bin/postal"], sudo=True)
        console.print("[green]Postal binary linked.[/green]")
    else:
        console.print("Postal binary already linked.")


def setup_database(db_password: str):
    """Run MariaDB container."""
    console.print(Panel("Setting up MariaDB", style="bold blue"))

    res = run_command(["docker", "ps", "-a", "-q", "-f", "name=postal-mariadb"])
    if res.stdout.strip():
        console.print("[yellow]MariaDB container 'postal-mariadb' already exists. Skipping creation.[/yellow]")
        return

    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        "postal-mariadb",
        "-p",
        "127.0.0.1:3306:3306",
        "--restart",
        "always",
        "-e",
        "MARIADB_DATABASE=postal",
        "-e",
        f"MARIADB_ROOT_PASSWORD={db_password}",
        "mariadb",
    ]
    run_command(cmd)
    console.print("[green]MariaDB container started.[/green]")
    console.print("Waiting for Database to initialize...")
    time.sleep(10)


def update_postal_config_yaml(updates: dict[str, Any]):
    """Update postal.yml using PyYAML for robust handling."""
    config_path = "/opt/postal/config/postal.yml"
    console.print(f"Updating configuration in {config_path}...")

    try:
        # Read the file (requires sudo, so we copy it to temp, edit, move back)
        temp_path = "/tmp/postal.yml.tmp"
        run_command(["sudo", "cp", config_path, temp_path])
        run_command(["sudo", "chmod", "666", temp_path])  # make readable/writable

        with open(temp_path) as f:
            config = yaml.safe_load(f) or {}

        # Apply updates
        for key, value in updates.items():
            keys = key.split(".")
            current = config
            for i, k in enumerate(keys[:-1]):
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value

        with open(temp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        # Move back
        run_command(["sudo", "mv", temp_path, config_path])

        console.print("[green]Configuration updated successfully (YAML).[/green]")

    except Exception as e:
        console.print(f"[bold red]Failed to update configuration YAML: {e}[/bold red]")
        sys.exit(1)


def ensure_postal_config_correct(domain: str, db_password: str, web_port: int):
    """
    Ensure Postal configuration is correct according to v3 standards.

    Based on Postal documentation:
    - https://docs.postalserver.io/getting-started/configuration
    - https://docs.postalserver.io/getting-started/dns-configuration
    """
    config_path = "/opt/postal/config/postal.yml"

    # Read current config
    temp_path = "/tmp/postal.yml.tmp"
    run_command(["sudo", "cp", config_path, temp_path])
    run_command(["sudo", "chmod", "666", temp_path])

    with open(temp_path) as f:
        config = yaml.safe_load(f) or {}

    # Ensure version 2 (required for Postal v3)
    if "version" not in config or config.get("version") != 2:
        console.print("[yellow]Setting configuration version to 2 (required for Postal v3)[/yellow]")
        config["version"] = 2

    # Ensure postal block exists with required fields
    if "postal" not in config:
        config["postal"] = {}

    # Set required postal fields according to docs
    config["postal"]["web_hostname"] = domain
    config["postal"]["smtp_hostname"] = domain

    # Initialize smtp_relays as empty array (can be added later)
    if "smtp_relays" not in config["postal"]:
        config["postal"]["smtp_relays"] = []

    # Ensure web_server configuration
    if "web_server" not in config:
        config["web_server"] = {}
    config["web_server"]["default_port"] = web_port
    config["web_server"]["default_bind_address"] = "0.0.0.0"

    # Ensure smtp_server configuration (defaults from docs)
    if "smtp_server" not in config:
        config["smtp_server"] = {}
    if "default_port" not in config["smtp_server"]:
        config["smtp_server"]["default_port"] = 25
    if "default_bind_address" not in config["smtp_server"]:
        # IPv6 wildcard also listens on IPv4 (dual-stack)
        config["smtp_server"]["default_bind_address"] = "::"

    # Ensure smtp_client configuration for TLS
    if "smtp_client" not in config:
        config["smtp_client"] = {}
    if "tls_mode" not in config["smtp_client"]:
        config["smtp_client"]["tls_mode"] = "TLS"

    # Ensure database passwords are set
    if "main_db" not in config:
        config["main_db"] = {}
    config["main_db"]["host"] = "127.0.0.1"
    config["main_db"]["database"] = "postal"
    config["main_db"]["username"] = "root"
    config["main_db"]["password"] = db_password

    if "message_db" not in config:
        config["message_db"] = {}
    config["message_db"]["host"] = "127.0.0.1"
    config["message_db"]["username"] = "root"
    config["message_db"]["password"] = db_password
    config["message_db"]["prefix"] = "postal"

    # DNS configuration - minimal for local testing
    # According to docs, these are optional for local testing
    # Only needed when receiving external mail or sending with proper DNS
    if "dns" not in config:
        config["dns"] = {}

    # Write back
    with open(temp_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    run_command(["sudo", "mv", temp_path, config_path])
    console.print("[green]Configuration validated and updated.[/green]")


def bootstrap_postal(domain: str, db_password: str, web_port: int):
    """Bootstrap configuration and update it."""
    console.print(Panel("Bootstrapping Postal Configuration", style="bold blue"))

    if os.path.exists("/opt/postal/config/postal.yml"):
        console.print("[yellow]Configuration already exists. Validating and updating...[/yellow]")
    else:
        run_command(["postal", "bootstrap", domain], sudo=True)
        console.print("[green]Configuration bootstrapped.[/green]")

    console.print("Ensuring configuration is correct for Postal v3...")

    # Ensure all configuration is correct according to Postal v3 standards
    ensure_postal_config_correct(domain, db_password, web_port)


def setup_caddy_config(domain: str, port: int):
    """Write Caddyfile configuration."""
    console.print("Configuring Caddy...")

    # We write a clean Caddyfile to avoid sed corruption.
    # This also handles the 'tls internal' needed for local domains.
    caddy_content = f"""{domain} {{
  tls internal
  reverse_proxy 127.0.0.1:{port}
}}

# If you need external access via public IP, you might need to remove 'tls internal'
# and ensure your domain resolves publicly for Let's Encrypt.
"""
    try:
        process = subprocess.Popen(
            ["sudo", "tee", "/opt/postal/config/Caddyfile"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.communicate(input=caddy_content)
        console.print("[green]Caddyfile configured successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to write Caddyfile: {e}[/red]")


def update_hosts_file(domain: str):
    """Add domain to /etc/hosts if not present."""
    console.print(Panel("Updating /etc/hosts", style="bold blue"))

    entry = f"127.0.0.1 {domain}"
    try:
        with open("/etc/hosts") as f:
            content = f.read()

        if domain in content:
            console.print(f"/etc/hosts already contains {domain}.")
            return

        console.print(f"Adding '{entry}' to /etc/hosts...")
        # Use sudo tee -a with text=True to fix encoding issues
        cmd = ["sudo", "tee", "-a", "/etc/hosts"]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True)
        process.communicate(input=f"\n{entry}\n")

        if process.returncode == 0:
            console.print("[green]Updated /etc/hosts successfully.[/green]")
        else:
            console.print("[red]Failed to update /etc/hosts (return code non-zero).[/red]")

    except Exception as e:
        console.print(f"[red]Failed to update /etc/hosts: {e}[/red]")


def create_initial_user(email: str, password: str, first_name: str, last_name: str):
    """Create the initial admin user non-interactively."""
    console.print(Panel("Creating Admin User", style="bold blue"))

    input_str = f"{email}\n{first_name}\n{last_name}\n{password}\n"

    cmd = ["postal", "make-user"]
    if os.geteuid() != 0:
        cmd = ["sudo"] + cmd

    console.print(f"Creating user [bold]{email}[/bold]...")

    try:
        process = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = process.communicate(input=input_str)

        if process.returncode == 0:
            console.print("[green]Admin user created successfully.[/green]")
        else:
            if "Email has already been taken" in stdout or "Email has already been taken" in stderr:
                console.print("[yellow]User already exists. Skipping creation.[/yellow]")
            else:
                console.print("[red]Failed to create user.[/red]")
                if stderr:
                    console.print(stderr)
                if stdout:
                    console.print(stdout)

    except Exception as e:
        console.print(f"[red]Error creating user: {e}[/red]")


def start_postal_services():
    """Start postal."""
    console.print(Panel("Starting Postal", style="bold blue"))
    run_command(["postal", "start"], sudo=True)
    console.print("[green]Postal started.[/green]")
    run_command(["postal", "status"], sudo=True, check=False)


def setup_caddy():
    """Run Caddy."""
    console.print(Panel("Setting up Caddy", style="bold blue"))

    res = run_command(["docker", "ps", "-a", "-q", "-f", "name=postal-caddy"])
    if res.stdout.strip():
        console.print("[yellow]Caddy container already exists.[/yellow]")
        return

    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        "postal-caddy",
        "--restart",
        "always",
        "--network",
        "host",
        "-v",
        "/opt/postal/config/Caddyfile:/etc/caddy/Caddyfile",
        "-v",
        "/opt/postal/caddy-data:/data",
        "caddy",
    ]
    run_command(cmd)
    console.print("[green]Caddy started.[/green]")


@app.command()
def main(
    domain: str = typer.Option("postal.example.com", help="The domain for your Postal installation"),
    db_password: str = typer.Option("postal", help="Password for the MariaDB database"),
    admin_email: str = typer.Option("admin@example.com", help="Email for the admin user"),
    admin_password: str = typer.Option("admin123", help="Password for the admin user"),
    skip_user_creation: bool = typer.Option(False, help="Skip admin user creation"),
    force_cleanup: bool = typer.Option(False, help="Force cleanup of existing installation without prompting"),
):
    """
    Automated Postal Installation Script.
    """
    console.print(Markdown("# Postal Installer"))

    ensure_sudo()

    # Check if yaml is actually usable (double check)
    if "yaml" not in sys.modules:
        console.print("[bold red]PyYAML is strictly required. Please install it.[/bold red]")
        raise typer.Exit(1)

    check_and_cleanup(force_cleanup)

    check_system_requirements()
    check_docker()
    install_system_utils()

    setup_postal_repo()
    setup_database(db_password)

    # Check for port conflict for Postal Web (default 5000) BEFORE bootstrapping
    target_web_port = find_free_port(5000)
    if target_web_port != 5000:
        console.print(f"[yellow]Port 5000 is occupied. Using internal port {target_web_port}.[/yellow]")

    # Bootstrap and configure Postal with correct settings
    bootstrap_postal(domain, db_password, target_web_port)

    # Setup Caddy Config (Handles TLS internal + Port)
    setup_caddy_config(domain, target_web_port)

    console.print(Panel("Initializing Postal Database", style="bold blue"))
    run_command(["postal", "initialize"], sudo=True)

    if not skip_user_creation:
        create_initial_user(admin_email, admin_password, "Admin", "User")

    start_postal_services()
    setup_caddy()

    update_hosts_file(domain)

    console.print(
        Panel(
            f"[bold green]Installation Complete![/bold green]\n\n"
            f"URL: https://{domain}\n"
            f"Admin Email: {admin_email}\n"
            f"Admin Password: {admin_password}\n\n"
            f"Internal Web Port: {target_web_port}\n"
            f"Configuration: Postal v3 format (version: 2)\n\n"
            f"[bold cyan]Next Steps:[/bold cyan]\n"
            f"  1. Access the web UI at https://{domain}\n"
            f"  2. Create an organization and mail server\n"
            f"  3. Generate SMTP/API credentials\n"
            f"  4. For external relay (Gmail), see GMAIL_RELAY_LIMITATION.md\n\n"
            f"[dim]Note:[/dim] Caddy handles TLS. Accept self-signed cert in browser.",
            title="Success",
        )
    )


@app.command()
def add_relay(
    host: str = typer.Option(..., help="SMTP Relay Hostname (e.g., smtp.gmail.com)"),
    port: int = typer.Option(587, help="SMTP Port"),
    username: str = typer.Option("", help="SMTP Username (leave empty if none)"),
    password: str = typer.Option("", help="SMTP Password (leave empty if none)"),
    ssl_mode: str = typer.Option("StartTLS", help="SSL Mode (StartTLS, TLS, SSL, or None)"),
    force_ipv4: bool = typer.Option(True, help="Force IPv4 resolution to avoid IPv6 connectivity issues"),
    skip_ipv4_resolution: bool = typer.Option(False, help="Skip IPv4 resolution and use hostname as-is"),
):
    """
    Add an upstream SMTP relay to the Postal configuration.

    By default, hostnames are resolved to IPv4 addresses to avoid IPv6 connectivity
    issues in Docker containers. Use --skip-ipv4-resolution to disable this behavior.
    """
    import urllib.parse

    console.print(Panel("Adding Upstream SMTP Relay", style="bold blue"))
    ensure_sudo()

    config_path = "/opt/postal/config/postal.yml"
    if not os.path.exists(config_path):
        console.print(f"[bold red]Configuration file not found at {config_path}. Is Postal installed?[/bold red]")
        raise typer.Exit(1)

    # Resolve hostname to IPv4 to bypass potential IPv6 routing issues in Docker
    final_host = host
    is_ipv4 = False
    ipv6_addresses: list[str] = []

    if skip_ipv4_resolution:
        console.print("[yellow]Skipping IPv4 resolution as requested. Using hostname as-is.[/yellow]")
        final_host = host
        is_ipv4 = is_valid_ipv4(host)
    elif force_ipv4:
        console.print(f"[dim]Resolving '{host}' to IPv4 address...[/dim]")
        final_host, is_ipv4, ipv6_addresses = resolve_to_ipv4(host)

        if not is_ipv4:
            console.print(
                Panel(
                    "[bold red]IPv4 Resolution Failed![/bold red]\n\n"
                    f"Could not resolve '{host}' to an IPv4 address.\n\n"
                    "[bold]Options:[/bold]\n"
                    "  1. Manually specify an IPv4 address: --host <ip_address>\n"
                    "  2. Skip resolution (may cause issues): --skip-ipv4-resolution\n"
                    "  3. Check your DNS configuration and network connectivity\n\n"
                    f"[dim]IPv6 addresses found: {', '.join(ipv6_addresses) if ipv6_addresses else 'None'}[/dim]",
                    title="Error",
                    style="red",
                )
            )
            raise typer.Exit(1)

        # Display summary of resolution
        if final_host != host:
            console.print(f"[green]Using IPv4 address: {final_host} (resolved from {host})[/green]")
    else:
        # Just check if it's already an IP
        is_ipv4 = is_valid_ipv4(host)
        final_host = host

    # Validate and normalize SSL mode according to Postal documentation
    # Postal docs show lowercase: starttls, tls, none
    ssl_mode_lower = ssl_mode.lower()
    valid_ssl_modes = {"starttls", "tls", "ssl", "none"}

    if ssl_mode_lower not in valid_ssl_modes:
        console.print(
            Panel(
                f"[bold red]Invalid SSL mode: {ssl_mode}[/bold red]\n\n"
                f"Valid values are: {', '.join(sorted(valid_ssl_modes))}\n\n"
                "Note: 'ssl' is treated as 'tls' for port 465 (SMTPS).",
                title="Error",
                style="red",
            )
        )
        raise typer.Exit(1)

    # Normalize SSL mode for URL (Postal uses lowercase in URL)
    # Map 'ssl' to 'tls' since port 465 uses implicit TLS
    url_ssl_mode = "tls" if ssl_mode_lower == "ssl" else ssl_mode_lower

    # URL-encode credentials for the relay string (if provided)
    # Note: Postal doesn't officially support credentials in URL, but we allow it for testing
    safe_user = urllib.parse.quote_plus(username) if username else ""
    safe_pass = urllib.parse.quote_plus(password) if password else ""
    auth_part = f"{safe_user}:{safe_pass}@" if safe_user or safe_pass else ""

    # Build the relay string in Postal's expected format
    # Format: smtp://[user:pass@]host:port?ssl_mode=mode
    # Postal docs show lowercase ssl_mode values
    relay_str = f"smtp://{auth_part}{final_host}:{port}?ssl_mode={url_ssl_mode}"

    # Display the relay config (with password masked)
    display_relay = relay_str.replace(safe_pass, "***") if safe_pass else relay_str
    console.print(f"Relay URL: [cyan]{display_relay}[/cyan]")

    # Validate relay URL format
    try:
        from urllib.parse import urlparse, parse_qs

        parsed = urlparse(relay_str)
        if parsed.scheme != "smtp":
            raise ValueError("Scheme must be 'smtp'")
        if not parsed.hostname:
            raise ValueError("Hostname is required")
        if not parsed.port:
            raise ValueError("Port is required")

        # Check ssl_mode parameter
        query_params = parse_qs(parsed.query)
        if "ssl_mode" not in query_params:
            raise ValueError("ssl_mode parameter is required")

        console.print("[green]✓ Relay URL format validated[/green]")
    except Exception as e:
        console.print(f"[yellow]Warning: Relay URL validation issue: {e}[/yellow]")

    # Warning about authenticated relays
    if username or password:
        console.print(
            Panel(
                "[bold yellow]⚠️  WARNING: Authenticated Relays May Not Work[/bold yellow]\n\n"
                "Postal's `smtp_relays` does NOT officially support embedded credentials.\n"
                "The format `smtp://user:pass@host:port` is not documented and may fail.\n\n"
                "[bold]For Gmail/authenticated relays, consider:[/bold]\n"
                "  1. Use Postfix as local authenticated relay (see GMAIL_RELAY_LIMITATION.md)\n"
                "  2. Use a provider with IP whitelisting (SendGrid, Mailgun, etc.)\n"
                "  3. Test if this format works (may work unofficially)\n\n"
                "[dim]If delivery fails, check Postal logs for authentication errors.[/dim]",
                title="Authentication Limitation",
                style="yellow",
            )
        )

    try:
        # Update smtp_client settings to ensure TLS is enabled globally if using StartTLS or TLS
        # Postal uses PascalCase for smtp_client.tls_mode (StartTLS, TLS, None)
        # But lowercase for relay URL ssl_mode parameter
        tls_map = {"starttls": "StartTLS", "tls": "TLS", "ssl": "TLS", "none": "None"}
        normalized_mode = tls_map.get(ssl_mode_lower, "None")

        if normalized_mode != "None":
            console.print(f"[dim]Updating global SMTP client TLS mode: {normalized_mode}[/dim]")
            update_postal_config_yaml({"smtp_client.tls_mode": normalized_mode})

        # Read the file
        temp_path = "/tmp/postal.yml.tmp"
        run_command(["sudo", "cp", config_path, temp_path])
        run_command(["sudo", "chmod", "666", temp_path])

        with open(temp_path) as f:
            config = yaml.safe_load(f) or {}

        # Verify configuration version
        if config.get("version") != 2:
            console.print("[yellow]Warning: Configuration version is not 2. Postal v3 requires version 2.[/yellow]")
            if not Confirm.ask("Continue anyway?", default=True):
                raise typer.Exit(1)

        # Ensure 'postal' key exists (v2 config)
        if "postal" not in config:
            config["postal"] = {}

        # Ensure smtp_relays exists under postal block for V2
        # Note: Docs say "smtp_relays changes to postal.smtp_relays"
        if "smtp_relays" not in config["postal"]:
            config["postal"]["smtp_relays"] = []

        # Check for duplicate relays
        existing_relays = config["postal"]["smtp_relays"]

        # Extract host:port from our relay URL for comparison
        # Compare normalized versions (without credentials for duplicate detection)
        relay_base = f"smtp://{final_host}:{port}?ssl_mode={url_ssl_mode}"

        # Check if this relay already exists (compare base URL without credentials)
        for existing in existing_relays:
            # Parse existing relay to get base URL
            try:
                from urllib.parse import urlparse

                existing_parsed = urlparse(existing)
                existing_base = f"smtp://{existing_parsed.hostname}:{existing_parsed.port}?ssl_mode={url_ssl_mode}"

                # Compare base URLs (host:port:ssl_mode) - credentials may differ
                if relay_base == existing_base:
                    # Mask password in display
                    display_existing = existing
                    if safe_pass:
                        # Try to mask password in existing URL too
                        import re

                        display_existing = re.sub(r":([^:@]+)@", r":***@", existing)

                    console.print(
                        Panel(
                            f"[bold yellow]Similar relay already exists![/bold yellow]\n\n"
                            f"Existing: {display_existing}\n"
                            f"New:      {display_relay}\n\n"
                            "Same host:port:ssl_mode combination detected.\n"
                            "Use 'clear-relays' to remove all relays, or manually edit postal.yml",
                            title="Duplicate Relay",
                            style="yellow",
                        )
                    )
                    if not Confirm.ask("Add anyway (will create duplicate)?", default=False):
                        console.print("[dim]Aborted.[/dim]")
                        raise typer.Exit(0)
            except Exception:
                # If parsing fails, do simple string comparison
                if f"{final_host}:{port}" in existing:
                    console.print(f"[yellow]Warning: Found similar relay: {existing}[/yellow]")

        # Append new relay string
        config["postal"]["smtp_relays"].append(relay_str)
        console.print(f"[green]Added relay to configuration (total: {len(config['postal']['smtp_relays'])})[/green]")

        with open(temp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        # Move back
        run_command(["sudo", "mv", temp_path, config_path])
        console.print("[green]Configuration updated.[/green]")

        console.print("Restarting Postal to apply changes...")
        run_command(["postal", "restart"], sudo=True)
        console.print("[green]Postal restarted successfully.[/green]")

    except Exception as e:
        console.print(f"[bold red]Failed to update configuration: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def add_postfix_relay(
    postfix_host: str = typer.Option("127.0.0.1", help="Postfix hostname (default: localhost)"),
    postfix_port: int = typer.Option(
        2525, help="Postfix port (default: 2525 to avoid conflict with Postal on port 25)"
    ),
):
    """
    Configure Postal to use local Postfix as SMTP relay.

    This is the recommended way to use Gmail with Postal, as Postfix handles
    Gmail authentication and Postal just relays to localhost.

    Default port is 2525 because Postal typically runs on port 25.

    Prerequisites:
    - Postfix must be installed and configured for Gmail
    - Use install_postfix.py to set up Postfix first
    """
    console.print(Panel("Configuring Postal to Use Postfix Relay", style="bold blue"))
    ensure_sudo()

    # Check if Postfix is running
    postfix_running = False
    if shutil.which("systemctl"):
        try:
            result = run_command(["systemctl", "is-active", "postfix"], sudo=True, check=False)
            postfix_running = result.returncode == 0
        except Exception:
            pass

    if not postfix_running:
        console.print(
            Panel(
                "[bold yellow]Postfix may not be running![/bold yellow]\n\n"
                "Please ensure Postfix is installed and configured first:\n"
                "  [cyan]uv run src/gishant_scripts/postal/install_postfix.py main \\[/cyan]\n"
                "  [cyan]  --gmail-address your@gmail.com --app-password your-app-password[/cyan]\n\n"
                "Then verify Postfix is running:\n"
                "  [cyan]sudo systemctl status postfix[/cyan]",
                title="Warning",
                style="yellow",
            )
        )
        if not Confirm.ask("Continue anyway?", default=False):
            raise typer.Exit(0)

    # Test Postfix connectivity
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((postfix_host, postfix_port))
        sock.close()
        if result != 0:
            console.print(f"[yellow]Warning: Could not connect to Postfix at {postfix_host}:{postfix_port}[/yellow]")
            if not Confirm.ask("Continue anyway?", default=False):
                raise typer.Exit(0)
        else:
            console.print(f"[green]✓ Postfix is reachable at {postfix_host}:{postfix_port}[/green]")
    except Exception as e:
        console.print(f"[yellow]Could not test Postfix connectivity: {e}[/yellow]")

    # Add relay using the existing add_relay logic
    console.print(f"\n[dim]Adding Postfix relay: {postfix_host}:{postfix_port}[/dim]")

    # Use the add_relay function's logic but simplified for localhost
    config_path = "/opt/postal/config/postal.yml"
    if not os.path.exists(config_path):
        console.print(f"[bold red]Configuration file not found at {config_path}. Is Postal installed?[/bold red]")
        raise typer.Exit(1)

    relay_str = f"smtp://{postfix_host}:{postfix_port}?ssl_mode=none"

    try:
        temp_path = "/tmp/postal.yml.tmp"
        run_command(["sudo", "cp", config_path, temp_path])
        run_command(["sudo", "chmod", "666", temp_path])

        with open(temp_path) as f:
            config = yaml.safe_load(f) or {}

        # Verify configuration version
        if config.get("version") != 2:
            console.print("[yellow]Warning: Configuration version is not 2. Postal v3 requires version 2.[/yellow]")

        # Ensure 'postal' key exists
        if "postal" not in config:
            config["postal"] = {}

        # Ensure smtp_relays exists
        if "smtp_relays" not in config["postal"]:
            config["postal"]["smtp_relays"] = []

        # Check for duplicate
        existing_relays = config["postal"]["smtp_relays"]
        for existing in existing_relays:
            if f"{postfix_host}:{postfix_port}" in existing:
                console.print(
                    Panel(
                        f"[bold yellow]Postfix relay already configured![/bold yellow]\n\n"
                        f"Found: {existing}\n\n"
                        "Use 'clear-relays' to remove all relays first if you want to reconfigure.",
                        title="Duplicate Relay",
                        style="yellow",
                    )
                )
                if not Confirm.ask("Add anyway?", default=False):
                    raise typer.Exit(0)

        # Add relay
        config["postal"]["smtp_relays"].append(relay_str)

        with open(temp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        run_command(["sudo", "mv", temp_path, config_path])
        console.print("[green]✓ Postfix relay added to Postal configuration.[/green]")

        console.print("Restarting Postal to apply changes...")
        run_command(["postal", "restart"], sudo=True)
        console.print("[green]Postal restarted successfully.[/green]")

        console.print(
            Panel(
                "[bold green]Postfix Relay Configured![/bold green]\n\n"
                f"Postal is now configured to relay through Postfix at {postfix_host}:{postfix_port}.\n\n"
                "[bold]Email Flow:[/bold]\n"
                "  Postal → localhost:25 (Postfix) → smtp.gmail.com:465 (Gmail)\n\n"
                "[bold]Next Steps:[/bold]\n"
                "  1. Test email sending via Postal\n"
                "  2. Check Postal logs: [cyan]docker logs postal-worker-1[/cyan]\n"
                "  3. Check Postfix logs: [cyan]sudo tail -f /var/log/mail.log[/cyan]",
                title="Success",
            )
        )

    except Exception as e:
        console.print(f"[bold red]Failed to update configuration: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def setup_tls(
    cert_path: str = typer.Option(..., help="Path to your .crt or .pem certificate file"),
    key_path: str = typer.Option(..., help="Path to your .key private key file"),
):
    """
    Configure Custom SSL Certificates for Postal (SMTP) and Caddy (Web).
    """
    console.print(Panel("Setting up Custom TLS Certificates", style="bold blue"))
    ensure_sudo()

    cert_path = os.path.abspath(cert_path)
    key_path = os.path.abspath(key_path)

    if not os.path.exists(cert_path) or not os.path.exists(key_path):
        console.print("[bold red]Certificate or Key file not found![/bold red]")
        raise typer.Exit(1)

    # Use /opt/postal/config/ as the base for keys, as per docs
    target_cert = "/opt/postal/config/smtp.cert"
    target_key = "/opt/postal/config/smtp.key"

    console.print(f"Copying certificates to {target_cert} & {target_key}...")
    run_command(["cp", cert_path, target_cert], sudo=True)
    run_command(["cp", key_path, target_key], sudo=True)

    # Ensure readable
    run_command(["chmod", "644", target_cert], sudo=True)
    run_command(["chmod", "600", target_key], sudo=True)

    # 1. Update Postal Config for SMTP TLS
    console.print("Enabling SMTP TLS in postal.yml...")

    try:
        # We need to update nested keys safely
        # Just use update_postal_config_yaml but need to ensure it handles nested keys or just pass flat
        # My update_postal_config_yaml implementation splits by dot.
        # Docs say: smtp_server: ... tls_enabled: true
        # So "smtp_server.tls_enabled" work.

        update_postal_config_yaml(
            {
                "smtp_server.tls_enabled": True,
                # Docs say: tls_certificate_path: other/path/to/cert/within/container
                # We are putting it in /opt/postal/config/smtp.cert
                # Default mounts usually map /opt/postal/config to /config in container
                # So path inside container is `/config/smtp.cert`
                "smtp_server.tls_certificate_path": "/config/smtp.cert",
                "smtp_server.tls_private_key_path": "/config/smtp.key",
            }
        )
    except Exception as e:
        console.print(f"[bold red]Failed to update postal config: {e}[/bold red]")

    # 2. Re-create Caddy Container with Volume Mounts
    console.print("Re-creating Caddy container with custom certs...")

    # Stop existing
    run_command(["docker", "rm", "-f", "postal-caddy"], sudo=True, check=False)

    # Run new with /certs mount
    # We mount /opt/postal/config to /certs in Caddy to access the same files cleanly
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        "postal-caddy",
        "--restart",
        "always",
        "--network",
        "host",
        "-v",
        "/opt/postal/config/Caddyfile:/etc/caddy/Caddyfile",
        "-v",
        "/opt/postal/caddy-data:/data",
        "-v",
        "/opt/postal/config:/certs:ro",
        "caddy",
    ]
    run_command(cmd)

    # 3. Update Caddyfile to use these certs
    console.print("Updating Caddyfile to use provided certificates...")

    sed_cmd = ["sed", "-i", "s|tls internal|tls /certs/smtp.cert /certs/smtp.key|g", "/opt/postal/config/Caddyfile"]
    run_command(sed_cmd, sudo=True)

    console.print("Reloading Caddy...")
    run_command(["docker", "restart", "postal-caddy"], sudo=True)

    console.print("Restarting Postal to apply SMTP TLS settings...")
    run_command(["postal", "restart"], sudo=True)

    console.print("[bold green]TLS Configuration Complete![/bold green]")


@app.command()
def clear_relays():
    """
    Remove ALL upstream SMTP relays from configuration.
    Use this if you have duplicate or incorrect relays.
    """
    console.print(Panel("Clearing Upstream SMTP Relays", style="bold red"))
    ensure_sudo()

    config_path = "/opt/postal/config/postal.yml"
    if not os.path.exists(config_path):
        console.print(f"[bold red]Configuration file not found at {config_path}.[/bold red]")
        raise typer.Exit(1)

    try:
        temp_path = "/tmp/postal.yml.tmp"
        run_command(["sudo", "cp", config_path, temp_path])
        run_command(["sudo", "chmod", "666", temp_path])

        with open(temp_path) as f:
            config = yaml.safe_load(f) or {}

        if "postal" in config and "smtp_relays" in config["postal"]:
            count = len(config["postal"]["smtp_relays"])
            console.print(f"Found {count} relays. Removing...")
            del config["postal"]["smtp_relays"]
        else:
            console.print("No relays found in configuration.")

        with open(temp_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)

        run_command(["sudo", "mv", temp_path, config_path])
        console.print("[green]Relays cleared.[/green]")

        console.print("Restarting Postal...")
        run_command(["postal", "restart"], sudo=True)
        console.print("[green]Postal restarted.[/green]")

    except Exception as e:
        console.print(f"[bold red]Failed to clear relays: {e}[/bold red]")


@app.command()
def test_relay(
    host: str = typer.Option(..., help="SMTP Relay Hostname (e.g., smtp.gmail.com)"),
    port: int = typer.Option(465, help="SMTP Port to test"),
    timeout: int = typer.Option(10, help="Connection timeout in seconds"),
):
    """
    Test connectivity to an SMTP relay host.

    This command helps diagnose connectivity issues by:
    - Resolving the hostname to both IPv4 and IPv6 addresses
    - Testing TCP connectivity to each resolved address
    - Showing which IP versions are reachable from your system
    """
    import socket

    console.print(Panel(f"Testing SMTP Relay: {host}:{port}", style="bold blue"))

    # Resolve IPv4 addresses
    ipv4_addresses: list[str] = []
    try:
        addrinfo = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        ipv4_addresses = list(set(info[4][0] for info in addrinfo))
    except socket.gaierror as e:
        console.print(f"[yellow]IPv4 resolution failed: {e}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error resolving IPv4: {e}[/red]")

    # Resolve IPv6 addresses
    ipv6_addresses: list[str] = []
    try:
        addrinfo = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
        ipv6_addresses = list(set(info[4][0] for info in addrinfo))
    except socket.gaierror as e:
        console.print(f"[yellow]IPv6 resolution failed: {e}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error resolving IPv6: {e}[/red]")

    # Display resolved addresses
    console.print("\n[bold]Resolved Addresses:[/bold]")
    console.print(f"  IPv4: {', '.join(ipv4_addresses) if ipv4_addresses else '[red]None[/red]'}")
    console.print(f"  IPv6: {', '.join(ipv6_addresses) if ipv6_addresses else '[dim]None[/dim]'}")

    # Test IPv4 connectivity
    console.print("\n[bold]Testing IPv4 Connectivity:[/bold]")
    ipv4_success = False
    for addr in ipv4_addresses:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((addr, port))
            sock.close()

            if result == 0:
                console.print(f"  [green]{addr}:{port} - CONNECTED[/green]")
                ipv4_success = True
            else:
                console.print(f"  [red]{addr}:{port} - FAILED (error code: {result})[/red]")
        except socket.timeout:
            console.print(f"  [red]{addr}:{port} - TIMEOUT[/red]")
        except Exception as e:
            console.print(f"  [red]{addr}:{port} - ERROR: {e}[/red]")

    if not ipv4_addresses:
        console.print("  [dim]No IPv4 addresses to test[/dim]")

    # Test IPv6 connectivity
    console.print("\n[bold]Testing IPv6 Connectivity:[/bold]")
    ipv6_success = False
    for addr in ipv6_addresses:
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((addr, port, 0, 0))
            sock.close()

            if result == 0:
                console.print(f"  [green][{addr}]:{port} - CONNECTED[/green]")
                ipv6_success = True
            else:
                console.print(f"  [red][{addr}]:{port} - FAILED (error code: {result})[/red]")
        except socket.timeout:
            console.print(f"  [red][{addr}]:{port} - TIMEOUT[/red]")
        except OSError as e:
            if "Network is unreachable" in str(e):
                console.print(f"  [red][{addr}]:{port} - NETWORK UNREACHABLE (IPv6 not available)[/red]")
            else:
                console.print(f"  [red][{addr}]:{port} - ERROR: {e}[/red]")
        except Exception as e:
            console.print(f"  [red][{addr}]:{port} - ERROR: {e}[/red]")

    if not ipv6_addresses:
        console.print("  [dim]No IPv6 addresses to test[/dim]")

    # Summary and recommendations
    console.print("\n[bold]Summary:[/bold]")
    if ipv4_success and not ipv6_success:
        console.print(
            Panel(
                "[green]IPv4 connectivity works![/green]\n\n"
                "[yellow]IPv6 connectivity failed.[/yellow] This is common in Docker environments.\n\n"
                "[bold]Recommendation:[/bold] Use the default IPv4 resolution when adding relays:\n"
                f"  [cyan]add-relay --host {host} --port {port} ...[/cyan]\n\n"
                "The script will automatically resolve to IPv4 and avoid IPv6 issues.",
                title="Diagnosis",
                style="green",
            )
        )
    elif ipv4_success and ipv6_success:
        console.print(
            Panel(
                "[green]Both IPv4 and IPv6 connectivity work![/green]\n\n"
                "Your system has full network connectivity.\n"
                "However, for reliability in Docker, IPv4 is still recommended.",
                title="Diagnosis",
                style="green",
            )
        )
    elif not ipv4_success and ipv6_success:
        console.print(
            Panel(
                "[yellow]Only IPv6 connectivity works![/yellow]\n\n"
                "IPv4 failed but IPv6 succeeded. This is unusual.\n"
                "Check your network configuration or firewall rules.",
                title="Diagnosis",
                style="yellow",
            )
        )
    else:
        console.print(
            Panel(
                "[bold red]No connectivity to the relay host![/bold red]\n\n"
                "Both IPv4 and IPv6 connections failed.\n\n"
                "[bold]Possible causes:[/bold]\n"
                "  - Firewall blocking outbound connections on port " + str(port) + "\n"
                "  - Network connectivity issues\n"
                "  - Incorrect hostname\n"
                "  - DNS resolution problems\n\n"
                "[bold]Try:[/bold]\n"
                "  - Check if port " + str(port) + " is allowed outbound\n"
                "  - Verify the hostname is correct\n"
                "  - Test with a different network",
                title="Diagnosis",
                style="red",
            )
        )


def analyze_relay_string(relay_str: str) -> dict[str, Any]:
    """
    Parse and analyze a relay string for potential issues.

    Returns a dict with host, port, is_ipv4, is_hostname, and any warnings.
    """
    import re
    import socket
    from urllib.parse import urlparse

    result: dict[str, Any] = {
        "original": relay_str,
        "host": None,
        "port": None,
        "is_ipv4": False,
        "is_ipv6": False,
        "is_hostname": False,
        "warnings": [],
    }

    try:
        # Parse the relay URL
        parsed = urlparse(relay_str)

        # Extract host (handle IPv6 in brackets)
        host = parsed.hostname or ""
        port = parsed.port

        result["host"] = host
        result["port"] = port

        # Check if it's an IPv4 address
        try:
            socket.inet_aton(host)
            if ":" not in host:
                result["is_ipv4"] = True
        except OSError:
            pass

        # Check if it's an IPv6 address
        try:
            socket.inet_pton(socket.AF_INET6, host)
            result["is_ipv6"] = True
            result["warnings"].append("Using IPv6 address - may cause connectivity issues in Docker")
        except OSError:
            pass

        # If not an IP, it's a hostname
        if not result["is_ipv4"] and not result["is_ipv6"]:
            result["is_hostname"] = True
            result["warnings"].append("Using hostname instead of IP - Postal may resolve to IPv6 and fail")

    except Exception as e:
        result["warnings"].append(f"Could not parse relay string: {e}")

    return result


@app.command()
def show_config(
    analyze_relays: bool = typer.Option(True, help="Analyze SMTP relays for potential issues"),
):
    """
    Show current Postal configuration with relay analysis.

    Displays the configuration and analyzes SMTP relays for potential IPv6/connectivity issues.
    """
    import socket

    console.print(Panel("Current Postal Configuration", style="bold blue"))
    ensure_sudo()

    config_path = "/opt/postal/config/postal.yml"
    try:
        # We use cat via sudo to read it
        result = run_command(["sudo", "cat", config_path], check=True)
        config = yaml.safe_load(result.stdout)

        # Redact some secrets for display
        if "main_db" in config:
            config["main_db"]["password"] = "***"
        if "message_db" in config:
            config["message_db"]["password"] = "***"

        # Redact passwords in relay strings
        if "postal" in config and "smtp_relays" in config["postal"]:
            relays = config["postal"]["smtp_relays"]
            redacted_relays = []
            for relay in relays:
                # Redact password portion (between : and @ after //)
                import re

                redacted = re.sub(r"(://[^:]*:)[^@]*(@)", r"\1***\2", relay)
                redacted_relays.append(redacted)
            config["postal"]["smtp_relays"] = redacted_relays

        console.print(yaml.dump(config, default_flow_style=False))

        # Analyze SMTP relays if enabled
        if analyze_relays:
            # Re-read original config to analyze actual relay strings
            result = run_command(["sudo", "cat", config_path], check=True)
            original_config = yaml.safe_load(result.stdout)

            if "postal" in original_config and "smtp_relays" in original_config["postal"]:
                relays = original_config["postal"]["smtp_relays"]

                if relays:
                    console.print("\n")
                    console.print(Panel("SMTP Relay Analysis", style="bold cyan"))

                    all_ok = True
                    for i, relay in enumerate(relays, 1):
                        analysis = analyze_relay_string(relay)

                        # Determine status color
                        if analysis["is_ipv4"]:
                            status = "[green]OK (IPv4)[/green]"
                        elif analysis["is_ipv6"]:
                            status = "[yellow]Warning (IPv6)[/yellow]"
                            all_ok = False
                        elif analysis["is_hostname"]:
                            status = "[yellow]Warning (Hostname)[/yellow]"
                            all_ok = False
                        else:
                            status = "[red]Unknown[/red]"
                            all_ok = False

                        console.print(f"\n[bold]Relay {i}:[/bold] {status}")
                        console.print(f"  Host: {analysis['host']}")
                        console.print(f"  Port: {analysis['port']}")

                        # Show warnings
                        for warning in analysis["warnings"]:
                            console.print(f"  [yellow]Warning: {warning}[/yellow]")

                        # If it's a hostname, try to show what it would resolve to
                        if analysis["is_hostname"] and analysis["host"]:
                            console.print(f"  [dim]Attempting to resolve '{analysis['host']}'...[/dim]")
                            try:
                                # Try IPv4
                                addrinfo = socket.getaddrinfo(
                                    analysis["host"], None, socket.AF_INET, socket.SOCK_STREAM
                                )
                                ipv4_addrs = list(set(info[4][0] for info in addrinfo))
                                if ipv4_addrs:
                                    console.print(f"    IPv4: {', '.join(ipv4_addrs)}")
                            except Exception:
                                console.print("    IPv4: [red]Resolution failed[/red]")

                            try:
                                # Try IPv6
                                addrinfo = socket.getaddrinfo(
                                    analysis["host"], None, socket.AF_INET6, socket.SOCK_STREAM
                                )
                                ipv6_addrs = list(set(info[4][0] for info in addrinfo))
                                if ipv6_addrs:
                                    console.print(f"    IPv6: {', '.join(ipv6_addrs[:2])}")
                            except Exception:
                                pass

                    # Summary
                    console.print("\n")
                    if all_ok:
                        console.print(
                            Panel(
                                "[green]All relays are using IPv4 addresses.[/green]\n"
                                "This is the recommended configuration for Docker environments.",
                                title="Relay Status",
                                style="green",
                            )
                        )
                    else:
                        console.print(
                            Panel(
                                "[yellow]Some relays may have connectivity issues.[/yellow]\n\n"
                                "Relays using hostnames or IPv6 addresses may fail in Docker.\n\n"
                                "[bold]To fix:[/bold]\n"
                                "  1. Clear existing relays: [cyan]clear-relays[/cyan]\n"
                                "  2. Re-add with IPv4 resolution: [cyan]add-relay --host smtp.gmail.com ...[/cyan]\n\n"
                                "The script will automatically resolve hostnames to IPv4 addresses.",
                                title="Relay Status",
                                style="yellow",
                            )
                        )
            else:
                console.print("\n[dim]No SMTP relays configured.[/dim]")

    except Exception as e:
        console.print(f"[bold red]Failed to read config: {e}[/bold red]")


@app.command()
def verify_access(
    url: str = typer.Option(..., help="URL to check"), timeout: int = typer.Option(5, help="Timeout in seconds")
):
    """
    Verify if a URL is accessible (e.g. checks if Caddy is serving).
    """
    try:
        response = requests.get(url, timeout=timeout, verify=False)
        console.print(f"Status Code: {response.status_code}")
        if response.status_code < 400:
            console.print(f"[green]Success: {url} is reachable.[/green]")
        else:
            console.print(f"[yellow]Warning: {url} returned {response.status_code}[/yellow]")
    except Exception as e:
        console.print(f"[red]Error reaching {url}: {e}[/red]")


if __name__ == "__main__":
    app()
