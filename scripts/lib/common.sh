#!/usr/bin/env bash
# ==============================================================================
# common.sh - Shared utility functions for RKO provisioning scripts
# ==============================================================================

# Formatting and Colors
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
CYAN="\033[0;36m"
DIM="\033[2m"
NC="\033[0m"

# TUI Symbols
TICK="${GREEN}✔${NC}"
CROSS="${RED}✖${NC}"
ARROW="${BLUE}➜${NC}"
WARN="${YELLOW}⚠${NC}"

# Logging Destination
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${REPO_ROOT}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/bootstrap.log}"

log_info() {
    echo -e "${ARROW} $*"
}

log_success() {
    echo -e "${TICK} $*"
}

log_warn() {
    echo -e "${WARN} $*"
}

log_error() {
    echo -e "${CROSS} $*" >&2
}

log_dry() {
    echo -e "  ${YELLOW}[DRY-RUN]${NC} Would execute: $*"
}

check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

# Run a task with an interactive spinner, suppressing verbose output to $LOG_FILE
spin_task() {
    local msg="$1"
    shift
    local cmd=("$@")

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo -e "  ${YELLOW}[DRY-RUN]${NC} ${msg}"
        return 0
    fi

    if [[ "${VERBOSE:-false}" == "true" ]]; then
        echo -e "  ${ARROW} ${msg}..."
        "${cmd[@]}" 2>&1 | tee -a "${LOG_FILE}"
        local status=${PIPESTATUS[0]}
        if [[ $status -eq 0 ]]; then
            echo -e "  ${TICK} ${msg}"
        else
            echo -e "  ${CROSS} ${msg} ${RED}(failed with code ${status})${NC}"
            return $status
        fi
        return 0
    fi

    # Check if stdout is an interactive terminal
    if [[ -t 1 ]]; then
        # Hide cursor
        printf '\033[?25l'
        # Execute command in background, redirecting output to LOG_FILE
        "${cmd[@]}" >> "${LOG_FILE}" 2>&1 &
        local pid=$!
        local spin_chars=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
        local i=0
        while kill -0 "$pid" 2>/dev/null; do
            printf "\r  ${CYAN}%s${NC} %s..." "${spin_chars[i]}" "$msg"
            i=$(( (i + 1) % 10 ))
            sleep 0.08
        done
        wait "$pid"
        local status=$?
        # Restore cursor
        printf '\033[?25h'
        if [[ $status -eq 0 ]]; then
            printf "\r\033[2K  ${TICK} %s\n" "$msg"
        else
            printf "\r\033[2K  ${CROSS} %s ${RED}(failed with code %s)${NC}\n" "$msg" "$status"
            echo -e "  ${RED}--- Last 20 lines of log (${LOG_FILE}) ---${NC}"
            tail -n 20 "${LOG_FILE}" 2>/dev/null | sed 's/^/    /'
            echo -e "  ${RED}--------------------------------------------${NC}"
            return $status
        fi
    else
        # Non-interactive / CI output
        echo -e "  ${ARROW} ${msg}..."
        "${cmd[@]}" >> "${LOG_FILE}" 2>&1
        local status=$?
        if [[ $status -eq 0 ]]; then
            echo -e "  ${TICK} ${msg}"
        else
            echo -e "  ${CROSS} ${msg} ${RED}(failed with code ${status})${NC}"
            tail -n 20 "${LOG_FILE}" 2>/dev/null | sed 's/^/    /'
            return $status
        fi
    fi
}

# Run command or simulate in dry-run mode
run_safe() {
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_dry "$*"
    else
        "$@"
    fi
}
