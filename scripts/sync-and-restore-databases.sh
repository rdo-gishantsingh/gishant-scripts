#!/bin/bash
# Sync and restore Ayon and Kitsu databases from hourly backup sources.
#
# Phase 1 – Copy: pulls the latest backup from /tech/backups/… into local staging dirs.
# Phase 2 – Restore Ayon: restores the copied backup into the local Ayon Docker stack.
# Phase 3 – Restore Kitsu: restores the copied backup into the local Kitsu Docker stack.
#
# Must run as root (to read the Kitsu hourly backup directory).
#
# Cron (12:30 AM daily):
#   30 0 * * * /home/gisi/dev/repos/gishant-scripts/scripts/sync-and-restore-databases.sh >> /home/gisi/dev/backups/sync-restore.log 2>&1
# Install: sudo crontab -e

set -e

################################################################################
# Configuration
################################################################################

# Staging: where the latest backup is held locally before restore
AYON_STAGING_DIR="/home/gisi/dev/backups/ayon"
KITSU_STAGING_DIR="/home/gisi/dev/backups/kitsu"

# Source: hourly backup directories on the backup mount
AYON_SOURCE_DIR="/tech/backups/database/ayon/1.12.0/hourly"
KITSU_SOURCE_DIR="/tech/backups/database/kitsu/0.20.51/hourly"

# Docker Compose directories (script changes into these to run docker compose)
AYON_COMPOSE_DIR="/home/gisi/dev/repos/gishant-scripts/src/gishant_scripts/ayon/ayon-server"
KITSU_COMPOSE_DIR="/home/gisi/dev/repos/gishant-scripts/src/gishant_scripts/kitsu/kitsu-server"

# Ayon database credentials
AYON_DB_SERVICE="db"
AYON_APP_SERVICE="server"
AYON_WORKER_SERVICE="worker"
AYON_DB_USER="ayon"
AYON_DB_NAME="ayon"

# Kitsu database credentials
KITSU_DB_SERVICE="db"
KITSU_APP_SERVICE="zou"
KITSU_FRONTEND_SERVICE="kitsu"
KITSU_DB_USER="zou"
KITSU_DB_NAME="zoudb"

################################################################################
# Guards
################################################################################

if [[ "$EUID" -ne 0 ]]; then
    echo "This script must run as root to access the Kitsu backup directory."
    exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0"
    echo ""
    echo "Copy the latest Ayon and Kitsu database backups from hourly sources"
    echo "and restore them into the local Docker Compose stacks."
    echo ""
    echo "Cron (12:30 AM daily):"
    echo "  30 0 * * * $0 >> /home/gisi/dev/backups/sync-restore.log 2>&1"
    echo ""
    echo "Install: sudo crontab -e"
    exit 0
fi

if ! docker compose version &>/dev/null; then
    echo "[ERROR] docker compose not found"
    exit 1
fi

# Check for pv (pipe viewer) – used to show restore progress.
# Install with: sudo apt install pv
USE_PV=false
if command -v pv &>/dev/null; then
    USE_PV=true
else
    echo "[WARNING] pv not found – restore will run without a progress bar"
    echo "[WARNING] Install with: sudo apt install pv"
fi

################################################################################
# Helpers
################################################################################

mkdir -p "$AYON_STAGING_DIR" "$KITSU_STAGING_DIR"

# Colors and Icons
NC='\033[0m'
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'

ICON_INFO="${BLUE}i${NC}"
ICON_SUCCESS="${GREEN}✓${NC}"
ICON_WARNING="${YELLOW}!${NC}"
ICON_ERROR="${RED}✗${NC}"

header()  { 
    echo -e "\n${BOLD}${CYAN}=== $* ===${NC}"
}

log()     { echo -e "  ${ICON_INFO}  $*"; }
success() { echo -e "  ${ICON_SUCCESS}  ${GREEN}$*${NC}"; }
warning() { echo -e "  ${ICON_WARNING}  ${YELLOW}$*${NC}"; }
error()   { echo -e "  ${ICON_ERROR}  ${RED}$*${NC}"; }

