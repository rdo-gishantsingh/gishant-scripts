#!/bin/bash

################################################################################
# AYON Database Restore Script
################################################################################

set -e

# Configuration
DB_SERVICE="db"
APP_SERVICE="server"
WORKER_SERVICE="worker"
DB_USER="ayon"
DB_NAME="ayon"
COMPOSE_FILE="docker-compose.yml"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Helpers
info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check Docker
if ! docker compose version &> /dev/null; then
    error "docker compose not found"
    exit 1
fi

# Args
if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file>"
    exit 1
fi
BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Stop App
info "Stopping AYON Server..."
docker compose stop $APP_SERVICE $WORKER_SERVICE || true

# Ensure DB is running
info "Ensuring Database is running..."
docker compose start $DB_SERVICE
sleep 5

# Drop and Create DB
info "Recreating Database..."
# Terminate connections first
docker compose exec -T $DB_SERVICE psql -U $DB_USER -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
docker compose exec -T $DB_SERVICE psql -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"
docker compose exec -T $DB_SERVICE psql -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;"

# Restore
info "Restoring from $BACKUP_FILE..."

if [[ "$BACKUP_FILE" == *.dump ]] || [[ "$BACKUP_FILE" == *.backup ]]; then
    info "Detected Custom Format (.dump/.backup). Using pg_restore..."
    # Copy file to container for pg_restore
    docker compose cp "$BACKUP_FILE" $DB_SERVICE:/tmp/restore.dump
    docker compose exec -T $DB_SERVICE pg_restore -U $DB_USER -d $DB_NAME -v "/tmp/restore.dump" || true
    docker compose exec -T $DB_SERVICE rm /tmp/restore.dump
elif [[ "$BACKUP_FILE" == *.gz ]]; then
    info "Detected Gzip Format. Using zcat | psql..."
    zcat "$BACKUP_FILE" | docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
else
    info "Assuming Plain SQL. Using psql..."
    cat "$BACKUP_FILE" | docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
fi

# Start App
info "Starting AYON Server..."
docker compose start $APP_SERVICE $WORKER_SERVICE

success "Restore Complete"
