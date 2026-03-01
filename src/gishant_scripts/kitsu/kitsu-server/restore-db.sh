#!/bin/bash

################################################################################
# Kitsu Database Restore Script (Optimized with Progress Tracking)
# Enhanced with staging location and progress bars
################################################################################

set -e

# Configuration
DB_SERVICE="db"
APP_SERVICE="zou"
FRONTEND_SERVICE="kitsu"
DB_USER="zou"
DB_NAME="zoudb"
COMPOSE_FILE="docker-compose.yml"

# Staging Configuration
STAGING_DIR="/home/gisi/dev/backups/kitsu"
STAGING_FILE=""
CLEANUP_STAGING=true  # Set to false to keep staging files after restore

# Performance Configuration
PARALLEL_JOBS=0  # 0 = auto-detect cores, or set manually (e.g., 4)

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
progress() { echo -e "${CYAN}[PROGRESS]${NC} $1"; }

# Progress tracking variables
SPINNER_CHARS="|/-\\"
SPINNER_POS=0

# Progress helper functions
show_spinner() {
    local pid=$1
    local message=$2
    while kill -0 $pid 2>/dev/null; do
        SPINNER_POS=$(( (SPINNER_POS + 1) % 4 ))
        printf "\r${CYAN}[PROGRESS]${NC} $message ${SPINNER_CHARS:$SPINNER_POS:1}"
        sleep 0.1
    done
    printf "\r${CYAN}[PROGRESS]${NC} $message ✓\n"
}

format_size() {
    local size=$1
    if [ $size -ge 1073741824 ]; then
        echo "$(awk "BEGIN {printf \"%.2f\", $size/1073741824}") GB"
    elif [ $size -ge 1048576 ]; then
        echo "$(awk "BEGIN {printf \"%.2f\", $size/1048576}") MB"
    elif [ $size -ge 1024 ]; then
        echo "$(awk "BEGIN {printf \"%.2f\", $size/1024}") KB"
    else
        echo "${size} B"
    fi
}

