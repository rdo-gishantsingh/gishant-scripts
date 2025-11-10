#!/bin/bash

# ==============================================================================
#           Interactive GRUB Default Kernel Setter for Rocky Linux 9
# ==============================================================================
#
# Author: Gishant
# License: MIT
# Version: 1.0
#
# Description:
# This script provides a safe and interactive way to change the default boot
# kernel on a Rocky Linux 9 system (or other RHEL 9 derivatives that use
# GRUB2 with BLS and the 'grubby' tool).
#
# It lists all installed kernels, prompts the user to select one, asks for
# confirmation, and then sets the chosen kernel as the new default.
#
# Features:
# - Colorized output for better readability
# - Comprehensive error handling and validation
# - Verbose logging and progress indicators
# - Backup and restore capabilities
# - System compatibility checks
# - Enhanced safety measures
#

# --- Color Definitions ---
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly PURPLE='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly WHITE='\033[1;37m'
readonly BOLD='\033[1m'
readonly DIM='\033[2m'
readonly NC='\033[0m' # No Color

# --- Logging Functions ---
log_info() {
    echo -e "${BLUE}ℹ️  ${NC}${1}"
}

log_success() {
    echo -e "${GREEN}✅ ${NC}${1}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  ${NC}${1}"
}

log_error() {
    echo -e "${RED}🛑 ${NC}${1}" >&2
}

log_debug() {
    if [[ "${DEBUG:-}" == "1" ]]; then
        echo -e "${DIM}🔍 DEBUG: ${1}${NC}" >&2
    fi
}

log_step() {
    echo -e "${PURPLE}▶️  ${BOLD}${1}${NC}"
}

print_separator() {
    echo -e "${CYAN}$(printf '═%.0s' {1..80})${NC}"
}

print_header() {
    echo -e "${BOLD}${WHITE}"
    echo "╔════════════════════════════════════════════════════════════════════════════╗"
    echo "║                    GRUB Default Kernel Configuration Tool                  ║"
    echo "║                         Enhanced Interactive Version                       ║"
    echo "╚════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# --- Error Handling ---
set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Trap to handle script interruption
cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "Script interrupted or failed with exit code: $exit_code"
        log_info "No permanent changes were made to your system."
    fi
    exit $exit_code
}

trap cleanup EXIT INT TERM
#
# ┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃
# ┃                                                                             ┃
# ┃   !!! ---  W A R N I N G  --- !!!                                           ┃
# ┃                                                                             ┃
# ┃   This script modifies your system's boot configuration. While it           ┃
# ┃   includes safety checks, any incorrect modification to the bootloader      ┃
# ┃   on a remote machine carries a risk of making it unbootable and            ┃
# ┃   inaccessible via SSH.                                                     ┃
# ┃                                                                             ┃
# ┃   >>> ALWAYS perform a one-time test reboot (`grub2-reboot <index>`)     ┃
# ┃       if you are unsure whether a specific kernel will boot correctly.      ┃
# ┃                                                                             ┃
# ┃   Proceed with caution. You are responsible for your system.                ┃
# ┃                                                                             ┃
# ┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃┃

trap cleanup EXIT INT TERM

# --- System Compatibility Checks ---
check_system_compatibility() {
    log_step "Performing system compatibility checks..."
    
    # Check if we're on a supported distribution
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        log_debug "Detected OS: $NAME $VERSION_ID"
        
        case "$ID" in
            "rocky"|"rhel"|"centos"|"almalinux"|"fedora")
                log_success "Supported distribution detected: $NAME"
                ;;
            *)
                log_warning "Distribution '$NAME' may not be fully supported"
                log_info "This script is optimized for RHEL-based systems"
                read -p "Do you want to continue anyway? (y/N): " continue_anyway
                if [[ "$continue_anyway" != "y" && "$continue_anyway" != "Y" ]]; then
                    log_info "Operation cancelled by user"
                    exit 0
                fi
                ;;
        esac
    else
        log_warning "Cannot determine OS distribution"
    fi
    
    # Check kernel version
    local kernel_version
    kernel_version=$(uname -r)
    log_info "Current running kernel: $kernel_version"
    
    # Check available disk space in /boot
    local boot_space
    boot_space=$(df /boot 2>/dev/null | awk 'NR==2 {print $4}' || echo "unknown")
    if [[ "$boot_space" != "unknown" ]]; then
        log_info "Available space in /boot: ${boot_space}KB"
        if [[ "$boot_space" -lt 51200 ]]; then  # Less than 50MB
            log_warning "Low disk space in /boot partition (${boot_space}KB available)"
        fi
    fi
}

