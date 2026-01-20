# Send Test Email Guide

This guide covers using the `send_test_email.py` script to test email delivery through Postal via SMTP or API.

## Overview

The `send_test_email.py` script provides two methods to send test emails:
1. **SMTP**: Direct SMTP connection to Postal server
2. **API**: HTTP API call to Postal server

## Prerequisites

Before using the test email script, ensure you have:

1. **Postal Installed**: Postal server must be installed and running
2. **SMTP Credentials**: Username and password from Postal web UI
3. **API Key** (for API method): API credential from Postal web UI
4. **Python Dependencies**: `typer`, `rich`, `requests` (for API method)

## Architecture

```mermaid
graph TB
    subgraph "Test Script"
        SMTPCmd[SMTP Command]
        APICmd[API Command]
    end

    subgraph "Postal Server"
        SMTPPort[SMTP Port 25]
        APIPort[API Endpoint<br/>/api/v1/send/message]
        Queue[Message Queue]
    end

    subgraph "Email Delivery"
        Worker[Postal Worker]
        Relay[SMTP Relay]
        Recipient[Email Recipient]
    end

    SMTPCmd -->|SMTP Connection| SMTPPort
    APICmd -->|HTTP POST| APIPort

    SMTPPort --> Queue
    APIPort --> Queue

    Queue --> Worker
    Worker --> Relay
    Relay --> Recipient

    classDef script fill:#e3f2fd,stroke:#1976d2;
    classDef postal fill:#fff3e0,stroke:#f57c00;
    classDef delivery fill:#e8f5e9,stroke:#2e7d32;
```

## Email Sending Flow

```mermaid
sequenceDiagram
    participant Script as Test Script
    participant Postal as Postal Server
    participant Queue as Message Queue
    participant Worker as Postal Worker
    participant Relay as SMTP Relay
    participant Recipient as Email Recipient

    alt SMTP Method
        Script->>Postal: Connect via SMTP
        Postal->>Postal: Authenticate
        Script->>Postal: Send Email
    else API Method
        Script->>Postal: HTTP POST /api/v1/send/message
        Postal->>Postal: Authenticate via API Key
    end

    Postal->>Queue: Queue Message
    Queue->>Worker: Process Message
    Worker->>Relay: Relay Email
    Relay->>Recipient: Deliver Email
    Recipient-->>Relay: Delivery Confirmation
    Relay-->>Worker: Delivery Status
    Worker-->>Postal: Update Status
    Postal-->>Script: Success Response
```

## SMTP Method

### Usage

```bash
uv run --with typer --with rich \
  src/gishant_scripts/postal/send_test_email.py smtp \
  --host "postal.example.com" \
  --port 25 \
  --username "postal-smtp" \
  --password "your-smtp-password" \
  --sender "sender@example.com" \
  --recipient "recipient@example.com" \
  --subject "Test Email Subject" \
  --body "Test email body content"
```

### Parameters

- `--host`: Postal SMTP hostname (default: `postal.example.com`)
- `--port`: Postal SMTP port (default: `25`)
- `--username`: SMTP username from Postal (prompted if not provided)
- `--password`: SMTP password from Postal (prompted, hidden input)
- `--sender`: From email address (prompted if not provided)
- `--recipient`: To email address (prompted if not provided)
- `--subject`: Email subject (default: "Postal Test Email (SMTP)")
- `--body`: Email body text (default: "This is a test email sent via Postal SMTP.")

### Example

```bash
# Basic usage (will prompt for credentials)
uv run --with typer --with rich \
  src/gishant_scripts/postal/send_test_email.py smtp

# Full command with all parameters
uv run --with typer --with rich \
  src/gishant_scripts/postal/send_test_email.py smtp \
  --host "mail.yourdomain.com" \
  --port 25 \
  --username "postal-smtp" \
  --password "vqR5XKvBgrQbNnj5XdtUntmx" \
  --sender "test@yourdomain.com" \
  --recipient "recipient@example.com" \
  --subject "Test Email from Postal" \
  --body "This is a test email to verify Postal is working correctly."
```

