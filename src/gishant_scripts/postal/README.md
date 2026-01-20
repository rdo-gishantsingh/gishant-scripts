# Postal & Postfix Automation Scripts

This directory contains automation scripts for installing, configuring, and managing Postal mail server and Postfix SMTP relay.

## Overview

These scripts simplify the deployment of a self-hosted email infrastructure using Postal. They handle:
- **Postal Installation**: Automated setup of Postal v2/v3
- **Postfix Installation**: Automated setup of Postfix as an authenticated relay (essential for Gmail)
- **Configuration**: Automated DNS, SSL/TLS, and SMTP relay configuration
- **Testing**: Tools to verify connectivity and send test emails

## Documentation

### Installation Guides
- [Postal Installation (Production)](POSTAL_INSTALL_PRODUCTION.md): Guide for deploying Postal in a production environment.
- [Postal Installation (Testing)](POSTAL_INSTALL_TESTING.md): Guide for setting up Postal for local development/testing.
- [Postfix Installation (Production)](POSTFIX_INSTALL_PRODUCTION.md): Guide for setting up Postfix as a relay in production.
- [Postfix Installation (Testing)](POSTFIX_INSTALL_TESTING.md): Guide for setting up Postfix with personal Gmail for testing.

### Workflows
- [Production Setup Workflow](PRODUCTION_WORKFLOW.md): Complete end-to-end guide for production deployment with Gmail Workspace.
- [Testing Setup Workflow](TESTING_WORKFLOW.md): Complete end-to-end guide for local testing with personal Gmail.

### Tools
- [Send Test Email](SEND_TEST_EMAIL.md): Documentation for the email testing utility.

## System Architecture

The following diagram illustrates how the components interact in both production and testing scenarios.

```mermaid
graph TD
    subgraph "Your Infrastructure"
        Postal[Postal Mail Server]
        Postfix[Postfix Relay]
        App[Your Application]
    end

    subgraph "External Providers"
        GmailWorkspace[Gmail Workspace Relay]
        PersonalGmail[Personal Gmail SMTP]
        Recipient[Email Recipient]
    end

    App -->|SMTP| Postal
    Postal -->|SMTP (Unauthenticated)| Postfix

    %% Production Flow
    Postfix -.->|Production Flow (Authenticated)| GmailWorkspace
    GmailWorkspace -.->|Production Delivery| Recipient

    %% Testing Flow
    Postfix ==>|Testing Flow (Authenticated)| PersonalGmail
    PersonalGmail ==>|Testing Delivery| Recipient

    %% Direct Flow (Optional/Alternative)
    Postal -.->|Direct Delivery (Production)| Recipient

    classDef production fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef testing fill:#fff3e0,stroke:#e65100,stroke-width:2px;

    linkStyle 3,4 stroke:#01579b,stroke-width:2px,fill:none;
    linkStyle 5,6 stroke:#e65100,stroke-width:2px,fill:none;
```

## Quick Start

### 1. Install Postfix
```bash
# For Testing (Personal Gmail)
uv run src/gishant_scripts/postal/install_postfix.py main \
  --gmail-address "your.email@gmail.com" \
  --app-password "your-app-password"

# For Production (Gmail Workspace)
uv run src/gishant_scripts/postal/install_postfix.py main \
  --relay-host "smtp-relay.gmail.com" \
  --relay-port 587
```

### 2. Install Postal
```bash
# Install and configure Postal
uv run src/gishant_scripts/postal/install_postal.py main \
  --domain "mail.yourdomain.com" \
  --db-password "secure-password" \
  --admin-email "admin@yourdomain.com" \
  --admin-password "secure-password"
```

### 3. Connect Postal to Postfix
```bash
# Configure Postal to use the local Postfix relay
uv run src/gishant_scripts/postal/install_postal.py add-postfix-relay
```

## Requirements
- Python 3.10+
- `uv` package manager
- **Ubuntu 20.04+ / Debian 11+** (recommended)
- **Rocky Linux 8+ / 9+** (also supported)
- Docker & Docker Compose (installed by scripts if missing)

## Supported Operating Systems

The scripts support both Debian-based and RHEL-based distributions:

- **Debian/Ubuntu**: Uses `apt` package manager, CA certificates at `/etc/ssl/certs/ca-certificates.crt`
- **Rocky Linux/RHEL/CentOS**: Uses `dnf`/`yum` package manager, CA certificates at `/etc/pki/tls/certs/ca-bundle.crt`

The installation scripts automatically detect your distribution and use the appropriate package manager and paths.