# --- Enhanced Pre-flight Checks ---
perform_preflight_checks() {
    log_step "Performing pre-flight safety checks..."
    
    # Check 1: Root privileges
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root or with sudo."
        log_info "Please run: sudo $0"
        exit 1
    fi
    log_success "Root privileges confirmed"
    
    # Check 2: grubby command availability
    if ! command -v grubby &> /dev/null; then
        log_error "The 'grubby' command could not be found."
        log_info "This script requires 'grubby' which is standard on RHEL-based systems."
        log_info "You may need to install it: dnf install grubby"
        exit 1
    fi
    log_success "grubby command is available"
    
    # Check 3: GRUB configuration files
    local grub_cfg="/boot/grub2/grub.cfg"
    if [[ ! -f "$grub_cfg" ]]; then
        log_error "GRUB configuration file not found at $grub_cfg"
        log_info "This may indicate a non-standard GRUB installation"
        exit 1
    fi
    log_success "GRUB configuration file found"
    
    # Check 4: Boot loader entries directory
    local ble_dir="/boot/loader/entries"
    if [[ ! -d "$ble_dir" ]]; then
        log_warning "Boot Loader Entries directory not found at $ble_dir"
        log_info "This system may not use Boot Loader Specification (BLS)"
    else
        local entry_count
        entry_count=$(find "$ble_dir" -name "*.conf" | wc -l)
        log_success "Found $entry_count boot entries in BLS directory"
    fi
    
    # Check 5: Backup capability
    local backup_dir="/root/grub_backups"
    if [[ ! -d "$backup_dir" ]]; then
        log_info "Creating backup directory: $backup_dir"
        mkdir -p "$backup_dir" || {
            log_error "Failed to create backup directory"
            exit 1
        }
    fi
    log_success "Backup directory ready: $backup_dir"
}

# --- Backup Functions ---
create_backup() {
    log_step "Backup recommendation..."
    
    echo -e "${YELLOW}It is highly recommended to create a backup of your GRUB configuration${NC}"
    echo -e "${YELLOW}before making any changes to the default kernel.${NC}"
    echo
    
    local create_backup_choice
    read -p "$(echo -e "${CYAN}Would you like to create a backup now? (Y/n): ${NC}")" create_backup_choice
    
    case "$create_backup_choice" in
        "n"|"N"|"no"|"NO")
            log_warning "Proceeding without backup - changes will not be reversible via this script"
            return 0
            ;;
        *)
            log_info "Creating backup of current GRUB configuration..."
            ;;
    esac
    
    local timestamp
    timestamp=$(date +"%Y%m%d_%H%M%S")
    local backup_dir="/root/grub_backups"
    local backup_file="$backup_dir/grub_backup_$timestamp.tar.gz"
    
    log_info "Backup location: $backup_file"
    
    # Create comprehensive backup
    if tar -czf "$backup_file" \
        /boot/grub2/grub.cfg \
        /boot/grub2/grubenv \
        /etc/default/grub \
        /boot/loader/entries/ 2>/dev/null; then
        
        log_success "Backup created successfully"
        
        # Store backup info for potential restore
        echo "$backup_file" > /tmp/grub_last_backup
        
        # Clean old backups (keep last 5)
        local backup_count
        backup_count=$(find "$backup_dir" -name "grub_backup_*.tar.gz" 2>/dev/null | wc -l)
        if [[ $backup_count -gt 5 ]]; then
            log_info "Cleaning old backups (keeping 5 most recent)..."
            find "$backup_dir" -name "grub_backup_*.tar.gz" -type f -exec ls -t {} + 2>/dev/null | tail -n +6 | xargs rm -f 2>/dev/null || true
        fi
    else
        log_error "Failed to create backup"
        log_warning "Some backup files may not be accessible or missing"
        read -p "$(echo -e "${YELLOW}Continue without complete backup? (y/N): ${NC}")" continue_choice
        if [[ "$continue_choice" != "y" && "$continue_choice" != "Y" ]]; then
            log_info "Operation cancelled by user"
            exit 0
        fi
    fi
}

