#!/bin/bash

################################################################################
# AYON Database Restore Script (Optimized with Parallel Processing)
# Enhanced with staging location and thumbnail removal
################################################################################

set -e

# Configuration
DB_SERVICE="db"
APP_SERVICE="server"
WORKER_SERVICE="worker"
DB_USER="ayon"
DB_NAME="ayon"
COMPOSE_FILE="docker-compose.yml"

# Staging Configuration
STAGING_DIR="/home/gisi/dev/backups/ayon"
STAGING_FILE=""
STAGING_SQL=""
CLEANUP_STAGING=true  # Set to false to keep staging files after restore
REMOVE_THUMBNAILS=true  # Set to false to skip thumbnail removal

# Performance Configuration
USE_PIGZ=true              # Use parallel gzip (pigz) instead of gzip/zcat
PARALLEL_JOBS=0            # 0 = auto-detect cores, or set manually (e.g., 4)
FILTER_ENABLED=false       # Set to true if you want to filter content
FILTER_PATTERNS=()         # Add patterns to exclude, e.g., ("unwanted_table" "logs_2023")

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

# Check for pigz if enabled
if [ "$USE_PIGZ" = true ]; then
    if ! command -v pigz &> /dev/null; then
        warning "pigz not found, falling back to standard gzip"
        warning "Install pigz for faster decompression: sudo apt install pigz"
        USE_PIGZ=false
    else
        info "Using pigz for parallel decompression"
    fi
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

# Ensure staging directory exists
if [ ! -d "$STAGING_DIR" ]; then
    info "Creating staging directory: $STAGING_DIR"
    mkdir -p "$STAGING_DIR"
    success "Staging directory created"
fi

# Detect number of CPU cores
if [ "$PARALLEL_JOBS" -eq 0 ]; then
    PARALLEL_JOBS=$(nproc)
    info "Auto-detected $PARALLEL_JOBS CPU cores"
fi

# Args
if [ -z "$1" ]; then
    echo "Usage: $0 <backup-file> [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --filter                Enable content filtering (configure FILTER_PATTERNS in script)"
    echo "  --keep-staging          Keep staging files after restore (skip cleanup)"
    echo "  --skip-thumbnail-removal Skip thumbnail removal stage"
    exit 1
fi
BACKUP_FILE="$1"

# Parse additional arguments
shift
while [ $# -gt 0 ]; do
    case "$1" in
        --filter)
            FILTER_ENABLED=true
            info "Content filtering enabled"
            ;;
        --keep-staging)
            CLEANUP_STAGING=false
            info "Staging files will be kept after restore"
            ;;
        --skip-thumbnail-removal)
            REMOVE_THUMBNAILS=false
            info "Thumbnail removal will be skipped"
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
    progress "Stage 1/5: Copying backup to staging location..."

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

# Stage 2: Extract backup if compressed
stage_extract_backup() {
    progress "Stage 2/5: Extracting backup..."

    if [[ "$STAGING_FILE" == *.gz ]]; then
        STAGING_SQL="${STAGING_FILE%.gz}"
        local file_size=$(stat -f%z "$STAGING_FILE" 2>/dev/null || stat -c%s "$STAGING_FILE" 2>/dev/null)

        info "Decompressing $STAGING_FILE..."

        if [ "$USE_PIGZ" = true ]; then
            if [ "$USE_PV" = true ]; then
                pv "$STAGING_FILE" | pigz -dc -p "$PARALLEL_JOBS" > "$STAGING_SQL"
            else
                pigz -dc -p "$PARALLEL_JOBS" "$STAGING_FILE" > "$STAGING_SQL"
                progress "Extraction completed"
            fi
        else
            if [ "$USE_PV" = true ]; then
                pv "$STAGING_FILE" | gunzip > "$STAGING_SQL"
            else
                gunzip -c "$STAGING_FILE" > "$STAGING_SQL"
                progress "Extraction completed"
            fi
        fi

        local sql_size=$(stat -f%z "$STAGING_SQL" 2>/dev/null || stat -c%s "$STAGING_SQL" 2>/dev/null)
        local sql_size_formatted=$(format_size $sql_size)
        success "Extraction completed ($sql_size_formatted)"
    else
        STAGING_SQL="$STAGING_FILE"
        info "Backup is not compressed, using as-is"
    fi
}

