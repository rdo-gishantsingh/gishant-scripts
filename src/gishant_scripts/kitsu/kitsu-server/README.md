# Custom Kitsu/Zou Docker Setup

This directory contains a custom Docker Compose setup for running Kitsu (frontend) and Zou (API backend) for local development.

## Overview

This setup is based on the [official Zou documentation](https://zou.cg-wire.com/) and provides:

- **PostgreSQL 17**: Database for Zou
- **Redis 7**: Key-value store for caching and message queue
- **Zou API**: Main API server running on port 5000 (exposed as 5005)
- **Zou Events**: WebSocket event stream server on port 5001 (exposed as 5006)
- **Kitsu Frontend**: Vue.js frontend served via Nginx on port 80 (exposed as 8090)

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Kitsu Frontend (Nginx)                │
│                      localhost:8090                      │
└──────────┬──────────────────────────────────────────────┘
           │
           ├─→ /api → Zou API (port 5000)
           │          - Main REST API
           │          - Worker: gevent (async)
           │
           └─→ /socket.io → Zou Events (port 5001)
                            - WebSocket event stream
                            - Worker: geventwebsocket
                            - Uses Redis for pub/sub
```

## Prerequisites

- Docker and Docker Compose
- Git repositories cloned:
  - `zou` at `/home/gisi/dev/repos/zou`
  - `kitsu` at `/home/gisi/dev/repos/kitsu`

## Quick Start

### 1. Start Services

```bash
cd /home/gisi/dev/repos/gishant-scripts/src/gishant_scripts/kitsu/kitsu-server
docker compose up --build -d
```

### 2. Initialize Database (First Time Only)

```bash
./init-zou.sh
```

This script will:
- Create database schema (`zou init-db`)
- Initialize base data (`zou init-data`)
- Create admin user with credentials:
  - Email: `admin@example.com`
  - Password: `mysecretpassword`

### 3. Access Kitsu

Open your browser and navigate to: http://localhost:8090

Login with:
- **Email**: `admin@example.com`
- **Password**: `mysecretpassword`

**⚠️ Important**: Change the default password after first login!

## Services

### Database (db)
- **Image**: postgres:17
- **Container**: `db`
- **Port**: 5432 (internal only)
- **Credentials**:
  - User: `zou`
  - Password: `zou`
  - Database: `zoudb`

### Redis (redis)
- **Image**: redis:7
- **Container**: `redis`
- **Port**: 6379 (internal only)

### Zou API (zou)
- **Container**: `zou`
- **Port**: 5005 → 5000
- **Worker**: gevent (3 workers)
- **Command**: `gunicorn zou.app:app`

### Zou Events (zou-events)
- **Container**: `zou-events`
- **Port**: 5006 → 5001
- **Worker**: geventwebsocket (1 worker)
- **Command**: `gunicorn zou.event_stream:app`

### Kitsu Frontend (kitsu)
- **Container**: `kitsu`
- **Port**: 8090 → 80
- **Server**: Nginx

## Environment Variables

The following environment variables are configured for Zou services:

| Variable | Value | Description |
|----------|-------|-------------|
| `DB_USERNAME` | `zou` | Database username |
| `DB_PASSWORD` | `zou` | Database password |
| `DB_HOST` | `db` | Database host (container name) |
| `DB_DATABASE` | `zoudb` | Database name |
| `KV_HOST` | `redis` | Redis host (container name) |
| `KV_PORT` | `6379` | Redis port |
| `SECRET_KEY` | `supersecretkey` | JWT token encryption key |
| `PREVIEW_FOLDER` | `/opt/zou/previews` | Preview files storage |
| `TMP_DIR` | `/opt/zou/tmp` | Temporary files directory |

**⚠️ Security**: Change `SECRET_KEY` in production!

## Volumes

### Persistent Data
- `db-data`: PostgreSQL database files
- `zou-previews`: Preview files (thumbnails, videos)
- `zou-tmp`: Temporary upload files

### Development Mounts
- `zou` source code mounted at `/app` (hot reload)
- `kitsu` source code used during build

## Networks

- **default**: Internal network for service communication
- **pipeline_network**: External network for integration with other services

## Management Scripts

### Database Restoration

To restore from a backup:

```bash
./restore-db.sh /path/to/backup.dump
```

Supported formats:
- Custom format (`.dump`, `.backup`)
- Gzipped SQL (`.gz`)
- Plain SQL (`.sql`)

### Database Initialization

To reinitialize the database:

```bash
./init-zou.sh
```

## Development Workflow

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f zou
docker compose logs -f zou-events
docker compose logs -f kitsu
```

### Restart Services

```bash
# All services
docker compose restart

# Specific service
docker compose restart zou
docker compose restart zou-events
```

### Access Service Shell

```bash
# Zou API
docker compose exec zou bash

# Database
docker compose exec db psql -U zou -d zoudb
```

### Rebuild After Code Changes

```bash
docker compose up --build -d
```

## Differences from Official Documentation

This setup differs from the [official Zou documentation](https://zou.cg-wire.com/) in the following ways:

### Advantages
✅ Containerized - easier to set up and manage
✅ Development-friendly with source code mounting
✅ All services in one docker-compose file
✅ Integrated with pipeline_network

### Key Implementation Details
- Uses Docker instead of systemd for service management
- Python 3.12 as recommended in docs
- Separate containers for zou and zou-events (required for websockets)
- Gunicorn workers properly configured:
  - `gevent` for main API (async)
  - `geventwebsocket` for event stream (websocket support)
- All required Python packages installed (gevent, geventwebsocket, flask-socketio)

## Troubleshooting

### Issue: Can't connect to Kitsu
- Check if all services are running: `docker compose ps`
- Check logs: `docker compose logs -f`
- Verify database is initialized: `./init-zou.sh`

### Issue: WebSocket connections failing
- Verify `zou-events` service is running
- Check nginx configuration points to `zou-events:5001`
- Check logs: `docker compose logs -f zou-events`

### Issue: Database connection errors
- Wait for PostgreSQL to be ready (takes ~5 seconds)
- Check environment variables in docker-compose.yml
- Verify database exists: `docker compose exec db psql -U zou -l`

### Issue: Preview uploads failing
- Check `PREVIEW_FOLDER` and `TMP_DIR` volumes are mounted
- Verify permissions on volumes
- Check disk space

## Production Considerations

⚠️ **This setup is for development only!** For production:

1. **Change default credentials**
   - Database password
   - SECRET_KEY
   - Admin user password

2. **Enable HTTPS**
   - Add SSL certificates
   - Update nginx configuration
   - Set `DOMAIN_PROTOCOL=https`

3. **Configure email**
   - Set MAIL_* environment variables
   - Configure SMTP server

4. **Resource limits**
   - Add CPU/memory limits to services
   - Scale workers based on load

5. **Backup strategy**
   - Regular database backups
   - Preview files backup
   - Monitor disk space

6. **External volumes**
   - Use named volumes or bind mounts for data
   - Consider S3/Swift for preview storage

## References

- [Zou Documentation](https://zou.cg-wire.com/)
- [Kitsu Documentation](https://kitsu.cg-wire.com/)
- [Zou Configuration](https://zou.cg-wire.com/configuration/)
- [Zou Events](https://zou.cg-wire.com/events/)
- [Gunicorn Documentation](https://docs.gunicorn.org/)