### SMTP Connection Flow

```mermaid
flowchart TD
    Start([Start SMTP Test]) --> Connect[Connect to SMTP Server]
    Connect --> EHLO[Send EHLO]
    EHLO --> CheckTLS{STARTTLS Available?}

    CheckTLS -->|Yes| StartTLS[Start TLS]
    CheckTLS -->|No| Auth
    StartTLS --> EHLO2[Send EHLO Again]
    EHLO2 --> Auth

    Auth[Authenticate] --> Login{Login Success?}
    Login -->|No| Fail([Authentication Failed])
    Login -->|Yes| SendEmail[Send Email]

    SendEmail --> Success{Email Sent?}
    Success -->|Yes| Complete([Email Sent Successfully])
    Success -->|No| Fail2([Send Failed])

    Fail --> End([End])
    Fail2 --> End
    Complete --> End

    style Start fill:#c8e6c9
    style Complete fill:#c8e6c9
    style Fail fill:#ffcdd2
    style Fail2 fill:#ffcdd2
```

## API Method

### Usage

```bash
uv run --with typer --with rich --with requests \
  src/gishant_scripts/postal/send_test_email.py api \
  --host "postal.example.com" \
  --api-key "your-api-key" \
  --sender "sender@example.com" \
  --recipient "recipient@example.com" \
  --subject "Test Email Subject" \
  --body "Test email body content"
```

### Parameters

- `--host`: Postal hostname (default: `postal.example.com`)
- `--api-key`: Postal API key/credential (prompted if not provided, hidden input)
- `--sender`: From email address (prompted if not provided)
- `--recipient`: To email address (prompted if not provided)
- `--subject`: Email subject (default: "Postal Test Email (API)")
- `--body`: Email body text (default: "This is a test email sent via Postal API.")

### Example

```bash
# Basic usage (will prompt for API key)
uv run --with typer --with rich --with requests \
  src/gishant_scripts/postal/send_test_email.py api

# Full command with all parameters
uv run --with typer --with rich --with requests \
  src/gishant_scripts/postal/send_test_email.py api \
  --host "mail.yourdomain.com" \
  --api-key "your-api-credential-key" \
  --sender "test@yourdomain.com" \
  --recipient "recipient@example.com" \
  --subject "Test Email via API" \
  --body "This is a test email sent via Postal API."
```

### API Request Flow

```mermaid
flowchart TD
    Start([Start API Test]) --> BuildRequest[Build API Request]
    BuildRequest --> SetHeaders[Set Headers<br/>X-Server-API-Key]
    SetHeaders --> POST[POST /api/v1/send/message]

    POST --> Response{Response Status?}
    Response -->|200 OK| CheckStatus{Status Success?}
    Response -->|Error| Fail([HTTP Error])

    CheckStatus -->|Yes| GetID[Get Message ID]
    CheckStatus -->|No| Fail2([API Error])

    GetID --> Complete([Email Sent Successfully])

    Fail --> End([End])
    Fail2 --> End
    Complete --> End

    style Start fill:#c8e6c9
    style Complete fill:#c8e6c9
    style Fail fill:#ffcdd2
    style Fail2 fill:#ffcdd2
```

## Getting Credentials

### SMTP Credentials

1. Log in to Postal web UI: `https://your-postal-domain`
2. Navigate to your organization
3. Go to "Mail Servers"
4. Select your mail server
5. Go to "Credentials" tab
6. Create a new SMTP credential
7. Copy the username and password

### API Credentials

1. Log in to Postal web UI: `https://your-postal-domain`
2. Navigate to your organization
3. Go to "Mail Servers"
4. Select your mail server
5. Go to "Credentials" tab
6. Create a new API credential
7. Copy the API key

## Testing Scenarios

### Scenario 1: Basic SMTP Test

Test basic email delivery through Postal:

```bash
uv run --with typer --with rich \
  src/gishant_scripts/postal/send_test_email.py smtp \
  --host "postal.example.com" \
  --username "postal-smtp" \
  --password "your-password" \
  --sender "test@example.com" \
  --recipient "your.email@gmail.com"
```

### Scenario 2: API Test

Test email delivery via API:

```bash
uv run --with typer --with rich --with requests \
  src/gishant_scripts/postal/send_test_email.py api \
  --host "postal.example.com" \
  --api-key "your-api-key" \
  --sender "test@example.com" \
  --recipient "your.email@gmail.com"
```

### Scenario 3: Custom Subject and Body

Send email with custom content:

```bash
uv run --with typer --with rich \
  src/gishant_scripts/postal/send_test_email.py smtp \
  --host "postal.example.com" \
  --username "postal-smtp" \
  --password "your-password" \
  --sender "test@example.com" \
  --recipient "your.email@gmail.com" \
  --subject "Custom Test Subject" \
  --body "This is a custom test email with specific content."
```

## Troubleshooting

### Issue: SMTP Authentication Failed

**Symptoms**: "Authentication failed" error

**Solutions**:
1. Verify username and password are correct
2. Check credentials in Postal web UI
3. Ensure SMTP credential is enabled
4. Check Postal SMTP server is running: `docker logs postal-web-1`

### Issue: Connection Refused

**Symptoms**: "Connection refused" or "Connection timeout"

**Solutions**:
1. Verify Postal is running: `sudo postal status`
2. Check SMTP port is accessible: `telnet postal.example.com 25`
3. Verify hostname is correct
4. Check firewall rules (port 25 should be open)

### Issue: STARTTLS Errors

**Symptoms**: TLS handshake failures

**Solutions**:
1. Postal may require STARTTLS - script handles this automatically
2. Check Postal SMTP configuration
3. Verify TLS certificates if using custom certificates

### Issue: API Returns Error

**Symptoms**: HTTP error or API returns error status

**Solutions**:
1. Verify API key is correct
2. Check API credential is enabled in Postal
3. Verify hostname is correct (should be accessible via HTTPS)
4. Check Postal web server logs: `docker logs postal-web-1`
5. For self-signed certificates, script uses `verify=False` (warning is expected)

### Issue: Email Not Delivering

**Symptoms**: Script reports success but email not received

**Solutions**:
1. Check Postal worker logs: `docker logs postal-worker-1 --tail 50`
2. Verify SMTP relay is configured
3. Check suppression list (recipient may be suppressed)
4. Verify recipient email address is correct
5. Check spam folder
6. For testing setup, verify Postfix is running and configured

## Verification

After sending a test email:

1. **Check Postal Logs**:
```bash
# Worker logs
docker logs postal-worker-1 --tail 50

# Web server logs
docker logs postal-web-1 --tail 50
```

2. **Check Email Queue**:
```bash
# Access Postal console
sudo postal console

# Check messages
Server.first.message_db.messages.last
```

3. **Check Delivery Status**:
   - Log in to Postal web UI
   - Navigate to "Messages"
   - Find your test email
   - Check delivery status

## Best Practices

1. **Use Test Email Addresses**: Use dedicated test email addresses
2. **Check Spam Folder**: Test emails may end up in spam
3. **Monitor Logs**: Always check logs after sending test emails
4. **Verify Relay**: Ensure SMTP relay is properly configured
5. **Clean Suppression List**: Remove test addresses from suppression list if needed

## Quick Reference

```bash
# SMTP method
uv run --with typer --with rich \
  src/gishant_scripts/postal/send_test_email.py smtp \
  --host "postal.example.com" \
  --port 25 \
  --username "postal-smtp" \
  --password "your-password" \
  --sender "sender@example.com" \
  --recipient "recipient@example.com"

# API method
uv run --with typer --with rich --with requests \
  src/gishant_scripts/postal/send_test_email.py api \
  --host "postal.example.com" \
  --api-key "your-api-key" \
  --sender "sender@example.com" \
  --recipient "recipient@example.com"
```
