# Postal Installation Guide

This guide describes how to install Postal on a Linux server, strictly following the [official documentation](https://docs.postalserver.io/getting-started).

## Prerequisites

1.  **Server**: A dedicated server (not shared hosting) with at least:
    *   4GB RAM
    *   2 CPU Cores
    *   25GB Disk Space
    *   Operating System: **Ubuntu/Debian** or **Rocky Linux 9 / RHEL** (Must support Docker)
    *   **Port 25 outbound** must be open (check with your provider).

2.  **Dependencies**:
    *   Docker Engine
    *   Docker Compose Plugin
    *   `git`, `curl`, `jq`
    *   **PyYAML** (Required for the installer script)

> [!TIP]
> **Production Deployment & Gmail Integration**
> For details on deploying to Rocky Linux 9 and integrating with **Google Workspace**, see [`PRODUCTION.md`](PRODUCTION.md).

## Installation Steps (Automated)

The script handles Postal v3 configuration automatically, including:
*   Setting `web_server.default_bind_address` to `0.0.0.0` to ensure Docker container connectivity.
*   Generating a robust `Caddyfile` with internal TLS for local testing.
*   Detecting port conflicts (e.g., if port 5000 is taken, it uses 5001).

Run the installer with:
```bash
uv run --with typer --with rich --with pyyaml src/gishant_scripts/postal/install_postal.py
```

### Manual Installation Overview (Reference)

### 1. Install System Utilities

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y git curl jq
```

**Rocky Linux 9 / RHEL:**
```bash
sudo dnf install -y git curl jq
```

### 2. Install Docker

Follow the [official Docker installation guide](https://docs.docker.com/engine/install/) for your distribution. Ensure `docker` and `docker compose` commands work.

### 3. Setup Postal Command

Clone the installation helper repository and link the binary:

```bash
sudo git clone https://github.com/postalserver/install /opt/postal/install
sudo ln -s /opt/postal/install/bin/postal /usr/bin/postal
```

### 4. Database Setup (MariaDB)

Postal requires MariaDB (10.6 or higher). Run it in a container:

```bash
docker run -d \
   --name postal-mariadb \
   -p 127.0.0.1:3306:3306 \
   --restart always \
   -e MARIADB_DATABASE=postal \
   -e MARIADB_ROOT_PASSWORD=YOUR_STRONG_PASSWORD \
   mariadb
```
*Replace `YOUR_STRONG_PASSWORD` with a secure password.*

### 5. Configuration

Bootstrap the configuration. Replace `postal.yourdomain.com` with your actual domain.

```bash
postal bootstrap postal.yourdomain.com
```

This creates files in `/opt/postal/config`:
*   `postal.yml`
*   `signing.key`
*   `Caddyfile`

**Important**: Edit `/opt/postal/config/postal.yml` and set the database password to the one you chose in Step 4.

### 6. Initialize Postal

Initialize the database and create a user:

```bash
postal initialize
postal make-user
```
Follow the prompts to create your admin user.

### 7. Start Postal

Start the Postal components:

```bash
postal start
```

Check status:
```bash
postal status
```

### 8. Setup Caddy (Web Proxy & SSL)

Use Caddy to handle SSL and web traffic:

```bash
docker run -d \
   --name postal-caddy \
   --restart always \
   --network host \
   -v /opt/postal/config/Caddyfile:/etc/caddy/Caddyfile \
   -v /opt/postal/caddy-data:/data \
   caddy
```

You can now access the interface at `https://postal.yourdomain.com`.
