#!/usr/bin/env python3
"""
Simple script to send a test email via Postal SMTP.
"""
import smtplib
import sys
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import typer
from rich.console import Console
from rich.panel import Panel

console = Console()
app = typer.Typer()


@app.command()
def main(
    to_email: str = typer.Option(..., help="Recipient email address"),
    from_email: str = typer.Option("test@yourdomain.com", help="Sender email address"),
    smtp_username: str = typer.Option(..., help="SMTP username from Postal"),
    smtp_password: str = typer.Option(..., help="SMTP password from Postal"),
    smtp_host: str = typer.Option("127.0.0.1", help="SMTP server hostname or IP"),
    smtp_port: int = typer.Option(25, help="SMTP server port"),
    domain: str = typer.Option("yourdomain.com", help="Your domain name"),
):
    """
    Send a test email via Postal SMTP server.
    """
    console.print(Panel("Sending Test Email", style="bold blue"))
    
    try:
        console.print(f"Connecting to SMTP server at {smtp_host}:{smtp_port}...")
        
        # Create SMTP connection
        server = smtplib.SMTP(timeout=30)
        server.set_debuglevel(0)
        
        # Connect with delay to ensure greeting is received
        server.connect(smtp_host, smtp_port)
        time.sleep(0.5)
        
        console.print("[green]✓ Connected to SMTP server[/green]")
        
        # EHLO
        code, message = server.ehlo()
        if code != 250:
            console.print(f"[yellow]⚠ EHLO returned code {code}: {message}[/yellow]")
        
        # STARTTLS if available
        if server.has_extn("STARTTLS"):
            console.print("Starting TLS...")
            server.starttls()
            server.ehlo()
            console.print("[green]✓ TLS started[/green]")
        
        # Authenticate
        console.print("Authenticating...")
        server.login(smtp_username, smtp_password)
        console.print("[green]✓ Authenticated[/green]")
        
        # Create test email
        import uuid
        from email.utils import formatdate, make_msgid
        
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = f"Test Email from {domain}"
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=domain)
        
        body = f"""This is a test email from Postal mail server configured for {domain}.

If you receive this email, the configuration is working correctly!

Sent at: {time.strftime('%Y-%m-%d %H:%M:%S')}
Domain: {domain}
SMTP Server: {smtp_host}:{smtp_port}
"""
        msg.attach(MIMEText(body, "plain"))
        
        # Send email
        console.print(f"Sending test email to {to_email}...")
        server.send_message(msg)
        console.print("[green]✓ Test email sent successfully![/green]")
        console.print(f"\n[bold]Email Details:[/bold]")
        console.print(f"  From: {from_email}")
        console.print(f"  To: {to_email}")
        console.print(f"  Subject: Test Email from {domain}")
        console.print(f"\n[green]Check the recipient's inbox (and spam folder)![/green]")
        
        server.quit()
        return True
        
    except smtplib.SMTPException as e:
        console.print(f"[bold red]✗ SMTP error:[/bold red] {e}")
        return False
    except Exception as e:
        console.print(f"[bold red]✗ Error:[/bold red] {e}")
        return False


if __name__ == "__main__":
    app()
