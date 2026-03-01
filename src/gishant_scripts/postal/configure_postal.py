#!/usr/bin/env python3
"""
Configure Postal mail server for a specific domain.
Fixes postal.yml and Caddy configuration in one go.
"""
import os
import subprocess
import sys
import time
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

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


def fix_postal_config(domain: str) -> bool:
    """
    Fix postal.yml configuration for the given domain.
    
    Updates:
    - postal.web_hostname
    - postal.smtp_hostname
    - DNS subdomain records (mx, spf, return_path, route_domain, track_domain)
    """
    console.print(Panel("Fixing Postal Configuration", style="bold blue"))
    
    config_path = "/opt/postal/config/postal.yml"
    
    if not os.path.exists(config_path):
        console.print(f"[bold red]Postal config not found at {config_path}[/bold red]")
        console.print("[yellow]Make sure Postal is installed first.[/yellow]")
        return False
    
    # Read current config
    temp_path = "/tmp/postal.yml.tmp"
    run_command(["sudo", "cp", config_path, temp_path])
    run_command(["sudo", "chmod", "666", temp_path])
    
    with open(temp_path) as f:
        config = yaml.safe_load(f) or {}
    
    changes_made = []
    
    # Ensure postal block exists
    if "postal" not in config:
        config["postal"] = {}
    
    # Fix postal.web_hostname
    if config.get("postal", {}).get("web_hostname") != domain:
        old_value = config["postal"].get("web_hostname", "not set")
        config["postal"]["web_hostname"] = domain
        changes_made.append(f"postal.web_hostname: {old_value} → {domain}")
    
    # Fix postal.smtp_hostname
    if config.get("postal", {}).get("smtp_hostname") != domain:
        old_value = config["postal"].get("smtp_hostname", "not set")
        config["postal"]["smtp_hostname"] = domain
        changes_made.append(f"postal.smtp_hostname: {old_value} → {domain}")
    
    # Fix DNS configuration
    if "dns" not in config:
        config["dns"] = {}
    
    # Update DNS records to use actual domain
    dns_updates = {
        "mx_records": [f"mx.{domain}"],
        "return_path_domain": f"rp.{domain}",
        "route_domain": f"routes.{domain}",
        "spf_include": f"spf.{domain}",
        "track_domain": f"track.{domain}",
    }
    
    for key, new_value in dns_updates.items():
        old_value = config["dns"].get(key, "not set")
        if old_value != new_value:
            config["dns"][key] = new_value
            if isinstance(new_value, list):
                changes_made.append(f"dns.{key}: {old_value} → {new_value[0]}")
            else:
                changes_made.append(f"dns.{key}: {old_value} → {new_value}")
    
    if not changes_made:
        console.print("[green]✓ Postal configuration already correct.[/green]")
        return True
    
    # Write back
    with open(temp_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    run_command(["sudo", "mv", temp_path, config_path])
    
    console.print("[green]✓ Postal configuration updated.[/green]")
    for change in changes_made:
        console.print(f"  • {change}")
    
    return True


def fix_caddy_config(domain: str, port: int) -> bool:
    """
    Fix Caddyfile configuration for domain and direct port access.
    
    Configures:
    - Domain-based access with TLS internal
    - Port 8080 access with correct Host header forwarding
    """
    console.print(Panel("Fixing Caddy Configuration", style="bold blue"))
    
    caddyfile_path = "/opt/postal/config/Caddyfile"
    
    if not os.path.exists(caddyfile_path):
        console.print(f"[yellow]Caddyfile not found at {caddyfile_path}, creating new one...[/yellow]")
    
    # Read current Caddyfile if it exists
    current_content = ""
    if os.path.exists(caddyfile_path):
        temp_read = "/tmp/Caddyfile.read.tmp"
        run_command(["sudo", "cp", caddyfile_path, temp_read])
        run_command(["sudo", "chmod", "666", temp_read])
        with open(temp_read) as f:
            current_content = f.read()
        # Remove temp file using sudo since it's owned by root
        try:
            run_command(["sudo", "rm", temp_read], check=False)
        except Exception:
            pass  # Ignore errors when removing temp file
    
    # Build new Caddyfile content
    # For port 8080, we need to ensure the Host header is correctly forwarded
    # Caddy v2's header_up should work, but we'll also add X-Forwarded-Host
    caddy_content = f"""# Domain-based access (requires /etc/hosts or DNS)
{domain} {{
  tls internal
  reverse_proxy 127.0.0.1:5001
}}

# Direct port access with correct Host header (no DNS needed)
# Note: Access via http://127.0.0.1:{port} - the Host header will be forwarded correctly
:{port} {{
  reverse_proxy 127.0.0.1:5001 {{
    # These headers ensure Postal receives the correct Host
    header_up Host {domain}
    header_up X-Forwarded-Host {domain}
    header_up X-Forwarded-Proto http
  }}
}}
"""
    
    # Check if content is already correct
    if current_content.strip() == caddy_content.strip():
        console.print("[green]✓ Caddyfile already configured correctly.[/green]")
        return True
    
    # Write new Caddyfile
    temp_path = "/tmp/Caddyfile.tmp"
    with open(temp_path, "w") as f:
        f.write(caddy_content)
    
    run_command(["sudo", "mv", temp_path, caddyfile_path])
    console.print("[green]✓ Caddyfile updated.[/green]")
    
    # Validate Caddyfile syntax
    console.print("Validating Caddyfile syntax...")
    try:
        result = run_command(
            ["docker", "exec", "postal-caddy", "caddy", "validate", "--config", "/etc/caddy/Caddyfile"],
            check=False
        )
        if result.returncode == 0:
            console.print("[green]✓ Caddyfile syntax is valid.[/green]")
        else:
            console.print("[yellow]⚠ Caddyfile validation returned non-zero exit code.[/yellow]")
            console.print(f"[dim]{result.stderr}[/dim]")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not validate Caddyfile: {e}[/yellow]")
        console.print("[yellow]Caddy will validate on restart.[/yellow]")
    
    return True


def update_hosts_file(domain: str) -> bool:
    """
    Add domain to /etc/hosts if not present.
    This overrides DNS resolution so the domain points to localhost.
    """
    console.print(Panel("Updating /etc/hosts", style="bold blue"))
    
    entry = f"127.0.0.1 {domain}"
    hosts_path = "/etc/hosts"
    
    try:
        # Read current hosts file
        temp_read = "/tmp/hosts.read.tmp"
        run_command(["sudo", "cp", hosts_path, temp_read])
        run_command(["sudo", "chmod", "666", temp_read])
        
        with open(temp_read) as f:
            content = f.read()
        
        # Remove temp file
        try:
            run_command(["sudo", "rm", temp_read], check=False)
        except Exception:
            pass
        
        # Check if domain already exists
        if domain in content and "127.0.0.1" in content:
            # Check if it's already pointing to 127.0.0.1
            lines = content.split("\n")
            for line in lines:
                if domain in line and "127.0.0.1" in line:
                    console.print(f"[green]✓ /etc/hosts already contains: {entry}[/green]")
                    return True
        
        # Add entry
        console.print(f"Adding '{entry}' to /etc/hosts...")
        console.print("[yellow]This will override DNS resolution for this domain locally.[/yellow]")
        
        # Use sudo tee -a to append
        process = subprocess.Popen(
            ["sudo", "tee", "-a", hosts_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        process.communicate(input=f"\n{entry}\n")
        
        if process.returncode == 0:
            console.print(f"[green]✓ Added {entry} to /etc/hosts[/green]")
            console.print("[yellow]Note: This overrides DNS. The domain will now resolve to localhost.[/yellow]")
            return True
        else:
            console.print("[yellow]⚠ Could not add entry to /etc/hosts. You may need to add it manually.[/yellow]")
            return False
            
    except Exception as e:
        console.print(f"[yellow]⚠ Could not update /etc/hosts: {e}[/yellow]")
        console.print(f"[yellow]Please add manually: echo '127.0.0.1 {domain}' | sudo tee -a /etc/hosts[/yellow]")
        return False


def restart_services() -> bool:
    """Restart Postal and Caddy services."""
    console.print(Panel("Restarting Services", style="bold blue"))
    
    # Restart Postal
    console.print("Restarting Postal...")
    try:
        run_command(["sudo", "postal", "restart"], check=False)
        console.print("[green]✓ Postal restart command executed.[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not restart Postal: {e}[/yellow]")
        console.print("[yellow]You may need to restart manually: sudo postal restart[/yellow]")
    
    # Wait a moment
    time.sleep(2)
    
    # Restart Caddy
    console.print("Restarting Caddy...")
    try:
        run_command(["docker", "restart", "postal-caddy"], check=False)
        console.print("[green]✓ Caddy restart command executed.[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not restart Caddy: {e}[/yellow]")
        console.print("[yellow]You may need to restart manually: docker restart postal-caddy[/yellow]")
    
    # Wait for services to start
    console.print("Waiting for services to start...")
    time.sleep(3)
    
    return True


def verify_configuration(domain: str, port: int) -> bool:
    """Verify that configuration is correct and services are running."""
    console.print(Panel("Verifying Configuration", style="bold blue"))
    
    all_good = True
    
    # Check postal.yml
    console.print("Checking postal.yml...")
    config_path = "/opt/postal/config/postal.yml"
    if os.path.exists(config_path):
        temp_read = "/tmp/postal.yml.verify.tmp"
        run_command(["sudo", "cp", config_path, temp_read])
        run_command(["sudo", "chmod", "666", temp_read])
        with open(temp_read) as f:
            config = yaml.safe_load(f) or {}
        # Remove temp file using sudo since it's owned by root
        try:
            run_command(["sudo", "rm", temp_read], check=False)
        except Exception:
            pass  # Ignore errors when removing temp file
        
        web_hostname = config.get("postal", {}).get("web_hostname", "not set")
        smtp_hostname = config.get("postal", {}).get("smtp_hostname", "not set")
        
        if web_hostname == domain and smtp_hostname == domain:
            console.print(f"[green]✓ postal.web_hostname: {web_hostname}[/green]")
            console.print(f"[green]✓ postal.smtp_hostname: {smtp_hostname}[/green]")
        else:
            console.print(f"[red]✗ postal.web_hostname: {web_hostname} (expected: {domain})[/red]")
            console.print(f"[red]✗ postal.smtp_hostname: {smtp_hostname} (expected: {domain})[/red]")
            all_good = False
    else:
        console.print("[red]✗ postal.yml not found[/red]")
        all_good = False
    
    # Check Caddyfile
    console.print("Checking Caddyfile...")
    caddyfile_path = "/opt/postal/config/Caddyfile"
    if os.path.exists(caddyfile_path):
        temp_read = "/tmp/Caddyfile.verify.tmp"
        run_command(["sudo", "cp", caddyfile_path, temp_read])
        run_command(["sudo", "chmod", "666", temp_read])
        with open(temp_read) as f:
            caddy_content = f.read()
        # Remove temp file using sudo since it's owned by root
        try:
            run_command(["sudo", "rm", temp_read], check=False)
        except Exception:
            pass  # Ignore errors when removing temp file
        
        if f":{port}" in caddy_content and domain in caddy_content:
            console.print(f"[green]✓ Caddyfile contains port {port} and domain {domain}[/green]")
        else:
            console.print(f"[red]✗ Caddyfile missing port {port} or domain {domain}[/red]")
            all_good = False
    else:
        console.print("[red]✗ Caddyfile not found[/red]")
        all_good = False
    
    # Check Postal services
    console.print("Checking Postal services...")
    try:
        result = run_command(["sudo", "postal", "status"], check=False)
        if result.returncode == 0:
            console.print("[green]✓ Postal services are running[/green]")
        else:
            console.print("[yellow]⚠ Postal status check returned non-zero exit code[/yellow]")
            all_good = False
    except Exception as e:
        console.print(f"[yellow]⚠ Could not check Postal status: {e}[/yellow]")
    
    # Check Caddy container
    console.print("Checking Caddy container...")
    try:
        result = run_command(
            ["docker", "ps", "--filter", "name=postal-caddy", "--format", "{{.Status}}"],
            check=False
        )
        if "Up" in result.stdout:
            console.print("[green]✓ Caddy container is running[/green]")
        else:
            console.print("[yellow]⚠ Caddy container may not be running[/yellow]")
            console.print(f"[dim]Status: {result.stdout.strip()}[/dim]")
            all_good = False
    except Exception as e:
        console.print(f"[yellow]⚠ Could not check Caddy container: {e}[/yellow]")
    
    return all_good


def test_email_sending(
    domain: str,
    test_email: str,
    smtp_username: str,
    smtp_password: str,
    smtp_host: str = "127.0.0.1",
    smtp_port: int = 25,
) -> bool:
    """
    Test email sending via SMTP.
    
    Connects to Postal SMTP server and sends a test email.
    """
    console.print(Panel("Testing Email Sending", style="bold blue"))
    
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        console.print(f"Connecting to SMTP server at {smtp_host}:{smtp_port}...")
        
        # Create SMTP connection with timeout and debug
        server = smtplib.SMTP(timeout=30)
        server.set_debuglevel(0)  # Set to 2 for verbose debugging
        
        # Two-step connect with delay to ensure greeting is received
        server.connect(smtp_host, smtp_port)
        time.sleep(0.5)  # Give server time to send greeting
        
        console.print("[green]✓ Connected to SMTP server[/green]")
        
        # EHLO
        code, message = server.ehlo()
        if code != 250:
            console.print(f"[yellow]⚠ EHLO returned code {code}: {message}[/yellow]")
        
        # STARTTLS if available
        if server.has_extn("STARTTLS"):
            console.print("Starting TLS...")
            server.starttls()
            server.ehlo()  # Re-EHLO after STARTTLS
            console.print("[green]✓ TLS started[/green]")
        
        # Authenticate
        console.print("Authenticating...")
        server.login(smtp_username, smtp_password)
        console.print("[green]✓ Authenticated[/green]")
        
        # Create test email
        from email.utils import formatdate, make_msgid
        
        msg = MIMEMultipart()
        msg["From"] = f"test@{domain}"
        msg["To"] = test_email
        msg["Subject"] = f"Test Email from {domain}"
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=domain)
        
        body = f"""This is a test email from Postal mail server configured for {domain}.

If you receive this email, the configuration is working correctly!

Sent at: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
        msg.attach(MIMEText(body, "plain"))
        
        # Send email
        console.print(f"Sending test email to {test_email}...")
        server.send_message(msg)
        console.print("[green]✓ Test email sent successfully![/green]")
        
        server.quit()
        return True
        
    except smtplib.SMTPException as e:
        console.print(f"[red]✗ SMTP error: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]✗ Error sending test email: {e}[/red]")
        return False


@app.command()
def main(
    domain: str = typer.Option(..., help="Domain name (e.g., yourdomain.com)"),
    web_port: int = typer.Option(8080, help="Port for direct web access"),
    test_email: Optional[str] = typer.Option(None, help="Optional: Send test email to this address"),
    smtp_username: Optional[str] = typer.Option(None, help="Optional: SMTP username for testing"),
    smtp_password: Optional[str] = typer.Option(None, help="Optional: SMTP password for testing"),
    smtp_host: str = typer.Option("127.0.0.1", help="SMTP server hostname or IP"),
    smtp_port: int = typer.Option(25, help="SMTP server port"),
):
    """
    Configure Postal for domain and optionally test email sending.
    
    This script will:
    1. Fix postal.yml configuration (web_hostname, smtp_hostname, DNS records)
    2. Fix Caddyfile configuration (domain access and port 8080 with Host header)
    3. Restart Postal and Caddy services
    4. Verify configuration is correct
    5. Optionally test email sending if credentials are provided
    """
    console.print(Panel(f"Postal Configuration for {domain}", style="bold green"))
    
    # Step 1: Fix postal.yml
    if not fix_postal_config(domain):
        console.print("[bold red]Failed to fix Postal configuration. Exiting.[/bold red]")
        raise typer.Exit(1)
    
    # Step 2: Fix Caddyfile
    if not fix_caddy_config(domain, web_port):
        console.print("[bold red]Failed to fix Caddy configuration. Exiting.[/bold red]")
        raise typer.Exit(1)
    
    # Step 2.5: Update /etc/hosts to override DNS (so domain points to localhost, not Firebase)
    update_hosts_file(domain)
    
    # Step 3: Restart services
    if not restart_services():
        console.print("[yellow]Service restart had issues, but continuing...[/yellow]")
    
    # Step 4: Verify configuration
    if not verify_configuration(domain, web_port):
        console.print("[yellow]Some verification checks failed, but configuration may still work.[/yellow]")
    
    # Step 5: Test email sending (if credentials provided)
    if test_email and smtp_username and smtp_password:
        test_email_sending(domain, test_email, smtp_username, smtp_password, smtp_host, smtp_port)
    elif test_email or smtp_username or smtp_password:
        console.print("[yellow]⚠ Test email skipped: provide all of --test-email, --smtp-username, and --smtp-password to test[/yellow]")
    
    # Summary
    console.print("\n" + "=" * 60)
    console.print(Panel("Configuration Complete", style="bold green"))
    console.print(f"\n[bold]Domain:[/bold] {domain}")
    console.print(f"[bold]Web UI Access:[/bold]")
    console.print(f"\n[bold]IMPORTANT: Clear Browser HSTS Cache First![/bold]")
    console.print(f"  Your browser has HSTS cached for {domain}, which forces HTTPS.")
    console.print(f"  To fix this:")
    console.print(f"  1. Open: [cyan]chrome://net-internals/#hsts[/cyan] (or edge://net-internals/#hsts)")
    console.print(f"  2. Under 'Delete domain security policies', enter: [cyan]{domain}[/cyan]")
    console.print(f"  3. Click 'Delete'")
    console.print(f"  4. Close and reopen your browser")
    console.print(f"\n  OR use an [bold]incognito/private window[/bold]")
    console.print(f"\n[bold]Then access:[/bold]")
    console.print(f"  • [cyan]http://{domain}[/cyan] (use HTTP, not HTTPS!)")
    console.print(f"    (Domain points to localhost via /etc/hosts)")
    console.print(f"  • Alternative: [cyan]http://127.0.0.1:{web_port}[/cyan]")
    console.print(f"    (May show 403 - use domain access instead)")
    console.print(f"\n[bold]SMTP Server:[/bold] {smtp_host}:{smtp_port}")
    console.print(f"[bold]From Address:[/bold] *@{domain}")
    console.print(f"\n[green]✓ Domain {domain} is now configured to use Postal locally![/green]")
    console.print(f"[yellow]⚠ Remember: Use HTTP (not HTTPS) and clear HSTS cache![/yellow]")
    console.print("\n[green]Postal is now configured for your domain![/green]")


if __name__ == "__main__":
    app()
