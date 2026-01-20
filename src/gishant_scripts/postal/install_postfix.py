#!/usr/bin/env python3
"""
Postfix Installation and Configuration Script for Gmail SMTP Relay

This script sets up Postfix as an authenticated SMTP relay to Gmail,
which can then be used by Postal or other mail servers.

Based on: https://docs.postalserver.io and Postfix documentation
"""
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


def check_postfix_installed() -> bool:
    """Check if Postfix is already installed."""
    return shutil.which("postfix") is not None


def install_postfix_packages():
    """Install Postfix and required SASL packages."""
    console.print(Panel("Installing Postfix and Required Packages", style="bold blue"))

    # Detect package manager and OS type
    if shutil.which("apt"):
        # Debian/Ubuntu packages
        required_packages = ["postfix", "sasl2-bin", "libsasl2-modules"]
        optional_packages = ["mailutils"]  # Optional: for mail command testing
        pkg_manager = "apt"
    elif shutil.which("yum") or shutil.which("dnf"):
        # RHEL/Rocky Linux packages
        # cyrus-sasl provides SASL framework
        # cyrus-sasl-plain provides PLAIN/LOGIN authentication (needed for Gmail)
        required_packages = ["postfix", "cyrus-sasl", "cyrus-sasl-plain"]
        optional_packages = []  # mailx not available in Rocky Linux 9, skip it
        pkg_manager = "yum" if shutil.which("yum") else "dnf"
    else:
        console.print(
            "[bold red]Could not detect package manager. Please install postfix and SASL packages manually.[/bold red]"
        )
        raise typer.Exit(1)

    to_install = []

    # Check required packages
    for pkg in required_packages:
        if pkg == "postfix":
            if not shutil.which("postfix"):
                to_install.append(pkg)
        else:
            # For other packages, add to install list (package manager will handle if already installed)
            to_install.append(pkg)

    if not to_install:
        console.print("[green]All required packages are already installed.[/green]")
    else:
        console.print(f"Installing required packages: {', '.join(to_install)}")

        # Install required packages based on package manager
        if pkg_manager == "apt":
            run_command(["apt", "update"], sudo=True)
            # Use DEBIAN_FRONTEND=noninteractive to avoid prompts
            env = os.environ.copy()
            env["DEBIAN_FRONTEND"] = "noninteractive"
            run_command(
                ["apt", "install", "-y"] + to_install,
                sudo=True,
                check=True,
            )
        elif pkg_manager in ["yum", "dnf"]:
            run_command([pkg_manager, "install", "-y"] + to_install, sudo=True, check=True)
        else:
            console.print(
                "[bold red]Could not detect package manager. Please install postfix and SASL packages manually.[/bold red]"
            )
            raise typer.Exit(1)

        console.print("[green]Required packages installed successfully.[/green]")

    # Try to install optional packages (don't fail if unavailable)
    if optional_packages:
        optional_to_install = []
        for pkg in optional_packages:
            if pkg == "mailutils" and not shutil.which("mail"):
                optional_to_install.append(pkg)

        if optional_to_install:
            console.print(f"[dim]Attempting to install optional packages: {', '.join(optional_to_install)}[/dim]")
            try:
                if pkg_manager == "apt":
                    run_command(
                        ["apt", "install", "-y"] + optional_to_install,
                        sudo=True,
                        check=True,
                    )
                    console.print("[green]Optional packages installed successfully.[/green]")
                elif pkg_manager in ["yum", "dnf"]:
                    # For RHEL/Rocky, try but don't fail
                    result = run_command(
                        [pkg_manager, "install", "-y"] + optional_to_install,
                        sudo=True,
                        check=False,
                    )
                    if result.returncode == 0:
                        console.print("[green]Optional packages installed successfully.[/green]")
                    else:
                        console.print(
                            "[yellow]Optional packages not available (this is OK, not required for Postfix).[/yellow]"
                        )
            except Exception as e:
                console.print(
                    f"[yellow]Could not install optional packages (this is OK): {e}[/yellow]"
                )