# Filter for transaction_timeout (PostgreSQL 17+ param unsupported by older versions)
FILTER_PG="sed '/SET transaction_timeout = 0;/d'"

format_size() {
    local size=$1
    if   [[ "$size" -ge 1073741824 ]]; then awk "BEGIN {printf \"%.2f GB\", $size/1073741824}"
    elif [[ "$size" -ge 1048576 ]];    then awk "BEGIN {printf \"%.2f MB\", $size/1048576}"
    elif [[ "$size" -ge 1024 ]];       then awk "BEGIN {printf \"%.2f KB\", $size/1024}"
    else echo "${size} B"
    fi
}

################################################################################
# Phase 1 – Copy latest backup to staging
################################################################################

# copy_latest_backup <source_dir> <dest_dir> <name>
# Returns 0 on success, 1 on failure.
copy_latest_backup() {
    local source_dir="$1"
    local dest_dir="$2"
    local name="$3"

    if [[ ! -d "$source_dir" ]]; then
        error "$name: Source directory does not exist: $source_dir"
        return 1
    fi

    local latest
    latest=$(find "$source_dir" -maxdepth 1 -type f \
        \( -name "*.sql.gz" -o -name "*.dump.gz" -o -name "*.dump" -o -name "*.backup" -o -name "*.sql" \) \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)

    if [[ -z "$latest" || ! -f "$latest" ]]; then
        error "$name: No backup file found in $source_dir"
        return 1
    fi

    # Clear staging dir and copy the new file
    mkdir -p "$dest_dir"
    find "$dest_dir" -maxdepth 1 -type f -delete 2>/dev/null || true

    local dest_file="$dest_dir/$(basename "$latest")"

    log "$name: Copying $(basename "$latest")..."
    if command -v rsync &>/dev/null; then
        rsync --human-readable --info=progress2 "$latest" "$dest_file"
    else
        cp "$latest" "$dest_file"
    fi

    chown gisi: "$dest_file"
    local size
    size=$(stat -c%s "$dest_file" 2>/dev/null)
    success "$name: Copied $(basename "$latest") ($(format_size "$size")) to $dest_dir"
}

################################################################################
# Phase 2/3 – Generic restore function
################################################################################

