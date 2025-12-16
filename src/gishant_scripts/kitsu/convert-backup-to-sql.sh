#!/bin/bash

################################################################################
# Backup Format Converter
#
# Converts PostgreSQL custom format backups to plain SQL format for compatibility
# This is useful when the backup was created with a newer PostgreSQL version
# than what's available in the target container.
#
# Usage:
#   ./convert-backup-to-sql.sh <input-backup.dump> [output-backup.sql]
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

if [ -z "$1" ]; then
    error "No backup file specified!"
    echo "Usage: $0 <input-backup.dump> [output-backup.sql]"
    exit 1
fi

INPUT_FILE="$1"
OUTPUT_FILE="${2:-${INPUT_FILE%.dump}.sql}"

if [ ! -f "$INPUT_FILE" ]; then
    error "Input file not found: $INPUT_FILE"
    exit 1
fi

# Check if output file already exists
if [ -f "$OUTPUT_FILE" ]; then
    warning "Output file already exists: $OUTPUT_FILE"
    read -p "Overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Conversion cancelled"
        exit 0
    fi
fi

echo ""
info "Converting PostgreSQL backup to plain SQL format..."
info "Input:  $INPUT_FILE"
info "Output: $OUTPUT_FILE"
echo ""

# Detect PostgreSQL version in backup
BACKUP_VERSION=$(strings "$INPUT_FILE" 2>/dev/null | grep -E "^[0-9]+\.[0-9]+" | head -1)
if [ -n "$BACKUP_VERSION" ]; then
    MAJOR_VERSION=$(echo "$BACKUP_VERSION" | cut -d. -f1)
    info "Backup created with PostgreSQL $BACKUP_VERSION"
else
    MAJOR_VERSION="17"
    warning "Could not detect PostgreSQL version, assuming 17"
fi

# Use PostgreSQL docker image matching the backup version
POSTGRES_IMAGE="postgres:${MAJOR_VERSION}-alpine"

info "Using Docker image: $POSTGRES_IMAGE"
info "Pulling image if needed..."

if ! docker pull "$POSTGRES_IMAGE" > /dev/null 2>&1; then
    error "Failed to pull Docker image: $POSTGRES_IMAGE"
    exit 1
fi

info "Converting backup (this may take a while)..."
echo ""

# Convert the backup using pg_restore in a container
if docker run --rm -i \
    -v "$(dirname "$(readlink -f "$INPUT_FILE")"):/backup:ro" \
    "$POSTGRES_IMAGE" \
    pg_restore --no-owner --no-acl --verbose -f - \
    "/backup/$(basename "$INPUT_FILE")" > "$OUTPUT_FILE" 2>&1; then

    echo ""
    success "Conversion completed successfully!"

    # Get file sizes
    INPUT_SIZE=$(du -h "$INPUT_FILE" | cut -f1)
    OUTPUT_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)

    info "Input file size:  $INPUT_SIZE"
    info "Output file size: $OUTPUT_SIZE"

    echo ""
    info "Next steps:"
    echo "  1. Optionally compress the SQL file:"
    echo "     gzip $OUTPUT_FILE"
    echo ""
    echo "  2. Restore the database:"
    echo "     ./restore-db.sh $OUTPUT_FILE"
    echo "     # or if compressed:"
    echo "     ./restore-db.sh ${OUTPUT_FILE}.gz"
    echo ""
else
    echo ""
    error "Conversion failed!"
    error "Check the error messages above for details"

    # Clean up partial output file
    if [ -f "$OUTPUT_FILE" ]; then
        rm -f "$OUTPUT_FILE"
        info "Removed partial output file"
    fi

    exit 1
fi


