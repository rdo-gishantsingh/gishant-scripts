# Postal Installation Script Usage Guide

This guide explains how to use the `install_postal.py` automation script to set up Postal on a Linux server and send test emails.

## Overview

The scripts provided automate the installation of Postal and generic testing tasks.

*   `install_postal.py`: Installs Postal, Docker, Caddy, etc.
*   `send_test_email.py`: Helps you verify the installation by sending emails via SMTP or API.

## Features

*   **Conflict Resolution**: Automatically detects if port **5000** (default for Postal web) is used and picks a free port.
*   **Host Management**: Automatically updates `/etc/hosts` so `postal.example.com` resolves locally.
*   **Postal V3 Support**: Uses robust YAML configuration handling.
*   **Force Cleanup**: Detects existing installations and offers to **WIPE** them for a fresh start.

## 1. Quick Start (Testing Environment)

For a quick test installation (e.g., on a local VM), run:

```bash
uv run --with typer --with rich --with pyyaml src/gishant_scripts/postal/install_postal.py
```

> [!IMPORTANT]
> **PyYAML is required.** Make sure to include `--with pyyaml` in your command.

This will:
*   Ask for `sudo` permission.
*   Check for existing data/conflicts.
*   Install Postal, configure ports, and set up TLS for local domains.
*   **Print the dashboard URL** and credentials upon completion.

## 2. Admin Login & Credentials Setup

Once installed:
1.  Go to `https://postal.example.com` (or whatever domain you set).
    *   *Note: Accept the self-signed certificate warning if running locally.*
2.  Login with:
    *   **Email**: `admin@example.com`
    *   **Password**: `admin123`
3.  **Click "Add Organization"** on the dashboard.
4.  **Click "Add Mail Server"** (e.g., call it "Test Server").
5.  Inside the Mail Server, click **"Credentials"** in the menu.
    *   **SMTP**: You will see the setup credentials.
    *   **API**: Create a new API Key (Type: "SMTP/Recall/Log").

## 3. Sending Test Emails

Use the `send_test_email.py` script to verify your credentials.

### Using SMTP

```bash
uv run --with typer --with rich --with requests src/gishant_scripts/postal/send_test_email.py smtp \
    --username "your_credential_username" \
    --password "your_credential_password" \
    --recipient "test@example.com"
```

### Using API

```bash
uv run --with typer --with rich --with requests src/gishant_scripts/postal/send_test_email.py api \
    --api-key "your_api_key" \
    --recipient "test@example.com"
```

## Troubleshooting

*   **Port Conflicts**: The script auto-assigns a new port if 5000 is taken.
*   **SSL Errors**: If you see protocol errors, ensure you accepted the cleanup during installation to apply the new TLS configs.
