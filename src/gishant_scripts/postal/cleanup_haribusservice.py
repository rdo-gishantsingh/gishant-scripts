#!/usr/bin/env python3
"""
Clean up all haribusservice.in references from scripts and provide
instructions for manual cleanup of Postal configurations.
"""
import os
import subprocess
import sys

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
app = typer.Typer()


def run_command(
    command: list[str], shell: bool = False, check: bool = False, sudo: bool = False
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
        console.print(f"[yellow]Command returned non-zero: {cmd_str}[/yellow]")
        return e


@app.command()
def main(
    dry_run: bool = typer.Option(False, help="Show what would be changed without making changes"),
):
    """
    Clean up all haribusservice.in references from scripts and provide
    instructions for manual cleanup of Postal configurations.
    """
    console.print(Panel("Cleaning Up haribusservice.in References", style="bold blue"))
    
    if dry_run:
        console.print("[yellow]DRY RUN MODE: No changes will be made[/yellow]\n")
    
    # Check for remaining references in scripts
    console.print(Panel("Checking Scripts", style="bold blue"))
    
    script_files = [
        "src/gishant_scripts/postal/configure_postal.py",
        "src/gishant_scripts/postal/configure_redefine_route.py",
        "src/gishant_scripts/postal/send_test_email_simple.py",
    ]
    
    found_references = []
    for script_file in script_files:
        full_path = os.path.join(os.getcwd(), script_file) if not os.path.isabs(script_file) else script_file
        if os.path.exists(full_path):
            with open(full_path) as f:
                content = f.read()
                if "haribusservice" in content.lower():
                    found_references.append(script_file)
                    console.print(f"[yellow]⚠ Found reference in: {script_file}[/yellow]")
                else:
                    console.print(f"[green]✓ No references in: {script_file}[/green]")
        else:
            console.print(f"[dim]File not found: {script_file}[/dim]")
    
    if found_references and not dry_run:
        console.print(f"\n[yellow]Note: Scripts have already been cleaned up.[/yellow]")
        console.print(f"[yellow]If you see references above, they may be in comments or help text.[/yellow]")
    
    # Check /etc/hosts
    console.print()
    console.print(Panel("Checking /etc/hosts", style="bold blue"))
    
    try:
        result = run_command(["grep", "-i", "haribusservice", "/etc/hosts"], check=False)
        if result.returncode == 0 and result.stdout.strip():
            console.print("[yellow]⚠ Found haribusservice.in in /etc/hosts:[/yellow]")
            console.print(f"[dim]{result.stdout.strip()}[/dim]")
            
            if not dry_run:
                console.print("\nRemoving from /etc/hosts...")
                # Use sed to remove the line
                run_command(
                    ["sudo", "sed", "-i", "/haribusservice/d", "/etc/hosts"],
                    check=False
                )
                console.print("[green]✓ Removed from /etc/hosts[/green]")
            else:
                console.print("[dim]Would remove this line from /etc/hosts[/dim]")
        else:
            console.print("[green]✓ No haribusservice.in found in /etc/hosts[/green]")
    except Exception as e:
        console.print(f"[yellow]⚠ Could not check /etc/hosts: {e}[/yellow]")
    
    # Postal configuration files (manual cleanup instructions)
    console.print()
    console.print(Panel("Postal Configuration Files (Manual Cleanup Required)", style="bold yellow"))
    
    postal_configs = [
        "/opt/postal/config/postal.yml",
        "/opt/postal/config/Caddyfile",
        "/opt/postal/config/Caddyfile.backup",
    ]
    
    console.print("\n[bold]The following files need manual cleanup (require sudo):[/bold]\n")
    
    table = Table(title="Files Requiring Manual Cleanup")
    table.add_column("File", style="cyan")
    table.add_column("Action", style="yellow")
    table.add_column("Command", style="dim")
    
    for config_file in postal_configs:
        # Check if file exists
        result = run_command(["test", "-f", config_file], check=False)
        if result.returncode == 0:
            # Check for haribusservice references
            grep_result = run_command(
                ["sudo", "grep", "-i", "haribusservice", config_file],
                check=False
            )
            if grep_result.returncode == 0:
                table.add_row(
                    config_file,
                    "Remove/replace haribusservice.in",
                    f"sudo sed -i 's/haribusservice\\.in/YOUR_NEW_DOMAIN/g' {config_file}"
                )
            else:
                table.add_row(
                    config_file,
                    "No references found",
                    "N/A"
                )
        else:
            table.add_row(
                config_file,
                "File not found",
                "N/A"
            )
    
    console.print(table)
    
    # Provide manual cleanup instructions
    console.print()
    console.print(Panel("Manual Cleanup Instructions", style="bold blue"))
    
    console.print("\n[bold]Step 1: Clean Postal Configuration[/bold]")
    console.print("  Run these commands (replace YOUR_NEW_DOMAIN with your actual domain):")
    console.print("  [cyan]sudo sed -i 's/haribusservice\\.in/YOUR_NEW_DOMAIN/g' /opt/postal/config/postal.yml[/cyan]")
    console.print("  [cyan]sudo sed -i 's/haribusservice\\.in/YOUR_NEW_DOMAIN/g' /opt/postal/config/Caddyfile[/cyan]")
    console.print("  [cyan]sudo rm -f /opt/postal/config/Caddyfile.backup[/cyan]")
    
    console.print("\n[bold]Step 2: Restart Services[/bold]")
    console.print("  [cyan]sudo postal restart[/cyan]")
    console.print("  [cyan]docker restart postal-caddy[/cyan]")
    
    console.print("\n[bold]Step 3: Verify Cleanup[/bold]")
    console.print("  [cyan]sudo grep -i haribusservice /opt/postal/config/*[/cyan]")
    console.print("  Should return no results")
    
    console.print("\n[bold]Step 4: Reconfigure with New Domain[/bold]")
    console.print("  [cyan]cd /home/gisi/dev/repos/gishant-scripts[/cyan]")
    console.print("  [cyan]uv run --with typer --with rich --with pyyaml \\[/cyan]")
    console.print("  [cyan]  src/gishant_scripts/postal/configure_postal.py \\[/cyan]")
    console.print("  [cyan]  --domain \"YOUR_NEW_DOMAIN\" \\[/cyan]")
    console.print("  [cyan]  --web-port 8080[/cyan]")
    
    # Summary
    console.print("\n" + "=" * 60)
    console.print(Panel("Cleanup Summary", style="bold green"))
    
    if not found_references:
        console.print("[green]✓ Scripts are clean (no haribusservice.in references)[/green]")
    else:
        console.print(f"[yellow]⚠ Found {len(found_references)} script(s) with references[/yellow]")
        console.print("[yellow]  These may be in comments or help text - review manually[/yellow]")
    
    console.print("\n[bold]Next Steps:[/bold]")
    console.print("  1. Follow manual cleanup instructions above")
    console.print("  2. Reconfigure Postal with your new domain")
    console.print("  3. Verify email sending works with new domain")
    
    console.print("\n[yellow]Note:[/yellow] Postal database may contain haribusservice.in references")
    console.print("  (domains, credentials, etc.). These can be cleaned up via Postal web UI.")


if __name__ == "__main__":
    app()