# restore_database \
#   <compose_dir> \
#   <staging_dir> \
#   <db_service> \
#   <db_user> \
#   <db_name> \
#   <app_services_csv>          (e.g. "server worker" or "zou kitsu") \
#   <schema_upgrade_service>    (empty string = skip) \
#   <label>
restore_database() {
    local compose_dir="$1"
    local staging_dir="$2"
    local db_service="$3"
    local db_user="$4"
    local db_name="$5"
    local app_services="$6"
    local schema_upgrade_service="$7"
    local label="$8"

    # log "====== Starting $label database restore ======"

    # ── Find latest staged backup ──────────────────────────────────────────
    local backup_file
    backup_file=$(find "$staging_dir" -maxdepth 1 -type f \
        \( -name "*.sql.gz" -o -name "*.dump.gz" -o -name "*.dump" -o -name "*.backup" -o -name "*.sql" \) \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)

    if [[ -z "$backup_file" || ! -f "$backup_file" ]]; then
        error "$label: No backup file found in $staging_dir – skipping restore"
        return 1
    fi

    local file_size
    file_size=$(stat -c%s "$backup_file" 2>/dev/null)
    
    if [[ "$file_size" -eq 0 ]]; then
        error "$label: Backup file $(basename "$backup_file") is 0 bytes! Skipping restore to prevent errors."
        return 1
    fi
    
    log "$label: Restoring from $(basename "$backup_file") ($(format_size "$file_size"))"

    # All docker compose commands run from inside the compose directory
    pushd "$compose_dir" > /dev/null

    # ── Stop application services ────────────────────────────────────────────
    log "$label: Stopping application services ($app_services)..."
    # shellcheck disable=SC2086
    docker compose stop $app_services || true

    # ── Ensure database container is running ───────────────────────────────────
    log "$label: Starting database service ($db_service)..."
    docker compose start "$db_service"
    sleep 5

    # ── Drop & recreate database ───────────────────────────────────────────
    log "$label: Terminating active connections to '$db_name'..."
    docker compose exec -T "$db_service" psql -U "$db_user" -d postgres \
        -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db_name' AND pid <> pg_backend_pid();" \
        > /dev/null 2>&1 || true

    log "$label: Dropping database '$db_name' (if exists)..."
    docker compose exec -T "$db_service" psql -U "$db_user" -d postgres \
        -c "DROP DATABASE IF EXISTS $db_name;"

    log "$label: Creating fresh database '$db_name'..."
    docker compose exec -T "$db_service" psql -U "$db_user" -d postgres \
        -c "CREATE DATABASE $db_name;"

    success "$label: Database is in clean state, starting restore..."

    # ── Restore ────────────────────────────────────────────────────────────────
    if [[ "$backup_file" == *.dump ]] || [[ "$backup_file" == *.dump.gz ]] || [[ "$backup_file" == *.backup ]] || [[ "$backup_file" == *.backup.gz ]]; then
        log "$label: Detected custom format – using pg_restore..."

        # Check whether the custom-format dump is gzip-compressed
        if file "$backup_file" | grep -q "gzip compressed"; then
            log "$label: Decompressing custom format dump first..."
            local temp_dump="/tmp/${label,,}_restore_temp.dump"
            if [[ "$USE_PV" == true ]]; then
                pv "$backup_file" | gunzip > "$temp_dump"
            else
                gunzip -c "$backup_file" > "$temp_dump"
            fi
            docker compose cp "$temp_dump" "${db_service}:/tmp/restore.dump"
            rm -f "$temp_dump"
        else
            docker compose cp "$backup_file" "${db_service}:/tmp/restore.dump"
        fi

        # Count total items in the dump for progress tracking
        local total_items
        total_items=$(docker compose exec -T "$db_service" \
            pg_restore -l /tmp/restore.dump 2>/dev/null | grep -c "^[0-9]")

        if [[ $INTERACTIVE -eq 1 ]] && [[ "$total_items" -gt 0 ]]; then
            log "$label: Restoring $total_items items with pg_restore..."

            # Run pg_restore with -v, parse stderr line count into a progress bar.
            # Each verbose line ~ one restored item. Stderr is piped through awk
            # which redraws a single terminal line with a bar and percentage.
            docker compose exec -T "$db_service" pg_restore \
                -U "$db_user" \
                -d "$db_name" \
                -j "$(nproc)" \
                -v \
                --no-owner \
                --no-acl \
                /tmp/restore.dump 2>&1 >/dev/null \
            | awk -v total="$total_items" '
                BEGIN { count = 0; bar_width = 30 }
                {
                    count++
                    pct = (count > total) ? 100 : int(count * 100 / total)
                    filled = int(pct * bar_width / 100)
                    empty = bar_width - filled
                    bar = ""
                    for (i = 0; i < filled; i++) bar = bar "#"
                    for (i = 0; i < empty;  i++) bar = bar "-"
                    printf "\r  Restoring: %d/%d items [%s] %d%%", count, total, bar, pct
                }
                END { printf "\n" }
            ' || true
        else
            # Non-interactive (cron) - run silently, log only errors
            log "$label: Restoring with pg_restore (non-interactive, errors only)..."
            docker compose exec -T "$db_service" pg_restore \
                -U "$db_user" \
                -d "$db_name" \
                -j "$(nproc)" \
                --no-owner \
                --no-acl \
                /tmp/restore.dump 2>&1 \
            | grep -i "error" || true
        fi

        docker compose exec -T "$db_service" rm /tmp/restore.dump

    elif [[ "$backup_file" == *.gz ]]; then
        log "$label: Detected gzip SQL format – streaming restore..."
        if [[ "$USE_PV" == true ]]; then
            pv "$backup_file" | gunzip | eval "$FILTER_PG" | docker compose exec -T "$db_service" psql -U "$db_user" -d "$db_name" -q
        else
            gunzip -c "$backup_file" | eval "$FILTER_PG" | docker compose exec -T "$db_service" psql -U "$db_user" -d "$db_name" -q
        fi

    else
        log "$label: Detected plain SQL format..."
        if [[ "$USE_PV" == true ]]; then
            pv "$backup_file" | eval "$FILTER_PG" | docker compose exec -T "$db_service" psql -U "$db_user" -d "$db_name" -q
        else
            eval "$FILTER_PG" < "$backup_file" | docker compose exec -T "$db_service" psql -U "$db_user" -d "$db_name" -q
        fi
    fi

    success "$label: Database restore completed"

    # ── Schema upgrade (Kitsu / zou only) ───────────────────────────────────
    if [[ -n "$schema_upgrade_service" ]]; then
        log "$label: Running schema upgrade ($schema_upgrade_service upgrade-db)..."
        docker compose run --rm "$schema_upgrade_service" zou upgrade-db || true
        success "$label: Schema upgrade completed"
    fi

    # ── Start application services ────────────────────────────────────────────
    log "$label: Starting application services ($app_services)..."
    # shellcheck disable=SC2086
    docker compose start $app_services

    popd > /dev/null

    # ── Clean up staging file ─────────────────────────────────────────────────
    log "$label: Removing staging file $(basename "$backup_file")..."
    rm -f "$backup_file"

    success "$label: Restore complete"
    echo ""
}

