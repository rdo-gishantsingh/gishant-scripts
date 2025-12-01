#!/bin/bash
# Reset and populate both AYON and Kitsu with test data

set -e

# Load .env file if it exists
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "Loading environment variables from .env..."
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Configuration
PREFIX="${PREFIX:-test}"
PROJECTS="${PROJECTS:-2}"
SEQUENCES="${SEQUENCES:-10}"
SHOTS="${SHOTS:-10}"
TASKS="${TASKS:-3}"
USERS="${USERS:-5}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  AYON & Kitsu - Reset and Populate Test Data            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Configuration:${NC}"
echo -e "  Prefix:    ${GREEN}${PREFIX}${NC}"
echo -e "  Projects:  ${GREEN}${PROJECTS}${NC}"
echo -e "  Sequences: ${GREEN}${SEQUENCES}${NC}"
echo -e "  Shots:     ${GREEN}${SHOTS}${NC}"
echo -e "  Tasks:     ${GREEN}${TASKS}${NC}"
echo -e "  Users:     ${GREEN}${USERS}${NC}"
echo ""

# Check if bulk-data command is available
if ! command -v bulk-data &> /dev/null; then
    echo -e "${RED}Error: bulk-data command not found${NC}"
    echo -e "${YELLOW}Please install gishant-scripts package first:${NC}"
    echo -e "  cd /home/gisi/dev/repos/gishant-scripts"
    echo -e "  pip install -e ."
    exit 1
fi

# Check if environment variables are set
if [ -z "$AYON_SERVER_URL_LOCAL" ]; then
    echo -e "${RED}Error: AYON_SERVER_URL not set${NC}"
    echo -e "${YELLOW}Please set AYON environment variables${NC}"
    exit 1
fi

if [ -z "$KITSU_API_URL_LOCAL" ]; then
    echo -e "${RED}Error: KITSU_API_URL not set${NC}"
    echo -e "${YELLOW}Please set Kitsu environment variables${NC}"
    exit 1
fi

# Confirm before proceeding
echo -e "${YELLOW}⚠️  WARNING: This will delete ALL existing test data with prefix '${PREFIX}'${NC}"
echo -e "${YELLOW}             and generate fresh data in both AYON and Kitsu.${NC}"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${YELLOW}Operation cancelled.${NC}"
    exit 0
fi

# Run the reset and generate command
echo ""
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${CYAN}Starting reset and generate process...${NC}"
echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
echo ""

bulk-data reset-and-generate \
    --projects "$PROJECTS" \
    --sequences "$SEQUENCES" \
    --shots "$SHOTS" \
    --tasks "$TASKS" \
    --users "$USERS" \
    --prefix "$PREFIX" \
    --yes

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✓ Successfully reset and populated test data!          ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}Summary:${NC}"
    echo -e "  • Cleaned up all '${PREFIX}' prefixed data"
    echo -e "  • Generated ${GREEN}${PROJECTS}${NC} projects"
    echo -e "  • Generated ${GREEN}$((PROJECTS * SEQUENCES))${NC} sequences"
    echo -e "  • Generated ${GREEN}$((PROJECTS * SEQUENCES * SHOTS))${NC} shots"
    echo -e "  • Generated ${GREEN}$((PROJECTS * SEQUENCES * SHOTS * TASKS))${NC} tasks"
    echo -e "  • Created ${GREEN}${USERS}${NC} users"
    echo ""
else
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ✗ Error occurred during reset and populate             ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    exit 1
fi