check_pv() {
    if command -v pv &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Check Docker
if ! docker compose version &> /dev/null; then
    error "docker compose not found"
    exit 1
fi

# Check for pv (pipe viewer) for progress tracking
USE_PV=false
if check_pv; then
    USE_PV=true
    info "Using pv for progress tracking"
else
    warning "pv not found, using basic progress indicators"
    warning "Install pv for better progress tracking: sudo apt install pv"
fi

# Detect number of CPU cores
if [ "$PARALLEL_JOBS" -eq 0 ]; then
    PARALLEL_JOBS=$(nproc)
    info "Auto-detected $PARALLEL_JOBS CPU cores"
fi

# Ensure staging directory exists
if [ ! -d "$STAGING_DIR" ]; then
    info "Creating staging directory: $STAGING_DIR"
    mkdir -p "$STAGING_DIR"
    success "Staging directory created"
fi

# Args
if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file> [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --keep-staging  Keep staging files after restore (skip cleanup)"
    exit 1
fi
BACKUP_FILE="$1"

# Parse additional arguments
shift
while [ $# -gt 0 ]; do
    case "$1" in
        --keep-staging)
            CLEANUP_STAGING=false
            info "Staging files will be kept after restore"
            ;;
        *)
            warning "Unknown option: $1"
            ;;
    esac
    shift
done

if [ ! -f "$BACKUP_FILE" ]; then
    error "Backup file not found: $BACKUP_FILE"
    exit 1
fi

# Stage 1: Copy backup to staging location
stage_copy_to_staging() {
    progress "Stage 1/4: Copying backup to staging location..."

    local source_file="$1"
    local source_basename=$(basename "$source_file")
    STAGING_FILE="$STAGING_DIR/$source_basename"

    local source_size=$(stat -f%z "$source_file" 2>/dev/null || stat -c%s "$source_file" 2>/dev/null)
    local source_size_formatted=$(format_size $source_size)

    info "Source: $source_file ($source_size_formatted)"
    info "Destination: $STAGING_FILE"

    if [ "$USE_PV" = true ]; then
        pv "$source_file" > "$STAGING_FILE"
    else
        if command -v rsync &> /dev/null; then
            rsync --progress "$source_file" "$STAGING_FILE"
        else
            cp "$source_file" "$STAGING_FILE"
            progress "Copy completed"
        fi
    fi

    local dest_size=$(stat -f%z "$STAGING_FILE" 2>/dev/null || stat -c%s "$STAGING_FILE" 2>/dev/null)
    if [ "$source_size" -eq "$dest_size" ]; then
        success "Copy completed successfully ($source_size_formatted)"
    else
        error "Copy verification failed: source=$source_size, dest=$dest_size"
        exit 1
    fi
}

# Stage 2: Restore database
stage_restore_database() {
    progress "Stage 2/4: Restoring database..."

    local restore_file="$STAGING_FILE"

    if [[ "$restore_file" == *.dump ]] || [[ "$restore_file" == *.backup ]]; then
        info "Detected Custom Format (.dump/.backup). Using pg_restore..."

        # Check if it's compressed custom format
        if file "$restore_file" | grep -q "gzip compressed"; then
            warning "Custom format appears compressed. Decompressing first..."
            TEMP_DUMP="/tmp/kitsu_restore_temp.dump"

            if [ "$USE_PV" = true ]; then
                pv "$restore_file" | gunzip > "$TEMP_DUMP"
            else
                gunzip -c "$restore_file" > "$TEMP_DUMP"
                progress "Decompression completed"
            fi

            docker compose cp "$TEMP_DUMP" $DB_SERVICE:/tmp/restore.dump
            rm "$TEMP_DUMP"
        else
            info "Copying backup file to container..."
            local file_size=$(stat -f%z "$restore_file" 2>/dev/null || stat -c%s "$restore_file" 2>/dev/null)
            local file_size_formatted=$(format_size $file_size)
            info "File size: $file_size_formatted"
            docker compose cp "$restore_file" $DB_SERVICE:/tmp/restore.dump
            progress "File copied to container"
        fi

        # Use pg_restore with parallel jobs for faster restore
        if [ "$USE_PV" = true ]; then
            info "Restoring with pg_restore (progress shown by pg_restore)..."
        fi

        docker compose exec -T $DB_SERVICE pg_restore \
            -U $DB_USER \
            -d $DB_NAME \
            -j "$PARALLEL_JOBS" \
            -v \
            --no-owner \
            --no-acl \
            "/tmp/restore.dump" || true

        docker compose exec -T $DB_SERVICE rm /tmp/restore.dump

    elif [[ "$restore_file" == *.gz ]]; then
        info "Detected Gzip Format. Using streaming decompression..."

        if [ "$USE_PV" = true ]; then
            pv "$restore_file" | gunzip | \
                docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
        else
            gunzip -c "$restore_file" | \
                docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
        fi

    else
        info "Assuming Plain SQL. Using psql..."

        if [ "$USE_PV" = true ]; then
            pv "$restore_file" | \
                docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
        else
            cat "$restore_file" | \
                docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
        fi
    fi

    success "Database restore completed"
}

# Stage 3: Upgrade database schema
stage_upgrade_schema() {
    progress "Stage 3/4: Upgrading database schema..."

    info "Running zou upgrade-db..."
    docker compose run --rm "${APP_SERVICE}" zou upgrade-db || true

    success "Schema upgrade completed"
}

# Stage 4: Cleanup staging location
stage_cleanup_staging() {
    progress "Stage 4/4: Cleaning up staging location..."

    local files_removed=0
    local total_size_removed=0

    # Remove staging file (original backup copy)
    if [ -f "$STAGING_FILE" ]; then
        local file_size=$(stat -f%z "$STAGING_FILE" 2>/dev/null || stat -c%s "$STAGING_FILE" 2>/dev/null)
        rm -f "$STAGING_FILE"
        files_removed=$((files_removed + 1))
        total_size_removed=$((total_size_removed + file_size))
    fi

    if [ "$files_removed" -gt 0 ]; then
        local size_formatted=$(format_size $total_size_removed)
        success "Cleanup completed: $files_removed file(s) removed ($size_formatted)"
    else
        info "No files to clean up"
    fi
}

# Main execution flow
info "Starting Kitsu database restore process..."
info "Source backup: $BACKUP_FILE"
info "Staging location: $STAGING_DIR"

# Execute all stages
stage_copy_to_staging "$BACKUP_FILE"

# Stop App before restore to ensure clean state
info "Stopping Kitsu Services..."
docker compose stop $APP_SERVICE $FRONTEND_SERVICE || true

# Ensure DB is running
info "Ensuring Database is running..."
docker compose start $DB_SERVICE
sleep 5

# Drop and Create DB - ensuring clean state before restore
info "Preparing clean database state..."
info "Terminating all connections to database '$DB_NAME'..."
docker compose exec -T $DB_SERVICE psql -U $DB_USER -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true

info "Dropping existing database (if exists)..."
docker compose exec -T $DB_SERVICE psql -U $DB_USER -d postgres -c "DROP DATABASE IF EXISTS $DB_NAME;"

info "Creating fresh database..."
docker compose exec -T $DB_SERVICE psql -U $DB_USER -d postgres -c "CREATE DATABASE $DB_NAME;"

success "Database is now in clean state, ready for restore"

# Restore from staging file
stage_restore_database

# Upgrade schema
stage_upgrade_schema

# Start App
info "Starting Kitsu Services..."
docker compose start $APP_SERVICE $FRONTEND_SERVICE

# Cleanup staging location (if enabled)
if [ "$CLEANUP_STAGING" = true ]; then
    stage_cleanup_staging
else
    info "Skipping cleanup - staging files preserved at: $STAGING_DIR"
    if [ -n "$STAGING_FILE" ] && [ -f "$STAGING_FILE" ]; then
        local file_size=$(stat -f%z "$STAGING_FILE" 2>/dev/null || stat -c%s "$STAGING_FILE" 2>/dev/null)
        local file_size_formatted=$(format_size $file_size)
        info "Backup file available: $STAGING_FILE ($file_size_formatted)"
    fi
fi

success "Restore Complete"
success "Database restored successfully!"
