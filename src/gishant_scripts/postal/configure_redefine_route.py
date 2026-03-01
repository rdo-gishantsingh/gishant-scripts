#!/usr/bin/env python3
"""
Configure Postal to route emails for redefine.co to specific mail servers.
This handles the case where redefine.co uses private IP mail servers.
"""
import typer
from rich.console import Console
from rich.panel import Panel

console = Console()
app = typer.Typer()


@app.command()
def main(
    domain: str = typer.Option("redefine.co", help="Domain to configure routing for"),
    mail_server_1: str = typer.Option("10.1.64.5", help="First mail server IP"),
    mail_server_2: str = typer.Option("10.1.64.6", help="Second mail server IP (optional)"),
    port: int = typer.Option(25, help="SMTP port"),
):
    """
    Configure Postal routing for redefine.co to use private IP mail servers.
    
    This creates a route in Postal's web UI that tells Postal to send emails
    for redefine.co directly to the specified mail server IPs instead of
    looking up MX records.
    """
    console.print(Panel(f"Configuring Postal Route for {domain}", style="bold blue"))
    
    console.print("\n[bold]Instructions:[/bold]")
    console.print("\n1. Open Postal web UI (use your configured domain or http://127.0.0.1:8080)")
    console.print("2. Go to [bold]Routing[/bold] in the navigation")
    console.print("3. Click [bold]New Route[/bold] or [bold]Add Route[/bold]")
    console.print(f"4. Configure the route as follows:\n")
    
    console.print(f"   [bold]Domain Pattern:[/bold] [cyan]{domain}[/cyan]")
    console.print(f"   [bold]Route Type:[/bold] [cyan]SMTP Server[/cyan]")
    console.print(f"   [bold]Server Address:[/bold] [cyan]{mail_server_1}:{port}[/cyan]")
    
    if mail_server_2:
        console.print(f"\n   [bold]Backup Server:[/bold] [cyan]{mail_server_2}:{port}[/cyan]")
        console.print("   (Add as a second route or backup server if Postal supports it)")
    
    console.print(f"\n5. Save the route")
    console.print(f"\n[bold]Alternative: Manual Configuration[/bold]")
    console.print(f"\nIf Postal doesn't support direct IP routing, you may need to:")
    console.print(f"  1. Set up a local Postfix relay that can reach {mail_server_1}")
    console.print(f"  2. Configure Postal to use that relay for {domain}")
    console.print(f"  3. Configure Postfix to forward {domain} to {mail_server_1}:{port}")
    
    console.print(f"\n[bold]Network Check:[/bold]")
    console.print(f"  Your server IP: [cyan]10.1.69.24[/cyan]")
    console.print(f"  Target mail server: [cyan]{mail_server_1}[/cyan]")
    console.print(f"  [yellow]⚠ Ensure network routing/firewall allows connection between these IPs[/yellow]")
    
    console.print(f"\n[bold]Testing Connection:[/bold]")
    console.print(f"  Run: [cyan]telnet {mail_server_1} {port}[/cyan]")
    console.print(f"  If connection succeeds, Postal should be able to send emails.")


if __name__ == "__main__":
    app()
