#!/usr/bin/env python3
import os
import sys
import subprocess
import shutil
import time
from typing import Optional, Dict, Any
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn

# Try to import yaml
try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Please run with 'uv run --with pyyaml ...'")
    sys.exit(1)

console = Console()
app = typer.Typer()

def run_command(command: list[str], shell: bool = False, check: bool = True, sudo: bool = False) -> subprocess.CompletedProcess:
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
            subprocess.check_call(['sudo', '-v'])
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
        "/opt/postal/install", # The repo itself
        "/usr/bin/postal"      # The symlink
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
        shutil.which("docker") and subprocess.run(["docker", "ps", "-a", "-q", "-f", "name=postal-mariadb"], capture_output=True).stdout.strip(),
        shutil.which("docker") and subprocess.run(["docker", "ps", "-a", "-q", "-f", "name=postal-caddy"], capture_output=True).stdout.strip()
    ]

    if any(indicators):
        console.print(Panel("[yellow]Existing Postal components detected.[/yellow]", style="yellow"))
        if force:
            perform_cleanup()
        else:
            if Confirm.ask("Do you want to [bold red]WIPE[/bold red] the existing installation and start fresh?", default=False):
                perform_cleanup()
            else:
                console.print("[dim]Proceeding with existing components (skipping creation steps if resources exist)...[/dim]")

def check_system_requirements():
    """Check basic system requirements."""
    console.print(Panel("Checking System Requirements", style="bold blue"))

    # Check RAM
    total_ram_gb = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / (1024.**3)
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
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
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
                console.print("[bold red]Could not detect package manager. Please install git, curl, jq manually.[/bold red]")
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
        "docker", "run", "-d",
        "--name", "postal-mariadb",
        "-p", "127.0.0.1:3306:3306",
        "--restart", "always",
        "-e", "MARIADB_DATABASE=postal",
        "-e", f"MARIADB_ROOT_PASSWORD={db_password}",
        "mariadb"
    ]
    run_command(cmd)
    console.print("[green]MariaDB container started.[/green]")
    console.print("Waiting for Database to initialize...")
    time.sleep(10)

def update_postal_config_yaml(updates: Dict[str, Any]):
    """Update postal.yml using PyYAML for robust handling."""
    config_path = "/opt/postal/config/postal.yml"
    console.print(f"Updating configuration in {config_path}...")

    try:
        # Read the file (requires sudo, so we copy it to temp, edit, move back)
        temp_path = "/tmp/postal.yml.tmp"
        run_command(["sudo", "cp", config_path, temp_path])
        run_command(["sudo", "chmod", "666", temp_path]) # make readable/writable

        with open(temp_path, 'r') as f:
            config = yaml.safe_load(f) or {}

        # Apply updates
        for key, value in updates.items():
            keys = key.split('.')
            current = config
            for i, k in enumerate(keys[:-1]):
                if k not in current:
                    current[k] = {}
                current = current[k]
            current[keys[-1]] = value

        with open(temp_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)

        # Move back
        run_command(["sudo", "mv", temp_path, config_path])

        console.print("[green]Configuration updated successfully (YAML).[/green]")

    except Exception as e:
        console.print(f"[bold red]Failed to update configuration YAML: {e}[/bold red]")
        sys.exit(1)


def bootstrap_postal(domain: str, db_password: str):
    """Bootstrap configuration and update it."""
    console.print(Panel("Bootstrapping Postal Configuration", style="bold blue"))

    if os.path.exists("/opt/postal/config/postal.yml"):
         console.print("[yellow]Configuration already exists. Skipping bootstrap.[/yellow]")
    else:
        run_command(["postal", "bootstrap", domain], sudo=True)
        console.print("[green]Configuration bootstrapped.[/green]")

    console.print("Updating database password in config...")

    # We use our new YAML updater
    update_postal_config_yaml({
        "main_db.password": db_password,
        "message_db.password": db_password
    })

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
        process = subprocess.Popen(['sudo', 'tee', '/opt/postal/config/Caddyfile'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        process.communicate(input=caddy_content)
        console.print("[green]Caddyfile configured successfully.[/green]")
    except Exception as e:
        console.print(f"[red]Failed to write Caddyfile: {e}[/red]")

def update_hosts_file(domain: str):
    """Add domain to /etc/hosts if not present."""
    console.print(Panel("Updating /etc/hosts", style="bold blue"))

    entry = f"127.0.0.1 {domain}"
    try:
        with open("/etc/hosts", "r") as f:
            content = f.read()

        if domain in content:
            console.print(f"/etc/hosts already contains {domain}.")
            return

        console.print(f"Adding '{entry}' to /etc/hosts...")
        # Use sudo tee -a with text=True to fix encoding issues
        cmd = ["sudo", "tee", "-a", "/etc/hosts"]
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            text=True
        )
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
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=input_str)

        if process.returncode == 0:
            console.print("[green]Admin user created successfully.[/green]")
        else:
            if "Email has already been taken" in stdout or "Email has already been taken" in stderr:
                console.print("[yellow]User already exists. Skipping creation.[/yellow]")
            else:
                console.print(f"[red]Failed to create user.[/red]")
                if stderr: console.print(stderr)
                if stdout: console.print(stdout)

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
        "docker", "run", "-d",
        "--name", "postal-caddy",
        "--restart", "always",
        "--network", "host",
        "-v", "/opt/postal/config/Caddyfile:/etc/caddy/Caddyfile",
        "-v", "/opt/postal/caddy-data:/data",
        "caddy"
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
    force_cleanup: bool = typer.Option(False, help="Force cleanup of existing installation without prompting")
):
    """
    Automated Postal Installation Script.
    """
    console.print(Markdown("# Postal Installer"))

    ensure_sudo()

    # Check if yaml is actually usable (double check)
    if 'yaml' not in sys.modules:
         console.print("[bold red]PyYAML is strictly required. Please install it.[/bold red]")
         raise typer.Exit(1)

    check_and_cleanup(force_cleanup)

    check_system_requirements()
    check_docker()
    install_system_utils()

    setup_postal_repo()
    setup_database(db_password)

    bootstrap_postal(domain, db_password)

    # Check for port conflict for Postal Web (default 5000)
    target_web_port = find_free_port(5000)
    if target_web_port != 5000:
        console.print(f"[yellow]Port 5000 is occupied. Using internal port {target_web_port}.[/yellow]")

    # Update Config for v3
    console.print(f"Updating Postal config (Bind 0.0.0.0, Port {target_web_port})...")
    updates = {
        "web_server.default_port": target_web_port,
        "web_server.default_bind_address": "0.0.0.0"
    }
    update_postal_config_yaml(updates)

    # Setup Caddy Config (Handles TLS internal + Port)
    setup_caddy_config(domain, target_web_port)

    console.print(Panel("Initializing Postal Database", style="bold blue"))
    run_command(["postal", "initialize"], sudo=True)

    if not skip_user_creation:
         create_initial_user(admin_email, admin_password, "Admin", "User")

    start_postal_services()
    setup_caddy()

    update_hosts_file(domain)

    console.print(Panel(
        f"[bold green]Installation Complete![/bold green]\n\n"
        f"URL: https://{domain}\n"
        f"Admin Email: {admin_email}\n"
        f"Admin Password: {admin_password}\n\n"
        f"Internal Web Port: {target_web_port}\n"
        f"[bold cyan]Note:[/bold cyan] Access the URL directly! Caddy handles the proxying.\n"
        f"If using Firefox, you might need to accept the self-signed certificate exception.",
        title="Success"
    ))

if __name__ == "__main__":
    app()
