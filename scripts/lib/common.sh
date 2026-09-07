#!/usr/bin/env bash
# ==============================================================================
# common.sh - Shared utility functions for KOS provisioning scripts
# ==============================================================================

# Formatting and Colors
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

log_dry() {
    echo -e "${YELLOW}[DRY-RUN]${NC} Would execute: $*"
}

check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

# Run command or simulate in dry-run mode
run_safe() {
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_dry "$*"
    else
        "$@"
    fi
}