def configure_postfix_gmail(
    gmail_address: str,
    app_password: str,
    relay_host: str = "smtp.gmail.com",
    relay_port: int = 465,
    listen_port: int = 2525,
):
    """
    Configure Postfix for Gmail SMTP relay with authentication.

    Args:
        gmail_address: Gmail email address (e.g., user@gmail.com)
        app_password: Gmail app password (16-character password)
        relay_host: SMTP relay hostname (default: smtp.gmail.com)
        relay_port: SMTP relay port (default: 465 for SMTPS)
        listen_port: Port for Postfix to listen on (default: 2525 to avoid conflict with Postal)
    """
    console.print(Panel("Configuring Postfix for Gmail Relay", style="bold blue"))

    postfix_main_cf = "/etc/postfix/main.cf"
    sasl_passwd = "/etc/postfix/sasl_passwd"

    # Stop Postfix if it's running (to avoid port conflicts)
    console.print("[dim]Stopping Postfix service if running...[/dim]")
    run_command(["systemctl", "stop", "postfix"], sudo=True, check=False)
    # Wait a moment for the port to be released
    time.sleep(2)

    # Backup existing configuration
    if os.path.exists(postfix_main_cf):
        backup_path = f"{postfix_main_cf}.backup.{int(time.time())}"
        run_command(["cp", postfix_main_cf, backup_path], sudo=True)
        console.print(f"[dim]Backed up existing config to {backup_path}[/dim]")

    # Create SASL password file
    console.print("Creating SASL password file...")
    sasl_content = f"[{relay_host}]:{relay_port}    {gmail_address}:{app_password}\n"

    # Write SASL password file
    with open("/tmp/sasl_passwd", "w") as f:
        f.write(sasl_content)

    # Move and secure the SASL password file
    run_command(["mv", "/tmp/sasl_passwd", sasl_passwd], sudo=True)
    run_command(["chmod", "600", sasl_passwd], sudo=True)
    run_command(["chown", "root:root", sasl_passwd], sudo=True)
    
    # Remove existing database file (always, to avoid permission issues)
    sasl_passwd_db = f"{sasl_passwd}.db"
    run_command(["rm", "-f", sasl_passwd_db], sudo=True, check=False)  # Don't fail if doesn't exist
    
    # Create the password map database
    run_command(["postmap", sasl_passwd], sudo=True)
    
    # Ensure the database file has correct permissions
    run_command(["chmod", "600", sasl_passwd_db], sudo=True)
    run_command(["chown", "root:root", sasl_passwd_db], sudo=True)

    console.print("[green]SASL password file created and secured.[/green]")

    # Read existing main.cf or create new
    if os.path.exists(postfix_main_cf):
        with open(postfix_main_cf, "r") as f:
            main_cf_content = f.read()
    else:
        main_cf_content = ""

    # Find CA certificate file (different locations on different distros)
    ca_cert_paths = [
        "/etc/ssl/certs/ca-certificates.crt",  # Debian/Ubuntu
        "/etc/pki/tls/certs/ca-bundle.crt",  # RHEL/CentOS/Rocky
        "/etc/ssl/cert.pem",  # Alpine
    ]
    ca_cert = None
    for path in ca_cert_paths:
        if os.path.exists(path):
            ca_cert = path
            break

    if not ca_cert:
        console.print("[yellow]Warning: Could not find CA certificate file. TLS may not work correctly.[/yellow]")
        ca_cert = "/etc/ssl/certs/ca-certificates.crt"  # Default, may not exist

    # Configuration settings for Gmail relay
    # Port 465 uses SMTPS (implicit TLS), Port 587 uses STARTTLS
    # inet_interfaces = 127.0.0.1 makes Postfix listen only on localhost
    base_config = {
        "inet_interfaces": "127.0.0.1",  # Listen only on localhost
        "relayhost": f"[{relay_host}]:{relay_port}",
        "smtp_use_tls": "yes",
        "smtp_sasl_auth_enable": "yes",
        "smtp_sasl_password_maps": "hash:/etc/postfix/sasl_passwd",
        "smtp_sasl_security_options": "noanonymous",
        "smtp_tls_CAfile": ca_cert,
    }
    
    if relay_port == 465:
        # SMTPS - implicit TLS (wrappermode)
        config_updates = {
            **base_config,
            "smtp_tls_wrappermode": "yes",  # Required for port 465 (SMTPS)
            "smtp_tls_security_level": "encrypt",
        }
    elif relay_port == 587:
        # STARTTLS - explicit TLS after connection
        config_updates = {
            **base_config,
            "smtp_tls_security_level": "may",  # STARTTLS - opportunistic
        }
    else:
        # Generic configuration
        config_updates = {
            **base_config,
            "smtp_tls_security_level": "encrypt",
        }

    if ca_cert and os.path.exists(ca_cert):
        console.print(f"[dim]Using CA certificate: {ca_cert}[/dim]")

    # Update or add configuration lines
    # Preserve existing config structure and comments
    lines = main_cf_content.split("\n")
    updated_lines = []
    config_keys_set = set()

    # Process existing lines
    for line in lines:
        stripped = line.strip()
        # Preserve comments and empty lines
        if not stripped or stripped.startswith("#"):
            updated_lines.append(line)
            continue

        # Check if this line sets one of our config keys
        # Handle both "key = value" and "key=value" formats
        key_found = False
        for key in config_updates.keys():
            # Match key at start of line (with optional spaces before =)
            if stripped.startswith(key) and ("=" in stripped or " " in stripped[:len(key)+5]):
                # Extract just the key part (before = or space)
                line_key = stripped.split("=")[0].split()[0] if "=" in stripped else stripped.split()[0]
                if line_key == key:
                    # Replace with our value
                    updated_lines.append(f"{key} = {config_updates[key]}")
                    config_keys_set.add(key)
                    key_found = True
                    break

        if not key_found:
            updated_lines.append(line)

    # Add any missing configuration at the end (before any trailing comments)
    # Add a section header if we're adding new config
    if config_keys_set != set(config_updates.keys()):
        # Find a good place to insert (after last non-comment line, or at end)
        insert_pos = len(updated_lines)
        for i in range(len(updated_lines) - 1, -1, -1):
            if updated_lines[i].strip() and not updated_lines[i].strip().startswith("#"):
                insert_pos = i + 1
                break

        # Add section comment
        if insert_pos < len(updated_lines):
            updated_lines.insert(insert_pos, "")
        updated_lines.insert(insert_pos, "# Gmail SMTP Relay Configuration (added by install_postfix.py)")

        # Add missing config
        for key, value in config_updates.items():
            if key not in config_keys_set:
                updated_lines.insert(insert_pos + 1, f"{key} = {value}")

    # Write updated configuration
    with open("/tmp/main.cf", "w") as f:
        f.write("\n".join(updated_lines))
        f.write("\n")

    run_command(["mv", "/tmp/main.cf", postfix_main_cf], sudo=True)
    run_command(["chown", "root:root", postfix_main_cf], sudo=True)
    run_command(["chmod", "644", postfix_main_cf], sudo=True)

    console.print("[green]Postfix main.cf updated.[/green]")

    # Configure master.cf to listen on the specified port
    # This is necessary when running alongside Postal (which uses port 25)
    master_cf = "/etc/postfix/master.cf"
    if listen_port != 25:
        console.print(f"[dim]Configuring Postfix to listen on port {listen_port}...[/dim]")
        
        # Read master.cf
        result = run_command(["cat", master_cf], sudo=True, check=False)
        if result.returncode == 0:
            master_content = result.stdout
            
            # Replace the smtp inet line to use our listen port
            # Original: smtp      inet  n       -       n       -       -       smtpd
            # New: 127.0.0.1:2525 inet  n       -       n       -       -       smtpd
            import re
            # Match the smtp inet line (handles various spacing)
            pattern = r'^smtp\s+inet\s+'
            replacement = f'127.0.0.1:{listen_port} inet  '
            
            new_master_content = re.sub(pattern, replacement, master_content, flags=re.MULTILINE)
            
            # Write updated master.cf
            with open("/tmp/master.cf", "w") as f:
                f.write(new_master_content)
            
            run_command(["mv", "/tmp/master.cf", master_cf], sudo=True)
            run_command(["chown", "root:root", master_cf], sudo=True)
            run_command(["chmod", "644", master_cf], sudo=True)
            
            console.print(f"[green]Postfix configured to listen on 127.0.0.1:{listen_port}[/green]")
        else:
            console.print(f"[yellow]Warning: Could not read {master_cf}, skipping port configuration.[/yellow]")

    console.print("[green]Postfix configuration updated.[/green]")


