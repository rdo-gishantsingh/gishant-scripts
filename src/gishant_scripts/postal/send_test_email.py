#!/usr/bin/env python3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import typer
from rich.console import Console

app = typer.Typer()
console = Console()

@app.command()
def smtp(
    host: str = typer.Option("postal.example.com", help="Postal SMTP Host"),
    port: int = typer.Option(25, help="Postal SMTP Port"),
    username: str = typer.Option(..., prompt=True, help="SMTP Username (from Postal)"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="SMTP Password"),
    sender: str = typer.Option(..., prompt="Sender Address", help="From Address"),
    recipient: str = typer.Option(..., prompt="Recipient Address", help="To Address"),
    subject: str = typer.Option("Postal Test Email (SMTP)", help="Email Subject"),
    body: str = typer.Option("This is a test email sent via Postal SMTP.", help="Email Body")
):
    """
    Send a test email using SMTP.
    """
    console.print(f"Connecting to SMTP server at {host}:{port}...")

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Postal often supports STARTTLS on 25 or plain 25, depending on config.
        # Often for internal tests checks, plain might be allowed, but usually auth requires TLS.
        # We will try nice defaults.

        server = smtplib.SMTP(host, port)
        # server.set_debuglevel(1)

        # Check if we need EHLO and STARTTLS
        server.ehlo()
        if server.has_extn('STARTTLS'):
            console.print("Starting TLS...")
            server.starttls()
            server.ehlo()

        console.print("Logging in...")
        server.login(username, password)

        console.print("Sending email...")
        server.send_message(msg)
        server.quit()

        console.print("[bold green]Email sent successfully via SMTP![/bold green]")

    except Exception as e:
        console.print(f"[bold red]Failed to send email via SMTP:[/bold red] {e}")


@app.command()
def api(
    host: str = typer.Option("postal.example.com", help="Postal Host"),
    api_key: str = typer.Option(..., prompt=True, hide_input=True, help="Postal API Key (Credential)"),
    sender: str = typer.Option(..., prompt="Sender Address", help="From Address"),
    recipient: str = typer.Option(..., prompt="Recipient Address", help="To Address"),
    subject: str = typer.Option("Postal Test Email (API)", help="Email Subject"),
    body: str = typer.Option("This is a test email sent via Postal API.", help="Email Body")
):
    """
    Send a test email using HTTP API.
    """
    url = f"https://{host}/api/v1/send/message"

    payload = {
        "to": [recipient],
        "from": sender,
        "subject": subject,
        "plain_body": body
    }

    headers = {
        "X-Server-API-Key": api_key,
        "Content-Type": "application/json"
    }

    console.print(f"Sending via API to {url}...")

    try:
        # Verify=False because automated self-signed certs via Caddy might not be trusted by python requests unless added to store
        # For a test script, we warn but allow.
        response = requests.post(url, json=payload, headers=headers, verify=False)

        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                console.print(f"[bold green]Email sent successfully via API![/bold green] ID: {data.get('data', {}).get('message_id')}")
            else:
                 console.print(f"[bold red]API returned error:[/bold red] {data}")
        else:
            console.print(f"[bold red]HTTP Error:[/bold red] {response.status_code}")
            console.print(response.text)

    except Exception as e:
        console.print(f"[bold red]Failed to call API:[/bold red] {e}")

if __name__ == "__main__":
    app()
