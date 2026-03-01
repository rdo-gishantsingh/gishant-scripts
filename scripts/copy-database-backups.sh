#!/bin/bash
# Copy latest Ayon and Kitsu database backups from hourly sources to local destinations.
# Keeps only one backup file per database in each destination.
# Must run as root to access /tech/backups/database/kitsu/0.20.51/hourly
#
# Cron (12:30 AM daily): 30 0 * * * /home/gisi/dev/repos/gishant-scripts/scripts/copy-database-backups.sh >> /home/gisi/dev/backups/copy.log 2>&1
# Install: sudo crontab -e

set -e

if [[ "$EUID" -ne 0 ]]; then
    echo "This script must run as root to access Kitsu backup directory."
    exit 1
fi

# Show cron info when run manually with -h/--help or when run interactively at start
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0 [options]"
    echo ""
    echo "Copy latest Ayon and Kitsu backups to local directories."
    echo ""
    echo "Cron (12:30 AM daily):"
    echo "  30 0 * * * /home/gisi/dev/repos/gishant-scripts/scripts/copy-database-backups.sh >> /home/gisi/dev/backups/copy.log 2>&1"
    echo ""
    echo "Install: sudo crontab -e"
    exit 0
fi

mkdir -p /home/gisi/dev/backups
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"
INTERACTIVE=0
[[ -t 1 ]] && INTERACTIVE=1

if [[ $INTERACTIVE -eq 1 ]]; then
    echo "Copy database backups (cron: 30 0 * * *)"
    echo ""
fi

copy_latest_backup() {
    local source_dir="$1"
    local dest_dir="$2"
    local name="$3"

    if [[ ! -d "$source_dir" ]]; then
        echo "$LOG_PREFIX $name: Source directory does not exist: $source_dir"
        return 1
    fi

    local latest
    latest=$(find "$source_dir" -maxdepth 1 -type f \
        \( -name "*.sql.gz" -o -name "*.dump.gz" -o -name "*.dump" -o -name "*.backup" -o -name "*.sql" \) \
        -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2-)

    if [[ -z "$latest" || ! -f "$latest" ]]; then
        echo "$LOG_PREFIX $name: No backup file found in $source_dir"
        return 1
    fi

    mkdir -p "$dest_dir"
    find "$dest_dir" -maxdepth 1 -type f -delete 2>/dev/null || true

    local dest_file="$dest_dir/$(basename "$latest")"
    local copy_ok=0

    if [[ $INTERACTIVE -eq 1 ]]; then
        echo "$LOG_PREFIX $name: Copying $(basename "$latest")..."
        if command -v rsync >/dev/null 2>&1; then
            # rsync gives reliable, continuously updating progress for local copies.
            if rsync --human-readable --info=progress2 "$latest" "$dest_file"; then
                copy_ok=1
            fi
        else
            # Fallback when rsync is unavailable.
            if cp "$latest" "$dest_file"; then
                copy_ok=1
            fi
        fi
    else
        if cp "$latest" "$dest_dir/"; then
            copy_ok=1
        fi
    fi

    if [[ $copy_ok -eq 1 ]]; then
        chown gisi: "$dest_file"
        echo "$LOG_PREFIX $name: Copied $(basename "$latest") to $dest_dir"
        return 0
    else
        echo "$LOG_PREFIX $name: Failed to copy $(basename "$latest")"
        return 1
    fi
}

copy_latest_backup "/tech/backups/database/ayon/1.12.0/hourly" "/home/gisi/dev/backups/ayon" "Ayon" || true
copy_latest_backup "/tech/backups/database/kitsu/0.20.51/hourly" "/home/gisi/dev/backups/kitsu" "Kitsu" || true