def test_postfix_configuration():
    """Test Postfix configuration for syntax errors."""
    console.print(Panel("Testing Postfix Configuration", style="bold blue"))

    try:
        result = run_command(["postfix", "check"], sudo=True)
        console.print("[green]✓ Postfix configuration is valid.[/green]")
        return True
    except subprocess.CalledProcessError as e:
        console.print("[bold red]Postfix configuration has errors![/bold red]")
        console.print(f"[red]{e.stderr}[/red]")
        return False


def restart_postfix():
    """Restart Postfix service."""
    console.print("Restarting Postfix service...")

    # Try systemd first
    if shutil.which("systemctl"):
        try:
            run_command(["systemctl", "restart", "postfix"], sudo=True)
            run_command(["systemctl", "enable", "postfix"], sudo=True, check=False)
            console.print("[green]Postfix restarted via systemctl.[/green]")
            return
        except subprocess.CalledProcessError:
            pass

    # Fallback to service command
    if shutil.which("service"):
        try:
            run_command(["service", "postfix", "restart"], sudo=True)
            console.print("[green]Postfix restarted via service.[/green]")
            return
        except subprocess.CalledProcessError:
            pass

    # Last resort: direct postfix command
    try:
        run_command(["postfix", "reload"], sudo=True)
        console.print("[green]Postfix reloaded.[/green]")
    except subprocess.CalledProcessError:
        console.print("[yellow]Could not restart Postfix automatically. Please restart manually.[/yellow]")


