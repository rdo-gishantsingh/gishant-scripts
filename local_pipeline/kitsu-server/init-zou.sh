#!/bin/bash

################################################################################
# Zou Database Initialization Script
#
# This script initializes the Zou database schema and creates initial data
# Run this after the first startup or when resetting the database
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

# Configuration
COMPOSE_FILE="docker-compose.yml"
ZOU_SERVICE="zou"

info "Initializing Zou database..."

# Wait for database to be ready
info "Waiting for database to be ready..."
sleep 5

# Initialize database schema
info "Creating database schema..."
if docker compose run --rm "$ZOU_SERVICE" zou init-db; then
    success "Database schema created successfully"
else
    error "Failed to create database schema"
    exit 1
fi

# Initialize base data (project status, task types, etc.)
info "Creating initial data..."
if docker compose run --rm "$ZOU_SERVICE" zou init-data; then
    success "Initial data created successfully"
else
    warning "Failed to create initial data (may already exist)"
fi

# Create admin user
info "Creating admin user..."
info "Default credentials: admin@example.com / mysecretpassword"
if docker compose run --rm "$ZOU_SERVICE" zou create-admin --password mysecretpassword admin@example.com; then
    success "Admin user created successfully"
else
    warning "Admin user may already exist"
fi

success "Zou initialization complete!"
echo ""
info "You can now access Kitsu at http://localhost:8090"
info "Login with: admin@example.com / mysecretpassword"
echo ""
warning "Remember to change the default password after first login!"