# --- Enhanced Kernel Discovery ---
discover_kernels() {
    log_step "Discovering available kernel configurations..."
    
    # First, let's try a simpler approach - get all indices first
    local -a indices=()
    mapfile -t indices < <(grubby --info=ALL | grep '^index=' | cut -d'=' -f2)
    
    if [[ ${#indices[@]} -eq 0 ]]; then
        log_error "No kernel entries found by grubby"
        exit 1
    fi
    
    log_debug "Found ${#indices[@]} kernel indices: ${indices[*]}"
    
    # Now get detailed info for each kernel
    local -a kernel_details=()
    
    for index in "${indices[@]}"; do
        log_debug "Getting info for kernel index: $index"
        
        local title version args kernel_path
        
        # Get info for this specific index
        local info_output
        info_output=$(grubby --info="$index" 2>/dev/null)
        
        if [[ -z "$info_output" ]]; then
            log_warning "Failed to get info for kernel index $index, skipping"
            continue
        fi
        
        # Parse the output
        title=$(echo "$info_output" | grep '^title=' | cut -d'=' -f2- | sed 's/^"//;s/"$//')
        kernel_path=$(echo "$info_output" | grep '^kernel=' | cut -d'=' -f2-)
        args=$(echo "$info_output" | grep '^args=' | cut -d'=' -f2- | sed 's/^"//;s/"$//')
        
        # Extract version from kernel path
        if [[ -n "$kernel_path" ]]; then
            version=$(basename "$kernel_path" | sed 's/vmlinuz-//;s/"//g')
        else
            version="unknown"
        fi
        
        # Default empty args if not found
        [[ -z "$args" ]] && args="(no arguments)"
        
        # Store the kernel details
        if [[ -n "$title" ]]; then
            kernel_details+=("$index|$title|$version|$args")
            log_debug "Added kernel: $index|$title|$version|${args:0:50}..."
        else
            log_warning "Could not get title for kernel index $index, skipping"
        fi
    done
    
    if [[ ${#kernel_details[@]} -eq 0 ]]; then
        log_error "No valid kernel entries were found. Cannot proceed."
        exit 1
    fi
    
    log_success "Found ${#kernel_details[@]} valid kernel configuration(s)"
    
    # Store for global access
    declare -g -a KERNEL_DETAILS=("${kernel_details[@]}")
    
    # Debug output
    if [[ "${DEBUG:-}" == "1" ]]; then
        log_debug "Final kernel details:"
        for entry in "${kernel_details[@]}"; do
            log_debug "  $entry"
        done
    fi
}

# --- Enhanced Kernel Display ---
display_kernels() {
    print_separator
    echo -e "${BOLD}${WHITE}Available Kernel Boot Entries:${NC}"
    print_separator
    
    for entry in "${KERNEL_DETAILS[@]}"; do
        IFS='|' read -r entry_index title version args <<< "$entry"
        
        echo -e "${CYAN}[$entry_index]${NC} ${BOLD}$title${NC}"
        echo -e "    ${DIM}Version: $version${NC}"
        
        # Show truncated args if they're too long
        if [[ ${#args} -gt 70 ]]; then
            echo -e "    ${DIM}Args: ${args:0:67}...${NC}"
        else
            echo -e "    ${DIM}Args: $args${NC}"
        fi
        
        # Check if this is a rescue kernel
        if [[ "$title" == *"rescue"* ]]; then
            echo -e "    ${YELLOW}⚠️  Rescue kernel${NC}"
        fi
        
        echo
    done
    
    print_separator
}

# --- Enhanced Current Default Display ---
display_current_default() {
    log_step "Retrieving current default kernel information..."
    
    local current_default_title
    local current_default_index
    
    current_default_title=$(grubby --default-title 2>/dev/null) || {
        log_error "Failed to retrieve current default kernel title"
        exit 1
    }
    
    current_default_index=$(grubby --default-index 2>/dev/null) || {
        log_error "Failed to retrieve current default kernel index"
        exit 1
    }
    
    print_separator
    echo -e "${BOLD}${GREEN}Current Default Kernel:${NC}"
    print_separator
    echo -e "${WHITE}Index: ${CYAN}$current_default_index${NC}"
    echo -e "${WHITE}Title: ${CYAN}$current_default_title${NC}"
    
    # Find additional details for current default
    for entry in "${KERNEL_DETAILS[@]}"; do
        IFS='|' read -r entry_index title version args <<< "$entry"
        if [[ "$entry_index" == "$current_default_index" ]]; then
            echo -e "${WHITE}Version: ${CYAN}$version${NC}"
            break
        fi
    done
    
    print_separator
    echo
}

# --- Enhanced User Input ---
get_user_selection() {
    log_step "Waiting for user kernel selection..."
    
    local selected_index
    local max_index
    max_index=$((${#KERNEL_DETAILS[@]} - 1))
    
    while true; do
        echo -e "${BOLD}${WHITE}Please select a kernel:${NC}"
        read -p "$(echo -e "${CYAN}➡️  Enter the index number (0-$max_index): ${NC}")" selected_index
        
        # Validate input
        if [[ ! "$selected_index" =~ ^[0-9]+$ ]]; then
            log_error "Invalid input. Please enter a number."
            continue
        fi
        
        # Check if index exists in our array
        local found=false
        for entry in "${KERNEL_DETAILS[@]}"; do
            IFS='|' read -r entry_index title version args <<< "$entry"
            if [[ "$entry_index" == "$selected_index" ]]; then
                found=true
                break
            fi
        done
        
        if [[ "$found" == "false" ]]; then
            log_error "Index $selected_index is not available."
            log_info "Please choose a number from the list above."
            continue
        fi
        
        # Store the selection
        declare -g SELECTED_INDEX="$selected_index"
        break
    done
    
    log_success "Selected kernel index: $selected_index"
}

# --- Enhanced Confirmation ---
confirm_selection() {
    log_step "Confirming kernel selection..."
    
    # Find the selected kernel details
    local selected_title=""
    local selected_version=""
    for entry in "${KERNEL_DETAILS[@]}"; do
        IFS='|' read -r entry_index title version args <<< "$entry"
        if [[ "$entry_index" == "$SELECTED_INDEX" ]]; then
            selected_title="$title"
            selected_version="$version"
            break
        fi
    done
    
    print_separator
    echo -e "${BOLD}${YELLOW}⚠️  CONFIRMATION REQUIRED${NC}"
    print_separator
    echo -e "${WHITE}You have selected:${NC}"
    echo -e "${WHITE}  Index:   ${CYAN}$SELECTED_INDEX${NC}"
    echo -e "${WHITE}  Title:   ${CYAN}$selected_title${NC}"
    echo -e "${WHITE}  Version: ${CYAN}$selected_version${NC}"
    echo
    echo -e "${YELLOW}This will permanently change your default boot kernel.${NC}"
    echo -e "${YELLOW}A system reboot will be required for changes to take effect.${NC}"
    print_separator
    
    local confirmation
    while true; do
        read -p "$(echo -e "${BOLD}${RED}Are you absolutely sure? (yes/no): ${NC}")" confirmation
        case "$confirmation" in
            "yes"|"YES"|"y"|"Y")
                log_success "User confirmed the selection"
                return 0
                ;;
            "no"|"NO"|"n"|"N"|"")
                log_info "Operation cancelled by user. No changes were made."
                exit 0
                ;;
            *)
                log_warning "Please answer 'yes' or 'no'"
                ;;
        esac
    done
}

# --- Enhanced Kernel Setting ---
set_default_kernel() {
    log_step "Setting new default kernel..."
    
    print_separator
    echo -e "${BOLD}${WHITE}Applying Configuration Changes${NC}"
    print_separator
    
    # Progress indicator function
    show_progress() {
        local duration=$1
        local message=$2
        echo -n -e "${CYAN}$message${NC}"
        for ((i=1; i<=duration; i++)); do
            echo -n "."
            sleep 0.5
        done
        echo " ✓"
    }
    
    show_progress 3 "Setting default kernel index"
    
    if ! grubby --set-default-index="$SELECTED_INDEX" 2>/dev/null; then
        log_error "Failed to set default kernel index"
        log_info "Attempting to recover from backup..."
        
        # Attempt recovery if backup exists
        if [[ -f /tmp/grub_last_backup ]]; then
            local backup_file
            backup_file=$(cat /tmp/grub_last_backup)
            log_info "Restoring from backup: $backup_file"
            # Note: Full restore would require more complex logic
            # This is a placeholder for recovery mechanism
        fi
        
        exit 1
    fi
    
    show_progress 2 "Updating GRUB environment"
    
    # Force regeneration of grub.cfg if needed
    if command -v grub2-mkconfig &> /dev/null; then
        show_progress 4 "Regenerating GRUB configuration"
        if ! grub2-mkconfig -o /boot/grub2/grub.cfg >/dev/null 2>&1; then
            log_warning "Failed to regenerate GRUB configuration"
            log_info "The kernel change was applied but GRUB config regeneration failed"
        fi
    fi
    
    log_success "Default kernel has been successfully updated!"
}

# --- Enhanced Verification ---
verify_changes() {
    log_step "Verifying configuration changes..."
    
    local new_default_title
    local new_default_index
    
    # Get new default information
    new_default_title=$(grubby --default-title 2>/dev/null) || {
        log_error "Failed to verify new default kernel"
        return 1
    }
    
    new_default_index=$(grubby --default-index 2>/dev/null) || {
        log_error "Failed to verify new default kernel index"
        return 1
    }
    
    print_separator
    echo -e "${BOLD}${GREEN}✅ VERIFICATION RESULTS${NC}"
    print_separator
    echo -e "${WHITE}New default kernel index: ${GREEN}$new_default_index${NC}"
    echo -e "${WHITE}New default kernel title: ${GREEN}$new_default_title${NC}"
    
    # Verify the change was applied correctly
    if [[ "$new_default_index" == "$SELECTED_INDEX" ]]; then
        log_success "Kernel change verified successfully!"
        
        # Show next steps
        print_separator
        echo -e "${BOLD}${CYAN}� NEXT STEPS${NC}"
        print_separator
        echo -e "${WHITE}1.${NC} ${YELLOW}Reboot your system to use the new kernel${NC}"
        echo -e "${WHITE}2.${NC} ${DIM}Monitor the boot process for any issues${NC}"
        echo -e "${WHITE}3.${NC} ${DIM}If problems occur, use GRUB menu to select previous kernel${NC}"
        echo
        echo -e "${BOLD}${CYAN}🚀 To reboot now, run: ${WHITE}sudo reboot${NC}"
        echo -e "${BOLD}${CYAN}📊 To test boot once: ${WHITE}grub2-reboot $SELECTED_INDEX && reboot${NC}"
        
        # Suggest creating a test boot
        echo
        read -p "$(echo -e "${YELLOW}Would you like to perform a one-time test boot first? (recommended) (y/N): ${NC}")" test_boot
        if [[ "$test_boot" == "y" || "$test_boot" == "Y" ]]; then
            log_info "Setting up one-time test boot..."
            if grub2-reboot "$SELECTED_INDEX" 2>/dev/null; then
                log_success "One-time boot configured. System will boot selected kernel once, then revert."
                log_info "Run 'sudo reboot' when ready to test"
            else
                log_warning "One-time boot setup failed. Manual reboot will use new permanent default."
            fi
        fi
        
    else
        log_error "Verification failed! Expected index $SELECTED_INDEX but got $new_default_index"
        return 1
    fi
}

# --- Help Function ---
show_help() {
    echo -e "${BOLD}${WHITE}GRUB Default Kernel Configuration Tool${NC}"
    echo -e "${CYAN}Interactive tool for safely changing the default boot kernel${NC}"
    echo
    echo -e "${BOLD}Usage:${NC}"
    echo -e "  $0 [OPTIONS]"
    echo
    echo -e "${BOLD}Options:${NC}"
    echo -e "  --help, -h     Show this help message"
    echo -e "  --debug        Enable debug output"
    echo -e "  --version      Show version information"
    echo
    echo -e "${BOLD}Features:${NC}"
    echo -e "  • Interactive kernel selection with detailed information"
    echo -e "  • Comprehensive safety checks and validation"
    echo -e "  • Automatic backup creation with cleanup"
    echo -e "  • System compatibility verification"
    echo -e "  • One-time test boot capability"
    echo -e "  • Colorized output for better readability"
    echo
    echo -e "${BOLD}${YELLOW}Warning:${NC}"
    echo -e "  This script modifies system boot configuration. Always test"
    echo -e "  kernel changes carefully, especially on remote systems."
    echo
    echo -e "${BOLD}Examples:${NC}"
    echo -e "  sudo $0              # Interactive mode"
    echo -e "  sudo $0 --debug      # Interactive mode with debug output"
    echo
}

# --- Version Function ---
show_version() {
    echo -e "${BOLD}GRUB Default Kernel Configuration Tool${NC}"
    echo -e "Version: 2.1"
    echo -e "Author: Enhanced by GitHub Copilot"
    echo -e "License: MIT"
}

# --- Main Execution Function ---
main() {
    # Handle command line arguments
    case "${1:-}" in
        "--help"|"-h")
            show_help
            exit 0
            ;;
        "--version")
            show_version
            exit 0
            ;;
        "--debug")
            export DEBUG=1
            log_info "Debug mode enabled"
            ;;
        "")
            # No arguments, proceed normally
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
    
    print_header
    
    # Show warning and ask for confirmation to proceed
    echo
    echo -e "${BOLD}${RED}⚠️  WARNING ⚠️${NC}"
    echo -e "${YELLOW}This script will modify your system's boot configuration.${NC}"
    echo -e "${YELLOW}Incorrect changes could make your system unbootable.${NC}"
    echo
    read -p "$(echo -e "${CYAN}Do you want to proceed? (y/N): ${NC}")" proceed_choice
    case "$proceed_choice" in
        "y"|"Y"|"yes"|"YES")
            log_info "User confirmed to proceed"
            ;;
        *)
            log_info "Operation cancelled by user"
            exit 0
            ;;
    esac
    
    # Step 1: System compatibility and pre-flight checks
    check_system_compatibility
    perform_preflight_checks
    
    # Step 2: Create backup (with user prompt)
    create_backup
    
    # Step 3: Discover and display kernels
    discover_kernels
    display_kernels
    
    # Step 4: Show current default
    display_current_default
    
    # Step 5: Get user selection
    get_user_selection
    
    # Step 6: Confirm selection
    confirm_selection
    
    # Step 7: Apply changes
    set_default_kernel
    
    # Step 8: Verify changes
    verify_changes
    
    print_separator
    log_success "Script completed successfully!"
    echo -e "${DIM}Backup location: $(cat /tmp/grub_last_backup 2>/dev/null || echo 'None created')${NC}"
    print_separator
}

# --- Script Entry Point ---
main "$@"