def test_gmail_relay(gmail_address: str, test_recipient: str):
    """Test sending an email through the Gmail relay."""
    console.print(Panel("Testing Gmail Relay", style="bold blue"))

    test_subject = f"Postfix Gmail Relay Test - {int(time.time())}"
    test_body = "This is a test email sent through Postfix configured as a Gmail SMTP relay."

    try:
        # Use mail command to send test email
        mail_cmd = [
            "mail",
            "-s",
            test_subject,
            "-r",
            gmail_address,
            test_recipient,
        ]

        process = subprocess.Popen(
            mail_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(input=test_body)

        if process.returncode == 0:
            console.print(f"[green]✓ Test email sent successfully![/green]")
            console.print(f"[dim]Check {test_recipient} inbox for the test email.[/dim]")
            return True
        else:
            console.print(f"[yellow]Mail command returned non-zero: {process.returncode}[/yellow]")
            if stderr:
                console.print(f"[dim]Stderr: {stderr}[/dim]")
            return False

    except FileNotFoundError:
        console.print("[yellow]mail command not found. Skipping email test.[/yellow]")
        console.print("[dim]You can test manually by sending an email through Postfix.[/dim]")
        return None
    except Exception as e:
        console.print(f"[yellow]Test email failed: {e}[/yellow]")
        return False


@app.command()
def main(
    gmail_address: str = typer.Option(..., prompt=True, help="Gmail email address (e.g., user@gmail.com)"),
    app_password: str = typer.Option(..., prompt=True, hide_input=True, help="Gmail app password (16 characters)"),
    relay_host: str = typer.Option("smtp.gmail.com", help="Gmail SMTP hostname"),
    relay_port: int = typer.Option(465, help="Gmail SMTP port (465 for SMTPS, 587 for STARTTLS)"),
    listen_port: int = typer.Option(2525, help="Port for Postfix to listen on (default: 2525 to avoid conflict with Postal on port 25)"),
    test_recipient: str = typer.Option("", help="Email address to send test email to (optional)"),
    skip_test: bool = typer.Option(False, help="Skip sending test email"),
):
    """
    Install and configure Postfix as an authenticated Gmail SMTP relay.

    This sets up Postfix to relay emails through Gmail's SMTP servers using
    your Gmail account credentials. Postfix will listen on localhost (default port 2525)
    and can be used by Postal or other mail servers.

    Default port is 2525 to avoid conflict with Postal (which typically uses port 25).

    Requirements:
    - Gmail account with 2FA enabled
    - Gmail app password (generate at: https://myaccount.google.com/apppasswords)
    """
    console.print(Markdown("# Postfix Gmail Relay Setup"))

    ensure_sudo()

    # Validate inputs
    if "@gmail.com" not in gmail_address.lower() and "@googlemail.com" not in gmail_address.lower():
        console.print(
            "[yellow]Warning: Email address doesn't appear to be a Gmail address.[/yellow]"
        )
        if not Confirm.ask("Continue anyway?", default=True):
            raise typer.Exit(0)

    if len(app_password.replace(" ", "")) != 16:
        console.print(
            "[yellow]Warning: App password should be 16 characters (without spaces).[/yellow]"
        )
        if not Confirm.ask("Continue anyway?", default=True):
            raise typer.Exit(0)

    # Check if Postfix is already configured
    if check_postfix_installed():
        console.print("[yellow]Postfix is already installed.[/yellow]")
        if not Confirm.ask("Reconfigure Postfix for Gmail relay?", default=False):
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    # Install packages
    install_postfix_packages()

    # Configure Postfix
    configure_postfix_gmail(gmail_address, app_password, relay_host, relay_port, listen_port)

    # Test configuration
    if not test_postfix_configuration():
        console.print(
            Panel(
                "[bold red]Configuration test failed![/bold red]\n\n"
                "Please check the errors above and fix the configuration manually.\n"
                "Configuration file: /etc/postfix/main.cf",
                title="Error",
                style="red",
            )
        )
        raise typer.Exit(1)

    # Restart Postfix
    restart_postfix()

    # Test email sending (optional)
    if not skip_test and test_recipient:
        test_gmail_relay(gmail_address, test_recipient)
    elif not skip_test:
        console.print("[dim]Skipping test email (no recipient provided).[/dim]")

    # Success message
    console.print(
        Panel(
            f"[bold green]Postfix Gmail Relay Setup Complete![/bold green]\n\n"
            f"Gmail Address: {gmail_address}\n"
            f"Relay Host: {relay_host}:{relay_port}\n"
            f"Postfix Status: Running on localhost:{listen_port}\n\n"
            f"[bold cyan]Next Steps:[/bold cyan]\n"
            f"  1. Configure Postal to use this relay:\n"
            f"     [cyan]install_postal.py add-postfix-relay --port {listen_port}[/cyan]\n"
            f"     Or manually: [cyan]add-relay --host 127.0.0.1 --port {listen_port} --ssl-mode None[/cyan]\n\n"
            f"  2. Test the relay (via telnet):\n"
            f"     [cyan]telnet 127.0.0.1 {listen_port}[/cyan]\n\n"
            f"  3. Check Postfix logs:\n"
            f"     [cyan]sudo tail -f /var/log/maillog[/cyan]  (Rocky Linux)\n"
            f"     [cyan]sudo tail -f /var/log/mail.log[/cyan]  (Debian/Ubuntu)\n\n"
            f"[dim]Configuration files:[/dim]\n"
            f"  - /etc/postfix/main.cf (main configuration)\n"
            f"  - /etc/postfix/master.cf (service configuration)\n"
            f"  - /etc/postfix/sasl_passwd (Gmail credentials - secured)",
            title="Success",
        )
    )


@app.command()
def status():
    """Check Postfix service status and configuration."""
    console.print(Panel("Postfix Status", style="bold blue"))
    ensure_sudo()

    # Check if Postfix is installed
    if not check_postfix_installed():
        console.print("[red]Postfix is not installed.[/red]")
        raise typer.Exit(1)

    # Check service status
    console.print("\n[bold]Service Status:[/bold]")
    if shutil.which("systemctl"):
        try:
            result = run_command(["systemctl", "status", "postfix"], sudo=True, check=False)
            console.print(result.stdout)
        except Exception:
            pass
    elif shutil.which("service"):
        try:
            result = run_command(["service", "postfix", "status"], sudo=True, check=False)
            console.print(result.stdout)
        except Exception:
            pass

    # Check configuration
    console.print("\n[bold]Configuration:[/bold]")
    try:
        result = run_command(["postfix", "check"], sudo=True)
        console.print("[green]✓ Configuration is valid.[/green]")
    except subprocess.CalledProcessError as e:
        console.print("[red]✗ Configuration has errors.[/red]")
        console.print(e.stderr)

    # Show relay configuration
    console.print("\n[bold]Relay Configuration:[/bold]")
    try:
        with open("/etc/postfix/main.cf", "r") as f:
            content = f.read()
            if "relayhost" in content:
                for line in content.split("\n"):
                    if line.strip().startswith("relayhost"):
                        console.print(f"  {line.strip()}")
            else:
                console.print("  [yellow]No relayhost configured.[/yellow]")
    except Exception as e:
        console.print(f"  [red]Could not read configuration: {e}[/red]")


@app.command()
def test(
    recipient: str = typer.Option(..., prompt=True, help="Email address to send test email to"),
    sender: str = typer.Option("", help="From address (defaults to Gmail address from config)"),
    subject: str = typer.Option("Postfix Test Email", help="Email subject"),
):
    """Send a test email through the Postfix Gmail relay."""
    console.print(Panel("Sending Test Email", style="bold blue"))

    if not check_postfix_installed():
        console.print("[red]Postfix is not installed.[/red]")
        raise typer.Exit(1)

    # Try to get sender from config if not provided
    if not sender:
        try:
            with open("/etc/postfix/sasl_passwd", "r") as f:
                for line in f:
                    if ":" in line and "@" in line:
                        # Extract email from line like "[host]:port    email:pass"
                        parts = line.strip().split()
                        if len(parts) >= 2 and ":" in parts[1]:
                            sender = parts[1].split(":")[0]
                            break
        except Exception:
            sender = "test@localhost"

    if not sender:
        sender = "test@localhost"

    console.print(f"From: {sender}")
    console.print(f"To: {recipient}")
    console.print(f"Subject: {subject}")

    test_body = f"""This is a test email sent through Postfix configured as a Gmail SMTP relay.

Timestamp: {time.time()}
"""

    try:
        mail_cmd = ["mail", "-s", subject, "-r", sender, recipient]
        process = subprocess.Popen(
            mail_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(input=test_body)

        if process.returncode == 0:
            console.print("[green]✓ Test email sent successfully![/green]")
            console.print(f"[dim]Check {recipient} inbox for the email.[/dim]")
        else:
            console.print(f"[red]Failed to send email (exit code: {process.returncode})[/red]")
            if stderr:
                console.print(f"[red]Error: {stderr}[/red]")
            raise typer.Exit(1)

    except FileNotFoundError:
        console.print("[bold red]mail command not found. Please install mailutils.[/bold red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Failed to send test email: {e}[/bold red]")
        raise typer.Exit(1)


@app.command()
def show_config():
    """Show current Postfix configuration (excluding passwords)."""
    console.print(Panel("Postfix Configuration", style="bold blue"))
    ensure_sudo()

    config_path = "/etc/postfix/main.cf"
    if not os.path.exists(config_path):
        console.print("[red]Postfix configuration file not found.[/red]")
        raise typer.Exit(1)

    try:
        with open(config_path, "r") as f:
            content = f.read()

        console.print("\n[bold]Main Configuration (main.cf):[/bold]")
        # Show relevant relay settings
        relevant_keys = [
            "relayhost",
            "smtp_use_tls",
            "smtp_sasl_auth_enable",
            "smtp_sasl_password_maps",
            "smtp_tls_wrappermode",
            "smtp_tls_security_level",
        ]

        for line in content.split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for key in relevant_keys:
                if stripped.startswith(key):
                    # Mask password in sasl_password_maps
                    if "sasl_passwd" in stripped:
                        console.print(f"  {key} = hash:/etc/postfix/sasl_passwd")
                    else:
                        console.print(f"  {stripped}")
                    break

        # Check if SASL password file exists
        sasl_path = "/etc/postfix/sasl_passwd"
        if os.path.exists(sasl_path):
            console.print("\n[bold]SASL Configuration:[/bold]")
            console.print("  [green]✓ SASL password file exists[/green]")
            try:
                with open(sasl_path, "r") as f:
                    sasl_line = f.read().strip()
                    # Mask password
                    if ":" in sasl_line:
                        parts = sasl_line.split()
                        if len(parts) >= 2:
                            cred_part = parts[1]
                            if ":" in cred_part:
                                email, _ = cred_part.split(":", 1)
                                console.print(f"  Relay: {parts[0]}")
                                console.print(f"  Email: {email}")
                                console.print(f"  Password: [masked]")
            except Exception as e:
                console.print(f"  [yellow]Could not read SASL file: {e}[/yellow]")
        else:
            console.print("\n[yellow]⚠ SASL password file not found[/yellow]")

    except Exception as e:
        console.print(f"[red]Failed to read configuration: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