################################################################################
# Main
################################################################################

INTERACTIVE=0
[[ -t 1 ]] && INTERACTIVE=1

if [[ $INTERACTIVE -eq 1 ]]; then
    echo "Sync and restore databases (cron: 30 0 * * *)"
    echo ""
fi

log "Starting sync-and-restore-databases"

# ── Phase 1: Copy ───────────────────────────────────────────────────────────
header "Phase 1: Copying latest backups to staging"
AYON_COPY_OK=1
KITSU_COPY_OK=1

copy_latest_backup "$AYON_SOURCE_DIR" "$AYON_STAGING_DIR" "Ayon" || AYON_COPY_OK=0
copy_latest_backup "$KITSU_SOURCE_DIR" "$KITSU_STAGING_DIR" "Kitsu" || KITSU_COPY_OK=0
echo ""

# ── Phase 2: Restore Ayon ─────────────────────────────────────────────────
if [[ $AYON_COPY_OK -eq 1 ]]; then
    header "Phase 2: Restoring Ayon database"
    restore_database \
        "$AYON_COMPOSE_DIR" \
        "$AYON_STAGING_DIR" \
        "$AYON_DB_SERVICE" \
        "$AYON_DB_USER" \
        "$AYON_DB_NAME" \
        "$AYON_APP_SERVICE $AYON_WORKER_SERVICE" \
        "" \
        "Ayon"
else
    warning "Phase 2: Skipping Ayon restore (copy failed)"
fi

# ── Phase 3: Restore Kitsu ─────────────────────────────────────────────────
if [[ $KITSU_COPY_OK -eq 1 ]]; then
    header "Phase 3: Restoring Kitsu database"
    restore_database \
        "$KITSU_COMPOSE_DIR" \
        "$KITSU_STAGING_DIR" \
        "$KITSU_DB_SERVICE" \
        "$KITSU_DB_USER" \
        "$KITSU_DB_NAME" \
        "$KITSU_APP_SERVICE $KITSU_FRONTEND_SERVICE" \
        "$KITSU_APP_SERVICE" \
        "Kitsu"
else
    warning "Phase 3: Skipping Kitsu restore (copy failed)"
fi

header "sync-and-restore-databases complete"
