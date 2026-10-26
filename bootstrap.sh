#!/usr/bin/env bash
# ==============================================================================
# bootstrap.sh - Master Orchestrator for riced-kubuntu-os (RKO)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/common.sh disable=SC1091
source "${SCRIPT_DIR}/scripts/lib/common.sh"

DRY_RUN=false
VERBOSE=false
TARGET_STAGE=""

print_usage() {
    echo -e "${BOLD}Usage:${NC} ./bootstrap.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -n, --dry-run        Simulate execution without modifying the host"
    echo "  -v, --verbose        Stream full command outputs live (instead of suppressing to log)"
    echo "  -s, --stage <00-04>  Run only a specific stage (e.g. 01, 03)"
    echo "  -h, --help           Show this help message"
    echo ""
    echo "Available Stages:"
    echo "  00 : Configure repositories & PPAs (scripts/00-repositories.sh)"
    echo "  01 : Install base APT packages (scripts/01-apt-core.sh)"
    echo "  02 : Install Flatpaks & Snaps (scripts/02-snaps-flatpaks.sh)"
    echo "  03 : Deploy dotfiles (scripts/03-dotfiles.sh)"
    echo "  04 : Apply KDE Plasma 6 configurations (scripts/04-plasma-theming.sh)"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -n|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -s|--stage)
            TARGET_STAGE="$2"
            shift 2
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

export DRY_RUN VERBOSE

# Configure central log destination
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/bootstrap-$(date +%Y%m%d-%H%M%S).log"
ln -sf "$(basename "${LOG_FILE}")" "${LOG_DIR}/latest.log"
export LOG_FILE

# Terminal hygiene and cleanup handler
cleanup() {
    local exit_code=$?
    if [[ -n "${SUDO_PID:-}" ]]; then
        kill "${SUDO_PID}" 2>/dev/null || true
    fi
    # Restore cursor visibility and terminal mode
    printf '\033[?25h\033[0m'
    stty echo 2>/dev/null || true
    # Drain any queued terminal escape sequence responses (such as ANSI CPR \e[<row>;<col>R)
    while read -r -t 0.05 -n 10000 _discard 2>/dev/null; do :; done
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# Pre-flight sudo authentication for privileged stages
needs_sudo=false
if [[ -z "${TARGET_STAGE}" ]] || [[ "${TARGET_STAGE}" =~ ^(00|01|02)$ ]]; then
    needs_sudo=true
fi

if [[ "${DRY_RUN}" == "false" && "${needs_sudo}" == "true" ]]; then
    echo -e "${ARROW} Administrative privileges required. Authenticating with sudo..."
    sudo -v || { log_error "Sudo authentication failed. Aborting."; exit 1; }
    # Keep sudo timestamp alive in background while script executes
    (while true; do sudo -n -v; sleep 50; done 2>/dev/null) &
    SUDO_PID=$!
fi

echo -e "${BOLD}${BLUE}=====================================================${NC}"
echo -e "${BOLD}${BLUE}   riced-kubuntu-os (RKO) Bootstrap Provisioner      ${NC}"
echo -e "${BOLD}${BLUE}=====================================================${NC}"

if [[ "${DRY_RUN}" == "true" ]]; then
    echo -e "  ${YELLOW}MODE:${NC} Dry-Run (simulating execution)"
else
    echo -e "  ${GREEN}MODE:${NC} Live Installation"
fi
echo -e "  ${DIM}Log File:   ${LOG_FILE}${NC}"
echo -e "  ${DIM}Stream Log: tail -f logs/latest.log${NC}"
echo -e "${BOLD}${BLUE}=====================================================${NC}"

STAGES=(
    "00:Software Repositories & PPAs:${SCRIPT_DIR}/scripts/00-repositories.sh"
    "01:Core APT Packages & Tools:${SCRIPT_DIR}/scripts/01-apt-core.sh"
    "02:Flatpak & Snap Applications:${SCRIPT_DIR}/scripts/02-snaps-flatpaks.sh"
    "03:Dotfiles, Shell & Font Stack:${SCRIPT_DIR}/scripts/03-dotfiles.sh"
    "04:KDE Plasma 6 Theming & Shortcuts:${SCRIPT_DIR}/scripts/04-plasma-theming.sh"
)

for item in "${STAGES[@]}"; do
    stage_id="$(echo "$item" | cut -d: -f1)"
    stage_name="$(echo "$item" | cut -d: -f2)"
    script_path="$(echo "$item" | cut -d: -f3)"

    if [[ -n "${TARGET_STAGE}" && "${TARGET_STAGE}" != "${stage_id}" ]]; then
        continue
    fi

    echo -e "\n${BOLD}${BLUE}[${stage_id}/04] ${stage_name}${NC}"
    extra_args=()
    [[ "${DRY_RUN}" == "true" ]] && extra_args+=("--dry-run")
    [[ "${VERBOSE}" == "true" ]] && extra_args+=("--verbose")

    bash "${script_path}" "${extra_args[@]}"
done

echo -e "\n${BOLD}${GREEN}=====================================================${NC}"
echo -e "${BOLD}${GREEN}   ✔ RKO Provisioning Finished Successfully!        ${NC}"
echo -e "${BOLD}${GREEN}=====================================================${NC}"
if [[ "${DRY_RUN}" == "false" ]]; then
    echo -e "Detailed logs saved to: ${LOG_FILE}"
    echo -e "Remember to restart your KDE Plasma session or log out/in to apply all desktop changes."
fi