# Stage 3: Remove thumbnail binary data
stage_remove_thumbnails() {
    progress "Stage 3/5: Removing thumbnail binary data..."

    local input_file="$STAGING_SQL"
    local output_file="${STAGING_SQL}.cleaned"
    local temp_awk="/tmp/ayon_thumbnail_removal.awk"

    # Create AWK script for thumbnail removal
    cat > "$temp_awk" << 'AWK_EOF'
BEGIN {
    in_thumbnails = 0
    data_col_index = -1
    rows_processed = 0
    bytes_saved = 0
}

# Detect COPY statement for thumbnails table
/^COPY project_[^.]+\.thumbnails \(/ {
    in_thumbnails = 1
    # Parse column list to find data column index
    # Format: COPY project_xxx.thumbnails (id, mime, data, created_at, meta)
    # Extract column list between parentheses
    start = index($0, "(")
    end = index($0, ")")
    if (start > 0 && end > start) {
        col_list = substr($0, start + 1, end - start - 1)
        # Split by comma and find data column
        n = split(col_list, col_array, /,\s*/)
        for (i = 1; i <= n; i++) {
            # Trim whitespace
            gsub(/^[ \t]+|[ \t]+$/, "", col_array[i])
            if (col_array[i] == "data") {
                data_col_index = i
                break
            }
        }
    }
    print $0
    next
}

# Process data rows in thumbnails COPY block
in_thumbnails && !/^COPY/ && !/^\\\.$/ && NF > 0 {
    rows_processed++
    # Split by tab
    n = split($0, fields, "\t")
    if (data_col_index > 0 && data_col_index <= n) {
        # Calculate original size
        original_size = length(fields[data_col_index])
        # Replace with empty bytea (\x)
        fields[data_col_index] = "\\x"
        bytes_saved += original_size - 2
    }
    # Reconstruct line
    line = fields[1]
    for (i = 2; i <= n; i++) {
        line = line "\t" fields[i]
    }
    print line
    next
}

# Exit thumbnails block on \.
/^\\\.$/ {
    if (in_thumbnails) {
        in_thumbnails = 0
        data_col_index = -1
    }
    print $0
    next
}

# All other lines pass through
{
    print $0
}

END {
    # Print statistics to stderr so they don't go into the output file
    printf "ROWS_PROCESSED=%d\n", rows_processed > "/dev/stderr"
    printf "BYTES_SAVED=%d\n", bytes_saved > "/dev/stderr"
}
AWK_EOF

    info "Processing SQL file to remove thumbnail data..."

    local input_size=$(stat -f%z "$input_file" 2>/dev/null || stat -c%s "$input_file" 2>/dev/null)
    local input_size_formatted=$(format_size $input_size)
    info "Input size: $input_size_formatted"

    # Run AWK script
    local stats_output=$(mktemp)
    if [ "$USE_PV" = true ]; then
        pv "$input_file" | awk -f "$temp_awk" 2> "$stats_output" > "$output_file"
    else
        awk -f "$temp_awk" "$input_file" 2> "$stats_output" > "$output_file"
        progress "Processing completed"
    fi

    # Read statistics from stderr output
    local rows_processed=0
    local bytes_saved=0
    if [ -f "$stats_output" ]; then
        rows_processed=$(grep "^ROWS_PROCESSED=" "$stats_output" | cut -d= -f2)
        bytes_saved=$(grep "^BYTES_SAVED=" "$stats_output" | cut -d= -f2)
        rows_processed=${rows_processed:-0}
        bytes_saved=${bytes_saved:-0}
    fi
    rm -f "$stats_output" "$temp_awk"

    local output_size=$(stat -f%z "$output_file" 2>/dev/null || stat -c%s "$output_file" 2>/dev/null)
    local output_size_formatted=$(format_size $output_size)
    local saved_size_formatted=$(format_size ${bytes_saved:-0})

    if [ -n "$rows_processed" ] && [ "$rows_processed" -gt 0 ]; then
        success "Thumbnail removal completed"
        info "  Rows processed: $rows_processed"
        info "  Bytes saved: $saved_size_formatted"
        info "  Output size: $output_size_formatted"
    else
        warning "No thumbnail rows found or processed"
    fi

    # Replace original with cleaned version
    mv "$output_file" "$STAGING_SQL"
}

# Stage 4: Restore database
stage_restore_database() {
    progress "Stage 4/5: Restoring database..."

    local restore_file="$STAGING_SQL"

    # Compress cleaned SQL if it's large (optional optimization)
    if [[ "$restore_file" != *.gz ]] && [[ "$restore_file" != *.dump ]] && [[ "$restore_file" != *.backup ]]; then
        local file_size=$(stat -f%z "$restore_file" 2>/dev/null || stat -c%s "$restore_file" 2>/dev/null)
        # If file is larger than 100MB, consider compressing for faster transfer
        if [ "$file_size" -gt 104857600 ]; then
            info "File is large, compressing for faster transfer..."
            if [ "$USE_PIGZ" = true ]; then
                if [ "$USE_PV" = true ]; then
                    pv "$restore_file" | pigz -c -p "$PARALLEL_JOBS" > "${restore_file}.gz"
                else
                    pigz -c -p "$PARALLEL_JOBS" "$restore_file" > "${restore_file}.gz"
                fi
                restore_file="${restore_file}.gz"
            else
                if [ "$USE_PV" = true ]; then
                    pv "$restore_file" | gzip > "${restore_file}.gz"
                else
                    gzip -c "$restore_file" > "${restore_file}.gz"
                fi
                restore_file="${restore_file}.gz"
            fi
        fi
    fi

    if [[ "$restore_file" == *.dump ]] || [[ "$restore_file" == *.backup ]]; then
        info "Detected Custom Format (.dump/.backup). Using pg_restore..."

        # Check if it's compressed custom format
        if file "$restore_file" | grep -q "gzip compressed"; then
            warning "Custom format appears compressed. Decompressing first..."
            TEMP_DUMP="/tmp/ayon_restore_temp.dump"

            if [ "$USE_PIGZ" = true ]; then
                if [ "$USE_PV" = true ]; then
                    pv "$restore_file" | pigz -dc -p "$PARALLEL_JOBS" > "$TEMP_DUMP"
                else
                    pigz -dc -p "$PARALLEL_JOBS" "$restore_file" > "$TEMP_DUMP"
                fi
            else
                if [ "$USE_PV" = true ]; then
                    pv "$restore_file" | gunzip > "$TEMP_DUMP"
                else
                    gunzip -c "$restore_file" > "$TEMP_DUMP"
                fi
            fi

            docker compose cp "$TEMP_DUMP" $DB_SERVICE:/tmp/restore.dump
            rm "$TEMP_DUMP"
        else
            docker compose cp "$restore_file" $DB_SERVICE:/tmp/restore.dump
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
            "/tmp/restore.dump" || true

        docker compose exec -T $DB_SERVICE rm /tmp/restore.dump

    elif [[ "$restore_file" == *.gz ]]; then
        info "Detected Gzip Format. Using streaming decompression..."

        if [ "$USE_PIGZ" = true ]; then
            info "Using pigz with $PARALLEL_JOBS parallel threads"
            if [ "$USE_PV" = true ]; then
                pv "$restore_file" | pigz -dc -p "$PARALLEL_JOBS" | \
                    docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
            else
                pigz -dc -p "$PARALLEL_JOBS" "$restore_file" | \
                    docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
            fi
        else
            info "Using standard gunzip"
            if [ "$USE_PV" = true ]; then
                pv "$restore_file" | gunzip | \
                    docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
            else
                gunzip -c "$restore_file" | \
                    docker compose exec -T $DB_SERVICE psql -U $DB_USER -d $DB_NAME
            fi
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

# Stage 5: Cleanup staging location
stage_cleanup_staging() {
    progress "Stage 5/5: Cleaning up staging location..."

    local files_removed=0
    local total_size_removed=0

    # Remove staging file (original backup copy)
    if [ -f "$STAGING_FILE" ]; then
        local file_size=$(stat -f%z "$STAGING_FILE" 2>/dev/null || stat -c%s "$STAGING_FILE" 2>/dev/null)
        rm -f "$STAGING_FILE"
        files_removed=$((files_removed + 1))
        total_size_removed=$((total_size_removed + file_size))
    fi

    # Remove extracted SQL file if different from staging file
    if [ -n "$STAGING_SQL" ] && [ "$STAGING_SQL" != "$STAGING_FILE" ] && [ -f "$STAGING_SQL" ]; then
        local file_size=$(stat -f%z "$STAGING_SQL" 2>/dev/null || stat -c%s "$STAGING_SQL" 2>/dev/null)
        rm -f "$STAGING_SQL"
        files_removed=$((files_removed + 1))
        total_size_removed=$((total_size_removed + file_size))
    fi

    # Remove any compressed versions created during restore
    if [ -f "${STAGING_SQL}.gz" ]; then
        local file_size=$(stat -f%z "${STAGING_SQL}.gz" 2>/dev/null || stat -c%s "${STAGING_SQL}.gz" 2>/dev/null)
        rm -f "${STAGING_SQL}.gz"
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
info "Starting Ayon database restore process..."
info "Source backup: $BACKUP_FILE"
info "Staging location: $STAGING_DIR"

# Execute all stages
stage_copy_to_staging "$BACKUP_FILE"
stage_extract_backup

# Remove thumbnails if enabled
if [ "$REMOVE_THUMBNAILS" = true ]; then
    stage_remove_thumbnails
else
    info "Skipping thumbnail removal stage"
fi

# Stop App before restore to ensure clean state
info "Stopping AYON Server..."
docker compose stop $APP_SERVICE $WORKER_SERVICE || true

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

# Restore from cleaned file
stage_restore_database

# Start App
info "Starting AYON Server..."
docker compose start $APP_SERVICE $WORKER_SERVICE

# Cleanup staging location (if enabled)
if [ "$CLEANUP_STAGING" = true ]; then
    stage_cleanup_staging
else
    info "Skipping cleanup - staging files preserved at: $STAGING_DIR"
    if [ -n "$STAGING_SQL" ] && [ -f "$STAGING_SQL" ]; then
        local file_size=$(stat -f%z "$STAGING_SQL" 2>/dev/null || stat -c%s "$STAGING_SQL" 2>/dev/null)
        local file_size_formatted=$(format_size $file_size)
        info "Cleaned backup file available: $STAGING_SQL ($file_size_formatted)"
    fi
fi

success "Restore Complete"
success "Database restored successfully with thumbnail data removed!"